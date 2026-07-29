"""
Healthcare Copilot powered by Claude + Orita

An AI medical copilot that takes patient symptoms in natural language,
identifies the right specialist, checks availability, and books the appointment.
No call center. No hold music. No human in the loop.

The copilot:
  • Listens to the patient's symptoms with empathy
  • Maps symptoms to the right medical specialty
  • Finds available providers in that specialty
  • Checks real-time availability and books the appointment
  • Provides clear instructions for the visit

Requirements:
    pip install anthropic orita-sdk

Usage:
    export ORITA_API_KEY=your_key
    export ANTHROPIC_API_KEY=your_key
    python healthcare_copilot.py
"""

import json
import os
from datetime import date, timedelta
from typing import Optional

import anthropic
from orita import OritaClient, OritaError

# ── Clients ────────────────────────────────────────────────────────────────────

orita = OritaClient(api_key=os.environ.get("ORITA_API_KEY", "orita_8512592d89fa1b1936adaa9a6e6847db"))
claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "sk-ant-..."))

TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
NEXT_WEEK = (date.today() + timedelta(days=7)).isoformat()

# ── Symptom-to-specialty mapping (used as a hint for Claude) ───────────────────

SPECIALTY_HINTS = {
    "anxiety": "psychology",
    "depression": "psychology",
    "stress": "psychology",
    "mental health": "psychology",
    "heart": "cardiology",
    "chest pain": "cardiology",
    "palpitations": "cardiology",
    "back pain": "physiotherapy",
    "knee pain": "physiotherapy",
    "joint pain": "physiotherapy",
    "skin": "dermatology",
    "rash": "dermatology",
    "acne": "dermatology",
    "diet": "nutrition",
    "weight": "nutrition",
    "eating": "nutrition",
    "vision": "ophthalmology",
    "eyes": "ophthalmology",
    "teeth": "dentistry",
    "dental": "dentistry",
}

# ── Tool definitions (Anthropic tool use) ──────────────────────────────────────

TOOLS = [
    {
        "name": "find_specialist",
        "description": (
            "Find medical specialists/professionals that match the patient's symptoms. "
            "Analyzes the symptoms and filters providers by the appropriate specialty. "
            "Returns a list of available professionals with their IDs and event types."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symptoms": {
                    "type": "string",
                    "description": "Patient's symptoms or health concerns in plain language",
                },
                "specialty": {
                    "type": "string",
                    "description": (
                        "The medical specialty to search for "
                        "(e.g., 'psychology', 'cardiology', 'physiotherapy', 'nutrition'). "
                        "Infer this from the symptoms."
                    ),
                },
            },
            "required": ["symptoms", "specialty"],
        },
    },
    {
        "name": "check_slots",
        "description": (
            "Check available appointment time slots for a provider on a given date. "
            "Returns available times. Always call this before book_appointment."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_type_id": {
                    "type": "string",
                    "description": "The event type ID from find_specialist",
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format",
                },
                "provider_id": {
                    "type": "string",
                    "description": "The provider ID from find_specialist",
                },
            },
            "required": ["event_type_id", "date"],
        },
    },
    {
        "name": "book_appointment",
        "description": (
            "Book a confirmed medical appointment. "
            "Only call this after the patient has approved the date, time, and provider. "
            "Returns booking ID and confirmation details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_type_id": {
                    "type": "string",
                    "description": "The event type ID",
                },
                "date": {
                    "type": "string",
                    "description": "Confirmed date in YYYY-MM-DD format",
                },
                "time": {
                    "type": "string",
                    "description": "Confirmed time in HH:MM format (24h)",
                },
                "client_name": {
                    "type": "string",
                    "description": "Patient's first name",
                },
                "client_lastname": {
                    "type": "string",
                    "description": "Patient's last name",
                },
                "client_email": {
                    "type": "string",
                    "description": "Patient's email address",
                },
                "notes": {
                    "type": "string",
                    "description": "Patient symptoms and reason for visit (pre-visit notes for the doctor)",
                },
                "provider_id": {
                    "type": "string",
                    "description": "The provider ID",
                },
            },
            "required": [
                "event_type_id", "date", "time",
                "client_name", "client_lastname", "client_email",
            ],
        },
    },
]

