document.addEventListener("DOMContentLoaded", () => {
  const menus = Array.from(document.querySelectorAll("[data-metric-menu]"));
  if (!menus.length) return;

  const getParts = (menu) => {
    const trigger = menu.querySelector(".metric--interactive");
    const dropdown = menu.querySelector(".metric-dropdown");
    return { trigger, dropdown };
  };

  const setOpen = (menu, open) => {
    const { trigger, dropdown } = getParts(menu);
    if (!trigger || !dropdown) return;
    menu.classList.toggle("is-open", open);
    dropdown.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
  };

  const closeAll = (except = null) => {
    menus.forEach((menu) => {
      if (menu !== except) setOpen(menu, false);
    });
  };

  menus.forEach((menu) => {
    const { trigger, dropdown } = getParts(menu);
    if (!trigger || !dropdown) return;

    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const willOpen = dropdown.hidden;
      closeAll(menu);
      setOpen(menu, willOpen);
    });

    dropdown.addEventListener("click", (event) => {
      event.stopPropagation();
    });
  });

  document.addEventListener("click", () => closeAll());

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeAll();
  });
});
