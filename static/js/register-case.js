(() => {
  const form = document.getElementById("register-case-form");
  if (!form) return;

  const searchUrl = form.dataset.clientSearchUrl;
  const suggestionsUrl = form.dataset.fieldSuggestionsUrl;
  const clientIdInput = document.getElementById("id_client");
  const searchInput = document.getElementById("id_client_search");
  const resultsList = document.getElementById("client-search-results");
  const selectedHint = document.getElementById("client-selected-hint");
  const partiesList = document.getElementById("parties-list");
  const addPartyBtn = document.getElementById("add-party-btn");
  const emptyTemplate = document.getElementById("party-empty-form");
  const totalFormsInput = document.getElementById("id_parties-TOTAL_FORMS");

  let searchTimer = null;
  let activeIndex = -1;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function firstPartyCard() {
    return partiesList?.querySelector('[data-client-party="true"]');
  }

  function fillClientParty(client) {
    const card = firstPartyCard();
    if (!card) return;
    const name = card.querySelector('[name$="-party_name"]');
    const phone = card.querySelector('[name$="-phone"]');
    const email = card.querySelector('[name$="-email"]');
    const category = card.querySelector('[name$="-category"]');
    const isClient = card.querySelector('[name$="-is_client_party"]');
    if (name) name.value = client.name || "";
    if (phone) phone.value = client.phone || "";
    if (email) email.value = client.email || "";
    if (category && client.category) category.value = client.category;
    if (isClient) isClient.value = "True";
  }

  function setSelectedClient(client) {
    if (!clientIdInput || !searchInput) return;
    clientIdInput.value = client.id;
    searchInput.value = client.name;
    if (selectedHint) {
      selectedHint.hidden = false;
      selectedHint.textContent = `Selected: ${client.label || client.name}${
        client.phone || client.meta ? ` · ${client.phone || client.meta}` : ""
      }`;
    }
    fillClientParty(client);
    hideClientResults();
  }

  function hideClientResults() {
    if (!resultsList || !searchInput) return;
    resultsList.hidden = true;
    resultsList.innerHTML = "";
    searchInput.setAttribute("aria-expanded", "false");
    activeIndex = -1;
  }

  function showClientResults(results, emptyMessage) {
    if (!resultsList || !searchInput) return;
    resultsList.innerHTML = "";
    if (!results.length) {
      const empty = document.createElement("li");
      empty.className = "client-search__empty";
      empty.textContent = emptyMessage || "No previous or matching clients";
      resultsList.appendChild(empty);
      resultsList.hidden = false;
      searchInput.setAttribute("aria-expanded", "true");
      return;
    }

    results.forEach((client, index) => {
      const item = document.createElement("li");
      item.className = "client-search__option";
      item.setAttribute("role", "option");
      item.dataset.index = String(index);
      item.innerHTML = `<strong>${escapeHtml(client.name)}</strong><span>${escapeHtml(
        client.phone || client.meta || client.email || ""
      )}</span>`;
      item.addEventListener("mousedown", (event) => {
        event.preventDefault();
        setSelectedClient(client);
      });
      resultsList.appendChild(item);
    });
    resultsList._results = results;
    resultsList.hidden = false;
    searchInput.setAttribute("aria-expanded", "true");
    activeIndex = -1;
  }

  async function fetchSuggestions(field, query) {
    if (!suggestionsUrl) return [];
    const url = `${suggestionsUrl}?field=${encodeURIComponent(field)}&q=${encodeURIComponent(
      query || ""
    )}`;
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) return [];
    const data = await response.json();
    return data.results || [];
  }

  async function runClientSearch(query) {
    if (!searchUrl) {
      hideClientResults();
      return;
    }
    const q = (query || "").trim();
    try {
      const url = `${searchUrl}?q=${encodeURIComponent(q)}`;
      const response = await fetch(url, {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        hideClientResults();
        return;
      }
      const data = await response.json();
      showClientResults(
        data.results || [],
        q ? "No matching clients found" : "No active clients yet"
      );
    } catch (_error) {
      hideClientResults();
    }
  }

  function highlightOption(index) {
    if (!resultsList) return;
    const options = resultsList.querySelectorAll(".client-search__option");
    options.forEach((el) => el.classList.remove("is-active"));
    if (index < 0 || index >= options.length) {
      activeIndex = -1;
      return;
    }
    activeIndex = index;
    options[index].classList.add("is-active");
    options[index].scrollIntoView({ block: "nearest" });
  }

  if (searchInput) {
    searchInput.addEventListener("focus", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => runClientSearch(searchInput.value), 50);
    });

    searchInput.addEventListener("input", () => {
      if (clientIdInput) clientIdInput.value = "";
      if (selectedHint) selectedHint.hidden = true;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => runClientSearch(searchInput.value), 150);
    });

    searchInput.addEventListener("keydown", (event) => {
      const results = resultsList?._results || [];
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (resultsList?.hidden) {
          runClientSearch(searchInput.value);
          return;
        }
        highlightOption(Math.min(activeIndex + 1, results.length - 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        highlightOption(Math.max(activeIndex - 1, 0));
      } else if (event.key === "Enter" && activeIndex >= 0 && results[activeIndex]) {
        event.preventDefault();
        setSelectedClient(results[activeIndex]);
      } else if (event.key === "Escape") {
        hideClientResults();
      }
    });

    searchInput.addEventListener("blur", () => {
      setTimeout(hideClientResults, 180);
    });
  }

  if (clientIdInput?.value && searchInput && !searchInput.value) {
    searchInput.placeholder = "Client selected — search again to change";
    if (selectedHint) {
      selectedHint.hidden = false;
      selectedHint.textContent =
        "Client selected. First party details should match the client.";
    }
  }

  /* Live suggestions for case fields (not parties / description) */
  function hideFieldSuggest(wrap) {
    const list = wrap.querySelector(".field-suggest__results");
    const control = wrap.querySelector("input, select");
    if (!list) return;
    list.hidden = true;
    list.innerHTML = "";
    list._results = [];
    list._active = -1;
    if (control) control.setAttribute("aria-expanded", "false");
  }

  function applySuggestion(wrap, item) {
    const field = wrap.dataset.suggestField;
    const control = wrap.querySelector("input, select");
    if (!control || !item) return;

    if (field === "client") {
      setSelectedClient({
        id: item.id || item.value,
        name: item.name || item.label,
        phone: item.phone || "",
        email: item.email || "",
        category: item.category,
        label: item.label,
        meta: item.meta,
      });
      return;
    }

    control.value = item.value;
    control.dispatchEvent(new Event("change", { bubbles: true }));
    hideFieldSuggest(wrap);
  }

  function showFieldSuggest(wrap, results, emptyMessage) {
    const list = wrap.querySelector(".field-suggest__results");
    const control = wrap.querySelector("input, select");
    if (!list || !control) return;

    list.innerHTML = "";
    if (!results.length) {
      const empty = document.createElement("li");
      empty.className = "field-suggest__empty";
      empty.textContent =
        emptyMessage || "Keep typing to register a new value";
      list.appendChild(empty);
      list.hidden = false;
      control.setAttribute("aria-expanded", "true");
      list._results = [];
      list._active = -1;
      return;
    }

    results.forEach((item, index) => {
      const li = document.createElement("li");
      li.className = "field-suggest__option";
      li.setAttribute("role", "option");
      li.dataset.index = String(index);
      li.innerHTML = `<strong>${escapeHtml(item.label || item.value)}</strong>${
        item.meta ? `<span>${escapeHtml(item.meta)}</span>` : ""
      }`;
      li.addEventListener("mousedown", (event) => {
        event.preventDefault();
        applySuggestion(wrap, item);
      });
      list.appendChild(li);
    });
    list._results = results;
    list._active = -1;
    list.hidden = false;
    control.setAttribute("aria-expanded", "true");
  }

  function highlightFieldOption(wrap, index) {
    const list = wrap.querySelector(".field-suggest__results");
    if (!list) return;
    const options = list.querySelectorAll(".field-suggest__option");
    options.forEach((el) => el.classList.remove("is-active"));
    if (index < 0 || index >= options.length) {
      list._active = -1;
      return;
    }
    list._active = index;
    options[index].classList.add("is-active");
    options[index].scrollIntoView({ block: "nearest" });
  }

  const FREE_REGISTER_FIELDS = new Set([
    "court_rank",
    "case_category",
    "case_type",
    "station",
  ]);

  function wireFieldSuggest(wrap) {
    const field = wrap.dataset.suggestField;
    if (!field || field === "client") return;
    const control = wrap.querySelector("input, select");
    if (!control) return;

    control.setAttribute("autocomplete", "off");
    control.setAttribute("aria-autocomplete", "list");

    let timer = null;
    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const q = (control.value || "").trim();
        try {
          const results = await fetchSuggestions(field, q);
          if (!results.length && !q && !FREE_REGISTER_FIELDS.has(field)) {
            hideFieldSuggest(wrap);
            return;
          }
          showFieldSuggest(
            wrap,
            results,
            FREE_REGISTER_FIELDS.has(field)
              ? "Type a new value to register it"
              : "No previous values yet"
          );
        } catch (_error) {
          hideFieldSuggest(wrap);
        }
      }, 160);
    };

    control.addEventListener("focus", schedule);
    control.addEventListener("input", schedule);
    control.addEventListener("keydown", (event) => {
      const list = wrap.querySelector(".field-suggest__results");
      const results = list?._results || [];
      const active = list?._active ?? -1;
      if (event.key === "ArrowDown") {
        if (list && !list.hidden && results.length) {
          event.preventDefault();
          highlightFieldOption(wrap, Math.min(active + 1, results.length - 1));
        }
      } else if (event.key === "ArrowUp") {
        if (list && !list.hidden && results.length) {
          event.preventDefault();
          highlightFieldOption(wrap, Math.max(active - 1, 0));
        }
      } else if (event.key === "Enter" && active >= 0 && results[active]) {
        event.preventDefault();
        applySuggestion(wrap, results[active]);
      } else if (event.key === "Escape") {
        hideFieldSuggest(wrap);
      }
    });
    control.addEventListener("blur", () => {
      setTimeout(() => hideFieldSuggest(wrap), 150);
    });
  }

  form.querySelectorAll(".field-suggest[data-suggest-field]").forEach(wireFieldSuggest);

  function renumberParties() {
    if (!partiesList) return;
    const cards = partiesList.querySelectorAll(".party-card:not([hidden])");
    cards.forEach((card, index) => {
      const title = card.querySelector(".party-card__title");
      if (!title) return;
      if (card.dataset.clientParty === "true") {
        title.textContent = "Client party";
      } else {
        title.textContent = `Party ${index + 1}`;
      }
    });
  }

  function wireRemove(card) {
    const remove = card.querySelector(".party-card__remove input[type='checkbox']");
    if (!remove) return;
    remove.addEventListener("change", () => {
      if (remove.checked) {
        card.hidden = true;
        card.querySelectorAll("input, select, textarea").forEach((el) => {
          if (el === remove) return;
          if (el.name && el.name.endsWith("-DELETE")) return;
          el.disabled = true;
        });
      } else {
        card.hidden = false;
        card.querySelectorAll("input, select, textarea").forEach((el) => {
          el.disabled = false;
        });
      }
      renumberParties();
    });
  }

  partiesList?.querySelectorAll(".party-card").forEach((card) => {
    if (card.dataset.clientParty !== "true") wireRemove(card);
  });

  addPartyBtn?.addEventListener("click", () => {
    if (!emptyTemplate || !totalFormsInput || !partiesList) return;
    const index = Number(totalFormsInput.value);
    const html = emptyTemplate.innerHTML
      .replaceAll("__prefix__", String(index))
      .replaceAll("__num__", String(index + 1));
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html.trim();
    const card = wrapper.firstElementChild;
    if (!card) return;
    partiesList.appendChild(card);
    totalFormsInput.value = String(index + 1);
    wireRemove(card);
    renumberParties();
    card.querySelector("input, select")?.focus();
  });
})();
