# Philips IntelliVue target VM (Mohamed — IIoT Target)

Real Vultr instance simulating the vulnerable Philips IntelliVue patient monitor for the live attack/defense demo.

## Current state — ACTIVE TARGET (Chicago)

| Item | Value |
|---|---|
| Provider | Vultr Cloud Compute |
| Region | Chicago (`ord`) |
| Plan | `vc2-1c-1gb` ($5/mo, billed hourly — negligible cost for the event) |
| OS | Ubuntu 24.04 LTS |
| Instance ID | `efac5ff6-8cb8-4b2c-b522-f320e8573ea3` |
| Public IP | `64.177.118.214` |
| VPC | `panacea-medical-vpc` (`71c87a0e-97fd-4e31-9f65-85d520f428a4`), subnet `10.100.0.0/24`, region `ord` — matches the `target_vpc_id` field referenced in Contract B (e.g. `"vpc-medical-01"`) |
| VPC internal IP | `10.100.0.3` |
| Firewall group | `panacea-medical-lockdown` (`de7a05fc-ecdf-4645-92d2-989b02951598`) — replaces the earlier `panacea-target-fw` group (`b57ae685-a98b-44e2-a867-60270e9647de`), which was reused from the Paris instance. The new group is what's actually attached to the Chicago target instance now (confirmed via `infra/zain/.env`, `VULTR_FIREWALL_GROUP_ID`), put in place for the live "lockdown" firewall test. |
| Port 3200 (HL7) | **Open to everyone** at the Vultr cloud firewall level (`0.0.0.0/0`) — a real Python TCP listener (`hl7_listener.py`) is running as a systemd service, responds with a placeholder HL7-style ACK. Verified working via localhost on the box itself. The box's own OS-level `ufw` firewall (Ubuntu default) previously only allowed port 22 inbound and lacked an explicit allow rule for 3200, which could have blocked external connections to 3200 despite the Vultr cloud firewall being open — this gap also existed on the old Paris VM. **Resolved:** `ufw allow 3200/tcp` has since been applied on the Chicago target VM, so 3200 is now reachable end-to-end (cloud firewall + OS firewall). |
| Port 22 (SSH) | **Current (lockdown) state:** the Vultr cloud firewall allows port 22 only from the admin CIDR `102.159.195.84/32`. The rule that previously let Zain's attacker VM (`64.177.113.13/32`) through port 22 has been removed/denied as part of the live "lockdown" firewall test (`infra/zain/contract_b_lockdown.json` shows `{"port": 22, "action": "DENY"}` for the attacker's rule). This is the intended demo behavior for `panacea-medical-lockdown`: the attacker VM times out on port 22 (no SSH access) while still being able to reach port 3200. |

## Decommissioned — Paris instance

The original target VM in Paris (`3a71efd5-fb92-4334-83e9-3653c0386296`, `45.32.146.113`) has been **destroyed**. Chicago (`ord`) is now the only target VM — do not reference the old Paris IP anywhere (demo scripts, Zain's attacker config, docs).

## Team context (not Mohamed's action items, noted for reference)

- **Zain** (attacker VM / Python firewall execution scripts owner): attacker VM is live at `64.177.113.13` (root SSH access). Following the live lockdown test, this IP is now explicitly denied on port 22 by `panacea-medical-lockdown` — it can still reach port 3200, but no longer has SSH access to the target.
- **Brian** (backend/orchestrator, presumably FastAPI): service reported running at `45.76.26.39`. Not attached to the VPC and no action taken here — flagging in case private networking between backend and target VPC becomes relevant later.

## Files in this directory

- `hl7_listener.py` — the trivial placeholder TCP listener bound to port 3200. Not real HL7 protocol logic — just enough to be a real, alive service so the firewall's "allow 3200" rule has something real behind it. Deployed at `/root/hl7_listener.py` on the Chicago target VM.
- `hl7-listener.service` — systemd unit running the listener, auto-restarts, survives reboots. Installed at `/etc/systemd/system/hl7-listener.service`, enabled via `systemctl enable --now hl7-listener.service`.

## For Zain (attacker VM owner)

Target IP: `64.177.118.214` (Chicago — this is now the real target, NOT the old `45.32.146.113` Paris IP). Following the live lockdown test, port 22 from your attacker VM's IP (`64.177.113.13/32`) is now explicitly denied at the Vultr cloud firewall (`panacea-medical-lockdown`) — a connection timeout on 22 is the correct, intended result of the demo, not a bug. Port 3200 remains reachable from your VM as before; `ufw` on the target box now has an explicit `allow 3200/tcp` rule, so 3200 connectivity should be reliable.

## Re-provisioning notes

- SSH key pair for admin access is `panacea-target-key` (registered on the Vultr account, ID `e766aa16-af8a-4436-9aaf-2892ea5bac9c`), keypair not stored in this repo (local copy at `~/.ssh/panacea_target` on Mohamed's machine).
- Firewall group ID, instance IDs, and VPC ID are tracked outside this repo (Vultr Console) since they're account-specific, not portable config; this README mirrors them for team visibility only.
