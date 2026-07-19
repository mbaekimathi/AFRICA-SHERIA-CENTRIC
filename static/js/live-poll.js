/**
 * Lightweight adaptive polling for Sheria-Centric.
 * Pauses when the tab is hidden; backs off while nothing changes.
 * Resumes immediately on focus / bfcache restore.
 */

(function (global) {
  const wakeFns = new Set();
  function startLivePoll(options) {
    const url = options.url;
    const onPayload = options.onPayload;
    if (!url || typeof onPayload !== "function") return () => {};
    const minMs = options.minMs ?? 4000;
    const maxMs = options.maxMs ?? 30000;
    const factor = options.factor ?? 1.6;
    let delay = minMs;
    let timer = null;
    let inFlight = false;
    let stopped = false;
    const clearTimer = () => {
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
    };
    const schedule = (ms) => {
      clearTimer();
      if (stopped) return;
      timer = window.setTimeout(tick, ms);
    };
    const wake = () => {
      if (stopped || document.hidden) return;
      delay = minMs;
      schedule(0);
    };
    const tick = async () => {
      if (stopped) return;
      if (document.hidden) {
        // Wait for visibilitychange / focus — do not spin while hidden.
        return;
      }
      if (inFlight) {
        schedule(Math.min(delay, 1000));
        return;
      }
      inFlight = true;
      let changed = false;
      try {
        const response = await fetch(url, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (response.ok) {
          const data = await response.json();
          if (data && typeof data === "object") {
            changed = Boolean(onPayload(data));
          }
        }
      } catch (_error) {
        // Transient network errors — keep polling.
      } finally {
        inFlight = false;
      }
      if (stopped || document.hidden) return;
      if (changed) {
        delay = minMs;
      } else {
        delay = Math.min(maxMs, Math.round(delay * factor));
      }
      schedule(delay);
    };
    const onVisibility = () => {
      if (!document.hidden) wake();
    };
    const onPageShow = (event) => {
      // Back/forward cache can restore a stale badge DOM — refresh immediately.
      if (event.persisted) wake();
    };
    wakeFns.add(wake);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", wake);
    window.addEventListener("pageshow", onPageShow);
    schedule(0);
    return () => {
      stopped = true;
      wakeFns.delete(wake);
      clearTimer();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", wake);
      window.removeEventListener("pageshow", onPageShow);
    };
  }
  global.SheriaLivePoll = {
    start: startLivePoll,
    refreshAll() {
      wakeFns.forEach((wake) => wake());
    },
  };
})(window);
