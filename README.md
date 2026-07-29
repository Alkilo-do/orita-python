# orita-python

[![PyPI version](https://img.shields.io/pypi/v/orita-sdk.svg)](https://pypi.org/project/orita-sdk/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**The scheduling infrastructure for AI agents — Python SDK**

[Orita](https://orita.online) is the scheduling layer purpose-built for AI agents. Connect your LLM to real calendar availability in minutes.

→ **Docs & API keys:** [orita.online/developers](https://orita.online/developers)

---

## Installation

```bash
pip install orita-sdk
```

## Quickstart

```python
from orita import OritaClient

client = OritaClient(api_key="orita_your_key_here")
slots  = client.slots(event_type_id="evt_abc123", date="2026-08-01")
booking = client.book(
    event_type_id="evt_abc123", date="2026-08-01", time=slots[0]["value"],
    client_name="Ana", client_lastname="López", client_email="ana@example.com",
)
print(booking["id"])  # book_xyz789
```

---

## Authentication

All requests require an API key obtained from [orita.online/developers](https://orita.online/developers).

```python
from orita import OritaClient

client = OritaClient(api_key="orita_your_key_here")
```

API keys must start with `orita_`. Pass a custom `base_url` to point to a self-hosted or staging instance.

---

## API Reference

### `client.event_types() → list`

List all active event types for your account.

```python
event_types = client.event_types()
# [{"id": "evt_abc123", "title": "Initial Consultation", "duration": 30, ...}]
```

---

### `client.slots(event_type_id, date) → list`

Get available time slots for a given event type on a specific date.

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type_id` | `str` | Event type ID from `event_types()` |
| `date` | `str` | Date in `YYYY-MM-DD` format |

```python
slots = client.slots(event_type_id="evt_abc123", date="2026-08-01")
# [{"label": "09:00 AM", "value": "09:00"}, {"label": "09:30 AM", "value": "09:30"}, ...]
```

---

### `client.book(...) → dict`

Book an appointment. Returns the created booking object.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `event_type_id` | `str` | ✅ | Event type ID |
| `date` | `str` | ✅ | Date in `YYYY-MM-DD` |
| `time` | `str` | ✅ | Time in `HH:MM` (from `slots()`) |
| `client_name` | `str` | ✅ | Client first name |
| `client_lastname` | `str` | ✅ | Client last name |
| `client_email` | `str` | ✅ | Client email |
| `client_timezone` | `str` | ❌ | IANA timezone (e.g. `America/New_York`) |
| `notes` | `str` | ❌ | Additional notes for the professional |

```python
booking = client.book(
    event_type_id="evt_abc123",
    date="2026-08-01",
    time="10:00",
    client_name="Carlos",
    client_lastname="García",
    client_email="carlos@example.com",
    client_timezone="America/Bogota",
    notes="First appointment — prefers video call",
)
# {"id": "book_xyz789", "status": "confirmed", "date": "2026-08-01", ...}
```

---

### `client.bookings(page, limit, status) → list`

List bookings with optional filtering.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | `int` | `1` | Page number |
| `limit` | `int` | `20` | Results per page |
| `status` | `str` | `None` | Filter: `confirmed`, `cancelled`, `completed` |

```python
confirmed = client.bookings(status="confirmed")
all_bookings = client.bookings(page=2, limit=50)
```

---

### `client.get_booking(booking_id) → dict`

Retrieve a single booking by ID.

```python
booking = client.get_booking("book_xyz789")
print(booking["status"])  # "confirmed"
```

---

### `client.cancel(booking_id) → dict`

Cancel a booking by ID.

```python
result = client.cancel("book_xyz789")
print(result["status"])  # "cancelled"
```

---

### `client.profile() → dict`

Get your own **Capability Manifest** — the machine-readable description of your scheduling configuration that AI agents can read to understand how to book you.

```python
manifest = client.profile()
print(manifest["username"])
print(manifest["eventTypes"])
```

---

### `client.update_profile(**fields) → dict`

Update your profile fields.

```python
updated = client.update_profile(bio="AI-native therapist", timezone="Europe/Madrid")
```

---

### `client.get_profile(username) → dict`

Fetch the **public Capability Manifest** for any professional by username. No API key required internally — useful for cross-professional lookups.

```python
manifest = client.get_profile("dra-martinez")
# {"username": "dra-martinez", "eventTypes": [...], ...}
```

---

---

## Platform Accounts

If you are building a **scheduling platform** that hosts multiple professionals, use the `provider_id` parameter to scope API calls to a specific provider on your account.

### List professionals

```python
# List all professionals on your platform
professionals = client.professionals()

# Filter by specialty, language, profession, or location
pros = client.professionals(specialty="fisioterapia", language="es")
for pro in pros:
    print(pro["id"], pro["name"])
```

### Create an event type for a provider

```python
event_type = client.create_event_type(
    title="Consulta inicial",
    duration=30,
    location="Online",
    description="Primera visita con el profesional",
    provider_id="pro_abc123",
    buffer_time=15,
)
print(event_type["id"])  # evt_new456
```

### Scope bookings to a specific provider

```python
# Get event types for a specific provider
event_types = client.event_types(provider_id="pro_abc123")

# Get slots for a provider's event type
slots = client.slots(
    event_type_id="evt_new456",
    date="2026-08-01",
    provider_id="pro_abc123",
)

# Book under a specific provider
booking = client.book(
    event_type_id="evt_new456",
    date="2026-08-01",
    time=slots[0]["value"],
    client_name="María",
    client_lastname="Torres",
    client_email="maria@example.com",
    provider_id="pro_abc123",
)
print(booking["id"])  # book_xyz789

# List bookings for a provider
provider_bookings = client.bookings(provider_id="pro_abc123")
```

### Full platform flow example

```python
from orita import OritaClient
from datetime import date, timedelta

client = OritaClient(api_key="orita_your_platform_key")

# 1. List all professionals on the platform
professionals = client.professionals(specialty="psicología")
provider_id = professionals[0]["id"]

# 2. Create an event type for this provider
event_type = client.create_event_type(
    title="Consulta psicológica",
    duration=50,
    location="Online",
    provider_id=provider_id,
)

# 3. Get available slots for tomorrow
tomorrow = (date.today() + timedelta(days=1)).isoformat()
slots = client.slots(
    event_type_id=event_type["id"],
    date=tomorrow,
    provider_id=provider_id,
)

# 4. Book with the provider
if slots:
    booking = client.book(
        event_type_id=event_type["id"],
        date=tomorrow,
        time=slots[0]["value"],
        client_name="Juan",
        client_lastname="Pérez",
        client_email="juan@example.com",
        provider_id=provider_id,
    )
    print(f"✅ Booked with provider {provider_id}: {booking['id']}")
```

---

## Error Handling

```python
from orita import OritaClient
from orita import OritaAuthError, OritaNotFoundError, OritaSlotUnavailableError, OritaError

client = OritaClient(api_key="orita_your_key")

try:
    booking = client.book(
        event_type_id="evt_abc123",
        date="2026-08-01",
        time="10:00",
        client_name="Ana",
        client_lastname="López",
        client_email="ana@example.com",
    )
except OritaAuthError:
    print("Invalid API key")
except OritaSlotUnavailableError:
    print("That slot was just taken — fetch slots again")
except OritaNotFoundError:
    print("Event type not found")
except OritaError as e:
    print(f"API error: {e}")
```

| Exception | HTTP Status | When |
|-----------|-------------|------|
| `OritaAuthError` | 401 | Invalid or missing API key |
| `OritaNotFoundError` | 404 | Resource not found |
| `OritaSlotUnavailableError` | 409 | Slot already taken |
| `OritaError` | Other 4xx/5xx | Generic API error |

---

## Framework Integrations

### OpenAI Agents SDK

Give your OpenAI agent the ability to book appointments in real time:

```python
from openai import OpenAI
from orita import OritaClient
import json

orita = OritaClient(api_key="orita_your_key")
client = OpenAI()

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_available_slots",
            "description": "Get available appointment slots for a given date",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type_id": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["event_type_id", "date"],
            },
        },
    },
]

def handle_tool_call(name, args):
    if name == "get_available_slots":
        return json.dumps(orita.slots(args["event_type_id"], args["date"]))
```

→ Full example: [`examples/openai_agent.py`](examples/openai_agent.py)

---

### LangChain

Wrap Orita methods as LangChain `@tool` functions:

```python
from langchain.tools import tool
from orita import OritaClient

orita = OritaClient(api_key="orita_your_key")

@tool
def get_available_slots(date_str: str) -> str:
    """Get available appointment slots for a date (YYYY-MM-DD)."""
    slots = orita.slots(event_type_id="evt_abc123", date=date_str)
    return "\n".join([f"- {s['label']}" for s in slots])

@tool
def book_appointment(date_str: str, time_str: str, name: str, lastname: str, email: str) -> str:
    """Book an appointment for a client."""
    booking = orita.book(
        event_type_id="evt_abc123", date=date_str, time=time_str,
        client_name=name, client_lastname=lastname, client_email=email,
    )
    return f"Confirmed! Booking ID: {booking['id']}"
```

→ Full example: [`examples/langchain_tool.py`](examples/langchain_tool.py)

---

### LangGraph

Build a full scheduling agent as a **LangGraph `StateGraph`** — with nodes for understanding the request, querying availability, and confirming the booking:

```python
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from orita import OritaClient
from typing import Annotated, TypedDict
import json, os

orita = OritaClient(api_key=os.environ["ORITA_API_KEY"])

@tool
def check_slots(event_type_id: str, date_str: str) -> str:
    """Get available appointment slots for a given date (YYYY-MM-DD)."""
    slots = orita.slots(event_type_id=event_type_id, date=date_str)
    return json.dumps({"slots": [{"label": s["label"], "value": s["value"]} for s in slots]})

@tool
def confirm_booking(event_type_id: str, date_str: str, time_str: str,
                    client_name: str, client_lastname: str, client_email: str) -> str:
    """Confirm and create an appointment booking."""
    booking = orita.book(
        event_type_id=event_type_id, date=date_str, time=time_str,
        client_name=client_name, client_lastname=client_lastname, client_email=client_email,
    )
    return json.dumps({"booking_id": booking["id"], "status": booking["status"]})

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

orita_tools = [check_slots, confirm_booking]
tool_map = {t.name: t for t in orita_tools}

llm = ChatOpenAI(model="gpt-4o", temperature=0).bind_tools(orita_tools)

def understand_and_plan(state):
    from langchain_core.messages import SystemMessage
    messages = [SystemMessage(content="You are a scheduling assistant. Use tools to check slots and book appointments.")]
    return {"messages": [llm.invoke(messages + state["messages"])]}

def execute_tool(state):
    from langchain_core.messages import ToolMessage
    last = state["messages"][-1]
    results = []
    for call in last.tool_calls:
        result = tool_map[call["name"]].invoke(call["args"])
        results.append(ToolMessage(content=result, tool_call_id=call["id"], name=call["name"]))
    return {"messages": results}

def should_continue(state):
    last = state["messages"][-1]
    return "execute_tool" if getattr(last, "tool_calls", None) else END

graph = StateGraph(AgentState)
graph.add_node("understand", understand_and_plan)
graph.add_node("execute_tool", execute_tool)
graph.set_entry_point("understand")
graph.add_conditional_edges("understand", should_continue, {"execute_tool": "execute_tool", END: END})
graph.add_edge("execute_tool", "understand")
app = graph.compile()

# Run
from langchain_core.messages import HumanMessage
result = app.invoke({"messages": [HumanMessage(
    content="Book me a slot next Monday at 10am. I'm Ana López, ana@example.com"
)]})
print(result["messages"][-1].content)
```

→ Full example with `find_providers`, retry logic, and multi-turn support: [`examples/langgraph_orita.py`](examples/langgraph_orita.py)

---

### CrewAI

```python
from crewai.tools import tool
from orita import OritaClient

orita = OritaClient(api_key="orita_your_key")

@tool("Get Available Slots")
def get_slots(event_type_id: str, date: str) -> str:
    """Get available appointment slots. Input: event_type_id and date (YYYY-MM-DD)."""
    slots = orita.slots(event_type_id=event_type_id, date=date)
    return str([{"label": s["label"], "value": s["value"]} for s in slots])

@tool("Book Appointment")
def book(event_type_id: str, date: str, time: str,
         client_name: str, client_lastname: str, client_email: str) -> str:
    """Book an appointment for a client."""
    booking = orita.book(
        event_type_id=event_type_id, date=date, time=time,
        client_name=client_name, client_lastname=client_lastname, client_email=client_email,
    )
    return f"Booking {booking['id']} confirmed for {date} at {time}"
```

---

## Full Example: Book from Available Slots

```python
from orita import OritaClient
from datetime import date, timedelta

client = OritaClient(api_key="orita_your_key_here")

# 1. Get event types
event_types = client.event_types()
event_type_id = event_types[0]["id"]

# 2. Get tomorrow's slots
tomorrow = (date.today() + timedelta(days=1)).isoformat()
slots = client.slots(event_type_id=event_type_id, date=tomorrow)

# 3. Book the first available
if slots:
    booking = client.book(
        event_type_id=event_type_id,
        date=tomorrow,
        time=slots[0]["value"],
        client_name="Juan",
        client_lastname="García",
        client_email="juan@example.com",
    )
    print(f"✅ Booked: {booking['id']}")
else:
    print("No availability tomorrow")
```

---

## Requirements

- Python 3.8+
- `requests >= 2.28`

---

## Node.js / TypeScript

Looking for the JavaScript / TypeScript SDK?

```bash
npm install orita-sdk
```

```typescript
import { OritaClient } from 'orita-sdk';

const orita = new OritaClient({ apiKey: process.env.ORITA_API_KEY });

const { slots } = await orita.getSlots('evt_abc123', '2026-08-01');
const booking  = await orita.book({
  eventTypeId: 'evt_abc123', date: '2026-08-01', time: slots[0].value,
  clientName: 'Ana', clientLastname: 'López', clientEmail: 'ana@example.com',
});
```

→ **npm:** [npmjs.com/package/orita-sdk](https://www.npmjs.com/package/orita-sdk)  
→ **GitHub:** [github.com/Alkilo-do/orita-node](https://github.com/Alkilo-do/orita-node)

---

## Links

- 🌐 **Website:** [orita.online](https://orita.online)
- 📚 **Developer docs:** [orita.online/developers](https://orita.online/developers)
- 🟨 **Node.js / TypeScript SDK:** [github.com/Alkilo-do/orita-node](https://github.com/Alkilo-do/orita-node) — `npm install orita-sdk`
- 🐛 **Issues:** [github.com/Alkilo-do/orita-python/issues](https://github.com/Alkilo-do/orita-python/issues)

---

## License

MIT © [Alkilo-do](https://github.com/Alkilo-do)
