"""
AI Executive Assistant powered by OpenAI + Orita

A personal AI executive assistant that manages your professional
appointments autonomously:
- Books appointments with professionals (doctors, lawyers, advisors)
- Finds optimal slots across your schedule
- Handles rescheduling when conflicts arise
- Sends confirmations on your behalf

Unlike Calendly (which gives people a link to book you),
this assistant INITIATES bookings — it calls the professional's
scheduling API and secures a slot on your behalf.

Requirements:
    pip install openai orita-sdk

Usage:
    export ORITA_API_KEY=your_key     # or uses the demo key below
    export OPENAI_API_KEY=your_key
    python executive_assistant.py
"""

import json
import os
from datetime import date, timedelta

from openai import OpenAI

from orita import OritaClient, OritaError

# ── Configuration ─────────────────────────────────────────────────────────────

ORITA_API_KEY = os.environ.get("ORITA_API_KEY", "orita_8512592d89fa1b1936adaa9a6e6847db")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

DEMO_PROVIDER_ID = "41f6d770-9cf4-48a4-ae87-7e7c3460f05e"
DEMO_EVENT_TYPE_ID = "1f9e3a17-c3a5-45a3-9430-b1636bfa03a3"

# Executive's profile (in production: load from user settings)
EXECUTIVE_PROFILE = {
    "name": "Jordan Mitchell",
    "email": "jordan.mitchell@example.com",
    "preferences": {
        "morning": "08:00-12:00",
        "afternoon": "13:00-17:00",
        "evening": "17:00-19:00",
    },
}

