# UniFi SSH Logs

<p align="center">
  <img src="custom_components/unifi_ssh_logs/brand/logo.png" alt="UniFi SSH Logs" width="128" />
</p>

Home Assistant custom integration that fetches UniFi console logs over SSH, matches regex alert rules, and exposes events, binary sensors, a polling switch, and a Lovelace log card.

**Version:** 0.5.0 · **Domain:** `unifi_ssh_logs`

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=HenryHST&repository=ha-unifi-ssh-logs&category=integration)
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=unifi_ssh_logs)

**SoT (lab):** [Infra_LAB `scripts/ha-unifi-syslog/`](https://github.com/HenryHST/Infra_LAB/tree/main/scripts/ha-unifi-syslog) · full docs: [`docs/ha-unifi-ssh-logs.md`](https://github.com/HenryHST/Infra_LAB/blob/main/docs/ha-unifi-ssh-logs.md)

> Not a Supervisor add-on. Do **not** add [hassio-addons](https://github.com/HenryHST/hassio-addons) as a HACS integration repo — use this repository instead.

## Install (HACS)

1. Install via HACS (custom repository) — or click:  
   [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=HenryHST&repository=ha-unifi-ssh-logs&category=integration)  
   Manual: HACS → **⋯** → **Custom repositories** → URL `https://github.com/HenryHST/ha-unifi-ssh-logs` → Category **Integration** → Download
2. Restart Home Assistant
3. Add the integration under Settings → Devices & services, or click:  
   [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=unifi_ssh_logs)

## Auth (SSH)

- Enable SSH on the UniFi console (Settings → Control Plane → Console → SSH)
- **UI (0.5.0):** leave private key empty to generate ed25519 → authorize step shows the public key to paste into Console `authorized_keys` / SSH Keys; or paste an existing OpenSSH private key; or password-only
- **Legacy / YAML:** key file under `/config/ssh/` (paths must stay under the HA config directory) and/or password via `!secret`

## Lovelace card

1. Copy `www/unifi_ssh_logs/` to `/config/www/unifi_ssh_logs/` (HACS does not install `www/` automatically)
2. Dashboards → Resources → Add:
   - URL: `/local/unifi_ssh_logs/unifi-ssh-logs-card.js?v=0.4.1`
   - Type: **JavaScript Module**
3. Card:

```yaml
type: custom:unifi-ssh-logs-card
title: UniFi SSH Logs
```

Downloads use authenticated `fetchWithAuth` (TXT/CSV). After card updates, bump `?v=` and hard-reload.

## Blueprint

Copy `blueprints/automation/unifi_ssh_logs_notify.yaml` to `/config/blueprints/automation/unifi_ssh_logs/`.

## Sync from Infra_LAB (maintainers)

SoT remains in Infra_LAB. Publish to this repo:

```bash
# from Infra_LAB checkout
rsync -a --delete --exclude '__pycache__' --exclude '.*' \
  scripts/ha-unifi-syslog/custom_components/ \
  ../ha-unifi-ssh-logs/custom_components/
rsync -a --delete --exclude '.*' \
  scripts/ha-unifi-syslog/www/ \
  ../ha-unifi-ssh-logs/www/
rsync -a --delete --exclude '.*' \
  scripts/ha-unifi-syslog/blueprints/ \
  ../ha-unifi-ssh-logs/blueprints/
cp scripts/ha-unifi-syslog/hacs.json ../ha-unifi-ssh-logs/
cp scripts/ha-unifi-syslog/README.md ../ha-unifi-ssh-logs/
```

## License

See repository license / upstream Infra_LAB.
