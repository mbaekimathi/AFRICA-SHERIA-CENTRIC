document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("matter-analytics-page");
  if (!page) return;

  const filterForm = document.getElementById("matter-analytics-filter");
  const liveRoot = document.getElementById("matter-analytics-live");
  const focusInput = document.getElementById("matter-filter-focus");
  let chartData = { trend: [], focus: "all" };
  let activeFocus = "all";
  let requestToken = 0;
  let debounceTimer = null;

  const palette = () => {
    const styles = getComputedStyle(document.body);
    const value = (name, fallback) =>
      styles.getPropertyValue(name).trim() || fallback;
    return {
      ink: value("--ink", "#18202f"),
      muted: value("--ink-muted", "#667085"),
      line: value("--line", "#e4e7ec"),
      surface: value("--surface", "#ffffff"),
      litigation: "#0f766e",
      non: "#c2410c",
    };
  };

  const prepare = (canvas) => {
    const ratio = Math.max(1, window.devicePixelRatio || 1);
    const width = Math.max(1, canvas.clientWidth);
    const height = Math.max(1, canvas.clientHeight);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { context, width, height };
  };

  const emptyState = (context, width, height, colors, message) => {
    context.fillStyle = colors.muted;
    context.font = "12px IBM Plex Sans, Segoe UI, sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(message, width / 2, height / 2);
  };

  const readCharts = () => {
    const dataElement = document.getElementById("matter-analytics-charts-data");
    if (!dataElement) {
      chartData = { trend: [], focus: activeFocus };
      return;
    }
    try {
      chartData = JSON.parse(dataElement.textContent || "{}");
    } catch (_error) {
      chartData = { trend: [], focus: activeFocus };
    }
  };

  const seriesValue = (point, key) => Number(point?.[key] || 0);

  const drawCombinedTrend = () => {
    const canvas = liveRoot?.querySelector("[data-matter-trend]");
    if (!canvas) return;

    const colors = palette();
    const { context, width, height } = prepare(canvas);
    context.clearRect(0, 0, width, height);

    const points = Array.isArray(chartData.trend) ? chartData.trend : [];
    const focus = chartData.focus || activeFocus;
    const showLit = focus === "all" || focus === "litigation";
    const showNon = focus === "all" || focus === "non_litigation";

    const hasValues = points.some((point) => {
      const lit = seriesValue(point, "litigation");
      const non = seriesValue(point, "non_litigation");
      if (focus === "litigation") return lit > 0;
      if (focus === "non_litigation") return non > 0;
      return lit + non > 0;
    });

    if (!points.length || !hasValues) {
      emptyState(context, width, height, colors, "No openings in this period");
      return;
    }

    const padding = { top: 22, right: 16, bottom: 36, left: 36 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const maxValue = Math.max(
      1,
      ...points.map((point) => {
        const lit = seriesValue(point, "litigation");
        const non = seriesValue(point, "non_litigation");
        if (focus === "litigation") return lit;
        if (focus === "non_litigation") return non;
        return lit + non;
      })
    );

    const step = chartWidth / Math.max(1, points.length);
    const groupWidth = Math.max(8, Math.min(36, step * 0.62));
    const barGap = showLit && showNon ? 2 : 0;
    const barWidth =
      showLit && showNon
        ? Math.max(3, (groupWidth - barGap) / 2)
        : groupWidth;
    const floorY = padding.top + chartHeight;

    context.strokeStyle = colors.line;
    context.lineWidth = 1;
    context.fillStyle = colors.muted;
    context.font = "10px IBM Plex Sans, Segoe UI, sans-serif";
    context.textAlign = "right";
    context.textBaseline = "middle";
    for (let index = 0; index <= 4; index += 1) {
      const y = padding.top + (chartHeight * index) / 4;
      context.beginPath();
      context.moveTo(padding.left, y);
      context.lineTo(width - padding.right, y);
      context.stroke();
      context.fillText(
        String(Math.round(maxValue * (1 - index / 4))),
        padding.left - 8,
        y
      );
    }

    const drawBar = (x, value, color) => {
      const barHeight = (value / maxValue) * chartHeight;
      const top = floorY - barHeight;
      context.fillStyle = color;
      context.beginPath();
      const radius = Math.min(3, barWidth / 2);
      context.moveTo(x, floorY);
      context.lineTo(x, top + radius);
      context.quadraticCurveTo(x, top, x + radius, top);
      context.lineTo(x + barWidth - radius, top);
      context.quadraticCurveTo(x + barWidth, top, x + barWidth, top + radius);
      context.lineTo(x + barWidth, floorY);
      context.closePath();
      context.fill();
      return { x: x + barWidth / 2, y: top };
    };

    const litLine = [];
    const nonLine = [];

    points.forEach((point, index) => {
      const center = padding.left + step * index + step / 2;
      const lit = seriesValue(point, "litigation");
      const non = seriesValue(point, "non_litigation");

      if (showLit && showNon) {
        const startX = center - groupWidth / 2;
        litLine.push(drawBar(startX, lit, colors.litigation));
        nonLine.push(drawBar(startX + barWidth + barGap, non, colors.non));
      } else if (showLit) {
        litLine.push(drawBar(center - barWidth / 2, lit, colors.litigation));
      } else {
        nonLine.push(drawBar(center - barWidth / 2, non, colors.non));
      }
    });

    const drawLine = (linePoints, color) => {
      if (linePoints.length < 2) return;
      context.beginPath();
      linePoints.forEach((point, index) => {
        if (index === 0) context.moveTo(point.x, point.y);
        else context.lineTo(point.x, point.y);
      });
      context.strokeStyle = color;
      context.globalAlpha = 0.4;
      context.lineWidth = 2;
      context.lineJoin = "round";
      context.lineCap = "round";
      context.stroke();
      context.globalAlpha = 1;
    };

    if (showLit) drawLine(litLine, colors.litigation);
    if (showNon) drawLine(nonLine, colors.non);

    const labelEvery = Math.max(
      1,
      Math.ceil(points.length / Math.max(3, Math.floor(width / 72)))
    );
    context.fillStyle = colors.muted;
    context.font = "10px IBM Plex Sans, Segoe UI, sans-serif";
    context.textAlign = "center";
    context.textBaseline = "top";
    points.forEach((point, index) => {
      if (index % labelEvery !== 0 && index !== points.length - 1) return;
      const x = padding.left + step * index + step / 2;
      context.fillText(point.label || "", x, height - padding.bottom + 10);
    });
  };

  const setActiveFocus = (focusId, { refresh = false, pushUrl = false } = {}) => {
    activeFocus =
      focusId === "litigation" || focusId === "non_litigation"
        ? focusId
        : "all";
    page.dataset.focus = activeFocus;
    if (focusInput) focusInput.value = activeFocus;

    liveRoot?.querySelectorAll("[data-matter-focus]").forEach((pill) => {
      const selected = pill.getAttribute("data-matter-focus") === activeFocus;
      pill.classList.toggle("is-active", selected);
      pill.setAttribute("aria-selected", selected ? "true" : "false");
    });

    if (refresh) {
      scheduleRefresh(true);
      return;
    }

    window.requestAnimationFrame(drawCombinedTrend);

    if (pushUrl) {
      const params = new URLSearchParams(queryString());
      history.replaceState(null, "", `${window.location.pathname}?${params}`);
    }
  };

  const bindFocus = () => {
    liveRoot?.querySelectorAll("[data-matter-focus]").forEach((pill) => {
      pill.addEventListener("click", () => {
        setActiveFocus(pill.getAttribute("data-matter-focus"), {
          refresh: true,
          pushUrl: true,
        });
      });
    });
  };

  const syncMonthNavButtons = () => {
    const monthInput = filterForm?.querySelector("#matter-filter-month");
    if (!monthInput) return;
    const nextBtn = filterForm.querySelector('[data-month-step="1"]');
    if (nextBtn) {
      nextBtn.disabled = monthInput.dataset.canNext !== "1";
    }
  };

  const syncHeaderMeta = () => {
    const meta = document.getElementById("matter-analytics-meta");
    if (!meta) return;
    const status = page.querySelector("[data-matter-filter-status]");
    const summary = page.querySelector("[data-matter-summary]");
    const label =
      meta.content.querySelector("[data-filter-label]")?.textContent || "";
    const metaFocus = meta.content.querySelector(
      "[data-active-focus]"
    )?.textContent;
    const monthInput = filterForm?.querySelector("#matter-filter-month");

    if (status) status.textContent = `Showing ${label}`;
    if (summary) {
      const map = {
        "[data-summary-total]": "data-summary-total",
        "[data-summary-active]": "data-summary-active",
        "[data-summary-pending]": "data-summary-pending",
        "[data-summary-closed]": "data-summary-closed",
      };
      Object.entries(map).forEach(([selector, attr]) => {
        const target = summary.querySelector(selector);
        const source = meta.content.querySelector(`[${attr}]`);
        if (target && source) target.textContent = source.textContent || "0";
      });
    }
    if (monthInput) {
      monthInput.dataset.prevMonth =
        meta.content.querySelector("[data-prev-month]")?.textContent || "";
      monthInput.dataset.nextMonth =
        meta.content.querySelector("[data-next-month]")?.textContent || "";
      monthInput.dataset.canNext =
        meta.content.querySelector("[data-can-next]")?.textContent || "0";
      syncMonthNavButtons();
    }
    if (metaFocus) activeFocus = metaFocus.trim() || activeFocus;
    if (focusInput) focusInput.value = activeFocus;
  };

  const queryString = () => {
    const params = filterForm
      ? new URLSearchParams(new FormData(filterForm))
      : new URLSearchParams(window.location.search);
    params.set("focus", activeFocus);
    params.delete("tab");
    return params.toString();
  };

  const refreshLive = async () => {
    if (!liveRoot || !filterForm) return;
    const params = queryString();
    const token = ++requestToken;
    const status = page.querySelector("[data-matter-filter-status]");
    page.classList.add("is-filtering");
    if (status && !status.dataset.busyLabel) {
      status.dataset.busyLabel = status.textContent;
    }
    if (status) status.textContent = "Updating…";

    try {
      const response = await fetch(`${window.location.pathname}?${params}`, {
        headers: {
          "X-Matter-Analytics": "live",
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      if (!response.ok) throw new Error("Filter refresh failed");
      const html = await response.text();
      if (token !== requestToken) return;

      liveRoot.innerHTML = html;
      syncHeaderMeta();
      bindFocus();
      readCharts();
      setActiveFocus(activeFocus);
      history.replaceState(null, "", `${window.location.pathname}?${params}`);
    } catch (_error) {
      if (status) {
        status.textContent = status.dataset.busyLabel || "Could not update";
      }
    } finally {
      if (token === requestToken) {
        page.classList.remove("is-filtering");
      }
    }
  };

  const scheduleRefresh = (immediate = false) => {
    window.clearTimeout(debounceTimer);
    if (immediate) {
      refreshLive();
      return;
    }
    debounceTimer = window.setTimeout(() => refreshLive(), 280);
  };

  if (filterForm) {
    const modeInputs = filterForm.querySelectorAll('input[name="mode"]');
    const fieldGroups = filterForm.querySelectorAll("[data-mode-field]");

    const syncModeFields = ({ openPicker = false } = {}) => {
      const selected = filterForm.querySelector('input[name="mode"]:checked');
      const mode = selected ? selected.value : "month";
      fieldGroups.forEach((group) => {
        const active = group.getAttribute("data-mode-field") === mode;
        group.hidden = !active;
        group.querySelectorAll("input, select").forEach((input) => {
          input.disabled = !active;
        });
      });
      modeInputs.forEach((input) => {
        input.closest(".matter-hub__mode")?.classList.toggle(
          "is-active",
          input.checked
        );
      });
      syncMonthNavButtons();

      if (!openPicker) return;
      const activePanel = filterForm.querySelector(
        `[data-mode-field="${mode}"]:not([hidden])`
      );
      const focusEl = activePanel?.querySelector(
        "input:not([type='hidden']):not([disabled]), select:not([disabled])"
      );
      if (!focusEl) return;
      focusEl.focus({ preventScroll: true });
      if (typeof focusEl.showPicker === "function") {
        try {
          focusEl.showPicker();
        } catch (_error) {
          /* Browser may block picker unless from a direct click. */
        }
      }
    };

    modeInputs.forEach((input) => {
      input.addEventListener("change", () => {
        syncModeFields({ openPicker: true });
        scheduleRefresh(true);
      });
    });

    filterForm
      .querySelectorAll("input[type='date'], input[type='month']")
      .forEach((input) => {
        input.addEventListener("change", () => scheduleRefresh(true));
        input.addEventListener("input", () => scheduleRefresh());
      });

    const yearInput = filterForm.querySelector("#matter-filter-year");
    if (yearInput) {
      yearInput.addEventListener("change", () => scheduleRefresh(true));
      yearInput.addEventListener("input", () => scheduleRefresh());
    }

    filterForm.querySelectorAll("[data-month-step]").forEach((button) => {
      button.addEventListener("click", () => {
        const monthInput = filterForm.querySelector("#matter-filter-month");
        if (!monthInput || monthInput.disabled) return;
        const step = Number(button.getAttribute("data-month-step") || 0);
        const nextValue =
          step < 0 ? monthInput.dataset.prevMonth : monthInput.dataset.nextMonth;
        if (!nextValue) return;
        if (step > 0 && monthInput.dataset.canNext !== "1") return;
        monthInput.value = nextValue;
        scheduleRefresh(true);
      });
    });

    filterForm.addEventListener("submit", (event) => {
      event.preventDefault();
      scheduleRefresh(true);
    });

    syncModeFields();
  }

  const params = new URLSearchParams(window.location.search);
  const initialFocus = params.get("focus") || params.get("tab") || "all";
  activeFocus =
    initialFocus === "litigation" ||
    initialFocus === "non_litigation" ||
    initialFocus === "non-litigation"
      ? initialFocus === "non-litigation"
        ? "non_litigation"
        : initialFocus
      : "all";
  if (focusInput) focusInput.value = activeFocus;

  bindFocus();
  readCharts();
  setActiveFocus(activeFocus);
  window.addEventListener("resize", drawCombinedTrend);
});