# ── Tool execution ─────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> str:
    """Execute a healthcare copilot tool call."""
    try:
        if name == "find_specialist":
            specialty = args.get("specialty", "").lower()
            
            # Try to find providers with the specialty filter
            providers = orita.professionals(specialty=specialty)
            
            if not providers:
                # Broader search — return all event types
                event_types = orita.event_types()
                return json.dumps({
                    "message": f"No specialists found for '{specialty}'. Showing all available appointment types.",
                    "specialty_searched": specialty,
                    "event_types": [
                        {"id": et["id"], "title": et["title"], "duration": et.get("duration", 60)}
                        for et in event_types
                    ],
                    "providers": [],
                })

            result = []
            for pro in providers:
                try:
                    pro_events = orita.event_types(provider_id=pro["id"])
                except OritaError:
                    pro_events = []
                result.append({
                    "provider_id": pro["id"],
                    "name": f"Dr. {pro.get('name', '')} {pro.get('lastname', '')}".strip(),
                    "specialty": pro.get("specialty") or pro.get("profession") or specialty,
                    "location": pro.get("location") or "Online / In-person",
                    "languages": pro.get("languages") or ["en", "es"],
                    "event_types": [
                        {
                            "id": et["id"],
                            "title": et["title"],
                            "duration": et.get("duration", 60),
                        }
                        for et in pro_events
                    ],
                })
            return json.dumps({
                "specialty": specialty,
                "symptoms_analyzed": args.get("symptoms", ""),
                "specialists_found": len(result),
                "providers": result,
            })

        elif name == "check_slots":
            provider_id = args.get("provider_id") or None
            slots = orita.slots(
                event_type_id=args["event_type_id"],
                date=args["date"],
                provider_id=provider_id,
            )
            if not slots:
                next_day = (date.fromisoformat(args["date"]) + timedelta(days=1)).isoformat()
                return json.dumps({
                    "date": args["date"],
                    "available": False,
                    "slots": [],
                    "suggestion": f"No availability on {args['date']}. Try checking {next_day}.",
                })
            return json.dumps({
                "date": args["date"],
                "available": True,
                "slots": [{"time": s["value"], "display": s["label"]} for s in slots],
                "count": len(slots),
                "note": "Use the 'time' value (HH:MM) when booking.",
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
                "confirmed_date": booking.get("date", args["date"]),
                "confirmed_time": booking.get("time", args["time"]),
                "patient": f"{args['client_name']} {args['client_lastname']}",
                "email": args["client_email"],
                "next_steps": [
                    "Confirmation email sent to patient",
                    "Provider notified via Orita webhook",
                    "Calendar invite will arrive within 5 minutes",
                ],
            })

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except OritaError as e:
        return json.dumps({"error": str(e), "tool": name})


# ── Healthcare Copilot agent loop ──────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a compassionate AI healthcare copilot. Your role is to help patients 
get the right medical care quickly, without dealing with call centers or waiting on hold.

Today's date: {TODAY}

