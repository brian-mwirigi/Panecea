# LangChain tool wrapper around vultr_firewall.py. Called by the orchestrator to apply or retract firewall rules.

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from schemas.contract_b import ContractB, FirewallRule
from services.vultr_firewall import apply_rules, retract_rules

# In-memory store of active policies — keyed by device_model
# Zain's firewall scripts read ContractB; this bridges the orchestrator to that handoff
_active_policies: dict[str, ContractB] = {}


def apply_firewall_rule(
    target_vpc_id: str,
    firewall_rules: list[dict],
    confidence_score: int,
    cve_flagged: str,
    memo_text: str,
) -> str:
    """
    Tool executor for Nemotron's apply_firewall_rule tool call.
    Validates the payload, stores the policy, and calls the Vultr firewall client.
    Returns a plain string result Nemotron can reason about.
    """
    try:
        policy = ContractB(
            target_vpc_id=target_vpc_id,
            firewall_rules=[FirewallRule(**r) for r in firewall_rules],
            confidence_score=confidence_score,
            cve_flagged=cve_flagged,
            memo_text=memo_text,
        )
    except Exception as e:
        return f"ERROR: Invalid firewall payload — {e}"

    result = apply_rules(policy)

    # Store by VPC ID so DELETE /api/v1/policy/{device_id} can find it
    _active_policies[target_vpc_id] = policy

    return json.dumps({
        "status": result.get("status", "applied"),
        "vpc_id": target_vpc_id,
        "rules_enforced": len(firewall_rules),
        "confidence_score": confidence_score,
        "cve_flagged": cve_flagged,
    })


def retract_firewall_rule(device_id: str) -> str:
    """
    Human Override — called by DELETE /api/v1/policy/{device_id}.
    Retracts the active firewall policy for a device and removes it from the store.
    """
    policy = _active_policies.get(device_id)
    if not policy:
        return json.dumps({"status": "not_found", "device_id": device_id})

    result = retract_rules(policy)
    del _active_policies[device_id]

    return json.dumps({
        "status": result.get("status", "retracted"),
        "device_id": device_id,
        "vpc_id": policy.target_vpc_id,
        "rules_removed": len(policy.firewall_rules),
    })


def get_active_policy(device_id: str) -> ContractB | None:
    """Returns the active ContractB policy for a device, or None if not found."""
    return _active_policies.get(device_id)


