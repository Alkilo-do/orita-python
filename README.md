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

## Links

- 🌐 **Website:** [orita.online](https://orita.online)
- 📚 **Developer docs:** [orita.online/developers](https://orita.online/developers)
- 🐛 **Issues:** [github.com/Alkilo-do/orita-python/issues](https://github.com/Alkilo-do/orita-python/issues)

---

## License

MIT © [Alkilo-do](https://github.com/Alkilo-do)
