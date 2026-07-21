(() => {
  const DURATIONS = {
    error: 7500,
    warning: 4200,
    success: 2200,
    info: 2400,
    debug: 2400,
  };
  const EXIT_MS = 280;

  const resolveType = (toast) => {
    const raw = (toast.dataset.toastType || "").toLowerCase();
    if (raw.includes("error")) return "error";
    if (raw.includes("warning")) return "warning";
    if (raw.includes("success")) return "success";
    if (raw.includes("debug")) return "debug";
    return "info";
  };

  const dismissToast = (toast) => {
    if (!toast || toast.dataset.leaving === "1") return;
    toast.dataset.leaving = "1";
    toast.classList.add("is-leaving");
    window.setTimeout(() => toast.remove(), EXIT_MS);
  };

  const startProgress = (progress, remaining, total) => {
    if (!progress) return;
    const ratio = total > 0 ? Math.max(0, Math.min(1, remaining / total)) : 0;
    progress.style.transition = "none";
    progress.style.transform = `scaleX(${ratio})`;
    void progress.offsetWidth;
    progress.style.transition = `transform ${remaining}ms linear`;
    progress.style.transform = "scaleX(0)";
  };

  const freezeProgress = (progress, remaining, total) => {
    if (!progress) return;
    const ratio = total > 0 ? Math.max(0, Math.min(1, remaining / total)) : 0;
    progress.style.transition = "none";
    progress.style.transform = `scaleX(${ratio})`;
  };

  const initToast = (toast) => {
    const type = resolveType(toast);
    const duration = DURATIONS[type] ?? DURATIONS.info;
    const progress = toast.querySelector(".toast__progress");
    let remaining = duration;
    let startedAt = Date.now();
    let timerId = null;
    let paused = false;

    startProgress(progress, remaining, duration);

    const schedule = () => {
      timerId = window.setTimeout(() => dismissToast(toast), remaining);
    };

    const pause = () => {
      if (paused || toast.dataset.leaving === "1") return;
      paused = true;
      remaining = Math.max(0, remaining - (Date.now() - startedAt));
      if (timerId) window.clearTimeout(timerId);
      freezeProgress(progress, remaining, duration);
    };

    const resume = () => {
      if (!paused || toast.dataset.leaving === "1") return;
      paused = false;
      startedAt = Date.now();
      startProgress(progress, remaining, duration);
      schedule();
    };

    const closeBtn = toast.querySelector("[data-toast-close]");
    if (closeBtn) {
      closeBtn.addEventListener("click", (event) => {
        event.preventDefault();
        dismissToast(toast);
      });
    }

    toast.addEventListener("mouseenter", pause);
    toast.addEventListener("mouseleave", resume);
    toast.addEventListener("focusin", pause);
    toast.addEventListener("focusout", (event) => {
      if (!toast.contains(event.relatedTarget)) resume();
    });

    schedule();
  };

  const boot = () => {
    document.querySelectorAll("[data-toast]").forEach(initToast);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
