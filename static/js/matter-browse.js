document.addEventListener("DOMContentLoaded", () => {
  const page = document.querySelector(".page--matter-browse");
  if (!page) return;

  const searchInput = document.getElementById("matter-browse-search");
  const cardsRoot = document.getElementById("matter-browse-cards");
  const filteredEmpty = document.getElementById("matter-browse-filtered-empty");
  const groupCount = document.getElementById("matter-browse-group-count");
  const refreshBtn = document.getElementById("matter-browse-refresh");

  const cards = cardsRoot
    ? Array.from(cardsRoot.querySelectorAll(".matter-card"))
    : [];

  function applyFilter() {
    if (!cardsRoot) return;
    const query = (searchInput?.value || "").trim().toLowerCase();
    let visible = 0;

    cards.forEach((card) => {
      const haystack = card.dataset.search || "";
      const show = !query || haystack.includes(query);
      card.hidden = !show;
      if (show) visible += 1;
    });

    if (groupCount) groupCount.textContent = String(visible);
    if (filteredEmpty) filteredEmpty.hidden = visible !== 0;
    cardsRoot.hidden = visible === 0;
  }

  searchInput?.addEventListener("input", applyFilter);

  refreshBtn?.addEventListener("click", () => {
    refreshBtn.classList.add("is-spinning");
    window.setTimeout(() => {
      window.location.reload();
    }, 280);
  });

  cards.forEach((card) => {
    card.addEventListener("toggle", () => {
      if (!card.open) return;
      const body = card.querySelector(".matter-card__body--table");
      if (!body) return;
      body.style.animation = "none";
      // Force reflow so reopen replays the entrance motion.
      void body.offsetWidth;
      body.style.animation = "";
    });
  });
});
