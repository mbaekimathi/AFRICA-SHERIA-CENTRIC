document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("live-task-modal");
  const fab = document.getElementById("open-live-task-modal");
  const closeBtn = document.getElementById("close-live-task-modal");
  const openBtns = document.querySelectorAll(".open-live-task-modal");

  if (!modal) return;

  // Re-parent the FAB to <body> so position:fixed is viewport-relative
  // (ancestor transform / overflow:clip otherwise makes it scroll with content).
  if (fab && fab.parentElement !== document.body) {
    document.body.appendChild(fab);
  }

  const openModal = () => {
    if (typeof modal.showModal === "function") {
      if (!modal.open) modal.showModal();
    } else {
      modal.setAttribute("open", "");
    }
  };

  const closeModal = () => {
    if (typeof modal.close === "function") {
      modal.close();
    } else {
      modal.removeAttribute("open");
    }
  };

  const POSITION_KEY = "sheria.liveTaskFab.pos";
  const DRAG_THRESHOLD = 6;
  let suppressClick = false;

  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  const readSavedPosition = () => {
    try {
      const raw = localStorage.getItem(POSITION_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (
        typeof parsed?.left !== "number" ||
        typeof parsed?.top !== "number" ||
        Number.isNaN(parsed.left) ||
        Number.isNaN(parsed.top)
      ) {
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  };

  const savePosition = (left, top) => {
    try {
      localStorage.setItem(POSITION_KEY, JSON.stringify({ left, top }));
    } catch {
      /* ignore quota / private mode */
    }
  };

  const applyPosition = (left, top) => {
    if (!fab) return;
    const size = fab.offsetWidth || 58;
    const maxLeft = Math.max(8, window.innerWidth - size - 8);
    const maxTop = Math.max(8, window.innerHeight - size - 8);
    const nextLeft = clamp(left, 8, maxLeft);
    const nextTop = clamp(top, 8, maxTop);
    fab.style.left = `${nextLeft}px`;
    fab.style.top = `${nextTop}px`;
    fab.style.right = "auto";
    fab.style.bottom = "auto";
    fab.classList.add("is-placed");
    return { left: nextLeft, top: nextTop };
  };

  const restorePosition = () => {
    if (!fab) return;
    const saved = readSavedPosition();
    if (!saved) return;
    applyPosition(saved.left, saved.top);
  };

  const enableDrag = () => {
    if (!fab) return;

    let pointerId = null;
    let startX = 0;
    let startY = 0;
    let originLeft = 0;
    let originTop = 0;
    let dragged = false;

    const onPointerMove = (event) => {
      if (pointerId !== event.pointerId) return;
      const dx = event.clientX - startX;
      const dy = event.clientY - startY;
      if (!dragged && Math.hypot(dx, dy) >= DRAG_THRESHOLD) {
        dragged = true;
        fab.classList.add("is-dragging");
      }
      if (!dragged) return;
      event.preventDefault();
      applyPosition(originLeft + dx, originTop + dy);
    };

    const onPointerUp = (event) => {
      if (pointerId !== event.pointerId) return;
      fab.releasePointerCapture?.(pointerId);
      pointerId = null;
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);

      if (dragged) {
        fab.classList.remove("is-dragging");
        const rect = fab.getBoundingClientRect();
        const placed = applyPosition(rect.left, rect.top);
        if (placed) savePosition(placed.left, placed.top);
        suppressClick = true;
        window.setTimeout(() => {
          suppressClick = false;
        }, 0);
      }
    };

    fab.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      const rect = fab.getBoundingClientRect();
      pointerId = event.pointerId;
      startX = event.clientX;
      startY = event.clientY;
      originLeft = rect.left;
      originTop = rect.top;
      dragged = false;
      fab.setPointerCapture?.(pointerId);
      window.addEventListener("pointermove", onPointerMove, { passive: false });
      window.addEventListener("pointerup", onPointerUp);
      window.addEventListener("pointercancel", onPointerUp);
    });

    window.addEventListener("resize", () => {
      if (!fab.classList.contains("is-placed")) return;
      const rect = fab.getBoundingClientRect();
      const placed = applyPosition(rect.left, rect.top);
      if (placed) savePosition(placed.left, placed.top);
    });
  };

  restorePosition();
  enableDrag();

  openBtns.forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      if (suppressClick) return;
      openModal();
    });
  });
  closeBtn?.addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
});
