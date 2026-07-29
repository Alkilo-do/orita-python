"""
Orita + CrewAI — Medical Appointment Scheduling Crew

A multi-agent crew that handles medical appointment scheduling:
- Coordinator Agent: understands patient needs, finds the right specialist
- Scheduler Agent: checks availability and confirms the booking

Requirements:
    pip install orita-sdk crewai

Usage:
    export ORITA_API_KEY=orita_xxx
    export OPENAI_API_KEY=sk-xxx
    python crewai_orita.py
"""

import json
import os
from datetime import date, timedelta
from typing import Optional, Type

from crewai import Agent, Crew, Task
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from orita import OritaClient, OritaError

# ── Orita client ──────────────────────────────────────────────────────────────

orita = OritaClient(api_key=os.environ.get("ORITA_API_KEY", "orita_8512592d89fa1b1936adaa9a6e6847db"))
PROVIDER_ID: Optional[str] = os.environ.get("ORITA_PROVIDER_ID", None)

TODAY = date.today().isoformat()
NEXT_MONDAY = (date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)).isoformat()


# ── Tool input schemas ────────────────────────────────────────────────────────

class FindProvidersInput(BaseModel):
    specialty: str = Field(default="", description="Medical specialty to filter by (e.g. 'psychology', 'cardiology').")


class CheckSlotsInput(BaseModel):
    event_type_id: str = Field(description="The Orita event type ID.")
    date_str: str = Field(description="Date in YYYY-MM-DD format.")
    provider_id: str = Field(default="", description="Optional provider ID.")


class BookAppointmentInput(BaseModel):
    event_type_id: str = Field(description="The Orita event type ID.")
    date_str: str = Field(description="Date in YYYY-MM-DD format.")
    time_str: str = Field(description="Time in HH:MM 24h format (e.g. '09:00').")
    client_name: str = Field(description="Patient's first name.")
    client_lastname: str = Field(description="Patient's last name.")
    client_email: str = Field(description="Patient's email address.")
    notes: str = Field(default="", description="Optional clinical notes or reason for visit.")
    provider_id: str = Field(default="", description="Optional provider ID.")


class ListEventTypesInput(BaseModel):
    provider_id: str = Field(default="", description="Optional provider ID to scope the query.")


# ── Orita tools ───────────────────────────────────────────────────────────────

class ListEventTypesTool(BaseTool):
    name: str = "list_event_types"
    description: str = (
        "List all available appointment types (event types) for this account. "
        "Use this to find the correct event_type_id before checking slots or booking."
    )
    args_schema: Type[BaseModel] = ListEventTypesInput

    def _run(self, provider_id: str = "") -> str:
        try:
            pid = provider_id or PROVIDER_ID or None
            event_types = orita.event_types(provider_id=pid)
            if not event_types:
                return "No event types found on this account."
            result = [{"id": e["id"], "title": e["title"], "duration": e.get("duration", "?")} for e in event_types]
            return json.dumps(result, indent=2)
        except OritaError as e:
            return f"Error: {e}"


class FindProvidersTool(BaseTool):
    name: str = "find_providers"
    description: str = (
        "Find healthcare professionals on the platform. "
        "Filter by specialty (e.g. 'psychology', 'physiotherapy'). "
        "Returns a list with each provider's ID and name."
    )
    args_schema: Type[BaseModel] = FindProvidersInput

    def _run(self, specialty: str = "") -> str:
        try:
            pros = orita.professionals(specialty=specialty or None)
            if not pros:
                return json.dumps({"message": "No providers found.", "providers": []})
            result = [
                {
                    "id": p["id"],
                    "name": f"{p.get('name', '')} {p.get('lastname', '')}".strip(),
                    "specialty": p.get("specialty") or p.get("profession") or "General",
                }
                for p in pros
            ]
            return json.dumps({"providers": result}, indent=2)
        except OritaError as e:
            return f"Error: {e}"


class CheckSlotsTool(BaseTool):
    name: str = "check_slots"
    description: str = (
        "Check available appointment time slots for a specific event type and date. "
        "Returns a list of slots with their label (display text) and value (HH:MM for booking). "
        "Try adjacent dates if no slots are found."
    )
    args_schema: Type[BaseModel] = CheckSlotsInput

    def _run(self, event_type_id: str, date_str: str, provider_id: str = "") -> str:
        try:
            pid = provider_id or PROVIDER_ID or None
            slots = orita.slots(event_type_id=event_type_id, date=date_str, provider_id=pid)
            return json.dumps({
                "date": date_str,
                "slots": [{"label": s["label"], "value": s["value"]} for s in slots],
                "count": len(slots),
                "hint": "Use the 'value' field (HH:MM) when calling book_appointment.",
            }, indent=2)
        except OritaError as e:
            return f"Error: {e}"


