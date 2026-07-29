"""
Orita + LangGraph — Scheduling Agent Graph

A scheduling agent implemented as a LangGraph StateGraph that
routes between understanding the user's request, finding providers,
checking availability, and confirming bookings.

Requirements:
    pip install orita-sdk langgraph langchain-openai langchain-core

Usage:
    export ORITA_API_KEY=orita_xxx
    export OPENAI_API_KEY=sk-xxx
    python langgraph_orita.py
"""

import json
import os
from datetime import date, timedelta
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from orita import OritaClient, OritaError

# ── Orita client ──────────────────────────────────────────────────────────────

orita = OritaClient(api_key=os.environ["ORITA_API_KEY"])
PROVIDER_ID: str | None = os.environ.get("ORITA_PROVIDER_ID", None)

# ── Tools ─────────────────────────────────────────────────────────────────────


@tool
def find_providers(specialty: str = "") -> str:
    """
    Find available healthcare professionals. Filter by specialty (optional).

    Args:
        specialty: Medical specialty to filter by (e.g. "psychology", "cardiology").

    Returns a list of providers with their IDs and specialties.
    """
    try:
        pros = orita.professionals(specialty=specialty or None)
        if not pros:
            return json.dumps({"providers": [], "message": "No providers found."})
        result = [
            {
                "id": p["id"],
                "name": f"{p.get('name', '')} {p.get('lastname', '')}".strip(),
                "specialty": p.get("specialty") or p.get("profession") or "General",
            }
            for p in pros
        ]
        return json.dumps({"providers": result})
    except OritaError as e:
        return json.dumps({"error": str(e)})


@tool
def check_slots(event_type_id: str, date_str: str, provider_id: str = "") -> str:
    """
    Check available appointment slots for a given date.

    Args:
        event_type_id: The event type ID to check availability for.
        date_str: Date in YYYY-MM-DD format.
        provider_id: Optional professional/provider ID.

    Returns a list of available time slots.
    """
    try:
        pid = provider_id or PROVIDER_ID or None
        slots = orita.slots(event_type_id=event_type_id, date=date_str, provider_id=pid)
        return json.dumps({
            "date": date_str,
            "slots": [{"label": s["label"], "value": s["value"]} for s in slots],
            "count": len(slots),
        })
    except OritaError as e:
        return json.dumps({"error": str(e), "slots": []})


@tool
def confirm_booking(
    event_type_id: str,
    date_str: str,
    time_str: str,
    client_name: str,
    client_lastname: str,
    client_email: str,
    notes: str = "",
    provider_id: str = "",
) -> str:
    """
    Confirm and create an appointment booking.

    Args:
        event_type_id: The event type ID.
        date_str: Date in YYYY-MM-DD format.
        time_str: Time in HH:MM 24h format.
        client_name: Patient's first name.
        client_lastname: Patient's last name.
        client_email: Patient's email address.
        notes: Optional notes or reason for visit.
        provider_id: Optional provider ID.

    Returns the booking confirmation with ID and status.
    """
    try:
        pid = provider_id or PROVIDER_ID or None
        booking = orita.book(
            event_type_id=event_type_id,
            date=date_str,
            time=time_str,
            client_name=client_name,
            client_lastname=client_lastname,
            client_email=client_email,
            notes=notes or None,
            provider_id=pid,
        )
        return json.dumps({
            "success": True,
            "booking_id": booking["id"],
            "status": booking["status"],
            "date": booking.get("date", date_str),
            "time": booking.get("time", time_str),
            "patient": f"{client_name} {client_lastname}",
        })
    except OritaError as e:
        return json.dumps({"success": False, "error": str(e)})


# ── State ─────────────────────────────────────────────────────────────────────

orita_tools = [find_providers, check_slots, confirm_booking]
tool_map = {t.name: t for t in orita_tools}

TODAY = date.today().isoformat()
NEXT_MONDAY = (date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)).isoformat()

# Pre-fetch event types to inject into system prompt
try:
    _event_types = orita.event_types(provider_id=PROVIDER_ID)
    _et_info = json.dumps([{"id": e["id"], "title": e["title"]} for e in _event_types], indent=2)
except OritaError:
    _et_info = "[]"

SYSTEM_PROMPT = f"""You are a helpful medical appointment scheduling assistant using the Orita API.

Today: {TODAY}. Next Monday: {NEXT_MONDAY}.

Available event types on this account:
{_et_info}

Workflow:
1. Understand what specialty/service the patient needs.
2. Use find_providers to find the right professional (if needed).
3. Use check_slots to find an available time on the requested date.
   - If no slots are available, try the next day automatically.
4. Once you have all details (name, email, date, time), use confirm_booking.
5. Summarize the confirmation clearly to the patient.

Always be warm, professional, and concise.
"""


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# ── LLM with tools ────────────────────────────────────────────────────────────

llm = ChatOpenAI(model="gpt-4o", temperature=0)
llm_with_tools = llm.bind_tools(orita_tools)


# ── Graph nodes ───────────────────────────────────────────────────────────────


def understand_and_plan(state: AgentState) -> AgentState:
    """Main LLM node — understands request and calls tools as needed."""
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def execute_tool(state: AgentState) -> AgentState:
    """Execute whichever tool the LLM requested."""
    last_message = state["messages"][-1]
    tool_results = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        if tool_name in tool_map:
            result = tool_map[tool_name].invoke(tool_args)
        else:
            result = json.dumps({"error": f"Unknown tool: {tool_name}"})

        tool_results.append(
            ToolMessage(
                content=result,
                tool_call_id=tool_call["id"],
                name=tool_name,
            )
        )

    return {"messages": tool_results}


def should_continue(state: AgentState) -> str:
    """Route: if the last message has tool calls, execute them; otherwise done."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "execute_tool"
    return END


# ── Build the graph ───────────────────────────────────────────────────────────

def build_scheduling_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("understand", understand_and_plan)
    graph.add_node("execute_tool", execute_tool)

    graph.set_entry_point("understand")

    graph.add_conditional_edges(
        "understand",
        should_continue,
        {
            "execute_tool": "execute_tool",
            END: END,
        },
    )

    # After executing a tool, always return to understand for next step
    graph.add_edge("execute_tool", "understand")

    return graph.compile()


# ── Example usage ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Orita + LangGraph — Scheduling Agent")
    print("=" * 60)

    app = build_scheduling_graph()

    user_input = (
        "Book me an appointment with a psychologist for next Monday morning. "
        "My name is Laura Martínez, email: laura.martinez@example.com"
    )

    print(f"\nUser: {user_input}\n")

    config = {"recursion_limit": 20}
    initial_state = {"messages": [HumanMessage(content=user_input)]}

    final_state = app.invoke(initial_state, config=config)

    # Print the final AI response
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            print(f"Agent: {msg.content}")
            break

    print("\n" + "=" * 60)
    print("\nFull conversation trace:")
    for msg in final_state["messages"]:
        role = type(msg).__name__
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if content:
            print(f"\n[{role}]\n{content[:300]}{'...' if len(content) > 300 else ''}")
