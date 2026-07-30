// Sketch pad for digital signatures (stamp page + default signature page).
document.addEventListener("DOMContentLoaded", () => {
  const pad = document.querySelector("[data-signature-pad]");
  if (!pad) return;

  const canvas = pad.querySelector("[data-signature-canvas]");
  const field = pad.querySelector("[data-signature-drawing]");
  if (!canvas || !field) return;

  const form = pad.closest("form");
  const preview = pad.querySelector("[data-signature-preview]");
  const placeholder = pad.querySelector("[data-signature-placeholder]");
  const kicker = pad.querySelector("[data-signature-kicker]");
  const cue = pad.querySelector("[data-signature-cue]");
  const upload = pad.querySelector("[data-signature-upload]");
  const uploadName = pad.querySelector("[data-signature-upload-name]");
  const undoBtn = pad.querySelector("[data-signature-undo]");
  const clearBtn = pad.querySelector("[data-signature-clear]");
  const penBtns = Array.from(pad.querySelectorAll("[data-signature-width]"));

  const ctx = canvas.getContext("2d");
  const INK = "#101828";
  const strokes = [];
  let current = null;
  let baseWidth = Number(
    pad.querySelector("[data-signature-width].is-active")?.dataset
      .signatureWidth || 3
  );
  let previewObjectUrl = "";

  const cssSize = () => ({
    width: canvas.clientWidth || 1,
    height: canvas.clientHeight || 1,
  });

  const paintStrokes = (target, offsetX = 0, offsetY = 0) => {
    target.lineCap = "round";
    target.lineJoin = "round";
    target.strokeStyle = INK;
    target.fillStyle = INK;

    strokes.forEach((stroke) => {
      const points = stroke.points;
      if (points.length === 1) {
        const dot = points[0];
        target.beginPath();
        target.arc(
          dot.x - offsetX,
          dot.y - offsetY,
          dot.width / 2,
          0,
          Math.PI * 2
        );
        target.fill();
        return;
      }
      for (let i = 1; i < points.length; i += 1) {
        const from = points[i - 1];
        const to = points[i];
        target.beginPath();
        target.lineWidth = to.width;
        target.moveTo(from.x - offsetX, from.y - offsetY);
        target.quadraticCurveTo(
          from.x - offsetX,
          from.y - offsetY,
          (from.x + to.x) / 2 - offsetX,
          (from.y + to.y) / 2 - offsetY
        );
        target.lineTo(to.x - offsetX, to.y - offsetY);
        target.stroke();
      }
    });
  };

  const redraw = () => {
    const dpr = window.devicePixelRatio || 1;
    const { width, height } = cssSize();
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    paintStrokes(ctx);
  };

  const hasInk = () => strokes.some((stroke) => stroke.points.length > 0);

  // Export just the ink, so the preview and the saved file match.
  const exportInk = () => {
    const bounds = { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity };
    strokes.forEach((stroke) =>
      stroke.points.forEach((point) => {
        const reach = (point.width || baseWidth) / 2 + 1;
        bounds.left = Math.min(bounds.left, point.x - reach);
        bounds.top = Math.min(bounds.top, point.y - reach);
        bounds.right = Math.max(bounds.right, point.x + reach);
        bounds.bottom = Math.max(bounds.bottom, point.y + reach);
      })
    );
    if (!Number.isFinite(bounds.left)) return "";

    const pad = 10;
    const { width: maxWidth, height: maxHeight } = cssSize();
    const left = Math.max(bounds.left - pad, 0);
    const top = Math.max(bounds.top - pad, 0);
    const width = Math.min(bounds.right + pad, maxWidth) - left;
    const height = Math.min(bounds.bottom + pad, maxHeight) - top;
    if (width <= 0 || height <= 0) return "";

    const dpr = window.devicePixelRatio || 1;
    const out = document.createElement("canvas");
    out.width = Math.round(width * dpr);
    out.height = Math.round(height * dpr);
    const outCtx = out.getContext("2d");
    outCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    paintStrokes(outCtx, left, top);
    return out.toDataURL("image/png");
  };

  const showPreview = (src, { name = "", kickerText = "Ready to save" } = {}) => {
    if (preview) {
      preview.src = src;
      preview.alt = name || "Signature preview";
      preview.hidden = false;
      preview.removeAttribute("hidden");
    }
    if (placeholder) {
      placeholder.hidden = true;
      placeholder.setAttribute("hidden", "");
    }
    if (kicker) {
      kicker.textContent = kickerText;
      kicker.classList.add("is-live");
    }
    pad.classList.add("signature-pad--active");
  };

  const clearPreview = () => {
    if (preview) {
      preview.removeAttribute("src");
      preview.hidden = true;
      preview.setAttribute("hidden", "");
    }
    if (placeholder) {
      placeholder.hidden = false;
      placeholder.removeAttribute("hidden");
    }
    if (kicker) {
      kicker.textContent = "Nothing signed yet";
      kicker.classList.remove("is-live");
    }
    pad.classList.remove("signature-pad--active");
  };

  const syncField = () => {
    const ink = hasInk() ? exportInk() : "";
    field.value = ink;
    if (cue) cue.hidden = Boolean(ink);
    if (ink) showPreview(ink, { kickerText: "Ready to save" });
  };

  // Speed-sensitive width keeps the line lively instead of flat.
  const widthFor = (from, to) => {
    if (!from) return baseWidth;
    const distance = Math.hypot(to.x - from.x, to.y - from.y);
    const scale = Math.max(0.45, Math.min(1.35, 1.35 - distance / 26));
    const previous = from.width || baseWidth;
    return previous + (baseWidth * scale - previous) * 0.4;
  };

  const pointFrom = (event) => {
    const rect = canvas.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
      width: baseWidth,
    };
  };

  const startStroke = (event) => {
    if (event.button != null && event.button !== 0 && event.pointerType === "mouse") {
      return;
    }
    canvas.setPointerCapture?.(event.pointerId);
    current = { points: [pointFrom(event)] };
    strokes.push(current);
    if (cue) cue.hidden = true;
    redraw();
    event.preventDefault();
  };

  const extendStroke = (event) => {
    if (!current) return;
    const points = current.points;
    const previous = points[points.length - 1];
    const point = pointFrom(event);
    if (Math.hypot(point.x - previous.x, point.y - previous.y) < 0.8) return;
    point.width = widthFor(previous, point);
    points.push(point);
    redraw();
    event.preventDefault();
  };

  const endStroke = (event) => {
    if (!current) return;
    current = null;
    canvas.releasePointerCapture?.(event.pointerId);
    syncField();
  };

  canvas.addEventListener("pointerdown", startStroke);
  canvas.addEventListener("pointermove", extendStroke);
  canvas.addEventListener("pointerup", endStroke);
  canvas.addEventListener("pointercancel", endStroke);
  canvas.addEventListener("pointerleave", (event) => {
    if (current) endStroke(event);
  });

  penBtns.forEach((button) => {
    button.addEventListener("click", () => {
      baseWidth = Number(button.dataset.signatureWidth) || 3;
      penBtns.forEach((other) => {
        const active = other === button;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-pressed", active ? "true" : "false");
      });
    });
  });

  undoBtn?.addEventListener("click", () => {
    strokes.pop();
    redraw();
    if (hasInk()) {
      syncField();
    } else {
      field.value = "";
      if (cue) cue.hidden = false;
      clearPreview();
    }
  });

  clearBtn?.addEventListener("click", () => {
    strokes.length = 0;
    current = null;
    redraw();
    field.value = "";
    if (cue) cue.hidden = false;
    if (upload) upload.value = "";
    if (uploadName) {
      uploadName.textContent = uploadName.dataset.defaultLabel || uploadName.textContent;
    }
    clearPreview();
  });

  upload?.addEventListener("change", () => {
    const file = upload.files && upload.files[0];
    if (!file || !file.type.startsWith("image/")) return;
    strokes.length = 0;
    redraw();
    field.value = "";
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = URL.createObjectURL(file);
    if (uploadName) {
      if (!uploadName.dataset.defaultLabel) {
        uploadName.dataset.defaultLabel = uploadName.textContent.trim();
      }
      uploadName.textContent = file.name;
    }
    showPreview(previewObjectUrl, { name: file.name });
  });

  form?.addEventListener("submit", syncField);

  const observer = new ResizeObserver(() => redraw());
  observer.observe(canvas);
  redraw();
});
