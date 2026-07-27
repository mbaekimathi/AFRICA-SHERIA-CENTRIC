(function () {
  var page = document.getElementById("whatsapp-inbox-page");
  if (!page) return;

  var pollUrl = page.getAttribute("data-poll-url") || "";
  if (!pollUrl) return;

  var activeId = page.getAttribute("data-active-id") || "";
  var lastMessageId = parseInt(page.getAttribute("data-last-message-id") || "0", 10) || 0;
  var thread = document.getElementById("wa-message-thread");
  var timer = null;

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function appendMessages(messages) {
    if (!thread || !messages || !messages.length) return;
    var empty = thread.querySelector(".empty-state");
    if (empty) empty.remove();
    messages.forEach(function (msg) {
      if (!msg || !msg.id) return;
      if (thread.querySelector('[data-message-id="' + msg.id + '"]')) return;
      var dir = msg.direction === "out" ? "out" : "in";
      var bubble = document.createElement("div");
      bubble.className = "wa-bubble wa-bubble--" + dir;
      bubble.setAttribute("data-message-id", String(msg.id));
      var when = "";
      try {
        when = new Date(msg.created_at).toLocaleString();
      } catch (e) {
        when = msg.created_at || "";
      }
      bubble.innerHTML =
        escapeHtml(msg.body) +
        '<span class="wa-bubble__meta">' +
        escapeHtml(when) +
        " · " +
        escapeHtml(msg.status || "") +
        "</span>";
      thread.appendChild(bubble);
      lastMessageId = Math.max(lastMessageId, msg.id);
    });
    thread.scrollTop = thread.scrollHeight;
  }

  function poll() {
    var url = pollUrl + "?after=" + encodeURIComponent(String(lastMessageId || 0));
    if (activeId) {
      url += "&c=" + encodeURIComponent(activeId);
    }
    fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        if (!res.ok) throw new Error("poll failed");
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.ok) return;
        appendMessages(data.messages || []);
      })
      .catch(function () {
        /* ignore transient poll errors */
      });
  }

  if (thread) {
    thread.scrollTop = thread.scrollHeight;
  }

  timer = window.setInterval(poll, 8000);
  window.addEventListener("beforeunload", function () {
    if (timer) window.clearInterval(timer);
  });
})();
