# UniFi SSH Logs — Home Assistant Integration

Stand: 2026-11-16 · Version **0.5.2** · Domain **`unifi_ssh_logs`** · Ziel-Host **ha02** (`192.168.0.106`)

Eigene Custom-Integration (nicht die offizielle UniFi-Network-Integration). Holt Console-Logs per SSH von der UniFi-Gateway (`192.168.0.1`), matched Regex-Alert-Rules und liefert Events / Binary-Sensors für Automationen.

| | |
|--|--|
| SoT / Code | [`scripts/ha-unifi-syslog/`](../scripts/ha-unifi-syslog/) |
| **HACS** | [`HenryHST/ha-unifi-ssh-logs`](https://github.com/HenryHST/ha-unifi-ssh-logs) (Integration — nicht [hassio-addons](https://github.com/HenryHST/hassio-addons)) |
| CLI ohne HA | [`scripts/unifi-fetch-logs.sh`](../scripts/unifi-fetch-logs.sh) |
| Deploy-Notizen ha02 | [`ansible/.../files/ha02/README.md`](../ansible/playbooks/k3s_cluster/files/ha02/README.md) |
| **In HA (UI)** | [`/local/unifi_ssh_logs/`](http://192.168.0.106:8123/local/unifi_ssh_logs/) · optional Sidebar als **Webpage-Dashboard** |
| Log-Ablage (HA) | `/config/unifi_logs/` |
| Custom Rules | `/config/unifi_ssh_logs/rules.d/*.yaml` |

### Doku in Home Assistant

`panel_iframe` gibt es seit HA **2024.11** nicht mehr. Die HTML-Doku liegt unter `/local/` und kann optional als Webpage-Dashboard in der Sidebar erscheinen.

1. **HTML deployen** (SoT: [`scripts/ha-unifi-syslog/www/unifi_ssh_logs/`](../scripts/ha-unifi-syslog/www/unifi_ssh_logs/)):

```bash
rsync -a scripts/ha-unifi-syslog/www/unifi_ssh_logs/ \
  ha02.stadthagen.dev:/config/www/unifi_ssh_logs/
```

2. **Öffnen:** [`http://192.168.0.106:8123/local/unifi_ssh_logs/`](http://192.168.0.106:8123/local/unifi_ssh_logs/) (bzw. `/local/unifi_ssh_logs/index.html`)

3. **Optional Sidebar** (einmalig in der UI):
   - **Settings → Dashboards → Add dashboard → Webpage**
   - Title: `UniFi SSH Logs`
   - Icon: `mdi:router-network`
   - URL: `/local/unifi_ssh_logs/index.html`
   - Show in sidebar: ja

4. Integrations-Link „Dokumentation“ in HA zeigt auf das HACS-Repo [`ha-unifi-ssh-logs`](https://github.com/HenryHST/ha-unifi-ssh-logs).

Das Package [`unifi_ssh_logs_docs.yaml`](../ansible/playbooks/k3s_cluster/files/ha02/packages/unifi_ssh_logs_docs.yaml) ist absichtlich leer (`{}`) — nur noch Kommentar-Hinweis, kein YAML-Panel.

### Architektur (SeeCode)

![UniFi SSH Logs Ablauf](diagrams/seecode/unifi-ssh-logs-flow.svg)

Interaktiv (Trace/Focus): [`diagrams/seecode/unifi-ssh-logs-flow.html`](diagrams/seecode/unifi-ssh-logs-flow.html) · Spec: [`unifi-ssh-logs-flow.json`](diagrams/seecode/unifi-ssh-logs-flow.json)

In HA: eingebettetes Diagramm unter [`/local/unifi_ssh_logs/`](http://192.168.0.106:8123/local/unifi_ssh_logs/) (Abschnitt Diagramm).

---

## Was die Integration macht

1. Per SSH Logs holen: `/var/log/messages`, `journalctl -u unifi`, UniFi-App-Logs; optional Support-Bundle (`ubnt-make-support-file`)
2. Nur **neue** Zeilen seit letztem Cursor parsen
3. Regex-Rules anwenden → Bus-Event + Binary-Sensor `on`
4. Auto-Clear nach `clear_after_minutes` oder Button „Clear alerts“
5. Dateien unter `/config/unifi_logs/` ablegen

Default-Poll: **5 Minuten** (min. 60 s).

---

## Installation

### HACS (empfohlen)

1. HACS Custom Repository: [![HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=HenryHST&repository=ha-unifi-ssh-logs&category=integration)
   oder manuell: HACS → **⋯** → **Custom repositories** → `https://github.com/HenryHST/ha-unifi-ssh-logs` → Kategorie **Integration**
2. Integration installieren, HA neu starten
3. Setup: [![Config flow](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=unifi_ssh_logs)
   oder Einstellungen → Geräte & Dienste → Integration hinzufügen → **UniFi SSH Logs**

Lovelace-Card / HTML-Doku: `www/unifi_ssh_logs/` manuell nach `/config/www/unifi_ssh_logs/` kopieren (HACS installiert `www/` nicht). Resource: `/local/unifi_ssh_logs/unifi-ssh-logs-card.js?v=0.5.2` (JavaScript Module).

### Manuell (ha02 / Infra_LAB SoT)

```bash
# Aus Infra_LAB — Integration
rsync -a scripts/ha-unifi-syslog/custom_components/unifi_ssh_logs/ \
  ha02.stadthagen.dev:/config/custom_components/unifi_ssh_logs/

# HTML-Doku unter /local/
rsync -a scripts/ha-unifi-syslog/www/unifi_ssh_logs/ \
  ha02.stadthagen.dev:/config/www/unifi_ssh_logs/

# Optional: Notify-Blueprint
rsync -a scripts/ha-unifi-syslog/blueprints/automation/unifi_ssh_logs_notify.yaml \
  ha02.stadthagen.dev:/config/blueprints/automation/unifi_ssh_logs/

# Home Assistant Core neu starten (custom_components)
```

Bei Permission-Problemen über das SSH-Addon: `sudo tar` nach `/config/…` (Owner oft `911:1001`).

### Sync SoT → HACS-Repo (Maintainer)

SoT bleibt [`scripts/ha-unifi-syslog/`](../scripts/ha-unifi-syslog/). Publish-Schritte: siehe Sync-Abschnitt in der [HACS-README](https://github.com/HenryHST/ha-unifi-ssh-logs#sync-from-infra_lab-maintainers).
Danach: **Einstellungen → Geräte & Dienste → Integration hinzufügen → UniFi SSH Logs**.
Sidebar-Doku: siehe [Doku in Home Assistant](#doku-in-home-assistant) (Webpage-Dashboard, nicht `panel_iframe`).

---

## Sicherheitshinweis

Die Aktivierung von **Console-SSH** auf einer UniFi Dream Machine / UniFi-Gateway öffnet einen Shell-Zugang im erreichbaren Netz. Die Absicherung (Key bevorzugt, starkes Passwort falls nötig, wer Port 22 erreichen darf, ob SSH dauerhaft an bleibt) liegt beim Betreiber. Aktivierung von SSH in der UniFi-Console und Nutzung dieser Integration erfolgen **auf eigene Verantwortung**; die Autoren übernehmen keine Haftung für Missbrauch, Fehlkonfiguration oder Folgeschäden.

## Authentifizierung

SSH auf der Console muss aktiv sein (UniFi → Settings → Control Plane → Console → SSH).

### UI-Setup (0.5.0, empfohlen)

Im Config-Flow:

1. Host + SSH-Benutzer; **Private Key leer lassen** (HA erzeugt ed25519) oder bestehenden OpenSSH-Key einfügen; optional Passwort
2. Schritt **SSH-Key freigeben**: angezeigten Public Key auf der Console in `authorized_keys` / SSH Keys eintragen
3. Bestätigen — HA prüft die SSH-Verbindung; der Private Key wird in der Config-Entry gespeichert (nicht als Datei nötig)

Bestehende Setups mit `key_path` bleiben gültig.

### Variante A — SSH-Key-Datei (Legacy / YAML)

```bash
mkdir -p /opt/homelab/data/homeassistant/config/ssh
ssh-keygen -t ed25519 -f /opt/homelab/data/homeassistant/config/ssh/ha-unifi-logs -N '' -C ha-unifi-logs
# Public Key → authorized_keys auf root@192.168.0.1
ssh-keyscan -H 192.168.0.1 >> /opt/homelab/data/homeassistant/config/ssh/known_hosts
```

Im Config-Flow:

| Feld | Default |
|------|---------|
| Host | `192.168.0.1` |
| User | `root` |
| Key-Pfad | `/config/ssh/ha-unifi-logs` |
| known_hosts | `/config/ssh/known_hosts` |

Fehlt der Host in `known_hosts`, akzeptiert die Integration den Key einmalig (**accept-new**, analog OpenSSH). Vorhandene Einträge werden weiterhin geprüft.

### Variante B — Passwort über `secrets.yaml`

Der UI-Config-Flow kann `!secret` **nicht** auflösen. YAML:

```yaml
# configuration.yaml
unifi_ssh_logs:
  host: 192.168.0.1
  username: root
  password: !secret unifi_ssh_password
  known_hosts: /config/ssh/known_hosts
```

```yaml
# secrets.yaml
unifi_ssh_password: "…"
```

Nach Restart wird die YAML-Config als Config-Entry importiert. Im UI gesetzte Passwörter liegen verschlüsselt in `.storage`, nicht in `secrets.yaml`.

Key und Passwort können kombiniert werden; existiert die Key-Datei, wird sie bevorzugt.

---

## Entities & Service

| Typ | Beispiele / Keys |
|-----|------------------|
| Switch | **`polling`** — Auto-Abruf an/aus (`update_interval` = `None` wenn aus) |
| Buttons | `fetch_logs`, `fetch_support`, `fetch_all`, `clear_alerts` |
| Sensors | `last_status`, `last_fetch`, `last_error`, `open_alerts`, **`match_count`** |
| Binary sensors | eine pro Rule-ID, z. B. `wan_down`, `disk_full` |
| Event entity | `event.…_alert` (Typ `alert`) |
| Bus-Event | `unifi_ssh_logs_alert` |
| Service | `unifi_ssh_logs.fetch` (`mode`, `include_support`, optional `entry_id`) |

`match_count` trägt Attribut `alert_history` (letzte Treffer). Options: Quellen (`fetch_messages` / `fetch_journal` / `fetch_unifi`), Log-Retention (Anzahl + Alter).

Polling-Switch **aus**: kein periodischer SSH-Abruf; Buttons und Service `fetch` bleiben nutzbar. Zustand überlebt Restart.

### Lovelace-Card (Log-Download)

1. Resource (einmalig): **Settings → Dashboards → ⋮ → Resources → Add**
   - URL: `/local/unifi_ssh_logs/unifi-ssh-logs-card.js?v=0.5.2`
   - Type: **JavaScript Module**
   - Nach Card-Updates die Query (`?v=…`) erhöhen und Dashboard hard-reloaden (sonst bleibt altes Modul im Browser-Cache).
2. Card auf einem Dashboard:

```yaml
type: custom:unifi-ssh-logs-card
title: UniFi SSH Logs
# entry_id: optional — sonst erste Integration-Instanz
```

Die Card listet Dateien unter `/config/unifi_logs/` und bietet Download als **TXT** oder **CSV** (Support-Bundles nur als `.tar.gz`). Ab **0.5.1** filtert ein Monats-Kalender (Podcraft-Restore-Stil) nach lokalem `mtime`-Tag; erneuter Klick bzw. **All** zeigt wieder alle Dateien. API: `/api/unifi_ssh_logs/files`, `/api/unifi_ssh_logs/download` — Abruf nur mit HA-Auth über `fetchWithAuth` (kein unauthentifizierter Tab auf `/api/...`). Unter Safari kann der Download als Blob-Tab erscheinen (Popups ggf. erlauben).

### Service-Beispiel

```yaml
action: unifi_ssh_logs.fetch
data:
  mode: logs
  include_support: false
```

### Blueprint (Notify)

[`scripts/ha-unifi-syslog/blueprints/automation/unifi_ssh_logs_notify.yaml`](../scripts/ha-unifi-syslog/blueprints/automation/unifi_ssh_logs_notify.yaml) → nach `/config/blueprints/automation/unifi_ssh_logs/` kopieren.

Attribute der Alert-Binary-Sensors: `last_match`, `match_count`, `sample_line` (gekürzt), `severity`, `rule_id`.

`last_status` → Attribut `last_files` listet die zuletzt geschriebenen Log-Pfade.

---

## Default-Alert-Rules

Mitgeliefert in `rules.yaml` (deaktivierbar / überschreibbar):

| rule_id | Severity | Bedeutung |
|---------|----------|-----------|
| `wan_down` | critical | WAN weg / PPP LCP |
| `wan_up` | info | WAN wieder da |
| `ipsec_down` | warning | IPsec / charon |
| `dhcp_flood` | warning | DHCP-Probleme |
| `auth_fail` | warning | Login-/Auth-Fehler |
| `adopt_fail` | warning | Adoption / inform fail |
| `high_cpu_temp` | warning | Thermik |
| `disk_full` | critical | Speicher voll |

### Eigene Rules

```yaml
# /config/unifi_ssh_logs/rules.d/extra.yaml
- id: my_rule
  name: My pattern
  severity: warning
  source: any   # messages | journal | unifi | any
  pattern: '(?i)something.?bad'
  enabled: true
  clear_after_minutes: 30
```

Gleiche `id` wie eine Default-Rule **überschreibt** diese.

---

## Beispiel-Automation

```yaml
automation:
  - alias: UniFi WAN down notify
    triggers:
      - trigger: event
        event_type: unifi_ssh_logs_alert
        event_data:
          rule_id: wan_down
    actions:
      - action: notify.mobile_app_…
        data:
          title: UniFi WAN
          message: "{{ trigger.event.data.message }}"
```

---

## Log-Dateien finden

| Ort | Pfad |
|-----|------|
| In HA (SSH-Addon) | `/config/unifi_logs/` |
| Auf dem Host-Volume | `/opt/homelab/data/homeassistant/config/unifi_logs/` |

Beispiele: `messages-20261113-223000.log`, `journal-unifi-….txt`, `unifi-server-….log`, optional `support-….tar.gz`.

---

## Betrieb / Troubleshooting

| Symptom | Check |
|---------|--------|
| `Host key is not trusted` | Host fehlt in `known_hosts` oder Key geändert — Integration nutzt accept-new; alternativ `ssh-keyscan -H 192.168.0.1` anhängen |
| `last_status` = `error` | `last_error` lesen; Key-Pfad / Passwort / Console-SSH |
| Keine Alerts | Parsing aktiv? Rules `enabled`? Erster Lauf parst nur die letzten ~50 Zeilen (kein Alert-Sturm) |
| Blocking-Warnungen (`import asyncssh`) | Ab 0.4.1: `asyncssh`-Import im Executor; Component neu ausrollen + HA neu starten |
| Download **401** / `http.ban` | Alte Card ohne Auth-Fallback — Resource auf `?v=0.5.2` setzen, hard-reload |
| Download **HTTP 500** | Altes Response-`charset` in `content_type` — 0.4.1 deployen (aiohttp verlangt `charset=` separat) |

Internals (0.5.0): SSH-Verbindungen bleiben async auf dem Event-Loop; der **Import** von `asyncssh` (liboqs/fido2-I/O) läuft im Executor. Config-Flow kann Inline-`private_key` erzeugen/anzeigen. Download-Responses nutzen `content_type` ohne eingebettetes `charset=`.

Unit-Tests (ohne HA Core):

```bash
python3 -m pytest scripts/ha-unifi-syslog/tests -q \
  --ignore=scripts/ha-unifi-syslog/tests/test_ha_integration.py
```

Optionale HA-Integrationstests (`pytest-homeassistant-custom-component`):

```bash
PYTHONPATH=scripts/ha-unifi-syslog python3 -m pytest \
  scripts/ha-unifi-syslog/tests/test_ha_integration.py -q
```

Diagnostics: Einstellungen → Geräte & Dienste → UniFi SSH Logs → ⋮ → Diagnosedaten herunterladen (Passwort redacted).

### Sicherheit (0.3.0 / 0.4.x)

- `out_dir`, `key_path`, `known_hosts`, `custom_rules_path` müssen unter dem HA-Config-Verzeichnis liegen
- Alert-Events / `sample_line` / `alert_history` / Notify-Blueprint: Logzeilen redacted + gekürzt
- Custom-Rules: Pattern-Länge, Rule-Anzahl und nested Quantifiers begrenzt (ReDoS)
- Support-Bundle: Mutex + 5‑Minuten-Cooldown
- `last_error`: sanitisiert (keine Klartext-Passwörter)
- Log-Download-API nur mit HA-Auth; Dateinamen allowlistet unter `out_dir`
- Default-SSH-User bleibt `root` (UniFi-üblich); wenn möglich separaten least-privilege SSH-User nutzen
- 0.4.1: kein Blocking-Import von `asyncssh` auf dem Event-Loop; Card öffnet API-URLs nicht ohne Token

---

## Nicht im Scope

- Offizielle UniFi-Network-Integration ersetzen
- Separate Key-Passphrase (nur Login-Passwort / Key-Datei)
- ML / Anomalie-Erkennung — nur explizite Regex-Rules
- Strikte Host-Key-Prüfung ohne accept-new (weiterhin documented opt-in hardening)
