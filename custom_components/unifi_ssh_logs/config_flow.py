"""Config flow for UniFi SSH Logs (SSH key authorize dialog)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .auth import (
    AuthConfigError,
    generate_key,
    public_key_of,
    resolve_known_hosts_arg,
    resolve_ssh_auth,
)
from .const import (
    CONF_CUSTOM_RULES_PATH,
    CONF_ENABLE_PARSING,
    CONF_FETCH_JOURNAL,
    CONF_FETCH_MESSAGES,
    CONF_FETCH_UNIFI,
    CONF_KEY_PATH,
    CONF_KNOWN_HOSTS,
    CONF_OUT_DIR,
    CONF_PRIVATE_KEY,
    CONF_RETENTION_MAX_AGE_DAYS,
    CONF_RETENTION_MAX_FILES,
    CONF_SCAN_INTERVAL,
    DEFAULT_CUSTOM_RULES_PATH,
    DEFAULT_HOST,
    DEFAULT_KNOWN_HOSTS,
    DEFAULT_OUT_DIR,
    DEFAULT_RETENTION_MAX_AGE_DAYS,
    DEFAULT_RETENTION_MAX_FILES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    MIN_SCAN_SECONDS,
)
from .coordinator import load_asyncssh_blocking
from .paths import PathConfigError, require_under_config, resolve_under_config

_LOGGER = logging.getLogger(__name__)


def _validate_paths(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Ensure configurable paths stay under HA config dir."""
    config_dir = hass.config.config_dir
    require_under_config(
        data.get(CONF_KNOWN_HOSTS, DEFAULT_KNOWN_HOSTS), config_dir
    )
    require_under_config(data.get(CONF_OUT_DIR, DEFAULT_OUT_DIR), config_dir)
    require_under_config(
        data.get(CONF_CUSTOM_RULES_PATH, DEFAULT_CUSTOM_RULES_PATH), config_dir
    )
    key = (data.get(CONF_KEY_PATH) or "").strip()
    if key:
        require_under_config(key, config_dir)


