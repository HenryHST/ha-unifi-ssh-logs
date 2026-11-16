"""DataUpdateCoordinator: SSH fetch + parse UniFi logs."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .auth import incremental_new_lines, resolve_known_hosts_arg, resolve_ssh_auth
from .const import (
    CONF_CUSTOM_RULES_PATH,
    CONF_ENABLE_PARSING,
    CONF_FETCH_JOURNAL,
    CONF_FETCH_MESSAGES,
    CONF_FETCH_UNIFI,
    CONF_HOST,
    CONF_KEY_PATH,
    CONF_KNOWN_HOSTS,
    CONF_OUT_DIR,
    CONF_PASSWORD,
    CONF_RETENTION_MAX_AGE_DAYS,
    CONF_RETENTION_MAX_FILES,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    CURSOR_TAIL_LINES,
    DEFAULT_ALERT_HISTORY_SIZE,
    DEFAULT_CUSTOM_RULES_PATH,
    DEFAULT_KEY_PATH,
    DEFAULT_KNOWN_HOSTS,
    DEFAULT_OUT_DIR,
    DEFAULT_RETENTION_MAX_AGE_DAYS,
    DEFAULT_RETENTION_MAX_FILES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_ALERT,
    PUBLIC_SAMPLE_LEN,
    SOURCE_JOURNAL,
    SOURCE_MESSAGES,
    SOURCE_UNIFI,
    STATUS_ERROR,
    STATUS_IDLE,
    STATUS_OK,
    STATUS_RUNNING,
    SUPPORT_COOLDOWN_SECONDS,
)
from .parser import (
    AlertRule,
    AlertState,
    RuleMatch,
    apply_matches,
    clear_all,
    clear_expired,
    load_rules,
    match_lines,
)
from .paths import PathConfigError, require_under_config, resolve_under_config
from .retention import rotate_log_dir
from .sanitize import redact_text, sanitize_error

_LOGGER = logging.getLogger(__name__)

# Cached after first executor import — asyncssh does blocking I/O on first import.
_asyncssh_mod: Any = None


def load_asyncssh_blocking() -> Any:
    """Import asyncssh off the event loop (blocking: ctypes/glob/fido2)."""
    global _asyncssh_mod
    if _asyncssh_mod is None:
        import asyncssh as asyncssh_mod

        _asyncssh_mod = asyncssh_mod
    return _asyncssh_mod


@dataclass
class CoordinatorData:
    """Snapshot exposed to entities."""

    status: str = STATUS_IDLE
    last_fetch: datetime | None = None
    last_error: str = ""
    last_files: list[str] = field(default_factory=list)
    open_alerts: int = 0
    match_count_total: int = 0
    alert_states: dict[str, AlertState] = field(default_factory=dict)
    rules: list[AlertRule] = field(default_factory=list)
    alert_history: list[dict[str, Any]] = field(default_factory=list)


class UnifiSshLogsCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Fetch UniFi console logs over SSH and apply alert rules."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        options = {**entry.data, **entry.options}
        interval = options.get(CONF_SCAN_INTERVAL)
        update_interval = (
            DEFAULT_SCAN_INTERVAL
            if interval is None
            else timedelta(seconds=int(interval))
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
            config_entry=entry,
        )
        self._alert_states: dict[str, AlertState] = {}
        self._cursors: dict[str, str] = {}
        self._rules: list[AlertRule] = []
        self._alert_listeners: list[Callable[[dict[str, Any]], None]] = []
        self._match_count_total = 0
        self._alert_history: deque[dict[str, Any]] = deque(
            maxlen=DEFAULT_ALERT_HISTORY_SIZE
        )
        self._support_lock = asyncio.Lock()
        self._last_support_at: datetime | None = None
        self._polling_enabled = True
        self._configured_interval = update_interval
        self.data = CoordinatorData()

    def _cfg(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def _config_dir(self) -> Path:
        return Path(self.hass.config.config_dir)

    @property
    def polling_enabled(self) -> bool:
        """Whether scheduled SSH polling is active."""
        return self._polling_enabled

    def configured_scan_interval(self) -> timedelta:
        """Return scan interval from config (ignores polling switch)."""
        options = self._cfg()
        interval = options.get(CONF_SCAN_INTERVAL)
        if interval is None:
            return DEFAULT_SCAN_INTERVAL
        return timedelta(seconds=int(interval))

    @callback
    def set_polling_enabled(self, enabled: bool) -> None:
        """Enable or disable the scheduled update interval."""
        self._polling_enabled = bool(enabled)
        self._configured_interval = self.configured_scan_interval()
        self.update_interval = (
            self._configured_interval if self._polling_enabled else None
        )
        _LOGGER.debug(
            "Polling %s (interval=%s)",
            "enabled" if self._polling_enabled else "disabled",
            self.update_interval,
        )

    @callback
    def async_on_alert(
        self, listener: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Register a callback for newly activated alerts; return unsubscribe."""
        self._alert_listeners.append(listener)

        @callback
        def _unsub() -> None:
            if listener in self._alert_listeners:
                self._alert_listeners.remove(listener)

        return _unsub

    @property
    def host(self) -> str:
        return self.entry.data[CONF_HOST]

    @property
    def username(self) -> str:
        return self._cfg().get(CONF_USERNAME, "root")

    @property
    def key_path(self) -> str:
        raw = self._cfg().get(CONF_KEY_PATH, DEFAULT_KEY_PATH) or ""
        if not raw:
            return ""
        return str(require_under_config(raw, self._config_dir()))

    @property
    def password(self) -> str | None:
        value = self._cfg().get(CONF_PASSWORD)
        return str(value) if value else None

    @property
    def known_hosts(self) -> str:
        return str(
            require_under_config(
                self._cfg().get(CONF_KNOWN_HOSTS, DEFAULT_KNOWN_HOSTS),
                self._config_dir(),
            )
        )

    @property
    def out_dir(self) -> Path:
        return require_under_config(
            self._cfg().get(CONF_OUT_DIR, DEFAULT_OUT_DIR),
            self._config_dir(),
        )

    @property
    def enable_parsing(self) -> bool:
        return bool(self._cfg().get(CONF_ENABLE_PARSING, True))

    @property
    def fetch_messages(self) -> bool:
        return bool(self._cfg().get(CONF_FETCH_MESSAGES, True))

    @property
    def fetch_journal(self) -> bool:
        return bool(self._cfg().get(CONF_FETCH_JOURNAL, True))

    @property
    def fetch_unifi(self) -> bool:
        return bool(self._cfg().get(CONF_FETCH_UNIFI, True))

    @property
    def retention_max_files(self) -> int:
        return int(
            self._cfg().get(CONF_RETENTION_MAX_FILES, DEFAULT_RETENTION_MAX_FILES)
        )

    @property
    def retention_max_age_days(self) -> int:
        return int(
            self._cfg().get(
                CONF_RETENTION_MAX_AGE_DAYS, DEFAULT_RETENTION_MAX_AGE_DAYS
            )
        )

    @property
    def rules(self) -> list[AlertRule]:
        """Loaded alert rules."""
        return self._rules

    def reload_rules(self) -> None:
        """Load rules from disk (blocking; run in executor)."""
        bundled = Path(__file__).with_name("rules.yaml")
        raw_custom = self._cfg().get(CONF_CUSTOM_RULES_PATH, DEFAULT_CUSTOM_RULES_PATH)
        try:
            custom = resolve_under_config(
                raw_custom, self._config_dir(), allow_empty=True
            )
        except PathConfigError:
            _LOGGER.error("custom_rules_path outside config dir: %s", raw_custom)
            custom = None
        self._rules = load_rules(bundled, custom)
        for rule in self._rules:
            if rule.id not in self._alert_states:
                self._alert_states[rule.id] = AlertState(
                    name=rule.name,
                    severity=rule.severity,
                    clear_after=timedelta(minutes=rule.clear_after_minutes),
                )
        self._publish_snapshot(
            status=self.data.status,
            last_fetch=self.data.last_fetch,
            last_error=self.data.last_error,
            last_files=list(self.data.last_files),
        )

    def _publish_snapshot(
        self,
        *,
        status: str,
        last_fetch: datetime | None,
        last_error: str,
        last_files: list[str],
    ) -> None:
        self.data = CoordinatorData(
            status=status,
            last_fetch=last_fetch,
            last_error=last_error,
            last_files=last_files,
            open_alerts=sum(1 for s in self._alert_states.values() if s.active),
            match_count_total=self._match_count_total,
            alert_states=dict(self._alert_states),
            rules=list(self._rules),
            alert_history=list(self._alert_history),
        )

    async def _async_update_data(self) -> CoordinatorData:
        try:
            return await self.async_fetch(mode="logs", include_support=False)
        except Exception as err:
            raise UpdateFailed(str(err)) from err

    async def async_fetch(
        self, *, mode: str = "logs", include_support: bool = False
    ) -> CoordinatorData:
        """Run a fetch cycle (poll, button, or service)."""
        await self.hass.async_add_executor_job(self.reload_rules)
        self._publish_snapshot(
            status=STATUS_RUNNING,
            last_fetch=self.data.last_fetch,
            last_error=self.data.last_error,
            last_files=list(self.data.last_files),
        )
        self.async_set_updated_data(self.data)

        try:
            lines_by_source, files = await self._async_ssh_fetch(
                mode=mode, include_support=include_support
            )
            await self.hass.async_add_executor_job(
                lambda: rotate_log_dir(
                    self.out_dir,
                    max_files=self.retention_max_files,
                    max_age_days=self.retention_max_age_days,
                )
            )
            if self.enable_parsing:
                matches = match_lines(self._rules, lines_by_source)
                newly = apply_matches(self._alert_states, self._rules, matches)
                for match in newly:
                    self._fire_alert(match)
                self._match_count_total = sum(
                    s.match_count for s in self._alert_states.values()
                )
                clear_expired(self._alert_states)

            self._publish_snapshot(
                status=STATUS_OK,
                last_fetch=datetime.now(timezone.utc),
                last_error="",
                last_files=files,
            )
            return self.data
        except Exception as err:  # noqa: BLE001 — surface to UI sensor
            safe_err = sanitize_error(str(err), max_len=500)
            _LOGGER.exception("UniFi SSH fetch failed: %s", safe_err)
            self._publish_snapshot(
                status=STATUS_ERROR,
                last_fetch=datetime.now(timezone.utc),
                last_error=safe_err,
                last_files=list(self.data.last_files),
            )
            self.async_set_updated_data(self.data)
            raise

    def clear_alerts(self) -> None:
        """Clear all alert binary sensors."""
        clear_all(self._alert_states)
        self._publish_snapshot(
            status=self.data.status,
            last_fetch=self.data.last_fetch,
            last_error=self.data.last_error,
            last_files=list(self.data.last_files),
        )
        self.async_set_updated_data(self.data)

    def _fire_alert(self, match: RuleMatch) -> None:
        safe_message = redact_text(match.line, max_len=PUBLIC_SAMPLE_LEN)
        data = {
            "rule_id": match.rule_id,
            "name": match.name,
            "severity": match.severity,
            "source": match.source,
            "message": safe_message,
            "matched_at": match.matched_at.isoformat(),
        }
        self._alert_history.appendleft(dict(data))
        self.hass.bus.async_fire(EVENT_ALERT, data)
        for listener in list(self._alert_listeners):
            listener(data)

    def _want_source(self, mode: str, source: str, include_support: bool) -> bool:
        if mode == "all":
            if source == "support":
                return True
            enabled = {
                SOURCE_MESSAGES: self.fetch_messages,
                SOURCE_JOURNAL: self.fetch_journal,
                SOURCE_UNIFI: self.fetch_unifi,
            }
            return enabled.get(source, True)
        if mode == "support":
            return source == "support" or include_support
        if mode == "logs":
            if source == SOURCE_MESSAGES:
                return self.fetch_messages
            if source == SOURCE_JOURNAL:
                return self.fetch_journal
            if source == SOURCE_UNIFI:
                return self.fetch_unifi
            return False
        if mode == "messages":
            return source == SOURCE_MESSAGES and self.fetch_messages
        if mode == "journal":
            return source == SOURCE_JOURNAL and self.fetch_journal
        if mode == "unifi":
            return source == SOURCE_UNIFI and self.fetch_unifi
        return False

    async def _async_ssh_fetch(
        self, *, mode: str, include_support: bool
    ) -> tuple[dict[str, list[str]], list[str]]:
        """Fetch logs via asyncssh on the Home Assistant event loop."""
        # Import in executor — first import blocks (liboqs/fido2 file I/O).
        asyncssh = await self.hass.async_add_executor_job(load_asyncssh_blocking)

        out = self.out_dir
        await self.hass.async_add_executor_job(
            lambda: out.mkdir(parents=True, exist_ok=True)
        )

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        files: list[str] = []
        lines_by_source: dict[str, list[str]] = {
            SOURCE_MESSAGES: [],
            SOURCE_JOURNAL: [],
            SOURCE_UNIFI: [],
        }

        key_path, password, known_hosts, host = (
            self.key_path,
            self.password,
            self.known_hosts,
            self.host,
        )
        auth = await self.hass.async_add_executor_job(
            lambda: resolve_ssh_auth(key_path, password, key_must_exist=True)
        )
        known_arg = await self.hass.async_add_executor_job(
            lambda: resolve_known_hosts_arg(known_hosts, host)
        )
        kwargs: dict[str, Any] = {
            "host": self.host,
            "username": self.username,
            "known_hosts": known_arg,
            "connect_timeout": 20,
            **auth.to_connect_kwargs(),
        }

        want_support = include_support or mode in ("support", "all")

        async with asyncssh.connect(**kwargs) as conn:
            if self._want_source(mode, SOURCE_MESSAGES, include_support):
                text = await _remote_text(
                    conn,
                    f"tail -n {CURSOR_TAIL_LINES} /var/log/messages 2>/dev/null || true",
                )
                path = out / f"messages-{ts}.log"
                await self.hass.async_add_executor_job(
                    lambda p=path, t=text: p.write_text(
                        t, encoding="utf-8", errors="replace"
                    )
                )
                files.append(str(path))
                lines_by_source[SOURCE_MESSAGES] = incremental_new_lines(
                    self._cursors, SOURCE_MESSAGES, text.splitlines()
                )

            if self._want_source(mode, SOURCE_JOURNAL, include_support):
                text = await _remote_text(
                    conn,
                    f"journalctl -u unifi -n {CURSOR_TAIL_LINES} --no-pager 2>/dev/null || true",
                )
                path = out / f"journal-unifi-{ts}.txt"
                await self.hass.async_add_executor_job(
                    lambda p=path, t=text: p.write_text(
                        t, encoding="utf-8", errors="replace"
                    )
                )
                files.append(str(path))
                lines_by_source[SOURCE_JOURNAL] = incremental_new_lines(
                    self._cursors, SOURCE_JOURNAL, text.splitlines()
                )

            if self._want_source(mode, SOURCE_UNIFI, include_support):
                for remote, name in (
                    ("/var/log/unifi/server.log", "unifi-server"),
                    ("/var/log/unifi-core/unifi-core.log", "unifi-core"),
                ):
                    text = await _remote_text(
                        conn,
                        f"tail -n {CURSOR_TAIL_LINES} {remote} 2>/dev/null || true",
                    )
                    if not text.strip():
                        continue
                    path = out / f"{name}-{ts}.log"
                    await self.hass.async_add_executor_job(
                        lambda p=path, t=text: p.write_text(
                            t, encoding="utf-8", errors="replace"
                        )
                    )
                    files.append(str(path))
                    lines_by_source[SOURCE_UNIFI].extend(
                        incremental_new_lines(
                            self._cursors,
                            f"{SOURCE_UNIFI}:{name}",
                            text.splitlines(),
                        )
                    )

            if want_support:
                await self._async_fetch_support(conn, out, ts, files)

        return lines_by_source, files

    async def _async_fetch_support(
        self,
        conn: Any,
        out: Path,
        ts: str,
        files: list[str],
    ) -> None:
        """Download support bundle with mutex + cooldown to protect the console."""
        import asyncssh

        async with self._support_lock:
            now = datetime.now(timezone.utc)
            if self._last_support_at is not None:
                elapsed = (now - self._last_support_at).total_seconds()
                if elapsed < SUPPORT_COOLDOWN_SECONDS:
                    _LOGGER.warning(
                        "Support fetch skipped (cooldown %ss remaining)",
                        int(SUPPORT_COOLDOWN_SECONDS - elapsed),
                    )
                    return
            remote_path = f"/tmp/unifi-support-{ts}.tar.gz"
            await conn.run(f"ubnt-make-support-file {remote_path}", check=False)
            local = out / f"support-{ts}.tar.gz"

            try:
                async with conn.start_sftp_client() as sftp:
                    await sftp.get(remote_path, str(local))
                files.append(str(local))
                self._last_support_at = now
            except (OSError, asyncssh.Error) as err:
                _LOGGER.warning(
                    "Support file download failed: %s", sanitize_error(str(err))
                )
            await conn.run(f"rm -f {remote_path}", check=False)


async def _remote_text(conn: Any, command: str) -> str:
    """Run a remote command and return stdout as str."""
    result = await conn.run(command, check=False)
    stdout = result.stdout or ""
    if isinstance(stdout, bytes):
        return stdout.decode("utf-8", errors="replace")
    return str(stdout)
