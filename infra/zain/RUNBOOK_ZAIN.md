# RUNBOOK - Zain Module (Threat Execution & Security Infra)

Panacea v2 - RAISE Summit 2026 - Vultr track

## 1. Purpose

This module is the "muscle" of Panacea's zero-trust immune system. It does two
things:

1. **`backend/services/vultr_firewall.py`** - takes a `ContractB` lockdown
   decision produced upstream in the pipeline and enforces it by programming a
   **Vultr Cloud Firewall** group: allowing approved medical ports and denying
   lateral-pivot ports (e.g. SSH/22). It exposes importable functions so
   Brian's FastAPI orchestrator can call it directly.
2. **`infra/zain/attack_simulator.py`** - a *controlled* probe that proves the
   "before" (SSH reachable) vs "after" (SSH blocked) state for the demo. It
   only touches one fixed target on two fixed ports.

Everything is written for a live demo: it never crashes, and it degrades to a
mocked `fallback_success` response if Vultr is unreachable.

## 2. Required environment variables

Copy `.env.example` to `.env` and fill it in. Keys:

| Variable | Meaning |
|---|---|
| `VULTR_API_KEY` | API key for the account that **owns the firewall group**. |
| `VULTR_FIREWALL_GROUP_ID` | Vultr Cloud Firewall group to program. |
| `VULTR_TARGET_INSTANCE_ID` | Philips IntelliVue simulator instance id. |
| `VULTR_TARGET_PUBLIC_IP` | Target public IP (probed by the simulator). |
| `VULTR_TARGET_PRIVATE_IP` | Target private/VPC IP. |
| `VULTR_TARGET_REGION` | Target region. |
| `VULTR_ATTACKER_INSTANCE_ID` | Attacker VM instance id (Zain's account). |
| `VULTR_ATTACKER_PUBLIC_IP` | Attacker public IP - the source we ALLOW/DENY. |
| `VULTR_ATTACKER_PRIVATE_IP` | Attacker private/VPC IP. |
| `MANAGEMENT_SSH_SOURCE_CIDR` | Admin SSH source CIDR - **never touched**. |
| `PANACEA_DEMO_MODE` | `live` (real Vultr calls) or `mock` (skip API). |

## 3. Cross-account architecture note (READ THIS)

The attacker VM lives on Zain's Vultr account. The target VM and Vultr Cloud
Firewall group live on Mohamed's Vultr account.

Because of this, `backend/services/vultr_firewall.py` is fully account-agnostic:
it reads `VULTR_API_KEY` and `VULTR_FIREWALL_GROUP_ID` from the environment /
`.env` only - nothing is hardcoded. Whoever owns the Vultr firewall group runs
live tests with their own `VULTR_API_KEY` in their own `.env`. API keys are
never shared between teammates.

## 4. How to run

### Install deps

```bash
pip install requests python-dotenv
```

The backend also lists these dependencies in `backend/requirements.txt`.

### Attack simulator

```bash
python infra/zain/attack_simulator.py
```

Prints a JSON anomaly event including `port_22_reachable` and
`port_3200_reachable`. Run it **before** applying the contract (SSH should be
reachable) and **after** (SSH should be blocked).

### Firewall service - apply mode

`apply_rules()` lives in `backend/services/vultr_firewall.py` and takes a
`ContractB` Pydantic object, not a raw `dict`.

```powershell
$env:PANACEA_DEMO_MODE="mock"; python -c "
import sys; sys.path.insert(0, 'backend')
from schemas.contract_b import ContractB
from services.vultr_firewall import apply_rules, retract_rules
import json
data = json.load(open('infra/zain/contract_b_lockdown.json'))
policy = ContractB(**data)
print(apply_rules(policy))
"
```

### Firewall service - rollback / demo reset mode

```powershell
$env:PANACEA_DEMO_MODE="mock"; python -c "
import sys; sys.path.insert(0, 'backend')
from services.vultr_firewall import retract_rules
print(retract_rules('philips-intellivue'))
"
```

Calls `retract_rules(device_id: str)` and prints the resulting JSON. This is a
**demo reset**, not a security rollback: it re-adds the temporary attacker SSH
rule so the demo can be replayed from a clean "before" state.

For a live reset call, set `VULTR_FIREWALL_GROUP_ID` and
`VULTR_ATTACKER_PUBLIC_IP` first; the mock example above intentionally
short-circuits without live Vultr credentials.

Known limitation: `device_id` is currently decorative in single-device
hackathon scope. `retract_rules()` always resets the one
`VULTR_FIREWALL_GROUP_ID` from env. Wire real device routing here if
multi-device support is ever needed.

## 5. Expected before / after firewall state

| State | Port 3200 (HL7) | Port 22 (SSH) from attacker | Admin SSH (`MANAGEMENT_SSH_SOURCE_CIDR`) |
|---|---|---|---|
| **Before** (`retract_rules()` applied) | (unchanged) | ALLOW (temp, unsafe) | ALLOW (always) |
| **After** (`apply_rules()` applied) | ALLOW from attacker /32 | removed (DENY) | ALLOW (untouched) |

The attack simulator should report `port_22_reachable: true` before and
`false` after; `port_3200_reachable` stays `true`.

## 6. Safety constraints (enforced in code)

- **No real exploits.** The simulator does a single TCP connect per port - no
  payloads, no brute force.
- **No public scanning.** Only `VULTR_TARGET_PUBLIC_IP` and only ports 22 & 3200.
- **Never opens SSH to `0.0.0.0/0`.** The service only creates attacker-scoped
  `/32` rules from `VULTR_ATTACKER_PUBLIC_IP`.
- **Never deletes the admin SSH rule.** A DENY for port 22 is skipped when the
  attacker IP matches `MANAGEMENT_SSH_SOURCE_CIDR`.
- **ALLOW rules deduplicate before creating.** Existing Vultr rules are checked
  for the same port and attacker source before a new rule is posted.
- **Attacker-scoped changes only.** ALLOW/DENY operate on the attacker's own
  `/32`, not arbitrary sources.

## 7. Fallback behavior (Vultr unreachable)

If `PANACEA_DEMO_MODE=mock`, if `VULTR_FIREWALL_GROUP_ID` is missing, or if
Vultr API access fails while listing rules, `apply_rules()` returns a
`fallback_success` mock response instead of raising. Per-rule live failures are
reported as `failed_mocked` in `applied_rules`.

`retract_rules()` also returns `fallback_success` in mock mode, when required
env vars are missing, or when the live reset call fails. The orchestrator always
receives a dict with a `status` field.

## 8. Integration note for Brian (orchestrator)

> `apply_rules(policy: ContractB) -> dict` and
> `retract_rules(device_id: str) -> dict` live in
> `backend/services/vultr_firewall.py`, already matching your schema. Both are
> safe to call repeatedly and never raise - always return a dict with a status
> field: `success | fallback_success`. Set `PANACEA_DEMO_MODE=mock` in env to
> test without live Vultr credentials.

## 9. Display note for Oleh (UI)

> Display: `status`, `mode`, `firewall_group_id`, `vpc_id`, `memo_text`,
> `applied_rules`.
> If `status` is `fallback_success`, show:
> "Live Vultr firewall unavailable, mocked firewall action completed for demo."
