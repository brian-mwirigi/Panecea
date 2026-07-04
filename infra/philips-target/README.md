# Philips IntelliVue target VM (Mohamed — IIoT Target)

Real Vultr instance simulating the vulnerable Philips IntelliVue patient monitor for the live attack/defense demo.

## Current state

| Item | Value |
|---|---|
| Provider | Vultr Cloud Compute |
| Region | Paris (`cdg`) |
| Plan | `vc2-1c-1gb` ($5/mo, billed hourly — negligible cost for the event) |
| OS | Ubuntu 24.04 LTS |
| Public IP | `45.32.146.113` |
| Firewall group | `panacea-target-fw` |
| Port 3200 (HL7) | **Open to everyone** (`0.0.0.0/0`) — a real Python TCP listener (`hl7_listener.py`) is running as a systemd service, responds with a placeholder HL7-style ACK. This is what the "allow port 3200" firewall rule protects/allows. |
| Port 22 (SSH) | **Intentionally NOT open to the world yet** — this is the vulnerability the demo exploits. Currently scoped to a single admin IP for setup access only. **Needs to be opened to Zain's attacker VM's IP (or `0.0.0.0/0` if going fully public) before the live attack demo can work.** |

## Files in this directory

- `hl7_listener.py` — the trivial placeholder TCP listener bound to port 3200. Not real HL7 protocol logic — just enough to be a real, alive service so the firewall's "allow 3200" rule has something real behind it. Deployed at `/root/hl7_listener.py` on the target VM.
- `hl7-listener.service` — systemd unit running the listener, auto-restarts, survives reboots. Installed at `/etc/systemd/system/hl7-listener.service`, enabled via `systemctl enable --now hl7-listener.service`.

## For Zain (attacker VM owner)

Target IP: `45.32.146.113`. Port 22 is currently locked down to a single admin IP — ping Mohamed to get your attacker VM's IP added to the `panacea-target-fw` firewall group before testing the brute-force → firewall-lockdown handoff (the Hour-14 Checkpoint).

## Re-provisioning notes

- SSH key pair for admin access is `panacea-target-key` (registered on the Vultr account), keypair not stored in this repo.
- Firewall group ID and instance ID are tracked outside this repo (Vultr Console) since they're account-specific, not portable config.
