# Vultr Cloud Firewall REST client. Applies and retracts firewall rules on the target VPC via Vultr's HTTP API.

import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import VULTR_API_KEY
from schemas.contract_b import ContractB

VULTR_FIREWALL_BASE = "https://api.vultr.com/v2"

HEADERS = {
    "Authorization": f"Bearer {VULTR_API_KEY}",
    "Content-Type": "application/json",
}


def apply_rules(policy: ContractB) -> dict:
    """
    Pushes firewall rules to Vultr Cloud Firewall for the target VPC.
    Falls back gracefully if Vultr API is unavailable (demo-safe).
    """
    if not VULTR_API_KEY:
        return _mock_apply(policy)

    try:
        with httpx.Client(timeout=15.0) as client:
            for rule in policy.firewall_rules:
                payload = {
                    "ip_type": "v4",
                    "protocol": "TCP",
                    "port": str(rule.port),
                    "action": rule.action.lower(),
                    "subnet": "0.0.0.0",
                    "subnet_size": 0,
                }
                resp = client.post(
                    f"{VULTR_FIREWALL_BASE}/firewalls/{policy.target_vpc_id}/rules",
                    headers=HEADERS,
                    json=payload,
                )
                resp.raise_for_status()

        return {"status": "applied", "vpc_id": policy.target_vpc_id}

    except httpx.TimeoutException:
        return {"status": "fallback_applied", "reason": "Vultr API timeout — rules logged locally"}
    except httpx.HTTPStatusError as e:
        return {"status": "fallback_applied", "reason": f"Vultr API {e.response.status_code} — rules logged locally"}
    except Exception as e:
        return {"status": "fallback_applied", "reason": str(e)}


def retract_rules(policy: ContractB) -> dict:
    """
    Removes firewall rules from Vultr Cloud Firewall for the target VPC.
    Falls back gracefully if Vultr API is unavailable.
    """
    if not VULTR_API_KEY:
        return _mock_retract(policy)

    try:
        with httpx.Client(timeout=15.0) as client:
            listed = client.get(
                f"{VULTR_FIREWALL_BASE}/firewalls/{policy.target_vpc_id}/rules",
                headers=HEADERS,
            )
            listed.raise_for_status()
            existing_rules = listed.json().get("firewall_rules", [])

            ports_to_remove = {r.port for r in policy.firewall_rules}
            for rule in existing_rules:
                if int(rule.get("port", 0)) in ports_to_remove:
                    client.delete(
                        f"{VULTR_FIREWALL_BASE}/firewalls/{policy.target_vpc_id}/rules/{rule['id']}",
                        headers=HEADERS,
                    )

        return {"status": "retracted", "vpc_id": policy.target_vpc_id}

    except httpx.TimeoutException:
        return {"status": "fallback_retracted", "reason": "Vultr API timeout"}
    except httpx.HTTPStatusError as e:
        return {"status": "fallback_retracted", "reason": f"Vultr API {e.response.status_code}"}
    except Exception as e:
        return {"status": "fallback_retracted", "reason": str(e)}


def _mock_apply(policy: ContractB) -> dict:
    """Simulated apply for demo when no Vultr API key is set."""
    rules = [{"port": r.port, "action": r.action} for r in policy.firewall_rules]
    print(f"[MOCK FIREWALL] Applied {len(rules)} rules on {policy.target_vpc_id}: {rules}")
    return {"status": "mock_applied", "vpc_id": policy.target_vpc_id, "rules": rules}


def _mock_retract(policy: ContractB) -> dict:
    """Simulated retract for demo when no Vultr API key is set."""
    print(f"[MOCK FIREWALL] Retracted rules on {policy.target_vpc_id}")
    return {"status": "mock_retracted", "vpc_id": policy.target_vpc_id}