class BookAppointmentTool(BaseTool):
    name: str = "book_appointment"
    description: str = (
        "Book a medical appointment for a patient. "
        "Requires event_type_id, date (YYYY-MM-DD), time (HH:MM from check_slots), "
        "and patient details (name, lastname, email). "
        "Returns a booking confirmation with ID and status."
    )
    args_schema: Type[BaseModel] = BookAppointmentInput

    def _run(
        self,
        event_type_id: str,
        date_str: str,
        time_str: str,
        client_name: str,
        client_lastname: str,
        client_email: str,
        notes: str = "",
        provider_id: str = "",
    ) -> str:
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
                "patient": f"{client_name} {client_lastname} <{client_email}>",
            }, indent=2)
        except OritaError as e:
            return json.dumps({"success": False, "error": str(e)})


# ── Instantiate tools ─────────────────────────────────────────────────────────

list_event_types_tool = ListEventTypesTool()
find_providers_tool = FindProvidersTool()
check_slots_tool = CheckSlotsTool()
book_appointment_tool = BookAppointmentTool()


# ── Agents ────────────────────────────────────────────────────────────────────

coordinator_agent = Agent(
    role="Medical Appointment Coordinator",
    goal=(
        "Understand what the patient needs, identify the right specialist and appointment type, "
        "and gather all required patient information (name, email, preferred date and time)."
    ),
    backstory=(
        "You are an experienced medical receptionist with deep knowledge of healthcare specialties. "
        "You excel at understanding patient needs, matching them to the right professional, "
        "and collecting all necessary details with empathy and efficiency. "
        f"Today is {TODAY}. Next Monday is {NEXT_MONDAY}."
    ),
    tools=[list_event_types_tool, find_providers_tool],
    verbose=True,
    allow_delegation=True,
)

scheduler_agent = Agent(
    role="Appointment Scheduler",
    goal=(
        "Check availability for the requested date/time and complete the booking. "
        "If the preferred slot is unavailable, find the next best option and confirm with the patient."
    ),
    backstory=(
        "You are a precise scheduling specialist who works with the Orita calendar system. "
        "You always verify slot availability before booking and handle conflicts gracefully "
        "by suggesting alternatives. You never book without confirming the details are correct."
    ),
    tools=[check_slots_tool, book_appointment_tool],
    verbose=True,
    allow_delegation=False,
)


# ── Tasks ─────────────────────────────────────────────────────────────────────

def build_crew(patient_request: str) -> Crew:
    """Build a scheduling crew for the given patient request."""

    coordination_task = Task(
        description=(
            f"A patient has requested: '{patient_request}'\n\n"
            f"Today is {TODAY}. Next Monday is {NEXT_MONDAY}.\n\n"
            "Your job:\n"
            "1. Use list_event_types to find the available appointment types.\n"
            "2. If needed, use find_providers to identify the right specialist.\n"
            "3. Extract the patient's name, email, and preferred date/time from the request.\n"
            "4. Output a clear scheduling brief with: event_type_id, date, preferred_time, "
            "client_name, client_lastname, client_email, and provider_id (if applicable)."
        ),
        expected_output=(
            "A structured scheduling brief in JSON format with: "
            "event_type_id, date (YYYY-MM-DD), preferred_time (HH:MM or 'morning'/'afternoon'), "
            "client_name, client_lastname, client_email, provider_id (or empty string)."
        ),
        agent=coordinator_agent,
    )

    scheduling_task = Task(
        description=(
            "Using the scheduling brief from the coordinator:\n"
            "1. Call check_slots with the event_type_id and date from the brief.\n"
            "2. Select the most appropriate slot (earliest if 'morning', latest morning if afternoon).\n"
            "3. If no slots available, try the next business day.\n"
            "4. Call book_appointment with all the details.\n"
            "5. Return a friendly booking confirmation to the patient."
        ),
        expected_output=(
            "A friendly booking confirmation message including: booking ID, "
            "confirmed date and time, patient name, and any relevant instructions."
        ),
        agent=scheduler_agent,
        context=[coordination_task],
    )

    return Crew(
        agents=[coordinator_agent, scheduler_agent],
        tasks=[coordination_task, scheduling_task],
        verbose=True,
    )


# ── Example usage ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Orita + CrewAI — Medical Appointment Scheduling Crew")
    print("=" * 60)

    patient_request = (
        "I'd like to book a psychology appointment for next Monday morning. "
        "My name is Carlos Rodríguez and my email is carlos.rodriguez@example.com."
    )

    print(f"\nPatient Request: {patient_request}\n")
    print("-" * 60)

    crew = build_crew(patient_request)
    result = crew.kickoff()

    print("\n" + "=" * 60)
    print("Final Result:")
    print("=" * 60)
    print(result)
