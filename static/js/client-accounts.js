(() => {
  function wireFilter(inputId, listId, emptyId) {
    const input = document.getElementById(inputId);
    const list = document.getElementById(listId);
    const empty = document.getElementById(emptyId);
    if (!input || !list) return;

    const items = Array.from(list.querySelectorAll(".client-accounts-list__item"));

    function applyFilter() {
      const query = input.value.trim().toLowerCase();
      let visible = 0;

      items.forEach((item) => {
        const haystack = item.dataset.search || "";
        const show = !query || haystack.includes(query);
        item.hidden = !show;
        if (show) visible += 1;
      });

      if (empty) empty.hidden = visible !== 0;
      list.hidden = visible === 0;
    }

    input.addEventListener("input", applyFilter);
  }

  wireFilter("corporate-client-filter", "corporate-client-list", "corporate-client-empty");
  wireFilter("individual-client-filter", "individual-client-list", "individual-client-empty");

  const page = document.getElementById("client-accounts-page");
  const searchUrl = page?.dataset.clientSearchUrl;
  const listUrl = page?.dataset.listUrl;
  const searchInput = document.getElementById("client-accounts-search");
  const resultsList = document.getElementById("client-accounts-results");

  if (!searchUrl || !listUrl || !searchInput || !resultsList) return;

  let searchTimer = null;
  let activeIndex = -1;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function hideResults() {
    resultsList.hidden = true;
    resultsList.innerHTML = "";
    searchInput.setAttribute("aria-expanded", "false");
    searchInput.removeAttribute("aria-activedescendant");
    activeIndex = -1;
  }

  function openClient(clientId) {
    hideResults();
    searchInput.value = "";
    window.location.assign(`${listUrl}?client=${encodeURIComponent(clientId)}`);
  }

  function showResults(results, emptyMessage) {
    resultsList.innerHTML = "";

    if (!results.length) {
      const empty = document.createElement("li");
      empty.className = "client-search__empty";
      empty.textContent = emptyMessage || "No matching clients";
      resultsList.appendChild(empty);
      resultsList.hidden = false;
      searchInput.setAttribute("aria-expanded", "true");
      return;
    }

    results.forEach((client, index) => {
      const item = document.createElement("li");
      item.className = "client-search__option";
      item.id = `client-accounts-option-${index}`;
      item.setAttribute("role", "option");
      item.dataset.clientId = client.id;
      item.innerHTML = `
        <strong>${escapeHtml(client.name)}</strong>
        <span>${escapeHtml(client.label || client.phone || client.email || "")}</span>
      `;
      item.addEventListener("mousedown", (event) => {
        event.preventDefault();
        openClient(client.id);
      });
      resultsList.appendChild(item);
    });

    resultsList.hidden = false;
    searchInput.setAttribute("aria-expanded", "true");
  }

  function fetchClients(query) {
    const url = new URL(searchUrl, window.location.origin);
    url.searchParams.set("q", query);
    fetch(url.toString(), {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((payload) => {
        showResults(payload.results || [], "No matching clients");
      })
      .catch(() => {
        showResults([], "Could not load clients");
      });
  }

  function setActiveOption(index) {
    const options = Array.from(
      resultsList.querySelectorAll(".client-search__option")
    );
    options.forEach((option, optionIndex) => {
      option.classList.toggle("is-active", optionIndex === index);
    });
    if (index >= 0 && options[index]) {
      options[index].scrollIntoView({ block: "nearest" });
      searchInput.setAttribute("aria-activedescendant", options[index].id);
    } else {
      searchInput.removeAttribute("aria-activedescendant");
    }
  }

  searchInput.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    const query = searchInput.value.trim();
    if (!query) {
      hideResults();
      return;
    }
    searchTimer = window.setTimeout(() => fetchClients(query), 220);
  });

  searchInput.addEventListener("keydown", (event) => {
    if (resultsList.hidden) return;
    const options = Array.from(
      resultsList.querySelectorAll(".client-search__option")
    );
    if (!options.length) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      activeIndex = Math.min(activeIndex + 1, options.length - 1);
      setActiveOption(activeIndex);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      setActiveOption(activeIndex);
    } else if (event.key === "Enter") {
      if (activeIndex >= 0 && options[activeIndex]) {
        event.preventDefault();
        openClient(options[activeIndex].dataset.clientId);
      }
    } else if (event.key === "Escape") {
      hideResults();
    }
  });

  document.addEventListener("click", (event) => {
    if (event.target === searchInput || resultsList.contains(event.target)) {
      return;
    }
    hideResults();
  });
})();
