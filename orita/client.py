"""
Orita Python SDK — Provider Resolution API v2

Primary workflow (provider resolution):
    from orita import OritaClient

    client = OritaClient(api_key="orita_live_...")

    # 1. Resolve — find eligible providers with verified availability
    resolution = client.resolutions.create(
        service_id="svc_therapy",
        date_range={"from": "2026-08-05", "to": "2026-08-12"},
        constraints={"languageCodes": {"anyOf": ["es"]}, "acceptsNewClients": True},
    )

    # 2. Inspect candidates (optional)
    candidates = client.resolutions.list_candidates(resolution["resolutionId"])

    # 3. Hold the chosen option
    hold = client.resolutions.hold_option(
        resolution["resolutionId"],
        resolution["options"][0]["optionId"],
    )

    # 4. Confirm — creates the booking atomically
    booking = client.resolutions.confirm(
        resolution["resolutionId"],
        option_id=resolution["options"][0]["optionId"],
        hold_id=hold["holdId"],
        customer={"name": "Ana García", "email": "ana@example.com"},
        idempotency_key="session-abc-confirm-1",
    )

Secondary workflow (known-provider direct scheduling) — uses v1 API:
    slots   = client.slots(event_type_id="evt_...", date="2026-08-05")
    booking = client.book(slot_id=slots[0]["id"], customer={"name": "...", ...})
"""

import uuid
import requests
from typing import Optional
from .exceptions import OritaError, OritaAuthError, OritaNotFoundError, OritaSlotUnavailableError


class _Namespace:
    """Base class for API namespaces."""

    def __init__(self, client: "OritaClient"):
        self._c = client


