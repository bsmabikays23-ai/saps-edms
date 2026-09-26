/* ==========================================================================
   SAPS eDMS — Shared helpers
   ========================================================================== */

const SAPS = (() => {
  const TOKEN_KEY = "saps_token";
  const USER_KEY  = "saps_user";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function showResult(el, msg, kind = "ok") {
    if (el) el.innerHTML = `<div class="${kind}">${msg}</div>`;
  }

  function getToken() {
    return window.SAPS_TOKEN || sessionStorage.getItem(TOKEN_KEY) || null;
  }

  function getUser() {
    try { return JSON.parse(sessionStorage.getItem(USER_KEY) || "null"); }
    catch { return null; }
  }

  function setSession(token, user) {
    if (token) {
      sessionStorage.setItem(TOKEN_KEY, token);
      sessionStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      sessionStorage.removeItem(TOKEN_KEY);
      sessionStorage.removeItem(USER_KEY);
    }
  }

  async function api(path, { method = "GET", body, json = true, raw = false } = {}) {
    const headers = {};
    const token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;

    const opts = { method, headers };
    if (body !== undefined) {
      if (raw) {
        opts.body = body;
      } else {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
    }

    const res = await fetch(path, opts);
    const ct = res.headers.get("content-type") || "";
    const payload = ct.includes("application/json")
      ? await res.json()
      : await res.text();

    if (!res.ok) {
      if (res.status === 401 || res.status === 403) {
        sessionStorage.clear();
        window.location.href = "/";
        return;
      }
      const msg = (payload && payload.msg) ? payload.msg
                : ("Request failed (" + res.status + ")");
      throw new Error(msg);
    }
    return payload;
  }

  function logout() {
    sessionStorage.clear();
    window.location.href = "/";
  }

  /* ---------------------------------------------------------------------
     Pagination renderer
     opts: { container, page, totalPages, onPage(n) }
     --------------------------------------------------------------------- */
  function renderPager(opts) {
    const { container, page, totalPages, onPage } = opts;
    if (!container) return;

    if (totalPages <= 1) {
      container.innerHTML = "";
      return;
    }

    const mk = (label, target, opts = {}) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "page-btn" + (opts.active ? " active" : "");
      btn.textContent = label;
      if (opts.disabled) {
        btn.disabled = true;
      } else {
        btn.addEventListener("click", () => onPage(target));
      }
      return btn;
    };

    const frag = document.createDocumentFragment();

    // Prev
    frag.appendChild(mk("‹ Prev", page - 1, { disabled: page <= 1 }));

    // Page numbers with ellipses
    const pages = [];
    const add = (n) => pages.push(n);
    const range = (a, b) => { for (let i = a; i <= b; i++) add(i); };

    if (totalPages <= 7) {
      range(1, totalPages);
    } else if (page <= 4) {
      range(1, 5); add("…"); add(totalPages);
    } else if (page >= totalPages - 3) {
      add(1); add("…"); range(totalPages - 4, totalPages);
    } else {
      add(1); add("…"); range(page - 1, page + 1); add("…"); add(totalPages);
    }

    pages.forEach(p => {
      if (p === "…") {
        const span = document.createElement("span");
        span.className = "page-ellipsis";
        span.textContent = "…";
        frag.appendChild(span);
      } else {
        frag.appendChild(mk(String(p), p, { active: p === page }));
      }
    });

    // Next
    frag.appendChild(mk("Next ›", page + 1, { disabled: page >= totalPages }));

    container.innerHTML = "";
    container.appendChild(frag);
  }

  /* ---------------------------------------------------------------------
     Auto-wire common elements
     --------------------------------------------------------------------- */
  document.addEventListener("DOMContentLoaded", () => {
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) logoutBtn.addEventListener("click", logout);

    const profileLink = document.getElementById("profileLink");
    if (profileLink) {
      const token = getToken();
      profileLink.href = "/profile" +
        (token ? "?token=" + encodeURIComponent(token) : "");
    }
  });

  return {
    esc, showResult, api, getToken, getUser, setSession, logout,
    renderPager,
  };
})();