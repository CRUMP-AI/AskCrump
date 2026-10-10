/*
 * Ask Crump — Director's Cut · Library view (1.0)
 *
 * Registers the 'library' view on window.CrumpVision. The bookshelf is fed by
 * the real Library API: GET /api/library/books for the shelf, and
 * GET /api/manuscripts/:id for the reading overlay. Nothing here is seeded or
 * invented — an empty Library shows the designed empty state, and the
 * "version history" expander shows the honest record (Crump keeps the current
 * version of each keepsake; earlier revisions are not stored).
 *
 * Defensive by design: if CrumpVision is not ready yet, registration retries
 * until it is. All markup is escaped; all events are bound with
 * addEventListener (no inline handlers). This view only reads — it never
 * writes to any existing library or project store.
 */
(function () {
  'use strict';

  if (window.__cvLibraryRegistered) return;
  window.__cvLibraryRegistered = true;

  function cv() {
    return window.CrumpVision || null;
  }

  function esc(value) {
    var c = cv();
    if (c && typeof c.esc === 'function') return c.esc(value);
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function eyebrowHTML(text) {
    var c = cv();
    if (c && typeof c.eyebrow === 'function') {
      try {
        var out = c.eyebrow(text);
        if (typeof out === 'string' && out) return out;
      } catch (_) { /* fall through to local markup */ }
    }
    return '<div class="cv-eyebrow">' + esc(text) + '</div>';
  }

  function fmtDate(value) {
    if (!value) return '';
    var d = new Date(value);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function fmtCount(value) {
    var n = Number(value || 0);
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'm';
    if (n >= 1000) return Math.round(n / 1000) + 'k';
    return String(n);
  }

  function capitalize(value) {
    var s = String(value || '');
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
  }

  function fileExtension(name) {
    var match = /\.([a-z0-9]{2,5})$/i.exec(String(name || ''));
    return match ? match[1].toUpperCase() : '';
  }

  async function api(path) {
    var response = await fetch(path, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
    var data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok || data.success === false) {
      var error = new Error(data.error || data.message || 'Request failed (' + response.status + ')');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function bookInitial(title) {
    var t = String(title || '').trim();
    return t ? t.charAt(0).toUpperCase() : 'A';
  }

  function bookMatches(book, needle) {
    if (!needle) return true;
    var haystack = [
      book.title, book.subtitle, book.authorName, book.projectName,
      book.sourceFile && book.sourceFile.name, book.origin, book.status,
    ].join(' ').toLowerCase();
    return haystack.indexOf(needle) !== -1;
  }

  function bookCardHTML(book) {
    var id = esc(book.id);
    var title = esc(book.title || 'Untitled manuscript');
    var author = esc(book.authorName || 'Ask Crump Library');
    var origin = book.origin === 'imported' ? 'Imported' : 'Created in Crump';
    var status = capitalize(book.status || 'draft');
    var ext = fileExtension(book.sourceFile && book.sourceFile.name);
    var updated = fmtDate(book.updatedAt);
    var created = fmtDate(book.createdAt);
    var words = fmtCount(book.wordCount) + ' words';
    var sections = Number(book.sectionCount || 0) + (Number(book.sectionCount || 0) === 1 ? ' section' : ' sections');

    return (
      '<article class="cvl-book" data-cvl-book="' + id + '">' +
        '<div class="cvl-cover" aria-hidden="true">' +
          '<span class="cvl-cover-initial">' + esc(bookInitial(book.title)) + '</span>' +
          '<span class="cvl-cover-spine"></span>' +
        '</div>' +
        '<div class="cvl-book-body">' +
          '<div class="cvl-book-top">' +
            '<span class="cvl-type-chip">' + esc(origin) + (ext ? ' · ' + esc(ext) : '') + '</span>' +
            '<span class="cvl-version-pill" title="Current status">' + esc(status) + '</span>' +
          '</div>' +
          '<h3 class="cvl-book-title" title="' + title + '">' + title + '</h3>' +
          '<p class="cvl-book-author">' + author + '</p>' +
          '<p class="cvl-book-meta">' + esc(words) + ' · ' + esc(sections) +
            (updated ? ' · Updated ' + esc(updated) : '') + '</p>' +
          '<details class="cvl-history">' +
            '<summary>Version history</summary>' +
            '<div class="cvl-history-body">' +
              '<div class="cvl-history-row"><span>Current version</span><time>' + esc(updated || '—') + '</time></div>' +
              (created ? '<div class="cvl-history-row"><span>Added to Library</span><time>' + esc(created) + '</time></div>' : '') +
              '<p class="cvl-history-note">Crump keeps the current version of each keepsake. Earlier revisions are not stored.</p>' +
            '</div>' +
          '</details>' +
          '<button type="button" class="cvl-open" data-cvl-open="' + id + '">Open</button>' +
        '</div>' +
      '</article>'
    );
  }

  /* ------------------------------------------------------------------ */
  /* Document viewer overlay — reads the real manuscript sections.      */
  /* ------------------------------------------------------------------ */

  function paragraphsHTML(content) {
    var value = String(content || '').replace(/\r\n?/g, '\n').trim();
    if (!value) return '<p class="cvl-reader-empty">This section does not have readable text yet.</p>';
    return value.split(/\n{2,}/).map(function (paragraph) {
      return '<p>' + esc(paragraph).replace(/\n/g, '<br>') + '</p>';
    }).join('');
  }

  function openReader(book) {
    var previousFocus = document.activeElement;

    var overlay = document.createElement('div');
    overlay.className = 'cvl-overlay';
    overlay.setAttribute('role', 'presentation');
    overlay.innerHTML =
      '<section class="cvl-sheet" role="dialog" aria-modal="true" aria-label="Read ' + esc(book.title || 'manuscript') + '">' +
        '<header class="cvl-sheet-head">' +
          '<div>' +
            '<div class="cv-eyebrow">READING</div>' +
            '<h3>' + esc(book.title || 'Untitled manuscript') + '</h3>' +
            '<p>' + esc(book.authorName || 'Ask Crump Library') + '</p>' +
          '</div>' +
          '<button type="button" class="cvl-close" data-cvl-close aria-label="Close reader">×</button>' +
        '</header>' +
        '<div class="cvl-reader-loading" data-cvl-loading>' +
          '<strong>Opening book…</strong>' +
          '<span>Crump is preparing the manuscript for reading.</span>' +
        '</div>' +
      '</section>';

    function close() {
      document.removeEventListener('keydown', onKey, true);
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      if (previousFocus && typeof previousFocus.focus === 'function') {
        try { previousFocus.focus(); } catch (_) { /* best effort */ }
      }
    }

    function onKey(event) {
      if (event.key === 'Escape') close();
    }

    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) close();
    });
    overlay.querySelector('[data-cvl-close]').addEventListener('click', close);
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(overlay);
    var closeButton = overlay.querySelector('[data-cvl-close]');
    if (closeButton) closeButton.focus();

    api('/api/manuscripts/' + encodeURIComponent(book.id)).then(function (data) {
      if (!overlay.isConnected) return;
      var sections = Array.isArray(data.sections) ? data.sections : [];
      var loading = overlay.querySelector('[data-cvl-loading]');
      var sheet = overlay.querySelector('.cvl-sheet');
      if (!sheet || !loading) return;

      if (!sections.length) {
        loading.innerHTML =
          '<strong>No readable sections yet.</strong>' +
          '<span>This keepsake exists in your Library, but it does not have any sections to read yet.</span>';
        return;
      }

      loading.parentNode.removeChild(loading);

      var reader = document.createElement('div');
      reader.className = 'cvl-reader';
      reader.innerHTML =
        '<nav class="cvl-reader-nav" aria-label="Book sections">' +
          '<p class="cvl-reader-nav-head">' + sections.length + (sections.length === 1 ? ' section' : ' sections') + '</p>' +
          '<div class="cvl-reader-nav-list" role="list">' +
            sections.map(function (section, index) {
              return (
                '<button type="button" role="listitem" data-cvl-section="' + index + '"' + (index === 0 ? ' class="is-active"' : '') + '>' +
                  '<small>' + String(index + 1).padStart(2, '0') + '</small>' +
                  '<span>' + esc(section.title || ('Section ' + (index + 1))) + '</span>' +
                '</button>'
              );
            }).join('') +
          '</div>' +
        '</nav>' +
        '<div class="cvl-reader-main" data-cvl-main></div>';
      sheet.appendChild(reader);

      var main = reader.querySelector('[data-cvl-main]');
      var navButtons = Array.prototype.slice.call(reader.querySelectorAll('[data-cvl-section]'));

      function showSection(index) {
        var section = sections[index] || {};
        navButtons.forEach(function (button, i) {
          button.classList.toggle('is-active', i === index);
        });
        main.innerHTML =
          '<h4>' + esc(section.title || ('Section ' + (index + 1))) + '</h4>' +
          paragraphsHTML(section.content);
        main.scrollTop = 0;
      }

      navButtons.forEach(function (button) {
        button.addEventListener('click', function () {
          showSection(Number(button.getAttribute('data-cvl-section')));
        });
      });

      showSection(0);
    }).catch(function (error) {
      if (!overlay.isConnected) return;
      var loading = overlay.querySelector('[data-cvl-loading]');
      if (!loading) return;
      loading.innerHTML =
        '<strong>This book could not open.</strong>' +
        '<span>' + esc(error.message || 'Try again in a moment.') + '</span>' +
        '<button type="button" class="cvl-button" data-cvl-retry>Try again</button>';
      loading.querySelector('[data-cvl-retry]').addEventListener('click', function () {
        close();
        openReader(book);
      });
    });
  }

  /* ------------------------------------------------------------------ */
  /* View render.                                                        */
  /* ------------------------------------------------------------------ */

  function renderLibraryView(root) {
    if (!root) return;
    root.innerHTML = '';
    root.className = 'cvl-root';

    var header = document.createElement('div');
    header.className = 'cvl-header';
    header.innerHTML =
      eyebrowHTML('YOUR WORK HAS A HOME') +
      '<h1 class="cvl-title">Library</h1>' +
      '<p class="cvl-lede">Every keepsake finished with Crump — documents, decks, and manuscripts — lives here, ready to reopen, read, and share.</p>';
    root.appendChild(header);

    var toolbar = document.createElement('div');
    toolbar.className = 'cvl-toolbar';
    toolbar.innerHTML =
      '<label class="cvl-search">' +
        '<span class="cvl-search-icon" aria-hidden="true">' +
          '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5"/><path d="M11 11l3.2 3.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>' +
        '</span>' +
        '<input type="search" data-cvl-search placeholder="Search your library…" aria-label="Search your library">' +
      '</label>' +
      '<p class="cvl-count" data-cvl-count role="status"></p>';
    root.appendChild(toolbar);

    var shelf = document.createElement('div');
    shelf.className = 'cvl-shelf';
    root.appendChild(shelf);

    shelf.innerHTML =
      '<div class="cvl-skeleton" aria-hidden="true"><i></i><i></i><i></i><i></i></div>' +
      '<p class="cvl-status" role="status">Opening your library…</p>';

    // Authenticated data only: never fire workspace API calls for signed-out
    // visitors (they 404 and pollute the console). Demo mode serves fixture
    // data through its own interceptor.
    var authed = Boolean(window.currentUser && window.currentUser.id);
    var demo = window.__crumpVisionDemo === true;
    if (!authed && !demo) {
      shelf.innerHTML =
        '<div class="cvl-panel" role="status">' +
          '<h2>Sign in to open your library.</h2>' +
          '<p>Every keepsake you finish with Crump — documents, decks, and manuscripts — lives here, ready to reopen, read, and share.</p>' +
        '</div>';
      return;
    }

    api('/api/library/books').then(function (data) {
      var books = Array.isArray(data.books) ? data.books : [];
      books.sort(function (a, b) {
        return new Date(b.updatedAt || 0).getTime() - new Date(a.updatedAt || 0).getTime();
      });
      renderShelf(root, shelf, books);
    }).catch(function (error) {
      shelf.innerHTML =
        '<div class="cvl-panel cvl-error" role="alert">' +
          '<h2>The Library could not load.</h2>' +
          '<p>' + esc(error.message || 'Try again in a moment.') + '</p>' +
          '<button type="button" class="cvl-button" data-cvl-retry>Try again</button>' +
        '</div>';
      shelf.querySelector('[data-cvl-retry]').addEventListener('click', function () {
        renderLibraryView(root);
      });
    });
  }

  function renderShelf(root, shelf, books) {
    var search = root.querySelector('[data-cvl-search]');
    var count = root.querySelector('[data-cvl-count]');

    if (!books.length) {
      root.querySelector('.cvl-toolbar').style.display = 'none';
      shelf.innerHTML =
        '<div class="cvl-empty">' +
          '<img class="cvl-empty-mascot" src="/assets/crump-mascot-official.jpg" alt="Crump, the Ask Crump mascot" width="120" height="120">' +
          '<h2>Make something you can keep.</h2>' +
          '<p>Your shelf is empty. When Crump finishes a document, deck, or manuscript with you, it will live here — yours to reopen, read, and share.</p>' +
          '<button type="button" class="cvl-button" data-cvl-chats>Go to Chats</button>' +
        '</div>';
      shelf.querySelector('[data-cvl-chats]').addEventListener('click', goToChats);
      return;
    }

    function paint(needle) {
      var visible = books.filter(function (book) { return bookMatches(book, needle); });
      count.textContent = visible.length + (visible.length === 1 ? ' keepsake' : ' keepsakes');

      if (!visible.length) {
        shelf.innerHTML =
          '<div class="cvl-nomatch">' +
            '<h2>No books match that search.</h2>' +
            '<p>Try a different title, author, or project.</p>' +
          '</div>';
        return;
      }

      shelf.innerHTML =
        '<div class="cvl-grid">' + visible.map(bookCardHTML).join('') + '</div>';

      var byId = {};
      visible.forEach(function (book) { byId[String(book.id)] = book; });
      shelf.querySelectorAll('[data-cvl-open]').forEach(function (button) {
        button.addEventListener('click', function () {
          var book = byId[button.getAttribute('data-cvl-open')];
          if (book) openReader(book);
        });
      });
    }

    var debounce = null;
    search.addEventListener('input', function () {
      if (debounce) clearTimeout(debounce);
      debounce = setTimeout(function () {
        paint(search.value.trim().toLowerCase());
      }, 120);
    });

    paint('');
  }

  function goToChats() {
    var c = cv();
    try {
      if (c && typeof c.navigate === 'function') { c.navigate('chats'); return; }
    } catch (_) { /* fall through */ }
    window.location.href = '/app';
  }

  /* ------------------------------------------------------------------ */
  /* Registration — retries until the CrumpVision shell is ready.        */
  /* ------------------------------------------------------------------ */

  function register() {
    var c = cv();
    if (!c || typeof c.registerView !== 'function') return false;
    try {
      c.registerView('library', { title: 'Library', render: renderLibraryView });
    } catch (_) {
      return false;
    }
    return true;
  }

  var attempts = 0;
  if (!register()) {
    var timer = setInterval(function () {
      attempts += 1;
      if (register() || attempts >= 150) clearInterval(timer);
    }, 200);
  }
})();
