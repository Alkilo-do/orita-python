"""
Orita + OpenAI Agents SDK — Scheduling Agent Example

A medical appointment scheduling agent that uses the Orita API
to check availability and book appointments.

Requirements:
    pip install orita-sdk openai-agents

Usage:
    export ORITA_API_KEY=orita_xxx
    export OPENAI_API_KEY=sk-xxx
    python openai_agents_orita.py
"""

import os
from datetime import date, timedelta

from agents import Agent, Runner, tool
from orita import OritaClient, OritaError

# ── Orita client ──────────────────────────────────────────────────────────────

orita = OritaClient(api_key=os.environ.get("ORITA_API_KEY", "orita_8512592d89fa1b1936adaa9a6e6847db"))

# Optional: scope all calls to a specific provider (multi-tenant platforms)
PROVIDER_ID: str | None = os.environ.get("ORITA_PROVIDER_ID", None)


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def list_providers() -> str:
    """
    List available professionals / providers on the platform.
    Returns a JSON list with each provider's id, name, and specialty.
    Use this first to find which provider the patient wants.
    """
    try:
        professionals = orita.professionals()
        if not professionals:
            return "No professionals found on this account."
        lines = []
        for p in professionals:
            name = f"{p.get('name', '')} {p.get('lastname', '')}".strip()
            specialty = p.get("specialty") or p.get("profession") or "General"
            lines.append(f"- ID: {p['id']} | Name: {name} | Specialty: {specialty}")
        return "Available professionals:\n" + "\n".join(lines)
    except OritaError as e:
        return f"Error fetching providers: {e}"


@tool
def get_available_slots(event_type_id: str, date_str: str, provider_id: str = "") -> str:
    """
    Get available appointment slots for a given event type and date.

    Args:
        event_type_id: The event type ID (get from the account's event types).
        date_str: Target date in YYYY-MM-DD format.
        provider_id: Optional provider/professional ID to scope the query.

    Returns a list of available time slots with their labels and values (HH:MM).
    """
    try:
        pid = provider_id or PROVIDER_ID or None
        slots = orita.slots(event_type_id=event_type_id, date=date_str, provider_id=pid)
        if not slots:
            return f"No slots available on {date_str}. Try a different date."
        lines = [f"- {s['label']} (book with time: {s['value']})" for s in slots]
        return f"Available slots on {date_str}:\n" + "\n".join(lines)
    except OritaError as e:
        return f"Error fetching slots: {e}"


@tool
def book_appointment(
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
    Book an appointment for a patient.

    Args:
        event_type_id: The event type ID.
        date_str: Date in YYYY-MM-DD format.
        time_str: Time in HH:MM format (from get_available_slots).
        client_name: Patient's first name.
        client_lastname: Patient's last name.
        client_email: Patient's email address.
        notes: Optional clinical notes or reason for visit.
        provider_id: Optional provider ID (required on multi-tenant platforms).

    Returns confirmation with booking ID and status.
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
        return (
            f"✅ Appointment confirmed!\n"
            f"  Booking ID : {booking['id']}\n"
            f"  Status     : {booking['status']}\n"
            f"  Date       : {booking.get('date', date_str)} at {booking.get('time', time_str)}\n"
            f"  Patient    : {client_name} {client_lastname} ({client_email})"
        )
    except OritaError as e:
        return f"❌ Booking failed: {e}"


# ── Agent ─────────────────────────────────────────────────────────────────────

# Resolve the event type at startup so the agent knows what to use by default
try:
    _event_types = orita.event_types(provider_id=PROVIDER_ID)
    _default_et = _event_types[0] if _event_types else None
    _et_context = (
        f"Default event type: '{_default_et['title']}' (ID: {_default_et['id']})"
        if _default_et
        else "No event types configured — ask the user for the event type ID."
    )
except OritaError:
    _et_context = "Could not load event types at startup."

# Compute a useful "next Monday morning" example date
_today = date.today()
_days_until_monday = (7 - _today.weekday()) % 7 or 7
_next_monday = (_today + timedelta(days=_days_until_monday)).isoformat()

scheduling_agent = Agent(
    name="Orita Scheduling Agent",
    model="gpt-4o",
    instructions=f"""You are a friendly medical appointment scheduling assistant powered by Orita.

{_et_context}

Your workflow:
1. Greet the patient and understand their needs (specialist type, preferred date/time).
2. If they need a specific specialist, use `list_providers` to find available professionals.
3. Use `get_available_slots` to check availability for the requested date.
   - If no slots are available, try nearby dates (±1-3 days).
   - Suggest morning slots (before 12:00) when the patient says "morning".
4. Confirm the details with the patient before booking.
5. Use `book_appointment` to finalize the reservation.
6. Share the booking confirmation including the booking ID.

Today is {_today.isoformat()}. Next Monday is {_next_monday}.

Always be empathetic and professional. If a slot is taken, apologize and offer alternatives.
""",
    tools=[list_providers, get_available_slots, book_appointment],
)


# ── Example usage ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Orita + OpenAI Agents SDK — Scheduling Agent")
    print("=" * 60)

    # Example: Book an appointment via natural language
    user_request = (
        "Hi! I need to book a psychology appointment for next Monday morning. "
        "My name is María García and my email is maria.garcia@example.com."
    )

    print(f"\nUser: {user_request}\n")

    result = Runner.run_sync(scheduling_agent, user_request)

    print(f"Agent: {result.final_output}")
    print("\n" + "=" * 60)
