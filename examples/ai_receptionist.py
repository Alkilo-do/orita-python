"""
AI Receptionist powered by OpenAI + Orita

An always-on AI receptionist that understands natural language requests,
finds the right professional, checks availability, and books appointments
— without any human intervention.

The agent maintains a multi-turn conversation, just like a real receptionist:
  • Greets the caller and asks what they need
  • Identifies the right professional and appointment type
  • Presents available slots in a friendly way
  • Confirms all details before booking
  • Sends a confirmation with booking ID

Requirements:
    pip install openai orita-sdk

Usage:
    export ORITA_API_KEY=your_key
    export OPENAI_API_KEY=your_key
    python ai_receptionist.py
"""

import json
import os
from datetime import date, timedelta
from typing import Optional

from openai import OpenAI
from orita import OritaClient, OritaError

# ── Clients ────────────────────────────────────────────────────────────────────

orita = OritaClient(api_key=os.environ.get("ORITA_API_KEY", "orita_8512592d89fa1b1936adaa9a6e6847db"))
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "sk-..."))

TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()

# ── Tool definitions (OpenAI function calling) ─────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_professionals",
            "description": (
                "List all professionals available for booking. "
                "Optionally filter by specialty (e.g. 'psychology', 'nutrition', 'physiotherapy'). "
                "Returns each professional's ID, name, specialty, and their available event types."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": {
                        "type": "string",
                        "description": "Optional specialty to filter by (e.g. 'psychology', 'cardiology')",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "Check available appointment slots for a given event type and date. "
                "Returns a list of available times. "
                "Try multiple dates if no slots are found on the first date."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {
                        "type": "string",
                        "description": "The event type ID obtained from list_professionals",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format",
                    },
                    "provider_id": {
                        "type": "string",
                        "description": "Optional provider ID to scope availability to a specific professional",
                    },
                },
                "required": ["event_type_id", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": (
                "Book a confirmed appointment. Only call this after the user has explicitly agreed "
                "to the date, time, and professional. Returns a booking confirmation with ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {
                        "type": "string",
                        "description": "The event type ID",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format",
                    },
                    "time": {
                        "type": "string",
                        "description": "Time in HH:MM format (24h), taken from check_availability",
                    },
                    "client_name": {
                        "type": "string",
                        "description": "Client's first name",
                    },
                    "client_lastname": {
                        "type": "string",
                        "description": "Client's last name",
                    },
                    "client_email": {
                        "type": "string",
                        "description": "Client's email address",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about the appointment reason",
                    },
                    "provider_id": {
                        "type": "string",
                        "description": "Optional provider ID",
                    },
                },
                "required": ["event_type_id", "date", "time", "client_name", "client_lastname", "client_email"],
            },
        },
    },
]

# ── Tool execution ─────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> str:
    """Execute an Orita tool call and return a JSON string result."""
    try:
        if name == "list_professionals":
            specialty = args.get("specialty") or None
            professionals = orita.professionals(specialty=specialty)

            if not professionals:
                # Fallback: list event types without provider filter
                event_types = orita.event_types()
                return json.dumps({
                    "message": "No individual professionals found; showing available appointment types.",
                    "event_types": [
                        {"id": et["id"], "title": et["title"], "duration": et.get("duration", 60)}
                        for et in event_types
                    ],
                })

            result = []
            for pro in professionals:
                # Fetch event types for each professional
                try:
                    pro_events = orita.event_types(provider_id=pro["id"])
                except OritaError:
                    pro_events = []
                result.append({
                    "provider_id": pro["id"],
                    "name": f"{pro.get('name', '')} {pro.get('lastname', '')}".strip(),
                    "specialty": pro.get("specialty") or pro.get("profession") or "General Practice",
                    "event_types": [
                        {"id": et["id"], "title": et["title"], "duration": et.get("duration", 60)}
                        for et in pro_events
                    ],
                })
            return json.dumps({"professionals": result})

        elif name == "check_availability":
            provider_id = args.get("provider_id") or None
            slots = orita.slots(
                event_type_id=args["event_type_id"],
                date=args["date"],
                provider_id=provider_id,
            )
            if not slots:
                return json.dumps({
                    "date": args["date"],
                    "available": False,
                    "message": "No slots available on this date. Try the next business day.",
                    "slots": [],
                })
            return json.dumps({
                "date": args["date"],
                "available": True,
                "slots": [{"time": s["value"], "display": s["label"]} for s in slots],
                "count": len(slots),
            })

        elif name == "book_appointment":
            booking = orita.book(
                event_type_id=args["event_type_id"],
                date=args["date"],
                time=args["time"],
                client_name=args["client_name"],
                client_lastname=args["client_lastname"],
                client_email=args["client_email"],
                notes=args.get("notes") or None,
                provider_id=args.get("provider_id") or None,
            )
            return json.dumps({
                "success": True,
                "booking_id": booking["id"],
                "status": booking["status"],
                "date": booking.get("date", args["date"]),
                "time": booking.get("time", args["time"]),
                "client": f"{args['client_name']} {args['client_lastname']} <{args['client_email']}>",
                "message": "Appointment confirmed! A confirmation email has been sent to the client.",
            })

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except OritaError as e:
        return json.dumps({"error": str(e), "tool": name})


# ── AI Receptionist agent loop ─────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are Vera, an AI receptionist for a professional services clinic. 
You are warm, professional, and efficient.

Today is {TODAY}.

