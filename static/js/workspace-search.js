/* Workspace command palette — Ctrl+K global search (matters, clients, tasks). */
document.addEventListener("DOMContentLoaded", () => {
  const dialog = document.getElementById("cmdk");
  const trigger = document.getElementById("cmdk-trigger");
  if (!dialog || !trigger) return;

  const input = dialog.querySelector("#cmdk-input");
  const results = dialog.querySelector("#cmdk-results");
  const searchUrl = dialog.getAttribute("data-search-url");
  let activeIndex = -1;
  let controller = null;

  const items = () => [...results.querySelectorAll(".cmdk__item")];

  const setActive = (index) => {
    const list = items();
    activeIndex = list.length ? (index + list.length) % list.length : -1;
    list.forEach((item, i) => {
      const on = i === activeIndex;
      item.classList.toggle("is-active", on);
      item.setAttribute("aria-selected", on ? "true" : "false");
      if (on) item.scrollIntoView({ block: "nearest" });
    });
  };

  const open = () => {
    if (dialog.open) return;
    dialog.showModal();
    input.select();
    input.focus();
  };

  const close = () => dialog.close();

  const hint = (text) => {
    results.replaceChildren();
    const p = document.createElement("p");
    p.className = "cmdk__hint";
    p.textContent = text;
    results.appendChild(p);
  };

  const render = (groups) => {
    results.replaceChildren();
    if (!groups.length) {
      hint("No results — try a client name, case number, or task title.");
      return;
    }
    groups.forEach((group) => {
      const section = document.createElement("div");
      section.className = "cmdk__group";

      const label = document.createElement("p");
      label.className = "cmdk__group-label";
      label.textContent = group.label;
      section.appendChild(label);

      group.items.forEach((item) => {
        const a = document.createElement("a");
        a.className = "cmdk__item";
        a.href = item.url;
        a.setAttribute("role", "option");

        const title = document.createElement("span");
        title.className = "cmdk__item-title";
        title.textContent = item.title;
        a.appendChild(title);

        if (item.meta) {
          const meta = document.createElement("span");
          meta.className = "cmdk__item-meta";
          meta.textContent = item.meta;
          a.appendChild(meta);
        }
        section.appendChild(a);
      });
      results.appendChild(section);
    });
    setActive(0);
  };

  const search = () => {
    const q = input.value.trim();
    if (controller) controller.abort();
    if (q.length < 2) {
      hint("Type at least 2 characters to search matters, clients, and tasks.");
      return;
    }
    controller = new AbortController();
    fetch(`${searchUrl}?q=${encodeURIComponent(q)}`, {
      signal: controller.signal,
      headers: { "X-Requested-With": "fetch" },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.q === q) render(data.groups || []);
      })
      .catch((err) => {
        if (err.name !== "AbortError") hint("Search failed — try again.");
      });
  };

  let debounce = null;
  input.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(search, 220);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive(activeIndex + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive(activeIndex - 1);
    } else if (event.key === "Enter") {
      const list = items();
      const target = list[activeIndex] || list[0];
      if (target) {
        event.preventDefault();
        window.location.href = target.href;
      }
    }
  });

  trigger.addEventListener("click", open);

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (dialog.open) close();
      else open();
    }
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) close();
  });
});
