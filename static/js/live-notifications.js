/**
 * Live workspace notifications — topbar bell with grouped feed.
 */
(function () {
  function csrfToken() {
    const field = document.querySelector("[name=csrfmiddlewaretoken]");
    if (field?.value) return field.value;
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function setBadgeCount(badge, count) {
    if (!badge) return;
    const n = Number(count) || 0;
    if (n > 0) {
      badge.hidden = false;
      badge.removeAttribute("hidden");
      badge.textContent = n > 99 ? "99+" : String(n);
    } else {
      badge.hidden = true;
      badge.setAttribute("hidden", "");
      badge.textContent = "0";
    }
  }

  function createNotificationSound(getVolume) {
    let audioCtx = null;
    let unlocked = false;
    let lastPlayedAt = 0;
    const resolveVolume = typeof getVolume === "function" ? getVolume : () => 70;

    function getContext() {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return null;
      if (!audioCtx) audioCtx = new AudioContext();
      return audioCtx;
    }

    function unlock() {
      const ctx = getContext();
      if (!ctx) return;
      if (ctx.state === "suspended") {
        ctx.resume().catch(() => {});
      }
      unlocked = true;
    }

    function playTone(ctx, frequency, startAt, duration, gainValue) {
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0.0001, startAt);
      gain.gain.exponentialRampToValueAtTime(gainValue, startAt + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);
      oscillator.connect(gain);
      gain.connect(ctx.destination);
      oscillator.start(startAt);
      oscillator.stop(startAt + duration + 0.02);
    }

    function play(force = false) {
      const ctx = getContext();
      if (!ctx) return;
      if (force) {
        unlocked = true;
      }
      if (!force && !unlocked) return;

      const volumePct = Math.max(0, Math.min(100, Number(resolveVolume()) || 0));
      if (volumePct <= 0) return;
      const volumeScale = volumePct / 100;

      const run = () => {
        const now = Date.now();
        if (!force && now - lastPlayedAt < 1500) return;
        lastPlayedAt = now;
        const t = ctx.currentTime;
        playTone(ctx, 880, t, 0.14, 0.12 * volumeScale);
        playTone(ctx, 1174.7, t + 0.12, 0.18, 0.09 * volumeScale);
      };

      if (ctx.state === "suspended") {
        ctx.resume().then(run).catch(() => {});
        return;
      }
      run();
    }

    const unlockEvents = ["pointerdown", "keydown", "touchstart"];
    unlockEvents.forEach((eventName) => {
      document.addEventListener(eventName, unlock, { once: true, passive: true });
    });

    return { play, unlock };
  }

  function createBrowserNotifications(menu) {
    const firmName = () =>
      (menu.dataset.firmName || "Sheria Centric").trim() || "Sheria Centric";
    const preferenceEnabled = () =>
      (menu.dataset.browserEnabled || "true").toLowerCase() !== "false";
    let lastPlayedAt = 0;

    function supported() {
      return typeof window.Notification === "function";
    }

    function permission() {
      if (!supported()) return "unsupported";
      return window.Notification.permission || "default";
    }

    async function requestPermission() {
      if (!supported()) return "unsupported";
      if (permission() !== "default") return permission();
      try {
        const result = await window.Notification.requestPermission();
        return result || permission();
      } catch (_error) {
        return permission();
      }
    }

    function newestUnreadItems(groups) {
      const items = [];
      (groups || []).forEach((group) => {
        (group.items || []).forEach((item) => {
          if (!item || item.is_read) return;
          items.push(item);
        });
      });
      items.sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
      return items;
    }

    function show(item, { force = false } = {}) {
      if (!supported()) return false;
      if (!force && !preferenceEnabled()) return false;
      if (permission() !== "granted") return false;
      if (!force && menu.classList.contains("is-open")) return false;

      const now = Date.now();
      if (!force && now - lastPlayedAt < 1500) return false;
      lastPlayedAt = now;

      const title = (item && item.title) || "New notification";
      const body =
        (item && (item.body || item.category_label)) ||
        "You have a new alert in Sheria Centric.";
      const targetUrl = (item && item.url) || window.location.href;

      try {
        const note = new window.Notification(`${firmName()} · ${title}`, {
          body: String(body).slice(0, 180),
          tag: item && item.id ? `sheria-notif-${item.id}` : "sheria-notif",
          renotify: true,
          requireInteraction: false,
        });
        note.onclick = () => {
          try {
            window.focus();
            if (targetUrl) window.location.href = targetUrl;
          } catch (_error) {
            // Ignore focus / navigation failures.
          }
          note.close();
        };
        window.setTimeout(() => {
          try {
            note.close();
          } catch (_error) {
            // Ignore close failures.
          }
        }, 8000);
        return true;
      } catch (_error) {
        return false;
      }
    }

    function notifyFromPayload(groups, addedCount) {
      if (!preferenceEnabled() || permission() !== "granted") return;
      const unread = newestUnreadItems(groups);
      if (!unread.length) return;
      if (addedCount > 1) {
        show(
          {
            id: `batch-${unread[0].id}`,
            title: `${addedCount} new notifications`,
            body: unread[0].title || "Open Sheria Centric to review them.",
            url: unread[0].url,
          },
          { force: false }
        );
        return;
      }
      show(unread[0]);
    }

    return {
      supported,
      permission,
      requestPermission,
      show,
      notifyFromPayload,
      preferenceEnabled,
    };
  }

  function renderFeed(listEl, groups) {
    const hasAny = groups.some((group) => (group.items || []).length > 0);
    if (!hasAny) {
      listEl.innerHTML = '<p class="notif-empty">No notifications yet.</p>';
      return;
    }

    const parts = [];
    groups.forEach((group) => {
      const items = group.items || [];
      if (!items.length) return;

      parts.push(
        `<section class="notif-group" data-category="${escapeHtml(group.category)}">` +
          `<div class="notif-group__head">` +
          `<h2 class="notif-group__title">${escapeHtml(group.label)}</h2>` +
          (group.unread
            ? `<span class="notif-group__count">${group.unread}</span>`
            : "") +
          `</div>` +
          `<ul class="notif-group__list">`
      );

      items.forEach((item) => {
        const unreadClass = item.is_read ? "" : " is-unread";
        parts.push(
          `<li>` +
            `<a class="notif-item${unreadClass}" href="${escapeHtml(item.url)}">` +
            `<span class="notif-item__dot" aria-hidden="true"></span>` +
            `<span class="notif-item__text">` +
            `<span class="notif-item__title">${escapeHtml(item.title)}</span>` +
            (item.body
              ? `<span class="notif-item__body">${escapeHtml(item.body)}</span>`
              : "") +
            `<span class="notif-item__meta">${escapeHtml(item.created_display)}</span>` +
            `</span>` +
            `</a>` +
            `</li>`
        );
      });

      parts.push(`</ul></section>`);
    });

    listEl.innerHTML = parts.join("");
  }

  function applyUtilityBadges(badges) {
    const counts = badges && typeof badges === "object" ? badges : {};
    document.querySelectorAll("[data-utility-badge]").forEach((badge) => {
      const slug = badge.getAttribute("data-utility-badge");
      const count = Number(counts[slug] || 0);
      const link = badge.closest(".nav-link");
      const label = link?.dataset.label || slug || "Item";
      const unit = slug === "tasks" ? "pending" : "unread";
      setBadgeCount(badge, count);
      if (count > 0) {
        link?.classList.add("has-unread");
        link?.setAttribute("aria-label", `${label}, ${count} ${unit}`);
      } else {
        link?.classList.remove("has-unread");
        link?.removeAttribute("aria-label");
      }
    });
  }

  function applyUnreadState(trigger, badge, markAllBtn, unreadCount) {
    const hasUnread = unreadCount > 0;
    const menuOpen = trigger.closest(".notif-menu")?.classList.contains("is-open");
    trigger.classList.toggle("has-unread", hasUnread);
    // Ring only while unread and the panel is closed.
    trigger.classList.toggle("is-ringing", hasUnread && !menuOpen);
    trigger.setAttribute(
      "aria-label",
      hasUnread
        ? `Notifications, ${unreadCount} unread`
        : "Notifications"
    );

    setBadgeCount(badge, unreadCount);
    if (markAllBtn) {
      markAllBtn.hidden = !hasUnread;
      if (hasUnread) markAllBtn.removeAttribute("hidden");
      else markAllBtn.setAttribute("hidden", "");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const menu = document.getElementById("notif-menu");
    const trigger = document.getElementById("notif-trigger");
    const badge = document.getElementById("notif-badge");
    const listEl = document.getElementById("notif-list");
    const markAllBtn = document.getElementById("notif-mark-all");
    if (!menu || !trigger || !badge || !listEl) return;

    const sound = createNotificationSound(() => {
      const raw = Number(menu.dataset.soundVolume);
      return Number.isFinite(raw) ? raw : 70;
    });
    window.SheriaNotificationSound = sound;
    const browserAlerts = createBrowserNotifications(menu);
    window.SheriaBrowserNotifications = browserAlerts;
    window.dispatchEvent(new CustomEvent("sheria:notifications-ready"));

    const url = menu.dataset.notificationsUrl;
    const markAllUrl = menu.dataset.markAllUrl;
    if (!url || !window.SheriaLivePoll) return;

    let lastRevision = "";
    let lastUnreadCount = null;
    const soundEnabled = () =>
      (menu.dataset.soundEnabled || "true").toLowerCase() !== "false";

    const onPayload = (data) => {
      if (!data || typeof data !== "object") return false;
      const revision = data.revision || "";
      const changed = revision !== lastRevision;
      lastRevision = revision;

      const unreadCount = Number(data.unread_count || 0);
      if (lastUnreadCount !== null && unreadCount > lastUnreadCount) {
        const added = unreadCount - lastUnreadCount;
        if (soundEnabled()) sound.play();
        browserAlerts.notifyFromPayload(data.groups || [], added);
      }
      lastUnreadCount = unreadCount;

      applyUnreadState(trigger, badge, markAllBtn, unreadCount);
      applyUtilityBadges(data.badges || {});
      renderFeed(listEl, data.groups || []);
      return changed;
    };

    // Keep polling in background tabs so browser desktop alerts can fire.
    window.SheriaLivePoll.start({
      url,
      minMs: 8000,
      maxMs: 45000,
      factor: 1.7,
      runInBackground: true,
      onPayload,
    });

    async function markAllNotificationsRead() {
      if (!markAllUrl) return false;
      try {
        const response = await fetch(markAllUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "X-CSRFToken": csrfToken(),
          },
        });
        if (!response.ok) return false;
        const data = await response.json();
        if (!data || typeof data !== "object") return false;
        lastUnreadCount = Number(data.unread_count || 0);
        applyUnreadState(trigger, badge, markAllBtn, lastUnreadCount);
        applyUtilityBadges(data.badges || {});
        listEl.querySelectorAll(".notif-item.is-unread").forEach((el) => {
          el.classList.remove("is-unread");
        });
        listEl.querySelectorAll(".notif-group__count").forEach((el) => el.remove());
        lastRevision = "";
        window.SheriaLivePoll.refreshAll?.();
        return true;
      } catch (_error) {
        return false;
      }
    }

    // Pause / resume ring when the dropdown opens or closes.
    // Opening the panel marks notifications as read (same as viewing Tasks/Messages).
    let wasOpen = menu.classList.contains("is-open");
    const menuObserver = new MutationObserver(() => {
      const open = menu.classList.contains("is-open");
      const unread = Number.parseInt(badge.textContent || "0", 10) || 0;
      const hasUnread = !badge.hidden && unread > 0;
      trigger.classList.toggle("is-ringing", hasUnread && !open);
      if (open && !wasOpen) {
        markAllNotificationsRead();
      }
      wasOpen = open;
    });
    menuObserver.observe(menu, { attributes: true, attributeFilter: ["class"] });

    // Refresh as soon as the panel opens so counts match the feed.
    trigger.addEventListener("click", () => {
      window.SheriaLivePoll.refreshAll?.();
    });

    markAllBtn?.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      await markAllNotificationsRead();
    });
  });
})();
