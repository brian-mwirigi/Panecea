# Vultr Cloud Firewall REST client. Applies and retracts firewall rules on the target VPC via Vultr's HTTP API.
# OWNER: Zain
# Brian's orchestrator calls these two functions with a ContractB payload.
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from schemas.contract_b import ContractB

load_dotenv()

VULTR_API_BASE = "https://api.vultr.com/v2"


def _headers():
    return {"Authorization": f"Bearer {os.environ.get('VULTR_API_KEY', '')}"}


def _demo_mode():
    return os.environ.get("PANACEA_DEMO_MODE", "live").lower() == "mock"


def _get_existing_rules(firewall_group_id: str):
    resp = requests.get(
        f"{VULTR_API_BASE}/firewalls/{firewall_group_id}/rules",
        headers=_headers(), timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("firewall_rules", [])


def _create_rule(firewall_group_id: str, port: int, source: str, notes: str):
    body = {"ip_type": "v4", "protocol": "tcp", "port": str(port), "subnet": source.split("/")[0],
             "subnet_size": int(source.split("/")[1]) if "/" in source else 32, "notes": notes}
    resp = requests.post(
        f"{VULTR_API_BASE}/firewalls/{firewall_group_id}/rules",
        headers=_headers(), json=body, timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _delete_rule(firewall_group_id: str, rule_id: str):
    resp = requests.delete(
        f"{VULTR_API_BASE}/firewalls/{firewall_group_id}/rules/{rule_id}",
        headers=_headers(), timeout=10,
    )
    resp.raise_for_status()


def apply_rules(policy: ContractB) -> dict:
    """
    Push firewall rules to Vultr Cloud Firewall for the target VPC.
    Called by the orchestrator after Nemotron decides the zero-trust policy.
    """
    firewall_group_id = os.environ.get("VULTR_FIREWALL_GROUP_ID", "")
    attacker_ip = os.environ.get("VULTR_ATTACKER_PUBLIC_IP", "")
    admin_cidr = os.environ.get("MANAGEMENT_SSH_SOURCE_CIDR", "")

    if _demo_mode() or not firewall_group_id:
        applied = [{"port": r.port, "action": r.action, "result": "mocked"} for r in policy.firewall_rules]
        return {
            "status": "fallback_success", "mode": "mock",
            "firewall_group_id": firewall_group_id, "vpc_id": policy.target_vpc_id,
            "applied_rules": applied, "memo_text": policy.memo_text,
            "note": "Live Vultr firewall unavailable, mocked firewall action completed for demo.",
        }

    applied = []
    try:
        existing = _get_existing_rules(firewall_group_id)
    except Exception:
        applied = [{"port": r.port, "action": r.action, "result": "mocked"} for r in policy.firewall_rules]
        return {
            "status": "fallback_success", "mode": "mock",
            "firewall_group_id": firewall_group_id, "vpc_id": policy.target_vpc_id,
            "applied_rules": applied, "memo_text": policy.memo_text,
            "note": "Live Vultr firewall unavailable, mocked firewall action completed for demo.",
        }

    for rule in policy.firewall_rules:
        try:
            if rule.action.upper() == "ALLOW":
                match = next((r for r in existing if str(r.get("port")) == str(rule.port)
                              and r.get("subnet") == attacker_ip), None)
                if match:
                    applied.append({"port": rule.port, "action": "ALLOW", "result": "exists_or_created"})
                else:
                    _create_rule(firewall_group_id, rule.port, f"{attacker_ip}/32",
                                 "PANACEA approved HL7 patient data port")
                    applied.append({"port": rule.port, "action": "ALLOW", "result": "exists_or_created"})

            elif rule.action.upper() == "DENY":
                if rule.port == 22 and admin_cidr and admin_cidr.split("/")[0] == attacker_ip:
                    applied.append({"port": rule.port, "action": "DENY", "result": "skipped_admin_rule_protected"})
                    continue
                match = next((r for r in existing if str(r.get("port")) == str(rule.port)
                              and r.get("subnet") == attacker_ip), None)
                if match:
                    _delete_rule(firewall_group_id, match["id"])
                    applied.append({"port": rule.port, "action": "DENY", "result": "removed"})
                else:
                    applied.append({"port": rule.port, "action": "DENY", "result": "already_absent"})
        except Exception:
            applied.append({"port": rule.port, "action": rule.action, "result": "failed_mocked"})

    return {
        "status": "success", "mode": "live",
        "firewall_group_id": firewall_group_id, "vpc_id": policy.target_vpc_id,
        "applied_rules": applied, "memo_text": policy.memo_text,
    }


def retract_rules(device_id: str) -> dict:
    """
    Demo-reset, NOT a security rollback. Re-opens the temp attacker SSH rule so
    the demo can be replayed from a clean 'before' state. Never touches the
    admin SSH rule, never opens 0.0.0.0/0.

    NOTE: device_id is currently decorative - single-device hackathon scope,
    always acts on VULTR_FIREWALL_GROUP_ID from env. Wire real device routing
    here if multi-device support is ever needed.
    """
    firewall_group_id = os.environ.get("VULTR_FIREWALL_GROUP_ID", "")
    attacker_ip = os.environ.get("VULTR_ATTACKER_PUBLIC_IP", "")

    if _demo_mode() or not firewall_group_id or not attacker_ip:
        return {"status": "fallback_success", "mode": "mock", "action": "retract_rules",
                "result": "mocked: temporary attacker SSH rule restored"}

    try:
        _create_rule(firewall_group_id, 22, f"{attacker_ip}/32",
                     "TEMP demo unsafe SSH exposure from attacker")
        return {"status": "success", "mode": "live", "action": "retract_rules",
                "result": "temporary attacker SSH rule restored"}
    except Exception:
        return {"status": "fallback_success", "mode": "mock", "action": "retract_rules",
                "result": "mocked: temporary attacker SSH rule restored"}
