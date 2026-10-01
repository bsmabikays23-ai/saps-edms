(function () {
  "use strict";

  let wizardInitialized = false;

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

  /* =====================  CHARTS  ===================== */
  const NS = "http://www.w3.org/2000/svg";
  function svgEl(name, attrs) {
    const el = document.createElementNS(NS, name);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }

  function renderLineChart(container, points) {
    container.innerHTML = "";
    if (!points.length) { container.innerHTML = `<div class="chart-empty">No data yet.</div>`; return; }
    const W = 480, H = 220, PAD = { top: 24, right: 20, bottom: 40, left: 40 };
    const plotW = W - PAD.left - PAD.right, plotH = H - PAD.top - PAD.bottom;
    const maxCount = Math.max(1, ...points.map(p => p.count));
    const stepX = points.length > 1 ? plotW / (points.length - 1) : 0;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart-svg", preserveAspectRatio: "xMidYMid meet" });
    for (let i = 0; i <= 4; i++) {
      const y = PAD.top + (plotH * i) / 4;
      svg.appendChild(svgEl("line", { x1: PAD.left, x2: W - PAD.right, y1: y, y2: y, stroke: "#1e3a63", "stroke-width": 1 }));
      const t = svgEl("text", { x: PAD.left - 8, y: y + 4, fill: "#9fb0c9", "font-size": 10, "text-anchor": "end" });
      t.textContent = String(Math.round(maxCount * (1 - i / 4)));
      svg.appendChild(t);
    }
    const pathData = points.map((p, i) => ({
      x: PAD.left + i * stepX,
      y: PAD.top + plotH * (1 - p.count / maxCount),
    }));
    let area = `M ${pathData[0].x} ${PAD.top + plotH} `;
    pathData.forEach(pt => { area += `L ${pt.x} ${pt.y} `; });
    area += `L ${pathData[pathData.length - 1].x} ${PAD.top + plotH} Z`;
    svg.appendChild(svgEl("path", { d: area, fill: "rgba(212,175,55,0.12)", stroke: "none" }));
    let line = "";
    pathData.forEach((pt, i) => { line += (i === 0 ? "M" : "L") + ` ${pt.x} ${pt.y} `; });
    svg.appendChild(svgEl("path", { d: line, fill: "none", stroke: "#d4af37", "stroke-width": 2.2 }));
    pathData.forEach((pt, i) => {
      svg.appendChild(svgEl("circle", { cx: pt.x, cy: pt.y, r: 4.5, fill: "#0b1f3a", stroke: "#d4af37", "stroke-width": 2 }));
      const v = svgEl("text", { x: pt.x, y: pt.y - 10, fill: "#e8ecf3", "font-size": 10, "text-anchor": "middle", "font-weight": 600 });
      v.textContent = String(points[i].count);
      svg.appendChild(v);
    });
    points.forEach((p, i) => {
      const x = PAD.left + i * stepX;
      const t = svgEl("text", { x, y: H - PAD.bottom + 18, fill: "#9fb0c9", "font-size": 10, "text-anchor": "middle" });
      t.textContent = p.label;
      svg.appendChild(t);
    });
    container.appendChild(svg);
  }

  function renderBarChart(container, rows) {
    container.innerHTML = "";
    if (!rows.length) { container.innerHTML = `<div class="chart-empty">No data yet.</div>`; return; }
    const shown = rows.slice(0, 8);
    const maxCount = Math.max(1, ...shown.map(r => r.count));
    const barWrap = document.createElement("div"); barWrap.className = "bar-list";
    shown.forEach(r => {
      const row = document.createElement("div"); row.className = "bar-row";
      const label = document.createElement("div"); label.className = "bar-label"; label.textContent = r.label;
      const track = document.createElement("div"); track.className = "bar-track";
      const fill = document.createElement("div"); fill.className = "bar-fill"; fill.style.width = (100 * r.count / maxCount) + "%";
      const value = document.createElement("span"); value.className = "bar-value"; value.textContent = String(r.count);
      track.appendChild(fill); track.appendChild(value);
      row.appendChild(label); row.appendChild(track);
      barWrap.appendChild(row);
    });
    container.appendChild(barWrap);
  }

  const STATUS_COLORS = {
    "Open": "#d4af37", "Under Investigation": "#fbbf24",
    "Awaiting Forensics": "#b794f6", "Ready for Court": "#63b3ed", "Closed": "#4ade80",
    "Light / Routine": "#4ade80", "Small / Standard": "#d4af37",
    "Serious / Complex": "#fbbf24", "Priority / Highly Complex": "#e06b5c",
  };
  const FALLBACK_COLORS = ["#9fb0c9", "#f0cf5f", "#e06b5c", "#5bd68a", "#63b3ed"];

  function renderDonut(container, rows) {
    container.innerHTML = "";
    const total = rows.reduce((a, r) => a + r.count, 0);
    if (!total) { container.innerHTML = `<div class="chart-empty">No data yet.</div>`; return; }
    const W = 220, H = 220, cx = W / 2, cy = H / 2, rOuter = 88, rInner = 56;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "donut-svg", preserveAspectRatio: "xMidYMid meet" });
    svg.appendChild(svgEl("circle", { cx, cy, r: (rOuter + rInner) / 2, fill: "none", stroke: "#1e3a63", "stroke-width": rOuter - rInner }));
    let angle = -Math.PI / 2;
    rows.forEach((row, i) => {
      const sliceAngle = (row.count / total) * Math.PI * 2;
      const x1 = cx + Math.cos(angle) * rOuter, y1 = cy + Math.sin(angle) * rOuter;
      const x2 = cx + Math.cos(angle + sliceAngle) * rOuter, y2 = cy + Math.sin(angle + sliceAngle) * rOuter;
      svg.appendChild(svgEl("path", {
        d: `M ${x1} ${y1} A ${rOuter} ${rOuter} 0 ${sliceAngle > Math.PI ? 1 : 0} 1 ${x2} ${y2}`,
        fill: "none", stroke: STATUS_COLORS[row.label] || FALLBACK_COLORS[i % FALLBACK_COLORS.length],
        "stroke-width": rOuter - rInner,
      }));
      angle += sliceAngle;
    });
    const tt = svgEl("text", { x: cx, y: cy + 4, fill: "#e8ecf3", "font-size": 22, "font-weight": 700, "text-anchor": "middle" });
    tt.textContent = String(total);
    svg.appendChild(tt);
    const tl = svgEl("text", { x: cx, y: cy + 22, fill: "#9fb0c9", "font-size": 10, "text-anchor": "middle" });
    tl.textContent = "TOTAL";
    svg.appendChild(tl);
    container.appendChild(svg);
    const legend = document.createElement("div"); legend.className = "donut-legend";
    rows.forEach((row, i) => {
      const item = document.createElement("div"); item.className = "legend-item";
      const sw = document.createElement("span"); sw.className = "legend-swatch";
      sw.style.background = STATUS_COLORS[row.label] || FALLBACK_COLORS[i % FALLBACK_COLORS.length];
      const lb = document.createElement("span"); lb.className = "legend-label"; lb.textContent = row.label;
      const vv = document.createElement("span"); vv.className = "legend-value"; vv.textContent = String(row.count);
      item.appendChild(sw); item.appendChild(lb); item.appendChild(vv);
      legend.appendChild(item);
    });
    container.appendChild(legend);
  }

  /* =====================  OVERVIEW  ===================== */
  async function loadStats() {
    const totalEl = q("statTotal"), openEl = q("statOpen"), closedEl = q("statClosed");
    const workload = q("workloadArea");
    if (!workload) return;
    workload.innerHTML = `<div class="cmd-empty">Loading…</div>`;
    try {
      const s = await SAPS.api("/api/stats");
      if (totalEl) totalEl.textContent = s.total_cases;
      if (openEl) openEl.textContent = s.open_cases;
      if (closedEl) closedEl.textContent = s.closed_cases;
      const wl = s.detective_workload || [];
      if (!wl.length) { workload.innerHTML = `<div class="cmd-empty">No detectives registered yet.</div>`; return; }
      workload.innerHTML = wl.map(d => `
        <div class="item"><div class="row">
          <div><div class="k">Detective</div><div class="v">${esc(d.detective)}</div></div>
          <div><div class="k">PERSAL</div><div class="v small">${esc(d.persal_number)}</div></div>
          <div><div class="k">Unit</div><div class="v small">${esc(d.specialisation || "—")}</div></div>
          <div><div class="k">Open cases</div><div class="v">${d.open_cases}</div></div>
        </div></div>`).join("");
    } catch (e) { workload.innerHTML = `<div class="cmd-empty">${esc(e.message)}</div>`; }
  }

  async function loadCharts() {
    const m = q("chartMonths"), c = q("chartCrime"), s = q("chartStatus"), t = q("chartTier");
    if (!m && !c && !s && !t) return;
    [m, c, s, t].forEach(el => { if (el) el.innerHTML = `<div class="chart-empty">Loading…</div>`; });
    try {
      const data = await SAPS.api("/api/stats/charts");
      if (m) renderLineChart(m, data.cases_per_month || []);
      if (c) renderBarChart(c, data.cases_by_crime || []);
      if (s) renderDonut(s, data.cases_by_status || []);
      if (t) renderDonut(t, data.cases_by_tier || []);
    } catch (e) {
      const msg = `<div class="chart-empty">${esc(e.message)}</div>`;
      [m, c, s, t].forEach(el => { if (el) el.innerHTML = msg; });
    }
  }

  /* =====================  PERSONNEL  ===================== */
  async function loadUsers() {
    const out = q("usersList");
    if (!out) return;
    out.innerHTML = `<div class="cmd-empty">Loading…</div>`;
    try {
      const users = await SAPS.api("/api/users");
      if (!users.length) { out.innerHTML = `<div class="cmd-empty">No personnel registered yet.</div>`; return; }
      out.innerHTML = users.map(u => `
        <div class="item">
          <div class="row">
            <div><div class="k">PERSAL</div><div class="v">${esc(u.persal_number)}</div></div>
            <div><div class="k">Name</div><div class="v small">${esc(u.full_name)}</div></div>
            <div><div class="k">Email</div><div class="v small">${esc(u.email || "—")}</div></div>
            <div><div class="k">Role</div><div class="v small">${esc(u.role)}</div></div>
            <div><div class="k">Rank</div><div class="v small">${esc(u.rank || "—")}</div></div>
            <div><div class="k">Unit</div><div class="v small">${esc(u.specialisation || "—")}</div></div>
            <div><div class="k">Open cases</div><div class="v small">${u.open_cases}</div></div>
            <div><div class="k">Status</div><div class="v small">${u.active ? "Active" : "Inactive"}</div></div>
            <div style="flex:1 1 100%;display:flex;gap:8px;margin-top:6px;flex-wrap:wrap;">
              <button class="btn ghost" data-toggle="${u.id}" data-active="${u.active}">
                ${u.active ? "Deactivate" : "Activate"}
              </button>
              <button class="btn ghost" data-send-reset="${u.id}" data-email="${esc(u.email || "")}">
                Send reset code
              </button>
            </div>
          </div>
        </div>`).join("");

      out.querySelectorAll("[data-toggle]").forEach(b => {
        b.addEventListener("click", async () => {
          const id = b.dataset.toggle;
          const active = b.dataset.active === "true";
          try {
            await SAPS.api(`/api/users/${id}/active`, { method: "PATCH", body: { active: !active } });
            loadUsers();
          } catch (e) { alert(e.message); }
        });
      });
      out.querySelectorAll("[data-send-reset]").forEach(b => {
        b.addEventListener("click", async () => {
          const id = b.dataset.sendReset;
          const email = b.dataset.email;
          if (!email) { alert("This account has no email on file."); return; }
          if (!confirm(`Send a password reset code to ${email}?`)) return;
          try {
            const res = await SAPS.api(`/api/users/${id}/send-reset-code`, { method: "POST" });
            alert(res.msg || "Reset code sent.");
          } catch (e) { alert(e.message); }
        });
      });
    } catch (e) { out.innerHTML = `<div class="cmd-empty">${esc(e.message)}</div>`; }
  }

  /* =====================  REGISTRATION WIZARD  ===================== */
  const WIZ = {
    step: 1,
    roles: [],
    specialisations: [],
    role: null,
    rank: null,
    spec: null,
  };

  const RANK_ORDER = [
    "Constable", "Sergeant", "Warrant Officer",
    "Senior Warrant Officer", "Chief Warrant Officer",
    "Lieutenant", "Captain", "Major",
    "Lieutenant Colonel", "Colonel", "Brigadier",
    "Major General", "Lieutenant General", "General",
  ];

  async function loadRegisterOptions() {
    const data = await SAPS.api("/api/register-options");
    WIZ.roles = data.roles || [];
    WIZ.specialisations = data.specialisations || [];
  }

  function deselectAll(box) {
    box.querySelectorAll(".wiz-choice").forEach(x => x.classList.remove("selected"));
  }

  function renderRoleChoices() {
    const box = q("roleChoices");
    if (!box) return;
    box.innerHTML = WIZ.roles.map(r => `
      <button type="button" class="wiz-choice" data-role="${r.value}">
        <span class="wiz-choice-title">${esc(r.label)}</span>
        <span class="wiz-choice-sub">${esc(r.guidance)}</span>
      </button>`).join("");
    box.querySelectorAll("[data-role]").forEach(btn => {
      btn.addEventListener("click", () => {
        WIZ.role = btn.dataset.role;
        WIZ.rank = null;
        WIZ.spec = null;
        const role = WIZ.roles.find(r => r.value === WIZ.role);
        if (role && role.ranks.length) WIZ.rank = role.ranks[0];
        deselectAll(box);
        btn.classList.add("selected");

        // Auto-advance to step 2
        setTimeout(() => {
          WIZ.step = 2;
          renderRankChoices();
          updateSteps();
          updateNavState();
        }, 220);
      });
    });
  }

  function renderRankChoices() {
    const box = q("rankChoices");
    const hint = q("rankHint");
    if (!box) return;
    const role = WIZ.roles.find(r => r.value === WIZ.role);
    if (!role) { box.innerHTML = ""; return; }
    hint.textContent = role.guidance + " Lowest valid rank is pre-selected.";

    let ranks = role.ranks.slice();
    if (role.needs_specialisation && WIZ.spec) {
      const spec = WIZ.specialisations.find(s => s.value === WIZ.spec);
      if (spec) {
        const minIdx = RANK_ORDER.indexOf(spec.min_rank);
        ranks = ranks.filter(r => RANK_ORDER.indexOf(r) >= minIdx);
      }
    }

    if (!WIZ.rank || !ranks.includes(WIZ.rank)) WIZ.rank = ranks[0];

    box.innerHTML = ranks.map(rk => `
      <button type="button" class="wiz-choice ${rk === WIZ.rank ? "selected" : ""}" data-rank="${rk}">
        <span class="wiz-choice-title">${esc(rk)}</span>
        ${rk === ranks[0] ? `<span class="wiz-choice-badge">Recommended entry rank</span>` : ""}
      </button>`).join("");

    box.querySelectorAll("[data-rank]").forEach(btn => {
      btn.addEventListener("click", () => {
        WIZ.rank = btn.dataset.rank;
        deselectAll(box);
        btn.classList.add("selected");

        // Auto-advance: CSC skips to step 4, Detective goes to step 3
        setTimeout(() => {
          if (role.needs_specialisation) {
            WIZ.step = 3;
            renderSpecChoices();
          } else {
            WIZ.step = 4;
            renderSummary();
          }
          updateSteps();
          updateNavState();
        }, 220);
      });
    });
  }

  function renderSpecChoices() {
    const box = q("specChoices");
    const hint = q("specHint");
    if (!box) return;
    const role = WIZ.roles.find(r => r.value === WIZ.role);
    if (!role || !role.needs_specialisation) { box.innerHTML = ""; return; }

    const rankIdx = RANK_ORDER.indexOf(WIZ.rank || "");
    const valid = WIZ.specialisations.filter(s => RANK_ORDER.indexOf(s.min_rank) <= rankIdx);

    hint.textContent = valid.length
      ? `Only units available at rank ${WIZ.rank} are shown.`
      : `No units are available at rank ${WIZ.rank}. Go back and choose a higher rank.`;

    if (WIZ.spec && !valid.find(s => s.value === WIZ.spec)) WIZ.spec = null;

    box.innerHTML = valid.map(s => `
      <button type="button" class="wiz-choice ${s.value === WIZ.spec ? "selected" : ""}" data-spec="${esc(s.value)}">
        <span class="wiz-choice-title">${esc(s.label)}</span>
        <span class="wiz-choice-sub">${esc(s.handles)}</span>
        <span class="wiz-choice-badge">Min rank: ${esc(s.min_rank)}</span>
      </button>`).join("");

    box.querySelectorAll("[data-spec]").forEach(btn => {
      btn.addEventListener("click", () => {
        WIZ.spec = btn.dataset.spec;
        deselectAll(box);
        btn.classList.add("selected");
        updateNavState();
        // No auto-advance here — admin should confirm the unit explicitly
      });
    });
  }

  function renderSummary() {
    const box = q("wizardSummary");
    if (!box) return;
    const role = WIZ.roles.find(r => r.value === WIZ.role);
    const spec = WIZ.specialisations.find(s => s.value === WIZ.spec);
    box.innerHTML = `
      <div><div class="ws-k">Role</div><div class="ws-v">${esc(role ? role.label : "—")}</div></div>
      <div><div class="ws-k">Rank</div><div class="ws-v">${esc(WIZ.rank || "—")}</div></div>
      <div><div class="ws-k">Unit</div><div class="ws-v">${esc(spec ? spec.label : "—")}</div></div>
    `;
  }

  function updateSteps() {
    document.querySelectorAll(".wizard-step").forEach(el => {
      const n = parseInt(el.dataset.step, 10);
      el.classList.toggle("active", n === WIZ.step);
      el.classList.toggle("done", n < WIZ.step);
    });
    document.querySelectorAll(".wizard-panel").forEach(el => {
      const n = parseInt(el.dataset.panel, 10);
      el.classList.toggle("active", n === WIZ.step);
    });
  }

  function updateNavState() {
    const back = q("wizBack"), next = q("wizNext"), create = q("wizCreate");
    if (!back || !next || !create) return;
    back.style.visibility = WIZ.step > 1 ? "visible" : "hidden";
    if (WIZ.step === 4) {
      next.style.display = "none";
      create.style.display = "inline-flex";
    } else {
      next.style.display = "inline-flex";
      create.style.display = "none";
    }
  }

  function canAdvance() {
    if (WIZ.step === 1) return !!WIZ.role;
    if (WIZ.step === 2) return !!WIZ.rank;
    if (WIZ.step === 3) {
      const role = WIZ.roles.find(r => r.value === WIZ.role);
      if (!role) return false;
      return role.needs_specialisation ? !!WIZ.spec : true;
    }
    return true;
  }

  function goNext() {
    if (!canAdvance()) { alert("Please make a selection before continuing."); return; }
    if (WIZ.step === 1) {
      WIZ.step = 2; renderRankChoices();
    } else if (WIZ.step === 2) {
      const role = WIZ.roles.find(r => r.value === WIZ.role);
      if (role && role.needs_specialisation) { WIZ.step = 3; renderSpecChoices(); }
      else { WIZ.step = 4; renderSummary(); }
    } else if (WIZ.step === 3) {
      WIZ.step = 4; renderSummary();
    }
    updateSteps(); updateNavState();
  }

  function goBack() {
    if (WIZ.step === 4) {
      const role = WIZ.roles.find(r => r.value === WIZ.role);
      WIZ.step = (role && role.needs_specialisation) ? 3 : 2;
      if (WIZ.step === 3) renderSpecChoices();
      if (WIZ.step === 2) renderRankChoices();
    } else if (WIZ.step === 3) {
      WIZ.step = 2; renderRankChoices();
    } else if (WIZ.step === 2) {
      WIZ.step = 1;
    }
    updateSteps(); updateNavState();
  }

  async function submitWizard() {
    const out = q("userResult");
    const nameEl = q("uName"), emailEl = q("uEmail"), passEl = q("uPass");
    const persalEl = q("uPersal"), stationEl = q("uStation");
    const name = nameEl.value.trim(), email = emailEl.value.trim(), pass = passEl.value;

    if (!name) { showResult(out, "Full name is required.", "err"); nameEl.focus(); return; }
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      showResult(out, "A valid email address is required.", "err"); emailEl.focus(); return;
    }
    if (!pass || pass.length < 8 || !/[0-9]/.test(pass) || !/[A-Za-z]/.test(pass)) {
      showResult(out, "Password must be at least 8 characters with a letter and a digit.", "err");
      passEl.focus(); return;
    }

    let persal = (persalEl.value || "").trim().toUpperCase();
    if (!persal) {
      persal = "PER" + Math.floor(10000 + Math.random() * 90000);
      persalEl.value = persal;
    }

    const body = {
      persal_number: persal,
      full_name: name,
      email: email,
      password: pass,
      role: WIZ.role,
      rank: WIZ.rank,
      station: (stationEl.value || "").trim(),
      specialisation: WIZ.role === "detective" ? WIZ.spec : null,
    };

    try {
      const u = await SAPS.api("/api/users", { method: "POST", body });
      showResult(out, `Created <b>${esc(u.full_name)}</b> — ${esc(u.persal_number)} · ${esc(u.role)} · ${esc(u.rank || "")} · ${esc(u.specialisation || "—")}.`, "ok");
      WIZ.step = 1; WIZ.role = null; WIZ.rank = null; WIZ.spec = null;
      ["uPersal", "uName", "uEmail", "uPass"].forEach(id => { const el = q(id); if (el) el.value = ""; });
      renderRoleChoices();
      updateSteps(); updateNavState();
    } catch (e) { showResult(out, esc(e.message), "err"); }
  }

  function initWizard() {
    if (wizardInitialized || !q("roleChoices")) return;
    wizardInitialized = true;
    loadRegisterOptions()
      .then(() => { renderRoleChoices(); updateSteps(); updateNavState(); })
      .catch(err => {
        const out = q("userResult");
        showResult(out, `Could not load options: ${esc(err.message)}`, "err");
      });
    q("wizNext").addEventListener("click", goNext);
    q("wizBack").addEventListener("click", goBack);
    q("wizCreate").addEventListener("click", submitWizard);
  }

  /* =====================  APPROVALS  ===================== */
  async function refuseCase(caseId, onSuccess) {
    const reason = prompt("Refusal reason:");
    if (reason === null) return;
    const note = prompt("Optional note:");
    if (note === null) return;
    try {
      await SAPS.api(`/api/cases/${caseId}/refuse`, {
        method: "POST",
        body: { reason, note }
      });
      alert("Case refused successfully.");
      if (onSuccess) onSuccess();
    } catch (e) {
      alert(e.message);
    }
  }

  async function transferCase(caseId, onSuccess) {
    const station = prompt("Destination station:");
    if (station === null) return;
    const note = prompt("Optional note:");
    if (note === null) return;
    try {
      await SAPS.api(`/api/cases/${caseId}/transfer`, {
        method: "POST",
        body: { station, note }
      });
      alert("Case transferred successfully.");
      if (onSuccess) onSuccess();
    } catch (e) {
      alert(e.message);
    }
  }

  async function loadApprovals() {
    const out = q("approvalsList");
    if (!out) return;
    out.innerHTML = `<div class="cmd-empty">Loading…</div>`;
    try {
      const [casesData, users] = await Promise.all([
        SAPS.api("/api/cases?approval_status=Awaiting%20Approval&page=1&per_page=200"),
        SAPS.api("/api/users"),
      ]);
      const detectives = (users || []).filter(u => u.role === "detective" && u.active);
      const cases = casesData.cases || [];
      if (!cases.length) { out.innerHTML = `<div class="cmd-empty">No cases awaiting commander approval.</div>`; return; }

      out.innerHTML = cases.map(c => {
        const reasons = (c.classification_reasons || []).slice(0, 4);
        const suitableDetectives = detectives.filter(d => {
          if (!c.assigned_unit) return true;
          if (!d.specialisation || d.specialisation === "General Detective") return true;
          return d.specialisation === c.assigned_unit;
        });

        const options = suitableDetectives.length
          ? suitableDetectives.map(d => `<option value="${d.id}">${SAPS.esc(d.full_name)} · ${SAPS.esc(d.rank || "—")} · ${SAPS.esc(d.specialisation || "General Detective")}</option>`).join("")
          : `<option value="">No suitable detective available</option>`;

        return `
          <div class="item">
            <div class="row">
              <div><div class="k">CAS</div><div class="v">${esc(c.cas_number)}</div></div>
              <div><div class="k">Crime</div><div class="v small">${esc(c.crime_type)}</div></div>
              <div><div class="k">Tier</div><div class="v small">${esc(c.case_tier || "—")}</div></div>
              <div><div class="k">Recommended unit</div><div class="v small">${esc(c.assigned_unit || "—")}</div></div>
              <div><div class="k">Complainant</div><div class="v small">${esc(c.complainant_name)}</div></div>
              <div style="flex:1 1 100%;display:flex;flex-direction:column;gap:8px;margin-top:8px;">
                <div class="cmd-muted" style="font-size:12px;line-height:1.5;">
                  <strong>Case type:</strong> ${esc(c.crime_type)}<br>
                  <strong>Classification:</strong> ${esc(c.case_tier || "—")}<br>
                  <strong>Reasons:</strong> ${reasons.length ? esc(reasons.join("; ")) : "No reasons recorded"}
                </div>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                  <select data-det-for="${c.id}" class="search-select" style="min-width:260px;">
                    <option value="">— Select suitable detective —</option>
                    ${options}
                  </select>
                  <button class="btn primary" data-approve="${c.id}">Approve assignment</button>
                  <button class="btn ghost" data-refuse="${c.id}">Refuse</button>
                  <button class="btn secondary" data-transfer="${c.id}">Transfer</button>
                </div>
              </div>
            </div>
          </div>`;
      }).join("");

      out.querySelectorAll("[data-approve]").forEach(btn => {
        btn.addEventListener("click", async () => {
          const id = btn.dataset.approve;
          const sel = out.querySelector(`[data-det-for="${id}"]`);
          const detId = sel ? sel.value : "";
          if (!detId) {
            alert("Please select a suitable detective before approving this case.");
            return;
          }
          try {
            await SAPS.api(`/api/cases/${id}/approve`, { method: "POST", body: { detective_id: Number(detId) } });
            alert("Case approved and assigned to the selected detective.");
            loadApprovals();
          } catch (e) { alert(e.message); }
        });
      });

      out.querySelectorAll("[data-refuse]").forEach(btn => {
        btn.addEventListener("click", async () => {
          const id = btn.dataset.refuse;
          await refuseCase(id, loadApprovals);
        });
      });

      out.querySelectorAll("[data-transfer]").forEach(btn => {
        btn.addEventListener("click", async () => {
          const id = btn.dataset.transfer;
          await transferCase(id, loadApprovals);
        });
      });
    } catch (e) { out.innerHTML = `<div class="cmd-empty">${esc(e.message)}</div>`; }
  }

  /* =====================  DOCKETS  ===================== */
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
    const searchEl = q("searchText"), crimeEl = q("filterCrime"), statusEl = q("filterStatus");
    const tierEl = q("filterTier"), verifEl = q("filterVerification");
    const fromEl = q("filterDateFrom"), toEl = q("filterDateTo"), countEl = q("docketsCount");

    let pager = q("docketsPager");
    if (!pager) {
      pager = document.createElement("div"); pager.id = "docketsPager"; pager.className = "pager";
      out.parentNode.insertBefore(pager, countEl);
    }

    const params = new URLSearchParams();
    if (searchEl && searchEl.value.trim()) params.set("q", searchEl.value.trim());
    if (crimeEl && crimeEl.value) params.set("crime_type", crimeEl.value);
    if (statusEl && statusEl.value && statusEl.value !== "All") params.set("status", statusEl.value);
    if (tierEl && tierEl.value && tierEl.value !== "All") params.set("case_tier", tierEl.value);
    if (verifEl && verifEl.value && verifEl.value !== "All") params.set("verification_status", verifEl.value);
    if (fromEl && fromEl.value) params.set("date_from", fromEl.value);
    if (toEl && toEl.value) params.set("date_to", toEl.value);
    params.set("page", currentDocketPage); params.set("per_page", DOCKETS_PER_PAGE);

    out.innerHTML = `<div class="cmd-empty">Loading…</div>`;
    try {
      const data = await SAPS.api("/api/cases?" + params.toString());
      const cases = data.cases || [];
      if (countEl) countEl.textContent = data.total === 0 ? "0 dockets" : `${data.total} docket${data.total === 1 ? "" : "s"} · page ${data.page} of ${data.total_pages}`;
      if (!cases.length) { out.innerHTML = `<div class="cmd-empty">No dockets match your search.</div>`; SAPS.renderPager({ container: pager }); return; }
      out.innerHTML = cases.map(c => `
        <div class="item"><div class="row">
          <div><div class="k">CAS</div><div class="v">${esc(c.cas_number)}</div></div>
          <div><div class="k">Complainant</div><div class="v small">${esc(c.complainant_name)}</div></div>
          <div><div class="k">Crime</div><div class="v small">${esc(c.crime_type)}</div></div>
          <div><div class="k">Tier</div><div class="v small">${esc(c.case_tier || "—")}</div></div>
          <div><div class="k">Unit</div><div class="v small">${esc(c.assigned_unit || "—")}</div></div>
          <div><div class="k">Detective</div><div class="v small">${esc(c.detective ? c.detective.full_name : "—")}</div></div>
          <div><div class="k">Verification</div><div class="v small">${esc(c.verification_status)}</div></div>
          <div><div class="k">Approval</div><div class="v small">${esc(c.approval_status)}</div></div>
          <div><div class="k">Status</div><div class="v"><span class="badge-status">${esc(c.status)}</span></div></div>
        </div></div>`).join("");
      SAPS.renderPager({ container: pager, page: data.page, totalPages: data.total_pages, onPage: (n) => { currentDocketPage = n; loadDockets(); } });
    } catch (e) { out.innerHTML = `<div class="cmd-empty">${esc(e.message)}</div>`; SAPS.renderPager({ container: pager }); }
  }

  /* =====================  AUDIT  ===================== */
  async function loadAudit() {
    const out = q("auditList");
    if (!out) return;
    out.innerHTML = `<div class="cmd-empty">Loading…</div>`;
    try {
      const logs = await SAPS.api("/api/audit?limit=300");
      if (!logs.length) { out.innerHTML = `<div class="cmd-empty">No audit entries yet.</div>`; return; }
      out.innerHTML = logs.map(l => `
        <div class="item"><div class="row">
          <div><div class="k">When</div><div class="v small">${new Date(l.created_at).toLocaleString()}</div></div>
          <div><div class="k">Actor</div><div class="v small">${esc(l.actor)}</div></div>
          <div><div class="k">Action</div><div class="v small">${esc(l.action)}</div></div>
          <div><div class="k">Target</div><div class="v small">${esc(l.target_type || "")}${l.target_id ? " #" + l.target_id : ""}</div></div>
          <div><div class="k">IP</div><div class="v small">${esc(l.ip_address || "")}</div></div>
        </div>
        ${l.detail ? `<div style="margin-top:8px;font-family:Consolas,monospace;font-size:11.5px;color:var(--cmd-muted);word-break:break-all;">${esc(l.detail)}</div>` : ""}
        </div>`).join("");
    } catch (e) { out.innerHTML = `<div class="cmd-empty">${esc(e.message)}</div>`; }
  }

  /* =====================  BOOT  ===================== */
  document.addEventListener("DOMContentLoaded", () => {
    if (q("statGrid")) { loadStats(); const b = q("statsRefreshBtn"); if (b) b.addEventListener("click", loadStats); }
    if (q("chartMonths") || q("chartCrime") || q("chartStatus") || q("chartTier")) {
      loadCharts(); const b = q("chartsRefreshBtn"); if (b) b.addEventListener("click", loadCharts);
    }
    if (q("usersList")) { loadUsers(); const b = q("usersRefreshBtn"); if (b) b.addEventListener("click", loadUsers); }
    if (q("roleChoices")) initWizard();
    if (q("approvalsList")) { loadApprovals(); const b = q("approvalsRefreshBtn"); if (b) b.addEventListener("click", loadApprovals); }
    if (q("docketsList")) {
      loadDockets();
      const searchEl = q("searchText"), crimeEl = q("filterCrime"), statusEl = q("filterStatus");
      const tierEl = q("filterTier"), verifEl = q("filterVerification");
      const fromEl = q("filterDateFrom"), toEl = q("filterDateTo"), clearEl = q("clearSearch");
      [searchEl, crimeEl, statusEl, tierEl, verifEl, fromEl, toEl].forEach(el => {
        if (!el) return;
        el.addEventListener("input", () => scheduleDockets(true));
        el.addEventListener("change", () => scheduleDockets(true));
      });
      if (clearEl) clearEl.addEventListener("click", () => {
        [searchEl, crimeEl, fromEl, toEl].forEach(el => { if (el) el.value = ""; });
        if (statusEl) statusEl.value = "All";
        if (tierEl) tierEl.value = "All";
        if (verifEl) verifEl.value = "All";
        currentDocketPage = 1; loadDockets();
      });
    }
    if (q("auditList")) { loadAudit(); const b = q("auditRefreshBtn"); if (b) b.addEventListener("click", loadAudit); }
  });
})();