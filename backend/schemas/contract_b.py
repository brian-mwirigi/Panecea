# Pydantic model for Contract B: the agent decision schema sent to the Firewall API and rendered as the Incident Memo on the UI.

from pydantic import BaseModel


class FirewallRule(BaseModel):
    port: int
    action: str  # "ALLOW" or "DENY"


class ContractB(BaseModel):
    target_vpc_id: str
    firewall_rules: list[FirewallRule]
    confidence_score: int
    cve_flagged: str
    memo_text: str
