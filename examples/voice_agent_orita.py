"""
Voice Agent powered by OpenAI + Orita

An AI voice agent that answers phone calls, understands natural speech,
and books real-world appointments — 24/7, without a human receptionist.

This example simulates the voice interaction as text (since you need
phone infrastructure like Twilio for actual calls), but shows the
exact same logic that would run in production.

── How it works (production) ──────────────────────────────────────────────────
  Caller → Twilio (phone) → Twilio webhook → This agent
  Agent → OpenAI STT (transcribe) → Agent logic → Orita (book)
  Orita confirmation → Agent → OpenAI TTS → Twilio → Caller (speech)

── This demo ──────────────────────────────────────────────────────────────────
  The same agent logic runs here, but input/output is text in the console.
  Swap console I/O for Twilio's <Gather> + TTS and you have a production agent.

Requirements:
    pip install openai orita-sdk

Usage:
    export ORITA_API_KEY=your_key
    export OPENAI_API_KEY=your_key
    python voice_agent_orita.py
    python voice_agent_orita.py --demo    # Run scripted call demo
"""

import json
import os
import sys
from datetime import date, timedelta
from typing import Optional

from openai import OpenAI
from orita import OritaClient, OritaError

# ── Clients ────────────────────────────────────────────────────────────────────

orita = OritaClient(api_key=os.environ.get("ORITA_API_KEY", "orita_8512592d89fa1b1936adaa9a6e6847db"))
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "sk-..."))

TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()

# ── Tool definitions ───────────────────────────────────────────────────────────
# Voice-optimized: fewer parameters, simpler interface
# A voice agent needs to be fast and decisive — no long menus

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_appointment_types",
            "description": (
                "Get available appointment types. "
                "Call this first to understand what bookings are possible."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_next_available",
            "description": (
                "Check the next available appointment slot for a given event type. "
                "Automatically checks today, tomorrow, and the next 7 days. "
                "Returns the first available slot found."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {
                        "type": "string",
                        "description": "The event type ID",
                    },
                    "preference": {
                        "type": "string",
                        "enum": ["morning", "afternoon", "any"],
                        "description": "Time preference. Default: any",
                    },
                    "preferred_date": {
                        "type": "string",
                        "description": "Optional preferred date in YYYY-MM-DD. Defaults to today.",
                    },
                },
                "required": ["event_type_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_booking",
            "description": (
                "Book the appointment after caller confirms. "
                "Use the slot details from check_next_available. "
                "Returns booking ID and confirmation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM (24h)"},
                    "caller_name": {"type": "string"},
                    "caller_lastname": {"type": "string"},
                    "caller_email": {"type": "string"},
                    "reason": {
                        "type": "string",
                        "description": "Brief reason for visit (from conversation)",
                    },
                },
                "required": ["event_type_id", "date", "time", "caller_name", "caller_lastname", "caller_email"],
            },
        },
    },
]


