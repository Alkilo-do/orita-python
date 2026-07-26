"""
OpenAI Agents SDK integration example.
Books appointments via an AI agent using Orita as the scheduling backend.
"""
from openai import OpenAI
from orita import OritaClient
import json

orita = OritaClient(api_key="orita_your_key_here")
openai_client = OpenAI()

# Define Orita tools for the OpenAI agent
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_available_slots",
            "description": "Get available appointment slots for a given date",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {"type": "string", "description": "The event type ID"},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                },
                "required": ["event_type_id", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book an appointment for a client",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {"type": "string"},
                    "date": {"type": "string"},
                    "time": {"type": "string", "description": "Time in HH:MM format"},
                    "client_name": {"type": "string"},
                    "client_lastname": {"type": "string"},
                    "client_email": {"type": "string"},
                },
                "required": ["event_type_id", "date", "time", "client_name", "client_lastname", "client_email"],
            },
        },
    },
]

def handle_tool_call(name, args):
    if name == "get_available_slots":
        slots = orita.slots(args["event_type_id"], args["date"])
        return json.dumps(slots)
    elif name == "book_appointment":
        booking = orita.book(**args)
        return json.dumps(booking)

# Simple agent loop
event_types = orita.event_types()
EVENT_TYPE_ID = event_types[0]["id"]

messages = [
    {"role": "system", "content": f"You are a scheduling assistant. Event type ID: {EVENT_TYPE_ID}"},
    {"role": "user", "content": "Book me an appointment for tomorrow at the earliest available slot. My name is Ana López, email ana@example.com"},
]

response = openai_client.chat.completions.create(model="gpt-4o", messages=messages, tools=tools)
# Handle tool calls here...
print(response.choices[0].message)