async def _probe_ssh(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Attempt one SSH connection with the given credentials."""
    asyncssh = await hass.async_add_executor_job(load_asyncssh_blocking)

    def _resolve() -> tuple[Any, str | None]:
        _validate_paths(hass, data)
        key_path = (data.get(CONF_KEY_PATH) or "").strip() or None
        if key_path:
            resolved = resolve_under_config(
                key_path, hass.config.config_dir, allow_empty=True
            )
            key_path = str(resolved) if resolved else key_path
        auth = resolve_ssh_auth(
            key_path,
            data.get(CONF_PASSWORD),
            private_key=data.get(CONF_PRIVATE_KEY),
            key_must_exist=bool(key_path),
        )
        known = resolve_known_hosts_arg(
            data.get(CONF_KNOWN_HOSTS, DEFAULT_KNOWN_HOSTS),
            data[CONF_HOST],
        )
        return auth, known

    try:
        auth, known_arg = await hass.async_add_executor_job(_resolve)
    except PathConfigError as err:
        raise ValueError(str(err) or "path_outside_config") from err
    except AuthConfigError as err:
        raise ValueError(str(err)) from err

    kwargs: dict[str, Any] = {
        "host": data[CONF_HOST],
        "username": data.get(CONF_USERNAME, DEFAULT_USERNAME),
        "known_hosts": known_arg,
        "connect_timeout": 20,
        **auth.to_connect_kwargs(asyncssh),
    }
    try:
        async with asyncssh.connect(**kwargs) as conn:
            await conn.run("true", check=False)
    except asyncssh.PermissionDenied as err:
        raise ValueError("invalid_auth") from err
    except (OSError, asyncssh.Error, TimeoutError) as err:
        _LOGGER.debug("SSH probe failed: %s", err)
        raise ValueError("cannot_connect") from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UniFi SSH Logs."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Host, user, optional private key (or generate) / password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            key = (user_input.get(CONF_PRIVATE_KEY) or "").strip()
            password = user_input.get(CONF_PASSWORD) or None
            try:
                if key:
                    key = key if key.endswith("\n") else key + "\n"
                    await self.hass.async_add_executor_job(public_key_of, key)
                elif not password:
                    key, _pub = await self.hass.async_add_executor_job(generate_key)
            except Exception:  # noqa: BLE001 — asyncssh key parse errors
                errors[CONF_PRIVATE_KEY] = "invalid_key"
            else:
                self._data = {
                    CONF_HOST: user_input[CONF_HOST].strip(),
                    CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                    CONF_KNOWN_HOSTS: DEFAULT_KNOWN_HOSTS,
                    CONF_OUT_DIR: DEFAULT_OUT_DIR,
                    CONF_SCAN_INTERVAL: int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                    CONF_ENABLE_PARSING: True,
                    CONF_CUSTOM_RULES_PATH: DEFAULT_CUSTOM_RULES_PATH,
                    CONF_FETCH_MESSAGES: True,
                    CONF_FETCH_JOURNAL: True,
                    CONF_FETCH_UNIFI: True,
                }
                if key:
                    self._data[CONF_PRIVATE_KEY] = key
                if password:
                    self._data[CONF_PASSWORD] = password
                # Password-only: skip authorize (no public key to show).
                if key:
                    return await self.async_step_authorize()
                return await self.async_step_connect()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                vol.Optional(CONF_PRIVATE_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT, multiline=True
                    )
                ),
                vol.Optional(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    def _authorize_form(self, errors: dict[str, str] | None = None) -> FlowResult:
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_USERNAME): str,
            }
        )
        return self.async_show_form(
            step_id="authorize",
            data_schema=self.add_suggested_values_to_schema(schema, self._data),
            description_placeholders={
                "public_key": public_key_of(self._data[CONF_PRIVATE_KEY]),
            },
            errors=errors or {},
        )

    async def async_step_authorize(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show public key for Console authorized_keys; then probe."""
        if user_input is None:
            return self._authorize_form()
        self._data.update(
            {
                CONF_HOST: user_input[CONF_HOST].strip(),
                CONF_USERNAME: user_input[CONF_USERNAME].strip(),
            }
        )
        return await self.async_step_connect()

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Probe SSH and create the config entry."""
        del user_input  # unused; invoked from authorize/user
        errors: dict[str, str] = {}
        await self.async_set_unique_id(f"{self._data[CONF_HOST]}")
        self._abort_if_unique_id_configured()
        try:
            await _probe_ssh(self.hass, self._data)
        except ValueError as err:
            code = str(err)
            errors["base"] = (
                code
                if code
                in (
                    "invalid_auth",
                    "cannot_connect",
                    "key_missing",
                    "auth_missing",
                    "path_outside_config",
                )
                else "unknown"
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected SSH probe error")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(
                title=f"UniFi SSH ({self._data[CONF_HOST]})",
                data=self._data,
            )

        if CONF_PRIVATE_KEY in self._data:
            return self._authorize_form(errors)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._data.get(CONF_HOST)): str,
                    vol.Required(
                        CONF_USERNAME, default=self._data.get(CONF_USERNAME)
                    ): str,
                    vol.Optional(CONF_PRIVATE_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT, multiline=True
                        )
                    ),
                    vol.Optional(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any] | None) -> FlowResult:
        """Import from configuration.yaml (supports !secret for password)."""
        data = dict(import_data or {})
        await self.async_set_unique_id(f"{data[CONF_HOST]}")
        self._abort_if_unique_id_configured()
        self._data = {
            CONF_HOST: data[CONF_HOST],
            CONF_USERNAME: data.get(CONF_USERNAME, DEFAULT_USERNAME),
            CONF_KNOWN_HOSTS: data.get(CONF_KNOWN_HOSTS, DEFAULT_KNOWN_HOSTS),
            CONF_OUT_DIR: data.get(CONF_OUT_DIR, DEFAULT_OUT_DIR),
            CONF_SCAN_INTERVAL: data.get(
                CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds())
            ),
            CONF_ENABLE_PARSING: data.get(CONF_ENABLE_PARSING, True),
            CONF_CUSTOM_RULES_PATH: data.get(
                CONF_CUSTOM_RULES_PATH, DEFAULT_CUSTOM_RULES_PATH
            ),
            CONF_FETCH_MESSAGES: data.get(CONF_FETCH_MESSAGES, True),
            CONF_FETCH_JOURNAL: data.get(CONF_FETCH_JOURNAL, True),
            CONF_FETCH_UNIFI: data.get(CONF_FETCH_UNIFI, True),
        }
        if data.get(CONF_PRIVATE_KEY):
            self._data[CONF_PRIVATE_KEY] = data[CONF_PRIVATE_KEY]
        if data.get(CONF_KEY_PATH):
            self._data[CONF_KEY_PATH] = data[CONF_KEY_PATH]
        if data.get(CONF_PASSWORD):
            self._data[CONF_PASSWORD] = data[CONF_PASSWORD]
        try:
            await _probe_ssh(self.hass, self._data)
        except ValueError as err:
            return self.async_abort(reason=str(err) or "unknown")
        except Exception:  # noqa: BLE001
            return self.async_abort(reason="unknown")
        return self.async_create_entry(
            title=f"UniFi SSH ({self._data[CONF_HOST]})",
            data=self._data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options (paths, polling, optional key_path / password)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(user_input)
            if not data.get(CONF_PASSWORD):
                data.pop(CONF_PASSWORD, None)
                existing = {
                    **self.config_entry.data,
                    **self.config_entry.options,
                }.get(CONF_PASSWORD)
                if existing:
                    data[CONF_PASSWORD] = existing
            try:
                await self.hass.async_add_executor_job(
                    _validate_paths, self.hass, data
                )
                merged = {**self.config_entry.data, **data}
                key = (data.get(CONF_KEY_PATH) or "").strip()
                if (
                    key
                    or data.get(CONF_PASSWORD)
                    or merged.get(CONF_PRIVATE_KEY)
                ):
                    resolved = (
                        resolve_under_config(
                            key, self.hass.config.config_dir, allow_empty=True
                        )
                        if key
                        else None
                    )
                    resolve_ssh_auth(
                        str(resolved) if resolved else key or None,
                        data.get(CONF_PASSWORD) or merged.get(CONF_PASSWORD),
                        private_key=merged.get(CONF_PRIVATE_KEY),
                        key_must_exist=bool(key),
                    )
            except PathConfigError:
                errors["base"] = "path_outside_config"
            except AuthConfigError as err:
                code = str(err)
                errors["base"] = (
                    code if code in ("key_missing", "auth_missing") else "unknown"
                )
            else:
                return self.async_create_entry(title="", data=data)

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=int(
                        current.get(
                            CONF_SCAN_INTERVAL,
                            int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                        )
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_SECONDS)),
                vol.Optional(
                    CONF_ENABLE_PARSING,
                    default=bool(current.get(CONF_ENABLE_PARSING, True)),
                ): bool,
                vol.Optional(
                    CONF_FETCH_MESSAGES,
                    default=bool(current.get(CONF_FETCH_MESSAGES, True)),
                ): bool,
                vol.Optional(
                    CONF_FETCH_JOURNAL,
                    default=bool(current.get(CONF_FETCH_JOURNAL, True)),
                ): bool,
                vol.Optional(
                    CONF_FETCH_UNIFI,
                    default=bool(current.get(CONF_FETCH_UNIFI, True)),
                ): bool,
                vol.Optional(
                    CONF_RETENTION_MAX_FILES,
                    default=int(
                        current.get(
                            CONF_RETENTION_MAX_FILES, DEFAULT_RETENTION_MAX_FILES
                        )
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
                vol.Optional(
                    CONF_RETENTION_MAX_AGE_DAYS,
                    default=int(
                        current.get(
                            CONF_RETENTION_MAX_AGE_DAYS,
                            DEFAULT_RETENTION_MAX_AGE_DAYS,
                        )
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                vol.Optional(
                    CONF_CUSTOM_RULES_PATH,
                    default=current.get(
                        CONF_CUSTOM_RULES_PATH, DEFAULT_CUSTOM_RULES_PATH
                    ),
                ): str,
                vol.Optional(
                    CONF_OUT_DIR,
                    default=current.get(CONF_OUT_DIR, DEFAULT_OUT_DIR),
                ): str,
                vol.Optional(
                    CONF_KEY_PATH, default=current.get(CONF_KEY_PATH, "")
                ): str,
                vol.Optional(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