# ── Tool execution ─────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> str:
    """Execute a tool call. Returns JSON string."""
    try:
        if name == "get_appointment_types":
            event_types = orita.event_types()
            return json.dumps({
                "types": [
                    {
                        "id": et["id"],
                        "name": et["title"],
                        "duration_minutes": et.get("duration", 60),
                    }
                    for et in event_types
                ],
                "count": len(event_types),
            })

        elif name == "check_next_available":
            event_type_id = args["event_type_id"]
            preference = args.get("preference", "any")
            start_date_str = args.get("preferred_date", TODAY)
            
            try:
                start_date = date.fromisoformat(start_date_str)
            except ValueError:
                start_date = date.today()

            # Search up to 7 days ahead
            for days_ahead in range(8):
                check_date = start_date + timedelta(days=days_ahead)
                check_date_str = check_date.isoformat()
                
                try:
                    slots = orita.slots(event_type_id=event_type_id, date=check_date_str)
                except OritaError:
                    continue
                
                if not slots:
                    continue
                
                # Filter by time preference
                filtered = slots
                if preference == "morning":
                    filtered = [s for s in slots if int(s["value"].split(":")[0]) < 12]
                elif preference == "afternoon":
                    filtered = [s for s in slots if int(s["value"].split(":")[0]) >= 12]
                
                if filtered:
                    chosen = filtered[0]  # First available
                    return json.dumps({
                        "found": True,
                        "date": check_date_str,
                        "time": chosen["value"],
                        "display_time": chosen["label"],
                        "days_from_today": days_ahead,
                        "all_slots_that_day": [s["label"] for s in filtered[:5]],
                    })
            
            return json.dumps({
                "found": False,
                "message": "No availability in the next 7 days. Please call back or try a different appointment type.",
            })

        elif name == "confirm_booking":
            booking = orita.book(
                event_type_id=args["event_type_id"],
                date=args["date"],
                time=args["time"],
                client_name=args["caller_name"],
                client_lastname=args["caller_lastname"],
                client_email=args["caller_email"],
                notes=args.get("reason") or None,
            )
            return json.dumps({
                "success": True,
                "booking_id": booking["id"],
                "status": booking["status"],
                "date": booking.get("date", args["date"]),
                "time": booking.get("time", args["time"]),
                "confirmation_sent_to": args["caller_email"],
            })

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except OritaError as e:
        return json.dumps({"error": str(e), "tool": name})


# ── Voice agent system prompt ──────────────────────────────────────────────────
# Voice-optimized: short sentences, no markdown, natural speech patterns

SYSTEM_PROMPT = f"""You are an AI receptionist answering phone calls for a medical clinic.
Today is {TODAY}.

VOICE RULES — CRITICAL:
- Keep responses SHORT. Max 2-3 sentences per turn.
- No bullet points, no markdown, no lists. This is speech.
- Speak naturally, like a real receptionist on the phone.
- Be warm but efficient — callers want to book quickly, not chat.
- Say numbers clearly: "nine AM" not "9:00", "July twenty-ninth" not "2026-07-29".
- Confirm back what you heard before booking.

YOUR FLOW:
1. Answer the call warmly, ask what kind of appointment they need.
2. Call get_appointment_types to find the right one.
3. Ask for their date preference (morning or afternoon, specific day).
4. Call check_next_available — tell them the first slot you found.
5. If they agree, ask for their full name and email.
6. Call confirm_booking to lock it in.
7. Read back the booking ID and tell them to check their email.

If you don't catch something, ask them to repeat it. Keep it natural.
Never read out raw IDs or JSON to the caller.
"""


def _process_tool_calls(tool_calls, messages: list) -> tuple[list, bool]:
    """
    Process all tool calls, append tool results to messages.
    Returns (updated_messages, booking_confirmed).
    """
    booking_confirmed = False
    
    for tc in tool_calls:
        tool_name = tc.function.name
        tool_args = json.loads(tc.function.arguments)
        
        # In production: log tool calls for call center analytics
        print(f"  [→ Orita] {tool_name}({list(tool_args.keys())})")
        
        result = execute_tool(tool_name, tool_args)
        result_data = json.loads(result)
        
        if tool_name == "confirm_booking" and result_data.get("success"):
            booking_confirmed = True
        
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result,
        })
    
    return messages, booking_confirmed


