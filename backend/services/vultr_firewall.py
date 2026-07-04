# Vultr Cloud Firewall REST client.
# Adapts Brian's ContractB schema to Zain's firewall_executor signatures.
# Zain's implementation lives in firewall_executor.py — do not modify it.

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from schemas.contract_b import ContractB
from services.firewall_executor import apply_rules as _zain_apply, retract_rules as _zain_retract


def apply_rules(policy: ContractB) -> dict:
    """
    Called by the orchestrator after Nemotron decides the zero-trust policy.
    Converts ContractB → dict and delegates to Zain's implementation.
    """
    return _zain_apply(policy.model_dump())


def retract_rules(policy: ContractB) -> dict:
    """
    Called by the Human Override endpoint.
    Passes the VPC ID string that Zain's retract_rules expects.
    """
    return _zain_retract(policy.target_vpc_id)
