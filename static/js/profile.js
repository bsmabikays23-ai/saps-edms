/* ==========================================================================
   SAPS eDMS — My Profile page controller
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

  function setFieldError(fieldId, show) {
    const f = q(fieldId);
    if (!f) return;
    f.classList.toggle("invalid", !!show);
  }

  function wireBackLink() {
    const back = q("backLink");
    if (!back) return;
    const token = SAPS.getToken();
    const qs = token ? `?token=${encodeURIComponent(token)}` : "";
    const role = window.SAPS_USER_ROLE || (SAPS.getUser() || {}).role;
    const dest = role === "commander" ? "/commander"
                : role === "csc"      ? "/csc"
                : role === "detective"? "/detective"
                : "/";
    back.href = dest + qs;
  }

  function wireToggle(btnId, inputId) {
    const btn = q(btnId);
    const inp = q(inputId);
    if (!btn || !inp) return;
    btn.addEventListener("click", () => {
      const hidden = inp.type === "password";
      inp.type = hidden ? "text" : "password";
      btn.setAttribute("aria-pressed", String(hidden));
      btn.setAttribute("aria-label", hidden ? "Hide password" : "Show password");
    });
  }

  function passwordError(pwd) {
    if (!pwd || pwd.length < 8) return "Password must be at least 8 characters.";
    if (!/[0-9]/.test(pwd))     return "Password must contain at least one digit.";
    if (!/[A-Za-z]/.test(pwd))  return "Password must contain at least one letter.";
    return null;
  }

  function initChangePassword() {
    const btn = q("changePwBtn");
    if (!btn) return;

    const currentEl = q("currentPassword");
    const newEl     = q("newPassword");
    const confirmEl = q("confirmPassword");
    const out       = q("pwResult");

    [currentEl, newEl, confirmEl].forEach(el => {
      el.addEventListener("input", () => {
        setFieldError("fieldCurrent", false);
        setFieldError("fieldNew", false);
        setFieldError("fieldConfirm", false);
        clearResult(out);
      });
    });

    btn.addEventListener("click", async () => {
      clearResult(out);
      setFieldError("fieldCurrent", false);
      setFieldError("fieldNew", false);
      setFieldError("fieldConfirm", false);

      const current = currentEl.value;
      const next    = newEl.value;
      const confirm = confirmEl.value;

      let bad = false;
      if (!current) { setFieldError("fieldCurrent", true); bad = true; }

      const ruleErr = passwordError(next);
      if (ruleErr) { setFieldError("fieldNew", true); bad = true; }

      if (next !== confirm) { setFieldError("fieldConfirm", true); bad = true; }

      if (bad) {
        showResult(out, ruleErr || "Please correct the highlighted fields.", "err");
        return;
      }

      btn.disabled = true;
      const original = btn.textContent;
      btn.textContent = "Updating…";

      try {
        await SAPS.api("/api/auth/change-password", {
          method: "POST",
          body: { current_password: current, new_password: next },
        });
        showResult(out, "Password updated successfully.", "ok");
        currentEl.value = "";
        newEl.value = "";
        confirmEl.value = "";
      } catch (e) {
        showResult(out, SAPS.esc(e.message), "err");
      } finally {
        btn.disabled = false;
        btn.textContent = original;
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    wireBackLink();
    wireToggle("pwToggle1", "currentPassword");
    wireToggle("pwToggle2", "newPassword");
    wireToggle("pwToggle3", "confirmPassword");
    initChangePassword();
  });
})();