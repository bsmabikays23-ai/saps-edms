document.addEventListener("DOMContentLoaded", () => {
  const out = document.getElementById("cscResult");

  /* ---------------- Register new docket ---------------- */
  document.getElementById("createCaseBtn").addEventListener("click", async () => {
    const body = {
      complainant_name:  document.getElementById("cName").value.trim(),
      complainant_id:    document.getElementById("cId").value.trim(),
      complainant_phone: document.getElementById("cPhone").value.trim(),
      complainant_email: document.getElementById("cEmail").value.trim(),
      crime_type:        document.getElementById("cType").value,
      location:          document.getElementById("cLocation").value.trim(),
      description:       document.getElementById("cDesc").value.trim(),
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
      if (!el.value.trim()) {
        SAPS.showResult(out, msg, "err");
        el.focus();
        return;
      }
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.complainant_email)) {
      SAPS.showResult(out, "Please enter a valid email address.", "err");
      document.getElementById("cEmail").focus();
      return;
    }

    try {
      const c = await SAPS.api("/api/cases", { method: "POST", body });

      let msg = `Docket <b>${SAPS.esc(c.cas_number)}</b> created and assigned to ` +
                `<b>${SAPS.esc(c.detective.full_name)}</b>.`;
      if (c.email && c.email.ok) {
        msg += `<br><span style="color:var(--ok);font-size:12px;">` +
               `CAS number emailed to ${SAPS.esc(body.complainant_email)}.</span>`;
      } else if (c.email && c.email.error) {
        msg += `<br><span style="color:var(--danger);font-size:12px;">` +
               `Email not sent: ${SAPS.esc(c.email.error)}</span>`;
      }
      SAPS.showResult(out, msg, "ok");

      ["cName","cId","cPhone","cEmail","cLocation","cDesc"].forEach(id => {
        document.getElementById(id).value = "";
      });
      currentPage = 1;
      loadCases();
    } catch (e) {
      SAPS.showResult(out, SAPS.esc(e.message), "err");
    }
  });

  /* ---------------- Search + filter state ---------------- */
  const searchEl  = document.getElementById("searchText");
  const crimeEl   = document.getElementById("filterCrime");
  const statusEl  = document.getElementById("filterStatus");
  const fromEl    = document.getElementById("filterDateFrom");
  const toEl      = document.getElementById("filterDateTo");
  const clearEl   = document.getElementById("clearSearch");
  const list      = document.getElementById("cscList");
  const count     = document.getElementById("cscCount");

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

  [searchEl, crimeEl, statusEl, fromEl, toEl].forEach(el => {
    el.addEventListener("input", () => scheduleLoad(true));
    el.addEventListener("change", () => scheduleLoad(true));
  });

  clearEl.addEventListener("click", () => {
    searchEl.value = "";
    crimeEl.value = "";
    statusEl.value = "All";
    fromEl.value = "";
    toEl.value = "";
    currentPage = 1;
    loadCases();
  });

  async function loadCases() {
    list.innerHTML = "Loading…";

    const params = new URLSearchParams();
    if (searchEl.value.trim()) params.set("q", searchEl.value.trim());
    if (crimeEl.value)         params.set("crime_type", crimeEl.value);
    if (statusEl.value && statusEl.value !== "All")
      params.set("status", statusEl.value);
    if (fromEl.value)          params.set("date_from", fromEl.value);
    if (toEl.value)            params.set("date_to", toEl.value);
    params.set("page", currentPage);
    params.set("per_page", PER_PAGE);

    try {
      const data = await SAPS.api("/api/cases?" + params.toString());
      const cases = data.cases || [];

      count.textContent = data.total === 0
        ? "0 dockets"
        : `${data.total} docket${data.total === 1 ? "" : "s"} · page ${data.page} of ${data.total_pages}`;

      if (!cases.length) {
        list.innerHTML = `<div class="empty-state">No dockets match your search.</div>`;
        SAPS.renderPager({ container: pager });
        return;
      }

      list.innerHTML = cases.map(c => `
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
          <div><span class="badge-status">${SAPS.esc(c.status)}</span></div>
          <div>
            <div class="rc-sub">Detective</div>
            <div class="rc-main rc-sub" style="color:var(--ink);font-weight:600;">
              ${SAPS.esc(c.detective ? c.detective.full_name : "—")}
            </div>
          </div>
          <div class="rc-num">${c.evidence_count}<div class="rc-sub">files</div></div>
          <div class="rc-num">${c.milestone_count}<div class="rc-sub">steps</div></div>
          <button class="rc-open" disabled title="CSC officers cannot modify cases">View</button>
        </div>
      `).join("");

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