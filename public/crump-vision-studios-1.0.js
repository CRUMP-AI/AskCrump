/* Crump Vision — Studios view: Image Studio and Video Studio entry cards.
   Launches the real in-app generators. When a generator did not load in this
   session, the view says so on its own status line instead of leaving the
   app — nothing here ever ejects to a marketing page. */

(() => {
  'use strict';

  var VIEW_ID = 'studios';
  var registered = false;

  var MODES = [
    { id: 'quick', label: 'Quick', desc: 'Short, efficient first takes. The fastest way to see an idea move.' },
    { id: 'extendable', label: 'Extendable', desc: 'Continue a compatible clip from its ending — the ending of one scene becomes the start of the next.' },
    { id: 'cinematic', label: 'Cinematic', desc: 'Premium short-form scenes where framing, motion, and finish matter more than iteration speed.' }
  ];

  var IMAGE_MODES = [
    { id: 'quick', label: 'Quick', desc: 'A fast first take — rough framing to explore the idea before committing to a finished image.' },
    { id: 'refined', label: 'Refined', desc: 'Slower and more deliberate — higher detail and polish for images worth keeping.' },
    { id: 'cinematic', label: 'Cinematic', desc: 'Dramatic, editorial finish — considered light and composition for a hero frame.' }
  ];

  function esc(value) {
    var shell = window.CrumpVision;
    if (shell && typeof shell.esc === 'function') return shell.esc(value);
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function shell() {
    return window.CrumpVision;
  }

  /* Image Studio opens as a sheet over the current surface; the chosen mode
     is handed to the real studio when it accepts one. */
  function launchImageStudio(modeId, statusEl) {
    var open = window.CrumpImageStudio && window.CrumpImageStudio.open;
    if (typeof open !== 'function') {
      if (statusEl) {
        statusEl.textContent = 'The Image Studio did not load in this session. Find it again under Studios and try once more.';
        statusEl.classList.add('is-error');
      }
      return;
    }
    window.setTimeout(function () {
      try {
        try {
          open(modeId);
        } catch (_) {
          open();
        }
      } catch (_) {
        if (statusEl) {
          statusEl.textContent = 'The Image Studio could not open. Please try again from Studios.';
          statusEl.classList.add('is-error');
        }
      }
    }, 60);
  }

  /* Video Studio: open the real panel, then hand over the chosen mode and
     prompt into its own controls so nothing is lost. The in-app studio is
     the only destination — if it did not load, say so on the status line and
     stay inside the app (never eject to a marketing page). */
  function videoStudioUnavailable(statusEl) {
    if (statusEl) {
      statusEl.textContent = 'The Video Studio did not load in this session. Find it again under Studios and try once more.';
      statusEl.classList.add('is-error');
    }
  }

  function launchVideoStudio(modeId, prompt, statusEl) {
    var open = window.CrumpProduct53 && window.CrumpProduct53.open;
    if (typeof open !== 'function') {
      videoStudioUnavailable(statusEl);
      return;
    }
    try { open('video'); } catch (_) {
      videoStudioUnavailable(statusEl);
      return;
    }
    window.setTimeout(function () {
      var engine = document.getElementById('crump53VideoEngine');
      if (engine) {
        engine.value = modeId;
        engine.dispatchEvent(new Event('change', { bubbles: true }));
      }
      var promptField = document.getElementById('crump53VideoPrompt');
      var trimmed = String(prompt || '').trim();
      if (promptField && trimmed && !String(promptField.value || '').trim()) {
        promptField.value = trimmed;
        promptField.dispatchEvent(new Event('input', { bubbles: true }));
      }
      if (promptField && typeof promptField.focus === 'function') {
        try { promptField.focus({ preventScroll: false }); } catch (_) {}
      }
    }, 120);
  }

  function formatJobDate(value) {
    if (!value) return '';
    var d = new Date(value);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function renderGalleryItem(job) {
    var status = String(job && job.status || 'processing').toLowerCase();
    var label = status === 'ready' ? 'Ready' : (status === 'failed' ? 'Needs attention' : 'Generating');
    var engine = String(job && job.engine || 'quick');
    var created = formatJobDate(job && job.createdAt) || 'Recent';
    var url = job && job.file && job.file.url ? String(job.file.url) : '';
    var inner = '<strong>' + esc(label) + '</strong><span>' + esc(engine) + ' · ' + esc(created) + '</span>';
    if (status === 'ready' && url) {
      return '<a class="cv-gallery-item" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + inner + '</a>';
    }
    return '<div class="cv-gallery-item">' + inner + '</div>';
  }

  function loadGallery(listEl) {
    if (!listEl) return;
    var authed = Boolean(window.currentUser && window.currentUser.id);
    var demo = window.__crumpVisionDemo === true;
    if (!authed && !demo) {
      listEl.innerHTML = '<div class="cv-gallery-empty"><strong>No clips yet</strong><p>Sign in and generate your first video — finished clips appear here.</p></div>';
      return;
    }
    listEl.innerHTML = '<div class="cv-loading">Checking your private video jobs…</div>';
    fetch('/api/media/video', { credentials: 'same-origin' })
      .then(function (res) {
        if (!res.ok) throw new Error('unavailable');
        return res.json();
      })
      .then(function (data) {
        var jobs = Array.isArray(data && data.jobs) ? data.jobs.slice(0, 6) : [];
        if (!jobs.length) {
          listEl.innerHTML = '<div class="cv-gallery-empty"><strong>No clips yet</strong><p>Generate your first video and it will live here, kept in your workspace.</p></div>';
          return;
        }
        listEl.innerHTML = jobs.map(renderGalleryItem).join('');
      })
      .catch(function () {
        listEl.innerHTML = '<div class="cv-gallery-empty"><strong>Could not load your clips</strong><p>Your recent videos are unavailable right now. Open Video Studio to check on them.</p></div>';
      });
  }

  function render(root) {
    root.classList.add('cv-view');
    root.innerHTML =
      '<div class="cv-wrap">' +
        '<p class="cv-eyebrow">Create</p>' +
        '<h1 class="cv-headline">Studios</h1>' +
        '<p class="cv-sub">Two purpose-built studios for work that starts as an idea and ends as something you can keep.</p>' +

        '<section class="cv-card" aria-labelledby="cvImageTitle">' +
          '<div class="cv-card-head">' +
            '<h2 class="cv-card-title" id="cvImageTitle">Image Studio</h2>' +
            '<span class="cv-card-kicker">Still frames</span>' +
          '</div>' +
          '<p class="cv-card-copy">One studio, three modes. Pick the finish that fits the frame, then generate the image and keep it in your workspace.</p>' +
          '<div class="cv-pills" role="group" aria-label="Image mode" data-cv-image-mode-pills>' +
            IMAGE_MODES.map(function (m, i) {
              return '<button type="button" class="cv-pill" data-cv-image-mode="' + esc(m.id) + '" aria-pressed="' + (i === 0 ? 'true' : 'false') + '">' + esc(m.label) + '</button>';
            }).join('') +
          '</div>' +
          '<p class="cv-mode-desc" data-cv-image-mode-desc>' + esc(IMAGE_MODES[0].desc) + '</p>' +
          '<div class="cv-actions">' +
            '<button type="button" class="cv-btn cv-btn-primary" data-cv-open-image>Open Image Studio</button>' +
          '</div>' +
          '<p class="cv-status" data-cv-image-status></p>' +
        '</section>' +

        '<section class="cv-card" aria-labelledby="cvVideoTitle">' +
          '<div class="cv-card-head">' +
            '<h2 class="cv-card-title" id="cvVideoTitle">Video Studio</h2>' +
            '<span class="cv-card-kicker">Motion</span>' +
          '</div>' +
          '<p class="cv-card-copy">One studio, three modes. Pick the mode that fits the shot, write the direction, and generate the scene.</p>' +
          '<div class="cv-pills" role="group" aria-label="Video mode" data-cv-mode-pills>' +
            MODES.map(function (m, i) {
              return '<button type="button" class="cv-pill" data-cv-mode="' + esc(m.id) + '" aria-pressed="' + (i === 0 ? 'true' : 'false') + '">' + esc(m.label) + '</button>';
            }).join('') +
          '</div>' +
          '<p class="cv-mode-desc" data-cv-mode-desc>' + esc(MODES[0].desc) + '</p>' +
          '<label class="cv-field-label" for="cvVideoPrompt">Direction</label>' +
          '<textarea class="cv-textarea" id="cvVideoPrompt" data-cv-video-prompt placeholder="A lighthouse keeper waves from a cliff at dawn, gulls crossing the frame…"></textarea>' +
          '<div class="cv-actions">' +
            '<button type="button" class="cv-btn cv-btn-primary" data-cv-open-video>Continue in Video Studio</button>' +
            '<button type="button" class="cv-btn cv-btn-ghost" data-cv-refresh-gallery>Refresh gallery</button>' +
          '</div>' +
          '<p class="cv-status" data-cv-video-status></p>' +
          '<div class="cv-gallery-head" style="margin-top:32px">' +
            '<h3 class="cv-field-label" style="margin:0">Recent clips</h3>' +
          '</div>' +
          '<div class="cv-gallery-grid" data-cv-gallery></div>' +
        '</section>' +
      '</div>';

    var selectedImageMode = 'quick';
    var selectedMode = 'quick';

    var imagePillGroup = root.querySelector('[data-cv-image-mode-pills]');
    var imageModeDesc = root.querySelector('[data-cv-image-mode-desc]');
    if (imagePillGroup && imageModeDesc) {
      imagePillGroup.addEventListener('click', function (event) {
        var pill = event.target.closest('[data-cv-image-mode]');
        if (!pill) return;
        selectedImageMode = pill.getAttribute('data-cv-image-mode');
        imagePillGroup.querySelectorAll('[data-cv-image-mode]').forEach(function (node) {
          node.setAttribute('aria-pressed', node === pill ? 'true' : 'false');
        });
        var mode = IMAGE_MODES.find(function (m) { return m.id === selectedImageMode; });
        imageModeDesc.textContent = mode ? mode.desc : '';
      });
    }

    var pillGroup = root.querySelector('[data-cv-mode-pills]');
    var modeDesc = root.querySelector('[data-cv-mode-desc]');
    if (pillGroup && modeDesc) {
      pillGroup.addEventListener('click', function (event) {
        var pill = event.target.closest('[data-cv-mode]');
        if (!pill) return;
        selectedMode = pill.getAttribute('data-cv-mode');
        pillGroup.querySelectorAll('[data-cv-mode]').forEach(function (node) {
          node.setAttribute('aria-pressed', node === pill ? 'true' : 'false');
        });
        var mode = MODES.find(function (m) { return m.id === selectedMode; });
        modeDesc.textContent = mode ? mode.desc : '';
      });
    }

    var imageStatus = root.querySelector('[data-cv-image-status]');
    var imageBtn = root.querySelector('[data-cv-open-image]');
    if (imageBtn) {
      imageBtn.addEventListener('click', function () {
        if (imageStatus) { imageStatus.textContent = ''; imageStatus.classList.remove('is-error'); }
        launchImageStudio(selectedImageMode, imageStatus);
      });
    }

    var videoStatus = root.querySelector('[data-cv-video-status]');
    var videoBtn = root.querySelector('[data-cv-open-video]');
    var promptField = root.querySelector('[data-cv-video-prompt]');
    if (videoBtn) {
      videoBtn.addEventListener('click', function () {
        if (videoStatus) { videoStatus.textContent = ''; videoStatus.classList.remove('is-error'); }
        launchVideoStudio(selectedMode, promptField ? promptField.value : '', videoStatus);
      });
    }

    var gallery = root.querySelector('[data-cv-gallery]');
    var refreshBtn = root.querySelector('[data-cv-refresh-gallery]');
    if (refreshBtn && gallery) {
      refreshBtn.addEventListener('click', function () { loadGallery(gallery); });
    }
    loadGallery(gallery);
  }

  function tryRegister() {
    if (registered) return true;
    var v = shell();
    if (!v || typeof v.registerView !== 'function') return false;
    try {
      v.registerView(VIEW_ID, { title: 'Studios', render: render });
    } catch (_) {
      return false;
    }
    registered = true;
    return true;
  }

  /* The vision shell loads separately; register now and keep retrying. */
  function boot() {
    if (tryRegister()) return;
    var startedAt = Date.now();
    var timer = window.setInterval(function () {
      if (tryRegister() || Date.now() - startedAt > 10000) {
        window.clearInterval(timer);
      }
    }, 250);
    window.addEventListener('load', tryRegister, { once: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
