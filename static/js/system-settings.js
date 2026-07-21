document.addEventListener("DOMContentLoaded", () => {
  const trendElement = document.getElementById("analytics-trend-data");
  const statusElement = document.getElementById("analytics-status-data");
  const trendCanvas = document.getElementById("performance-trend-chart");
  const statusCanvas = document.getElementById("status-chart");
  const gaugeCards = Array.from(document.querySelectorAll("[data-gauge]"));

  if (!trendElement || !statusElement || !trendCanvas || !statusCanvas) return;

  const trend = JSON.parse(trendElement.textContent || "[]");
  const status = JSON.parse(statusElement.textContent || "{}");

  const palette = () => {
    const styles = getComputedStyle(document.body);
    const value = (name, fallback) =>
      styles.getPropertyValue(name).trim() || fallback;
    return {
      accent: value("--accent", "#4f46e5"),
      ink: value("--ink", "#18202f"),
      muted: value("--ink-muted", "#667085"),
      line: value("--line", "#e4e7ec"),
      surface: value("--surface", "#ffffff"),
      success: value("--success", "#067647"),
      danger: value("--danger", "#b42318"),
      warning: "#d97706",
    };
  };

  const toneColor = (tone, colors) => {
    if (tone === "critical") return colors.danger;
    if (tone === "warning") return colors.warning;
    return colors.success;
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

  const drawTrend = () => {
    const colors = palette();
    const { context, width, height } = prepare(trendCanvas);
    context.clearRect(0, 0, width, height);
    if (!trend.length) {
      emptyState(context, width, height, colors, "Waiting for request telemetry");
      return;
    }

    const padding = { top: 18, right: 18, bottom: 34, left: 42 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const maxRequests = Math.max(1, ...trend.map((point) => point.requests));
    const maxLatency = Math.max(1, ...trend.map((point) => point.latency));
    const step = chartWidth / Math.max(1, trend.length);
    const barWidth = Math.max(3, Math.min(18, step * 0.48));

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
      const label = Math.round(maxLatency * (1 - index / 4));
      context.fillText(`${label}ms`, padding.left - 7, y);
    }

    context.fillStyle = `${colors.accent}2b`;
    trend.forEach((point, index) => {
      const x = padding.left + step * index + step / 2;
      const barHeight = (point.requests / maxRequests) * chartHeight;
      context.fillRect(x - barWidth / 2, padding.top + chartHeight - barHeight, barWidth, barHeight);
    });

    context.strokeStyle = colors.accent;
    context.lineWidth = 2.5;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.beginPath();
    trend.forEach((point, index) => {
      const x = padding.left + step * index + step / 2;
      const y = padding.top + chartHeight - (point.latency / maxLatency) * chartHeight;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.stroke();

    trend.forEach((point, index) => {
      const x = padding.left + step * index + step / 2;
      const y = padding.top + chartHeight - (point.latency / maxLatency) * chartHeight;
      context.beginPath();
      context.fillStyle = colors.surface;
      context.strokeStyle = colors.accent;
      context.lineWidth = 2;
      context.arc(x, y, 3.2, 0, Math.PI * 2);
      context.fill();
      context.stroke();
    });

    const labelEvery = Math.max(1, Math.ceil(trend.length / Math.max(3, Math.floor(width / 70))));
    context.fillStyle = colors.muted;
    context.font = "10px IBM Plex Sans, Segoe UI, sans-serif";
    context.textAlign = "center";
    context.textBaseline = "top";
    trend.forEach((point, index) => {
      if (index % labelEvery !== 0 && index !== trend.length - 1) return;
      const x = padding.left + step * index + step / 2;
      context.fillText(point.label, x, height - padding.bottom + 10);
    });
  };

  const drawStatus = () => {
    const colors = palette();
    const { context, width, height } = prepare(statusCanvas);
    context.clearRect(0, 0, width, height);
    const values = [
      Number(status.success || 0),
      Number(status.client_error || 0),
      Number(status.server_error || 0),
    ];
    const total = values.reduce((sum, value) => sum + value, 0);
    if (!total) {
      emptyState(context, width, height, colors, "No responses yet");
      return;
    }

    const radius = Math.min(width, height) * 0.39;
    const innerRadius = radius * 0.68;
    const centerX = width / 2;
    const centerY = height / 2;
    const segmentColors = [colors.success, colors.warning, colors.danger];
    let angle = -Math.PI / 2;

    values.forEach((value, index) => {
      if (!value) return;
      const nextAngle = angle + (value / total) * Math.PI * 2;
      context.beginPath();
      context.arc(centerX, centerY, radius, angle, nextAngle);
      context.arc(centerX, centerY, innerRadius, nextAngle, angle, true);
      context.closePath();
      context.fillStyle = segmentColors[index];
      context.fill();
      angle = nextAngle;
    });

    context.fillStyle = colors.ink;
    context.font = "700 18px IBM Plex Sans, Segoe UI, sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(String(total), centerX, centerY - 5);
    context.fillStyle = colors.muted;
    context.font = "10px IBM Plex Sans, Segoe UI, sans-serif";
    context.fillText("responses", centerX, centerY + 12);
  };

  const drawGauge = (card) => {
    const canvas = card.querySelector("canvas");
    if (!canvas) return;
    const colors = palette();
    const { context, width, height } = prepare(canvas);
    context.clearRect(0, 0, width, height);

    const value = Math.max(0, Math.min(100, Number(card.dataset.value || 0)));
    const display = card.dataset.display || `${Math.round(value)}%`;
    const tone = card.dataset.tone || "good";
    const color = toneColor(tone, colors);
    const centerX = width / 2;
    const centerY = height / 2 + 8;
    const radius = Math.min(width, height) * 0.38;
    const start = Math.PI * 0.8;
    const end = Math.PI * 2.2;
    const sweep = end - start;

    context.lineCap = "round";
    context.lineWidth = Math.max(8, radius * 0.22);
    context.strokeStyle = colors.line;
    context.beginPath();
    context.arc(centerX, centerY, radius, start, end);
    context.stroke();

    context.strokeStyle = color;
    context.beginPath();
    context.arc(centerX, centerY, radius, start, start + sweep * (value / 100));
    context.stroke();

    context.fillStyle = colors.ink;
    context.font = "700 15px IBM Plex Sans, Segoe UI, sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(display, centerX, centerY - 2);
  };

  const drawAll = () => {
    drawTrend();
    drawStatus();
    gaugeCards.forEach(drawGauge);
  };

  let resizeFrame = null;
  const scheduleDraw = () => {
    if (resizeFrame) cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(drawAll);
  };

  drawAll();
  if ("ResizeObserver" in window) {
    const observer = new ResizeObserver(scheduleDraw);
    observer.observe(trendCanvas);
    observer.observe(statusCanvas);
    gaugeCards.forEach((card) => {
      const canvas = card.querySelector("canvas");
      if (canvas) observer.observe(canvas);
    });
  } else {
    window.addEventListener("resize", scheduleDraw);
  }
});
