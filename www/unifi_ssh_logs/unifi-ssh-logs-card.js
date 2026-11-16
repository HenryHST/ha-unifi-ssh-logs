/**
 * Lovelace card: UniFi SSH log files with month calendar filter + TXT/CSV download.
 * Resource: /local/unifi_ssh_logs/unifi-ssh-logs-card.js?v=0.5.2 (type: module)
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
    this._selectedDate = null;
    const now = new Date();
    this._viewMonth = new Date(now.getFullYear(), now.getMonth(), 1);
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
    return 7;
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

  /** UTC ISO mtime → local calendar date key YYYY-MM-DD. */
  _localDateKey(isoMtime) {
    if (!isoMtime) return null;
    const d = new Date(isoMtime);
    if (Number.isNaN(d.getTime())) return null;
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  _datesWithLogs() {
    const set = new Set();
    for (const f of this._files) {
      const key = this._localDateKey(f.mtime);
      if (key) set.add(key);
    }
    return set;
  }

  _filteredFiles() {
    if (!this._selectedDate) return this._files;
    return this._files.filter(
      (f) => this._localDateKey(f.mtime) === this._selectedDate
    );
  }

  _monthLabel(d) {
    try {
      return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    } catch {
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    }
  }

  _shiftMonth(delta) {
    const y = this._viewMonth.getFullYear();
    const m = this._viewMonth.getMonth() + delta;
    this._viewMonth = new Date(y, m, 1);
    this._renderBody();
  }

  _selectDate(key) {
    this._selectedDate = this._selectedDate === key ? null : key;
    this._renderBody();
  }

  _clearFilter() {
    this._selectedDate = null;
    this._renderBody();
  }

  _weekdayLabels() {
    // 2024-01-01 is a Monday — labels Mon…Sun for Monday-first grid.
    const labels = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(2024, 0, 1 + i);
      try {
        labels.push(d.toLocaleDateString(undefined, { weekday: "short" }).slice(0, 2));
      } catch {
        labels.push(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"][i]);
      }
    }
    return labels;
  }

  _renderCalendarHtml(datesWithLogs) {
    const year = this._viewMonth.getFullYear();
    const month = this._viewMonth.getMonth();
    const first = new Date(year, month, 1);
    // Monday-first: JS getDay() Sun=0 … Sat=6 → Mon=0 … Sun=6
    const startPad = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const weekdays = this._weekdayLabels()
      .map((w) => `<span>${this._esc(w)}</span>`)
      .join("");

    const cells = [];
    for (let i = 0; i < startPad; i++) {
      cells.push(`<button type="button" class="cal-day muted" disabled tabindex="-1"></button>`);
    }
    for (let day = 1; day <= daysInMonth; day++) {
      const key = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const hasLogs = datesWithLogs.has(key);
      const selected = this._selectedDate === key;
      const cls = ["cal-day"];
      if (hasLogs) cls.push("has-logs");
      if (selected) cls.push("selected");
      // Avoid nested quotes inside the template — they can swallow the HTML attr closing quote.
      const pressed = selected ? "true" : "false";
      const attrs = hasLogs
        ? `data-date="${key}" aria-pressed="${pressed}"`
        : `disabled tabindex="-1"`;
      cells.push(
        `<button type="button" class="${cls.join(" ")}" ${attrs}>${day}</button>`
      );
    }

    const filtered = this._filteredFiles();
    const totalSize = filtered.reduce((sum, f) => sum + (f.size || 0), 0);
    let detailTitle = "All days";
    let detailSub = "Select a marked day to filter";
    if (this._selectedDate) {
      detailTitle = this._selectedDate;
      detailSub = `${filtered.length} file${filtered.length === 1 ? "" : "s"} · ${this._fmtSize(totalSize)}`;
    } else {
      detailSub = `${this._files.length} file${this._files.length === 1 ? "" : "s"} · ${this._fmtSize(
        this._files.reduce((s, f) => s + (f.size || 0), 0)
      )}`;
    }

    return `
      <aside class="cal-aside" aria-label="Log calendar">
        <article class="cal-card" data-sel-theme="a">
          <div class="cal-head">
            <button type="button" class="cal-nav" data-cal-nav="-1" aria-label="Previous month">‹</button>
            <h3 class="cal-month">${this._esc(this._monthLabel(this._viewMonth))}</h3>
            <button type="button" class="cal-nav" data-cal-nav="1" aria-label="Next month">›</button>
          </div>
          <div class="cal-weekdays">${weekdays}</div>
          <div class="cal-grid" role="grid">${cells.join("")}</div>
          <div class="cal-legend">
            <span><i class="cal-dot" aria-hidden="true"></i> Logs</span>
            <span><i class="cal-dot sel" aria-hidden="true"></i> Selected</span>
          </div>
        </article>
        <div class="cal-detail">
          <div>
            <strong class="cal-detail-title">${this._esc(detailTitle)}</strong>
            <p class="muted cal-detail-sub">${this._esc(detailSub)}</p>
          </div>
          <button type="button" class="clear-filter" ${this._selectedDate ? "" : "disabled"}>All</button>
        </div>
      </aside>
    `;
  }

  _renderFileTable(files) {
    if (!files.length) {
      const empty = this._selectedDate
        ? "No logs on this day."
        : "No log files found.";
      return `<p class="muted">${empty}</p>`;
    }
    const rows = files
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
    return `
      <table>
        <thead><tr><th>File</th><th>Size</th><th>Download</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  _renderShell() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; container-type: inline-size; }
        ha-card { padding: 12px 16px 16px; }
        .header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
        h2 { margin: 0; font-size: 1.1rem; font-weight: 500; color: var(--primary-text-color); }
        .muted { color: var(--secondary-text-color); font-size: 0.85rem; }
        .warn { color: var(--warning-color, #f4a261); font-size: 0.85rem; margin: 0 0 8px; }
        .err { color: var(--error-color); font-size: 0.85rem; margin: 0 0 8px; }
        .layout {
          display: flex;
          flex-direction: column;
          gap: 12px;
          align-items: stretch;
        }
        .cal-aside {
          width: 100%;
          max-width: 320px;
          align-self: center;
        }
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
        button:hover:not(:disabled) { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        button:disabled { opacity: 0.45; cursor: not-allowed; }
        .toolbar button { margin-left: 4px; }

        /* Podcraft Restore-style calendar */
        .cal-aside { display: flex; flex-direction: column; gap: 10px; }
        .cal-card {
          background: #f4f2fb;
          color: #2d3142;
          border-radius: 18px;
          padding: 1rem 0.9rem 1.05rem;
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
        }
        .cal-head {
          display: grid;
          grid-template-columns: 36px 1fr 36px;
          align-items: center;
          margin-bottom: 0.75rem;
        }
        .cal-month {
          margin: 0;
          text-align: center;
          font-size: 1rem;
          font-weight: 600;
          color: #3a3f51;
          text-transform: none;
          letter-spacing: 0;
        }
        .cal-nav {
          width: 36px; height: 36px; border: 0; border-radius: 10px;
          background: transparent; color: #f0a06a; font-size: 1.15rem;
          display: grid; place-items: center; padding: 0;
        }
        .cal-nav:hover:not(:disabled) {
          background: rgba(240, 160, 106, 0.15);
          color: #f0a06a;
        }
        .cal-weekdays, .cal-grid {
          display: grid;
          gap: 0.2rem;
          grid-template-columns: repeat(7, minmax(0, 1fr));
          align-items: center;
          justify-items: center;
        }
        .cal-weekdays {
          margin-bottom: 0.2rem;
          font-size: 0.72rem;
          color: #9aa0b4;
          text-transform: lowercase;
        }
        .cal-weekdays > span {
          display: grid; place-items: center;
          width: 100%; max-width: 2.55rem; aspect-ratio: 1;
        }
        .cal-day {
          aspect-ratio: 1; border: 0; background: transparent; border-radius: 50%;
          font: inherit; font-size: 0.88rem; color: #3a3f51;
          display: grid; place-items: center; cursor: default;
          width: 100%; max-width: 2.55rem; min-height: 0; box-sizing: border-box;
          line-height: 1; padding: 0;
        }
        .cal-day.muted { color: #c2c6d4; }
        .cal-day.has-logs {
          cursor: pointer;
          box-shadow: inset 0 0 0 2px #f0a06a;
        }
        .cal-day.has-logs.selected {
          font-weight: 700;
          color: #fff;
          box-shadow: 0 0 0 2px #99f6e4;
          background: #0f766e;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 0.18rem;
          padding: 0.2rem 0 0.28rem;
        }
        .cal-day.has-logs.selected::after {
          content: "";
          width: 5px; height: 5px; border-radius: 50%;
          background: rgba(255, 255, 255, 0.95);
          flex-shrink: 0;
        }
        .cal-day.has-logs:hover:not(.selected):not(:disabled) {
          background: rgba(240, 160, 106, 0.12);
          color: #3a3f51;
        }
        .cal-legend {
          margin-top: 0.75rem;
          display: flex; flex-wrap: wrap; gap: 0.65rem;
          font-size: 0.72rem; color: #6b7285;
        }
        .cal-legend span { display: inline-flex; align-items: center; gap: 0.35rem; }
        .cal-dot {
          width: 10px; height: 10px; border-radius: 50%;
          box-shadow: inset 0 0 0 2px #f0a06a;
          display: inline-block;
        }
        .cal-dot.sel { box-shadow: none; background: #0f766e; }
        .cal-detail {
          display: flex; align-items: center; justify-content: space-between; gap: 8px;
          padding: 8px 4px 0;
        }
        .cal-detail-title { font-size: 0.95rem; color: var(--primary-text-color); }
        .cal-detail-sub { margin: 2px 0 0; }
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

  _bindBodyEvents(body) {
    body.querySelectorAll("[data-cal-nav]").forEach((btn) => {
      btn.addEventListener("click", () =>
        this._shiftMonth(Number(btn.getAttribute("data-cal-nav")))
      );
    });
    body.querySelectorAll(".cal-day.has-logs[data-date]").forEach((btn) => {
      btn.addEventListener("click", () => this._selectDate(btn.getAttribute("data-date")));
    });
    const clear = body.querySelector(".clear-filter");
    if (clear) clear.addEventListener("click", () => this._clearFilter());
    body.querySelectorAll("button[data-name]").forEach((btn) => {
      btn.addEventListener("click", () =>
        this._download(btn.getAttribute("data-name"), btn.getAttribute("data-fmt"))
      );
    });
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

    const datesWithLogs = this._datesWithLogs();
    const files = this._filteredFiles();
    body.innerHTML = `
      <div class="layout">
        ${this._renderCalendarHtml(datesWithLogs)}
        <div class="list-pane">${this._renderFileTable(files)}</div>
      </div>
    `;
    this._bindBodyEvents(body);
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
  description: "Calendar-filtered UniFi log files with TXT/CSV download",
});