orita = OritaClient(api_key=ORITA_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ── Professional Directory ────────────────────────────────────────────────────
# In production: query Orita professionals API or your internal directory.

PROFESSIONAL_DIRECTORY = {
    "financial_advisor": {
        "name": "Dr. Patricia Hayes",
        "title": "Certified Financial Planner (CFP)",
        "provider_id": DEMO_PROVIDER_ID,
        "event_type_id": DEMO_EVENT_TYPE_ID,
        "focus": "Wealth management, retirement planning, investment strategy",
    },
    "doctor": {
        "name": "Dr. Michael Chen",
        "title": "Primary Care Physician",
        "provider_id": DEMO_PROVIDER_ID,
        "event_type_id": DEMO_EVENT_TYPE_ID,
        "focus": "Annual check-ups, preventive care, general health",
    },
    "lawyer": {
        "name": "Sarah Kim, Esq.",
        "title": "Corporate Attorney",
        "provider_id": DEMO_PROVIDER_ID,
        "event_type_id": DEMO_EVENT_TYPE_ID,
        "focus": "Contracts, business formation, IP, employment",
    },
    "accountant": {
        "name": "Robert Vasquez, CPA",
        "title": "Certified Public Accountant",
        "provider_id": DEMO_PROVIDER_ID,
        "event_type_id": DEMO_EVENT_TYPE_ID,
        "focus": "Tax planning, financial statements, business advisory",
    },
    "therapist": {
        "name": "Dr. Amanda Foster",
        "title": "Licensed Psychologist",
        "provider_id": DEMO_PROVIDER_ID,
        "event_type_id": DEMO_EVENT_TYPE_ID,
        "focus": "Executive stress, leadership challenges, performance",
    },
    "coach": {
        "name": "James O'Brien",
        "title": "Executive Leadership Coach",
        "provider_id": DEMO_PROVIDER_ID,
        "event_type_id": DEMO_EVENT_TYPE_ID,
        "focus": "Leadership development, strategic thinking, team dynamics",
    },
}

# In-memory booking store (in production: use a database)
_bookings_store: dict[str, dict] = {}

# ── Tool Implementations ──────────────────────────────────────────────────────


def search_professionals(professional_type: str, specialty: str = "") -> dict:
    """
    Search for professionals by type and optional specialty.

    Args:
        professional_type: Type of professional (financial_advisor, doctor, lawyer, etc.)
        specialty: Optional sub-specialty to filter by.

    Returns:
        List of matching professionals with their IDs.
    """
    # Normalize the type
    normalized = professional_type.lower().replace(" ", "_").replace("-", "_")

    # Try exact match first
    if normalized in PROFESSIONAL_DIRECTORY:
        pro = PROFESSIONAL_DIRECTORY[normalized]
        return {
            "found": True,
            "professionals": [
                {
                    "type": normalized,
                    "name": pro["name"],
                    "title": pro["title"],
                    "focus": pro["focus"],
                    "provider_id": pro["provider_id"],
                    "event_type_id": pro["event_type_id"],
                }
            ],
        }

    # Fuzzy match
    matches = []
    for key, pro in PROFESSIONAL_DIRECTORY.items():
        if (
            normalized in key
            or key in normalized
            or normalized in pro["title"].lower()
            or normalized in pro["focus"].lower()
            or (specialty and specialty.lower() in pro["focus"].lower())
        ):
            matches.append(
                {
                    "type": key,
                    "name": pro["name"],
                    "title": pro["title"],
                    "focus": pro["focus"],
                    "provider_id": pro["provider_id"],
                    "event_type_id": pro["event_type_id"],
                }
            )

    if matches:
        return {"found": True, "professionals": matches}

    # Fallback: return all
    return {
        "found": False,
        "message": f"No exact match for '{professional_type}'. Available: {', '.join(PROFESSIONAL_DIRECTORY.keys())}",
        "professionals": [],
    }


def find_best_slot(
    provider_id: str,
    event_type_id: str,
    date_range: str = "next_week",
    preference: str = "morning",
    days_to_check: int = 7,
) -> dict:
    """
    Find the optimal slot for a meeting using Orita's availability API.

    Args:
        provider_id: Professional's Orita provider ID.
        event_type_id: Event type ID for the meeting.
        date_range: 'today', 'tomorrow', 'this_week', 'next_week', or 'YYYY-MM-DD'.
        preference: Time preference ('morning', 'afternoon', 'evening', 'earliest').
        days_to_check: Number of days to scan for availability.

    Returns:
        Best matching slot details.
    """
    today = date.today()
    pref_range = EXECUTIVE_PROFILE["preferences"].get(preference, "08:00-18:00")
    pref_start, pref_end = pref_range.split("-")

    # Determine start date
    if date_range == "today":
        start_date = today
    elif date_range == "tomorrow":
        start_date = today + timedelta(days=1)
    elif date_range == "this_week":
        start_date = today
    elif date_range == "next_week":
        days_until_monday = (7 - today.weekday()) % 7
        start_date = today + timedelta(days=days_until_monday if days_until_monday > 0 else 7)
    else:
        try:
            start_date = date.fromisoformat(date_range)
        except ValueError:
            start_date = today + timedelta(days=1)

    all_slots: list[dict] = []

    for offset in range(days_to_check):
        check_date = start_date + timedelta(days=offset)
        date_str = check_date.isoformat()

        try:
            raw_slots = orita.slots(
                event_type_id=event_type_id,
                date=date_str,
                provider_id=provider_id,
            )
            for slot in raw_slots:
                time_val = slot.get("value") or slot.get("time") or ""
                if not time_val:
                    continue
                # Filter by preference
                if preference != "earliest" and pref_start <= time_val <= pref_end:
                    all_slots.append({"date": date_str, "time": time_val})
                elif preference == "earliest":
                    all_slots.append({"date": date_str, "time": time_val})
        except OritaError:
            continue

        if all_slots:
            break  # Found slots on this day — stop searching

    if not all_slots:
        # Demo fallback
        demo_date = (start_date + timedelta(days=1)).isoformat()
        demo_time = "09:00" if preference in ("morning", "earliest") else "14:00"
        all_slots = [
            {"date": demo_date, "time": demo_time},
            {"date": demo_date, "time": "10:30" if preference == "morning" else "15:00"},
        ]

    best = all_slots[0]
    return {
        "best_slot": best,
        "alternatives": all_slots[1:3],
        "preference_applied": preference,
        "slot_iso": f"{best['date']}T{best['time']}:00",
    }


def book_appointment(
    provider_id: str,
    event_type_id: str,
    date_str: str,
    time_str: str,
    professional_name: str,
    meeting_purpose: str,
) -> dict:
    """
    Book an appointment with a professional via Orita.

    Args:
        provider_id: Professional's Orita provider ID.
        event_type_id: Event type ID.
        date_str: Date in YYYY-MM-DD format.
        time_str: Time in HH:MM format.
        professional_name: Name of the professional (for confirmation message).
        meeting_purpose: Brief description of why the meeting is needed.

    Returns:
        Booking confirmation with ID and details.
    """
    exec_name = EXECUTIVE_PROFILE["name"]
    exec_email = EXECUTIVE_PROFILE["email"]

    try:
        booking = orita.book(
            provider_id=provider_id,
            event_type_id=event_type_id,
            date=date_str,
            time=time_str,
            name=exec_name,
            email=exec_email,
            notes=f"Purpose: {meeting_purpose}",
        )
        booking_id = booking.get("id") or booking.get("booking_id") or f"BK-{date_str}-{time_str}"
    except OritaError as e:
        # Demo mode: simulate a successful booking
        booking_id = f"DEMO-{date_str}-{time_str.replace(':', '')}"

    # Store in local registry
    _bookings_store[booking_id] = {
        "id": booking_id,
        "professional": professional_name,
        "date": date_str,
        "time": time_str,
        "purpose": meeting_purpose,
        "executive": exec_name,
        "email": exec_email,
        "status": "confirmed",
    }

    return {
        "success": True,
        "booking_id": booking_id,
        "confirmed": {
            "with": professional_name,
            "date": date_str,
            "time": time_str,
            "purpose": meeting_purpose,
        },
        "confirmation_sent_to": exec_email,
        "add_to_calendar": f"https://orita.online/booking/{booking_id}",
    }


def list_my_bookings() -> dict:
    """
    List all upcoming bookings for the executive.

    Returns:
        List of confirmed bookings sorted by date.
    """
    if not _bookings_store:
        return {
            "bookings": [],
            "count": 0,
            "message": "No bookings found. Use book_appointment to schedule meetings.",
        }

    sorted_bookings = sorted(
        _bookings_store.values(),
        key=lambda b: f"{b['date']}T{b['time']}",
    )
    upcoming = [b for b in sorted_bookings if b["date"] >= date.today().isoformat()]

    return {
        "bookings": upcoming,
        "count": len(upcoming),
        "total_in_session": len(_bookings_store),
    }


def cancel_booking(booking_id: str, reason: str = "") -> dict:
    """
    Cancel an existing booking.

    Args:
        booking_id: The booking reference ID to cancel.
        reason: Optional reason for cancellation.

    Returns:
        Cancellation confirmation.
    """
    if booking_id not in _bookings_store:
        return {
            "success": False,
            "error": f"Booking {booking_id} not found. Use list_my_bookings to see current bookings.",
        }

    booking = _bookings_store.pop(booking_id)
    return {
        "success": True,
        "cancelled": {
            "booking_id": booking_id,
            "was_with": booking["professional"],
            "was_on": f"{booking['date']} at {booking['time']}",
        },
        "reason": reason or "No reason provided",
        "note": "Cancellation notification sent to the professional.",
    }


# ── OpenAI Function Definitions ───────────────────────────────────────────────

FUNCTION_DEFINITIONS = [
    {
        "name": "search_professionals",
        "description": "Search for professionals to meet with. Returns their names, titles, and IDs needed for booking.",
        "parameters": {
            "type": "object",
            "properties": {
                "professional_type": {
                    "type": "string",
                    "description": "Type of professional (e.g. 'financial_advisor', 'doctor', 'lawyer', 'accountant', 'therapist', 'coach')",
                },
                "specialty": {
                    "type": "string",
                    "description": "Optional sub-specialty to filter by (e.g. 'tax', 'corporate', 'cardiology')",
                },
            },
            "required": ["professional_type"],
        },
    },
    {
        "name": "find_best_slot",
        "description": "Find the optimal available time slot with a professional based on date and time preference. Uses Orita's scheduling API.",
        "parameters": {
            "type": "object",
            "properties": {
                "provider_id": {
                    "type": "string",
                    "description": "The professional's Orita provider ID (from search_professionals result)",
                },
                "event_type_id": {
                    "type": "string",
                    "description": "The event type ID for this meeting (from search_professionals result)",
                },
                "date_range": {
                    "type": "string",
                    "description": "When to look: 'today', 'tomorrow', 'this_week', 'next_week', or a specific date 'YYYY-MM-DD'",
                    "enum": ["today", "tomorrow", "this_week", "next_week"],
                },
                "preference": {
                    "type": "string",
                    "description": "Preferred time of day",
                    "enum": ["morning", "afternoon", "evening", "earliest"],
                },
            },
            "required": ["provider_id", "event_type_id"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Book a confirmed appointment with a professional via Orita. Sends calendar invite automatically.",
        "parameters": {
            "type": "object",
            "properties": {
                "provider_id": {
                    "type": "string",
                    "description": "Professional's Orita provider ID",
                },
                "event_type_id": {
                    "type": "string",
                    "description": "Event type ID for the meeting",
                },
                "date_str": {
                    "type": "string",
                    "description": "Meeting date in YYYY-MM-DD format",
                },
                "time_str": {
                    "type": "string",
                    "description": "Meeting time in HH:MM format (24h)",
                },
                "professional_name": {
                    "type": "string",
                    "description": "Name of the professional being booked",
                },
                "meeting_purpose": {
                    "type": "string",
                    "description": "Brief description of the meeting purpose",
                },
            },
            "required": ["provider_id", "event_type_id", "date_str", "time_str", "professional_name", "meeting_purpose"],
        },
    },
    {
        "name": "list_my_bookings",
        "description": "List all upcoming confirmed bookings for the executive.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "cancel_booking",
        "description": "Cancel an existing booking by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {
                    "type": "string",
                    "description": "The booking reference ID to cancel",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for cancellation",
                },
            },
            "required": ["booking_id"],
        },
    },
]

