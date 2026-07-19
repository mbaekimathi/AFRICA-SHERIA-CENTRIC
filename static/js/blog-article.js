/**
 * Public blog article: reading progress, TOC highlight, copy link.
 */
(function () {
  const progressBar = document.getElementById("article-progress-bar");
  const articleBody = document.getElementById("article-body");
  const copyBtn = document.getElementById("article-copy-link");
  const tocLinks = Array.from(document.querySelectorAll(".article-contents a"));

  function updateProgress() {
    if (!progressBar || !articleBody) return;
    const rect = articleBody.getBoundingClientRect();
    const start = window.scrollY + rect.top - 80;
    const end = start + rect.height - window.innerHeight * 0.65;
    const raw = end <= start ? 1 : (window.scrollY - start) / (end - start);
    const pct = Math.max(0, Math.min(1, raw)) * 100;
    progressBar.style.width = pct.toFixed(2) + "%";
  }

  function updateToc() {
    if (!tocLinks.length) return;
    let currentId = "";
    tocLinks.forEach((link) => {
      const id = link.getAttribute("href")?.slice(1);
      const el = id ? document.getElementById(id) : null;
      if (!el) return;
      if (el.getBoundingClientRect().top <= 140) currentId = id;
    });
    tocLinks.forEach((link) => {
      const id = link.getAttribute("href")?.slice(1);
      link.classList.toggle("is-active", Boolean(currentId) && id === currentId);
    });
  }

  function onScroll() {
    updateProgress();
    updateToc();
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  onScroll();

  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      const url = copyBtn.getAttribute("data-url") || window.location.href;
      try {
        await navigator.clipboard.writeText(url);
        const original = copyBtn.textContent;
        copyBtn.textContent = "Copied";
        window.setTimeout(() => {
          copyBtn.textContent = original || "Copy link";
        }, 1500);
      } catch (_) {
        copyBtn.textContent = "Copy failed";
      }
    });
  }
})();
