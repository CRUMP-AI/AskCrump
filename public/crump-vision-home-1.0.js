/*
 * Crump Vision — Home screen (1.0)
 *
 * The briefing: a warm greeting row, what's really on the plate (live
 * projects), what's actually waiting (latest keepsakes), and quick actions
 * into the rest of the workspace. Every row below is real data — loading,
 * empty, and error states included. Nothing here is staged.
 * Registered as the vision 'home' view through window.CrumpVision.
 */
(() => {
  'use strict';

  // Briefing requests must never hang the home view: a stuck request used to
  // leave "Loading your projects…" on screen forever. Abort past the timeout
  // and let the caller render an honest error state instead.
  var BRIEFING_TIMEOUT_MS = 15000;

  function captureAuthBoundary() {
    var boundary = window.CrumpAuthBoundary;
    var rawRevision = typeof boundary?.revision === 'function' ? boundary.revision() : 0;
    var revision = Number(rawRevision);
    return Object.freeze({
      ownerId: String(
        typeof boundary?.authenticatedUserId === 'function'
          ? boundary.authenticatedUserId()
          : (window.currentUser && window.currentUser.id) || '',
      ).trim(),
      revision: Number.isFinite(revision) ? revision : 0,
    });
  }

  function authBoundaryIsCurrent(snapshot) {
    if (window.__crumpVisionDemo === true) return true;
    if (!snapshot || !snapshot.ownerId) return false;
    var current = captureAuthBoundary();
    return current.ownerId === snapshot.ownerId && current.revision === snapshot.revision;
  }

  function requestTimeoutError() {
    var error = new Error('The request took too long. Check your connection and try again.');
    error.code = 'REQUEST_TIMEOUT';
    return error;
  }

  function api(path, authBoundary) {
    if (window.__crumpVisionDemo !== true && !authBoundaryIsCurrent(authBoundary)) {
      return Promise.reject(new Error('The signed-in account changed before this request began.'));
    }
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, BRIEFING_TIMEOUT_MS);
    function done() { clearTimeout(timer); }
    return fetch(path, {
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'X-Ask-Crump-Expected-Owner': authBoundary?.ownerId || '',
      },
      signal: controller.signal,
    }).then(function (response) {
      // Two-argument then: the rejection handler covers only response.json()
      // failures. An application-level failure (HTTP 200 with success:false)
      // thrown below must propagate to the caller, not resolve as {}.
      return response.json().then(function (data) {
        done();
        if (!response.ok || data.success === false) {
          var message = (data && (data.error || data.message)) ||
            (!response.ok ? 'Request failed (' + response.status + ')' : 'Request failed');
          throw new Error(message);
        }
        return data || {};
      }, function (err) {
        done();
        if (err && err.name === 'AbortError') throw requestTimeoutError();
        if (!response.ok) throw new Error('Request failed (' + response.status + ')');
        return {};
      });
    }, function (err) {
      done();
      if (err && err.name === 'AbortError') throw requestTimeoutError();
      throw err;
    });
  }

  function fmtDate(value) {
    if (!value) return '';
    var d = new Date(value);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function partOfDay(date) {
    var h = (date || new Date()).getHours();
    if (h >= 5 && h < 12) return 'morning';
    if (h >= 12 && h < 18) return 'afternoon';
    return 'evening';
  }

  function init() {
    var V = window.CrumpVision;
    if (!V || typeof V.registerView !== 'function') return;

    function plateRowsHTML(projects) {
      if (!projects.length) {
        return '<p class="cv-empty">Nothing on your plate. Durable work you save as a Project will land here.</p>';
      }
      return projects.slice(0, 3).map(function (p) {
        var date = fmtDate(p.updated_at);
        return (
          '<div class="cv-plate-row">' +
          '<div class="cv-plate-main"><strong>' + V.esc(p.name || 'Untitled project') + '</strong>' +
          '<small>' + V.esc(p.description || 'Project workspace') + '</small></div>' +
          (date ? '<span class="cv-state cv-state-ivory">' + V.esc(date) + '</span>' : '') +
          '</div>'
        );
      }).join('');
    }

    function nudgeListHTML(books) {
      if (!books.length) {
        return '<p class="cv-empty">You\u2019re all caught up. Nothing needs you right this second.</p>';
      }
      var book = books[0];
      return (
        '<div class="cv-nudge">' +
        '<div class="cv-nudge-main"><strong>' + V.esc('Latest keepsake is in your Library') + '</strong>' +
        '<p>' + V.esc(book.title || 'Untitled') + '</p></div>' +
        '<button type="button" class="cv-nudge-btn" data-cv-nudge="library">' +
        'Open Library <span aria-hidden="true">\u2192</span></button>' +
        '</div>'
      );
    }

    function wireNudges(cardNode) {
      var buttons = cardNode.querySelectorAll('[data-cv-nudge]');
      Array.prototype.forEach.call(buttons, function (button) {
        button.addEventListener('click', function () {
          V.navigate(button.getAttribute('data-cv-nudge') || 'library');
        });
      });
    }

    function greetingSub(projects, books, projectsOk, booksOk) {
      // Failure-aware: a failed section must never be summarized as empty.
      // (Both-failed is handled by unreachableState(); this only sees
      // at-most-one failure.)
      var bits = [];
      bits.push(projectsOk
        ? (projects.length === 1 ? 'One project in motion' : projects.length + ' projects in motion')
        : 'couldn\u2019t check your projects just now');
      bits.push(booksOk
        ? (books.length ? 'your latest keepsake is waiting' : 'nothing waiting on you')
        : 'couldn\u2019t check your library just now');
      return bits.join(', ').replace(/^./, function (c) { return c.toUpperCase(); }) + '.';
    }

    function render(container) {
      container.innerHTML = '';
      var day = partOfDay();

      var root = V.el('<div class="cv-view cv-home"></div>');
      var wrap = V.el('<div class="cv-wrap"></div>');
      wrap.appendChild(V.eyebrow('Your ' + day + ' briefing'));

      var greet = V.el('<div class="cv-home-greet"></div>');
      var greetText = V.el('<div class="cv-home-greet-text"></div>');
      var title = document.createElement('h1');
      title.className = 'cv-home-title';
      title.textContent = 'Good ' + day + ', Greg.';
      var sub = document.createElement('p');
      sub.className = 'cv-sub cv-home-sub';
      sub.textContent = 'Checking what\u2019s in motion\u2026';
      greetText.appendChild(title);
      greetText.appendChild(sub);
      greet.appendChild(greetText);
      wrap.appendChild(greet);

      var grid = V.el('<div class="cv-home-grid"></div>');

      var plate = V.card({
        eyebrow: 'On your plate',
        body: '<div class="cv-plate"><p class="cv-empty" role="status">Loading your projects\u2026</p></div>',
      });
      var plateBody = plate.querySelector('.cv-card-copy');
      plate.classList.add('cv-home-span');
      grid.appendChild(plate);

      var nudges = V.card({
        eyebrow: 'Waiting on you',
        body: '<div class="cv-nudges"><p class="cv-empty" role="status">Checking your library\u2026</p></div>',
      });
      var nudgeBody = nudges.querySelector('.cv-card-copy');
      grid.appendChild(nudges);

      grid.appendChild(
        V.card({
          eyebrow: 'Quick actions',
          title: 'Start something',
          actions: [
            { label: 'New chat', primary: true, onSelect: function () { V.navigate('chats'); } },
            { label: 'New project', onSelect: function () { V.navigate('projects'); } },
            { label: 'Open Library', onSelect: function () { V.navigate('library'); } },
          ],
        })
      );

      wrap.appendChild(grid);
      root.appendChild(wrap);
      container.appendChild(root);

      // Authenticated data only: signed-out visitors get the auth screen, so
      // never fire workspace API calls for them (they 404 and pollute the
      // console). Demo mode serves fixture data through its own interceptor.
      var authed = Boolean(window.currentUser && window.currentUser.id);
      var demo = window.__crumpVisionDemo === true;
      if (!authed && !demo) {
        sub.textContent = 'Sign in to see your briefing.';
        plateBody.innerHTML = '<div class="cv-plate"><p class="cv-empty">Your projects will appear here once you sign in.</p></div>';
        nudgeBody.innerHTML = '<div class="cv-nudges"><p class="cv-empty">Your library will appear here once you sign in.</p></div>';
        return;
      }

      // Each briefing request settles on its own: one slow endpoint must not
      // take the other section down with it, and a failed section renders its
      // own honest state instead of masquerading as empty.
      function settled(promise) {
        return promise.then(
          function (data) { return { ok: true, data: data }; },
          function (error) { return { ok: false, error: error }; }
        );
      }

      function unreachableState() {
        sub.textContent = 'Couldn\u2019t reach your workspace just now.';
        plateBody.innerHTML = '<div class="cv-plate"><p class="cv-empty">Projects couldn\u2019t load. Try again in a moment.</p></div>';
        nudgeBody.innerHTML = '<div class="cv-nudges"><p class="cv-empty">Library couldn\u2019t load. Try again in a moment.</p></div>';
      }

      var authBoundary = captureAuthBoundary();
      Promise.all([
        settled(api('/api/projects', authBoundary)),
        settled(api('/api/library/books', authBoundary)),
      ]).then(function (results) {
        if (!container.isConnected || !authBoundaryIsCurrent(authBoundary)) return;
        var projectsResult = results[0];
        var booksResult = results[1];
        if (!projectsResult.ok && !booksResult.ok) {
          unreachableState();
          return;
        }
        var projects = projectsResult.ok && Array.isArray(projectsResult.data.projects)
          ? projectsResult.data.projects : [];
        var books = booksResult.ok && Array.isArray(booksResult.data.books)
          ? booksResult.data.books : [];
        sub.textContent = greetingSub(projects, books, projectsResult.ok, booksResult.ok);
        plateBody.innerHTML = '<div class="cv-plate">' +
          (projectsResult.ok
            ? plateRowsHTML(projects)
            : '<p class="cv-empty">Projects couldn\u2019t load. Try again in a moment.</p>') +
          '</div>';
        nudgeBody.innerHTML = '<div class="cv-nudges">' +
          (booksResult.ok
            ? nudgeListHTML(books)
            : '<p class="cv-empty">Library couldn\u2019t load. Try again in a moment.</p>') +
          '</div>';
        wireNudges(nudges);
      }).catch(function () {
        // Safety net only: settled() resolves for every request outcome, so
        // reaching here means something unexpected threw during render.
        if (!container.isConnected || !authBoundaryIsCurrent(authBoundary)) return;
        unreachableState();
      });
    }

    V.registerView('home', {
      title: 'Home',
      render: render,
      onShow: function () {},
      onHide: function () {},
    });
  }

  if (window.__crumpVisionShellLoaded) {
    init();
  } else {
    document.addEventListener('crumpvision:ready', init, { once: true });
  }
})();
