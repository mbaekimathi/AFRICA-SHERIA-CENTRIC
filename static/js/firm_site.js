(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  /* ——— Header / nav ——— */
  const header = document.querySelector("[data-fw-header]");
  if (header) {
    const toggle = header.querySelector("[data-fw-nav-toggle]");
    const panel = header.querySelector("[data-fw-nav]");
    const page = document.querySelector(".site-page--firm");
    const mqDesktop = window.matchMedia("(min-width: 1101px)");

    const setOpen = (open) => {
      header.classList.toggle("is-open", open);
      if (page) page.classList.toggle("is-nav-locked", open);
      if (toggle) {
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      }
    };

    if (toggle && panel) {
      toggle.addEventListener("click", () => {
        setOpen(!header.classList.contains("is-open"));
      });
      header.querySelectorAll(".fw-nav a, .fw-header__actions a").forEach((link) => {
        link.addEventListener("click", () => setOpen(false));
      });
    }

    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setOpen(false);
    });

    const onBreakpoint = () => {
      if (mqDesktop.matches) setOpen(false);
    };
    if (typeof mqDesktop.addEventListener === "function") {
      mqDesktop.addEventListener("change", onBreakpoint);
    } else if (typeof mqDesktop.addListener === "function") {
      mqDesktop.addListener(onBreakpoint);
    }

  }

  /* ——— Hero entrance ——— */
  const hero = document.querySelector("[data-fw-hero]");
  if (hero) {
    requestAnimationFrame(() => hero.classList.add("is-ready"));
  }

  /* ——— Smooth in-page anchors (header-aware) ——— */
  const headerOffset = () => {
    if (!header) return 16;
    return Math.ceil(header.getBoundingClientRect().height) + 12;
  };

  const easeInOutCubic = (t) =>
    t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

  const scrollToY = (targetY, { duration = 900 } = {}) => {
    const startY = window.scrollY || window.pageYOffset;
    const delta = targetY - startY;
    if (Math.abs(delta) < 2) return;
    if (reduceMotion) {
      window.scrollTo(0, targetY);
      return;
    }
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      window.scrollTo(0, startY + delta * easeInOutCubic(t));
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  const scrollToEl = (el) => {
    if (!el) return;
    const y = window.scrollY + el.getBoundingClientRect().top - headerOffset();
    scrollToY(Math.max(0, y));
  };

  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    const id = link.getAttribute("href");
    if (!id || id === "#" || id.length < 2) return;
    let target = null;
    try {
      target = document.querySelector(id);
    } catch (_) {
      return;
    }
    if (!target) return;
    link.addEventListener("click", (e) => {
      e.preventDefault();
      scrollToEl(target);
      if (history.pushState) {
        history.pushState(null, "", id);
      } else {
        location.hash = id;
      }
    });
  });

  if (location.hash.length > 1) {
    const bootTarget = document.querySelector(location.hash);
    if (bootTarget) {
      requestAnimationFrame(() => scrollToEl(bootTarget));
    }
  }

  /* ——— Background reveal as sections enter view ——— */
  const bgLayers = [
    ...document.querySelectorAll("[data-fw-bg]"),
    ...document.querySelectorAll(".fw-pagehead--photo"),
  ];
  if (bgLayers.length) {
    if (reduceMotion || !("IntersectionObserver" in window)) {
      bgLayers.forEach((el) => {
        el.classList.add("is-visible");
        el.classList.add("is-bg-in");
      });
    } else {
      const bgObserver = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add("is-visible");
            entry.target.classList.add("is-bg-in");
            bgObserver.unobserve(entry.target);
          });
        },
        { threshold: 0.08, rootMargin: "0px 0px -4% 0px" }
      );
      bgLayers.forEach((el) => bgObserver.observe(el));
    }
  }

  /* ——— Scroll-triggered reveals ——— */
  const animSelector = [
    ".fw-reveal",
    "[data-fw-anim]",
    ".fw-rail-card",
    ".fw-section__head",
    ".fw-practice-tile",
    ".fw-team-cine",
    ".fw-team-deck",
    ".fw-team-profile",
    ".fw-insight",
    ".fw-voice",
    ".fw-about-value",
    ".fw-contact-hero__item",
    ".fw-contact-item",
    ".fw-faq",
    ".fw-glimpse__item",
    ".fw-gallery-card",
    ".fw-strip__item",
    ".fw-story__copy",
    ".fw-story__visual",
    ".fw-about-split__copy",
    ".fw-about-split__media",
    ".fw-map",
    ".fw-detail__media",
    ".fw-cta > .fw-wrap",
    ".fw-insight-feature",
    ".fw-insight-rail__card",
    ".fw-faq-hub__side",
    ".fw-faq-hub__main",
    ".fw-faq-cta__inner",
    ".fw-gallery-spotlight",
    ".fw-gallery-tile",
    ".fw-gallery-cta__inner",
    ".fw-gallery-lounge__head",
  ].join(", ");

  const animTargets = document.querySelectorAll(animSelector);

  if (animTargets.length) {
    if (reduceMotion || !("IntersectionObserver" in window)) {
      animTargets.forEach((el) => el.classList.add("is-in"));
    } else {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            const delay = Number(
              entry.target.style.getPropertyValue("--i") ||
                entry.target.dataset.i ||
                0
            );
            entry.target.style.transitionDelay = `${Math.min(delay, 10) * 70}ms`;
            entry.target.classList.add("is-in");
            observer.unobserve(entry.target);
          });
        },
        { threshold: 0.12, rootMargin: "0px 0px -10% 0px" }
      );
      animTargets.forEach((el) => {
        if (!el.style.getPropertyValue("--i") && !el.dataset.i) {
          const siblings = el.parentElement
            ? [...el.parentElement.children].filter((n) =>
                n.matches(
                  ".fw-reveal, [data-fw-anim], .fw-practice-tile, .fw-team-cine, .fw-insight, .fw-voice, .fw-about-value, .fw-contact-hero__item, .fw-faq, .fw-glimpse__item, .fw-gallery-card"
                )
              )
            : [];
          const i = Math.max(0, siblings.indexOf(el));
          if (i > 0) el.style.setProperty("--i", String(Math.min(i, 10)));
        }
        if (
          !el.classList.contains("fw-reveal") &&
          !el.hasAttribute("data-fw-anim") &&
          !el.classList.contains("fw-team-deck")
        ) {
          el.setAttribute("data-fw-anim", el.dataset.fwAnim || "rise");
        }
        observer.observe(el);
      });
    }
  }

  /* ——— Unified scroll engine: progress, parallax, header, back-top ——— */
  const progress = document.createElement("div");
  progress.className = "fw-scroll-progress";
  progress.setAttribute("aria-hidden", "true");
  document.body.appendChild(progress);

  const backTop = document.createElement("button");
  backTop.type = "button";
  backTop.className = "fw-back-top";
  backTop.setAttribute("aria-label", "Back to top");
  backTop.innerHTML = "<span aria-hidden=\"true\">↑</span>";
  document.body.appendChild(backTop);
  backTop.addEventListener("click", () => scrollToY(0, { duration: 1000 }));

  const parallaxNodes = [
    ...new Set([
      ...document.querySelectorAll("[data-fw-parallax]"),
      ...document.querySelectorAll(
        ".fw-hero__plane, .fw-about-hero__plane, .fw-pagehead__photo, .fw-rail__img"
      ),
    ]),
  ];

  const scrollSections = [...document.querySelectorAll("[data-fw-scroll-section]")];

  let scrollY = window.scrollY || 0;
  let lastScrollY = scrollY;
  let progressTarget = 0;
  let progressCurrent = 0;
  let headerHidden = false;
  let engineRunning = false;
  let scrollIdleTimer = 0;

  const applyParallax = () => {
    if (reduceMotion || !parallaxNodes.length) return;
    const vh = window.innerHeight || 1;
    parallaxNodes.forEach((node) => {
      const host =
        node.closest(
          "section, .fw-hero, .fw-about-hero, .fw-pagehead, .fw-cta, .fw-strip, .fw-rail"
        ) || node;
      const rect = host.getBoundingClientRect();
      if (rect.bottom < -160 || rect.top > vh + 160) return;
      const p = (vh / 2 - (rect.top + rect.height / 2)) / vh;
      const speed = Number(node.dataset.speed || 0.16);
      const y = p * speed * 110;
      const baseScale = node.classList.contains("fw-pagehead__photo")
        ? 1.05
        : node.classList.contains("fw-rail__img")
          ? 1.08
          : node.classList.contains("fw-bg__plane")
            ? 1.06
            : 1.05;
      node.style.transform = `translate3d(0, ${y.toFixed(2)}px, 0) scale(${baseScale})`;
    });
  };

  const applySectionFocus = () => {
    if (!scrollSections.length) return;
    const focusLine = (window.innerHeight || 1) * 0.38;
    let best = null;
    let bestDist = Infinity;
    scrollSections.forEach((section) => {
      const rect = section.getBoundingClientRect();
      const mid = rect.top + rect.height * 0.35;
      const dist = Math.abs(mid - focusLine);
      const visible = rect.bottom > 80 && rect.top < window.innerHeight - 40;
      section.classList.toggle("is-section-in", visible);
      if (visible && dist < bestDist) {
        bestDist = dist;
        best = section;
      }
    });
    scrollSections.forEach((section) => {
      section.classList.toggle("is-section-focus", section === best);
    });
  };

  const applyHeader = () => {
    if (!header) return;
    const y = scrollY;
    header.classList.toggle("is-scrolled", y > 16);
    const goingDown = y > lastScrollY + 4;
    const goingUp = y < lastScrollY - 4;
    const navOpen = header.classList.contains("is-open");
    if (!reduceMotion && !navOpen) {
      if (goingDown && y > 140) headerHidden = true;
      if (goingUp || y < 80) headerHidden = false;
    } else {
      headerHidden = false;
    }
    header.classList.toggle("is-hide-away", headerHidden);
    lastScrollY = y;
  };

  const tickEngine = () => {
    scrollY = window.scrollY || 0;
    const doc = document.documentElement;
    const max = doc.scrollHeight - doc.clientHeight;
    progressTarget = max > 0 ? scrollY / max : 0;
    progressCurrent += (progressTarget - progressCurrent) * (reduceMotion ? 1 : 0.16);
    progress.style.transform = `scaleX(${Math.max(0, Math.min(1, progressCurrent)).toFixed(4)})`;
    applyParallax();
    applySectionFocus();
    applyHeader();
    backTop.classList.toggle("is-visible", scrollY > window.innerHeight * 0.85);
    if (engineRunning) requestAnimationFrame(tickEngine);
  };

  const requestEngine = () => {
    if (!engineRunning) {
      engineRunning = true;
      requestAnimationFrame(tickEngine);
    }
    window.clearTimeout(scrollIdleTimer);
    scrollIdleTimer = window.setTimeout(() => {
      engineRunning = false;
    }, 180);
  };

  requestEngine();
  window.addEventListener("scroll", requestEngine, { passive: true });
  window.addEventListener("resize", requestEngine, { passive: true });

  /* ——— Magnetic buttons ——— */
  if (!reduceMotion && finePointer) {
    document.querySelectorAll("[data-fw-magnetic]").forEach((btn) => {
      btn.addEventListener("pointermove", (e) => {
        const rect = btn.getBoundingClientRect();
        const x = e.clientX - rect.left - rect.width / 2;
        const y = e.clientY - rect.top - rect.height / 2;
        btn.style.transform = `translate(${x * 0.18}px, ${y * 0.22}px)`;
      });
      btn.addEventListener("pointerleave", () => {
        btn.style.transform = "";
      });
    });
  }

  /* ——— Tilt cards ——— */
  if (!reduceMotion && finePointer) {
    document.querySelectorAll("[data-fw-tilt]").forEach((card) => {
      card.addEventListener("pointermove", (e) => {
        const rect = card.getBoundingClientRect();
        const px = (e.clientX - rect.left) / rect.width;
        const py = (e.clientY - rect.top) / rect.height;
        const rx = (0.5 - py) * 8;
        const ry = (px - 0.5) * 10;
        card.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-2px)`;
      });
      card.addEventListener("pointerleave", () => {
        card.style.transform = "";
      });
    });
  }

  /* ——— Lightbox ——— */
  const lightboxLinks = [...document.querySelectorAll("[data-fw-lightbox]")];
  if (lightboxLinks.length) {
    const overlay = document.createElement("div");
    overlay.className = "fw-lightbox";
    overlay.hidden = true;
    overlay.innerHTML = `
      <button type="button" class="fw-lightbox__close" aria-label="Close">&times;</button>
      <button type="button" class="fw-lightbox__nav fw-lightbox__prev" aria-label="Previous">‹</button>
      <figure class="fw-lightbox__figure">
        <img class="fw-lightbox__img" alt="">
        <figcaption class="fw-lightbox__cap"></figcaption>
      </figure>
      <button type="button" class="fw-lightbox__nav fw-lightbox__next" aria-label="Next">›</button>
    `;
    document.body.appendChild(overlay);

    const img = overlay.querySelector(".fw-lightbox__img");
    const cap = overlay.querySelector(".fw-lightbox__cap");
    let index = 0;

    const show = (i) => {
      index = (i + lightboxLinks.length) % lightboxLinks.length;
      const link = lightboxLinks[index];
      img.src = link.getAttribute("href");
      img.alt = link.dataset.caption || "";
      cap.textContent = link.dataset.caption || "";
      overlay.hidden = false;
      document.body.classList.add("is-lightbox-open");
    };

    const hide = () => {
      overlay.hidden = true;
      document.body.classList.remove("is-lightbox-open");
      img.removeAttribute("src");
    };

    lightboxLinks.forEach((link, i) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        show(i);
      });
    });

    overlay.querySelector(".fw-lightbox__close").addEventListener("click", hide);
    overlay.querySelector(".fw-lightbox__prev").addEventListener("click", () => show(index - 1));
    overlay.querySelector(".fw-lightbox__next").addEventListener("click", () => show(index + 1));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) hide();
    });
    window.addEventListener("keydown", (e) => {
      if (overlay.hidden) return;
      if (e.key === "Escape") hide();
      if (e.key === "ArrowLeft") show(index - 1);
      if (e.key === "ArrowRight") show(index + 1);
    });
  }

  /* ——— Practice book flips ——— */
  const practiceSlides = document.querySelector("[data-fw-practice-slides]");
  if (practiceSlides) {
    const slides = [...practiceSlides.querySelectorAll("[data-fw-slide]")];
    const dots = [...practiceSlides.querySelectorAll("[data-fw-slide-dot]")];
    const prevBtn = practiceSlides.querySelector("[data-fw-slide-prev]");
    const nextBtn = practiceSlides.querySelector("[data-fw-slide-next]");
    const progress = practiceSlides.querySelector(".fw-practice-slides__progress span");
    let index = 0;
    let timer = 0;
    let flipping = false;
    const delay = 5600;
    const flipMs = reduceMotion ? 0 : 920;

    const bumpProgress = () => {
      if (!progress) return;
      progress.style.animation = "none";
      void progress.offsetWidth;
      progress.style.animation = "";
    };

    const syncDots = () => {
      dots.forEach((dot, i) => {
        const on = i === index;
        dot.classList.toggle("is-active", on);
        dot.setAttribute("aria-selected", on ? "true" : "false");
      });
    };

    const hardShow = (next) => {
      index = ((next % slides.length) + slides.length) % slides.length;
      slides.forEach((slide, i) => {
        slide.classList.remove(
          "is-active",
          "is-under",
          "is-flip-next",
          "is-flip-prev",
          "is-flip-in-next",
          "is-flip-in-prev"
        );
        const on = i === index;
        slide.classList.toggle("is-active", on);
        slide.setAttribute("aria-hidden", on ? "false" : "true");
      });
      syncDots();
      bumpProgress();
    };

    const show = (next, dir = 1) => {
      if (!slides.length || flipping) return;
      const target = ((next % slides.length) + slides.length) % slides.length;
      if (target === index) return;

      if (reduceMotion || flipMs === 0) {
        hardShow(target);
        return;
      }

      const outgoing = slides[index];
      const incoming = slides[target];
      flipping = true;
      practiceSlides.classList.add("is-flipping");
      practiceSlides.classList.toggle("is-flip-forward", dir > 0);
      practiceSlides.classList.toggle("is-flip-backward", dir < 0);

      incoming.classList.add("is-under", "is-active");
      incoming.setAttribute("aria-hidden", "false");
      outgoing.classList.add(dir > 0 ? "is-flip-next" : "is-flip-prev");
      incoming.classList.add(dir > 0 ? "is-flip-in-next" : "is-flip-in-prev");

      index = target;
      syncDots();
      bumpProgress();

      window.setTimeout(() => {
        slides.forEach((slide, i) => {
          slide.classList.remove(
            "is-under",
            "is-flip-next",
            "is-flip-prev",
            "is-flip-in-next",
            "is-flip-in-prev"
          );
          const on = i === index;
          slide.classList.toggle("is-active", on);
          slide.setAttribute("aria-hidden", on ? "false" : "true");
        });
        practiceSlides.classList.remove(
          "is-flipping",
          "is-flip-forward",
          "is-flip-backward"
        );
        flipping = false;
      }, flipMs);
    };

    const stop = () => {
      if (timer) {
        window.clearInterval(timer);
        timer = 0;
      }
      practiceSlides.classList.remove("is-playing");
    };

    const start = () => {
      stop();
      if (reduceMotion || slides.length < 2) return;
      practiceSlides.classList.add("is-playing");
      bumpProgress();
      timer = window.setInterval(() => show(index + 1, 1), delay);
    };

    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        show(index - 1, -1);
        start();
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        show(index + 1, 1);
        start();
      });
    }
    dots.forEach((dot) => {
      dot.addEventListener("click", () => {
        const next = Number(dot.getAttribute("data-fw-slide-dot") || 0);
        show(next, next >= index ? 1 : -1);
        start();
      });
    });

    practiceSlides.addEventListener("mouseenter", stop);
    practiceSlides.addEventListener("mouseleave", start);
    practiceSlides.addEventListener("focusin", stop);
    practiceSlides.addEventListener("focusout", start);

    hardShow(0);
    start();
  }

  /* ——— Practice story: sticky image follows active step ——— */
  const practiceStory = document.querySelector("[data-fw-practice-story]");
  if (practiceStory) {
    const steps = [...practiceStory.querySelectorAll("[data-fw-practice-step]")];
    const frames = [...practiceStory.querySelectorAll("[data-fw-practice-frame]")];
    const setActive = (index) => {
      steps.forEach((step, i) => step.classList.toggle("is-active", i === index));
      frames.forEach((frame, i) => frame.classList.toggle("is-active", i === index));
    };
    if (reduceMotion || !("IntersectionObserver" in window)) {
      setActive(0);
    } else {
      const storyObserver = new IntersectionObserver(
        (entries) => {
          const visible = entries
            .filter((entry) => entry.isIntersecting)
            .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
          if (!visible) return;
          const index = Number(visible.target.getAttribute("data-fw-practice-step") || 0);
          setActive(index);
        },
        { threshold: [0.35, 0.55, 0.7], rootMargin: "-20% 0px -25% 0px" }
      );
      steps.forEach((step) => storyObserver.observe(step));
      setActive(0);
    }
  }

  /* ——— Team coverflow slideshow ——— */
  document.querySelectorAll("[data-fw-team-slides]").forEach((root) => {
    const slides = [...root.querySelectorAll("[data-fw-team-slide]")];
    const dots = [...root.querySelectorAll("[data-fw-team-dot]")];
    const prevBtn = root.querySelector("[data-fw-team-prev]");
    const nextBtn = root.querySelector("[data-fw-team-next]");
    const toggleBtn = root.querySelector("[data-fw-team-toggle]");
    const progress = root.querySelector(".fw-team-deck__progress span");
    const who = root.querySelector("[data-fw-team-who]");
    const count = root.querySelector("[data-fw-team-count]");
    if (!slides.length) return;

    let index = 0;
    let timer = 0;
    let manualPause = false;
    const delay = 5000;
    const total = slides.length;
    const pad = (n) => String(n).padStart(2, "0");

    const bumpProgress = () => {
      if (!progress) return;
      progress.style.animation = "none";
      void progress.offsetWidth;
      progress.style.animation = "";
    };

    const show = (next) => {
      index = ((next % total) + total) % total;
      const prevIndex = (index - 1 + total) % total;
      const nextIndex = (index + 1) % total;
      const prev2Index = (index - 2 + total) % total;
      const next2Index = (index + 2) % total;

      slides.forEach((slide, i) => {
        const roles = {
          active: i === index,
          prev: total > 1 && i === prevIndex,
          next: total > 2 && i === nextIndex,
          prev2: total > 4 && i === prev2Index,
          next2: total > 4 && i === next2Index,
        };
        // Avoid double-assigning the same card to two peeks
        if (roles.prev && roles.prev2) roles.prev2 = false;
        if (roles.next && roles.next2) roles.next2 = false;
        if (roles.prev && roles.next) roles.next = false;

        slide.classList.toggle("is-active", roles.active);
        slide.classList.toggle("is-prev", roles.prev);
        slide.classList.toggle("is-next", roles.next);
        slide.classList.toggle("is-prev2", roles.prev2);
        slide.classList.toggle("is-next2", roles.next2);
        slide.setAttribute("aria-hidden", roles.active ? "false" : "true");
      });

      dots.forEach((dot, i) => {
        const on = i === index;
        dot.classList.toggle("is-active", on);
        dot.setAttribute("aria-selected", on ? "true" : "false");
      });

      const active = slides[index];
      if (who) who.textContent = active?.dataset.fwTeamName || "";
      if (count) count.textContent = `${pad(index + 1)} / ${pad(total)}`;

      const img = active?.querySelector(".fw-team-deck__media img");
      if (img) {
        img.style.animation = "none";
        void img.offsetWidth;
        img.style.animation = "";
      }

      bumpProgress();
    };

    const stop = ({ manual = false } = {}) => {
      if (timer) {
        window.clearInterval(timer);
        timer = 0;
      }
      if (manual) manualPause = true;
      root.classList.remove("is-playing");
      if (toggleBtn) {
        toggleBtn.setAttribute("aria-pressed", "true");
        toggleBtn.setAttribute("aria-label", "Play slideshow");
        toggleBtn.textContent = "▶";
      }
    };

    const start = () => {
      stop();
      manualPause = false;
      if (reduceMotion || total < 2) {
        show(index);
        return;
      }
      root.classList.add("is-playing");
      if (toggleBtn) {
        toggleBtn.setAttribute("aria-pressed", "false");
        toggleBtn.setAttribute("aria-label", "Pause slideshow");
        toggleBtn.textContent = "❚❚";
      }
      bumpProgress();
      timer = window.setInterval(() => show(index + 1), delay);
    };

    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        show(index - 1);
        start();
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        show(index + 1);
        start();
      });
    }
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        if (root.classList.contains("is-playing")) stop({ manual: true });
        else start();
      });
    }
    dots.forEach((dot) => {
      dot.addEventListener("click", () => {
        show(Number(dot.getAttribute("data-fw-team-dot") || 0));
        start();
      });
    });

    // Pause while interacting with the stage; keep chrome usable
    const stage = root.querySelector(".fw-team-deck__stage");
    if (stage) {
      stage.addEventListener("mouseenter", stop);
      stage.addEventListener("mouseleave", () => {
        if (!manualPause) start();
      });
    }
    root.addEventListener("focusin", stop);
    root.addEventListener("focusout", (e) => {
      if (!root.contains(e.relatedTarget) && !manualPause) start();
    });

    slides.forEach((slide, i) => {
      slide.addEventListener("click", () => {
        if (
          slide.classList.contains("is-prev") ||
          slide.classList.contains("is-next") ||
          slide.classList.contains("is-prev2") ||
          slide.classList.contains("is-next2")
        ) {
          show(i);
          start();
        }
      });
    });

    show(0);
    start();
  });

  /* ——— Gallery hub: activity filters ——— */
  const galleryHub = document.querySelector("[data-fw-gallery-hub]");
  if (galleryHub) {
    const matchEl = galleryHub.querySelector("[data-fw-gallery-match]");
    const emptyEl = galleryHub.querySelector("[data-fw-gallery-empty]");
    const resetBtn = galleryHub.querySelector("[data-fw-gallery-reset]");
    const items = [...galleryHub.querySelectorAll("[data-fw-gallery-item]")];
    const topicBtns = [
      ...galleryHub.querySelectorAll(
        ".fw-gallery-lounge__topic[data-fw-gallery-topic]"
      ),
    ];
    let activeTopic = "all";

    const setTopicActive = (slug) => {
      topicBtns.forEach((btn) => {
        const on = btn.dataset.fwGalleryTopic === slug;
        btn.classList.toggle("is-active", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      });
    };

    const applyFilters = () => {
      let visible = 0;
      items.forEach((el) => {
        const topic = el.dataset.fwGalleryTopic || "";
        const show = activeTopic === "all" || topic === activeTopic;
        el.classList.toggle("is-filtered-out", !show);
        if (show) visible += 1;
      });
      if (matchEl) {
        const total = items.length;
        if (activeTopic !== "all") {
          matchEl.textContent = `Showing ${visible} of ${total} moments`;
        } else {
          matchEl.textContent = total ? `Showing all ${total} moments` : "";
        }
      }
      if (emptyEl) emptyEl.hidden = visible > 0;
    };

    topicBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTopic = btn.dataset.fwGalleryTopic || "all";
        setTopicActive(activeTopic);
        applyFilters();
      });
    });

    resetBtn?.addEventListener("click", () => {
      activeTopic = "all";
      setTopicActive("all");
      applyFilters();
    });

    setTopicActive("all");
    applyFilters();
  }

  /* ——— FAQ hub: search, topics, expand ——— */
  const faqHub = document.querySelector("[data-fw-faq-hub]");
  if (faqHub) {
    const searchInput = faqHub.querySelector("[data-fw-faq-search]");
    const matchEl = faqHub.querySelector("[data-fw-faq-match]");
    const emptyEl = faqHub.querySelector("[data-fw-faq-empty]");
    const resetBtn = faqHub.querySelector("[data-fw-faq-reset]");
    const items = [...faqHub.querySelectorAll("[data-fw-faq-item]")];
    const topicBtns = [
      ...faqHub.querySelectorAll(".fw-faq-hub__topic[data-fw-faq-topic]"),
    ];
    const expandAll = faqHub.querySelector("[data-fw-faq-expand-all]");
    const collapseAll = faqHub.querySelector("[data-fw-faq-collapse-all]");
    let activeTopic = "all";
    let searchQuery = "";

    const setTopicActive = (slug) => {
      topicBtns.forEach((btn) => {
        const on = btn.dataset.fwFaqTopic === slug;
        btn.classList.toggle("is-active", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      });
    };

    const itemMatches = (el) => {
      const topic = el.dataset.fwFaqTopic || "";
      const blob = (el.dataset.fwSearch || "").toLowerCase();
      const topicOk = activeTopic === "all" || topic === activeTopic;
      const q = searchQuery.trim().toLowerCase();
      const searchOk = !q || blob.includes(q);
      return topicOk && searchOk;
    };

    const applyFilters = () => {
      let visible = 0;
      items.forEach((el) => {
        const show = itemMatches(el);
        el.classList.toggle("is-filtered-out", !show);
        if (show) visible += 1;
      });
      if (matchEl) {
        const total = items.length;
        if (searchQuery.trim() || activeTopic !== "all") {
          matchEl.textContent = `Showing ${visible} of ${total} questions`;
        } else {
          matchEl.textContent = total ? `Showing all ${total} questions` : "";
        }
      }
      if (emptyEl) {
        emptyEl.hidden = visible > 0;
      }
    };

    topicBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTopic = btn.dataset.fwFaqTopic || "all";
        setTopicActive(activeTopic);
        applyFilters();
      });
    });

    if (searchInput) {
      let searchTimer = 0;
      searchInput.addEventListener("input", () => {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => {
          searchQuery = searchInput.value || "";
          applyFilters();
        }, 120);
      });
    }

    const resetFilters = () => {
      activeTopic = "all";
      searchQuery = "";
      if (searchInput) searchInput.value = "";
      setTopicActive("all");
      applyFilters();
    };

    resetBtn?.addEventListener("click", resetFilters);

    let faqAccordionLock = false;

    expandAll?.addEventListener("click", () => {
      faqAccordionLock = true;
      items.forEach((el) => {
        if (!el.classList.contains("is-filtered-out")) el.open = true;
      });
      requestAnimationFrame(() => {
        faqAccordionLock = false;
      });
    });

    collapseAll?.addEventListener("click", () => {
      faqAccordionLock = true;
      items.forEach((el) => {
        el.open = false;
      });
      requestAnimationFrame(() => {
        faqAccordionLock = false;
      });
    });

    faqHub.querySelectorAll(".fw-faq__permalink").forEach((link) => {
      link.addEventListener("click", async (e) => {
        e.preventDefault();
        const href = link.getAttribute("href") || "";
        const url = new URL(href, window.location.href);
        try {
          await navigator.clipboard.writeText(url.href);
          const prev = link.textContent;
          link.textContent = "Link copied";
          window.setTimeout(() => {
            link.textContent = prev;
          }, 1600);
        } catch (_) {
          location.hash = url.hash;
        }
        if (history.pushState) {
          history.pushState(null, "", url.hash);
        }
      });
    });

    items.forEach((el) => {
      el.addEventListener("toggle", () => {
        if (!el.open || reduceMotion || faqAccordionLock) return;
        items.forEach((other) => {
          if (other !== el && other.open) other.open = false;
        });
      });
    });

    const openFromHash = () => {
      const id = (location.hash || "").slice(1);
      if (!id) return;
      const target = document.getElementById(id);
      if (!target || !target.matches("[data-fw-faq-item]")) return;
      target.classList.remove("is-filtered-out");
      target.open = true;
      target.classList.add("is-highlight");
      window.setTimeout(() => target.classList.remove("is-highlight"), 2200);
      requestAnimationFrame(() => scrollToEl(target));
    };

    openFromHash();
    window.addEventListener("hashchange", openFromHash);

    setTopicActive("all");
    applyFilters();
  }

  /* ——— Icon hover pulse ——— */
  document.querySelectorAll(".fw-strip__ico, .fw-practice-tile__ico, .fw-contact-hero__ico, .fw-rail-strip__ico, .fw-rail-card__bullet, .fw-practice-reel__ico, .fw-practice-marquee__ico, .fw-practice-slides__ico").forEach((el) => {
    el.addEventListener("mouseenter", () => el.classList.add("is-spin"));
    el.addEventListener("animationend", () => el.classList.remove("is-spin"));
  });

  /* ——— Cursor glow (desktop only) ——— */
  if (!reduceMotion && finePointer) {
    const glow = document.createElement("div");
    glow.className = "fw-cursor-glow";
    glow.setAttribute("aria-hidden", "true");
    document.body.appendChild(glow);
    let raf = 0;
    let tx = 0;
    let ty = 0;
    window.addEventListener(
      "pointermove",
      (e) => {
        tx = e.clientX;
        ty = e.clientY;
        if (!raf) {
          raf = requestAnimationFrame(() => {
            glow.style.transform = `translate(${tx - 120}px, ${ty - 120}px)`;
            raf = 0;
          });
        }
      },
      { passive: true }
    );
  }
})();
