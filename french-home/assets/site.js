/* Public site: reads content/site.json and renders each page from the URL hash. */
(function () {
  "use strict";
  var M = window.MDC, esc = M.esc;
  var data = null;
  var app = document.getElementById("app");
  var lb = { list: [], i: 0 };

  var ORNAMENT = '<svg class="ornament" viewBox="0 0 44 14" fill="none" stroke="currentColor" stroke-width="1"><path d="M0 7h15M29 7h15"/><path d="M22 1c-3 3-3 9 0 12 3-3 3-9 0-12z"/><circle cx="22" cy="7" r="1.2" fill="currentColor"/></svg>';

  function published() {
    return M.sortArticles((data.articles || []).filter(function (a) { return a.status !== "draft"; }));
  }
  function cat(id) {
    return (data.categories || []).find(function (c) { return c.id === id; }) || { id: id, name: id || "" };
  }
  function photo(src) {
    return (data.photos || []).find(function (p) { return p.src === src; });
  }
  function img(src, alt, attrs) {
    return '<img src="' + esc(M.safeUrl(src)) + '" alt="' + esc(alt || "") + '" ' + (attrs || 'loading="lazy"') + ">";
  }

  function card(a) {
    return '<a class="card reveal" href="#/article/' + esc(a.slug) + '">' +
      '<div class="ph">' + img(a.cover, a.title) + "</div>" +
      '<span class="kicker">' + esc(cat(a.category).name) + "</span>" +
      "<h3>" + esc(a.title) + "</h3>" +
      "<p>" + esc(a.dek || "") + "</p>" +
      '<div class="meta">' + esc(M.fmtDate(a.date)) + "</div></a>";
  }

  /* ---------- pages ---------- */

  function home() {
    var list = published();
    var hero = list.find(function (a) { return a.featured; }) || list[0];
    var rest = list.filter(function (a) { return a !== hero; });
    var second = rest[3];
    var gallery = (data.photos || []).filter(function (p) { return p.gallery !== false; }).slice(0, 6);
    var s = data.site;
    var h = "";

    if (hero) {
      h += '<section class="hero">' + img(hero.cover, hero.title, 'fetchpriority="high"') +
        '<div class="wrap"><a class="kicker" href="#/journal/' + esc(hero.category) + '">' + esc(cat(hero.category).name) + "</a>" +
        "<h1>" + esc(hero.title) + "</h1><p>" + esc(hero.dek || "") + "</p>" +
        '<a class="btn" href="#/article/' + esc(hero.slug) + '">Read the story</a></div></section>';
    }

    h += '<section class="block"><div class="wrap"><div class="section-head"><h2>Latest from the club</h2><a href="#/journal">All stories →</a></div>' +
      '<div class="grid">' + rest.slice(0, 3).map(card).join("") + "</div></div></section>";

    if ((data.categories || []).length) {
      h += '<section class="block band"><div class="wrap"><div class="section-head"><h2>Explore the club</h2></div><div class="cats">' +
        data.categories.map(function (c) {
          return '<a class="cat reveal" href="#/journal/' + esc(c.id) + '">' + img(c.photo, c.name) + "<span>" + esc(c.name) + "</span></a>";
        }).join("") + "</div></div></section>";
    }

    if (second) {
      h += '<section class="block"><div class="wrap feature reveal"><a class="ph" href="#/article/' + esc(second.slug) + '">' + img(second.cover, second.title) + "</a>" +
        '<div><span class="kicker">' + esc(cat(second.category).name) + "</span><h3>" + esc(second.title) + "</h3>" +
        '<p style="color:var(--ink-soft)">' + esc(second.dek || "") + "</p>" +
        '<a class="btn dark" href="#/article/' + esc(second.slug) + '">Continue reading</a></div></div></section>';
    }

    if (s.quote) {
      h += '<section class="block band"><div class="wrap quote reveal">' + ORNAMENT +
        "<blockquote>" + esc(s.quote) + "</blockquote>" + (s.quoteBy ? "<cite>" + esc(s.quoteBy) + "</cite>" : "") + "</div></section>";
    }

    if (rest.length > 4) {
      h += '<section class="block"><div class="wrap"><div class="section-head"><h2>From the journal</h2><a href="#/journal">All stories →</a></div>' +
        '<div class="grid">' + rest.slice(4, 7).map(card).join("") + "</div></div></section>";
    }

    if (gallery.length) {
      h += '<section class="block" style="padding-top:0"><div class="wrap"><div class="section-head"><h2>Seen in the countryside</h2><a href="#/gallery">Gallery →</a></div>' +
        '<div class="strip">' + gallery.map(function (p, i) {
          return '<button data-lb="home" data-i="' + i + '" aria-label="' + esc(p.caption || "Open photo") + '">' + img(p.src, p.caption) + "</button>";
        }).join("") + "</div></div></section>";
      lb.sets = { home: gallery };
    }
    return h;
  }

  function journal(catId) {
    var list = published().filter(function (a) { return !catId || a.category === catId; });
    var c = catId ? cat(catId) : null;
    var h = '<div class="wrap page-head"><span class="kicker">The Club Journal</span><h1>' + esc(c ? c.name : "All stories") + "</h1>" +
      "<p>" + esc(c ? (c.blurb || "") : (data.site.tagline || "")) + "</p>" +
      '<nav class="filters"><a href="#/journal"' + (!catId ? ' class="on"' : "") + ">All</a>" +
      (data.categories || []).map(function (x) {
        return '<a href="#/journal/' + esc(x.id) + '"' + (x.id === catId ? ' class="on"' : "") + ">" + esc(x.name) + "</a>";
      }).join("") + "</nav></div>";
    h += '<section class="block" style="padding-top:20px"><div class="wrap">' +
      (list.length ? '<div class="grid">' + list.map(card).join("") + "</div>" : '<p class="empty">No stories here yet.</p>') + "</div></section>";
    return h;
  }

  function article(slug) {
    var all = published();
    var a = all.find(function (x) { return x.slug === slug; });
    if (!a) return '<div class="wrap page-head"><h1>Story not found</h1><p><a href="#/journal">Back to the journal</a></p></div>';
    document.title = a.title + " · " + data.site.name;
    var i = all.indexOf(a), newer = all[i - 1], older = all[i + 1];
    var related = all.filter(function (x) { return x !== a && x.category === a.category; }).slice(0, 3);
    var cap = a.coverCaption || (photo(a.cover) || {}).caption || "";
    var h = '<div class="article-hero">' + img(a.cover, cap || a.title, 'fetchpriority="high"') + "</div>" +
      '<header class="article-head"><a class="kicker" href="#/journal/' + esc(a.category) + '">' + esc(cat(a.category).name) + "</a>" +
      "<h1>" + esc(a.title) + "</h1>" + (a.dek ? '<p class="dek">' + esc(a.dek) + "</p>" : "") +
      '<div class="meta">' + [a.author ? "By " + esc(a.author) : "", esc(M.fmtDate(a.date)), M.readingTime(a.body)].filter(Boolean).join(" · ") + "</div></header>" +
      '<article class="prose">' + M.md(a.body) + "</article>" +
      '<nav class="article-foot"><span>' + (older ? '<a href="#/article/' + esc(older.slug) + '">← ' + esc(older.title) + "</a>" : "") + "</span>" +
      "<span>" + (newer ? '<a href="#/article/' + esc(newer.slug) + '">' + esc(newer.title) + " →</a>" : "") + "</span></nav>";
    if (related.length) {
      h += '<section class="block band"><div class="wrap"><div class="section-head"><h2>More in ' + esc(cat(a.category).name) + "</h2></div>" +
        '<div class="grid">' + related.map(card).join("") + "</div></div></section>";
    }
    return h;
  }

  function gallery() {
    var list = (data.photos || []).filter(function (p) { return p.gallery !== false; });
    lb.sets = { gallery: list };
    return '<div class="wrap page-head"><span class="kicker">Gallery</span><h1>Seen in the countryside</h1><p>' + esc(data.site.galleryIntro || "") + "</p></div>" +
      '<section class="block" style="padding-top:10px"><div class="wrap">' +
      (list.length ? '<div class="masonry">' + list.map(function (p, i) {
        return '<figure class="reveal" data-lb="gallery" data-i="' + i + '">' + img(p.src, p.caption) + (p.caption ? "<figcaption>" + esc(p.caption) + "</figcaption>" : "") + "</figure>";
      }).join("") + "</div>" : '<p class="empty">No photos yet.</p>') + "</div></section>";
  }

  function about() {
    var s = data.site;
    return '<div class="wrap page-head"><span class="kicker">About the club</span><h1>' + esc(s.aboutTitle || "About") + "</h1></div>" +
      '<section class="block" style="padding-top:10px"><div class="wrap about"><div class="ph">' + img(s.aboutPhoto, s.name) + "</div>" +
      '<div class="prose" style="padding-top:0">' + M.md(s.about) +
      (s.email ? '<p>Write to the club: <a href="mailto:' + esc(s.email) + '">' + esc(s.email) + "</a></p>" : "") + "</div></div></section>";
  }

  function credits() {
    var list = (data.photos || []).filter(function (p) { return p.credit; });
    return '<div class="wrap page-head"><span class="kicker">Credits</span><h1>Photo credits</h1><p>With thanks to the photographers who share their work under open licences.</p></div>' +
      '<section class="block" style="padding-top:10px"><div class="wrap"><ul class="credits">' +
      list.map(function (p) {
        return "<li><strong>" + esc(p.caption || p.src) + "</strong>: " + esc(p.credit) + (p.license ? ", " + esc(p.license) : "") +
          (p.sourceUrl ? ' (<a href="' + esc(M.safeUrl(p.sourceUrl)) + '" target="_blank" rel="noopener">source</a>)' : "") + "</li>";
      }).join("") + "</ul></div></section>";
  }

  /* ---------- shell ---------- */

  function shell() {
    var s = data.site;
    document.querySelectorAll("[data-site-name]").forEach(function (el) { el.textContent = s.name; });
    document.querySelectorAll("[data-site-tagline]").forEach(function (el) { el.textContent = s.tagline || ""; });
    document.getElementById("today").textContent = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
    var nav = document.getElementById("nav");
    nav.innerHTML = '<a href="#/journal" data-r="journal">Journal</a>' +
      (data.categories || []).map(function (c) { return '<a href="#/journal/' + esc(c.id) + '" data-r="journal/' + esc(c.id) + '">' + esc(c.name) + "</a>"; }).join("") +
      '<a href="#/gallery" data-r="gallery">Gallery</a><a href="#/about" data-r="about">About</a>';
    document.getElementById("foot-cats").innerHTML = (data.categories || []).map(function (c) {
      return '<li><a href="#/journal/' + esc(c.id) + '">' + esc(c.name) + "</a></li>";
    }).join("");
    var links = [];
    if (s.instagram) links.push('<li><a href="' + esc(M.safeUrl(s.instagram)) + '" target="_blank" rel="noopener">Instagram</a></li>');
    if (s.email) links.push('<li><a href="mailto:' + esc(s.email) + '">' + esc(s.email) + "</a></li>");
    document.getElementById("foot-links").innerHTML = links.join("") + '<li><a href="#/credits">Photo credits</a></li>';
    document.getElementById("year").textContent = new Date().getFullYear();
    document.getElementById("foot-about").textContent = s.description || "";
  }

  function route() {
    var r = (location.hash.replace(/^#\/?/, "") || "").split("/");
    var page = r[0] || "", arg = decodeURIComponent(r[1] || "");
    document.title = data.site.name + (data.site.tagline ? " · " + data.site.tagline : "");
    var html;
    if (page === "journal") html = journal(arg);
    else if (page === "article") html = article(arg);
    else if (page === "gallery") html = gallery();
    else if (page === "about") html = about();
    else if (page === "credits") html = credits();
    else html = home();
    app.innerHTML = html;
    document.querySelectorAll("#nav a").forEach(function (a) {
      var k = a.getAttribute("data-r");
      a.classList.toggle("on", (page + (arg ? "/" + arg : "")) === k || (page === "journal" && !arg && k === "journal"));
    });
    document.getElementById("nav").classList.remove("open");
    window.scrollTo(0, 0);
    observe();
  }

  function observe() {
    var els = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window)) { els.forEach(function (e) { e.classList.add("in"); }); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { rootMargin: "0px 0px -8% 0px" });
    els.forEach(function (e) { io.observe(e); });
  }

  /* ---------- lightbox ---------- */
  var box = document.getElementById("lightbox");
  function show() {
    var p = lb.list[lb.i];
    box.querySelector("img").src = p.src;
    box.querySelector("img").alt = p.caption || "";
    box.querySelector("p").textContent = p.caption || "";
  }
  function openLb(list, i) { lb.list = list; lb.i = i; show(); box.classList.add("open"); }
  function closeLb() { box.classList.remove("open"); }
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-lb]");
    if (t && lb.sets) { openLb(lb.sets[t.getAttribute("data-lb")], +t.getAttribute("data-i")); return; }
    var fig = e.target.closest(".prose figure img");
    if (fig) { openLb([{ src: fig.src, caption: fig.alt }], 0); }
  });
  box.querySelector(".x").onclick = closeLb;
  box.querySelector(".prev").onclick = function () { lb.i = (lb.i - 1 + lb.list.length) % lb.list.length; show(); };
  box.querySelector(".next").onclick = function () { lb.i = (lb.i + 1) % lb.list.length; show(); };
  box.addEventListener("click", function (e) { if (e.target === box) closeLb(); });
  document.addEventListener("keydown", function (e) {
    if (!box.classList.contains("open")) return;
    if (e.key === "Escape") closeLb();
    if (e.key === "ArrowLeft") box.querySelector(".prev").click();
    if (e.key === "ArrowRight") box.querySelector(".next").click();
  });

  document.getElementById("menu-btn").onclick = function () { document.getElementById("nav").classList.toggle("open"); };

  fetch("content/site.json", { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (d) { data = d; shell(); route(); window.addEventListener("hashchange", route); })
    .catch(function () {
      app.innerHTML = '<div class="wrap page-head"><h1>Unable to load the magazine</h1><p>The content file could not be read. If you opened this file straight from your computer, run it from a web server instead (see the README).</p></div>';
    });
})();