Your workflow:
1. Listen carefully to the patient's symptoms with empathy
2. Identify the right medical specialty (don't ask them to choose — figure it out)
3. Use find_specialist to find available providers in that specialty
4. Ask for their preferred date (suggest tomorrow or next week as options)
5. Use check_slots to find open times — present them clearly, not as raw data
6. Collect patient details: full name and email
7. Use book_appointment to confirm — include their symptoms in the notes field
8. Give them the booking ID, date, time, and what to expect

Clinical guidelines:
- IMPORTANT: You are a scheduling assistant, not a medical diagnosis tool
- Never diagnose or prescribe — always recommend seeing a professional
- If symptoms sound urgent or emergency-level, tell them to call emergency services (112/911) first
- Be empathetic — many patients are anxious about their health
- Explain clearly what type of specialist you're connecting them with and why

Communication style:
- Warm and reassuring, not clinical or cold
- Explain your reasoning ("Based on what you're describing, a physiotherapist would be the right specialist")
- Keep the patient informed at each step
- Translate times to human-readable format (not raw JSON)
"""


def run_healthcare_copilot():
    """Run the healthcare copilot in interactive mode."""
    messages = []
    
    print("\n" + "=" * 60)
    print("🏥 Healthcare Copilot — Powered by Claude + Orita")
    print("=" * 60)
    print("Tell me how you're feeling, and I'll help you book the right specialist.")
    print("Type 'exit' to quit.\n")
    
    # Initial greeting from the copilot
    initial_response = claude.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "Hello"}],
        tools=TOOLS,
    )
    
    greeting = initial_response.content[0].text if initial_response.content else ""
    if greeting:
        print(f"Copilot: {greeting}\n")
    
    messages.append({"role": "user", "content": "Hello"})
    messages.append({"role": "assistant", "content": initial_response.content})
    
    booking_confirmed = False
    
    while not booking_confirmed:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nCopilot: Take care of yourself! 💙")
            break
        
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("\nCopilot: Stay healthy! 💙")
            break
        
        messages.append({"role": "user", "content": user_input})
        
        # Agentic loop for this turn
        while True:
            response = claude.messages.create(
                model="claude-opus-4-5",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOLS,
            )
            
            # Check for tool use
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]
            
            # Print any text before tool calls
            for tb in text_blocks:
                if tb.text:
                    print(f"\nCopilot: {tb.text}")
            
            if not tool_uses:
                # No more tools — end of turn
                messages.append({"role": "assistant", "content": response.content})
                break
            
            # Process tool calls
            messages.append({"role": "assistant", "content": response.content})
            
            tool_results = []
            for tu in tool_uses:
                print(f"  → [Tool] {tu.name}({list(tu.input.keys())})")
                result_str = execute_tool(tu.name, tu.input)
                result_data = json.loads(result_str)
                
                if tu.name == "book_appointment" and result_data.get("success"):
                    booking_confirmed = True
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_str,
                })
            
            messages.append({"role": "user", "content": tool_results})
            
            if booking_confirmed:
                # Get final confirmation message
                final_response = claude.messages.create(
                    model="claude-opus-4-5",
                    max_tokens=512,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=TOOLS,
                )
                for b in final_response.content:
                    if hasattr(b, "text") and b.text:
                        print(f"\nCopilot: {b.text}")
                break
        
        if booking_confirmed:
            print("\n" + "=" * 60)
            print("✅ Appointment successfully booked via Orita!")
            print("=" * 60)
            break


# ── Simulated demo ─────────────────────────────────────────────────────────────

def run_demo():
    """
    Simulated demo — shows a complete healthcare copilot interaction
    without requiring user input. Useful for testing and CI.
    """
    print("\n" + "=" * 60)
    print("🏥 Healthcare Copilot Demo — Simulated Patient Session")
    print("=" * 60)
    print("Patient: Ana Martínez, experiencing anxiety and sleep problems\n")
    
    messages = []
    
    # Simulate patient conversation
    patient_turns = [
        "Hi, I've been feeling really anxious lately and having trouble sleeping. I'm not sure what kind of doctor I should see.",
        "Yes, that sounds right. I'd prefer something next week if possible. My name is Ana Martínez, email: ana.martinez@example.com.",
        "Morning works great for me. Let's go with the first available slot.",
        "Yes, please book it! Thank you so much.",
    ]
    
    for patient_msg in patient_turns:
        print(f"Patient: {patient_msg}")
        messages.append({"role": "user", "content": patient_msg})
        
        booking_confirmed = False
        while True:
            response = claude.messages.create(
                model="claude-opus-4-5",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOLS,
            )
            
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]
            
            for tb in text_blocks:
                if tb.text:
                    print(f"Copilot: {tb.text}")
            
            if not tool_uses:
                messages.append({"role": "assistant", "content": response.content})
                break
            
            messages.append({"role": "assistant", "content": response.content})
            
            tool_results = []
            for tu in tool_uses:
                print(f"  → [Orita] {tu.name}({list(tu.input.keys())})")
                result_str = execute_tool(tu.name, tu.input)
                result_data = json.loads(result_str)
                if tu.name == "book_appointment" and result_data.get("success"):
                    booking_confirmed = True
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result_str,
                })
            
            messages.append({"role": "user", "content": tool_results})
        
        print()
        
        if booking_confirmed:
            break
    
    print("=" * 60)
    print("✅ Demo complete! Healthcare appointment booked via Orita.")
    print("=" * 60)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    if "--demo" in sys.argv:
        run_demo()
    else:
        run_healthcare_copilot()
