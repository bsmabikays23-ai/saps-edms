(function () {
  "use strict";

  function q(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  function showResult(el, msg, kind) {
    if (!el) return;
    el.className = "result show";
    el.innerHTML = `<div class="${kind === "err" ? "err" : "ok"}">${msg}</div>`;
  }

  /* =====================================================================
     RANK ↔ ROLE GUIDANCE
     ===================================================================== */
  const RANK_ROLE_MAP = {
    "Constable":               ["csc"],
    "Sergeant":                ["csc", "detective"],
    "Warrant Officer":         ["csc", "detective"],
    "Senior Warrant Officer":  ["csc", "detective"],
    "Chief Warrant Officer":   ["csc", "detective"],
    "Lieutenant":              ["csc", "detective", "commander"],
    "Captain":                 ["csc", "detective", "commander"],
    "Major":                   ["detective", "commander"],
    "Lieutenant Colonel":      ["commander"],
    "Colonel":                 ["commander"],
    "Brigadier":               ["commander"],
    "Major General":           ["commander"],
    "Lieutenant General":      ["commander"],
    "General":                 ["commander"],
  };

  const ROLE_LABEL = {
    "csc":       "CSC Desk Officer",
    "detective": "Detective",
    "commander": "Branch Commander",
  };

  function isMismatch(rank, role) {
    if (!rank || !role) return false;
    const allowed = RANK_ROLE_MAP[rank];
    if (!allowed) return false;   // unknown rank — don't warn
    return !allowed.includes(role);
  }

  function describeMismatch(rank, role) {
    const allowed = RANK_ROLE_MAP[rank] || [];
    const humanRoles = allowed.map(r => ROLE_LABEL[r] || r).join(", ");
    return `The rank <b>${esc(rank)}</b> is not normally held by a ` +
           `<b>${esc(ROLE_LABEL[role] || role)}</b> in the SAPS. ` +
           `This rank is usually associated with: ${esc(humanRoles) || "no roles"}.`;
  }

  /* =====================================================================
     SVG CHART PRIMITIVES  (no external libraries)
     ===================================================================== */
  const NS = "http://www.w3.org/2000/svg";

  function svgEl(name, attrs) {
    const el = document.createElementNS(NS, name);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }

  function renderLineChart(container, points) {
    container.innerHTML = "";
    if (!points.length) {
      container.innerHTML = `<div class="chart-empty">No data yet.</div>`;
      return;
    }

    const W = 480, H = 220;
    const PAD = { top: 24, right: 20, bottom: 40, left: 40 };
    const plotW = W - PAD.left - PAD.right;
    const plotH = H - PAD.top - PAD.bottom;

    const maxCount = Math.max(1, ...points.map(p => p.count));
    const stepX = points.length > 1 ? plotW / (points.length - 1) : 0;

    const svg = svgEl("svg", {
      viewBox: `0 0 ${W} ${H}`,
      class: "chart-svg",
      preserveAspectRatio: "xMidYMid meet",
    });

    const yTicks = 4;
    for (let i = 0; i <= yTicks; i++) {
      const y = PAD.top + (plotH * i) / yTicks;
      const val = Math.round(maxCount * (1 - i / yTicks));
      svg.appendChild(svgEl("line", {
        x1: PAD.left, x2: W - PAD.right,
        y1: y, y2: y,
        stroke: "#1e3a63", "stroke-width": 1,
      }));
      const t = svgEl("text", {
        x: PAD.left - 8, y: y + 4,
        fill: "#9fb0c9", "font-size": 10,
        "text-anchor": "end",
      });
      t.textContent = String(val);
      svg.appendChild(t);
    }

    const pathData = points.map((p, i) => {
      const x = PAD.left + i * stepX;
      const y = PAD.top + plotH * (1 - p.count / maxCount);
      return { x, y };
    });

    let area = `M ${pathData[0].x} ${PAD.top + plotH} `;
    pathData.forEach(pt => { area += `L ${pt.x} ${pt.y} `; });
    area += `L ${pathData[pathData.length - 1].x} ${PAD.top + plotH} Z`;

    svg.appendChild(svgEl("path", {
      d: area, fill: "rgba(212,175,55,0.12)", stroke: "none",
    }));

    let line = "";
    pathData.forEach((pt, i) => {
      line += (i === 0 ? "M" : "L") + ` ${pt.x} ${pt.y} `;
    });
    svg.appendChild(svgEl("path", {
      d: line, fill: "none", stroke: "#d4af37", "stroke-width": 2.2,
      "stroke-linejoin": "round", "stroke-linecap": "round",
    }));

    pathData.forEach((pt, i) => {
      svg.appendChild(svgEl("circle", {
        cx: pt.x, cy: pt.y, r: 4.5,
        fill: "#0b1f3a", stroke: "#d4af37", "stroke-width": 2,
      }));
      const val = svgEl("text", {
        x: pt.x, y: pt.y - 10,
        fill: "#e8ecf3", "font-size": 10, "text-anchor": "middle",
        "font-weight": 600,
      });
      val.textContent = String(points[i].count);
      svg.appendChild(val);
    });

    points.forEach((p, i) => {
      const x = PAD.left + i * stepX;
      const t = svgEl("text", {
        x, y: H - PAD.bottom + 18,
        fill: "#9fb0c9", "font-size": 10, "text-anchor": "middle",
      });
      t.textContent = p.label;
      svg.appendChild(t);
    });

    container.appendChild(svg);
  }

  function renderBarChart(container, rows) {
    container.innerHTML = "";
    if (!rows.length) {
      container.innerHTML = `<div class="chart-empty">No data yet.</div>`;
      return;
    }
    const shown = rows.slice(0, 8);
    const maxCount = Math.max(1, ...shown.map(r => r.count));

    const barWrap = document.createElement("div");
    barWrap.className = "bar-list";

    shown.forEach(r => {
      const row = document.createElement("div");
      row.className = "bar-row";

      const label = document.createElement("div");
      label.className = "bar-label";
      label.textContent = r.label;

      const track = document.createElement("div");
      track.className = "bar-track";

      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = (100 * r.count / maxCount) + "%";

      const value = document.createElement("span");
      value.className = "bar-value";
      value.textContent = String(r.count);

      track.appendChild(fill);
      track.appendChild(value);
      row.appendChild(label);
      row.appendChild(track);
      barWrap.appendChild(row);
    });

    container.appendChild(barWrap);
  }

  const STATUS_COLORS = {
    "Open":                  "#d4af37",
    "Under Investigation":   "#fbbf24",
    "Awaiting Forensics":    "#b794f6",
    "Ready for Court":       "#63b3ed",
    "Closed":                "#4ade80",
  };
  const FALLBACK_COLORS = ["#9fb0c9", "#f0cf5f", "#e06b5c", "#5bd68a", "#63b3ed"];

  function renderDonut(container, rows) {
    container.innerHTML = "";
    const total = rows.reduce((a, r) => a + r.count, 0);
    if (!total) {
      container.innerHTML = `<div class="chart-empty">No data yet.</div>`;
      return;
    }

    const W = 220, H = 220;
    const cx = W / 2, cy = H / 2;
    const rOuter = 88, rInner = 56;

    const svg = svgEl("svg", {
      viewBox: `0 0 ${W} ${H}`,
      class: "donut-svg",
      preserveAspectRatio: "xMidYMid meet",
    });

    svg.appendChild(svgEl("circle", {
      cx, cy, r: (rOuter + rInner) / 2,
      fill: "none",
      stroke: "#1e3a63",
      "stroke-width": rOuter - rInner,
    }));

    let angle = -Math.PI / 2;
    rows.forEach((row, i) => {
      const frac = row.count / total;
      const sliceAngle = frac * Math.PI * 2;

      const x1 = cx + Math.cos(angle) * rOuter;
      const y1 = cy + Math.sin(angle) * rOuter;
      const x2 = cx + Math.cos(angle + sliceAngle) * rOuter;
      const y2 = cy + Math.sin(angle + sliceAngle) * rOuter;
      const largeArc = sliceAngle > Math.PI ? 1 : 0;

      const path = svgEl("path", {
        d: `M ${x1} ${y1} A ${rOuter} ${rOuter} 0 ${largeArc} 1 ${x2} ${y2}`,
        fill: "none",
        stroke: STATUS_COLORS[row.label] || FALLBACK_COLORS[i % FALLBACK_COLORS.length],
        "stroke-width": rOuter - rInner,
        "stroke-linecap": "butt",
      });
      svg.appendChild(path);
      angle += sliceAngle;
    });

    const totalText = svgEl("text", {
      x: cx, y: cy + 4,
      fill: "#e8ecf3", "font-size": 22,
      "font-weight": 700, "text-anchor": "middle",
    });
    totalText.textContent = String(total);
    svg.appendChild(totalText);

    const totalLabel = svgEl("text", {
      x: cx, y: cy + 22,
      fill: "#9fb0c9", "font-size": 10,
      "text-anchor": "middle", "letter-spacing": "1",
    });
    totalLabel.textContent = "TOTAL";
    svg.appendChild(totalLabel);

    container.appendChild(svg);

    const legend = document.createElement("div");
    legend.className = "donut-legend";
    rows.forEach((row, i) => {
      const item = document.createElement("div");
      item.className = "legend-item";

      const swatch = document.createElement("span");
      swatch.className = "legend-swatch";
      swatch.style.background =
        STATUS_COLORS[row.label] || FALLBACK_COLORS[i % FALLBACK_COLORS.length];

      const label = document.createElement("span");
      label.className = "legend-label";
      label.textContent = row.label;

      const value = document.createElement("span");
      value.className = "legend-value";
      value.textContent = String(row.count);

      item.appendChild(swatch);
      item.appendChild(label);
      item.appendChild(value);
      legend.appendChild(item);
    });

    container.appendChild(legend);
  }

  /* ------------------------------------------------------------------ */
  /* OVERVIEW                                                           */
  /* ------------------------------------------------------------------ */
  async function loadStats() {
    const totalEl  = q("statTotal");
    const openEl   = q("statOpen");
    const closedEl = q("statClosed");
    const workload = q("workloadArea");
    if (!workload) return;

    workload.innerHTML = `<div class="cmd-empty">Loading…</div>`;
    try {
      const s = await SAPS.api("/api/stats");
      if (totalEl)  totalEl.textContent  = s.total_cases;
      if (openEl)   openEl.textContent   = s.open_cases;
      if (closedEl) closedEl.textContent = s.closed_cases;

      const wl = (s.detective_workload || []);
      if (!wl.length) {
        workload.innerHTML = `<div class="cmd-empty">No detectives registered yet.</div>`;
        return;
      }
      workload.innerHTML = wl.map(d => `
        <div class="item">
          <div class="row">
            <div><div class="k">Detective</div><div class="v">${esc(d.detective)}</div></div>
            <div><div class="k">PERSAL</div><div class="v small">${esc(d.persal_number)}</div></div>
            <div><div class="k">Station</div><div class="v small">${esc(d.station || "—")}</div></div>
            <div><div class="k">Open cases</div><div class="v">${d.open_cases}</div></div>
          </div>
        </div>`).join("");
    } catch (e) {
      workload.innerHTML = `<div class="cmd-empty">${esc(e.message)}</div>`;
    }
  }

  async function loadCharts() {
    const monthsEl = q("chartMonths");
    const crimeEl  = q("chartCrime");
    const statusEl = q("chartStatus");
    if (!monthsEl && !crimeEl && !statusEl) return;

    if (monthsEl) monthsEl.innerHTML = `<div class="chart-empty">Loading…</div>`;
    if (crimeEl)  crimeEl.innerHTML  = `<div class="chart-empty">Loading…</div>`;
    if (statusEl) statusEl.innerHTML = `<div class="chart-empty">Loading…</div>`;

    try {
      const data = await SAPS.api("/api/stats/charts");
      if (monthsEl) renderLineChart(monthsEl, data.cases_per_month || []);
      if (crimeEl)  renderBarChart(crimeEl,  data.cases_by_crime  || []);
      if (statusEl) renderDonut(statusEl,     data.cases_by_status || []);
    } catch (e) {
      const msg = `<div class="chart-empty">${esc(e.message)}</div>`;
      if (monthsEl) monthsEl.innerHTML = msg;
      if (crimeEl)  crimeEl.innerHTML  = msg;
      if (statusEl) statusEl.innerHTML = msg;
    }
  }

  /* ------------------------------------------------------------------ */
  /* PERSONNEL                                                          */
  /* ------------------------------------------------------------------ */
  async function loadUsers() {
    const out = q("usersList");
    if (!out) return;

    out.innerHTML = `<div class="cmd-empty">Loading…</div>`;
    try {
      const users = await SAPS.api("/api/users");
      if (!users.length) {
        out.innerHTML = `<div class="cmd-empty">No personnel registered yet.</div>`;
        return;
      }
      out.innerHTML = users.map(u => `
        <div class="item">
          <div class="row">
            <div><div class="k">PERSAL</div><div class="v">${esc(u.persal_number)}</div></div>
            <div><div class="k">Name</div><div class="v small">${esc(u.full_name)}</div></div>
            <div><div class="k">Role</div><div class="v small">${esc(u.role)}</div></div>
            <div><div class="k">Rank</div><div class="v small">${esc(u.rank || "—")}</div></div>
            <div><div class="k">Station</div><div class="v small">${esc(u.station || "—")}</div></div>
            <div><div class="k">Open cases</div><div class="v small">${u.open_cases}</div></div>
            <div><div class="k">Status</div><div class="v small">${u.active ? "Active" : "Inactive"}</div></div>
            <div style="flex:1 1 100%;display:flex;gap:8px;margin-top:6px;">
              <button class="btn ghost"
                      data-toggle="${u.id}"
                      data-active="${u.active}"
                      data-role="${esc(u.role)}"
                      data-name="${esc(u.full_name)}"
                      data-open="${u.open_cases}">
                ${u.active ? "Deactivate" : "Activate"}
              </button>
              <button class="btn ghost" data-reset="${u.id}">Reset password</button>
            </div>
          </div>
        </div>`).join("");

      out.querySelectorAll("[data-toggle]").forEach(b => {
        b.addEventListener("click", async () => {
          const id       = b.dataset.toggle;
          const isActive = b.dataset.active === "true";
          const role     = b.dataset.role;
          const name     = b.dataset.name;
          const openN    = parseInt(b.dataset.open, 10) || 0;
          const willDeactivate = isActive;

          if (willDeactivate && role === "detective" && openN > 0) {
            const ok = confirm(
              `${name} has ${openN} open case(s).\n\n` +
              `Deactivating will reassign all open cases to the ` +
              `least-loaded active detective. Continue?`
            );
            if (!ok) return;
          }

          try {
            const res = await SAPS.api(`/api/users/${id}/active`, {
              method: "PATCH", body: { active: !isActive },
            });

            if (willDeactivate && res.reassignment) {
              const r = res.reassignment;
              alert(
                `${name} deactivated.\n\n` +
                `${r.moved} case(s) reassigned to ${r.to} (${r.to_persal}).`
              );
            }

            loadUsers();
          } catch (e) {
            alert(e.message);
          }
        });
      });

      out.querySelectorAll("[data-reset]").forEach(b => {
        b.addEventListener("click", async () => {
          const id = b.dataset.reset;
          const pwd = prompt("Enter new password (min 8 characters, 1 digit, 1 letter):");
          if (!pwd) return;
          try {
            await SAPS.api(`/api/users/${id}/password`, {
              method: "PATCH", body: { password: pwd },
            });
            alert("Password updated.");
          } catch (e) { alert(e.message); }
        });
      });
    } catch (e) {
      out.innerHTML = `<div class="cmd-empty">${esc(e.message)}</div>`;
    }
  }

  /* ------------------------------------------------------------------ */
  /* REGISTER — with rank/role guidance                                 */
  /* ------------------------------------------------------------------ */
  function initRegister() {
    const btn = q("createUserBtn");
    if (!btn) return;

    const persalEl  = q("uPersal");
    const roleEl    = q("uRole");
    const rankEl    = q("uRank");
    const nameEl    = q("uName");
    const passEl    = q("uPass");
    const warning   = q("rankWarning");
    const warnText  = q("rankWarningText");
    const confirmCb = q("confirmMismatch");
    const out       = q("userResult");

    function refreshWarning() {
      const rank = rankEl.value;
      const role = roleEl.value;
      const mism = isMismatch(rank, role);

      if (mism) {
        warnText.innerHTML = describeMismatch(rank, role);
        warning.classList.remove("hidden");
      } else {
        warning.classList.add("hidden");
        confirmCb.checked = false;
      }
      updateButtonState();
    }

    function updateButtonState() {
      const rank = rankEl.value;
      const role = roleEl.value;
      const mism = isMismatch(rank, role);
      const confirmed = confirmCb.checked;

      if (mism && !confirmed) {
        btn.disabled = true;
        btn.title = "Tick the confirmation checkbox to proceed.";
      } else {
        btn.disabled = false;
        btn.title = "";
      }
    }

    roleEl.addEventListener("change", refreshWarning);
    rankEl.addEventListener("change", refreshWarning);
    confirmCb.addEventListener("change", updateButtonState);

    btn.addEventListener("click", async () => {
      if (!nameEl.value.trim()) {
        showResult(out, "Full name is required.", "err");
        nameEl.focus();
        return;
      }
      if (!roleEl.value) {
        showResult(out, "Please select a role before creating the account.", "err");
        roleEl.focus();
        return;
      }
      if (!rankEl.value) {
        showResult(out, "Please select a rank before creating the account.", "err");
        rankEl.focus();
        return;
      }
      if (isMismatch(rankEl.value, roleEl.value) && !confirmCb.checked) {
        showResult(out, "Please confirm the unusual rank/role combination.", "err");
        return;
      }
      if (!passEl.value || passEl.value.length < 8) {
        showResult(out, "Password must be at least 8 characters, with at least one letter and one digit.", "err");
        passEl.focus();
        return;
      }

      let persal = (persalEl.value || "").trim().toUpperCase();
      if (!persal) {
        persal = generateLocalStudentNumber();
        persalEl.value = persal;
      }

      const body = {
        persal_number: persal,
        full_name:     nameEl.value.trim(),
        password:      passEl.value,
        role:          roleEl.value,
        rank:          rankEl.value,
        station:       (q("uStation").value || "").trim(),
      };

      try {
        const u = await SAPS.api("/api/users", { method: "POST", body });
        showResult(out,
          `Created <b>${esc(u.full_name)}</b> — ${esc(u.persal_number)} · ${esc(u.role)} · ${esc(u.rank || "")} · ${esc(u.station)}.`,
          "ok");
        ["uPersal", "uName", "uPass"].forEach(id => {
          const el = q(id); if (el) el.value = "";
        });
        roleEl.value = "";
        rankEl.value = "";
        warning.classList.add("hidden");
        confirmCb.checked = false;
        updateButtonState();
      } catch (e) {
        showResult(out, esc(e.message), "err");
      }
    });
  }

  function generateLocalStudentNumber() {
    const n = Math.floor(10000 + Math.random() * 90000);
    return "STU" + n;
  }

  /* ------------------------------------------------------------------ */
  /* DOCKETS — with smart search + pagination                          */
  /* ------------------------------------------------------------------ */
  let currentDocketPage = 1;
  const DOCKETS_PER_PAGE = 20;
  let debounceTimer = null;

  function scheduleDockets(resetPage = true) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      if (resetPage) currentDocketPage = 1;
      loadDockets();
    }, 300);
  }

  async function loadDockets() {
    const out = q("docketsList");
    if (!out) return;

    const searchEl = q("searchText");
    const crimeEl  = q("filterCrime");
    const statusEl = q("filterStatus");
    const fromEl   = q("filterDateFrom");
    const toEl     = q("filterDateTo");
    const countEl  = q("docketsCount");

    let pager = q("docketsPager");
    if (!pager) {
      pager = document.createElement("div");
      pager.id = "docketsPager";
      pager.className = "pager";
      out.parentNode.insertBefore(pager, countEl);
    }

    const params = new URLSearchParams();
    if (searchEl && searchEl.value.trim()) params.set("q", searchEl.value.trim());
    if (crimeEl && crimeEl.value)          params.set("crime_type", crimeEl.value);
    if (statusEl && statusEl.value && statusEl.value !== "All")
      params.set("status", statusEl.value);
    if (fromEl && fromEl.value)            params.set("date_from", fromEl.value);
    if (toEl && toEl.value)                params.set("date_to", toEl.value);
    params.set("page", currentDocketPage);
    params.set("per_page", DOCKETS_PER_PAGE);

    out.innerHTML = `<div class="cmd-empty">Loading…</div>`;
    try {
      const data = await SAPS.api("/api/cases?" + params.toString());
      const cases = data.cases || [];

      if (countEl) {
        countEl.textContent = data.total === 0
          ? "0 dockets"
          : `${data.total} docket${data.total === 1 ? "" : "s"} · page ${data.page} of ${data.total_pages}`;
      }

      if (!cases.length) {
        out.innerHTML = `<div class="cmd-empty">No dockets match your search.</div>`;
        SAPS.renderPager({ container: pager });
        return;
      }

      out.innerHTML = cases.map(c => `
        <div class="item">
          <div class="row">
            <div><div class="k">CAS</div><div class="v">${esc(c.cas_number)}</div></div>
            <div><div class="k">Complainant</div><div class="v small">${esc(c.complainant_name)}</div></div>
            <div><div class="k">Email</div><div class="v small">${esc(c.complainant_email || "—")}</div></div>
            <div><div class="k">Crime</div><div class="v small">${esc(c.crime_type)}</div></div>
            <div><div class="k">Location</div><div class="v small">${esc(c.location)}</div></div>
            <div><div class="k">Status</div><div class="v"><span class="badge-status">${esc(c.status)}</span></div></div>
            <div><div class="k">Detective</div><div class="v small">${esc(c.detective ? c.detective.full_name : "—")}</div></div>
            <div><div class="k">Evidence</div><div class="v small">${c.evidence_count} file(s)</div></div>
            <div><div class="k">Milestones</div><div class="v small">${c.milestone_count}</div></div>
            <div><div class="k">Opened</div><div class="v small">${esc((c.created_at || "").slice(0, 10))}</div></div>
          </div>
        </div>`).join("");

      SAPS.renderPager({
        container: pager,
        page: data.page,
        totalPages: data.total_pages,
        onPage: (n) => { currentDocketPage = n; loadDockets(); },
      });
    } catch (e) {
      out.innerHTML = `<div class="cmd-empty">${esc(e.message)}</div>`;
      SAPS.renderPager({ container: pager });
    }
  }

  /* ------------------------------------------------------------------ */
  /* AUDIT                                                              */
  /* ------------------------------------------------------------------ */
  async function loadAudit() {
    const out = q("auditList");
    if (!out) return;

    out.innerHTML = `<div class="cmd-empty">Loading…</div>`;
    try {
      const logs = await SAPS.api("/api/audit?limit=300");
      if (!logs.length) {
        out.innerHTML = `<div class="cmd-empty">No audit entries yet.</div>`;
        return;
      }
      out.innerHTML = logs.map(l => `
        <div class="item">
          <div class="row">
            <div><div class="k">When</div><div class="v small">${new Date(l.created_at).toLocaleString()}</div></div>
            <div><div class="k">Actor</div><div class="v small">${esc(l.actor)}</div></div>
            <div><div class="k">Action</div><div class="v small">${esc(l.action)}</div></div>
            <div><div class="k">Target</div><div class="v small">${esc(l.target_type || "")}${l.target_id ? " #" + l.target_id : ""}</div></div>
            <div><div class="k">IP</div><div class="v small">${esc(l.ip_address || "")}</div></div>
          </div>
          ${l.detail ? `<div style="margin-top:8px;font-family:Consolas,monospace;font-size:11.5px;color:var(--cmd-muted);word-break:break-all;">${esc(l.detail)}</div>` : ""}
        </div>`).join("");
    } catch (e) {
      out.innerHTML = `<div class="cmd-empty">${esc(e.message)}</div>`;
    }
  }

  /* ------------------------------------------------------------------ */
  /* BOOT                                                               */
  /* ------------------------------------------------------------------ */
  document.addEventListener("DOMContentLoaded", () => {
    if (q("statGrid")) {
      loadStats();
      const b = q("statsRefreshBtn");
      if (b) b.addEventListener("click", loadStats);
    }

    if (q("chartMonths") || q("chartCrime") || q("chartStatus")) {
      loadCharts();
      const b = q("chartsRefreshBtn");
      if (b) b.addEventListener("click", loadCharts);
    }

    if (q("usersList")) {
      loadUsers();
      const b = q("usersRefreshBtn");
      if (b) b.addEventListener("click", loadUsers);
    }

    initRegister();

    if (q("docketsList")) {
      loadDockets();

      const searchEl = q("searchText");
      const crimeEl  = q("filterCrime");
      const statusEl = q("filterStatus");
      const fromEl   = q("filterDateFrom");
      const toEl     = q("filterDateTo");
      const clearEl  = q("clearSearch");

      [searchEl, crimeEl, statusEl, fromEl, toEl].forEach(el => {
        if (!el) return;
        el.addEventListener("input", () => scheduleDockets(true));
        el.addEventListener("change", () => scheduleDockets(true));
      });

      if (clearEl) {
        clearEl.addEventListener("click", () => {
          if (searchEl) searchEl.value = "";
          if (crimeEl)  crimeEl.value = "";
          if (statusEl) statusEl.value = "All";
          if (fromEl)   fromEl.value = "";
          if (toEl)     toEl.value = "";
          currentDocketPage = 1;
          loadDockets();
        });
      }
    }

    if (q("auditList")) {
      loadAudit();
      const b = q("auditRefreshBtn");
      if (b) b.addEventListener("click", loadAudit);
    }
  });
})();