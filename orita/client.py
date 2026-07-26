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

    def event_types(self) -> list:
        """List all active event types for this account."""
        return self._request("GET", "/event-types")["data"]

    def slots(self, event_type_id: str, date: str) -> list:
        """Get available time slots for an event type on a given date (YYYY-MM-DD)."""
        data = self._request("GET", "/slots", params={
            "eventTypeId": event_type_id,
            "date": date,
        })
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
        return self._request("POST", "/bookings", json=payload)["data"]

    def bookings(self, page: int = 1, limit: int = 20, status: Optional[str] = None) -> list:
        """List bookings with optional status filter."""
        params = {"page": page, "limit": limit}
        if status:
            params["status"] = status
        return self._request("GET", "/bookings", params=params)["data"]

    def get_booking(self, booking_id: str) -> dict:
        """Get a booking by ID."""
        return self._request("GET", f"/bookings/{booking_id}")["data"]

    def cancel(self, booking_id: str) -> dict:
        """Cancel a booking by ID."""
        return self._request("POST", f"/bookings/{booking_id}/cancel")["data"]

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
