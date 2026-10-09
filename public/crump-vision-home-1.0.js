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

  function api(path) {
    return fetch(path, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || data.success === false) {
          throw new Error((data && (data.error || data.message)) || 'Request failed');
        }
        return data || {};
      }).catch(function () {
        if (!response.ok) throw new Error('Request failed (' + response.status + ')');
        return {};
      });
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

    function greetingSub(projects, books) {
      var bits = [];
      bits.push(projects.length === 1 ? 'One project in motion' : projects.length + ' projects in motion');
      if (books.length) bits.push('your latest keepsake is waiting');
      else bits.push('nothing waiting on you');
      return bits.join(', ').replace(/^./, function (c) { return c.toUpperCase(); }) + '.';
    }

    function render(container) {
      container.innerHTML = '';
      var day = partOfDay();

      var root = V.el('<div class="cv-view cv-home"></div>');
      var wrap = V.el('<div class="cv-wrap"></div>');
      wrap.appendChild(V.eyebrow('Your ' + day + ' briefing'));

      var greet = V.el('<div class="cv-home-greet"></div>');
      greet.appendChild(V.mascot(64));
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

      Promise.all([
        api('/api/projects').catch(function () { return {}; }),
        api('/api/library/books').catch(function () { return {}; }),
      ]).then(function (results) {
        var projects = Array.isArray(results[0].projects) ? results[0].projects : [];
        var books = Array.isArray(results[1].books) ? results[1].books : [];
        if (!container.isConnected) return;
        sub.textContent = greetingSub(projects, books);
        plateBody.innerHTML = '<div class="cv-plate">' + plateRowsHTML(projects) + '</div>';
        nudgeBody.innerHTML = '<div class="cv-nudges">' + nudgeListHTML(books) + '</div>';
        wireNudges(nudges);
      }).catch(function () {
        if (!container.isConnected) return;
        sub.textContent = 'Couldn\u2019t reach your workspace just now.';
        plateBody.innerHTML = '<div class="cv-plate"><p class="cv-empty">Projects couldn\u2019t load. Try again in a moment.</p></div>';
        nudgeBody.innerHTML = '<div class="cv-nudges"><p class="cv-empty">Library couldn\u2019t load. Try again in a moment.</p></div>';
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
