import requests
from typing import Optional
from .exceptions import OritaError, OritaAuthError, OritaNotFoundError, OritaSlotUnavailableError

class OritaClient:
    BASE_URL = "https://orita.online/api/v1"

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        if not api_key.startswith("orita_"):
            raise OritaAuthError("API key must start with 'orita_'")
        self.api_key = api_key
        self.base_url = base_url or self.BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, **kwargs)
        if response.status_code == 401:
            raise OritaAuthError("Invalid API key")
        if response.status_code == 404:
            raise OritaNotFoundError(response.json().get("error", "Not found"))
        if response.status_code == 409:
            raise OritaSlotUnavailableError(response.json().get("error", "Slot unavailable"))
        if not response.ok:
            raise OritaError(response.json().get("error", "API error"))
        return response.json()

    def event_types(self, provider_id: Optional[str] = None) -> list:
        """List all active event types for this account (or a platform provider)."""
        params = {}
        if provider_id:
            params["providerId"] = provider_id
        return self._request("GET", "/event-types", params=params if params else None)["data"]

    def slots(self, event_type_id: str, date: str, provider_id: Optional[str] = None) -> list:
        """Get available time slots for an event type on a given date (YYYY-MM-DD)."""
        params = {
            "eventTypeId": event_type_id,
            "date": date,
        }
        if provider_id:
            params["providerId"] = provider_id
        data = self._request("GET", "/slots", params=params)
        return data["slots"]

    def book(
        self,
        event_type_id: str,
        date: str,
        time: str,
        client_name: str,
        client_lastname: str,
        client_email: str,
        client_timezone: Optional[str] = None,
        notes: Optional[str] = None,
        provider_id: Optional[str] = None,
    ) -> dict:
        """Book an appointment. Returns the booking object."""
        payload = {
            "eventTypeId": event_type_id,
            "date": date,
            "time": time,
            "clientName": client_name,
            "clientLastname": client_lastname,
            "clientEmail": client_email,
        }
        if client_timezone:
            payload["clientTimezone"] = client_timezone
        if notes:
            payload["notes"] = notes
        if provider_id:
            payload["providerId"] = provider_id
        return self._request("POST", "/bookings", json=payload)["data"]

    def bookings(self, page: int = 1, limit: int = 20, status: Optional[str] = None, provider_id: Optional[str] = None) -> list:
        """List bookings with optional status filter."""
        params = {"page": page, "limit": limit}
        if status:
            params["status"] = status
        if provider_id:
            params["providerId"] = provider_id
        return self._request("GET", "/bookings", params=params)["data"]

    def get_booking(self, booking_id: str) -> dict:
        """Get a booking by ID."""
        return self._request("GET", f"/bookings/{booking_id}")["data"]

    def cancel(self, booking_id: str) -> dict:
        """Cancel a booking by ID."""
        return self._request("POST", f"/bookings/{booking_id}/cancel")["data"]

    def professionals(self, specialty: Optional[str] = None, language: Optional[str] = None, profession: Optional[str] = None, location: Optional[str] = None) -> list:
        """List professionals on the platform, with optional filters."""
        params = {}
        if specialty:
            params["specialty"] = specialty
        if language:
            params["language"] = language
        if profession:
            params["profession"] = profession
        if location:
            params["location"] = location
        return self._request("GET", "/professionals", params=params if params else None)["data"]

    def create_event_type(
        self,
        title: str,
        duration: int,
        location: str = "Online",
        description: str = "",
        availability_id: Optional[str] = None,
        provider_id: Optional[str] = None,
        buffer_time: int = 15,
        scheduling_notice_days: str = "0",
        scheduling_notice_hours: str = "0",
    ) -> dict:
        """Create a new event type. Returns the created event type."""
        payload = {
            "title": title,
            "duration": duration,
            "location": location,
            "description": description,
            "bufferTime": buffer_time,
            "schedulingNoticeDays": scheduling_notice_days,
            "schedulingNoticeHours": scheduling_notice_hours,
        }
        if availability_id:
            payload["availabilityId"] = availability_id
        if provider_id:
            payload["providerId"] = provider_id
        return self._request("POST", "/event-types", json=payload)["data"]

    def profile(self) -> dict:
        """Get your agent capability manifest (Capability Manifest)."""
        return self._request("GET", "/profile")["data"]

    def update_profile(self, **fields) -> dict:
        """Update your agent profile fields."""
        return self._request("PUT", "/profile", json=fields)["data"]

    def get_profile(self, username: str) -> dict:
        """Get the public Capability Manifest for any professional by username (no auth needed)."""
        import requests as req
        response = req.get(f"{self.base_url}/profile", params={"username": username})
        if response.status_code == 404:
            raise OritaNotFoundError(f"Professional '{username}' not found")
        return response.json()["data"]
