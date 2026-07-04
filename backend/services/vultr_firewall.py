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


def retract_rules(policy: ContractB) -> dict:
    """
    Remove firewall rules from Vultr Cloud Firewall for the target VPC.
    Called by the Human Override endpoint.

    Expected return:
        {"status": "retracted", "vpc_id": policy.target_vpc_id}
    """
    # TODO: Zain implements this using the Vultr Firewall REST API
    print(f"[MOCK FIREWALL] Retracted rules on {policy.target_vpc_id}")
    return {"status": "mock_retracted", "vpc_id": policy.target_vpc_id}
