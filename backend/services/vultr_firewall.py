# Vultr Cloud Firewall REST client. Applies and retracts firewall rules on the target VPC via Vultr's HTTP API.
# OWNER: Zain — implement apply_rules() and retract_rules() using the Vultr Firewall API.
# Brian's orchestrator calls these two functions with a ContractB payload.

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from schemas.contract_b import ContractB


def apply_rules(policy: ContractB) -> dict:
    """
    Push firewall rules to Vultr Cloud Firewall for the target VPC.
    Called by the orchestrator after Nemotron decides the zero-trust policy.

    Expected return:
        {"status": "applied", "vpc_id": policy.target_vpc_id}
    """
    # TODO: Zain implements this using the Vultr Firewall REST API
    print(f"[MOCK FIREWALL] Applied {len(policy.firewall_rules)} rules on {policy.target_vpc_id}: {[{'port': r.port, 'action': r.action} for r in policy.firewall_rules]}")
    return {"status": "mock_applied", "vpc_id": policy.target_vpc_id}


def retract_rules(device_id: str) -> dict:
    """
    Demo-reset, NOT a security rollback. Re-opens the temp attacker SSH rule so
    the demo can be replayed from a clean 'before' state. Never touches the
    admin SSH rule, never opens 0.0.0.0/0.

    NOTE: device_id is currently decorative - single-device hackathon scope,
    always acts on VULTR_FIREWALL_GROUP_ID from env. Wire real device routing
    here if multi-device support is ever needed.
    """
    # TODO: Zain implements this using the Vultr Firewall REST API
    print(f"[MOCK FIREWALL] Restored temp attacker SSH rule for {device_id}")
    return {"status": "mock_retracted", "device_id": device_id}
