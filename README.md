# orita-sdk (Python)

[![PyPI version](https://img.shields.io/pypi/v/orita-sdk.svg)](https://pypi.org/project/orita-sdk/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Provider resolution and booking infrastructure for AI applications — Python SDK**

[Orita](https://orita.online) searches your provider network, applies license, insurance, modality, and availability constraints, then confirms the booking safely through one API.

→ **API v2 docs:** [orita.online/developers](https://orita.online/developers)  
→ **API reference:** [orita.online/developers/reference](https://orita.online/developers/reference)  
→ **Node.js SDK:** [npmjs.com/package/orita-sdk](https://www.npmjs.com/package/orita-sdk)

---

## Installation

```bash
pip install orita-sdk
```

> **Requirements:** Python 3.8+. Only dependency: `requests`.

---

## Primary workflow — Provider resolution

Use when you know **what** the customer needs but not **who** should handle it.

```python
from orita import OritaClient
import uuid

client = OritaClient(api_key="orita_live_...")

# 1. Resolve — search eligible providers with verified availability
resolution = client.resolutions.create(
    service_id="svc_therapy_initial",
    date_range={"from": "2026-08-05", "to": "2026-08-12"},
    constraints={
        "languageCodes":      {"anyOf": ["es"]},
        "modalityCodes":      {"anyOf": ["virtual"]},
        "licenseRegionCodes": {"anyOf": ["US-NJ"]},
        "insurancePlanCodes": {"anyOf": ["aetna"]},
        "acceptsNewClients":  True,
    },
    preferences={
        "dayParts":         ["afternoon"],
        "earliestAvailable": True,
    },
)

# resolution["options"][0] = top-ranked, explained provider-time option
top = resolution["options"][0]
print(top["reason"])           # "Earliest available; speaks Spanish; accepts virtual visits."
print(top["score"])            # 94

# 2. Inspect candidates (optional — why each provider was included or excluded)
candidates = client.resolutions.list_candidates(resolution["resolutionId"])
for c in candidates["candidates"]:
    print(c["displayName"], c["eligibilityStatus"])

# 3. Hold the chosen option (prevents concurrent booking)
hold = client.resolutions.hold_option(
    resolution["resolutionId"],
    top["optionId"],
    ttl_seconds=120,
)
print(hold["expiresAt"])  # hold expires at this time

# 4. Present provider, service, time, and cancellation policy to customer
# Do not confirm before the customer has approved.

# 5. Confirm — creates the booking atomically
booking = client.resolutions.confirm(
    resolution_id=resolution["resolutionId"],
    option_id=top["optionId"],
    hold_id=hold["holdId"],
    customer={"name": "James Park", "email": "james@example.com"},
    idempotency_key=f"session-{uuid.uuid4()}",
)
print(booking["id"])      # booking UUID
print(booking["status"])  # "confirmed"
```

---

## Authentication

```python
client = OritaClient(api_key="orita_live_...")
```

All keys begin with `orita_`. Test keys (`orita_test_...`) have identical behavior but do not send real email notifications or trigger live webhooks.

---

## Provider resolution

### `client.resolutions.create()`

```python
resolution = client.resolutions.create(
    service_id="svc_therapy",
    date_range={"from": "2026-08-05", "to": "2026-08-12"},
    constraints={
        # Hard constraints — provider excluded if any fail
        "languageCodes":      {"anyOf": ["es", "en"]},
        "modalityCodes":      {"anyOf": ["virtual"]},
        "specialtyCodes":     {"anyOf": ["anxiety", "cbt"]},
        "licenseRegionCodes": {"anyOf": ["US-NJ"]},
        "insurancePlanCodes": {"anyOf": ["aetna"]},
        "acceptsNewClients":  True,
    },
    preferences={
        # Soft preferences — affect ranking only
        "dayParts":             ["afternoon"],
        "earliestAvailable":    True,
        "continuityProviderId": "pro_...",  # prefer existing provider
    },
    limit=5,
    idempotency_key="session-xyz-resolution-1",
)
```

Returns a resolution dict with `resolutionId`, `status`, `options`, `exclusionSummary`, `warnings`.

### `client.resolutions.get(resolution_id)`

Retrieve a stored resolution by ID.

### `client.resolutions.list_candidates(resolution_id, status=None, limit=50)`

Per-provider eligibility breakdown. `status` can be `"matched"`, `"excluded"`, or `"unknown"`.

```python
candidates = client.resolutions.list_candidates(
    resolution["resolutionId"],
    status="excluded",  # see why providers were excluded
)
for c in candidates["candidates"]:
    for excl in c["exclusions"]:
        print(f"{c['displayName']}: excluded — {excl['code']} ({excl['field']})")
```

### `client.resolutions.hold_option(resolution_id, option_id, ttl_seconds=120)`

Hold a slot. Returns `holdId`, `status`, `expiresAt`.

### `client.resolutions.release_hold(resolution_id, option_id)`

Release a hold before it expires. Returns `status='released'`.

### `client.resolutions.confirm(resolution_id, option_id, customer, hold_id=None, metadata=None, idempotency_key=None)`

Confirm an option and create the booking.

```python
booking = client.resolutions.confirm(
    resolution_id=resolution["resolutionId"],
    option_id=resolution["options"][0]["optionId"],
    hold_id=hold["holdId"],
    customer={"name": "James Park", "email": "james@example.com"},
    idempotency_key="session-xyz-confirm-1",
)
```

---

## Provider management

```python
# Create a provider
provider = client.providers.create(
    displayName="Dr. Ana García",
    externalId="your-db-id-2841",
    timezone="America/New_York",
    languageCodes=["es", "en"],
    modalityCodes=["virtual"],
    licenseRecords=[{
        "licenseTypeCode": "psychologist",
        "regionCode": "US-NJ",
        "status": "active",
        "expiresAt": "2027-06-30",
    }],
    insurancePlanCodes=["aetna", "cigna"],
    acceptsNewClients=True,
)

# Get a provider
p = client.providers.get(provider["id"])

# Update a provider (increments profileVersion)
client.providers.update(provider["id"], acceptsNewClients=False)

# Check readiness before resolution
readiness = client.providers.readiness(provider["id"])
print(readiness["readiness"])        # 'ready' | 'warning' | 'blocked'
print(readiness["readyForResolution"])  # True/False
for issue in readiness["issues"]:
    print(issue["code"], issue["severity"])

# Deactivate / reactivate
client.providers.deactivate(provider["id"])
client.providers.reactivate(provider["id"])
```

---

## Bulk provider import

```python
# Dry run — validate without writing
result = client.provider_imports.create(
    providers=[...],  # up to 500
    dry_run=True,
)
print(result["summary"])  # {received, created, updated, failed}

# Commit
job = client.provider_imports.create(providers=[...], mode="upsert")
print(job["importId"])

# Poll status
status = client.provider_imports.get(job["importId"])
print(status["status"])   # 'completed' | 'processing' | 'failed'
print(status["errors"])   # row-level validation errors
```

---

## Direct scheduling (secondary workflow — v1)

Use when you already know the provider. For unknown-provider matching, use provider resolution above.

```python
# Get available slots
slots = client.slots(event_type_id="evt_abc123", date="2026-08-05")
# [{"id": "slot_...", "label": "3:00 PM", ...}, ...]

# Book directly
booking = client.book(
    slot_id=slots[0]["id"],
    customer={"name": "Ana", "email": "ana@example.com"},
)

# Manage bookings
client.reschedule("booking-uuid", date="2026-08-06", time="10:00")
client.cancel("booking-uuid", reason="Patient requested cancellation")
```

---

## Error handling

```python
from orita import OritaClient, OritaError, OritaAuthError, OritaNotFoundError, OritaSlotUnavailableError

try:
    booking = client.resolutions.confirm(...)
except OritaSlotUnavailableError:
    # 409 — slot taken by concurrent booking; re-resolve
    resolution = client.resolutions.create(...)
except OritaNotFoundError:
    # 404 — resource not found or cross-tenant access
    pass
except OritaAuthError:
    # 401 — invalid or revoked API key
    pass
except OritaError as e:
    # Other API error
    print(str(e))
```

---

## Agent safety rules

- Resolution does not create a booking — call `confirm()` only after customer approval.
- Always display provider, service, start time, timezone, and cancellation policy before confirming.
- Use `idempotency_key` on every `confirm()` call for safe retries.
- Use `hold_option()` before `confirm()` to prevent race conditions.
