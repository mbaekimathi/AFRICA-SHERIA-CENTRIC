/** Shared phone country-code picker (expects #country-codes-data + #phone-field). */
window.initPhoneCountryPicker = function initPhoneCountryPicker() {
  const dataEl = document.getElementById("country-codes-data");
  if (!dataEl) return;

  const countries = JSON.parse(dataEl.textContent);
  const defaultCountry = countries.find((c) => c.iso === "ke") || countries[0];
  const phoneHidden = document.getElementById("id_country_code");
  const trigger = document.getElementById("country-trigger");
  const menu = document.getElementById("country-menu");
  const list = document.getElementById("country-list");
  const search = document.getElementById("country-search");
  const flag = document.getElementById("country-flag");
  const dial = document.getElementById("country-dial");
  if (!phoneHidden || !trigger || !menu || !list || !flag || !dial) return;

  const paint = (country) => {
    phoneHidden.value = country.value;
    flag.src = country.flag;
    flag.srcset = `${country.flag2x} 2x`;
    flag.alt = `${country.name} flag`;
    dial.textContent = country.dial;
    list.querySelectorAll(".country-option").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.value === country.value);
    });
  };

  const renderOptions = (query = "") => {
    const q = query.trim().toLowerCase();
    const filtered = countries.filter(
      (c) =>
        !q ||
        c.name.toLowerCase().includes(q) ||
        c.dial.includes(q) ||
        c.iso.includes(q)
    );
    list.innerHTML = "";
    filtered.forEach((country) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "country-option";
      btn.dataset.value = country.value;
      btn.setAttribute("role", "option");
      btn.innerHTML = `
        <img class="country-flag" src="${country.flag}" srcset="${country.flag2x} 2x" width="28" height="20" alt="">
        <span class="country-option__name">${country.name}</span>
        <span class="country-option__dial">${country.dial}</span>
      `;
      btn.addEventListener("click", () => {
        paint(country);
        menu.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
      });
      li.appendChild(btn);
      list.appendChild(li);
    });
  };

  const initial =
    countries.find((c) => c.value === phoneHidden.value) || defaultCountry;
  renderOptions();
  paint(initial);

  trigger.addEventListener("click", () => {
    const open = menu.hidden;
    menu.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
    if (open) search?.focus();
  });

  search?.addEventListener("input", () => renderOptions(search.value));

  document.addEventListener("click", (event) => {
    const root = document.getElementById("phone-field");
    if (root && !root.contains(event.target)) {
      menu.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
    }
  });
};
