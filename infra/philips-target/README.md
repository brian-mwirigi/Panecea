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
| Firewall group | `panacea-target-fw` (`b57ae685-a98b-44e2-a867-60270e9647de`) — same account-wide firewall group reused from the Paris instance (Vultr firewall groups are not region-locked) |
| Port 3200 (HL7) | **Open to everyone** at the Vultr cloud firewall level (`0.0.0.0/0`) — a real Python TCP listener (`hl7_listener.py`) is running as a systemd service, responds with a placeholder HL7-style ACK. Verified working via localhost on the box itself. **KNOWN ISSUE:** the box's own OS-level `ufw` firewall (Ubuntu default) only allows port 22 inbound and does NOT have an explicit allow rule for 3200 — so despite the Vultr cloud firewall being open, `ufw` may still be dropping external connections to 3200 at the OS level. This same gap exists on the old Paris VM too (verified — not a regression introduced during the Chicago migration). Needs `ufw allow 3200/tcp` on the box if full external reachability is required for the demo; not yet applied, pending confirmation (see report). |
| Port 22 (SSH) | Open at the Vultr cloud firewall to **two** scoped IPs: `102.159.195.84/32` (temporary sandbox admin-access IP, kept for continued admin/setup access) and `64.177.113.13/32` (Zain's real attacker VM — the actual intended attack surface for the brute-force demo). Both rules kept intentionally: one for admin convenience, one for the live attack. OS-level `ufw` already allows 22/tcp from anywhere, so this is fully live for both IPs. |

## Superseded — Paris instance (pending decommission decision)

The original target VM in Paris is still running but is **no longer the active demo target**. Team decided to move to Chicago (`ord`) to match a proper Vultr VPC setup. This instance has **not** been destroyed — awaiting explicit confirmation before deletion, since destroying cloud resources is a one-way decision. Cost is trivial (~$5/mo prorated hourly) so there's no urgency, but leaving it running risks Zain (or others) attacking the wrong IP if not clearly communicated.

| Item | Value |
|---|---|
| Status | **SUPERSEDED — still running, not yet destroyed** |
| Instance ID | `3a71efd5-fb92-4334-83e9-3653c0386296` |
| Region | Paris (`cdg`) |
| Public IP | `45.32.146.113` |
| Firewall group | Same shared group `panacea-target-fw` — so its port 22 rules changed too (now also reachable from `64.177.113.13/32` in addition to the sandbox admin IP), and it still has its own `hl7_listener.py` running on port 3200 from prior setup. |

## Team context (not Mohamed's action items, noted for reference)

- **Zain** (attacker VM / Python firewall execution scripts owner): attacker VM is live at `64.177.113.13` (root SSH access). This is the real IP now allowed through the target's firewall on port 22.
- **Brian** (backend/orchestrator, presumably FastAPI): service reported running at `45.76.26.39`. Not attached to the VPC and no action taken here — flagging in case private networking between backend and target VPC becomes relevant later.

## Files in this directory

- `hl7_listener.py` — the trivial placeholder TCP listener bound to port 3200. Not real HL7 protocol logic — just enough to be a real, alive service so the firewall's "allow 3200" rule has something real behind it. Deployed at `/root/hl7_listener.py` on both the Chicago and (still-running) Paris target VMs.
- `hl7-listener.service` — systemd unit running the listener, auto-restarts, survives reboots. Installed at `/etc/systemd/system/hl7-listener.service` on both boxes, enabled via `systemctl enable --now hl7-listener.service`.

## For Zain (attacker VM owner)

Target IP: `64.177.118.214` (Chicago — this is now the real target, NOT the old `45.32.146.113` Paris IP). Port 22 is open at the Vultr cloud firewall from your attacker VM's IP (`64.177.113.13/32`) specifically. If your brute-force attempts still don't reach the box, the likely culprit is the target's own `ufw` OS-level firewall, which currently only allows 22/tcp and may not have an explicit rule for 3200 — flag this back to Mohamed if 3200 connectivity is needed for your scripts too.

## Re-provisioning notes

- SSH key pair for admin access is `panacea-target-key` (registered on the Vultr account, ID `e766aa16-af8a-4436-9aaf-2892ea5bac9c`), keypair not stored in this repo (local copy at `~/.ssh/panacea_target` on Mohamed's machine).
- Firewall group ID, instance IDs, and VPC ID are tracked outside this repo (Vultr Console) since they're account-specific, not portable config; this README mirrors them for team visibility only.
