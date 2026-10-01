document.addEventListener("DOMContentLoaded", () => {
  const token = SAPS.getToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";

  const detList = document.getElementById("detList");
  const detCount = document.getElementById("detCount");
  const searchText = document.getElementById("searchText");
  const filterCrime = document.getElementById("filterCrime");
  const filterStatus = document.getElementById("filterStatus");
  const filterDateFrom = document.getElementById("filterDateFrom");
  const filterDateTo = document.getElementById("filterDateTo");
  const clearSearch = document.getElementById("clearSearch");

  const CASE_PAGE = "/detective/case/";
  let currentPage = 1;
  const PER_PAGE = 20;

  function getCaseLink(caseId) {
    return `${CASE_PAGE}${caseId}${qs}`;
  }

  function renderCaseCard(c) {
    const status = c.status || "Open";
    const caseLink = getCaseLink(c.id);
    const tier = c.case_tier ? SAPS.esc(c.case_tier) : "Unclassified";
    const assigned = c.detective ? SAPS.esc(c.detective.full_name) : "Unassigned";

    return `
      <div class="item">
        <div class="row">
          <div><div class="k">CAS</div><div class="v">${SAPS.esc(c.cas_number)}</div></div>
          <div><div class="k">Crime</div><div class="v small">${SAPS.esc(c.crime_type)}</div></div>
          <div><div class="k">Location</div><div class="v small">${SAPS.esc(c.location)}</div></div>
          <div><div class="k">Complainant</div><div class="v small">${SAPS.esc(c.complainant_name)}</div></div>
          <div><div class="k">Phone</div><div class="v small">${SAPS.esc(c.complainant_phone)}</div></div>
          <div><div class="k">Status</div><div class="v small">${SAPS.esc(status)}</div></div>
          <div><div class="k">Tier</div><div class="v small">${tier}</div></div>
          <div><div class="k">Assigned to</div><div class="v small">${assigned}</div></div>
          <div style="flex:1 1 100%;display:flex;justify-content:flex-end;">
            <a class="btn ghost" href="${caseLink}">Open case</a>
          </div>
        </div>
      </div>`;
  }

  async function loadAssignedCases() {
    if (!detList) return;
    detList.innerHTML = "Loading…";

    const params = new URLSearchParams();
    const searchValue = (searchText ? searchText.value : "").trim();
    if (searchValue) params.set("q", searchValue);
    if (filterCrime && filterCrime.value) params.set("crime_type", filterCrime.value);
    if (filterStatus && filterStatus.value && filterStatus.value !== "All") params.set("status", filterStatus.value);
    if (filterDateFrom && filterDateFrom.value) params.set("date_from", filterDateFrom.value);
    if (filterDateTo && filterDateTo.value) params.set("date_to", filterDateTo.value);
    params.set("page", String(currentPage));
    params.set("per_page", String(PER_PAGE));

    try {
      const data = await SAPS.api("/api/cases?" + params.toString());
      const cases = Array.isArray(data && data.cases) ? data.cases : [];
      const total = Number(data && data.total) || 0;

      if (detCount) {
        detCount.textContent = total === 0
          ? "0 dockets"
          : `${total} docket${total === 1 ? "" : "s"}`;
      }

      if (!cases.length) {
        detList.innerHTML = `<div class="empty-state">No assigned dockets found.</div>`;
        return;
      }

      detList.innerHTML = cases.map(renderCaseCard).join("");
    } catch (e) {
      detList.innerHTML = `<div class="empty-state">${SAPS.esc(e.message)}</div>`;
      if (detCount) detCount.textContent = "0 dockets";
    }
  }

  const back = document.getElementById("backToList");
  if (back) back.href = "/detective" + qs;

  const c = window.SAPS_CASE || {};
  const statusSelect = document.getElementById("statusSelect");
  const statusBtn    = document.getElementById("saveStatusBtn");
  const statusMsg    = document.getElementById("statusMsg");

  const msTitle  = document.getElementById("msTitle");
  const msDetail = document.getElementById("msDetail");
  const msBtn    = document.getElementById("addMilestoneBtn");
  const msResult = document.getElementById("msResult");

  const evFile   = document.getElementById("evFile");
  const evBtn    = document.getElementById("uploadEvidenceBtn");
  const evResult = document.getElementById("evResult");
  const evList   = document.getElementById("evidenceList");

  const timeline = document.getElementById("timelineList");

  const closureReason = document.getElementById("closureReason");
  const closureRef    = document.getElementById("closureRef");
  const closureNote   = document.getElementById("closureNote");
  const closeBtn      = document.getElementById("closeCaseBtn");
  const closeResult   = document.getElementById("closeResult");

  if (searchText) searchText.addEventListener("input", () => { currentPage = 1; loadAssignedCases(); });
  if (filterCrime) filterCrime.addEventListener("change", () => { currentPage = 1; loadAssignedCases(); });
  if (filterStatus) filterStatus.addEventListener("change", () => { currentPage = 1; loadAssignedCases(); });
  if (filterDateFrom) filterDateFrom.addEventListener("change", () => { currentPage = 1; loadAssignedCases(); });
  if (filterDateTo) filterDateTo.addEventListener("change", () => { currentPage = 1; loadAssignedCases(); });
  if (clearSearch) clearSearch.addEventListener("click", () => {
    if (searchText) searchText.value = "";
    if (filterCrime) filterCrime.value = "";
    if (filterStatus) filterStatus.value = "All";
    if (filterDateFrom) filterDateFrom.value = "";
    if (filterDateTo) filterDateTo.value = "";
    currentPage = 1;
    loadAssignedCases();
  });

  if (detList) loadAssignedCases();

  if (statusBtn && statusSelect && statusMsg) {
    statusBtn.addEventListener("click", async () => {
      statusMsg.textContent = "";
      statusMsg.className = "inline-msg";
      try {
        const updated = await SAPS.api(`/api/cases/${c.id}/status`, {
          method: "PATCH", body: { status: statusSelect.value },
        });
        statusMsg.textContent = "Saved.";
        statusMsg.classList.add("ok");
        const pill = document.querySelector(".case-status");
        if (pill) {
          pill.textContent = updated.status;
          pill.className = "case-status status-" + updated.status.toLowerCase().replace(/\s+/g, "-");
        }
        setTimeout(() => location.reload(), 700);
      } catch (e) {
        statusMsg.textContent = e.message;
        statusMsg.classList.add("err");
      }
    });
  }

  if (closeBtn && closureReason && closeResult) {
    closeBtn.addEventListener("click", async () => {
      const reason = closureReason.value;
      if (!reason) { SAPS.showResult(closeResult, "Select a closure reason.", "err"); return; }
      if (!confirm(`Close docket ${c.cas_number}?\n\nReason: ${reason}`)) return;
      try {
        await SAPS.api(`/api/cases/${c.id}/close`, {
          method: "POST",
          body: { reason, reference: closureRef ? closureRef.value.trim() : "", note: closureNote ? closureNote.value.trim() : "" },
        });
        SAPS.showResult(closeResult, "Docket closed. Complainant has been notified.", "ok");
        setTimeout(() => location.reload(), 900);
      } catch (e) { SAPS.showResult(closeResult, SAPS.esc(e.message), "err"); }
    });
  }

  if (msBtn && msTitle && msDetail && msResult) {
    msBtn.addEventListener("click", async () => {
      const title = msTitle.value.trim();
      const detail = msDetail.value.trim();
      if (!title) { SAPS.showResult(msResult, "Milestone title is required.", "err"); msTitle.focus(); return; }
      try {
        await SAPS.api(`/api/cases/${c.id}/milestones`, { method: "POST", body: { title, detail } });
        SAPS.showResult(msResult, "Milestone posted and complainant notified.", "ok");
        msTitle.value = ""; msDetail.value = "";
        setTimeout(() => location.reload(), 700);
      } catch (e) { SAPS.showResult(msResult, SAPS.esc(e.message), "err"); }
    });
  }

  if (evBtn && evFile && evResult) {
    evBtn.addEventListener("click", async () => {
      if (!evFile.files.length) { SAPS.showResult(evResult, "Choose a file first.", "err"); return; }
      const fd = new FormData();
      fd.append("file", evFile.files[0]);
      try {
        await SAPS.api(`/api/cases/${c.id}/evidence`, { method: "POST", body: fd, raw: true });
        SAPS.showResult(evResult, "Evidence uploaded.", "ok");
        evFile.value = "";
        setTimeout(() => location.reload(), 700);
      } catch (e) { SAPS.showResult(evResult, SAPS.esc(e.message), "err"); }
    });
  }

  if (evList) {
    const evidence = c.evidence || [];
    if (!evidence.length) {
      evList.innerHTML = `<div class="empty-state">No evidence uploaded yet.</div>`;
    } else {
      evList.innerHTML = evidence.map(e => `
        <div class="item"><div class="row">
          <div><div class="k">File</div><div class="v small">${SAPS.esc(e.filename)}</div></div>
          <div><div class="k">Size</div><div class="v small">${(e.file_size/1024).toFixed(1)} KB</div></div>
          <div><div class="k">Uploaded by</div><div class="v small">${SAPS.esc(e.uploaded_by)}</div></div>
          <div><div class="k">When</div><div class="v small">${new Date(e.uploaded_at).toLocaleString()}</div></div>
          <div><div class="k">SHA-256</div><div class="v small mono">${SAPS.esc(e.file_hash.slice(0,16))}…</div></div>
        </div></div>`).join("");
    }
  }

  if (timeline) {
    const milestones = c.milestones || [];
    if (!milestones.length) {
      timeline.innerHTML = `<div class="empty-state">No milestones yet.</div>`;
    } else {
      timeline.innerHTML = milestones.map((m, i) => `
        <div class="item"><div class="row">
          <div><div class="k">Step ${i+1}</div><div class="v">${SAPS.esc(m.title)}</div></div>
          <div><div class="k">Detail</div><div class="v small">${SAPS.esc(m.detail || "")}</div></div>
          <div><div class="k">Posted by</div><div class="v small">${SAPS.esc(m.posted_by)}</div></div>
          <div><div class="k">When</div><div class="v small">${new Date(m.created_at).toLocaleString()}</div></div>
        </div></div>`).join("");
    }
  }
});