document.addEventListener("DOMContentLoaded", () => {
  const page = document.getElementById("employee-performance-page");
  if (!page) return;

  const tabs = [...page.querySelectorAll(".performance-tab")];
  const panels = {
    overview: document.getElementById("panel-overview"),
    visuals: document.getElementById("panel-visuals"),
  };

  const activateTab = (name) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    Object.entries(panels).forEach(([key, panel]) => {
      if (!panel) return;
      panel.hidden = key !== name;
    });
    if (name === "visuals") drawAll();
  };

  tabs.forEach((tab) =>
    tab.addEventListener("click", () => activateTab(tab.dataset.tab))
  );

  const dataElement = document.getElementById("employee-performance-charts-data");
  if (!dataElement) return;

  const charts = JSON.parse(dataElement.textContent || "{}");
  const trendCards = Array.from(page.querySelectorAll("[data-trend-chart]"));

  const palette = () => {
    const s = getComputedStyle(document.body);
    const v = (name, fb) => s.getPropertyValue(name).trim() || fb;
    return {
      accent: v("--accent", "#4f46e5"),
      ink: v("--ink", "#18202f"),
      muted: v("--ink-muted", "#667085"),
      line: v("--line", "#e4e7ec"),
      surface: v("--surface", "#ffffff"),
      series: [v("--accent", "#4f46e5"), "#0d9488", "#d97706", "#7c3aed"],
    };
  };

  const prepare = (canvas) => {
    const ratio = Math.max(1, window.devicePixelRatio || 1);
    const w = Math.max(1, canvas.clientWidth);
    const h = Math.max(1, canvas.clientHeight);
    canvas.width = Math.round(w * ratio);
    canvas.height = Math.round(h * ratio);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { ctx, w, h };
  };

  /* Smooth Catmull-Rom to cubic bezier through all points */
  const smoothLine = (ctx, pts) => {
    if (pts.length < 2) return;
    ctx.moveTo(pts[0].x, pts[0].y);
    if (pts.length === 2) {
      ctx.lineTo(pts[1].x, pts[1].y);
      return;
    }
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[Math.max(0, i - 1)];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[Math.min(pts.length - 1, i + 2)];
      const t = 0.35;
      const cp1x = p1.x + ((p2.x - p0.x) * t) / 3;
      const cp1y = p1.y + ((p2.y - p0.y) * t) / 3;
      const cp2x = p2.x - ((p3.x - p1.x) * t) / 3;
      const cp2y = p2.y - ((p3.y - p1.y) * t) / 3;
      ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
    }
  };

  const drawTrend = (canvas, series, colorIndex) => {
    if (!canvas) return;
    const colors = palette();
    const stroke = colors.series[colorIndex % colors.series.length];
    const { ctx, w, h } = prepare(canvas);
    ctx.clearRect(0, 0, w, h);

    const pad = { top: 22, right: 22, bottom: 36, left: 22 };
    const cw = w - pad.left - pad.right;
    const ch = h - pad.top - pad.bottom;
    const hasValues = series.some((p) => p.value > 0);

    /* Grid lines */
    ctx.strokeStyle = colors.line;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (ch * i) / 4;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
    }

    if (!series.length || !hasValues) {
      ctx.fillStyle = colors.muted;
      ctx.font = "12px IBM Plex Sans, Segoe UI, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("No activity in this range", w / 2, h / 2);
      return;
    }

    const maxVal = Math.max(1, ...series.map((p) => p.value));
    const step = cw / Math.max(1, series.length - 1);
    const pts = series.map((p, i) => ({
      x: pad.left + step * i,
      y: pad.top + ch - (p.value / maxVal) * ch,
      value: p.value,
    }));

    /* Gradient fill */
    const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
    grad.addColorStop(0, `${stroke}38`);
    grad.addColorStop(0.6, `${stroke}12`);
    grad.addColorStop(1, `${stroke}02`);

    ctx.beginPath();
    smoothLine(ctx, pts);
    ctx.lineTo(pts[pts.length - 1].x, pad.top + ch);
    ctx.lineTo(pts[0].x, pad.top + ch);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    /* Trend line */
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 2.8;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();
    smoothLine(ctx, pts);
    ctx.stroke();

    /* Dots — only at peaks and endpoints */
    const peakValue = Math.max(...pts.map((p) => p.value));
    pts.forEach((p, i) => {
      const isPeak = p.value === peakValue && p.value > 0;
      const isEnd = i === 0 || i === pts.length - 1;
      if (!isPeak && !isEnd) return;
      ctx.beginPath();
      ctx.fillStyle = colors.surface;
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 2.2;
      ctx.arc(p.x, p.y, isPeak ? 4.5 : 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      if (isPeak && p.value > 0) {
        ctx.fillStyle = colors.ink;
        ctx.font = "700 11px IBM Plex Sans, Segoe UI, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(String(p.value), p.x, p.y - 8);
      }
    });

    /* X labels */
    const labelEvery = Math.max(
      1,
      Math.ceil(series.length / Math.max(4, Math.floor(w / 68)))
    );
    ctx.fillStyle = colors.muted;
    ctx.font = "10px IBM Plex Sans, Segoe UI, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    series.forEach((p, i) => {
      if (i % labelEvery !== 0 && i !== series.length - 1) return;
      ctx.fillText(p.label, pad.left + step * i, h - pad.bottom + 10);
    });
  };

  const drawAll = () => {
    const trends = charts.trends || [];
    trendCards.forEach((card, index) => {
      const canvas = card.querySelector("canvas");
      const trendId = card.dataset.trendChart;
      const trend = trends.find((t) => t.id === trendId) || trends[index];
      drawTrend(canvas, trend?.series || [], index);
    });
  };

  let frame = null;
  const schedule = () => {
    if (panels.visuals?.hidden) return;
    if (frame) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(drawAll);
  };

  if (!panels.visuals?.hidden) drawAll();

  if ("ResizeObserver" in window) {
    const obs = new ResizeObserver(schedule);
    trendCards.forEach((card) => {
      const c = card.querySelector("canvas");
      if (c) obs.observe(c);
    });
  } else {
    window.addEventListener("resize", schedule);
  }
});
