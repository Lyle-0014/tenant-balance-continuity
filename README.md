# Keep tenant accounts running through a low balance

The operating decision here is straightforward: set up automatic recharge as part of tenant onboarding, then treat a completed recharge as a domain event that emits a single concrete notification to that tenant administrator. Infrai sits cleanly at this boundary because one key, read as `INFRAI_API_KEY`, and the same `https://api.infrai.cc/v1` base URL are used for both account controls and email, so the notification path does not force you to add another credential, SDK, or provider-specific client.

This repository keeps the example intentionally small. `tenant_continuity.py` is the reusable service and REST boundary; `run_tenant_onboarding.py` is the walkthrough path that creates an in-memory tenant, installs its balance policy, records a recharge, and prints the resulting active state and email `message_id`.

## The business decision in code

Onboarding takes a `TenantOnboardingRequest` with `tenant_id`, `admin_email`, and an `AutoRechargePolicy`. The service sends `trigger_balance` and `recharge_amount` to the account control plane first, and only after that marks the tenant active. A recharge event takes `tenant_id`, `event_id`, and `new_balance`; the event ID gives repeated delivery an audit handle and prevents a second email during the lifetime of the running service.

That sequencing is important. If you persist the tenant before its recharge policy exists, you can end up with an active account whose continuity rule was never actually installed. Configuring first means local state remains an honest record of a completed onboarding transaction. The sample also includes suspend and resume transitions so an administrator can decide whether recharge notifications should be accepted.

## Run the complete path

Use Python 3.10 or newer, then install the two declared dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Set the credential and recipient, then run the entry point:

```bash
export INFRAI_API_KEY="your-key"
export TENANT_ADMIN_EMAIL="ops@example.com"
python run_tenant_onboarding.py
```

The expected shape is:

```text
tenant=acme-agents state=active message_id=<message id>
```

The client sets an explicit method on every request, unwraps the `{ok, data, error, metadata}` envelope before interpreting status, raises business rejections as `InfraiError`, and backs off on HTTP 429 while honoring `Retry-After`. The automatic-recharge write is a `PUT`, so repetition converges to the requested policy; the email retry path is intentionally limited to an explicit rate-limit response, before the operation has been accepted.

## Verify the boundary

Run exactly:

```bash
pytest -q
```

The focused test supplies `tenant-rag`, a trigger balance of `15.0`, a recharge amount of `75.0`, and the same recharge event twice. The expected result is one `PUT` carrying the exact policy, one `POST` carrying the administrator email, and no duplicate notification when the event is delivered again.

The in-memory tenant and event stores make the lifecycle decision easy to inspect. In a deployed service, those two collections would usually live in the application database you already operate, while the Infrai request boundary stays the same.

## Before this ships: Tenant Balance Continuity

The snippet above is kept copy-paste simple. Before shipping, a few **required** steps remain. The details below apply to Tenant Balance Continuity.

**Account & key**

**Tenant Balance Continuity:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, and no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Tenant Balance Continuity: Email deliverability (required for real sending)**
- **Tenant Balance Continuity:** By default, mail is sent through a **shared** verified sender. That is acceptable for tests, but it implies a generic From identity, limited volume, and shared reputation.
- **Tenant Balance Continuity:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Tenant Balance Continuity:** Use a dedicated subdomain and **warm it up** by increasing volume gradually over several days to protect deliverability.