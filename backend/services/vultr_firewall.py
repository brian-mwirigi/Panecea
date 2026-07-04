"""Live Vultr NAT Gateway enforcement for Contract B policies."""

from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from schemas.contract_b import ContractB
from schemas.control_plane import EnforcementReceipt, RuleChange


class VultrFirewallError(RuntimeError):
    pass


class VultrNATGatewayEnforcer:
    """Applies default-deny policy through Vultr's managed NAT Gateway APIs."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        gateway_id: str | None = None,
        device_ip: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("VULTR_API_KEY", "")
        self.gateway_id = gateway_id or os.getenv("VULTR_NAT_GATEWAY_ID", "")
        self.device_ip = device_ip or os.getenv("VULTR_DEVICE_PRIVATE_IP", "")
        self.base_url = (base_url or os.getenv("VULTR_API_BASE_URL", "https://api.vultr.com/v2")).rstrip("/")
        self.timeout = float(os.getenv("VULTR_NETWORK_TIMEOUT", "20"))
        self._client = client
        if not self.api_key:
            raise VultrFirewallError("VULTR_API_KEY is required for live network enforcement")
        if not self.gateway_id:
            raise VultrFirewallError("VULTR_NAT_GATEWAY_ID is required for live network enforcement")
        if not self.device_ip:
            raise VultrFirewallError("VULTR_DEVICE_PRIVATE_IP is required for live network enforcement")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self._client is not None:
            response = self._client.request(method, url, headers=self.headers, **kwargs)
        else:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, url, headers=self.headers, **kwargs)
        if response.is_error:
            raise VultrFirewallError(
                f"Vultr network API returned HTTP {response.status_code}: {response.text[:500]}"
            )
        return response

    def _root(self, vpc_id: str) -> str:
        return f"{self.base_url}/vpcs/{vpc_id}/nat-gateway/{self.gateway_id}/global"

    def _list(self, url: str, *keys: str) -> list[dict[str, Any]]:
        payload = self._request("GET", url).json()
        if isinstance(payload, list):
            return payload
        for key in (*keys, "data"):
            value = payload.get(key) if isinstance(payload, dict) else None
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for nested in value.values():
                    if isinstance(nested, list):
                        return nested
        return []

    @staticmethod
    def _id(payload: Any) -> str:
        if isinstance(payload, dict):
            if payload.get("id") is not None:
                return str(payload["id"])
            for value in payload.values():
                try:
                    return VultrNATGatewayEnforcer._id(value)
                except VultrFirewallError:
                    continue
        raise VultrFirewallError("Vultr network API response did not contain a resource ID")

    def apply(self, policy: ContractB) -> dict[str, Any]:
        root = self._root(policy.target_vpc_id)
        forwards_url = f"{root}/port-forwarding-rules"
        firewall_url = f"{root}/firewall-rules"
        forwards = self._list(forwards_url, "port_forwarding_rules", "rules")
        firewall_rules = self._list(firewall_url, "firewall_rules", "rules")

        lease_id = f"lease-{uuid.uuid4().hex[:16]}"
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(os.getenv("VULTR_POLICY_LEASE_SECONDS", "900"))
        )
        changes: list[RuleChange] = []

        for rule in policy.firewall_rules:
            matching_forwards = [
                item for item in forwards
                if int(item.get("external_port", -1)) == rule.port
                and item.get("internal_ip") == self.device_ip
            ]
            matching_firewall = [
                item for item in firewall_rules if str(item.get("port", "")) == str(rule.port)
            ]

            if rule.action == "ALLOW":
                resource_ids: list[str] = []
                if matching_forwards:
                    resource_ids.extend(str(item["id"]) for item in matching_forwards if item.get("id"))
                else:
                    response = self._request(
                        "POST",
                        forwards_url,
                        json={
                            "name": f"panacea-{rule.port}",
                            "protocol": "tcp",
                            "external_port": rule.port,
                            "internal_ip": self.device_ip,
                            "internal_port": rule.port,
                            "enabled": True,
                            "description": f"PANACEA {lease_id} expires {expires_at.isoformat()}",
                        },
                    )
                    resource_ids.append(self._id(response.json()))

                if matching_firewall:
                    resource_ids.extend(str(item["id"]) for item in matching_firewall if item.get("id"))
                else:
                    response = self._request(
                        "POST",
                        firewall_url,
                        json={
                            "protocol": "tcp",
                            "port": str(rule.port),
                            "subnet": os.getenv("VULTR_ALLOWED_SOURCE_SUBNET", "0.0.0.0"),
                            "subnet_size": int(os.getenv("VULTR_ALLOWED_SOURCE_SUBNET_SIZE", "0")),
                            "notes": f"PANACEA {lease_id} expires {expires_at.isoformat()}",
                        },
                    )
                    resource_ids.append(self._id(response.json()))
                changes.append(
                    RuleChange(
                        port=rule.port,
                        action="ALLOW",
                        status="active",
                        resource_ids=resource_ids,
                        probe_status=self._probe(rule.port),
                    )
                )
            else:
                removed: list[str] = []
                for item in matching_firewall:
                    item_id = str(item.get("id", ""))
                    if item_id:
                        self._request("DELETE", f"{firewall_url}/{item_id}")
                        removed.append(item_id)
                for item in matching_forwards:
                    item_id = str(item.get("id", ""))
                    if item_id:
                        self._request("DELETE", f"{forwards_url}/{item_id}")
                        removed.append(item_id)
                changes.append(
                    RuleChange(
                        port=rule.port,
                        action="DENY",
                        status="removed",
                        resource_ids=removed,
                        probe_status=self._probe(rule.port),
                    )
                )

        receipt = EnforcementReceipt(
            enforcement_plane="vultr_nat_gateway",
            vpc_id=policy.target_vpc_id,
            gateway_id=self.gateway_id,
            device_ip=self.device_ip,
            changes=changes,
        )
        return {
            "status": "applied",
            "vpc_id": policy.target_vpc_id,
            "lease_id": lease_id,
            "expires_at": expires_at.isoformat(),
            "receipt": receipt.model_dump(mode="json"),
        }

    def _probe(self, port: int) -> str:
        """Record live reachability from this control-plane location when configured."""
        host = os.getenv("VULTR_NETWORK_PROBE_HOST", "")
        if not host:
            return "unavailable"
        try:
            with socket.create_connection(
                (host, port), timeout=float(os.getenv("VULTR_NETWORK_PROBE_TIMEOUT", "2"))
            ):
                return "reachable"
        except OSError:
            return "blocked"

    def retract(self, policy: ContractB) -> dict[str, Any]:
        deny_policy = policy.model_copy(
            update={
                "firewall_rules": [rule.model_copy(update={"action": "DENY"}) for rule in policy.firewall_rules]
            }
        )
        result = self.apply(deny_policy)
        result["status"] = "retracted"
        return result


def apply_rules(policy: ContractB) -> dict[str, Any]:
    return VultrNATGatewayEnforcer().apply(policy)


def retract_rules(policy: ContractB) -> dict[str, Any]:
    return VultrNATGatewayEnforcer().retract(policy)
