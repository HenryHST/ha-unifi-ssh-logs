"""Authenticated HTTP API for listing/downloading UniFi SSH log files."""

from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .coordinator import UnifiSshLogsCoordinator
from .export import export_file_bytes, list_log_files, resolve_log_file
from .paths import PathConfigError

_LOGGER = logging.getLogger(__name__)

_VIEWS_REGISTERED = False


def _coordinator(hass: HomeAssistant, entry_id: str | None) -> UnifiSshLogsCoordinator:
    coordinators: dict[str, UnifiSshLogsCoordinator] = hass.data.get(DOMAIN, {})
    if not coordinators:
        raise KeyError("no_entry")
    if entry_id:
        if entry_id not in coordinators:
            raise KeyError("unknown_entry")
        return coordinators[entry_id]
    return next(iter(coordinators.values()))


class UnifiSshLogsFilesView(HomeAssistantView):
    """List log artifacts for an integration entry."""

    url = "/api/unifi_ssh_logs/files"
    name = "api:unifi_ssh_logs:files"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id")
        try:
            coordinator = _coordinator(hass, entry_id)
        except KeyError as err:
            return self.json({"error": str(err)}, status=404)
        try:
            out_dir = coordinator.out_dir
        except PathConfigError:
            return self.json({"error": "path_outside_config"}, status=400)

        files = await hass.async_add_executor_job(list_log_files, out_dir)
        return self.json(
            {
                "entry_id": coordinator.entry.entry_id,
                "out_dir": str(out_dir),
                "polling_enabled": coordinator.polling_enabled,
                "files": files,
            }
        )


class UnifiSshLogsDownloadView(HomeAssistantView):
    """Download a single log artifact as txt, csv, or gzip."""

    url = "/api/unifi_ssh_logs/download"
    name = "api:unifi_ssh_logs:download"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id")
        name = request.query.get("name") or ""
        fmt = request.query.get("format") or "txt"
        try:
            coordinator = _coordinator(hass, entry_id)
        except KeyError as err:
            return self.json({"error": str(err)}, status=404)
        try:
            out_dir = coordinator.out_dir
        except PathConfigError:
            return self.json({"error": "path_outside_config"}, status=400)

        def _load() -> tuple[bytes, str, str]:
            path = resolve_log_file(out_dir, name)
            return export_file_bytes(path, fmt)

        try:
            body, content_type, filename = await hass.async_add_executor_job(_load)
        except ValueError as err:
            code = str(err)
            status = 404 if code == "not_found" else 400
            return self.json({"error": code}, status=status)
        except OSError as err:
            _LOGGER.warning("Download failed for %s: %s", name, err)
            return self.json({"error": "read_failed"}, status=500)

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        # aiohttp raises if content_type contains "charset="; pass charset= separately.
        ct_main = content_type.split(";", 1)[0].strip()
        use_charset = ct_main.startswith("text/")
        try:
            if use_charset:
                return web.Response(
                    body=body,
                    content_type=ct_main,
                    charset="utf-8",
                    headers=headers,
                )
            return web.Response(body=body, content_type=ct_main, headers=headers)
        except Exception:
            _LOGGER.exception("Failed building download response for %s", name)
            return self.json({"error": "response_build_failed"}, status=500)


@callback
def async_register_http_views(hass: HomeAssistant) -> None:
    """Register API views once."""
    global _VIEWS_REGISTERED  # noqa: PLW0603
    if _VIEWS_REGISTERED:
        return
    hass.http.register_view(UnifiSshLogsFilesView())
    hass.http.register_view(UnifiSshLogsDownloadView())
    _VIEWS_REGISTERED = True
