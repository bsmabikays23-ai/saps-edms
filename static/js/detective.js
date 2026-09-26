document.addEventListener("DOMContentLoaded", () => {
  const token = SAPS.getToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";

  const searchEl  = document.getElementById("searchText");
  const crimeEl   = document.getElementById("filterCrime");
  const statusEl  = document.getElementById("filterStatus");
  const fromEl    = document.getElementById("filterDateFrom");
  const toEl      = document.getElementById("filterDateTo");
  const clearEl   = document.getElementById("clearSearch");
  const list      = document.getElementById("detList");
  const count     = document.getElementById("detCount");

  // Add a pager container right after the list if it doesn't exist
  let pager = document.getElementById("detPager");
  if (!pager) {
    pager = document.createElement("div");
    pager.id = "detPager";
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
            <div class="rc-sub">Opened</div>
            <div class="rc-main rc-sub" style="color:var(--ink);font-weight:600;">
              ${SAPS.esc((c.created_at || "").slice(0,10))}
            </div>
          </div>
          <div class="rc-num">${c.evidence_count}<div class="rc-sub">files</div></div>
          <div class="rc-num">${c.milestone_count}<div class="rc-sub">steps</div></div>
          <a class="rc-open" href="/detective/case/${c.id}${qs}">Open →</a>
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