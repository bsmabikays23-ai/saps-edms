document.addEventListener("DOMContentLoaded", () => {
  const token = window.SAPS_TOKEN || SAPS.getToken();
  const c = window.SAPS_CASE || {};

  const back = document.getElementById("backToList");
  if (back) {
    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    back.href = "/detective" + qs;
  }

  const statusSelect = document.getElementById("statusSelect");
  const statusBtn = document.getElementById("saveStatusBtn");
  const statusMsg = document.getElementById("statusMsg");

  const msTitle = document.getElementById("msTitle");
  const msDetail = document.getElementById("msDetail");
  const msBtn = document.getElementById("addMilestoneBtn");
  const msResult = document.getElementById("msResult");

  const evFile = document.getElementById("evFile");
  const evBtn = document.getElementById("uploadEvidenceBtn");
  const evResult = document.getElementById("evResult");
  const evList = document.getElementById("evidenceList");

  const timeline = document.getElementById("timelineList");

  const closureReason = document.getElementById("closureReason");
  const closureRef = document.getElementById("closureRef");
  const closureNote = document.getElementById("closureNote");
  const closeBtn = document.getElementById("closeCaseBtn");
  const closeResult = document.getElementById("closeResult");

  if (statusBtn && statusSelect && statusMsg) {
    statusBtn.addEventListener("click", async () => {
      statusMsg.textContent = "";
      statusMsg.className = "inline-msg";
      try {
        const updated = await SAPS.api(`/api/cases/${c.id}/status`, {
          method: "PATCH",
          body: { status: statusSelect.value },
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
      if (!reason) {
        SAPS.showResult(closeResult, "Select a closure reason.", "err");
        return;
      }
      if (!confirm(`Close docket ${c.cas_number}?\n\nReason: ${reason}`)) return;

      try {
        await SAPS.api(`/api/cases/${c.id}/close`, {
          method: "POST",
          body: {
            reason,
            reference: closureRef ? closureRef.value.trim() : "",
            note: closureNote ? closureNote.value.trim() : "",
          },
        });
        SAPS.showResult(closeResult, "Docket closed. Complainant has been notified.", "ok");
        setTimeout(() => location.reload(), 900);
      } catch (e) {
        SAPS.showResult(closeResult, SAPS.esc(e.message), "err");
      }
    });
  }

  if (msBtn && msTitle && msDetail && msResult) {
    msBtn.addEventListener("click", async () => {
      const title = msTitle.value.trim();
      const detail = msDetail.value.trim();
      if (!title) {
        SAPS.showResult(msResult, "Milestone title is required.", "err");
        msTitle.focus();
        return;
      }

      try {
        await SAPS.api(`/api/cases/${c.id}/milestones`, {
          method: "POST",
          body: { title, detail },
        });
        SAPS.showResult(msResult, "Milestone posted and complainant notified.", "ok");
        msTitle.value = "";
        msDetail.value = "";
        setTimeout(() => location.reload(), 700);
      } catch (e) {
        SAPS.showResult(msResult, SAPS.esc(e.message), "err");
      }
    });
  }

  if (evBtn && evFile && evResult) {
    evBtn.addEventListener("click", async () => {
      if (!evFile.files.length) {
        SAPS.showResult(evResult, "Choose a file first.", "err");
        return;
      }

      const fd = new FormData();
      fd.append("file", evFile.files[0]);

      try {
        await SAPS.api(`/api/cases/${c.id}/evidence`, {
          method: "POST",
          body: fd,
          raw: true,
        });
        SAPS.showResult(evResult, "Evidence uploaded.", "ok");
        evFile.value = "";
        setTimeout(() => location.reload(), 700);
      } catch (e) {
        SAPS.showResult(evResult, SAPS.esc(e.message), "err");
      }
    });
  }

  if (evList) {
    const evidence = c.evidence || [];
    if (!evidence.length) {
      evList.innerHTML = `<div class="empty-state">No evidence uploaded yet.</div>`;
    } else {
      evList.innerHTML = evidence.map((e) => `
        <div class="item"><div class="row">
          <div><div class="k">File</div><div class="v small"><a href="/api/cases/${c.id}/evidence/${e.id}?token=${encodeURIComponent(token || "")}" target="_blank" rel="noopener">${SAPS.esc(e.filename)}</a></div></div>
          <div><div class="k">Size</div><div class="v small">${(e.file_size / 1024).toFixed(1)} KB</div></div>
          <div><div class="k">Uploaded by</div><div class="v small">${SAPS.esc(e.uploaded_by)}</div></div>
          <div><div class="k">When</div><div class="v small">${new Date(e.uploaded_at).toLocaleString()}</div></div>
          <div><div class="k">SHA-256</div><div class="v small mono">${SAPS.esc(e.file_hash.slice(0, 16))}…</div></div>
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
          <div><div class="k">Step ${i + 1}</div><div class="v">${SAPS.esc(m.title)}</div></div>
          <div><div class="k">Detail</div><div class="v small">${SAPS.esc(m.detail || "")}</div></div>
          <div><div class="k">Posted by</div><div class="v small">${SAPS.esc(m.posted_by)}</div></div>
          <div><div class="k">When</div><div class="v small">${new Date(m.created_at).toLocaleString()}</div></div>
        </div></div>`).join("");
    }
  }
});
