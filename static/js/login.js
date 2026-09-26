/* ==========================================================================
   SAPS eDMS — Login page controller
   ========================================================================== */

(function () {
  "use strict";

  function q(id) { return document.getElementById(id); }

  function showResult(el, msg, kind) {
    if (!el) return;
    el.innerHTML = msg;
    el.className = "result show " + (kind === "err" ? "err" : "ok");
  }

  function clearResult(el) {
    if (!el) return;
    el.innerHTML = "";
    el.className = "result";
  }

  /* ---------- Live clock + client IP ------------------------------------- */
  function startClock() {
    const el = q("liveClock");
    if (!el) return;
    const tick = () => {
      const d = new Date();
      const hh = String(d.getHours()).padStart(2, "0");
      const mm = String(d.getMinutes()).padStart(2, "0");
      const ss = String(d.getSeconds()).padStart(2, "0");
      el.textContent = `${hh}:${mm}:${ss}`;
    };
    tick();
    setInterval(tick, 1000);
  }

  async function fetchClientIp() {
    const el = q("clientIp");
    if (!el) return;
    try {
      const r = await fetch("https://api.ipify.org?format=json");
      const j = await r.json();
      el.textContent = j.ip || "—";
    } catch (_) {
      el.textContent = "local";
    }
  }

  /* ---------- Password visibility toggle -------------------------------- */
  function initPasswordToggle() {
    const btn = q("pwToggle");
    const inp = q("officerPassword");
    if (!btn || !inp) return;
    btn.addEventListener("click", () => {
      const isHidden = inp.type === "password";
      inp.type = isHidden ? "text" : "password";
      btn.setAttribute("aria-pressed", String(isHidden));
      btn.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
    });
  }

  /* ---------- Validation ------------------------------------------------ */
  function setFieldError(fieldId, show) {
    const f = q(fieldId);
    if (!f) return;
    f.classList.toggle("invalid", !!show);
  }

  function validatePersal(value) {
    return /^[A-Z0-9]{2,8}$/.test(value);
  }

  /* ---------- Rate limit countdown -------------------------------------- */
  let countdownTimer = null;

  function startCountdown(seconds, out, submit) {
    if (countdownTimer) clearInterval(countdownTimer);
    let remaining = seconds;

    const render = () => {
      if (remaining <= 0) {
        clearInterval(countdownTimer);
        countdownTimer = null;
        submit.disabled = false;
        submit.textContent = "Authenticate";
        clearResult(out);
        return;
      }
      const m = Math.floor(remaining / 60);
      const s = remaining % 60;
      const label = m > 0
        ? `${m}m ${String(s).padStart(2, "0")}s`
        : `${s}s`;
      showResult(
        out,
        `Too many attempts. Try again in <b>${label}</b>.`,
        "err"
      );
      remaining -= 1;
    };

    render();
    countdownTimer = setInterval(render, 1000);
  }

  /* ---------- Server call ----------------------------------------------- */
  async function postJson(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const ct = res.headers.get("content-type") || "";
    const payload = ct.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) {
      const err = new Error(
        (payload && payload.msg) ? payload.msg : ("Request failed (" + res.status + ")")
      );
      err.status = res.status;
      err.retry_after = (payload && payload.retry_after) || null;
      throw err;
    }
    return payload;
  }

  /* ---------- Officer login --------------------------------------------- */
  function initOfficerForm() {
    const form   = q("officerForm");
    const persal = q("persalNumber");
    const pwd    = q("officerPassword");
    const submit = q("officerSubmit");
    const out    = q("officerResult");
    if (!form) return;

    function persistSession(data) {
      try {
        sessionStorage.setItem("saps_token", data.access_token);
        sessionStorage.setItem("saps_user",  JSON.stringify(data.user));
      } catch (_) { /* ignore */ }
    }

    function destinationFor(role) {
      if (role === "commander") return "/commander";
      if (role === "csc")       return "/csc";
      if (role === "detective") return "/detective";
      return null;
    }

    persal.addEventListener("input", () => {
      persal.value = persal.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
      setFieldError("fieldPersal", false);
    });
    pwd.addEventListener("input", () => setFieldError("fieldPassword", false));

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearResult(out);

      const persalVal = persal.value.trim().toUpperCase();
      const pwdVal    = pwd.value;

      let bad = false;
      if (!validatePersal(persalVal)) { setFieldError("fieldPersal", true); bad = true; }
      if (!pwdVal)                    { setFieldError("fieldPassword", true); bad = true; }
      if (bad) {
        showResult(out, "Please correct the highlighted fields.", "err");
        return;
      }

      const originalLabel = submit.textContent;
      submit.disabled = true;
      submit.textContent = "Authenticating…";

      let rateLimited = false;

      try {
        const data = await postJson("/api/auth/login", {
          persal_number: persalVal, password: pwdVal,
        });
        persistSession(data);
        showResult(out, "Authenticated. Redirecting…", "ok");
        const dest = destinationFor(data.user.role);
        if (!dest) {
          showResult(out, "Unknown role on this account.", "err");
          return;
        }
        window.location.href = `${dest}?token=${encodeURIComponent(data.access_token)}`;
      } catch (err) {
        if (err.status === 429) {
          rateLimited = true;
          const seconds = err.retry_after || 60;
          startCountdown(seconds, out, submit);
        } else if (/invalid credentials/i.test(err.message || "")) {
          showResult(out, "Invalid PERSAL number or password.", "err");
        } else {
          showResult(out, err.message || "Authentication failed.", "err");
        }
      } finally {
        if (!rateLimited) {
          submit.disabled = false;
          submit.textContent = originalLabel;
        }
      }
    });
  }

  /* ---------- Boot ------------------------------------------------------ */
  document.addEventListener("DOMContentLoaded", () => {
    startClock();
    fetchClientIp();
    initPasswordToggle();
    initOfficerForm();
  });
})();