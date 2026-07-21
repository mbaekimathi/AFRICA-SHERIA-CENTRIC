(function () {
  "use strict";

  var root = document.querySelector("[data-blog-track-url]");
  if (!root) return;

  var trackUrl = root.getAttribute("data-blog-track-url");
  if (!trackUrl) return;

  function sendEvent(eventType) {
    if (!eventType) return;
    var payload = JSON.stringify({ event_type: eventType });
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(
          trackUrl,
          new Blob([payload], { type: "application/json" })
        );
        return;
      }
    } catch (err) {
      /* fall through */
    }
    try {
      fetch(trackUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
        credentials: "same-origin",
      });
    } catch (err2) {
      /* ignore tracking failures */
    }
  }

  document.addEventListener(
    "click",
    function (event) {
      var target = event.target.closest("[data-blog-event]");
      if (!target) return;
      sendEvent(target.getAttribute("data-blog-event"));
    },
    true
  );
})();
