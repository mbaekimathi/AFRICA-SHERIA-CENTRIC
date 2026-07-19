(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const hero = document.querySelector("[data-landing-hero]");
  if (!hero) return;

  const slides = Array.from(hero.querySelectorAll("[data-slide]"));
  const dots = Array.from(hero.querySelectorAll("[data-slide-to]"));
  const progress = hero.querySelector("[data-slide-progress]");
  if (!slides.length) return;

  const SLIDE_MS = 7000;
  let index = 0;
  let timer = null;
  let typingTimer = null;
  let typingActive = true;

  function parsePhrases(el) {
    const raw = el?.getAttribute("data-type-phrases");
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function clearTyping() {
    if (typingTimer) {
      clearTimeout(typingTimer);
      typingTimer = null;
    }
  }

  function restartProgress() {
    if (!progress || reduceMotion) return;
    progress.classList.remove("is-running");
    progress.style.animationDuration = "";
    // Force reflow so the animation restarts cleanly
    void progress.offsetWidth;
    progress.style.animationDuration = `${SLIDE_MS}ms`;
    progress.classList.add("is-running");
  }

  function runTypewriter(slide) {
    clearTyping();
    const typeEl = slide.querySelector("[data-type-phrases]");
    const textEl = slide.querySelector("[data-type-text]");
    if (!typeEl || !textEl) return;

    const phrases = parsePhrases(typeEl);
    if (!phrases.length) {
      textEl.textContent = "";
      return;
    }

    if (reduceMotion) {
      textEl.textContent = phrases[0];
      return;
    }

    let phraseIndex = 0;
    let charIndex = 0;
    let deleting = false;

    const tick = () => {
      if (!typingActive || !slide.classList.contains("is-active")) return;

      const current = phrases[phraseIndex];
      if (!deleting) {
        charIndex += 1;
        textEl.textContent = current.slice(0, charIndex);
        if (charIndex >= current.length) {
          deleting = true;
          typingTimer = setTimeout(tick, 1800);
          return;
        }
        typingTimer = setTimeout(tick, 52);
      } else {
        charIndex -= 1;
        textEl.textContent = current.slice(0, charIndex);
        if (charIndex <= 0) {
          deleting = false;
          phraseIndex = (phraseIndex + 1) % phrases.length;
          typingTimer = setTimeout(tick, 280);
          return;
        }
        typingTimer = setTimeout(tick, 28);
      }
    };

    textEl.textContent = "";
    typingTimer = setTimeout(tick, 180);
  }

  function setActive(next) {
    if (next === index && slides[index].classList.contains("is-active")) {
      restartProgress();
      return;
    }

    const prev = index;
    index = (next + slides.length) % slides.length;

    slides.forEach((slide, i) => {
      const active = i === index;
      slide.classList.toggle("is-active", active);
      slide.classList.toggle("is-leaving", i === prev && !active);
      slide.setAttribute("aria-hidden", active ? "false" : "true");
    });

    dots.forEach((dot, i) => {
      const active = i === index;
      dot.classList.toggle("is-active", active);
      dot.setAttribute("aria-selected", active ? "true" : "false");
    });

    runTypewriter(slides[index]);
    restartProgress();
  }

  function nextSlide() {
    setActive(index + 1);
  }

  function startAutoplay() {
    if (reduceMotion || slides.length < 2) return;
    stopAutoplay();
    restartProgress();
    timer = setInterval(nextSlide, SLIDE_MS);
  }

  function stopAutoplay() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    if (progress) {
      progress.classList.remove("is-running");
    }
  }

  dots.forEach((dot) => {
    dot.addEventListener("click", () => {
      const to = Number(dot.getAttribute("data-slide-to"));
      if (Number.isNaN(to)) return;
      setActive(to);
      startAutoplay();
    });
  });

  hero.addEventListener("mouseenter", stopAutoplay);
  hero.addEventListener("mouseleave", startAutoplay);
  hero.addEventListener("focusin", stopAutoplay);
  hero.addEventListener("focusout", (event) => {
    if (!hero.contains(event.relatedTarget)) startAutoplay();
  });

  document.addEventListener("visibilitychange", () => {
    typingActive = document.visibilityState === "visible";
    if (typingActive) {
      runTypewriter(slides[index]);
      startAutoplay();
    } else {
      clearTyping();
      stopAutoplay();
    }
  });

  slides.forEach((slide, i) => {
    const active = i === 0;
    slide.classList.toggle("is-active", active);
    slide.setAttribute("aria-hidden", active ? "false" : "true");
  });
  runTypewriter(slides[0]);
  startAutoplay();
})();

(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const nodes = document.querySelectorAll(".landing [data-reveal]");
  if (!nodes.length) return;
  if (reduceMotion) {
    nodes.forEach((node) => node.classList.add("is-visible"));
    return;
  }
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.15, rootMargin: "0px 0px -8% 0px" }
  );
  nodes.forEach((node) => observer.observe(node));
})();
