from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from tenant_continuity import (
    AutoRechargePolicy,
    InfraiClient,
    RechargeFiredRequest,
    TenantContinuityService,
    TenantOnboardingRequest,
)


@dataclass
class FakeResponse:
    status_code: int
    payload: Mapping[str, Any]
    headers: Mapping[str, str] = field(default_factory=dict)

    def json(self) -> Mapping[str, Any]:
        return self.payload


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if kwargs["url"].endswith("/account/autorecharge/configure"):
            return FakeResponse(200, {"ok": True, "data": {"enabled": True}})
        return FakeResponse(200, {"ok": True, "data": {"message_id": "msg_123"}})


def test_onboarding_configures_policy_and_one_recharge_sends_one_email() -> None:
    transport = RecordingTransport()
    client = InfraiClient("test-key", transport=transport)
    service = TenantContinuityService(client)

    service.onboard(
        TenantOnboardingRequest(
            tenant_id="tenant-rag",
            admin_email="ops@example.com",
            policy=AutoRechargePolicy(trigger_balance=15.0, recharge_amount=75.0),
        )
    )
    event = RechargeFiredRequest("tenant-rag", "event-42", 90.0)

    assert service.record_recharge(event) == "msg_123"
    assert service.record_recharge(event) is None
    assert [call["method"] for call in transport.calls] == ["PUT", "POST"]
    assert transport.calls[0]["json"] == {
        "trigger_balance": 15.0,
        "recharge_amount": 75.0,
    }
    assert transport.calls[1]["json"] == {
        "to": "ops@example.com",
        "subject": "Recharge completed for tenant-rag",
        "body": "The account is active. Its new balance is 90.00.",
    }
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer test-key"
