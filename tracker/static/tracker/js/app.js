/* ============================================================
   LibTrack AI — UI behaviours
   Custom replacement for Bootstrap's JS bundle.
   Handles: modals, dropdowns, toasts, navbar collapse, theme.
   Reads the existing data-bs-* attributes so templates are
   unchanged.
   ============================================================ */
(function () {
  "use strict";

  /* ---------- Modals ------------------------------------------------ */
  var openModals = [];

  function getBackdrop() {
    var bd = document.querySelector(".modal-backdrop");
    if (!bd) {
      bd = document.createElement("div");
      bd.className = "modal-backdrop";
      document.body.appendChild(bd);
      /* force reflow so the opacity transition runs */
      void bd.offsetWidth;
    }
    return bd;
  }

  function showModal(modal, trigger) {
    if (!modal || modal.classList.contains("show")) return;

    var ev = new Event("show.bs.modal");
    ev.relatedTarget = trigger || null;
    modal.dispatchEvent(ev);

    closeAllDropdowns(null);
    var bd = getBackdrop();
    bd.classList.add("show");
    modal.style.display = "block";
    document.body.classList.add("modal-open");
    /* reflow before adding .show to trigger transition */
    void modal.offsetWidth;
    modal.classList.add("show");
    openModals.push(modal);

    var focusable = modal.querySelector(
      "input:not([type=hidden]), textarea, select, button"
    );
    if (focusable) {
      try { focusable.focus(); } catch (e) {}
    }
  }

  function hideModal(modal) {
    if (!modal || !modal.classList.contains("show")) return;

    modal.dispatchEvent(new Event("hide.bs.modal"));
    modal.classList.remove("show");
    openModals = openModals.filter(function (m) { return m !== modal; });

    window.setTimeout(function () {
      if (!modal.classList.contains("show")) {
        modal.style.display = "none";
      }
    }, 220);

    if (openModals.length === 0) {
      document.body.classList.remove("modal-open");
      var bd = document.querySelector(".modal-backdrop");
      if (bd) {
        bd.classList.remove("show");
        window.setTimeout(function () {
          if (bd && !bd.classList.contains("show") && bd.parentNode) {
            bd.parentNode.removeChild(bd);
          }
        }, 220);
      }
    }
  }

  /* Open triggers */
  document.addEventListener("click", function (e) {
    var trigger = e.target.closest('[data-bs-toggle="modal"]');
    if (trigger) {
      e.preventDefault();
      var sel = trigger.getAttribute("data-bs-target");
      var modal = sel ? document.querySelector(sel) : null;
      if (modal) showModal(modal, trigger);
      return;
    }

    /* Dismiss triggers */
    var dismiss = e.target.closest('[data-bs-dismiss="modal"]');
    if (dismiss) {
      e.preventDefault();
      var dm = dismiss.closest(".modal");
      if (dm) hideModal(dm);
      return;
    }

    /* Click on backdrop area of a modal closes it */
    if (e.target.classList && e.target.classList.contains("modal")) {
      hideModal(e.target);
    }
  });

  /* Esc closes the topmost modal */
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && openModals.length) {
      hideModal(openModals[openModals.length - 1]);
    }
  });

  /* ---------- Dropdowns -------------------------------------------- */
  function closeAllDropdowns(except) {
    document.querySelectorAll(".dropdown-menu.show").forEach(function (menu) {
      if (menu !== except) menu.classList.remove("show");
    });
  }

  document.addEventListener("click", function (e) {
    var toggle = e.target.closest('[data-bs-toggle="dropdown"]');
    if (toggle) {
      e.preventDefault();
      var parent = toggle.closest(".dropdown");
      var menu = parent ? parent.querySelector(".dropdown-menu") : null;
      if (menu) {
        var willShow = !menu.classList.contains("show");
        closeAllDropdowns(menu);
        menu.classList.toggle("show", willShow);
      }
      return;
    }
    /* clicking inside an open menu (not a dismiss link) keeps it; any
       other click closes all menus */
    if (!e.target.closest(".dropdown-menu")) {
      closeAllDropdowns(null);
    }
  });

  /* ---------- Navbar collapse -------------------------------------- */
  document.addEventListener("click", function (e) {
    var toggler = e.target.closest('[data-bs-toggle="collapse"]');
    if (!toggler) return;
    e.preventDefault();
    var sel = toggler.getAttribute("data-bs-target");
    var target = sel ? document.querySelector(sel) : null;
    if (target) {
      target.classList.toggle("show");
      toggler.setAttribute(
        "aria-expanded",
        target.classList.contains("show") ? "true" : "false"
      );
    }
  });

  /* ---------- Toasts ----------------------------------------------- */
  function showToast(toast) {
    var delay = parseInt(toast.getAttribute("data-bs-delay"), 10);
    if (isNaN(delay)) delay = 5000;

    void toast.offsetWidth;
    toast.classList.add("show");

    var timer = window.setTimeout(function () {
      dismissToast(toast);
    }, delay);
    toast._ltTimer = timer;
  }

  function dismissToast(toast) {
    if (toast._ltTimer) window.clearTimeout(toast._ltTimer);
    toast.classList.remove("show");
    toast.classList.add("hide");
    window.setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 320);
  }

  document.addEventListener("click", function (e) {
    var dismiss = e.target.closest('[data-bs-dismiss="toast"]');
    if (dismiss) {
      var t = dismiss.closest(".toast");
      if (t) dismissToast(t);
    }
  });

  /* ---------- Theme toggle ----------------------------------------- */
  function initTheme() {
    var root = document.documentElement;
    var buttons = Array.prototype.slice.call(
      document.querySelectorAll("[data-theme-toggle]")
    );

    function syncIcon() {
      var dark = root.getAttribute("data-bs-theme") === "dark";
      buttons.forEach(function (btn) {
        btn.innerHTML = dark
          ? '<i class="bi bi-sun-fill"></i>'
          : '<i class="bi bi-moon-stars-fill"></i>';
        btn.setAttribute(
          "aria-label",
          dark ? "Switch to light mode" : "Switch to dark mode"
        );
      });
    }
    syncIcon();

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var next =
          root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
        root.setAttribute("data-bs-theme", next);
        try { localStorage.setItem("lt-theme", next); } catch (e) {}
        syncIcon();
        document.dispatchEvent(
          new CustomEvent("lt-theme-change", { detail: next })
        );
      });
    });
  }

  /* ---------- Init -------------------------------------------------- */
  document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    document.querySelectorAll(".toast").forEach(showToast);
  });
})();
