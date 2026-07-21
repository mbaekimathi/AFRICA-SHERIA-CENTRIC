/**
 * Live SEO readiness coach for the employee blog editor.
 */
(function () {
  const form = document.getElementById("blog-editor-form");
  if (!form) return;

  const fields = {
    title: form.querySelector('[data-seo-field="title"]'),
    slug: form.querySelector('[data-seo-field="slug"]'),
    excerpt: form.querySelector('[data-seo-field="excerpt"]'),
    body: form.querySelector('[data-seo-field="body"]'),
    metaTitle: form.querySelector('[data-seo-field="meta_title"]'),
    metaDescription: form.querySelector('[data-seo-field="meta_description"]'),
    focusKeyword: form.querySelector('[data-seo-field="focus_keyword"]'),
    tags: form.querySelector('[data-seo-field="tags"]'),
    cover: form.querySelector('[data-seo-field="cover"]'),
  };

  const scoreEl = document.getElementById("blog-seo-score");
  const scoreMetaEl = document.getElementById("blog-seo-score-meta");
  const checklistEl = document.getElementById("blog-seo-checklist");
  const serpTitle = document.getElementById("serp-title");
  const serpDesc = document.getElementById("serp-desc");
  const serpSlug = document.getElementById("serp-slug");
  const slugPreview = document.getElementById("blog-slug-preview");
  const titleCount = document.getElementById("blog-title-count");
  const wordCount = document.getElementById("blog-word-count");
  const readingTime = document.getElementById("blog-reading-time");
  const bodyPreview = document.getElementById("blog-body-preview");
  const metaTitleCount = document.getElementById("blog-meta-title-count");
  const metaDescCount = document.getElementById("blog-meta-desc-count");
  const clearCover = form.querySelector('input[name="clear_cover"]');
  const hasExistingCover = Boolean(document.querySelector(".blog-cover-preview img"));

  function val(el) {
    return (el && el.value ? el.value : "").trim();
  }

  function slugify(text) {
    return text
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 220);
  }

  function wordCountOf(text) {
    return text ? text.split(/\s+/).filter(Boolean).length : 0;
  }

  function hasKeyword(haystack, keyword) {
    return Boolean(keyword) && haystack.toLowerCase().includes(keyword.toLowerCase());
  }

  function coverPresent() {
    if (clearCover && clearCover.checked) return false;
    if (fields.cover && fields.cover.files && fields.cover.files.length) return true;
    return hasExistingCover;
  }

  function insertFormatting(type) {
    const body = fields.body;
    if (!body) return;
    const start = body.selectionStart;
    const end = body.selectionEnd;
    const selected = body.value.slice(start, end);
    const formats = {
      bold: `**${selected || "important text"}**`,
      italic: `*${selected || "emphasised text"}*`,
      heading: `\n## ${selected || "Section heading"}\n`,
      bullet: selected
        ? `\n${selected
            .split("\n")
            .map((line) => `- ${line.replace(/^-\s*/, "")}`)
            .join("\n")}\n`
        : "\n- First point\n- Second point\n",
      quote: `\n> ${selected || "Quoted material — identify the source"}\n`,
      link: `[${selected || "Source title"}](https://example.com)`,
    };
    const replacement = formats[type];
    if (!replacement) return;
    body.setRangeText(replacement, start, end, "end");
    body.focus();
    body.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function appendInline(parent, text) {
    const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\(https?:\/\/[^)]+\))/g;
    let cursor = 0;
    for (const match of text.matchAll(pattern)) {
      parent.append(document.createTextNode(text.slice(cursor, match.index)));
      const token = match[0];
      let node;
      if (token.startsWith("**")) {
        node = document.createElement("strong");
        node.textContent = token.slice(2, -2);
      } else if (token.startsWith("*")) {
        node = document.createElement("em");
        node.textContent = token.slice(1, -1);
      } else {
        const parts = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
        node = document.createElement("a");
        node.textContent = parts[1];
        node.href = parts[2];
        node.target = "_blank";
        node.rel = "noopener noreferrer";
      }
      parent.append(node);
      cursor = match.index + token.length;
    }
    parent.append(document.createTextNode(text.slice(cursor)));
  }

  function renderBodyPreview() {
    if (!bodyPreview || !fields.body) return;
    bodyPreview.replaceChildren();
    let list = null;
    val(fields.body)
      .split("\n")
      .forEach((rawLine) => {
        const line = rawLine.trim();
        if (!line) {
          list = null;
          return;
        }
        let node;
        let content = line;
        if (/^#{2,3}\s/.test(line)) {
          node = document.createElement(line.startsWith("### ") ? "h3" : "h2");
          content = line.replace(/^#{2,3}\s+/, "");
          list = null;
        } else if (/^-\s/.test(line)) {
          if (!list) {
            list = document.createElement("ul");
            bodyPreview.append(list);
          }
          node = document.createElement("li");
          content = line.replace(/^-\s+/, "");
          appendInline(node, content);
          list.append(node);
          return;
        } else if (/^>\s?/.test(line)) {
          node = document.createElement("blockquote");
          content = line.replace(/^>\s?/, "");
          list = null;
        } else {
          node = document.createElement("p");
          list = null;
        }
        appendInline(node, content);
        bodyPreview.append(node);
      });
  }

  function setEditorView(view) {
    const previewing = view === "preview";
    fields.body.hidden = previewing;
    bodyPreview.hidden = !previewing;
    document.querySelectorAll("[data-blog-view]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.blogView === view);
    });
    if (previewing) renderBodyPreview();
  }

  function evaluate() {
    const title = val(fields.title);
    const slug = val(fields.slug) || slugify(title);
    const excerpt = val(fields.excerpt);
    const body = val(fields.body);
    const metaTitle = val(fields.metaTitle) || title;
    const metaDesc = val(fields.metaDescription);
    const keyword = val(fields.focusKeyword);
    const tags = val(fields.tags)
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const words = wordCountOf(body);
    const keywordSlug = keyword.toLowerCase().replace(/\s+/g, "-");
    const headingCount = (body.match(/^#{2,3}\s+\S/gm) || []).length;
    const keywordUses = keyword
      ? body.toLowerCase().split(keyword.toLowerCase()).length - 1
      : 0;
    const keywordDensity = words ? (keywordUses / words) * 100 : 0;

    const checks = [
      {
        id: "title_length",
        ok: title.length >= 30 && title.length <= 60,
        hint: `${title.length} characters — aim for a clear, specific title.`,
      },
      {
        id: "meta_title",
        ok: metaTitle.length >= 50 && metaTitle.length <= 60,
        hint: `${metaTitle.length} characters — this appears in the browser tab and Google.`,
      },
      {
        id: "meta_description",
        ok: metaDesc.length >= 120 && metaDesc.length <= 160,
        hint: `${metaDesc.length} characters — write a compelling snippet for search results.`,
      },
      {
        id: "excerpt",
        ok: excerpt.length >= 40 && excerpt.length <= 320,
        hint: "A short summary helps the blog list and social previews.",
      },
      {
        id: "focus_keyword",
        ok: Boolean(keyword),
        hint: "Pick one primary phrase readers would search for.",
      },
      {
        id: "keyword_in_title",
        ok: hasKeyword(title, keyword),
        hint: "Include the keyword naturally in the title.",
      },
      {
        id: "keyword_in_meta",
        ok: hasKeyword(metaDesc, keyword),
        hint: "Mention the keyword once in the meta description.",
      },
      {
        id: "keyword_in_body",
        ok: hasKeyword(body, keyword),
        hint: "Use the keyword early, then write naturally.",
      },
      {
        id: "body_length",
        ok: words >= 300,
        hint: `${words} words — longer, helpful posts tend to rank better.`,
      },
      {
        id: "headings",
        ok: headingCount >= 2,
        hint: `${headingCount} headings — use at least two to structure the article.`,
      },
      {
        id: "keyword_density",
        ok: Boolean(keyword) && keywordDensity >= 0.2 && keywordDensity <= 3,
        hint: `Used ${keywordUses} time(s) — avoid both omission and repetition.`,
      },
      {
        id: "source_link",
        ok: /https?:\/\/\S+/.test(body),
        hint: "Link to a primary or authoritative source where possible.",
      },
      {
        id: "slug",
        ok: Boolean(slug),
        hint: "Use a short, readable slug with your keyword if it fits.",
      },
      {
        id: "keyword_in_slug",
        ok: Boolean(keyword) && slug.includes(keywordSlug),
        hint: "A keyword-rich slug helps Google understand the page.",
      },
      {
        id: "cover",
        ok: coverPresent(),
        hint: "Images improve sharing and make the post stand out.",
      },
      {
        id: "tags",
        ok: tags.length >= 1,
        hint: "Tags help group related posts on the website.",
      },
    ];

    const passed = checks.filter((c) => c.ok).length;
    const score = Math.round((passed / checks.length) * 100);

    if (scoreEl) scoreEl.textContent = `${score}%`;
    if (scoreMetaEl) {
      scoreMetaEl.textContent = `${passed} of ${checks.length} checks passed`;
    }

    if (checklistEl) {
      checks.forEach((check) => {
        const item = checklistEl.querySelector(`[data-check="${check.id}"]`);
        if (!item) return;
        item.classList.toggle("is-ok", check.ok);
        item.classList.toggle("is-todo", !check.ok);
        const hint = item.querySelector(".blog-seo-check__copy span");
        if (hint) hint.textContent = check.hint;
      });
    }

    if (serpTitle) {
      serpTitle.textContent = metaTitle || "Your SEO title";
    }
    if (serpDesc) {
      serpDesc.textContent =
        metaDesc || excerpt || "Your meta description will appear here…";
    }
    if (serpSlug) serpSlug.textContent = slug || "your-slug";
    if (slugPreview) slugPreview.textContent = slug || "your-slug";

    if (titleCount) {
      titleCount.textContent = `${title.length} characters — aim for 30–60.`;
    }
    if (wordCount) {
      wordCount.textContent = `${words} words — write at least 300 for stronger SEO.`;
    }
    if (readingTime) {
      const minutes = Math.max(1, Math.ceil(words / 200));
      readingTime.textContent = `${minutes} minute${minutes === 1 ? "" : "s"} read`;
    }
    if (metaTitleCount) {
      metaTitleCount.textContent = `${metaTitle.length} characters — ideal SEO title is 50–60.`;
    }
    if (metaDescCount) {
      metaDescCount.textContent = `${metaDesc.length} characters — ideal meta description is 120–160.`;
    }
  }

  form.addEventListener("input", evaluate);
  form.addEventListener("change", evaluate);
  document.querySelectorAll("[data-blog-format]").forEach((button) => {
    button.addEventListener("click", () => {
      insertFormatting(button.dataset.blogFormat);
    });
  });
  document.querySelectorAll("[data-blog-view]").forEach((button) => {
    button.addEventListener("click", () => {
      setEditorView(button.dataset.blogView);
    });
  });
  evaluate();
})();