def run_voice_agent():
    """
    Run the voice agent in interactive console mode.
    
    In production, replace input() with Twilio <Gather> speech recognition
    and print() with OpenAI TTS → Twilio TwiML <Say>.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    print("\n" + "=" * 60)
    print("📞 Voice Agent — Powered by OpenAI + Orita")
    print("=" * 60)
    print("Simulating phone call. Type your responses as if speaking.\n")
    print("[PHONE RINGS]\n")
    
    # Agent picks up first
    messages.append({"role": "user", "content": "[caller connected]"})
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )
    msg = response.choices[0].message
    messages.append({
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [tc.dict() for tc in msg.tool_calls] if msg.tool_calls else None,
    })
    if msg.content:
        print(f"Agent: {msg.content}\n")
    
    booking_confirmed = False
    
    while not booking_confirmed:
        # Handle any pending tool calls first
        last = messages[-1]
        if last.get("role") == "assistant" and last.get("tool_calls"):
            # Need to reconstruct tool_call objects for the API
            # (stored as dicts, but already processed — skip re-execution)
            pass
        
        try:
            caller_speech = input("Caller: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nAgent: Thank you for calling! Goodbye.")
            break
        
        if not caller_speech:
            continue
        if caller_speech.lower() in ("bye", "goodbye", "hang up"):
            print("\nAgent: Thank you for calling! Have a great day.")
            break
        
        messages.append({"role": "user", "content": caller_speech})
        
        # Agentic loop
        while True:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            
            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.dict() for tc in msg.tool_calls],
                })
                messages, booking_confirmed = _process_tool_calls(msg.tool_calls, messages)
            else:
                messages.append({"role": "assistant", "content": msg.content or ""})
                if msg.content:
                    print(f"\nAgent: {msg.content}\n")
                break
            
            # Get response after tool results
            response2 = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            msg2 = response2.choices[0].message
            messages.append({
                "role": "assistant",
                "content": msg2.content or "",
                "tool_calls": [tc.dict() for tc in msg2.tool_calls] if msg2.tool_calls else None,
            })
            if msg2.content:
                print(f"\nAgent: {msg2.content}\n")
            
            if not msg2.tool_calls:
                break
        
        if booking_confirmed:
            print("\n" + "=" * 60)
            print("✅ Appointment booked via Orita!")
            print("[CALL ENDED]")
            print("=" * 60)


# ── Demo: Full simulated call ──────────────────────────────────────────────────

def run_demo():
    """
    Scripted demo simulating a complete phone call.
    Shows the exact conversation flow from ring to booking confirmation.
    """
    print("\n" + "=" * 60)
    print("📞 Voice Agent Demo — Full Simulated Phone Call")
    print("=" * 60)
    print("Caller: Carlos Fernández, booking a psychology appointment\n")
    print("[PHONE RINGS]\n")
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Scripted call transcript
    call_turns = [
        "[caller connected]",
        "Hi, I'd like to book an appointment with a psychologist.",
        "Tomorrow morning would be great.",
        "That sounds perfect, the nine AM slot.",
        "Sure, my name is Carlos Fernández, and my email is carlos.fernandez@example.com.",
        "Yes, please go ahead and book it.",
    ]
    
    booking_confirmed = False
    
    for i, turn in enumerate(call_turns):
        if i == 0:
            # Agent initiates
            messages.append({"role": "user", "content": turn})
        else:
            print(f"Caller: {turn}")
            messages.append({"role": "user", "content": turn})
        
        # Agentic loop
        while True:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            
            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.dict() for tc in msg.tool_calls],
                })
                if msg.content:
                    print(f"Agent: {msg.content}")
                
                messages, booking_confirmed = _process_tool_calls(msg.tool_calls, messages)
                
                # Continue to get spoken response after tool results
                response2 = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
                msg2 = response2.choices[0].message
                messages.append({
                    "role": "assistant",
                    "content": msg2.content or "",
                    "tool_calls": [tc.dict() for tc in msg2.tool_calls] if msg2.tool_calls else None,
                })
                if msg2.content:
                    print(f"Agent: {msg2.content}")
                
                if not msg2.tool_calls:
                    break
            else:
                messages.append({"role": "assistant", "content": msg.content or ""})
                if msg.content:
                    print(f"Agent: {msg.content}")
                break
        
        print()
        
        if booking_confirmed:
            break
    
    print("[CALL ENDED]")
    print("=" * 60)
    print("✅ Demo complete! Booking confirmed via Orita.")
    print("=" * 60)
    print()
    print("— Production wiring (Twilio) —")
    print("Replace input() → Twilio <Gather speech='true'>")
    print("Replace print() → OpenAI TTS → Twilio TwiML <Say>")
    print("Webhook: POST /voice → run this agent logic")
    print("Docs: https://www.twilio.com/docs/voice/tutorials/how-to-gather-user-input-using-python")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        run_voice_agent()
