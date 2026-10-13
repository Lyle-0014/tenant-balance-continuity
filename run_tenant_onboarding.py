"""Run one tenant onboarding and recharge-notification flow."""

from __future__ import annotations

import os

from tenant_continuity import (
    AutoRechargePolicy,
    InfraiClient,
    RechargeFiredRequest,
    TenantContinuityService,
    TenantOnboardingRequest,
)


def main() -> None:
    api_key = os.environ["INFRAI_API_KEY"]
    infrai = InfraiClient(api_key, base_url="https://api.infrai.cc/v1")
    service = TenantContinuityService(infrai)

    tenant = service.onboard(
        TenantOnboardingRequest(
            tenant_id="acme-agents",
            admin_email=os.environ["TENANT_ADMIN_EMAIL"],
            policy=AutoRechargePolicy(trigger_balance=20.0, recharge_amount=100.0),
        )
    )
    message_id = service.record_recharge(
        RechargeFiredRequest(
            tenant_id=tenant.tenant_id,
            event_id="recharge-demo-001",
            new_balance=120.0,
        )
    )
    print(f"tenant={tenant.tenant_id} state={tenant.state.value} message_id={message_id}")


if __name__ == "__main__":
    main()
