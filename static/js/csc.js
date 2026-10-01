document.addEventListener("DOMContentLoaded", () => {
  const currentPath = window.location.pathname;
  const apiBase = "/api";

  const toast = document.getElementById("toast");
  const showToast = (msg, kind = "info") => {
    if (!toast) return;
    toast.textContent = msg;
    toast.className = "toast show " + kind;
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => toast.className = "toast", 2800);
  };

  const safeSelector = (id) => (document.getElementById(id) ? true : false);

  if (currentPath.includes("/csc") || document.getElementById("docketForm")) {
    const docketForm = document.getElementById("docketForm");
    const saveBtn = document.getElementById("saveCaseBtn");
    const saveResult = document.getElementById("saveCaseResult");
    if (docketForm && saveBtn && saveResult) {
      saveBtn.addEventListener("click", async () => {
        const formData = new FormData(docketForm);
        const payload = Object.fromEntries(formData.entries());
        try {
          await SAPS.api(`${apiBase}/cases`, { method: "POST", body: payload });
          saveResult.textContent = "Docket saved.";
          saveResult.className = "inline-msg ok";
          showToast("Docket saved.", "ok");
          setTimeout(() => location.href = "/csc", 700);
        } catch (e) {
          saveResult.textContent = e.message || "Could not save docket.";
          saveResult.className = "inline-msg err";
          showToast(e.message || "Could not save docket.", "err");
        }
      });
    }
  }

  const reviewTable = document.getElementById("reviewTable");
  if (reviewTable) {
    reviewTable.addEventListener("click", async (event) => {
      const btn = event.target.closest("button[data-action]");
      if (!btn) return;
      const action = btn.dataset.action;
      const caseId = btn.dataset.caseId;
      if (!caseId || !action) return;

      try {
        if (action === "approve") {
          await SAPS.api(`${apiBase}/cases/${caseId}/approve`, { method: "POST" });
          showToast("Docket approved.", "ok");
          location.reload();
        } else if (action === "reject") {
          const reason = prompt("Reason for rejection:");
          if (!reason) return;
          await SAPS.api(`${apiBase}/cases/${caseId}/reject`, { method: "POST", body: { reason } });
          showToast("Docket rejected.", "ok");
          location.reload();
        } else if (action === "transfer") {
          const reason = prompt("Reason for transfer:");
          if (!reason) return;
          await SAPS.api(`${apiBase}/cases/${caseId}/transfer`, { method: "POST", body: { reason } });
          showToast("Docket transferred.", "ok");
          location.reload();
        }
      } catch (e) {
        showToast(e.message || "Action failed.", "err");
      }
    });
  }

  const applyBtn = document.getElementById("applyFiltersBtn");
  if (applyBtn) {
    applyBtn.addEventListener("click", () => {
      const params = new URLSearchParams(window.location.search);
      const status = document.getElementById("statusFilter")?.value || "";
      const search = document.getElementById("searchInput")?.value || "";
      if (status) params.set("status", status);
      else params.delete("status");
      if (search) params.set("q", search);
      else params.delete("q");
      window.location.search = params.toString();
    });
  }

  const resetBtn = document.getElementById("resetFiltersBtn");
  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      window.location.search = "";
    });
  }

  const exportBtn = document.getElementById("exportCsvBtn");
  if (exportBtn) {
    exportBtn.addEventListener("click", () => {
      window.location.href = "/csc/export";
    });
  }

  const actions = [
    ["assignCaseBtn", "assign"],
    ["openCaseBtn", "open"],
    ["resolveCaseBtn", "resolve"],
    ["closeCaseBtn", "close"],
  ];

  actions.forEach(([id, action]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const caseId = btn.dataset.caseId || document.body.dataset.caseId || "";
      if (!caseId) return;
      try {
        await SAPS.api(`${apiBase}/cases/${caseId}/${action}`, { method: "POST" });
        showToast(`Case ${action}ed.`, "ok");
        setTimeout(() => location.reload(), 700);
      } catch (e) {
        showToast(e.message || "Action failed.", "err");
      }
    });
  });

  if (document.getElementById("loginBtn")) {
    const loginBtn = document.getElementById("loginBtn");
    loginBtn.addEventListener("click", async () => {
      const username = document.getElementById("username")?.value?.trim();
      const password = document.getElementById("password")?.value || "";
      if (!username || !password) {
        showToast("Username and password required.", "err");
        return;
      }
      try {
        const result = await SAPS.api("/api/login", { method: "POST", body: { username, password } });
        if (result.token) {
          localStorage.setItem("authToken", result.token);
          window.location.href = "/";
        }
      } catch (e) {
        showToast(e.message || "Login failed.", "err");
      }
    });
  }

  const profileSaveBtn = document.getElementById("saveProfileBtn");
  if (profileSaveBtn) {
    profileSaveBtn.addEventListener("click", async () => {
      const form = document.getElementById("profileForm");
      if (!form) return;
      const payload = Object.fromEntries(new FormData(form).entries());
      try {
        await SAPS.api("/api/profile", { method: "PATCH", body: payload });
        showToast("Profile updated.", "ok");
      } catch (e) {
        showToast(e.message || "Profile update failed.", "err");
      }
    });
  }

  const out = document.getElementById("cscResult");

  // The CSC officer picks a plain-language reason. Behind the scenes we
  // store it as one of three legal ground flags on the Case row. This
  // keeps the database schema aligned with Section 205 and NI 3/2011
  // while presenting an easy-to-understand interface.
  function reasonToGrounds(reason) {
    switch (reason) {
      case "complainant":
        return { ground_sworn_statement: true,
                 ground_officer_present: false,
                 ground_court_order: false };
      case "arrest":
        return { ground_sworn_statement: false,
                 ground_officer_present: true,
                 ground_court_order: false };
      case "court":
        return { ground_sworn_statement: false,
                 ground_officer_present: false,
                 ground_court_order: true };
      case "followup":
        return { ground_sworn_statement: true,
                 ground_officer_present: false,
                 ground_court_order: false };
      case "referred":
        return { ground_sworn_statement: false,
                 ground_officer_present: true,
                 ground_court_order: false };
      default:
        return { ground_sworn_statement: false,
                 ground_officer_present: false,
                 ground_court_order: false };
    }
  }

  function readWeapons() {
    const boxes = document.querySelectorAll("#weaponsGroup input[type=checkbox]");
    const picked = [];
    boxes.forEach(b => { if (b.checked) picked.push(b.value); });
    if (picked.includes("None")) return [];
    return picked.filter(w => w !== "None");
  }

  function clearForm() {
    ["cName","cId","cPhone","cEmail","cLocation","cDesc","cValue","cSuspects",
     "swornRef"].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = "";
    });
    const reasonEl = document.getElementById("cReason");
    const stationEl = document.getElementById("cIncidentStation");
    if (reasonEl) reasonEl.value = "";
    if (stationEl) stationEl.value = "";
    document.querySelectorAll("#weaponsGroup input[type=checkbox]")
      .forEach(b => { b.checked = false; });
    const refWrap = document.getElementById("followupRefWrap");
    const hint = document.getElementById("jurisdictionHint");
    if (refWrap) refWrap.classList.add("hidden");
    if (hint) hint.classList.add("hidden");
  }

  async function submitCase(force) {
    const reasonEl = document.getElementById("cReason");
    const stationEl = document.getElementById("cIncidentStation");

    if (!reasonEl || !reasonEl.value.trim()) {
      SAPS.showResult(out, "Please select why this docket is being opened.", "err");
      if (reasonEl) reasonEl.focus();
      return;
    }

    if (!stationEl || !stationEl.value.trim()) {
      SAPS.showResult(out, "Please select where the crime happened.", "err");
      if (stationEl) stationEl.focus();
      return;
    }

    const grounds = reasonToGrounds(reasonEl.value);
    const body = {
      complainant_name:  document.getElementById("cName").value.trim(),
      complainant_id:    document.getElementById("cId").value.trim(),
      complainant_phone: document.getElementById("cPhone").value.trim(),
      complainant_email: document.getElementById("cEmail").value.trim(),
      crime_type:        document.getElementById("cType").value,
      location:          document.getElementById("cLocation").value.trim(),
      incident_station:  stationEl.value.trim(),
      description:       document.getElementById("cDesc").value.trim(),
      financial_value:   document.getElementById("cValue").value || null,
      num_suspects:      document.getElementById("cSuspects").value || null,
      weapons_involved:  readWeapons(),
      ground_sworn_statement: grounds.ground_sworn_statement,
      ground_officer_present: grounds.ground_officer_present,
      ground_court_order:     grounds.ground_court_order,
      sworn_statement_ref:    (reasonEl.value === "followup" ? document.getElementById("swornRef").value.trim() : ""),
      force_duplicate:   !!force,
    };

    const required = [
      ["cName",     "Complainant full name is required."],
      ["cId",       "SA ID number is required."],
      ["cPhone",    "Phone number is required."],
      ["cEmail",    "Email address is required."],
      ["cLocation", "Location is required."],
      ["cDesc",     "Description is required."],
    ];
    for (const [id, msg] of required) {
      const el = document.getElementById(id);
      if (!el.value.trim()) { SAPS.showResult(out, msg, "err"); el.focus(); return; }
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.complainant_email)) {
      SAPS.showResult(out, "Please enter a valid email address.", "err");
      document.getElementById("cEmail").focus();
      return;
    }

    try {
      const c = await SAPS.api("/api/cases", { method: "POST", body });
      let msg = `Docket <b>${SAPS.esc(c.cas_number)}</b> created. Awaiting verification and classification.`;
      if (c.email && c.email.ok) {
        msg += `<br><span style="color:var(--ok);font-size:12px;">CAS emailed to ${SAPS.esc(body.complainant_email)}.</span>`;
      }
      SAPS.showResult(out, msg, "ok");
      clearForm();
      currentPage = 1;
      loadCases();
    } catch (e) {
      // Duplicate warning path (HTTP 409 from our API)
      if (e.message && e.message.startsWith("A similar docket")) {
        SAPS.showResult(out, SAPS.esc(e.message) +
          `<br><br><button class="btn" id="forceCreateBtn">Create anyway</button>`, "err");
        const fb = document.getElementById("forceCreateBtn");
        if (fb) fb.addEventListener("click", () => submitCase(true));
        return;
      }
      SAPS.showResult(out, SAPS.esc(e.message), "err");
    }
  }

  document.getElementById("createCaseBtn").addEventListener("click", () => submitCase(false));

  // Event listeners for reason and station dropdowns
  const reasonEl = document.getElementById("cReason");
  const stationEl = document.getElementById("cIncidentStation");
  const refWrap = document.getElementById("followupRefWrap");
  const hint = document.getElementById("jurisdictionHint");

  if (reasonEl) {
    reasonEl.addEventListener("change", () => {
      if (reasonEl.value === "followup") {
        refWrap.classList.remove("hidden");
      } else {
        refWrap.classList.add("hidden");
        const swornRefEl = document.getElementById("swornRef");
        if (swornRefEl) swornRefEl.value = "";
      }
    });
  }

  if (stationEl) {
    stationEl.addEventListener("change", () => {
      const userStation = window.SAPS_USER_STATION || "";
      if (!stationEl.value || stationEl.value === userStation) {
        hint.classList.add("hidden");
      } else {
        hint.classList.remove("hidden");
      }
    });
  }

  const searchEl   = document.getElementById("searchText");
  const crimeEl    = document.getElementById("filterCrime");
  const statusEl   = document.getElementById("filterStatus");
  const tierEl     = document.getElementById("filterTier");
  const decisionEl = document.getElementById("filterDecision");
  const fromEl     = document.getElementById("filterDateFrom");
  const toEl       = document.getElementById("filterDateTo");
  const clearEl    = document.getElementById("clearSearch");
  const list       = document.getElementById("cscList");
  const count      = document.getElementById("cscCount");

  let pager = document.getElementById("cscPager");
  if (!pager) {
    pager = document.createElement("div");
    pager.id = "cscPager";
    pager.className = "pager";
    list.parentNode.insertBefore(pager, count);
  }

  let currentPage = 1;
  const PER_PAGE = 20;
  let debounceTimer = null;

  function scheduleLoad(resetPage = true) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      if (resetPage) currentPage = 1;
      loadCases();
    }, 300);
  }

  [searchEl, crimeEl, statusEl, tierEl, decisionEl, fromEl, toEl].forEach(el => {
    if (!el) return;
    el.addEventListener("input", () => scheduleLoad(true));
    el.addEventListener("change", () => scheduleLoad(true));
  });

  clearEl.addEventListener("click", () => {
    [searchEl, crimeEl, fromEl, toEl].forEach(el => { if (el) el.value = ""; });
    statusEl.value = "All";
    tierEl.value = "All";
    decisionEl.value = "All";
    currentPage = 1;
    loadCases();
  });

  function tierSlug(t) {
    return String(t || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  }

  async function verifyCase(id) {
    if (!confirm("Verify this docket? The classification engine will run and a detective will be assigned.")) return;
    try {
      const updated = await SAPS.api(`/api/cases/${id}/verify`, { method: "POST" });
      alert(`Verified.\n\nTier: ${updated.case_tier}\nUnit: ${updated.assigned_unit}\nDetective: ${updated.detective ? updated.detective.full_name : "Awaiting commander"}`);
      loadCases();
    } catch (e) { alert(e.message); }
  }

  async function refuseCase(id) {
    const reasons = window.SAPS_DECISION_REASONS || [];
    const list = reasons.map((r, i) => `${i + 1}. ${r}`).join("\n");
    const pick = prompt(`Select a refusal reason (number):\n\n${list}\n\nOr type the full reason.`);
    if (!pick) return;
    let reason = pick.trim();
    const n = parseInt(pick, 10);
    if (!isNaN(n) && n >= 1 && n <= reasons.length) reason = reasons[n - 1];
    if (!reasons.includes(reason)) { alert("Invalid reason."); return; }

    const note = prompt("Add a short note (optional):") || "";
    try {
      await SAPS.api(`/api/cases/${id}/refuse`, { method: "POST", body: { reason, note } });
      alert("Docket refused. Complainant has been notified.");
      loadCases();
    } catch (e) { alert(e.message); }
  }

  async function transferCase(id) {
    const station = prompt("Transfer to which station?");
    if (!station) return;
    const note = prompt("Reason / note (optional):") || "";
    try {
      await SAPS.api(`/api/cases/${id}/transfer`, { method: "POST", body: { station, note } });
      alert("Docket transferred. Complainant has been notified.");
      loadCases();
    } catch (e) { alert(e.message); }
  }

  async function loadCases() {
    list.innerHTML = "Loading…";

    const params = new URLSearchParams();
    if (searchEl.value.trim()) params.set("q", searchEl.value.trim());
    if (crimeEl.value)          params.set("crime_type", crimeEl.value);
    if (statusEl.value && statusEl.value !== "All") params.set("status", statusEl.value);
    if (tierEl.value && tierEl.value !== "All")     params.set("case_tier", tierEl.value);
    if (decisionEl.value && decisionEl.value !== "All") params.set("decision", decisionEl.value);
    if (fromEl.value)           params.set("date_from", fromEl.value);
    if (toEl.value)             params.set("date_to", toEl.value);
    params.set("page", currentPage);
    params.set("per_page", PER_PAGE);

    try {
      const data = await SAPS.api("/api/cases?" + params.toString());
      const cases = Array.isArray(data && data.cases) ? data.cases : [];
	  const total = Number(data && data.total) || 0;
      count.textContent = total === 0
        ? "0 dockets"
        : `${total} docket${total === 1 ? "" : "s"} · page ${data.page} of ${data.total_pages}`;

      if (!cases.length) {
        list.innerHTML = `<div class="empty-state">No dockets match your search.</div>`;
        SAPS.renderPager({ container: pager });
        return;
      }

      list.innerHTML = cases.map(c => {
        const isUnverified = c.verification_status === "Unverified";
        const decided = c.decision && c.decision !== "Pending";
        const tierBadge = c.case_tier
          ? `<span class="tier-badge tier-${tierSlug(c.case_tier)}">${SAPS.esc(c.case_tier)}</span>`
          : `<span class="tier-badge tier-pending">Unclassified</span>`;

        let actionBtn = "";
        if (isUnverified) {
          actionBtn = `<button class="rc-open verify-btn" data-verify="${c.id}">Verify</button>`;
        } else if (!decided) {
          actionBtn = `<span class="rc-open" style="opacity:.5;cursor:default;">Awaiting approval</span>`;
        } else {
          const label = c.decision === "Refused" ? "Refused"
                      : c.decision === "Transferred" ? "Transferred"
                      : "✓ Live";
          actionBtn = `<span class="rc-open" style="opacity:.6;cursor:default;">${label}</span>`;
        }

        const extraActions = isUnverified ? "" : `
          <div style="flex:1 1 100%;display:flex;gap:6px;margin-top:6px;">
            <button class="btn ghost" data-refuse="${c.id}">Refuse</button>
            <button class="btn ghost" data-transfer="${c.id}">Transfer</button>
          </div>`;

        return `
          <div class="row-card">
            <div>
              <div class="rc-cas">${SAPS.esc(c.cas_number)}</div>
              <div class="rc-sub">${SAPS.esc((c.created_at || "").slice(0,10))}</div>
            </div>
            <div>
              <div class="rc-main">${SAPS.esc(c.crime_type)}</div>
              <div class="rc-sub">${SAPS.esc(c.location)}</div>
            </div>
            <div>
              <div class="rc-main">${SAPS.esc(c.complainant_name)}</div>
              <div class="rc-sub">${SAPS.esc(c.complainant_phone)}</div>
            </div>
            <div>${tierBadge}</div>
            <div>
              <div class="rc-sub">Decision</div>
              <div class="rc-main rc-sub" style="color:var(--ink);font-weight:600;">
                ${SAPS.esc(c.decision || "Pending")}
              </div>
            </div>
            <div>
              <div class="rc-sub">Unit</div>
              <div class="rc-main rc-sub" style="color:var(--ink);font-weight:600;">
                ${SAPS.esc(c.assigned_unit || "—")}
              </div>
            </div>
            <div>
              <div class="rc-sub">Detective</div>
              <div class="rc-main rc-sub" style="color:var(--ink);font-weight:600;">
                ${SAPS.esc(c.detective ? c.detective.full_name : "—")}
              </div>
            </div>
            ${actionBtn}
            ${extraActions}
          </div>`;
      }).join("");

      list.querySelectorAll("[data-verify]").forEach(b =>
        b.addEventListener("click", () => verifyCase(b.dataset.verify)));
      list.querySelectorAll("[data-refuse]").forEach(b =>
        b.addEventListener("click", () => refuseCase(b.dataset.refuse)));
      list.querySelectorAll("[data-transfer]").forEach(b =>
        b.addEventListener("click", () => transferCase(b.dataset.transfer)));

      SAPS.renderPager({
        container: pager,
        page: data.page,
        totalPages: data.total_pages,
        onPage: (n) => { currentPage = n; loadCases(); },
      });
    } catch (e) {
      list.innerHTML = `<div class="empty-state">${SAPS.esc(e.message)}</div>`;
      SAPS.renderPager({ container: pager });
    }
  }

  loadCases();
});