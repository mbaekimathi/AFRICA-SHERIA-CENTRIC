/**
 * Place the session user's own stamp and signature on a document.
 *
 * Case-page checkboxes open the actual-document editor. In that editor the
 * document itself is the drag surface, with marks saved as sheet percentages.
 */
(function () {
  "use strict";

  var DEFAULTS = {
    signature: { x: 8, y: 74, width: 30 },
    stamp: { x: 62, y: 68, width: 22 },
  };
  var MIN_WIDTH = 6;
  var MAX_WIDTH = 90;

  var modal = null;
  var current = null;

  document.addEventListener("DOMContentLoaded", function () {
    initEditorLinks();
    modal = document.querySelector("[data-doc-marks-modal]");
    if (!modal) return;

    document.querySelectorAll("[data-doc-marks]").forEach(initRow);
    initModal();
    if (modal.hasAttribute("data-doc-marks-page")) {
      var kind = modal.dataset.initialKind || "";
      openStudio(modal, kind ? { kind: kind, enable: true } : null);
    }
  });

  function initEditorLinks() {
    document
      .querySelectorAll("[data-doc-mark-editor-url]")
      .forEach(function (input) {
        input.addEventListener("change", function () {
          window.location.assign(input.dataset.docMarkEditorUrl);
        });
      });
  }

  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input && input.value) return input.value;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function savedMarks(row) {
    var node = document.getElementById(row.dataset.marksId || "");
    if (!node) return [];
    try {
      return JSON.parse(node.textContent) || [];
    } catch (err) {
      return [];
    }
  }

  function initRow(row) {
    row.marks = savedMarks(row);
    row.querySelectorAll("[data-doc-mark-toggle]").forEach(function (input) {
      input.addEventListener("change", function () {
        openStudio(row, {
          kind: input.dataset.docMarkToggle,
          enable: input.checked,
        });
      });
    });
    var open = row.querySelector("[data-doc-marks-open]");
    if (open) {
      open.addEventListener("click", function () {
        openStudio(row, null);
      });
    }
  }

  function syncRow(row) {
    var kinds = row.marks.map(function (mark) {
      return mark.kind;
    });
    row.querySelectorAll("[data-doc-mark-toggle]").forEach(function (input) {
      input.checked = kinds.indexOf(input.dataset.docMarkToggle) !== -1;
    });
    var open = row.querySelector("[data-doc-marks-open]");
    if (open) open.hidden = kinds.length === 0;
  }

  /* ---------------------------------------------------------------- studio */

  function initModal() {
    modal.querySelectorAll("[data-doc-marks-studio-toggle]").forEach(function (input) {
      input.addEventListener("change", function () {
        var kind = input.dataset.docMarksStudioToggle;
        if (input.checked) addMark(kind, null);
        else removeMark(kind);
      });
    });
    modal
      .querySelector("[data-doc-marks-save]")
      .addEventListener("click", saveStudio);
    ["[data-doc-marks-cancel]", "[data-doc-marks-close]"].forEach(function (sel) {
      var button = modal.querySelector(sel);
      if (button) button.addEventListener("click", closeStudio);
    });
    modal.addEventListener("cancel", function (event) {
      event.preventDefault();
      closeStudio();
    });
    window.addEventListener("resize", function () {
      if (current) current.marks.forEach(rescale);
    });
  }

  function openStudio(row, intent) {
    current = { row: row, marks: [], removed: [] };

    modal.querySelector("[data-doc-marks-title]").textContent =
      row.dataset.documentTitle || "Document";
    setStatus("");
    renderPreview(row);

    var layer = modal.querySelector("[data-doc-marks-layer]");
    layer.textContent = "";

    row.marks.forEach(function (mark) {
      addMark(mark.kind, mark);
    });
    ["signature", "stamp"].forEach(function (kind) {
      setStudioToggle(kind, !!findMark(kind));
    });
    if (intent && intent.enable) addMark(intent.kind, null);
    else if (intent) removeMark(intent.kind);

    if (
      !modal.hasAttribute("data-doc-marks-page") &&
      typeof modal.showModal === "function" &&
      !modal.open
    ) {
      modal.showModal();
    }
    // The sheet only has a reliable size once it is on screen.
    requestAnimationFrame(function () {
      if (current) current.marks.forEach(rescale);
    });
  }

  function closeStudio() {
    if (current) syncRow(current.row);
    if (modal.hasAttribute("data-doc-marks-page")) {
      window.location.assign(modal.dataset.returnUrl || "/");
      return;
    }
    current = null;
    if (modal.open) modal.close();
  }

  function renderPreview(row) {
    var host = modal.querySelector("[data-doc-marks-preview]");
    host.textContent = "";
    var kind = row.dataset.previewKind;
    var url = row.dataset.previewUrl;

    if (kind === "image" && url) {
      var image = document.createElement("img");
      image.className = "doc-marks-preview__image";
      image.src = url;
      image.alt = "";
      host.appendChild(image);
      return;
    }
    if (kind === "frame" && url) {
      var frame = document.createElement("iframe");
      frame.className = "doc-marks-preview__frame";
      frame.src = url;
      frame.title = row.dataset.documentTitle || "Document preview";
      frame.setAttribute("loading", "lazy");
      host.appendChild(frame);
      return;
    }
    var blank = document.createElement("p");
    blank.className = "doc-marks-preview__blank";
    blank.textContent =
      "No preview available — place your marks on the sheet and they are kept for this document.";
    host.appendChild(blank);
  }

  /* ----------------------------------------------------------------- marks */

  function findMark(kind) {
    if (!current) return null;
    for (var i = 0; i < current.marks.length; i += 1) {
      if (current.marks[i].kind === kind) return current.marks[i];
    }
    return null;
  }

  function addMark(kind, saved) {
    if (!current || findMark(kind)) return;
    var source = document.querySelector('[data-doc-mark-source="' + kind + '"]');
    if (!source) return;

    var content = source.content.cloneNode(true);
    var inner = document.createElement("div");
    inner.className = "doc-mark__inner";
    inner.appendChild(content);

    var element = document.createElement("div");
    element.className = "doc-mark";
    element.dataset.kind = kind;
    element.appendChild(inner);

    var handle = document.createElement("button");
    handle.type = "button";
    handle.className = "doc-mark__resize";
    handle.setAttribute("aria-label", "Resize " + kind);
    element.appendChild(handle);

    // Scanned ink blends with the page, which a transform would break, so it
    // is sized through the image itself instead.
    var isImage = !!inner.querySelector(
      ".doc-stamp__scan, .doc-signature__drawing"
    );
    element.classList.add(isImage ? "doc-mark--image" : "doc-mark--scaled");

    var position = saved || DEFAULTS[kind] || DEFAULTS.signature;
    var mark = {
      kind: kind,
      element: element,
      inner: inner,
      isImage: isImage,
      x: position.x,
      y: position.y,
      width: position.width,
      page: position.page || 1,
    };
    if (saved && saved.date) setMarkDate(inner, kind, saved.date);

    place(mark);
    modal.querySelector("[data-doc-marks-layer]").appendChild(element);
    current.marks.push(mark);

    element.addEventListener("pointerdown", function (event) {
      if (event.target === handle) startResize(event, mark, handle);
      else startDrag(event, mark);
    });

    setStudioToggle(kind, true);
    requestAnimationFrame(function () {
      rescale(mark);
    });
  }

  function removeMark(kind) {
    var mark = findMark(kind);
    if (!mark) return;
    mark.element.remove();
    current.marks = current.marks.filter(function (item) {
      return item !== mark;
    });
    if (current.removed.indexOf(kind) === -1) current.removed.push(kind);
    setStudioToggle(kind, false);
  }

  function setStudioToggle(kind, checked) {
    var input = modal.querySelector(
      '[data-doc-marks-studio-toggle="' + kind + '"]'
    );
    if (input) input.checked = checked;
  }

  function setMarkDate(inner, kind, text) {
    var node = inner.querySelector(
      kind === "stamp" ? ".doc-stamp__date" : ".doc-signature__date"
    );
    if (node) node.textContent = text;
  }

  function place(mark) {
    mark.element.style.left = mark.x + "%";
    mark.element.style.top = mark.y + "%";
    mark.element.style.width = mark.width + "%";
  }

  /**
   * Fit the mark artwork to the placed box.
   *
   * Scanned stamps scale with the image itself so nothing wraps them in a
   * transform — a transform would isolate them and break the multiply blend
   * that keeps leftover paper out of the document.
   */
  function rescale(mark) {
    if (mark.isImage) return;
    var sheet = modal.querySelector("[data-doc-marks-sheet]");
    if (!sheet) return;
    mark.inner.style.setProperty("--mark-scale", 1);
    var natural = mark.inner.offsetWidth;
    var height = mark.inner.offsetHeight;
    if (!natural || !height) return;
    var target = (mark.width / 100) * sheet.clientWidth;
    var scale = target / natural;
    mark.inner.style.setProperty("--mark-scale", scale);
    mark.element.style.height = height * scale + "px";
  }

  function sheetBox() {
    return modal.querySelector("[data-doc-marks-sheet]").getBoundingClientRect();
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function startDrag(event, mark) {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    event.preventDefault();
    var box = sheetBox();
    var start = mark.element.getBoundingClientRect();
    var grabX = event.clientX - start.left;
    var grabY = event.clientY - start.top;

    mark.element.classList.add("doc-mark--active");
    // Capture keeps the drag alive over the preview iframe.
    mark.element.setPointerCapture(event.pointerId);

    function move(moveEvent) {
      var x = ((moveEvent.clientX - grabX - box.left) / box.width) * 100;
      var y = ((moveEvent.clientY - grabY - box.top) / box.height) * 100;
      mark.x = clamp(x, 0, 100 - mark.width);
      mark.y = clamp(y, 0, 99);
      place(mark);
    }

    function stop() {
      mark.element.classList.remove("doc-mark--active");
      mark.element.removeEventListener("pointermove", move);
      mark.element.removeEventListener("pointerup", stop);
      mark.element.removeEventListener("pointercancel", stop);
    }

    mark.element.addEventListener("pointermove", move);
    mark.element.addEventListener("pointerup", stop);
    mark.element.addEventListener("pointercancel", stop);
  }

  function startResize(event, mark, handle) {
    event.preventDefault();
    event.stopPropagation();
    var box = sheetBox();
    var startX = event.clientX;
    var startWidth = mark.width;

    mark.element.classList.add("doc-mark--active");
    handle.setPointerCapture(event.pointerId);

    function move(moveEvent) {
      var delta = ((moveEvent.clientX - startX) / box.width) * 100;
      mark.width = clamp(startWidth + delta, MIN_WIDTH, MAX_WIDTH);
      if (mark.x + mark.width > 100) mark.x = Math.max(0, 100 - mark.width);
      place(mark);
      rescale(mark);
    }

    function stop() {
      mark.element.classList.remove("doc-mark--active");
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
      handle.removeEventListener("pointercancel", stop);
    }

    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
  }

  /* ------------------------------------------------------------------ save */

  function setStatus(text, isError) {
    var status = modal.querySelector("[data-doc-marks-status]");
    if (!status) return;
    status.textContent = text || "";
    status.classList.toggle("doc-marks-status--error", !!isError);
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: JSON.stringify(body),
    }).then(function (response) {
      if (!response.ok) throw new Error("save failed");
      return response.json();
    });
  }

  function saveStudio() {
    if (!current) return;
    var row = current.row;
    var url = row.dataset.saveUrl;
    var kept = current.marks.map(function (mark) {
      return mark.kind;
    });
    var removals = current.removed.filter(function (kind) {
      return kept.indexOf(kind) === -1;
    });

    setStatus("Saving…");
    var requests = current.marks
      .map(function (mark) {
        return post(url, {
          kind: mark.kind,
          page: mark.page,
          x: mark.x,
          y: mark.y,
          width: mark.width,
        });
      })
      .concat(
        removals.map(function (kind) {
          return post(url, { kind: kind, remove: true });
        })
      );

    Promise.all(requests)
      .then(function () {
        row.marks = current.marks.map(function (mark) {
          return {
            kind: mark.kind,
            page: mark.page,
            x: mark.x,
            y: mark.y,
            width: mark.width,
          };
        });
        closeStudio();
      })
      .catch(function () {
        setStatus("Could not save the placement. Try again.", true);
      });
  }
})();
