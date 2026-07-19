document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.getElementById("sidebar");
  const toggle = document.getElementById("sidebar-toggle");
  const backdrop = document.getElementById("sidebar-backdrop");
  const profileMenu = document.getElementById("profile-menu");
  const profileTrigger = document.getElementById("profile-trigger");
  const profileDropdown = document.getElementById("profile-dropdown");
  const sessionMenu = document.getElementById("session-menu");
  const sessionTrigger = document.getElementById("session-trigger");
  const sessionDropdown = document.getElementById("session-dropdown");
  const notifMenu = document.getElementById("notif-menu");
  const notifTrigger = document.getElementById("notif-trigger");
  const notifDropdown = document.getElementById("notif-dropdown");

  const setSidebarOpen = (open) => {
    if (!sidebar) return;
    sidebar.classList.toggle("is-open", open);
    if (backdrop) backdrop.hidden = !open;
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    }
  };

  const setProfileOpen = (open) => {
    if (!profileMenu || !profileTrigger || !profileDropdown) return;
    profileMenu.classList.toggle("is-open", open);
    profileDropdown.hidden = !open;
    profileTrigger.setAttribute("aria-expanded", String(open));
  };

  const setSessionOpen = (open) => {
    if (!sessionMenu || !sessionTrigger || !sessionDropdown) return;
    sessionMenu.classList.toggle("is-open", open);
    sessionDropdown.hidden = !open;
    sessionTrigger.setAttribute("aria-expanded", String(open));
  };

  const setNotifOpen = (open) => {
    if (!notifMenu || !notifTrigger || !notifDropdown) return;
    notifMenu.classList.toggle("is-open", open);
    notifDropdown.hidden = !open;
    notifTrigger.setAttribute("aria-expanded", String(open));
  };

  toggle?.addEventListener("click", () => {
    setSidebarOpen(!sidebar.classList.contains("is-open"));
    setProfileOpen(false);
    setSessionOpen(false);
    setNotifOpen(false);
  });

  backdrop?.addEventListener("click", () => setSidebarOpen(false));

  profileTrigger?.addEventListener("click", (event) => {
    event.stopPropagation();
    const willOpen = profileDropdown?.hidden !== false;
    setProfileOpen(willOpen);
    setSessionOpen(false);
    setNotifOpen(false);
    if (willOpen) setSidebarOpen(false);
  });

  sessionTrigger?.addEventListener("click", (event) => {
    event.stopPropagation();
    const willOpen = sessionDropdown?.hidden !== false;
    setSessionOpen(willOpen);
    setProfileOpen(false);
    setNotifOpen(false);
    if (willOpen) setSidebarOpen(false);
  });

  notifTrigger?.addEventListener("click", (event) => {
    event.stopPropagation();
    const willOpen = notifDropdown?.hidden !== false;
    setNotifOpen(willOpen);
    setProfileOpen(false);
    setSessionOpen(false);
    if (willOpen) setSidebarOpen(false);
  });

  document.addEventListener("click", (event) => {
    if (profileMenu && !profileMenu.contains(event.target)) {
      setProfileOpen(false);
    }
    if (sessionMenu && !sessionMenu.contains(event.target)) {
      setSessionOpen(false);
    }
    if (notifMenu && !notifMenu.contains(event.target)) {
      setNotifOpen(false);
    }
  });

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setSidebarOpen(false);
      setProfileOpen(false);
      setSessionOpen(false);
      setNotifOpen(false);
    }
  });

  document.querySelectorAll(".toast").forEach((toast) => {
    window.setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.3s ease";
      window.setTimeout(() => toast.remove(), 320);
    }, 4200);
  });

  const initSessionClock = () => {
    if (!sessionMenu) return;

    const IDLE_MS = 15000;
    const startedRaw = sessionMenu.dataset.startedAt;
    const serverNowRaw = sessionMenu.dataset.serverNow;
    const accountStatus = (sessionMenu.dataset.accountStatus || "active").toLowerCase();
    const userCode = sessionMenu.dataset.userCode || "user";
    const startedAt = startedRaw ? new Date(startedRaw) : new Date();
    const serverNow = serverNowRaw ? new Date(serverNowRaw) : new Date();
    const offsetMs = Number.isNaN(serverNow.getTime())
      ? 0
      : serverNow.getTime() - Date.now();

    const hoursEl = document.getElementById("session-hours");
    const minsEl = document.getElementById("session-mins");
    const fullEl = document.getElementById("session-duration-full");
    const loginTimeEl = document.getElementById("session-login-time");
    const dateEl = document.getElementById("live-date");
    const timeEl = document.getElementById("live-time");
    const statusLabelEl = document.getElementById("session-status-label");
    const statusDotEl = document.getElementById("session-status-dot");
    const presenceDotEl = document.getElementById("session-presence-dot");

    const pad = (value) => String(value).padStart(2, "0");
    const nowServer = () => new Date(Date.now() + offsetMs);
    const dayKey = (date) =>
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    const storageKeyFor = (date) => `sc_active_${userCode}_${dayKey(date)}`;

    const readActiveSeconds = (date) => {
      const raw = window.localStorage.getItem(storageKeyFor(date));
      const parsed = Number.parseInt(raw || "0", 10);
      return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
    };

    const writeActiveSeconds = (date, seconds) => {
      window.localStorage.setItem(
        storageKeyFor(date),
        String(Math.max(0, Math.floor(seconds)))
      );
    };

    let lastActivityAt = Date.now();
    let lastTickAt = Date.now();
    let pageVisible = document.visibilityState !== "hidden";
    let trackedDay = dayKey(nowServer());
    let activeSeconds = readActiveSeconds(nowServer());

    const formatClock = (date) =>
      `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;

    const formatLoginTime = (now) => {
      if (Number.isNaN(startedAt.getTime())) return "—";
      const sameDay =
        startedAt.getFullYear() === now.getFullYear() &&
        startedAt.getMonth() === now.getMonth() &&
        startedAt.getDate() === now.getDate();
      if (!sameDay) return "Before today";
      return formatClock(startedAt);
    };

    const formatDuration = (totalSeconds) => {
      const safe = Math.max(0, Math.floor(totalSeconds));
      const hours = Math.floor(safe / 3600);
      const mins = Math.floor((safe % 3600) / 60);
      return { hours, mins };
    };

    const fullLabel = (hours, mins) => {
      const hourText = hours === 1 ? "1 hour" : `${hours} hours`;
      const minText = mins === 1 ? "1 min" : `${mins} mins`;
      return `${hourText} · ${minText} active`;
    };

    const inSessionStatuses = new Set([
      "active",
      "pending",
      "pending_onboarding",
      "pending_approval",
    ]);

    const isWorking = () =>
      pageVisible &&
      Date.now() - lastActivityAt <= IDLE_MS &&
      inSessionStatuses.has(accountStatus);

    const presenceState = () => {
      if (accountStatus === "suspended") {
        return { key: "suspended", label: "Suspended" };
      }
      if (!inSessionStatuses.has(accountStatus)) {
        return { key: "offline", label: "Not in session" };
      }
      if (isWorking()) {
        return { key: "working", label: "Working" };
      }
      return { key: "idle", label: "In session" };
    };

    const applyPresence = () => {
      const { key, label } = presenceState();
      const classes = [
        "meta-dot--working",
        "meta-dot--idle",
        "meta-dot--offline",
        "meta-dot--suspended",
      ];
      [statusDotEl, presenceDotEl].forEach((dot) => {
        if (!dot) return;
        classes.forEach((name) => dot.classList.remove(name));
        dot.classList.add(`meta-dot--${key}`);
      });
      if (statusLabelEl) statusLabelEl.textContent = label;
    };

    const markActivity = () => {
      lastActivityAt = Date.now();
      applyPresence();
    };

    [
      "mousemove",
      "mousedown",
      "keydown",
      "scroll",
      "touchstart",
      "touchmove",
      "click",
      "wheel",
    ].forEach((eventName) => {
      window.addEventListener(eventName, markActivity, { passive: true });
    });

    document.addEventListener("visibilitychange", () => {
      pageVisible = document.visibilityState !== "hidden";
      if (pageVisible) {
        lastActivityAt = Date.now();
        lastTickAt = Date.now();
      }
      applyPresence();
    });

    const tick = () => {
      const now = nowServer();
      const currentDay = dayKey(now);
      if (currentDay !== trackedDay) {
        trackedDay = currentDay;
        activeSeconds = readActiveSeconds(now);
      }

      const wallNow = Date.now();
      const elapsed = Math.max(0, (wallNow - lastTickAt) / 1000);
      lastTickAt = wallNow;

      // Only accumulate while the user is actively interacting.
      if (isWorking() && elapsed > 0 && elapsed < 5) {
        activeSeconds += elapsed;
        writeActiveSeconds(now, activeSeconds);
      }

      const { hours, mins } = formatDuration(activeSeconds);
      if (hoursEl) hoursEl.textContent = String(hours);
      if (minsEl) minsEl.textContent = String(mins);
      if (fullEl) fullEl.textContent = fullLabel(hours, mins);
      if (loginTimeEl) loginTimeEl.textContent = formatLoginTime(now);

      if (dateEl) {
        dateEl.textContent = now.toLocaleDateString(undefined, {
          weekday: "short",
          day: "numeric",
          month: "short",
          year: "numeric",
        });
      }
      if (timeEl) {
        timeEl.textContent = formatClock(now);
      }

      applyPresence();
    };

    markActivity();
    tick();
    window.setInterval(tick, 1000);
  };

  initSessionClock();

  /* Reveal + magnetic card motion */
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const initReveal = () => {
    const nodes = document.querySelectorAll("[data-reveal]");
    if (!nodes.length) return;
    if (reduceMotion) {
      nodes.forEach((node) => node.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -6% 0px" }
    );
    nodes.forEach((node) => observer.observe(node));
  };

  const initMagnetic = () => {
    if (reduceMotion) return;
    document.querySelectorAll("[data-magnetic]").forEach((card) => {
      const orb = card.querySelector(".icon-orb__core");
      card.addEventListener("pointermove", (event) => {
        const rect = card.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - 0.5;
        const y = (event.clientY - rect.top) / rect.height - 0.5;
        card.style.transform = `translateY(-3px) rotateX(${(-y * 4).toFixed(2)}deg) rotateY(${(x * 5).toFixed(2)}deg)`;
        if (orb) {
          orb.style.transform = `translate(${(x * 6).toFixed(1)}px, ${(y * 6).toFixed(1)}px) scale(1.05)`;
        }
      });
      card.addEventListener("pointerleave", () => {
        card.style.transform = "";
        if (orb) orb.style.transform = "";
      });
    });
  };

  const initHeroSpotlight = () => {
    if (reduceMotion) return;
    document.querySelectorAll(".dash-hero").forEach((hero) => {
      hero.addEventListener("pointermove", (event) => {
        const rect = hero.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * 100;
        const y = ((event.clientY - rect.top) / rect.height) * 100;
        hero.style.setProperty("--spotlight-x", `${x.toFixed(1)}%`);
        hero.style.setProperty("--spotlight-y", `${y.toFixed(1)}%`);
      });
    });
  };

  const initMetricCountUp = () => {
    const metrics = document.querySelectorAll(".metric--glass .metric__value");
    if (!metrics.length) return;

    const parseTarget = (text) => {
      const raw = String(text).trim();
      const match = raw.match(/^([^0-9-]*)(-?\d[\d,]*)(.*)$/);
      if (!match) return null;
      return {
        prefix: match[1],
        value: Number(match[2].replace(/,/g, "")),
        suffix: match[3],
        raw,
      };
    };

    const animateValue = (el, parsed) => {
      if (reduceMotion || !Number.isFinite(parsed.value)) {
        el.textContent = parsed.raw;
        return;
      }
      const duration = 900;
      const start = performance.now();
      el.closest(".metric--glass")?.classList.add("is-counting");
      const step = (now) => {
        const t = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - t, 3);
        const current = Math.round(parsed.value * eased);
        el.textContent = `${parsed.prefix}${current.toLocaleString()}${parsed.suffix}`;
        if (t < 1) {
          requestAnimationFrame(step);
        } else {
          el.textContent = parsed.raw;
          el.closest(".metric--glass")?.classList.remove("is-counting");
        }
      };
      requestAnimationFrame(step);
    };

    const run = () => {
      metrics.forEach((el) => {
        const parsed = parseTarget(el.textContent);
        if (parsed) animateValue(el, parsed);
      });
    };

    const host = document.querySelector(".metrics--dash[data-reveal]");
    if (!host || reduceMotion) {
      run();
      return;
    }
    if (host.classList.contains("is-visible")) {
      run();
      return;
    }
    const observer = new MutationObserver(() => {
      if (!host.classList.contains("is-visible")) return;
      observer.disconnect();
      run();
    });
    observer.observe(host, { attributes: true, attributeFilter: ["class"] });
  };

  initReveal();
  initMagnetic();
  initHeroSpotlight();
  initMetricCountUp();
});
