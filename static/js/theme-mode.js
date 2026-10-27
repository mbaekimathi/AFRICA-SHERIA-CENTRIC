/* theme-mode.js — light/dark controller.
   Initial mode is applied before first paint by the inline script in each
   layout <head> (same logic, duplicated so no JS file is render-blocking).
   This file wires [data-mode-toggle] buttons, persists the choice in
   localStorage under "sc-theme-mode" ("light"|"dark"; no value = system),
   and re-applies on OS-level changes when the user hasn't chosen. */
(function () {
  var KEY = "sc-theme-mode";
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function stored() {
    try {
      var v = localStorage.getItem(KEY);
      return v === "dark" || v === "light" ? v : null;
    } catch (e) {
      return null;
    }
  }

  function effective() {
    var v = stored();
    if (v) return v;
    return media && media.matches ? "dark" : "light";
  }

  function paint(mode) {
    var dark = mode === "dark";
    root.classList.toggle("mode-dark", dark);
    root.classList.toggle("mode-light", !dark);
    document.querySelectorAll("[data-mode-toggle]").forEach(function (btn) {
      btn.setAttribute("aria-pressed", dark ? "true" : "false");
      btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    });
  }

  function choose(mode) {
    try {
      localStorage.setItem(KEY, mode);
    } catch (e) {}
    paint(mode);
  }

  document.addEventListener("DOMContentLoaded", function () {
    paint(effective());
    // Enable smooth theme transitions only after the first paint,
    // so initial load doesn't animate.
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        root.classList.add("mode-anim");
      });
    });
    document.querySelectorAll("[data-mode-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        choose(effective() === "dark" ? "light" : "dark");
      });
    });
  });

  // Follow the OS only while the user hasn't made an explicit choice.
  if (media && media.addEventListener) {
    media.addEventListener("change", function () {
      if (!stored()) paint(effective());
    });
  }
})();
