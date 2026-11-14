/* Admin: edit articles, photos and settings, then publish them to GitHub in one commit. */
(function () {
  "use strict";
  var M = window.MDC, esc = M.esc;

  // Defaults. When the admin runs on GitHub Pages (<owner>.github.io/<repo>/...), the repository is detected from the address.
  var DEFAULTS = { repo: "mauritsreijnen97/Apps", branch: "", folder: "french-home" };
  var TOKEN_KEY = "mdc-admin-token", CFG_KEY = "mdc-admin-config";

  var S = {
    mode: null,          // "github" or "local"
    cfg: null, token: null, branch: null,
    data: null,          // working copy of site.json
    base: "",            // site.json text as last loaded or published
    pending: {},         // path -> { b64, url } new photos waiting to be published
    cache: {},           // path -> url published this session (shown until the live site has them)
    deletes: {},         // path -> true committed photo files to remove
    committed: {},       // src -> true photos that exist in the repository
    tab: "articles", editing: null, slugTouched: false, filter: ""
  };

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var root = $("#root");

  /* ---------------- storage ---------------- */
  function store(kind) { try { return window[kind]; } catch (e) { return null; } }
  function getSaved(key) {
    var v = null;
    ["sessionStorage", "localStorage"].some(function (k) { var s = store(k); try { v = s && s.getItem(key); } catch (e) {} return v; });
    return v;
  }
  function setSaved(key, val, remember) {
    ["sessionStorage", "localStorage"].forEach(function (k) { var s = store(k); try { s && s.removeItem(key); } catch (e) {} });
    var s = store(remember ? "localStorage" : "sessionStorage");
    try { if (s && val != null) s.setItem(key, val); } catch (e) {}
  }

  function detectCfg() {
    var cfg = {};
    try { cfg = JSON.parse(getSaved(CFG_KEY) || "{}"); } catch (e) {}
    var m = location.hostname.match(/^([\w-]+)\.github\.io$/);
    if (m && !cfg.repo) {
      var parts = location.pathname.split("/").filter(Boolean);
      var adminIdx = parts.length - 1;
      cfg.repo = m[1] + "/" + (parts[0] || m[1] + ".github.io");
      cfg.folder = parts.slice(1, adminIdx).join("/") || DEFAULTS.folder;
    }
    return { repo: cfg.repo || DEFAULTS.repo, branch: cfg.branch || DEFAULTS.branch, folder: cfg.folder != null ? cfg.folder : DEFAULTS.folder };
  }

  /* ---------------- GitHub API ---------------- */
  function gh(method, path, body, accept) {
    return fetch("https://api.github.com" + path, {
      method: method,
      headers: {
        "Authorization": "Bearer " + S.token,
        "Accept": accept || "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json"
      },
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store"
    }).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (t) {
          var msg = t; try { msg = JSON.parse(t).message; } catch (e) {}
          var err = new Error(friendly(r.status, msg)); err.status = r.status; throw err;
        });
      }
      return accept && accept.indexOf("raw") > -1 ? r.text() : r.json();
    });
  }
  function friendly(status, msg) {
    if (status === 401) return "GitHub did not accept this token. Check that you copied all of it and that it hasn't expired.";
    if (status === 403) return "This token isn't allowed to do that. It needs “Contents: Read and write” permission on the repository. (" + msg + ")";
    if (status === 404) return "Not found on GitHub. Check the repository name, branch and folder, and that the token has access to this repository.";
    if (status === 409 || status === 422) return "GitHub refused the update (" + msg + "). Reload the admin and try again.";
    return "GitHub error " + status + ": " + msg;
  }
  function repoPath(p) { return (S.cfg.folder ? S.cfg.folder.replace(/\/+$/, "") + "/" : "") + p; }
  function encPath(p) { return p.split("/").map(encodeURIComponent).join("/"); }
  function fetchRemoteJson() {
    return gh("GET", "/repos/" + S.cfg.repo + "/contents/" + encPath(repoPath("content/site.json")) + "?ref=" + encodeURIComponent(S.branch), null, "application/vnd.github.raw+json");
  }

  /* ---------------- data helpers ---------------- */
  function json() { return JSON.stringify(S.data, null, 2) + "\n"; }
  function changes() {
    var n = Object.keys(S.pending).length + Object.keys(S.deletes).length;
    return n + (json() !== S.base ? 1 : 0);
  }
  function dirty() { renderBar(); }
  function cat(id) { return (S.data.categories || []).find(function (c) { return c.id === id; }) || { name: id || "Uncategorised" }; }
  function uid(prefix) { return prefix + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
  function today() { var d = new Date(); return new Date(d - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); }

  // Image URL for previews: new uploads show from memory; committed photos fall back to the repository if Pages hasn't updated yet.
  function src(p) {
    if (!p) return "";
    if (S.pending[p]) return S.pending[p].url;
    if (S.cache[p]) return S.cache[p];
    return p;
  }
  function imgTag(p, alt, cls) {
    if (!p) return '<div class="noimg ' + (cls || "") + '"></div>';
    var fb = S.mode === "github" && /^[\w-]/.test(p) && !/^https?:/.test(p)
      ? ' onerror="this.onerror=null;this.src=\'https://raw.githubusercontent.com/' + esc(S.cfg.repo) + "/" + esc(encodeURIComponent(S.branch)) + "/" + esc(repoPath(p)) + '\'"' : "";
    return '<img class="' + (cls || "") + '" src="' + esc(M.safeUrl(src(p), true)) + '" alt="' + esc(alt || "") + '" loading="lazy"' + fb + ">";
  }

  /* ---------------- images ---------------- */
  function prepImage(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file), im = new Image();
      im.onload = function () {
        var max = 2000, w = im.naturalWidth, h = im.naturalHeight, k = Math.min(1, max / Math.max(w, h));
        var c = document.createElement("canvas");
        c.width = Math.round(w * k); c.height = Math.round(h * k);
        var ctx = c.getContext("2d");
        ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(im, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        var data = c.toDataURL("image/jpeg", 0.85);
        resolve({ url: data, b64: data.split(",")[1] });
      };
      im.onerror = function () { URL.revokeObjectURL(url); reject(new Error("Couldn't read " + file.name + ". Use a JPEG, PNG or WebP photo.")); };
      im.src = url;
    });
  }
  function addFiles(files) {
    files = Array.prototype.filter.call(files || [], function (f) { return /^image\//.test(f.type) || /\.(jpe?g|png|webp|heic|gif)$/i.test(f.name); });
    if (!files.length) return Promise.resolve([]);
    toast("Preparing " + files.length + " photo" + (files.length > 1 ? "s" : "") + "…");
    var added = [];
    return files.reduce(function (p, f) {
      return p.then(function () {
        return prepImage(f).then(function (img) {
          var name = M.slugify(f.name.replace(/\.[^.]+$/, "")).slice(0, 40);
          var path = "photos/uploads/" + today().slice(0, 7) + "-" + name + "-" + Math.random().toString(36).slice(2, 6) + ".jpg";
          S.pending[path] = img;
          var ph = { id: uid("p"), src: path, caption: f.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " "), credit: "", gallery: true, date: today() };
          S.data.photos.unshift(ph);
          added.push(ph);
        }).catch(function (e) { alert(e.message); });
      });
    }, Promise.resolve()).then(function () { dirty(); toast(added.length + " photo" + (added.length === 1 ? "" : "s") + " added. Publish to put them online."); return added; });
  }

  /* ---------------- UI: shell ---------------- */
  var toastT;
  function toast(msg) {
    var t = $(".toast") || document.body.appendChild(Object.assign(document.createElement("div"), { className: "toast" }));
    t.textContent = msg; t.classList.remove("hidden");
    clearTimeout(toastT); toastT = setTimeout(function () { t.classList.add("hidden"); }, 3800);
  }

  function renderBar() {
    var n = changes();
    var bar = $("#bar");
    if (!bar) return;
    bar.innerHTML = '<div class="in"><a class="adm-brand" href="index.html" target="_blank">' + esc(S.data.site.name) + "<small>Admin</small></a>" +
      (S.mode === "local" ? '<span class="pill warn">Preview mode: changes stay in this browser</span>' : '<span class="pill">' + esc(S.cfg.repo) + " · " + esc(S.branch) + "</span>") +
      (n ? '<span class="pill warn">' + n + " unpublished change" + (n > 1 ? "s" : "") + "</span>" : '<span class="pill ok">All changes published</span>') +
      '<a class="b" href="index.html" target="_blank">View site</a>' +
      (S.mode === "github"
        ? '<button class="b primary" data-act="publish"' + (n ? "" : " disabled") + ">Publish</button>"
        : '<button class="b primary" data-act="download">Download site.json</button>') +
      '<button class="b ghost" data-act="signout">Sign out</button></div>';
    var counts = { articles: S.data.articles.length, photos: S.data.photos.length };
    document.querySelectorAll(".adm-side [data-tab]").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-tab") === S.tab);
      var c = b.querySelector(".count"); if (c) c.textContent = counts[b.getAttribute("data-tab")] != null ? counts[b.getAttribute("data-tab")] : "";
    });
  }

  function renderApp() {
    root.innerHTML = '<header class="adm-bar" id="bar"></header><div class="adm-layout"><nav class="adm-side">' +
      '<button data-tab="articles">Articles <span class="count"></span></button>' +
      '<button data-tab="photos">Photos <span class="count"></span></button>' +
      '<button data-tab="settings">Site settings</button>' +
      '<button data-tab="help">Help</button></nav><main id="main"></main></div>';
    renderBar(); renderMain();
  }

  function renderMain() {
    var main = $("#main");
    if (S.editing) main.innerHTML = editorView();
    else if (S.tab === "articles") main.innerHTML = articlesView();
    else if (S.tab === "photos") main.innerHTML = photosView();
    else if (S.tab === "settings") main.innerHTML = settingsView();
    else main.innerHTML = helpView();
    renderBar();
    if (S.editing) updatePreview();
  }

  /* ---------------- articles ---------------- */
  function articlesView() {
    var q = S.filter.toLowerCase();
    var list = M.sortArticles(S.data.articles).filter(function (a) { return !q || (a.title + " " + (a.dek || "")).toLowerCase().indexOf(q) > -1; });
    return '<section class="panel"><div class="panel-head"><h2>Articles</h2><div style="display:flex;gap:8px;flex-wrap:wrap">' +
      '<input type="search" placeholder="Search articles" data-bind="filter" value="' + esc(S.filter) + '" style="width:220px">' +
      '<button class="b primary" data-act="new-article">+ New article</button></div></div>' +
      (list.length ? '<div class="alist">' + list.map(function (a) {
        return '<div class="aitem" data-act="edit" data-id="' + esc(a.id) + '">' + imgTag(a.cover, "") +
          "<div><h3>" + esc(a.title || "Untitled") + '</h3><div class="meta"><span>' + esc(cat(a.category).name) + "</span><span>" + esc(M.fmtDate(a.date)) + "</span>" +
          (a.status === "draft" ? '<span class="pill warn">Draft</span>' : '<span class="pill ok">Published</span>') +
          (a.featured ? '<span class="pill">★ Featured</span>' : "") + "</div></div>" +
          '<div class="acts"><button class="b sm">Edit</button></div></div>';
      }).join("") + "</div>" : '<p class="note">No articles yet. Click “New article” to write your first one.</p>') + "</section>";
  }

  function newArticle() {
    var a = { id: uid("a"), slug: "", title: "", dek: "", category: (S.data.categories[0] || {}).id || "", date: today(), author: S.data.site.author || "", cover: "", coverCaption: "", body: "", featured: false, status: "draft" };
    S.data.articles.unshift(a);
    S.editing = a.id; S.slugTouched = false;
    renderMain(); dirty();
    var t = $("#main [data-f=title]"); if (t) t.focus();
  }
  function current() { return S.data.articles.find(function (a) { return a.id === S.editing; }); }

  function editorView() {
    var a = current();
    if (!a) { S.editing = null; return articlesView(); }
    return '<div style="display:flex;justify-content:space-between;gap:10px;margin-bottom:14px;flex-wrap:wrap">' +
      '<button class="b" data-act="back">← All articles</button><div style="display:flex;gap:8px">' +
      '<button class="b danger" data-act="delete-article">Delete</button><button class="b primary" data-act="back">Done</button></div></div>' +
      '<div class="editor"><section class="panel">' +
      '<label class="field"><span>Title</span><input type="text" class="title-in" data-f="title" value="' + esc(a.title) + '" placeholder="A morning at the brocante"></label>' +
      '<label class="field"><span>Subtitle</span><input type="text" data-f="dek" value="' + esc(a.dek) + '" placeholder="One line that makes people want to read on"></label>' +
      '<div class="row"><label class="field"><span>Category</span><select data-f="category">' +
      S.data.categories.map(function (c) { return '<option value="' + esc(c.id) + '"' + (c.id === a.category ? " selected" : "") + ">" + esc(c.name) + "</option>"; }).join("") + "</select></label>" +
      '<label class="field"><span>Date</span><input type="date" data-f="date" value="' + esc(a.date) + '"></label>' +
      '<label class="field"><span>Author</span><input type="text" data-f="author" value="' + esc(a.author || "") + '"></label></div>' +
      '<div class="field"><span>Cover photo</span><div class="cover-pick">' + imgTag(a.cover, "") +
      '<div style="display:grid;gap:8px"><button class="b sm" data-act="pick-cover">Choose or upload…</button>' +
      (a.cover ? '<button class="b sm ghost" data-act="clear-cover">Remove</button>' : "") + "</div></div></div>" +
      '<label class="field"><span>Story</span><div class="toolbar">' +
      '<button data-md="h2" title="Heading">Heading</button><button data-md="h3" title="Small heading">Subheading</button>' +
      '<button data-md="b" title="Bold"><b>B</b></button><button data-md="i" title="Italic"><i>I</i></button>' +
      '<button data-md="quote">“ Quote</button><button data-md="list">• List</button><button data-md="link">Link</button>' +
      '<button data-md="photo">+ Photo</button></div>' +
      '<textarea data-f="body" id="body" placeholder="Write your story here. Leave an empty line between paragraphs.">' + esc(a.body) + "</textarea>" +
      "<small>Leave an empty line between paragraphs. Use the buttons above for headings, quotes and photos.</small></label>" +
      '<div class="row"><label class="check"><input type="checkbox" data-f="published"' + (a.status !== "draft" ? " checked" : "") + "> Published on the site</label>" +
      '<label class="check"><input type="checkbox" data-f="featured"' + (a.featured ? " checked" : "") + "> Feature on the home page</label></div>" +
      '<details><summary class="note" style="cursor:pointer">Web address</summary><label class="field" style="margin-top:10px"><span>Article address</span>' +
      '<input type="text" data-f="slug" value="' + esc(a.slug) + '"><small>The story will be at …/index.html#/article/<b id="slug-show">' + esc(a.slug) + "</b></small></label></details>" +
      '</section><aside class="preview"><div class="preview-label">Preview</div><div id="preview"></div></aside></div>';
  }

  function updatePreview() {
    var a = current(), p = $("#preview");
    if (!a || !p) return;
    p.innerHTML = (a.cover ? '<div class="ph">' + imgTag(a.cover, "") + "</div>" : "") +
      '<header class="article-head"><span class="kicker">' + esc(cat(a.category).name) + "</span><h1>" + esc(a.title || "Untitled") + "</h1>" +
      (a.dek ? '<p class="dek">' + esc(a.dek) + "</p>" : "") + '<div class="meta">' + [a.author ? "By " + esc(a.author) : "", esc(M.fmtDate(a.date)), M.readingTime(a.body)].filter(Boolean).join(" · ") + "</div></header>" +
      '<article class="prose">' + M.md(a.body, src) + "</article>";
  }

  function uniqueSlug(base, id) {
    var s = base || "article", n = 2;
    while (S.data.articles.some(function (a) { return a.slug === s && a.id !== id; })) s = base + "-" + n++;
    return s;
  }

  function onArticleInput(el) {
    var a = current(), f = el.getAttribute("data-f");
    if (!a) return;
    if (f === "published") a.status = el.checked ? "published" : "draft";
    else if (f === "featured") {
      a.featured = el.checked;
      if (el.checked) S.data.articles.forEach(function (x) { if (x !== a) x.featured = false; });
    } else if (f === "slug") { a.slug = M.slugify(el.value); S.slugTouched = true; }
    else a[f] = el.value;
    if (f === "title" && (!S.slugTouched || !a.slug)) a.slug = uniqueSlug(M.slugify(a.title), a.id);
    var ss = $("#slug-show"); if (ss) ss.textContent = a.slug;
    var si = $("[data-f=slug]"); if (si && f !== "slug") si.value = a.slug;
    updatePreview(); dirty();
  }

  function mdInsert(kind) {
    var ta = $("#body"); if (!ta) return;
    var s = ta.selectionStart, e = ta.selectionEnd, v = ta.value, sel = v.slice(s, e);
    var before = v.slice(0, s), after = v.slice(e), ins;
    var block = function (txt) { return (before && !/\n\n$/.test(before) ? (/\n$/.test(before) ? "\n" : "\n\n") : "") + txt + (after && !/^\n\n/.test(after) ? "\n\n" : ""); };
    if (kind === "b") ins = "**" + (sel || "bold text") + "**";
    else if (kind === "i") ins = "*" + (sel || "italic text") + "*";
    else if (kind === "h2") ins = block("## " + (sel || "Heading"));
    else if (kind === "h3") ins = block("### " + (sel || "Subheading"));
    else if (kind === "quote") ins = block("> " + (sel || "A line worth repeating"));
    else if (kind === "list") ins = block((sel || "First item\nSecond item").split("\n").map(function (l) { return "- " + l; }).join("\n"));
    else if (kind === "link") {
      var url = prompt("Link address (https://…)"); if (!url) return;
      ins = "[" + (sel || "link text") + "](" + url.trim() + ")";
    } else if (kind === "photo") {
      pickPhoto(function (ph) {
        var t = block("![" + (ph.caption || "").replace(/[\[\]]/g, "") + "](" + ph.src + ")");
        ta.value = before + t + after; ta.focus(); onArticleInput(ta);
      });
      return;
    }
    ta.value = before + ins + after;
    ta.focus(); ta.selectionStart = ta.selectionEnd = before.length + ins.length;
    onArticleInput(ta);
  }

  /* ---------------- photo picker ---------------- */
  function pickPhoto(cb) {
    var m = document.createElement("div");
    m.className = "modal";
    function draw() {
      m.innerHTML = '<div class="box"><h2>Choose a photo</h2>' +
        '<label class="drop" id="pick-drop"><input type="file" accept="image/*" multiple hidden id="pick-file"><strong>Upload new photos</strong>, or drop them here</label>' +
        '<div class="picker">' + S.data.photos.map(function (p, i) { return '<button data-i="' + i + '" title="' + esc(p.caption) + '">' + imgTag(p.src, p.caption) + "</button>"; }).join("") + "</div>" +
        '<div class="acts"><button class="b" data-close>Cancel</button></div></div>';
    }
    draw();
    document.body.appendChild(m);
    function close() { m.remove(); }
    function uploaded(list) { if (list.length) { close(); cb(list[0]); renderMain(); } }
    m.addEventListener("click", function (e) {
      if (e.target === m || e.target.closest("[data-close]")) return close();
      var b = e.target.closest(".picker button");
      if (b) { close(); cb(S.data.photos[+b.getAttribute("data-i")]); }
    });
    m.addEventListener("change", function (e) { if (e.target.id === "pick-file") addFiles(e.target.files).then(uploaded); });
    dropZone(m, function (files) { addFiles(files).then(uploaded); });
  }

  function dropZone(scope, onFiles) {
    scope.addEventListener("dragover", function (e) { var d = e.target.closest(".drop"); if (d) { e.preventDefault(); d.classList.add("over"); } });
    scope.addEventListener("dragleave", function (e) { var d = e.target.closest(".drop"); if (d) d.classList.remove("over"); });
    scope.addEventListener("drop", function (e) {
      var d = e.target.closest(".drop"); if (!d) return;
      e.preventDefault(); d.classList.remove("over"); onFiles(e.dataTransfer.files);
    });
  }

  /* ---------------- photos tab ---------------- */
  function usage(srcPath) {
    var n = S.data.articles.filter(function (a) { return a.cover === srcPath || (a.body || "").indexOf("](" + srcPath + ")") > -1; }).length;
    if (S.data.site.aboutPhoto === srcPath) n++;
    S.data.categories.forEach(function (c) { if (c.photo === srcPath) n++; });
    return n;
  }
  function photosView() {
    return '<section class="panel"><div class="panel-head"><h2>Photos</h2><span class="note">Photos marked “Gallery” appear on the Gallery page.</span></div>' +
      '<label class="drop"><input type="file" accept="image/*" multiple hidden id="photo-file"><strong>Click to upload photos</strong>, or drop them here.<br><span class="note">Large photos are resized to 2000 px automatically.</span></label>' +
      '<div class="pgrid">' + S.data.photos.map(function (p, i) {
        var used = usage(p.src);
        return '<div class="pcard"><div class="img">' + imgTag(p.src, p.caption) + (S.pending[p.src] ? '<span class="pill warn">Not published yet</span>' : "") + "</div>" +
          '<div class="body"><input type="text" data-p="caption" data-i="' + i + '" value="' + esc(p.caption) + '" placeholder="Caption">' +
          '<input type="text" data-p="credit" data-i="' + i + '" value="' + esc(p.credit || "") + '" placeholder="Photo credit (optional)">' +
          '<div class="foot"><label class="check"><input type="checkbox" data-p="gallery" data-i="' + i + '"' + (p.gallery !== false ? " checked" : "") + "> Gallery</label>" +
          '<span class="note">' + (used ? "Used " + used + "×" : "") + '</span><button class="b sm danger" data-act="delete-photo" data-i="' + i + '">Delete</button></div></div></div>';
      }).join("") + "</div></section>";
  }
  function deletePhoto(i) {
    var p = S.data.photos[i], used = usage(p.src);
    if (!confirm(used ? "This photo is used in " + used + " place(s). Delete it anyway? Those places will show no photo." : "Delete this photo?")) return;
    S.data.photos.splice(i, 1);
    if (S.pending[p.src]) delete S.pending[p.src];
    else if (S.committed[p.src] && /^photos\//.test(p.src)) S.deletes[repoPath(p.src)] = true;
    renderMain();
  }

  /* ---------------- settings ---------------- */
  function settingsView() {
    var s = S.data.site;
    var f = function (key, label, ph, type, help) {
      return '<label class="field"><span>' + label + '</span><input type="' + (type || "text") + '" data-s="' + key + '" value="' + esc(s[key] || "") + '" placeholder="' + esc(ph || "") + '">' + (help ? "<small>" + help + "</small>" : "") + "</label>";
    };
    return '<section class="panel"><div class="panel-head"><h2>Site settings</h2></div>' +
      '<div class="row">' + f("name", "Site name", "Maison de Campagne") + f("tagline", "Tagline", "French country living") + "</div>" +
      '<label class="field"><span>Short description</span><textarea data-s="description" rows="2">' + esc(s.description || "") + "</textarea><small>Shown in the footer.</small></label>" +
      '<div class="row">' + f("author", "Default author", "Your name") + f("email", "Contact email", "", "email") + f("instagram", "Instagram link", "https://instagram.com/…", "url") + "</div>" +
      '<div class="row">' + f("quote", "Home page quote", "") + f("quoteBy", "Quote by", "") + "</div>" +
      f("galleryIntro", "Gallery introduction", "") +
      "</section>" +
      '<section class="panel"><div class="panel-head"><h2>About page</h2></div>' +
      f("aboutTitle", "Title", "About") +
      '<div class="field"><span>Photo</span><div class="cover-pick">' + imgTag(s.aboutPhoto, "") + '<button class="b sm" data-act="pick-about">Choose or upload…</button></div></div>' +
      '<label class="field"><span>Text</span><textarea data-s="about" rows="10">' + esc(s.about || "") + "</textarea><small>Same formatting as articles: empty line between paragraphs, ## for headings.</small></label></section>" +
      '<section class="panel"><div class="panel-head"><h2>Categories</h2><button class="b sm" data-act="add-cat">+ Add category</button></div>' +
      '<p class="note">These appear in the menu. Click a picture to change it.</p>' +
      S.data.categories.map(function (c, i) {
        return '<div class="cat-row"><span data-act="pick-cat" data-i="' + i + '">' + imgTag(c.photo, c.name) + "</span>" +
          '<input type="text" data-c="name" data-i="' + i + '" value="' + esc(c.name) + '" placeholder="Name">' +
          '<input type="text" data-c="blurb" data-i="' + i + '" value="' + esc(c.blurb || "") + '" placeholder="Short description">' +
          '<button class="b sm danger" data-act="del-cat" data-i="' + i + '">Remove</button></div>';
      }).join("") + "</section>" +
      (S.mode === "github" ? '<section class="panel"><div class="panel-head"><h2>Connection</h2></div><p class="note">Publishing to <b>' + esc(S.cfg.repo) + "</b>, branch <b>" + esc(S.branch) + "</b>, folder <b>" + esc(S.cfg.folder || "(root)") + "</b>. Sign out to change these.</p></section>" : "");
  }

  /* ---------------- help ---------------- */
  function helpView() {
    return '<section class="panel help"><div class="panel-head"><h2>How it works</h2></div>' +
      "<p>Everything you change here is a draft until you click <b>Publish</b>. Publishing saves all your changes (articles, new photos and settings) to GitHub in one go, and the public site updates within a minute or two.</p>" +
      "<h3>Writing an article</h3><ol><li>Go to <b>Articles</b> and click <b>New article</b>.</li><li>Add a title, a cover photo and your story. The preview on the right shows how it will look.</li><li>Tick <b>Published on the site</b> when it is ready. Leave it unticked to keep it as a private draft.</li><li>Click <b>Publish</b> at the top.</li></ol>" +
      "<h3>Formatting</h3><pre>## A heading\n### A smaller heading\n**bold**   *italic*\n> A quote\n- a list item\n[link text](https://example.com)\n![Photo caption](photos/uploads/my-photo.jpg)</pre>" +
      "<h3>Photos</h3><p>Upload photos in the <b>Photos</b> tab or straight from the article editor. They are resized automatically. Add a caption, and a credit if the photo isn't yours.</p>" +
      "<h3>If someone else edits at the same time</h3><p>If the site was published from another device since you opened the admin, you'll be asked before your version replaces it.</p></section>";
  }

  /* ---------------- publish ---------------- */
  function publish() {
    var n = changes(); if (!n) return;
    var m = document.createElement("div");
    m.className = "modal";
    m.innerHTML = '<div class="box small"><h2>Publish changes</h2><p class="note">' + summary() + "</p>" +
      '<label class="field"><span>Note for the history (optional)</span><input type="text" id="cmsg" placeholder="e.g. New article about the garden in spring"></label>' +
      '<p id="pstatus" class="note"></p><div class="acts"><button class="b" data-close>Cancel</button><button class="b primary" id="go">Publish now</button></div></div>';
    document.body.appendChild(m);
    m.addEventListener("click", function (e) { if (e.target === m || e.target.closest("[data-close]")) m.remove(); });
    $("#go", m).onclick = function () {
      var go = this, st = $("#pstatus", m);
      go.disabled = true;
      var msg = ($("#cmsg", m).value || "").trim() || "Update site from admin";
      doPublish(msg, function (t) { st.textContent = t; })
        .then(function () { m.remove(); renderMain(); toast("Published. The live site updates in a minute or two."); })
        .catch(function (e) { st.innerHTML = '<span class="err" style="display:block">' + esc(e.message) + "</span>"; go.disabled = false; });
    };
  }
  function summary() {
    var parts = [], up = Object.keys(S.pending).length, del = Object.keys(S.deletes).length;
    if (json() !== S.base) parts.push("articles, photo details or settings changed");
    if (up) parts.push(up + " new photo" + (up > 1 ? "s" : ""));
    if (del) parts.push(del + " photo" + (del > 1 ? "s" : "") + " removed");
    return "This will publish: " + parts.join(", ") + ".";
  }
  function doPublish(message, status) {
    var repo = "/repos/" + S.cfg.repo, headSha, treeSha, newJson = json();
    status("Checking for changes made elsewhere…");
    return fetchRemoteJson().then(function (remote) {
      if (remote !== S.base && !confirm("The site was published from somewhere else since you opened the admin. Publishing now replaces those changes with yours. Continue?")) {
        throw new Error("Publishing cancelled. Sign out and back in to load the latest version, then make your changes again.");
      }
      return gh("GET", repo + "/git/ref/heads/" + encPath(S.branch));
    }).then(function (ref) {
      headSha = ref.object.sha;
      return gh("GET", repo + "/git/commits/" + headSha);
    }).then(function (commit) {
      treeSha = commit.tree.sha;
      var paths = Object.keys(S.pending), entries = [], i = 0;
      return paths.reduce(function (p, path) {
        return p.then(function () {
          status("Uploading photo " + (++i) + " of " + paths.length + "…");
          return gh("POST", repo + "/git/blobs", { content: S.pending[path].b64, encoding: "base64" }).then(function (b) {
            entries.push({ path: repoPath(path), mode: "100644", type: "blob", sha: b.sha });
          });
        });
      }, Promise.resolve()).then(function () {
        status("Saving content…");
        return gh("POST", repo + "/git/blobs", { content: newJson, encoding: "utf-8" });
      }).then(function (b) {
        entries.push({ path: repoPath("content/site.json"), mode: "100644", type: "blob", sha: b.sha });
        Object.keys(S.deletes).forEach(function (p) { entries.push({ path: p, mode: "100644", type: "blob", sha: null }); });
        return gh("POST", repo + "/git/trees", { base_tree: treeSha, tree: entries });
      });
    }).then(function (tree) {
      status("Creating the update…");
      return gh("POST", repo + "/git/commits", { message: message, tree: tree.sha, parents: [headSha] });
    }).then(function (c) {
      return gh("PATCH", repo + "/git/refs/heads/" + encPath(S.branch), { sha: c.sha, force: false });
    }).then(function () {
      Object.keys(S.pending).forEach(function (p) { S.committed[p] = true; S.cache[p] = S.pending[p].url; });
      Object.keys(S.deletes).forEach(function (p) { delete S.committed[p]; });
      S.pending = {}; S.deletes = {}; S.base = newJson;
    });
  }

  function download() {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([json()], { type: "application/json" }));
    a.download = "site.json"; a.click();
    if (Object.keys(S.pending).length) alert("Note: photos uploaded in preview mode are not included in site.json. Connect with GitHub to publish photos.");
  }

  /* ---------------- events ---------------- */
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-act],[data-tab],[data-md]");
    if (!t || !S.data) return;
    if (t.hasAttribute("data-tab")) { S.tab = t.getAttribute("data-tab"); S.editing = null; renderMain(); window.scrollTo(0, 0); return; }
    if (t.hasAttribute("data-md")) { e.preventDefault(); mdInsert(t.getAttribute("data-md")); return; }
    var act = t.getAttribute("data-act"), i = +t.getAttribute("data-i");
    switch (act) {
      case "new-article": newArticle(); break;
      case "edit": S.editing = t.getAttribute("data-id"); S.slugTouched = true; renderMain(); window.scrollTo(0, 0); break;
      case "back": S.editing = null; renderMain(); break;
      case "delete-article":
        if (confirm("Delete this article? It disappears from the site when you publish.")) {
          S.data.articles = S.data.articles.filter(function (a) { return a.id !== S.editing; });
          S.editing = null; renderMain();
        }
        break;
      case "pick-cover": pickPhoto(function (p) { current().cover = p.src; renderMain(); }); break;
      case "clear-cover": current().cover = ""; renderMain(); break;
      case "pick-about": pickPhoto(function (p) { S.data.site.aboutPhoto = p.src; renderMain(); }); break;
      case "pick-cat": pickPhoto(function (p) { S.data.categories[i].photo = p.src; renderMain(); }); break;
      case "add-cat":
        var name = prompt("Name of the new category"); if (!name) return;
        var id = M.slugify(name), n = 2, base = id;
        while (S.data.categories.some(function (c) { return c.id === id; })) id = base + "-" + n++;
        S.data.categories.push({ id: id, name: name.trim(), blurb: "", photo: "" }); renderMain(); break;
      case "del-cat":
        var c = S.data.categories[i], used = S.data.articles.filter(function (a) { return a.category === c.id; }).length;
        if (used) { alert(used + " article(s) use “" + c.name + "”. Move them to another category first."); return; }
        if (confirm("Remove the category “" + c.name + "”?")) { S.data.categories.splice(i, 1); renderMain(); }
        break;
      case "delete-photo": deletePhoto(i); break;
      case "publish": publish(); break;
      case "download": download(); break;
      case "signout":
        if (changes() && !confirm("You have unpublished changes. Sign out and lose them?")) return;
        setSaved(TOKEN_KEY, null); S.data = null; window.onbeforeunload = null; location.reload(); break;
    }
  });

  document.addEventListener("input", function (e) {
    var el = e.target;
    if (!S.data) return;
    if (el.hasAttribute("data-f")) return onArticleInput(el);
    if (el.getAttribute("data-bind") === "filter") {
      S.filter = el.value; var pos = el.selectionStart; renderMain();
      var f = $("[data-bind=filter]"); f.focus(); f.selectionStart = f.selectionEnd = pos; return;
    }
    if (el.hasAttribute("data-s")) { S.data.site[el.getAttribute("data-s")] = el.value; dirty(); return; }
    if (el.hasAttribute("data-c")) { S.data.categories[+el.getAttribute("data-i")][el.getAttribute("data-c")] = el.value; dirty(); return; }
    if (el.hasAttribute("data-p")) {
      var p = S.data.photos[+el.getAttribute("data-i")], k = el.getAttribute("data-p");
      p[k] = k === "gallery" ? el.checked : el.value; dirty();
    }
  });
  document.addEventListener("change", function (e) {
    if (e.target.id === "photo-file") addFiles(e.target.files).then(function () { renderMain(); });
    else if (e.target.matches("select[data-f], input[type=checkbox][data-f], input[type=date][data-f]")) onArticleInput(e.target);
    else if (e.target.matches("input[type=checkbox][data-p]")) { S.data.photos[+e.target.getAttribute("data-i")].gallery = e.target.checked; dirty(); }
  });

  window.addEventListener("beforeunload", function (e) {
    if (S.data && changes()) { e.preventDefault(); e.returnValue = ""; }
  });

  /* ---------------- start ---------------- */
  function start(data, base) {
    S.data = data;
    ["articles", "photos", "categories"].forEach(function (k) { if (!Array.isArray(S.data[k])) S.data[k] = []; });
    S.data.site = S.data.site || {};
    S.base = base;
    S.data.photos.forEach(function (p) { S.committed[p.src] = true; });
    renderApp();
    dropZone(root, function (files) { addFiles(files).then(function () { renderMain(); }); });
  }

  function loginView(err) {
    var cfg = detectCfg();
    root.innerHTML = '<div class="login"><div class="panel"><span class="kicker">Admin</span><h1>Sign in to publish</h1>' +
      '<p class="note">The admin saves your articles and photos straight to the site’s GitHub repository. Sign in with a GitHub access token that may edit it.</p>' +
      (err ? '<p class="err">' + esc(err) + "</p>" : "") +
      '<form id="login"><label class="field"><span>GitHub access token</span><input type="password" id="tok" autocomplete="current-password" placeholder="github_pat_…" required></label>' +
      '<details><summary>How do I get a token?</summary><ol style="margin-top:10px">' +
      '<li>On GitHub, open <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">Settings → Developer settings → Fine-grained tokens → Generate new token</a>.</li>' +
      "<li>Give it a name (for example “Site admin”) and an expiry date.</li>" +
      "<li>Under <b>Repository access</b>, choose <b>Only select repositories</b> and pick <b>" + esc(cfg.repo.split("/")[1] || "your repository") + "</b>.</li>" +
      "<li>Under <b>Permissions → Repository permissions</b>, set <b>Contents</b> to <b>Read and write</b>.</li>" +
      "<li>Generate the token, copy it and paste it here. Treat it like a password.</li></ol></details>" +
      '<details><summary>Repository settings</summary><div style="margin-top:10px">' +
      '<label class="field"><span>Repository</span><input type="text" id="repo" value="' + esc(cfg.repo) + '"><small>owner/name</small></label>' +
      '<label class="field"><span>Branch</span><input type="text" id="branch" value="' + esc(cfg.branch) + '" placeholder="(the repository’s default branch)"></label>' +
      '<label class="field"><span>Site folder</span><input type="text" id="folder" value="' + esc(cfg.folder) + '"></label></div></details>' +
      '<label class="check"><input type="checkbox" id="remember"> Keep me signed in on this device</label>' +
      '<div style="display:flex;gap:10px;flex-wrap:wrap"><button class="b primary" type="submit" id="go">Sign in</button>' +
      '<button class="b" type="button" id="local">Try it without publishing</button></div></form></div>' +
      '<p class="note" style="text-align:center;margin-top:16px"><a href="index.html">← Back to the site</a></p></div>';

    $("#local").onclick = function () {
      S.mode = "local"; S.cfg = cfg; S.branch = "";
      fetch("content/site.json", { cache: "no-cache" }).then(function (r) { if (!r.ok) throw 0; return r.text(); })
        .then(function (t) { start(JSON.parse(t), t); })
        .catch(function () { loginView("Couldn't read content/site.json. Preview mode needs the admin to be opened from the website itself."); });
    };
    $("#login").onsubmit = function (e) {
      e.preventDefault();
      var go = $("#go"); go.disabled = true; go.textContent = "Signing in…";
      var c = { repo: $("#repo").value.trim().replace(/^https:\/\/github\.com\//, "").replace(/\.git$|\/$/g, ""), branch: $("#branch").value.trim(), folder: $("#folder").value.trim().replace(/^\/+|\/+$/g, "") };
      connect($("#tok").value.trim(), c, $("#remember").checked).catch(function (er) { loginView(er.message); });
    };
  }

  function connect(token, cfg, remember) {
    S.token = token; S.cfg = cfg; S.mode = "github";
    return gh("GET", "/repos/" + cfg.repo).then(function (r) {
      if (r.permissions && !r.permissions.push) throw new Error("This token can read the repository but not change it. Give it “Contents: Read and write” permission.");
      S.branch = cfg.branch || r.default_branch;
      return fetchRemoteJson();
    }).then(function (text) {
      setSaved(TOKEN_KEY, token, remember);
      setSaved(CFG_KEY, JSON.stringify(cfg), true);
      start(JSON.parse(text), text);
    });
  }

  var saved = getSaved(TOKEN_KEY);
  if (saved) {
    root.innerHTML = '<p class="note" style="text-align:center;margin-top:20vh">Loading…</p>';
    connect(saved, detectCfg(), !!(store("localStorage") && (function () { try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; } })()))
      .catch(function (e) { setSaved(TOKEN_KEY, null); loginView(e.message); });
  } else loginView();
})();