Your job:
1. Greet the caller and understand what type of appointment they need
2. Use list_professionals to find the right specialist
3. Ask for their preferred date (suggest today or tomorrow if they're not sure)
4. Use check_availability to find open slots — present them in a friendly, readable way
5. Collect the caller's name, last name, and email
6. Use book_appointment to confirm the booking
7. Give them their booking ID and let them know they'll receive a confirmation email

Important rules:
- Be conversational and natural — this is a voice-to-text interface
- Don't dump raw JSON on the user — translate results into friendly language
- Always confirm details before booking
- If no slots are available, proactively check the next day
- Present times in a human-friendly format (e.g., "9:00 AM" not "09:00")
- Keep responses concise — the caller is on the phone
"""


def run_receptionist(initial_message: Optional[str] = None):
    """
    Run the AI receptionist in a conversation loop.
    
    Args:
        initial_message: Optional first message to start the conversation.
                        If None, the receptionist greets first.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    print("\n" + "=" * 60)
    print("🏥 AI Receptionist — Powered by OpenAI + Orita")
    print("=" * 60)
    print("Type 'quit' or 'exit' to end the conversation.\n")
    
    # If no initial message, let the receptionist greet first
    if initial_message is None:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages + [{"role": "user", "content": "Hello"}],
            tools=TOOLS,
            tool_choice="auto",
        )
        assistant_msg = response.choices[0].message
        messages.append({"role": "user", "content": "Hello"})
        messages.append({"role": "assistant", "content": assistant_msg.content or "", "tool_calls": assistant_msg.tool_calls})
        
        if assistant_msg.content:
            print(f"Vera: {assistant_msg.content}\n")
    else:
        print(f"Caller: {initial_message}\n")
        messages.append({"role": "user", "content": initial_message})
    
    booking_confirmed = False
    
    while not booking_confirmed:
        # If there are pending tool calls, process them first
        last_msg = messages[-1] if messages else None
        if last_msg and last_msg.get("role") == "assistant":
            raw_tool_calls = last_msg.get("tool_calls")
            if raw_tool_calls:
                # Execute all tool calls
                for tc in raw_tool_calls:
                    tool_name = tc.function.name
                    tool_args = json.loads(tc.function.arguments)
                    print(f"  [Tool] Calling {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:80]}...)")
                    result = execute_tool(tool_name, tool_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                    
                    # Check if appointment was just booked
                    result_data = json.loads(result)
                    if tool_name == "book_appointment" and result_data.get("success"):
                        booking_confirmed = True

                # Get the assistant's response after tool results
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
                assistant_msg = response.choices[0].message
                messages.append({
                    "role": "assistant",
                    "content": assistant_msg.content or "",
                    "tool_calls": [tc.dict() for tc in assistant_msg.tool_calls] if assistant_msg.tool_calls else None,
                })
                if assistant_msg.content:
                    print(f"\nVera: {assistant_msg.content}\n")
                
                if booking_confirmed:
                    break
                    
                if assistant_msg.tool_calls:
                    continue  # More tool calls to process
                    
        # Get user input
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nVera: Thank you for calling! Have a great day. 👋")
            break
            
        if not user_input:
            continue
            
        if user_input.lower() in ("quit", "exit", "bye", "goodbye"):
            print("\nVera: Thank you for calling! Have a great day. 👋")
            break
        
        messages.append({"role": "user", "content": user_input})
        
        # Get AI response
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        assistant_msg = response.choices[0].message
        messages.append({
            "role": "assistant",
            "content": assistant_msg.content or "",
            "tool_calls": [tc.dict() for tc in assistant_msg.tool_calls] if assistant_msg.tool_calls else None,
        })
        
        if assistant_msg.content:
            print(f"\nVera: {assistant_msg.content}\n")


# ── Simulated demo ─────────────────────────────────────────────────────────────

def run_demo():
    """
    Simulated demo conversation — shows the full receptionist flow
    without requiring user input. Useful for testing and documentation.
    """
    print("\n" + "=" * 60)
    print("🏥 AI Receptionist Demo — Simulated Conversation")
    print("=" * 60)
    print("(This demo simulates a complete booking flow)\n")
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Simulated conversation turns
    conversation = [
        "Hi, I'd like to book an appointment with a psychologist.",
        "My name is María García, email maria.garcia@example.com. Tomorrow works for me.",
        "The 10 AM slot sounds perfect!",
        "Yes, please confirm the booking.",
    ]
    
    for user_turn in conversation:
        print(f"Caller: {user_turn}")
        messages.append({"role": "user", "content": user_turn})
        
        # Agent loop for this turn
        while True:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            assistant_msg = response.choices[0].message
            
            if assistant_msg.tool_calls:
                # Process tool calls silently in demo
                messages.append({
                    "role": "assistant",
                    "content": assistant_msg.content or "",
                    "tool_calls": [tc.dict() for tc in assistant_msg.tool_calls],
                })
                for tc in assistant_msg.tool_calls:
                    tool_name = tc.function.name
                    tool_args = json.loads(tc.function.arguments)
                    print(f"  → [Tool] {tool_name}({list(tool_args.keys())})")
                    result = execute_tool(tool_name, tool_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                # Final text response for this turn
                messages.append({"role": "assistant", "content": assistant_msg.content or ""})
                print(f"Vera: {assistant_msg.content}\n")
                break
    
    print("=" * 60)
    print("✅ Demo complete! Appointment booked via Orita.")
    print("=" * 60)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    if "--demo" in sys.argv:
        # Run scripted demo
        run_demo()
    else:
        # Run interactive receptionist
        run_receptionist()
