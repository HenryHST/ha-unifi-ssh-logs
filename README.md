# UniFi SSH Logs

Home Assistant custom integration that fetches UniFi console logs over SSH, matches regex alert rules, and exposes events, binary sensors, a polling switch, and a Lovelace log card.

**Version:** 0.4.1  
**Domain:** `unifi_ssh_logs`  
**SoT (lab):** [Infra_LAB `scripts/ha-unifi-syslog/`](https://github.com/HenryHST/Infra_LAB/tree/main/scripts/ha-unifi-syslog) · full docs: [`docs/ha-unifi-ssh-logs.md`](https://github.com/HenryHST/Infra_LAB/blob/main/docs/ha-unifi-ssh-logs.md)

> Not a Supervisor add-on. Do **not** add [hassio-addons](https://github.com/HenryHST/hassio-addons) as a HACS integration repo — use this repository instead.

## Install (HACS)

1. HACS → **⋯** → **Custom repositories**
2. URL: `https://github.com/HenryHST/ha-unifi-ssh-logs`
3. Category: **Integration**
4. Download / install **UniFi SSH Logs**, then restart Home Assistant
5. Settings → Devices & services → Add integration → **UniFi SSH Logs**

## Auth (SSH)

- Enable SSH on the UniFi console
- Prefer a key under `/config/ssh/` (paths must stay under the HA config directory)
- Or password via YAML / `!secret` (UI passwords land in `.storage`)

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
