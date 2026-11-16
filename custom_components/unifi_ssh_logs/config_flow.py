"""Config flow for UniFi SSH Logs."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .auth import AuthConfigError, resolve_ssh_auth
from .const import (
    CONF_CUSTOM_RULES_PATH,
    CONF_ENABLE_PARSING,
    CONF_FETCH_JOURNAL,
    CONF_FETCH_MESSAGES,
    CONF_FETCH_UNIFI,
    CONF_KEY_PATH,
    CONF_KNOWN_HOSTS,
    CONF_OUT_DIR,
    CONF_RETENTION_MAX_AGE_DAYS,
    CONF_RETENTION_MAX_FILES,
    CONF_SCAN_INTERVAL,
    DEFAULT_CUSTOM_RULES_PATH,
    DEFAULT_HOST,
    DEFAULT_KEY_PATH,
    DEFAULT_KNOWN_HOSTS,
    DEFAULT_OUT_DIR,
    DEFAULT_RETENTION_MAX_AGE_DAYS,
    DEFAULT_RETENTION_MAX_FILES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    MIN_SCAN_SECONDS,
)
from .paths import PathConfigError, require_under_config, resolve_under_config

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Optional(CONF_KEY_PATH, default=DEFAULT_KEY_PATH): str,
        vol.Optional(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_KNOWN_HOSTS, default=DEFAULT_KNOWN_HOSTS): str,
        vol.Optional(CONF_OUT_DIR, default=DEFAULT_OUT_DIR): str,
        vol.Optional(
            CONF_SCAN_INTERVAL, default=int(DEFAULT_SCAN_INTERVAL.total_seconds())
        ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_SECONDS)),
        vol.Optional(CONF_ENABLE_PARSING, default=True): bool,
        vol.Optional(CONF_CUSTOM_RULES_PATH, default=DEFAULT_CUSTOM_RULES_PATH): str,
        vol.Optional(CONF_FETCH_MESSAGES, default=True): bool,
        vol.Optional(CONF_FETCH_JOURNAL, default=True): bool,
        vol.Optional(CONF_FETCH_UNIFI, default=True): bool,
    }
)


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


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate key/password and path allowlist (host reachability deferred)."""

    def _check() -> None:
        _validate_paths(hass, data)
        key = data.get(CONF_KEY_PATH)
        if key:
            # Resolve for existence check under allowlist
            resolved = resolve_under_config(key, hass.config.config_dir, allow_empty=True)
            key = str(resolved) if resolved else key
        resolve_ssh_auth(
            key,
            data.get(CONF_PASSWORD),
            key_must_exist=True,
        )

    try:
        await hass.async_add_executor_job(_check)
    except PathConfigError as err:
        raise ValueError(str(err) or "path_outside_config") from err
    except AuthConfigError as err:
        raise ValueError(str(err)) from err
    return {"title": f"UniFi SSH ({data[CONF_HOST]})"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UniFi SSH Logs."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}")
            self._abort_if_unique_id_configured()
            try:
                info = await _validate_input(self.hass, user_input)
            except ValueError as err:
                code = str(err)
                errors["base"] = (
                    code
                    if code
                    in ("key_missing", "auth_missing", "path_outside_config")
                    else "unknown"
                )
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Import from configuration.yaml (supports !secret for password)."""
        await self.async_set_unique_id(f"{import_data[CONF_HOST]}")
        self._abort_if_unique_id_configured()
        try:
            info = await _validate_input(self.hass, import_data)
        except ValueError as err:
            return self.async_abort(reason=str(err) or "unknown")
        except Exception:  # noqa: BLE001
            return self.async_abort(reason="unknown")
        return self.async_create_entry(title=info["title"], data=import_data)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

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
                key = (data.get(CONF_KEY_PATH) or "").strip()
                if key or data.get(CONF_PASSWORD):
                    resolved = (
                        resolve_under_config(
                            key, self.hass.config.config_dir, allow_empty=True
                        )
                        if key
                        else None
                    )
                    resolve_ssh_auth(
                        str(resolved) if resolved else key or None,
                        data.get(CONF_PASSWORD),
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
                vol.Optional(CONF_KEY_PATH, default=current.get(CONF_KEY_PATH, "")): str,
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
