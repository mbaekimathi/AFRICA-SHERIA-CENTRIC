(() => {
  const header = document.querySelector("[data-fw-header]");
  if (header) {
    const toggle = header.querySelector("[data-fw-nav-toggle]");
    const panel = header.querySelector("[data-fw-nav]");

    const setOpen = (open) => {
      header.classList.toggle("is-open", open);
      if (toggle) {
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      }
    };

    if (toggle && panel) {
      toggle.addEventListener("click", () => {
        setOpen(!header.classList.contains("is-open"));
      });
      panel.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => setOpen(false));
      });
    }

    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setOpen(false);
    });

    const onScroll = () => {
      header.classList.toggle("is-scrolled", window.scrollY > 12);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const reveals = document.querySelectorAll(".fw-reveal");
  if (!reveals.length) return;

  if (reduceMotion || !("IntersectionObserver" in window)) {
    reveals.forEach((el) => el.classList.add("is-in"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-in");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
  );

  reveals.forEach((el) => observer.observe(el));
})();
