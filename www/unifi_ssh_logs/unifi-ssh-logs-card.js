/**
 * Lovelace card: list UniFi SSH log files and download as TXT/CSV.
 * Resource: /local/unifi_ssh_logs/unifi-ssh-logs-card.js?v=0.4.1 (type: module)
 * Card type: custom:unifi-ssh-logs-card
 */
class UnifiSshLogsCard extends HTMLElement {
  static getStubConfig() {
    return { entry_id: "", title: "UniFi SSH Logs" };
  }

  setConfig(config) {
    this._config = { title: "UniFi SSH Logs", entry_id: "", ...config };
    this._files = [];
    this._meta = {};
    this._error = "";
    this._renderShell();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loadedOnce) {
      this._loadedOnce = true;
      this._refresh();
    }
  }

  getCardSize() {
    return 4;
  }

  _qs() {
    const id = (this._config && this._config.entry_id) || "";
    return id ? `?entry_id=${encodeURIComponent(id)}` : "";
  }

  async _refresh() {
    if (!this._hass) return;
    this._error = "";
    try {
      this._meta = await this._hass.callApi("GET", `unifi_ssh_logs/files${this._qs()}`);
      this._files = this._meta.files || [];
    } catch (err) {
      this._error = (err && err.message) || String(err);
      this._files = [];
    }
    this._renderBody();
  }

  _downloadUrl(name, format) {
    const params = new URLSearchParams();
    if (this._config.entry_id) params.set("entry_id", this._config.entry_id);
    params.set("name", name);
    params.set("format", format);
    return `/api/unifi_ssh_logs/download?${params.toString()}`;
  }

  _triggerBlobDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const doc = this.ownerDocument || document;
    // Safari drops <a download> after async fetch; blob tab still has auth'd bytes.
    const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
    if (isSafari) {
      const opened = window.open(url, "_blank", "noopener,noreferrer");
      if (!opened) {
        throw new Error("Popup blocked — allow popups for this site to download");
      }
    } else {
      const a = doc.createElement("a");
      a.href = url;
      a.download = filename;
      a.rel = "noopener";
      a.style.display = "none";
      doc.body.appendChild(a);
      a.click();
      a.remove();
    }
    // Keep blob URL alive briefly (Safari tab load / download start).
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    return url;
  }

  async _download(name, format) {
    if (!this._hass) return;
    // Relative /api/... only — fetchWithAuth already applies hassUrl.
    const href = this._downloadUrl(name, format);
    const filename =
      format === "csv" && !name.endsWith(".tar.gz")
        ? name.replace(/\.(log|txt)$/i, ".csv")
        : name;
    try {
      const resp = await this._hass.fetchWithAuth(href);
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      this._triggerBlobDownload(blob, filename);
      this._error = "";
      this._renderBody();
    } catch (err) {
      // Never window.open(api URL) — Safari/tabs have no HA auth → 401 + ban.
      this._error = `Download failed: ${err && err.message ? err.message : err}`;
      this._renderBody();
    }
  }

  _fmtSize(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }

  _renderShell() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 12px 16px 16px; }
        .header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
        h2 { margin: 0; font-size: 1.1rem; font-weight: 500; }
        .muted { color: var(--secondary-text-color); font-size: 0.85rem; }
        .warn { color: var(--warning-color, #f4a261); font-size: 0.85rem; margin: 0 0 8px; }
        .err { color: var(--error-color); font-size: 0.85rem; margin: 0 0 8px; }
        table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
        th, td { text-align: left; padding: 6px 4px; border-bottom: 1px solid var(--divider-color); vertical-align: middle; }
        th { font-weight: 500; color: var(--secondary-text-color); }
        .name { word-break: break-all; }
        .actions { display: flex; gap: 6px; flex-wrap: wrap; }
        button {
          cursor: pointer; border: 1px solid var(--divider-color);
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          border-radius: 4px; padding: 4px 8px; font: inherit;
        }
        button:hover { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        button:disabled { opacity: 0.45; cursor: not-allowed; }
        .toolbar button { margin-left: 4px; }
      </style>
      <ha-card>
        <div class="header">
          <h2 class="title"></h2>
          <div class="toolbar">
            <button type="button" class="refresh">Refresh</button>
          </div>
        </div>
        <p class="muted status"></p>
        <p class="warn polling-hint" hidden></p>
        <p class="err error" hidden></p>
        <div class="body"></div>
      </ha-card>
    `;
    this.shadowRoot.querySelector(".refresh").addEventListener("click", () => this._refresh());
    this.shadowRoot.querySelector(".title").textContent =
      (this._config && this._config.title) || "UniFi SSH Logs";
    this._renderBody();
  }

  _renderBody() {
    if (!this.shadowRoot) return;
    const status = this.shadowRoot.querySelector(".status");
    const hint = this.shadowRoot.querySelector(".polling-hint");
    const err = this.shadowRoot.querySelector(".error");
    const body = this.shadowRoot.querySelector(".body");

    status.textContent = this._meta.out_dir
      ? `Directory: ${this._meta.out_dir}`
      : "Log files under /config/unifi_logs/";

    if (this._meta.polling_enabled === false) {
      hint.hidden = false;
      hint.textContent = "Polling is off — list may be stale until you fetch manually.";
    } else {
      hint.hidden = true;
    }

    if (this._error) {
      err.hidden = false;
      err.textContent = this._error;
    } else {
      err.hidden = true;
    }

    if (!this._files.length) {
      body.innerHTML = `<p class="muted">No log files found.</p>`;
      return;
    }

    const rows = this._files
      .map((f) => {
        const csvDisabled = f.text ? "" : "disabled";
        return `<tr>
          <td class="name">${this._esc(f.name)}</td>
          <td>${this._fmtSize(f.size || 0)}</td>
          <td class="actions">
            <button type="button" data-name="${this._esc(f.name)}" data-fmt="txt">TXT</button>
            <button type="button" data-name="${this._esc(f.name)}" data-fmt="csv" ${csvDisabled}>CSV</button>
          </td>
        </tr>`;
      })
      .join("");

    body.innerHTML = `
      <table>
        <thead><tr><th>File</th><th>Size</th><th>Download</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
    body.querySelectorAll("button[data-name]").forEach((btn) => {
      btn.addEventListener("click", () =>
        this._download(btn.getAttribute("data-name"), btn.getAttribute("data-fmt"))
      );
    });
  }

  _esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }
}

customElements.define("unifi-ssh-logs-card", UnifiSshLogsCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "unifi-ssh-logs-card",
  name: "UniFi SSH Logs",
  description: "List fetched UniFi log files and download as TXT or CSV",
});
