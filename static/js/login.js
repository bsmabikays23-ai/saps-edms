/* ==========================================================================
   SAPS eDMS — Login page controller (with password reset flow)
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

  function startClock() {
    const el = q("liveClock");
    if (!el) return;
    const tick = () => {
      const d = new Date();
      el.textContent =
        String(d.getHours()).padStart(2, "0") + ":" +
        String(d.getMinutes()).padStart(2, "0") + ":" +
        String(d.getSeconds()).padStart(2, "0");
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
    } catch (_) { el.textContent = "local"; }
  }

  function initPasswordToggle() {
    const btn = q("pwToggle");
    const inp = q("officerPassword");
    if (!btn || !inp) return;
    btn.addEventListener("click", () => {
      const hidden = inp.type === "password";
      inp.type = hidden ? "text" : "password";
      btn.setAttribute("aria-pressed", String(hidden));
    });
  }

  function setFieldError(fieldId, show) {
    const f = q(fieldId);
    if (!f) return;
    f.classList.toggle("invalid", !!show);
  }

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
      const label = m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
      showResult(out, `Too many attempts. Try again in <b>${label}</b>.`, "err");
      remaining -= 1;
    };
    render();
    countdownTimer = setInterval(render, 1000);
  }

  async function postJson(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const ct = res.headers.get("content-type") || "";
    const payload = ct.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) {
      const err = new Error((payload && payload.msg) ? payload.msg : ("Request failed (" + res.status + ")"));
      err.status = res.status;
      err.retry_after = (payload && payload.retry_after) || null;
      throw err;
    }
    return payload;
  }

  /* ---------------- Officer login ---------------- */
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
        sessionStorage.setItem("saps_user", JSON.stringify(data.user));
      } catch (_) {}
    }

    function destinationFor(role) {
      if (role === "admin")     return "/commander/personnel";
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
      if (!/^[A-Z0-9]{2,8}$/.test(persalVal)) { setFieldError("fieldPersal", true); bad = true; }
      if (!pwdVal) { setFieldError("fieldPassword", true); bad = true; }
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
          startCountdown(err.retry_after || 60, out, submit);
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

  /* ---------------- Forgot password flow ---------------- */
  function initForgotFlow() {
    const link        = q("forgotPasswordLink");
    const back        = q("backToLoginLink");
    const panelLogin  = q("panelOfficer");
    const panelForgot = q("panelForgot");
    const formForgot  = q("forgotForm");
    const persalEl    = q("forgotPersal");
    const codeEl      = q("resetCode");
    const newPwdEl    = q("newPassword");
    const confirmEl   = q("confirmPassword");
    const sendBtn     = q("sendCodeBtn");
    const resetBtn    = q("resetPasswordBtn");
    const out         = q("forgotResult");
    const stepSend    = q("stepSendCode");
    const stepReset   = q("stepResetPassword");

    if (!link || !panelForgot) return;

    function showForgot() {
      panelLogin.classList.remove("active");
      panelForgot.classList.add("active");
      stepSend.style.display = "block";
      stepReset.style.display = "none";
      clearResult(out);
    }
    function showLogin() {
      panelForgot.classList.remove("active");
      panelLogin.classList.add("active");
      clearResult(out);
    }

    link.addEventListener("click", (e) => { e.preventDefault(); showForgot(); });
    back.addEventListener("click", (e) => { e.preventDefault(); showLogin(); });

    sendBtn.addEventListener("click", async () => {
      const persal = persalEl.value.trim().toUpperCase();
      if (!persal) {
        showResult(out, "Please enter your PERSAL number.", "err");
        return;
      }
      sendBtn.disabled = true;
      const original = sendBtn.textContent;
      sendBtn.textContent = "Sending…";
      try {
        await postJson("/api/auth/forgot-password", { persal_number: persal });
        stepSend.style.display = "none";
        stepReset.style.display = "block";
        showResult(out, "If that account exists, a 6-digit code has been sent to the registered email. Enter it below.", "ok");
      } catch (e) {
        showResult(out, e.message, "err");
      } finally {
        sendBtn.disabled = false;
        sendBtn.textContent = original;
      }
    });

    resetBtn.addEventListener("click", async () => {
      const persal = persalEl.value.trim().toUpperCase();
      const code = codeEl.value.trim();
      const pwd1 = newPwdEl.value;
      const pwd2 = confirmEl.value;

      if (!code || code.length !== 6) {
        showResult(out, "Enter the 6-digit code from your email.", "err"); return;
      }
      if (pwd1.length < 8) {
        showResult(out, "New password must be at least 8 characters.", "err"); return;
      }
      if (pwd1 !== pwd2) {
        showResult(out, "Passwords do not match.", "err"); return;
      }

      resetBtn.disabled = true;
      const original = resetBtn.textContent;
      resetBtn.textContent = "Resetting…";
      try {
        await postJson("/api/auth/reset-password", {
          persal_number: persal,
          code: code,
          new_password: pwd1,
        });
        showResult(out, "Password updated. You can now sign in.", "ok");
        setTimeout(showLogin, 1500);
      } catch (e) {
        showResult(out, e.message, "err");
      } finally {
        resetBtn.disabled = false;
        resetBtn.textContent = original;
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    startClock();
    fetchClientIp();
    initPasswordToggle();
    initOfficerForm();
    initForgotFlow();
  });
})();