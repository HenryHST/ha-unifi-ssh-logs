"""Constants for UniFi SSH Logs."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "unifi_ssh_logs"
VERSION: Final = "0.5.2"

DEFAULT_HOST: Final = "192.168.0.1"
DEFAULT_USERNAME: Final = "root"
DEFAULT_KEY_PATH: Final = "/config/ssh/ha-unifi-logs"
DEFAULT_KNOWN_HOSTS: Final = "/config/ssh/known_hosts"
DEFAULT_OUT_DIR: Final = "/config/unifi_logs"
DEFAULT_CUSTOM_RULES_PATH: Final = "/config/unifi_ssh_logs/rules.d"
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=5)
MIN_SCAN_SECONDS: Final = 60

DEFAULT_RETENTION_MAX_FILES: Final = 40
DEFAULT_RETENTION_MAX_AGE_DAYS: Final = 7
DEFAULT_ALERT_HISTORY_SIZE: Final = 20

CONF_HOST: Final = "host"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_KEY_PATH: Final = "key_path"
CONF_PRIVATE_KEY: Final = "private_key"
CONF_KNOWN_HOSTS: Final = "known_hosts"
CONF_OUT_DIR: Final = "out_dir"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_ENABLE_PARSING: Final = "enable_parsing"
CONF_CUSTOM_RULES_PATH: Final = "custom_rules_path"
CONF_FETCH_MESSAGES: Final = "fetch_messages"
CONF_FETCH_JOURNAL: Final = "fetch_journal"
CONF_FETCH_UNIFI: Final = "fetch_unifi"
CONF_RETENTION_MAX_FILES: Final = "retention_max_files"
CONF_RETENTION_MAX_AGE_DAYS: Final = "retention_max_age_days"

ATTR_LAST_MATCH: Final = "last_match"
ATTR_MATCH_COUNT: Final = "match_count"
ATTR_SAMPLE_LINE: Final = "sample_line"
ATTR_SEVERITY: Final = "severity"
ATTR_RULE_ID: Final = "rule_id"
ATTR_SOURCE: Final = "source"
ATTR_ALERT_HISTORY: Final = "alert_history"

EVENT_ALERT: Final = "unifi_ssh_logs_alert"

SERVICE_FETCH: Final = "fetch"

STATUS_IDLE: Final = "idle"
STATUS_OK: Final = "ok"
STATUS_ERROR: Final = "error"
STATUS_RUNNING: Final = "running"

SOURCE_MESSAGES: Final = "messages"
SOURCE_JOURNAL: Final = "journal"
SOURCE_UNIFI: Final = "unifi"
SOURCE_ANY: Final = "any"

CURSOR_TAIL_LINES: Final = 400

# Custom rule / ReDoS guardrails
MAX_PATTERN_LEN: Final = 200
MAX_CUSTOM_RULES: Final = 50
MAX_TOTAL_RULES: Final = 100

# Support bundle cooldown (seconds)
SUPPORT_COOLDOWN_SECONDS: Final = 300

# Public message sample length (after redaction)
PUBLIC_SAMPLE_LEN: Final = 120
