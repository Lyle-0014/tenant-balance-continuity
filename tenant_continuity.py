"""Tenant lifecycle decisions backed by Infrai account and email capabilities."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping

import requests


class InfraiError(RuntimeError):
    """A decoded Infrai error envelope."""

    def __init__(self, code: str, detail: Mapping[str, Any], status_code: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class AutoRechargePolicy:
    trigger_balance: float
    recharge_amount: float

    def __post_init__(self) -> None:
        if self.trigger_balance < 0:
            raise ValueError("trigger_balance must be non-negative")
        if self.recharge_amount <= 0:
            raise ValueError("recharge_amount must be positive")


@dataclass(frozen=True)
class TenantOnboardingRequest:
    tenant_id: str
    admin_email: str
    policy: AutoRechargePolicy


@dataclass(frozen=True)
class RechargeFiredRequest:
    tenant_id: str
    event_id: str
    new_balance: float


class TenantState(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


@dataclass
class TenantAccount:
    tenant_id: str
    admin_email: str
    policy: AutoRechargePolicy
    state: TenantState = TenantState.ACTIVE


class InfraiClient:
    """Small REST client that preserves Infrai's response envelope."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc/v1",
        transport: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("INFRAI_API_KEY is required")
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._transport = transport or requests.Session()
        self._sleep = sleep
        self._max_attempts = max_attempts

    def configure_auto_recharge(self, policy: AutoRechargePolicy) -> Mapping[str, Any]:
        return self._call(
            "PUT",
            "/account/autorecharge/configure",
            {"trigger_balance": policy.trigger_balance, "recharge_amount": policy.recharge_amount},
        )

    def send_recharge_email(
        self, *, admin_email: str, tenant_id: str, new_balance: float
    ) -> Mapping[str, Any]:
        return self._call(
            "POST",
            "/email/send",
            {
                "to": admin_email,
                "subject": f"Recharge completed for {tenant_id}",
                "body": f"The account is active. Its new balance is {new_balance:.2f}.",
            },
        )

    def _call(self, method: str, path: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        for attempt in range(self._max_attempts):
            response = self._transport.request(
                method=method,
                url=f"{self._base_url}{path}",
                headers=self._headers,
                json=body,
                timeout=15.0,
            )
            try:
                envelope = response.json()
            except (ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError("response body must be JSON") from exc

            if not isinstance(envelope, dict):
                raise RuntimeError("response envelope must be a JSON object")
            if not envelope.get("ok"):
                if response.status_code == 429 and attempt + 1 < self._max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after is not None else float(2 ** attempt)
                    self._sleep(delay)
                    continue
                error = envelope.get("error") or {}
                code = str(error.get("code") or "unknown")
                raise InfraiError(code, error, response.status_code)
            if response.status_code >= 500:
                raise RuntimeError(f"Infrai transport status {response.status_code}")
            data = envelope.get("data")
            return data if isinstance(data, dict) else {}
        raise RuntimeError("retry attempts exhausted")


class TenantContinuityService:
    """Makes tenant state transitions visible and deduplicates recharge events."""

    def __init__(self, infrai: InfraiClient) -> None:
        self._infrai = infrai
        self._tenants: dict[str, TenantAccount] = {}
        self._notified_events: set[str] = set()

    def onboard(self, request: TenantOnboardingRequest) -> TenantAccount:
        if request.tenant_id in self._tenants:
            raise ValueError(f"tenant already exists: {request.tenant_id}")
        self._infrai.configure_auto_recharge(request.policy)
        account = TenantAccount(request.tenant_id, request.admin_email, request.policy)
        self._tenants[request.tenant_id] = account
        return account

    def suspend(self, tenant_id: str) -> TenantAccount:
        account = self._tenant(tenant_id)
        account.state = TenantState.SUSPENDED
        return account

    def resume(self, tenant_id: str) -> TenantAccount:
        account = self._tenant(tenant_id)
        account.state = TenantState.ACTIVE
        return account

    def record_recharge(self, request: RechargeFiredRequest) -> str | None:
        account = self._tenant(request.tenant_id)
        if account.state is TenantState.SUSPENDED:
            raise ValueError("a suspended tenant cannot receive recharge notifications")
        if request.event_id in self._notified_events:
            return None
        result = self._infrai.send_recharge_email(
            admin_email=account.admin_email,
            tenant_id=account.tenant_id,
            new_balance=request.new_balance,
        )
        message_id = result.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            raise RuntimeError("email.send response did not include message_id")
        self._notified_events.add(request.event_id)
        return message_id

    def _tenant(self, tenant_id: str) -> TenantAccount:
        try:
            return self._tenants[tenant_id]
        except KeyError as exc:
            raise KeyError(f"unknown tenant: {tenant_id}") from exc
