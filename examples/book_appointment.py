"""
Basic example: find available slots and book an appointment.
"""
from orita import OritaClient

client = OritaClient(api_key="orita_your_key_here")

# 1. Get your event types
event_types = client.event_types()
event_type_id = event_types[0]["id"]
print(f"Using event type: {event_types[0]['title']}")

# 2. Get available slots for tomorrow
from datetime import date, timedelta
tomorrow = (date.today() + timedelta(days=1)).isoformat()
slots = client.slots(event_type_id=event_type_id, date=tomorrow)
print(f"Available slots: {[s['label'] for s in slots[:5]]}")

# 3. Book the first available slot
if slots:
    booking = client.book(
        event_type_id=event_type_id,
        date=tomorrow,
        time=slots[0]["value"],
        client_name="Juan",
        client_lastname="García",
        client_email="juan@example.com",
    )
    print(f"Booking created: {booking['id']}")
    print(f"Status: {booking['status']}")
