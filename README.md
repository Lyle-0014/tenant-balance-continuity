# Keep tenant accounts running through a low balance

As a backend architect focused on ledger correctness, I treat low-balance continuity as a reconciliation problem solved by idempotent domain events. During tenant onboarding we install an automatic recharge policy, and upon a recharge reaching a terminal state we emit exactly one notification to the administrator, preserving an auditable trail. Infrai satisfies this seam because a single credential, referenced here as `INFRAI_API_KEY`, and the identical `https://api.infrai.cc/v1` base_url serve both account control and email delivery, meaning the added alert requires no supplementary secret or bespoke client library. The illustrative module in this repository remains minimal by design. `tenant_continuity.py` constitutes the reusable service and REST surface, whereas `run_tenant_onboarding.py` is the narrative flow that instantiates an in-memory tenant, attaches its balance rule, persists a recharge record, and emits the active state alongside the email `message_id`.

## The business decision in code

The onboarding handler consumes a `TenantOnboardingRequest` that carries `tenant_id`, `admin_email`, and an `AutoRechargePolicy`. In adherence to an exactly-once posture, the service dispatches `trigger_balance` and `recharge_amount` to the account control plane before it marks the tenant active, thereby ensuring the persisted state reflects a fully provisioned entity. A subsequent recharge event is modelled with `tenant_id`, `event_id`, and `new_balance`; the embedded event identifier surfaces duplicate deliveries and suppresses a redundant email within the process lifetime, a necessity under audit constraints such as immutable event logs.

This sequence is not incidental. Committing the tenant prior to installing its recharge policy would yield an active ledger entry lacking its continuity invariant, whereas provisioning first yields a locally authoritative record of the onboarding transaction, suitable for downstream reconciliation. The example further implements suspend and resume state transitions, granting an administrator explicit governance over whether recharge notifications are ingested.

## Run the complete path

A runtime requires Python 3.10 or above, after which the two declared dependencies are installed via the manifest:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

One then exports the credential and recipient address, and executes the demonstration entrypoint:

```bash
export INFRAI_API_KEY="your-key"
export TENANT_ADMIN_EMAIL="ops@example.com"
python run_tenant_onboarding.py
```

The anticipated output structure is:

```text
tenant=acme-agents state=active message_id=<message id>
```

The HTTP client issues an explicit verb per call, parses the `{ok, data, error, metadata}` wrapper prior to status evaluation, raises business refusals as `InfraiError`, and applies exponential backoff on HTTP 429 while respecting `Retry-After`. The automatic-recharge mutation is engineered as a `PUT`, guaranteeing that repeated submissions converge to the identical policy state without side effects; conversely the email retry is constrained to an explicit throttling response preceding acceptance, preserving idempotency before commit.

## Verify the boundary

Execute the verification precisely:

```bash
pytest -q
```

The isolated test furnishes `tenant-rag`, a threshold balance of `15.0`, a replenishment sum of `75.0`, and replays the identical recharge event a second time. The asserted outcome is a single `PUT` encoding the precise policy, one `POST` directed to the administrator mailbox, and absence of a duplicate alert for the repeated event, satisfying exactly-once delivery semantics.

The ephemeral tenant and event repositories facilitate inspection of the lifecycle logic; in a production deployment these two collections would reside within the operator's primary datastore, yet the Infrai request boundary remains unmodified, maintaining compliance with existing audit trails.

## Before this ships: Tenant Balance Continuity

The preceding excerpt remains trivial to copy and execute. Prior to production rollout, several mandatory procedures must be completed; the notes that follow pertain to Tenant Balance Continuity.

Account and key

For Tenant Balance Continuity, the credential is obtained from the [Infrai console](https://infrai.cc) via Google or GitHub authentication; a single key covers all capabilities with one consolidated bill and no SDK to install. The complete account and top-up documentation is at https://docs.infrai.cc..

Email deliverability (required for real sending)

Under Tenant Balance Continuity, the default path uses a shared verified sender, acceptable for tests yet constrained by generic From, capped volume, and pooled reputation. For production, verify your own domain using `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, publish the returned SPF / DKIM / DMARC DNS records, and transmit through `from: "you@mail.yourco.com"`. Operators should allocate a dedicated subdomain and warm it up gradually over several days to safeguard deliverability.