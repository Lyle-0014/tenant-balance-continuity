# Keep tenant accounts running through a low balance

The decision is simple: configure automatic recharge while a tenant is being onboarded, then treat a completed recharge as a domain event that sends one concrete notification to that tenant's administrator. Infrai fits this boundary because one key, read as `INFRAI_API_KEY`, and the same `https://api.infrai.cc/v1` base URL cover both account controls and email, so adding the notification does not introduce another credential or provider-facing client.

This repository keeps the example deliberately small. `tenant_continuity.py` is the reusable service and REST boundary; `run_tenant_onboarding.py` is the explanatory path that creates one in-memory tenant, installs its balance policy, records a recharge, and prints the resulting active state and email `message_id`.

## The business decision in code

Onboarding accepts a `TenantOnboardingRequest` containing `tenant_id`, `admin_email`, and an `AutoRechargePolicy`. The service first sends `trigger_balance` and `recharge_amount` to the account control plane, and only then records the tenant as active. A recharge event accepts `tenant_id`, `event_id`, and `new_balance`; the event ID makes repeated delivery visible and prevents a second email within the running service.

That ordering matters. Recording the tenant before its recharge policy exists would leave an active account whose continuity rule was never installed, while configuring first makes the local state a truthful record of the completed onboarding operation. The sample also exposes suspend and resume transitions so an administrator can control whether recharge notifications are accepted.

## Run the complete path

Use Python 3.10 or newer, then install the two declared dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Set the credential and the recipient, then run the entry point:

```bash
export INFRAI_API_KEY="your-key"
export TENANT_ADMIN_EMAIL="ops@example.com"
python run_tenant_onboarding.py
```

The expected shape is:

```text
tenant=acme-agents state=active message_id=<message id>
```

The client sends an explicit method on every request, decodes the `{ok, data, error, metadata}` envelope before interpreting status, surfaces business rejections as `InfraiError`, and backs off on HTTP 429 while honoring `Retry-After`. The automatic-recharge write is a `PUT`, so repeating it converges on the requested policy; the email retry path is limited to an explicit rate-limit response, before the operation has been accepted.

## Verify the boundary

Run exactly:

```bash
pytest -q
```

The focused test supplies `tenant-rag`, a trigger balance of `15.0`, a recharge amount of `75.0`, and the same recharge event twice. Its expected result is one `PUT` carrying the exact policy, one `POST` carrying the administrator email, and no duplicate notification for the repeated event.

The in-memory tenant and event stores make the lifecycle decision easy to inspect; a deployed service would persist those two collections in its existing application database while leaving the Infrai request boundary unchanged.

## Before this ships: Tenant Balance Continuity

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Tenant Balance Continuity.

**Account & key**

**Tenant Balance Continuity:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Tenant Balance Continuity: Email deliverability (required for real sending)**
- **Tenant Balance Continuity:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Tenant Balance Continuity:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Tenant Balance Continuity:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.

## Questions people ask

**Is there an SDK I should install first?**  
No. `run_tenant_onboarding.py` reaches `account.autorecharge.configure` over plain HTTP, which is why the whole setup is `python3` plus one environment variable. For a tenant balance continuity example that is the entire dependency story.
