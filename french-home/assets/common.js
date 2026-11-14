/* Shared helpers for the public site and the admin. */
(function (global) {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Only allow web links, relative paths and in-page anchors. Blocks javascript: and data: URLs.
  function safeUrl(u, allowData) {
    u = String(u || "").trim();
    if (allowData && /^data:image\/(jpeg|png|webp|gif);base64,/i.test(u)) return u;
    if (/^(https?:\/\/|mailto:|#|\.{0,2}\/|[\w-]+\/)/i.test(u) || /^[\w.-]+\.(jpe?g|png|webp|gif)$/i.test(u)) return u;
    return "#";
  }

  function slugify(s) {
    return String(s || "")
      .normalize("NFD").replace(/[̀-ͯ]/g, "")
      .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 70) || "article";
  }

  function fmtDate(iso, lang) {
    if (!iso) return "";
    var d = new Date(iso + (iso.length === 10 ? "T12:00:00" : ""));
    if (isNaN(d)) return iso;
    return d.toLocaleDateString(lang || "en-GB", { day: "numeric", month: "long", year: "numeric" });
  }

  function readingTime(text) {
    var words = String(text || "").split(/\s+/).filter(Boolean).length;
    return Math.max(1, Math.round(words / 220)) + " min read";
  }

  // Inline markdown: **bold**, *italic*, [link](url). Input is escaped first.
  function inline(text, resolve) {
    var s = esc(text);
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (_, t, u) {
      var url = safeUrl(u.replace(/&amp;/g, "&"));
      var ext = /^https?:/i.test(url) ? ' target="_blank" rel="noopener"' : "";
      return '<a href="' + esc(url) + '"' + ext + ">" + t + "</a>";
    });
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    return s;
  }

  // Small, safe Markdown renderer for article bodies.
  // Supports: ## / ### headings, > quotes, - and 1. lists, ![caption](photo) on its own line, paragraphs.
  function md(src, resolve) {
    resolve = resolve || function (x) { return x; };
    var blocks = String(src || "").replace(/\r\n?/g, "\n").split(/\n{2,}/);
    var out = [];
    blocks.forEach(function (b) {
      b = b.trim();
      if (!b) return;
      var img = b.match(/^!\[([^\]]*)\]\(([^)\s]+)\)$/);
      if (img) {
        out.push('<figure><img loading="lazy" src="' + esc(safeUrl(resolve(img[2]), true)) + '" alt="' + esc(img[1]) + '">' +
          (img[1] ? "<figcaption>" + inline(img[1]) + "</figcaption>" : "") + "</figure>");
        return;
      }
      if (/^### /.test(b)) { out.push("<h3>" + inline(b.slice(4)) + "</h3>"); return; }
      if (/^## /.test(b)) { out.push("<h2>" + inline(b.slice(3)) + "</h2>"); return; }
      if (/^> /.test(b)) {
        out.push("<blockquote>" + b.split("\n").map(function (l) { return inline(l.replace(/^>\s?/, "")); }).join("<br>") + "</blockquote>");
        return;
      }
      var lines = b.split("\n");
      if (lines.every(function (l) { return /^[-*] /.test(l); })) {
        out.push("<ul>" + lines.map(function (l) { return "<li>" + inline(l.slice(2)) + "</li>"; }).join("") + "</ul>");
        return;
      }
      if (lines.every(function (l) { return /^\d+[.)] /.test(l); })) {
        out.push("<ol>" + lines.map(function (l) { return "<li>" + inline(l.replace(/^\d+[.)] /, "")) + "</li>"; }).join("") + "</ol>");
        return;
      }
      out.push("<p>" + lines.map(function (l) { return inline(l); }).join("<br>") + "</p>");
    });
    return out.join("\n");
  }

  function sortArticles(list) {
    return list.slice().sort(function (a, b) { return String(b.date).localeCompare(String(a.date)); });
  }

  global.MDC = { esc: esc, safeUrl: safeUrl, slugify: slugify, fmtDate: fmtDate, readingTime: readingTime, md: md, inline: inline, sortArticles: sortArticles };
})(window);