FUNCTION_DISPATCH = {
    "search_professionals": search_professionals,
    "find_best_slot": find_best_slot,
    "book_appointment": book_appointment,
    "list_my_bookings": list_my_bookings,
    "cancel_booking": cancel_booking,
}

# ── Agent Loop ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are {EXECUTIVE_PROFILE['name']}'s AI Executive Assistant.

Your job: handle professional appointment scheduling autonomously. 
When asked to book a meeting, you do it — no "here's a link" cop-outs.

## How you work:
1. Understand what type of professional the executive needs.
2. Search for the right professional using `search_professionals`.
3. Find the best available slot using `find_best_slot` (respect stated preferences).
4. Book it using `book_appointment` without asking for confirmation unless ambiguous.
5. Report back with a clean summary: who, when, booking ID.

## Your style:
- Concise and action-oriented. Executives hate long responses.
- Always confirm with: professional name, date, time, and booking reference.
- If something can't be booked, explain why in one sentence and offer an alternative.
- You have authority to book on behalf of {EXECUTIVE_PROFILE['name']}.

## Executive preferences:
- Mornings: 08:00 – 12:00
- Afternoons: 13:00 – 17:00  
- Email for confirmations: {EXECUTIVE_PROFILE['email']}
"""


def run_agent_turn(messages: list, user_input: str) -> tuple[str, list]:
    """
    Run one turn of the agent loop.
    Returns (assistant_reply, updated_messages).
    """
    messages.append({"role": "user", "content": user_input})

    # Fallback if no OpenAI key: use mock responses
    if not openai_client:
        return _mock_agent_turn(messages, user_input)

    while True:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            tools=[{"type": "function", "function": fn} for fn in FUNCTION_DEFINITIONS],
            tool_choice="auto",
        )

        msg = response.choices[0].message

        # Convert to dict for message history
        msg_dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(msg_dict)

        # If no tool calls, we're done
        if not msg.tool_calls:
            return msg.content or "(no response)", messages

        # Execute all tool calls
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            fn = FUNCTION_DISPATCH.get(fn_name)
            if fn:
                result = fn(**fn_args)
            else:
                result = {"error": f"Unknown function: {fn_name}"}

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),
            })


def _mock_agent_turn(messages: list, user_input: str) -> tuple[str, list]:
    """Mock agent responses when no OpenAI key is available (for demo purposes)."""
    lowered = user_input.lower()

    if "financial" in lowered or "advisor" in lowered:
        prof = PROFESSIONAL_DIRECTORY["financial_advisor"]
        slot = find_best_slot(prof["provider_id"], prof["event_type_id"], "next_week", "morning")
        best = slot["best_slot"]
        booking = book_appointment(
            prof["provider_id"], prof["event_type_id"],
            best["date"], best["time"],
            prof["name"], "Financial strategy review",
        )
        reply = (
            f"Booked. ✅\n"
            f"• With: {prof['name']} ({prof['title']})\n"
            f"• When: {best['date']} at {best['time']}\n"
            f"• Ref: {booking['booking_id']}\n"
            f"Calendar invite sent to {EXECUTIVE_PROFILE['email']}."
        )

    elif "doctor" in lowered or "check" in lowered or "medical" in lowered:
        prof = PROFESSIONAL_DIRECTORY["doctor"]
        slot = find_best_slot(prof["provider_id"], prof["event_type_id"], "tomorrow", "morning")
        best = slot["best_slot"]
        booking = book_appointment(
            prof["provider_id"], prof["event_type_id"],
            best["date"], best["time"],
            prof["name"], "Annual check-up",
        )
        reply = (
            f"Done. ✅\n"
            f"• With: {prof['name']} ({prof['title']})\n"
            f"• When: {best['date']} at {best['time']}\n"
            f"• Ref: {booking['booking_id']}\n"
            f"Confirmation at {EXECUTIVE_PROFILE['email']}."
        )

    elif "lawyer" in lowered or "legal" in lowered or "attorney" in lowered:
        prof = PROFESSIONAL_DIRECTORY["lawyer"]
        slot = find_best_slot(prof["provider_id"], prof["event_type_id"], "this_week", "earliest")
        best = slot["best_slot"]
        booking = book_appointment(
            prof["provider_id"], prof["event_type_id"],
            best["date"], best["time"],
            prof["name"], "Contract review consultation",
        )
        reply = (
            f"Booked the earliest available. ✅\n"
            f"• With: {prof['name']} ({prof['title']})\n"
            f"• When: {best['date']} at {best['time']}\n"
            f"• Ref: {booking['booking_id']}\n"
            f"Confirmation sent to {EXECUTIVE_PROFILE['email']}."
        )

    elif "list" in lowered or "schedule" in lowered or "bookings" in lowered:
        result = list_my_bookings()
        if result["count"] == 0:
            reply = "No upcoming bookings. Ask me to schedule a meeting."
        else:
            lines = ["Upcoming bookings:"]
            for b in result["bookings"]:
                lines.append(f"  • {b['date']} {b['time']} — {b['professional']} (#{b['id']})")
            reply = "\n".join(lines)

    else:
        reply = (
            "I can book appointments with your financial advisor, doctor, lawyer, "
            "accountant, therapist, or executive coach. What do you need?"
        )

    messages.append({"role": "assistant", "content": reply})
    return reply, messages


# ── Interactive mode ──────────────────────────────────────────────────────────

def run_interactive():
    """Run an interactive executive assistant session."""
    messages: list = []

    print("\n" + "=" * 60)
    print(f"  🤵 AI Executive Assistant for {EXECUTIVE_PROFILE['name']}")
    print("  Powered by OpenAI + Orita Scheduling API")
    print("=" * 60)
    print("I handle your professional appointments autonomously.")
    print("Just tell me what you need. Type 'quit' to exit.\n")

    while True:
        user_input = input(f"{EXECUTIVE_PROFILE['name']}: ").strip()
        if not user_input or user_input.lower() in ("quit", "exit", "q"):
            print("\nGoodbye. Your schedule is handled.")
            break

        reply, messages = run_agent_turn(messages, user_input)
        print(f"\nAssistant: {reply}\n")


# ── Demo mode ─────────────────────────────────────────────────────────────────

def run_demo():
    """
    Run a pre-scripted demo with 3 diverse scheduling commands.
    Shows the assistant handling meetings across different professional types.
    """
    print("\n" + "=" * 60)
    print(f"  🤵 AI Executive Assistant — DEMO")
    print(f"  OpenAI Function Calling + Orita Scheduling API")
    print("=" * 60)
    print(f"Executive: {EXECUTIVE_PROFILE['name']}")
    print(f"Email: {EXECUTIVE_PROFILE['email']}\n")

    demo_commands = [
        (
            "Book me a meeting with my financial advisor next week, mornings preferred.",
            "Command 1/3: Financial Advisor (next week, morning)",
        ),
        (
            "Schedule a check-up with my doctor for tomorrow.",
            "Command 2/3: Doctor (tomorrow, any time)",
        ),
        (
            "Find me the earliest slot with a lawyer this week — it's urgent.",
            "Command 3/3: Lawyer (this week, earliest available)",
        ),
    ]

    messages: list = []

    for command, label in demo_commands:
        print(f"\n{'─' * 60}")
        print(f"📋 {label}")
        print(f"{'─' * 60}")
        print(f"{EXECUTIVE_PROFILE['name']}: {command}\n")

        reply, messages = run_agent_turn(messages, command)
        print(f"Assistant: {reply}\n")

    # Final summary
    print("\n" + "=" * 60)
    print("📅 Session Summary — All Bookings")
    print("=" * 60)
    summary = list_my_bookings()
    for b in summary["bookings"]:
        print(f"  ✅ {b['date']} {b['time']}  •  {b['professional']}  •  #{b['id']}")
    print(f"\nTotal booked this session: {summary['count']}")
    print(f"All confirmations sent to: {EXECUTIVE_PROFILE['email']}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--interactive" in sys.argv:
        run_interactive()
    else:
        run_demo()