class ResolutionsNamespace(_Namespace):
    """
    Provider resolution — unknown-provider workflow.
    Maps to POST /api/v2/resolutions and related endpoints.
    """

    def create(
        self,
        service_id: str,
        date_range: dict,
        constraints: Optional[dict] = None,
        preferences: Optional[dict] = None,
        limit: int = 5,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Search the provider network, apply eligibility rules, and return
        ranked explained options.

        Args:
            service_id:       Service or event type ID to match against.
            date_range:       {'from': 'YYYY-MM-DD', 'to': 'YYYY-MM-DD'[, 'timezone': '...']}
            constraints:      Hard eligibility constraints. Supported keys:
                              languageCodes, modalityCodes, licenseRegionCodes,
                              insurancePlanCodes, ageGroupCodes, specialtyCodes,
                              professionCodes, acceptsNewClients, serviceRegionCodes.
                              Each code list uses {'anyOf': [...]} format.
            preferences:      Soft ranking preferences. Supported keys:
                              dayParts (['morning','afternoon','evening']),
                              earliestAvailable (bool),
                              continuityProviderId (str).
            limit:            Max options to return (default 5).
            idempotency_key:  Optional key for safe retries.

        Returns:
            Resolution dict with resolutionId, status, options, exclusionSummary, warnings.

        Example:
            resolution = client.resolutions.create(
                service_id='svc_therapy',
                date_range={'from': '2026-08-05', 'to': '2026-08-12'},
                constraints={
                    'languageCodes': {'anyOf': ['es']},
                    'modalityCodes': {'anyOf': ['virtual']},
                    'acceptsNewClients': True,
                },
                preferences={'dayParts': ['afternoon'], 'earliestAvailable': True},
            )
        """
        payload: dict = {
            "serviceId":  service_id,
            "dateRange":  date_range,
            "limit":      limit,
        }
        if constraints:
            payload["constraints"] = constraints
        if preferences:
            payload["preferences"] = preferences

        headers: dict = {}
        key = idempotency_key or str(uuid.uuid4())
        headers["Idempotency-Key"] = key

        return self._c._request("POST", "/resolutions", json=payload, extra_headers=headers, v2=True)

    def get(self, resolution_id: str) -> dict:
        """
        Retrieve a stored resolution by ID, including all ranked options and scores.

        Args:
            resolution_id: The resolution ID returned by create().

        Returns:
            Resolution dict with resolutionId, status, options, exclusionSummary.
        """
        return self._c._request("GET", f"/resolutions/{resolution_id}", v2=True)

    def list_candidates(
        self,
        resolution_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        """
        Retrieve per-provider eligibility records for a resolution.
        Use to debug zero results, unexpected exclusions, or unknown data.

        Args:
            resolution_id: Resolution ID.
            status:        Filter by eligibility: 'matched' | 'excluded' | 'unknown'.
            limit:         Max results (default 50, max 500).

        Returns:
            Dict with candidates list and summary counts.
        """
        params: dict = {"limit": limit}
        if status:
            params["status"] = status
        return self._c._request(
            "GET",
            f"/resolutions/{resolution_id}/candidates",
            params=params,
            v2=True,
        )

    def hold_option(
        self,
        resolution_id: str,
        option_id: str,
        ttl_seconds: int = 120,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Temporarily hold a resolution option to prevent concurrent bookings.

        Args:
            resolution_id:   Resolution ID.
            option_id:       Option ID to hold.
            ttl_seconds:     Hold duration in seconds (default 120, max 600).
            idempotency_key: Optional key for safe retries.

        Returns:
            Dict with holdId, status='active', expiresAt.
        """
        headers: dict = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return self._c._request(
            "POST",
            f"/resolutions/{resolution_id}/options/{option_id}/hold",
            json={"ttlSeconds": ttl_seconds},
            extra_headers=headers or None,
            v2=True,
        )

    def release_hold(self, resolution_id: str, option_id: str) -> dict:
        """
        Release an active hold before it expires.

        Args:
            resolution_id: Resolution ID.
            option_id:     Option ID whose hold should be released.

        Returns:
            Dict with holdId, status='released'.
        """
        return self._c._request(
            "DELETE",
            f"/resolutions/{resolution_id}/options/{option_id}/hold",
            v2=True,
        )

    def confirm(
        self,
        resolution_id: str,
        option_id: str,
        customer: dict,
        hold_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Confirm a resolution option and atomically create a booking.
        Requires human approval before calling — do not auto-confirm.

        Args:
            resolution_id:   Resolution ID.
            option_id:       Option ID to confirm.
            customer:        Dict with name (str), email (str), and optionally timezone (str).
            hold_id:         Hold ID from hold_option() — recommended, prevents races.
            metadata:        Optional key-value pairs to attach to the booking.
            idempotency_key: Required for safe retries. Auto-generated if not provided.

        Returns:
            Booking dict with id, status='confirmed', provider, service, slot.

        Example:
            booking = client.resolutions.confirm(
                resolution_id=resolution['resolutionId'],
                option_id=resolution['options'][0]['optionId'],
                hold_id=hold['holdId'],
                customer={'name': 'James Park', 'email': 'james@example.com'},
                idempotency_key='session-abc-confirm-1',
            )
        """
        payload: dict = {
            "optionId": option_id,
            "customer": customer,
        }
        if hold_id:
            payload["holdId"] = hold_id
        if metadata:
            payload["metadata"] = metadata

        headers: dict = {"Idempotency-Key": idempotency_key or str(uuid.uuid4())}

        return self._c._request(
            "POST",
            f"/resolutions/{resolution_id}/confirm",
            json=payload,
            extra_headers=headers,
            v2=True,
        )


class ProvidersNamespace(_Namespace):
    """Provider graph management — POST/GET/PUT /api/v2/providers"""

    def create(self, **fields) -> dict:
        """
        Create a single provider in the provider graph.

        Required fields: displayName, timezone.
        Optional: externalId, professionCode, specialtyCodes, languageCodes,
                  modalityCodes, serviceRegionCodes, insurancePlanCodes,
                  ageGroupCodes, licenseRecords, acceptsNewClients.

        Returns:
            Created provider dict with id, organizationId, profileVersion.
        """
        return self._c._request("POST", "/providers", json=fields, v2=True)

    def list(
        self,
        status: str = "active",
        limit: int = 50,
    ) -> dict:
        """
        List providers in the organization.

        Args:
            status: Filter by status ('active', 'inactive', 'all').
            limit:  Max results (default 50, max 200).

        Returns:
            Dict with data (list of providers), total, hasMore.
        """
        return self._c._request(
            "GET",
            "/providers",
            params={"status": status, "limit": limit},
            v2=True,
        )

    def get(self, provider_id: str) -> dict:
        """Retrieve a single provider by ID."""
        return self._c._request("GET", f"/providers/{provider_id}", v2=True)

    def update(self, provider_id: str, **fields) -> dict:
        """
        Update a provider profile. Increments profileVersion.
        externalId cannot be changed via update — use bulk import for re-keying.
        """
        return self._c._request("PUT", f"/providers/{provider_id}", json=fields, v2=True)

    def deactivate(self, provider_id: str) -> dict:
        """Mark a provider inactive. Excluded from future resolutions."""
        return self._c._request("POST", f"/providers/{provider_id}/deactivate", v2=True)

    def reactivate(self, provider_id: str) -> dict:
        """Restore a deactivated provider to active and searchable state."""
        return self._c._request("POST", f"/providers/{provider_id}/reactivate", v2=True)

    def readiness(self, provider_id: str) -> dict:
        """
        Check whether a provider is ready for resolution.

        Returns:
            Dict with readiness ('ready'|'warning'|'blocked'|'unknown'),
            readyForResolution (bool), and issues list.
        """
        return self._c._request("GET", f"/providers/{provider_id}/readiness", v2=True)


class ProviderImportsNamespace(_Namespace):
    """Bulk provider synchronization — POST /api/v2/provider-imports"""

    def create(
        self,
        providers: list,
        mode: str = "upsert",
        dry_run: bool = False,
    ) -> dict:
        """
        Bulk-upsert up to 500 providers. Use your externalId as the stable key.

        Args:
            providers: List of provider dicts. Each must have at minimum displayName.
            mode:      'upsert' (default), 'create_only', or 'update_only'.
            dry_run:   If True, validates rows without writing to the database.

        Returns:
            Dict with importId, status, summary (received, created, updated, failed).
        """
        return self._c._request(
            "POST",
            "/provider-imports",
            json={"providers": providers, "mode": mode, "dryRun": dry_run},
            v2=True,
        )

    def get(self, import_id: str) -> dict:
        """
        Poll the status of a provider import job.

        Args:
            import_id: Import ID returned by create().

        Returns:
            Dict with status, summary, and row-level errors.
        """
        return self._c._request("GET", f"/provider-imports/{import_id}", v2=True)


class OritaClient:
    """
    Orita API client — provider resolution and booking infrastructure for AI applications.

    Primary workflow (unknown-provider resolution):
        client = OritaClient(api_key="orita_live_...")
        resolution = client.resolutions.create(service_id=..., date_range=..., constraints=...)
        hold       = client.resolutions.hold_option(resolution['resolutionId'], option_id)
        booking    = client.resolutions.confirm(resolution_id, option_id, customer={...})

    Secondary workflow (known-provider direct scheduling — v1):
        slots   = client.slots(event_type_id=..., date=...)
        booking = client.book(slot_id=slots[0]['id'], customer={...})
    """

    V2_BASE = "https://orita.online/api/v2"
    V1_BASE = "https://orita.online/api/v1"

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        if not api_key.startswith("orita_"):
            raise OritaAuthError("API key must start with 'orita_'")
        self.api_key  = api_key
        self._v2_base = base_url or self.V2_BASE
        self._v1_base = self.V1_BASE
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        })

        # Namespaces
        self.resolutions     = ResolutionsNamespace(self)
        self.providers       = ProvidersNamespace(self)
        self.provider_imports = ProviderImportsNamespace(self)

    def _request(
        self,
        method: str,
        path: str,
        v2: bool = True,
        extra_headers: Optional[dict] = None,
        **kwargs,
    ):
        base = self._v2_base if v2 else self._v1_base
        url  = f"{base}{path}"
        resp = self._session.request(method, url, headers=extra_headers or {}, **kwargs)
        if resp.status_code == 401:
            raise OritaAuthError("Invalid or missing API key")
        if resp.status_code == 404:
            try:
                raise OritaNotFoundError(resp.json().get("error", {}).get("message", "Not found"))
            except Exception:
                raise OritaNotFoundError("Not found")
        if resp.status_code == 409:
            try:
                raise OritaSlotUnavailableError(resp.json().get("error", {}).get("message", "Conflict"))
            except Exception:
                raise OritaSlotUnavailableError("Slot unavailable or conflict")
        if not resp.ok:
            try:
                msg = resp.json().get("error", {}).get("message", "API error")
            except Exception:
                msg = f"HTTP {resp.status_code}"
            raise OritaError(f"{resp.status_code}: {msg}")
        return resp.json()

    # ── Direct scheduling — v1 (secondary workflow) ──────────────────────────

    def slots(self, event_type_id: str, date: str, provider_id: Optional[str] = None) -> list:
        """
        [Direct scheduling — v1] Get available slots for an event type on a date.
        Use when you already know the provider. For unknown-provider matching,
        use client.resolutions.create() instead.
        """
        params: dict = {"eventTypeId": event_type_id, "date": date}
        if provider_id:
            params["providerId"] = provider_id
        return self._request("GET", "/slots", params=params, v2=False)["slots"]

    def book(
        self,
        slot_id: str,
        customer: dict,
        event_type_id: Optional[str] = None,
        provider_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """
        [Direct scheduling — v1] Book a specific slot when the provider is already known.
        For unknown-provider booking, use client.resolutions.confirm() instead.

        Args:
            slot_id:       Slot ID from slots().
            customer:      Dict with name, email, and optionally timezone.
            event_type_id: Event type ID (required if not inferred from slot).
            provider_id:   Provider ID (required if not inferred from slot).
            notes:         Optional notes from the attendee.
        """
        payload: dict = {"slotId": slot_id, "customer": customer}
        if event_type_id:
            payload["eventTypeId"] = event_type_id
        if provider_id:
            payload["providerId"] = provider_id
        if notes:
            payload["notes"] = notes
        return self._request("POST", "/bookings", json=payload, v2=False)["data"]

    def get_booking(self, booking_id: str) -> dict:
        """[Direct scheduling — v1] Get a booking by ID."""
        return self._request("GET", f"/bookings/{booking_id}", v2=False)

    def cancel(self, booking_id: str, reason: Optional[str] = None) -> dict:
        """[Direct scheduling — v1] Cancel a booking."""
        payload = {"reason": reason} if reason else {}
        return self._request("POST", f"/bookings/{booking_id}/cancel", json=payload, v2=False)

    def reschedule(self, booking_id: str, date: str, time: str) -> dict:
        """[Direct scheduling — v1] Reschedule a booking to a new date and time."""
        return self._request(
            "POST",
            f"/bookings/{booking_id}/reschedule",
            json={"date": date, "time": time},
            v2=False,
        )
