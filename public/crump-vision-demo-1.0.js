/*
 * Crump Vision — preview-only demo mode (1.0)
 *
 * QA entry point for the Director's-Cut vision build. PREVIEW-ONLY
 * infrastructure, deliberately minimal and revert-clean:
 *
 *  - Activates ONLY on Vercel preview hostnames (*.vercel.app). It is inert
 *    on production (askcrump.com / www.askcrump.com) — the module returns
 *    before doing anything there.
 *  - Does NOT touch authentication. No sessions are created, no user data is
 *    read, no auth code paths are altered. Production auth is unchanged.
 *  - All demo "data" is static fixtures bundled below. The real API is never
 *    called for the six fixture routes while demo mode is on; everything
 *    else passes through untouched.
 *  - Writes nothing except a few clearly-labeled localStorage keys on the
 *    visitor's own browser (demo memory samples), only if absent.
 *  - To remove: delete this file and its <script> include in app.html.
 */
(function () {
  'use strict';

  if (window.__crumpVisionDemoLoaded) return;
  window.__crumpVisionDemoLoaded = true;

  /* ------------------------------------------------------------------ */
  /* Preview gate                                                        */
  /* ------------------------------------------------------------------ */

  function isPreviewHost() {
    try {
      var host = String(window.location.hostname || '').toLowerCase();
      return /\.vercel\.app$/.test(host);
    } catch (_) {
      return false;
    }
  }

  if (!isPreviewHost()) return; // production: this module stays inert.

  function demoRequested() {
    try {
      var hash = String(window.location.hash || '').toLowerCase();
      if (hash === '#demo' || hash.indexOf('#demo&') === 0) return true;
      return /(^|[?&])demo=1(&|#|$)/.test(String(window.location.search || ''));
    } catch (_) {
      return false;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Fixtures (static sample data — never real user data)                */
  /* ------------------------------------------------------------------ */

  var NOW = Date.now();
  function daysAgo(n) {
    return new Date(NOW - n * 864e5).toISOString();
  }

  var PROJECTS = [
    {
      id: 'demo-flagship',
      name: 'Flagship Launch',
      description: 'The Ask Crump Director\u2019s Cut \u2014 the reimagined workspace, end to end.',
      created_at: daysAgo(21),
      updated_at: daysAgo(0),
    },
    {
      id: 'demo-craft',
      name: 'Writing Craft',
      description: 'Essays and talks, kept somewhere they can be finished.',
      created_at: daysAgo(45),
      updated_at: daysAgo(2),
    },
    {
      id: 'demo-home',
      name: 'Home Office Reset',
      description: 'The room where the work happens.',
      created_at: daysAgo(60),
      updated_at: daysAgo(9),
    },
  ];

  var CONTEXTS = {
    'demo-flagship': {
      canon: [
        {
          kind: 'decision',
          label: 'Finish-first, not chat-first',
          content: 'Every answer should end in something you can keep \u2014 a document, a deck, a plan. The chat is the means, never the product.',
          updated_at: daysAgo(6),
        },
        {
          kind: 'instruction',
          label: 'Memory is legible',
          content: 'Everything Crump remembers lives in the Memory Console \u2014 visible, editable, erasable. Nothing is remembered in secret.',
          updated_at: daysAgo(4),
        },
        {
          kind: 'decision',
          label: 'Restrained gold, always',
          content: 'Ink black and quiet gold. No glows, no noise. A private members\u2019 club, not a slot machine.',
          updated_at: daysAgo(1),
        },
      ],
      manuscripts: [
        { title: 'Investor One-Pager', updated_at: daysAgo(0), status: 'ready' },
        { title: 'Launch Checklist', updated_at: daysAgo(2), status: 'draft' },
      ],
    },
    'demo-craft': {
      canon: [
        {
          kind: 'instruction',
          label: 'Voice notes',
          content: 'Short sentences. Warm, plain, exact. No jargon, no throat-clearing.',
          updated_at: daysAgo(12),
        },
      ],
      manuscripts: [{ title: 'Notes on Finishing', updated_at: daysAgo(3), status: 'draft' }],
    },
    'demo-home': { canon: [], manuscripts: [] },
  };

  var CHATS = {
    'demo-flagship': [
      { id: 'demo-c1', title: 'Investor one-pager draft', updatedAt: daysAgo(0) },
      { id: 'demo-c2', title: 'Pricing narrative', updatedAt: daysAgo(3) },
      { id: 'demo-c3', title: 'Launch checklist review', updatedAt: daysAgo(5) },
    ],
    'demo-craft': [{ id: 'demo-c4', title: 'Essay: on finishing things', updatedAt: daysAgo(4) }],
    'demo-home': [],
  };

  var BOOKS = [
    {
      id: 'demo-onepager',
      title: 'Investor One-Pager',
      subtitle: 'Ask Crump, Series A',
      authorName: 'Crump',
      origin: 'created',
      status: 'ready',
      sourceFile: { name: 'investor-one-pager.pdf' },
      updatedAt: daysAgo(0),
      createdAt: daysAgo(6),
      wordCount: 842,
      sectionCount: 3,
      projectId: 'demo-flagship',
      projectName: 'Flagship Launch',
    },
    {
      id: 'demo-checklist',
      title: 'Launch Checklist',
      subtitle: 'Director\u2019s Cut rollout',
      authorName: 'Crump',
      origin: 'created',
      status: 'draft',
      sourceFile: { name: 'launch-checklist.docx' },
      updatedAt: daysAgo(2),
      createdAt: daysAgo(9),
      wordCount: 1204,
      sectionCount: 4,
      projectId: 'demo-flagship',
      projectName: 'Flagship Launch',
    },
    {
      id: 'demo-voice',
      title: 'Brand Voice Guide',
      subtitle: 'How Ask Crump sounds',
      authorName: 'Crump',
      origin: 'created',
      status: 'ready',
      sourceFile: { name: 'brand-voice.pdf' },
      updatedAt: daysAgo(7),
      createdAt: daysAgo(30),
      wordCount: 2310,
      sectionCount: 5,
      projectId: '',
      projectName: '',
    },
    {
      id: 'demo-notes',
      title: 'Notes on Finishing',
      subtitle: 'An essay in progress',
      authorName: 'Crump',
      origin: 'created',
      status: 'draft',
      sourceFile: { name: 'notes-on-finishing.docx' },
      updatedAt: daysAgo(3),
      createdAt: daysAgo(20),
      wordCount: 1876,
      sectionCount: 2,
      projectId: 'demo-craft',
      projectName: 'Writing Craft',
    },
  ];

  var SECTIONS = {
    'demo-onepager': [
      {
        title: 'The thesis',
        content: 'AI should help you finish things.\n\nEvery product in this category answers. Almost none of them finish. Ask Crump is the workspace for work that survives one conversation \u2014 durable projects, legible memory, and keepsakes you can actually keep.',
      },
      {
        title: 'Why now',
        content: 'Models are a commodity. The interface is the moat.\n\nThe giants compete on intelligence. We compete on finished work \u2014 and on the feeling that the work is yours, kept in your library, under your control.',
      },
      {
        title: 'The ask',
        content: 'We are raising to make the Director\u2019s Cut real on every surface.\n\nThe money goes to craft: pixel-level QA on all six destinations, the Memory Console, and the keepsake pipeline \u2014 before a single App Store screenshot.',
      },
    ],
    'demo-checklist': [
      {
        title: 'Before the build',
        content: 'Lock the six destinations. Confirm the brand law on every screen.\n\nNo new features until the spine is solid: auth that never logs you out, sync that never loses a message.',
      },
      {
        title: 'The build',
        content: 'Home briefing. Chats with plans and keepsakes. Projects with durable memory. Library bookshelf. Studios. Memory Console.\n\nEach screen ships only after a pixel-level QA pass against the demo.',
      },
      {
        title: 'Before the store',
        content: 'Privacy URL live. Support email confirmed. Demo account ready.\n\nScreenshots from the real app \u2014 never mockups.',
      },
      {
        title: 'Launch day',
        content: 'Ship the story, not the feature list.\n\nOne finished piece of work, shown end to end. That is the whole marketing plan.',
      },
    ],
    'demo-voice': [
      {
        title: 'Sound',
        content: 'Warm, plain, exact. Short sentences.\n\nWe never hype, never hedge, never jargon. Confidence without volume.',
      },
      {
        title: 'We say',
        content: '\u201cThe answer is only the beginning.\u201d\n\u201cWork keeps its context.\u201d\n\u201cMake something you can keep.\u201d',
      },
      {
        title: 'We never say',
        content: 'No \u201csupercharge\u201d, no \u201cgame-changer\u201d, no \u201cunleash\u201d.\n\nIf a sentence could appear in any AI ad, it does not appear in ours.',
      },
      {
        title: 'The mascot',
        content: 'Crump is curious, never cute for cute\u2019s sake.\n\nHe shows his work: plans before answers, sources before claims, keepsakes at the end.',
      },
      {
        title: 'Restraint',
        content: 'One gold accent per screen is plenty.\n\nWhitespace is a feature. Silence is a feature.',
      },
    ],
    'demo-notes': [
      {
        title: 'I. The unfinished pile',
        content: 'Everyone has one: the drafts folder, the notes app, the thirty open tabs.\n\nUnfinished work is not a discipline problem. It is a tooling problem \u2014 the tools were built for chatting, not for finishing.',
      },
      {
        title: 'II. What finishing needs',
        content: 'Memory that survives the conversation. A place for the work to live. An ending you can hold.\n\nThat is the whole thesis. The rest is craft.',
      },
    ],
  };

  var DEMO_MEMORIES = [
    { id: 'demo-m1', text: 'Prefers annual billing over monthly.', createdAt: daysAgo(14), updatedAt: daysAgo(14) },
    { id: 'demo-m2', text: 'Keep work messages short after 8pm.', createdAt: daysAgo(10), updatedAt: daysAgo(10) },
    { id: 'demo-m3', text: 'Brand law: ink black and quiet gold \u2014 no glows, no noise.', createdAt: daysAgo(4), updatedAt: daysAgo(4) },
  ];

  /* Sample video jobs so the Studios gallery has something honest to render
     (and to re-render when "Refresh gallery" is pressed) in demo mode. */
  var VIDEO_JOBS = [
    {
      id: 'demo-video-1',
      status: 'processing',
      engine: 'cinematic',
      createdAt: daysAgo(0),
      file: null,
    },
    {
      id: 'demo-video-2',
      status: 'failed',
      engine: 'quick',
      createdAt: daysAgo(3),
      file: null,
    },
  ];

  /* ------------------------------------------------------------------ */
  /* Fixture router — only the six vision data routes, same-origin only  */
  /* ------------------------------------------------------------------ */

  function findProject(id) {
    for (var i = 0; i < PROJECTS.length; i++) {
      if (String(PROJECTS[i].id) === String(id)) return PROJECTS[i];
    }
    return null;
  }

  function fixtureFor(pathname) {
    var m;
    if (pathname === '/api/projects') return { projects: PROJECTS };
    if ((m = /^\/api\/projects\/([^/]+)\/chats$/.exec(pathname))) {
      return { conversations: CHATS[decodeURIComponent(m[1])] || [] };
    }
    if ((m = /^\/api\/projects\/([^/]+)$/.exec(pathname))) {
      var id = decodeURIComponent(m[1]);
      var project = findProject(id);
      if (!project) return null;
      return { project: project, context: CONTEXTS[id] || { canon: [], manuscripts: [] } };
    }
    if (pathname === '/api/library/books') return { books: BOOKS };
    if ((m = /^\/api\/manuscripts\/([^/]+)$/.exec(pathname))) {
      return { sections: SECTIONS[decodeURIComponent(m[1])] || [] };
    }
    if (pathname === '/api/media/video') return { jobs: VIDEO_JOBS };
    return null;
  }

  var origFetch = window.fetch ? window.fetch.bind(window) : null;

  function installInterceptor() {
    if (!origFetch || window.fetch.__cvDemoPatched) return;
    function patched(input, init) {
      if (window.__crumpVisionDemo !== true) return origFetch(input, init);
      var raw = input && typeof input === 'object' && input.url ? input.url : input;
      var url;
      try {
        url = new URL(String(raw), window.location.origin);
      } catch (_) {
        return origFetch(input, init);
      }
      if (url.origin !== window.location.origin) return origFetch(input, init);
      var fixture = fixtureFor(url.pathname);
      if (!fixture) return origFetch(input, init);
      return Promise.resolve(
        new Response(JSON.stringify(fixture), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );
    }
    patched.__cvDemoPatched = true;
    window.fetch = patched;
  }

  /* ------------------------------------------------------------------ */
  /* Demo-only Chats view — scripted showcase of the chats design        */
  /* language (mascot identity, thinking state, plan, keepsake card).    */
  /* ------------------------------------------------------------------ */

  var THINKING_VERBS = ['Reading your notes\u2026', 'Finding the story\u2026', 'Building your keepsake\u2026'];

  function el(html) {
    var t = document.createElement('template');
    t.innerHTML = String(html).trim();
    return t.content.firstElementChild;
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function renderChatsDemo(root) {
    root.className = 'cv-view';
    var wrap = el(
      '<div class="cv-wrap cv-demo-chat">' +
        '<p class="cv-eyebrow">Chats</p>' +
        '<h1 class="cv-headline">One conversation, finished.</h1>' +
        '<p class="cv-sub">A scripted look at the chats design language \u2014 mascot identity, calm thinking state, visible plan, and a keepsake at the end. Sign in to chat for real.</p>' +
        '<div class="cv-demo-thread" role="log" aria-label="Demo conversation"></div>' +
        '<div class="cv-demo-composer" aria-hidden="true">' +
          '<span>Message Crump\u2026</span><em>Demo \u2014 sign in to chat</em>' +
        '</div>' +
      '</div>'
    );
    var thread = wrap.querySelector('.cv-demo-thread');

    thread.appendChild(
      el(
        '<div class="cv-demo-user-row"><div class="cv-demo-user">Turn my launch notes into the investor one-pager.</div></div>'
      )
    );

    var assistant = el(
      '<div class="assistant-message"><div class="message-wrapper">' +
        '<div class="crump-message-meta cv-identity">' +
          '<span class="crump-message-avatar" aria-hidden="true"></span>' +
          '<span class="crump-message-name">Crump</span>' +
        '</div>' +
        '<div class="cv-demo-assistant"><p>On it \u2014 here\u2019s the plan, and the finished one-pager is waiting at the end.</p></div>' +
      '</div></div>'
    );
    thread.appendChild(assistant);

    var thinking = el(
      '<div class="presence-message cv-thinking" role="status" aria-label="Crump is thinking">' +
        '<span class="crump-message-avatar" aria-hidden="true"></span>' +
        '<div class="presence-bubble"><span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span>' +
        '<span class="cv-thinking-label">' + esc(THINKING_VERBS[0]) + '</span></div>' +
      '</div>'
    );
    thread.appendChild(thinking);
    var verbLabel = thinking.querySelector('.cv-thinking-label');
    var verbIndex = 1;
    var verbTimer = setInterval(function () {
      if (!thinking.isConnected) {
        clearInterval(verbTimer);
        return;
      }
      verbLabel.classList.add('cv-fade');
      setTimeout(function () {
        verbLabel.textContent = THINKING_VERBS[verbIndex % THINKING_VERBS.length];
        verbIndex += 1;
        verbLabel.classList.remove('cv-fade');
      }, 240);
    }, 2600);

    var plan = el(
      '<section class="cv-plan" role="status" aria-label="Crump\u2019s plan">' +
        '<div class="cv-eyebrow">Plan</div>' +
        '<ol class="cv-plan-steps">' +
          '<li class="cv-plan-step cv-plan-done" data-step-index="0"><span class="cv-plan-dot" aria-hidden="true"></span><span class="cv-plan-label">Read your launch notes</span></li>' +
          '<li class="cv-plan-step cv-plan-done" data-step-index="1"><span class="cv-plan-dot" aria-hidden="true"></span><span class="cv-plan-label">Find the story: finish-first</span></li>' +
          '<li class="cv-plan-step cv-plan-active" data-step-index="2"><span class="cv-plan-dot" aria-hidden="true"></span><span class="cv-plan-label">Build the one-pager keepsake</span></li>' +
        '</ol>' +
      '</section>'
    );
    thread.appendChild(plan);

    var keepsake = el(
      '<article class="cv-keepsake" aria-label="Keepsake: Investor One-Pager">' +
        '<div class="cv-eyebrow">Keepsake</div>' +
        '<h3 class="cv-keepsake-title">Investor One-Pager</h3>' +
        '<div class="cv-keepsake-meta">v1 \u00b7 PDF</div>' +
        '<div class="cv-keepsake-actions">' +
          '<button type="button" class="cv-keepsake-btn cv-keepsake-btn-primary" data-cv-demo-open-library>Open in Library</button>' +
          '<button type="button" class="cv-keepsake-btn" data-cv-demo-download>Download</button>' +
        '</div>' +
      '</article>'
    );
    keepsake.querySelector('[data-cv-demo-open-library]').addEventListener('click', function () {
      if (window.CrumpVision && typeof window.CrumpVision.navigate === 'function') {
        window.CrumpVision.navigate('library');
      }
    });
    keepsake.querySelector('[data-cv-demo-download]').addEventListener('click', function () {
      var lines = ['# Investor One-Pager', '', 'Sample keepsake from the Ask Crump demo.', ''];
      (SECTIONS['demo-onepager'] || []).forEach(function (section) {
        lines.push('## ' + (section.title || 'Section'), '');
        lines.push(String(section.content || ''), '');
      });
      var blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
      var url = URL.createObjectURL(blob);
      var anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'investor-one-pager-demo.md';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(function () {
        try { URL.revokeObjectURL(url); } catch (_) {}
      }, 5000);
    });
    thread.appendChild(keepsake);

    root.appendChild(wrap);
  }

  function registerChatsView() {
    try {
      var V = window.CrumpVision;
      if (V && typeof V.registerView === 'function') {
        V.registerView('chats', { title: 'Chats', render: renderChatsDemo });
      }
    } catch (_) {
      /* demo-only nicety; never break the app */
    }
  }

  /* ------------------------------------------------------------------ */
  /* Demo chrome: entry button, banner, styles                           */
  /* ------------------------------------------------------------------ */

  function injectStyles() {
    if (document.getElementById('cvDemoStyles')) return;
    var style = document.createElement('style');
    style.id = 'cvDemoStyles';
    style.textContent =
      'html[data-cv-demo="demo"] #authContainer { display: none !important; }' +
      'html[data-cv-demo="demo"] #v1RuntimeGate { display: none !important; }' +
      'html[data-cv-demo="demo"] .app-container { top: 36px !important; height: calc(100vh - 36px) !important; height: calc(100dvh - 36px) !important; }' +
      '#cvDemoBanner { position: fixed; top: 0; left: 0; right: 0; z-index: 9999; height: 36px; display: none;' +
      ' align-items: center; justify-content: center; gap: 10px; padding: 0 12px;' +
      ' background: #0b0f14; border-bottom: 1px solid rgba(213,185,113,0.35);' +
      ' color: #f1efe9; font: 12px/1 Inter, -apple-system, "Segoe UI", sans-serif; letter-spacing: 0.04em; }' +
      'html[data-cv-demo="demo"] #cvDemoBanner { display: flex; }' +
      '#cvDemoBanner .cv-demo-dot { width: 7px; height: 7px; border-radius: 50%; background: #d5b971; flex: 0 0 auto; }' +
      '#cvDemoBanner strong { color: #d5b971; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; font-size: 11px; }' +
      '#cvDemoBanner button { background: transparent; border: 1px solid rgba(213,185,113,0.5); color: #d5b971;' +
      ' border-radius: 999px; padding: 4px 12px; font-size: 11px; letter-spacing: 0.08em; cursor: pointer; }' +
      '#cvDemoBanner button:hover { background: rgba(213,185,113,0.12); }' +
      '.cv-demo-entry { margin-top: 18px; padding-top: 16px; border-top: 1px solid rgba(213,185,113,0.22); text-align: center; }' +
      '.cv-demo-entry .cv-demo-kicker { font-size: 10px; letter-spacing: 0.22em; text-transform: uppercase; color: #d5b971; margin-bottom: 10px; }' +
      '.cv-demo-entry .cv-demo-note { margin-top: 10px; font-size: 12px; color: #8a9196; line-height: 1.5; }' +
      '.cv-demo-chat .cv-demo-thread { display: flex; flex-direction: column; gap: 18px; margin: 26px 0; }' +
      '.cv-demo-user-row { display: flex; justify-content: flex-end; }' +
      '.cv-demo-user { max-width: 80%; background: rgba(213,185,113,0.10); border: 1px solid rgba(213,185,113,0.35);' +
      ' color: #f1efe9; border-radius: 14px 14px 4px 14px; padding: 12px 16px; font-size: 15px; line-height: 1.5; }' +
      '.cv-demo-chat .assistant-message { display: block; }' +
      '.cv-demo-chat .message-wrapper { display: flex; flex-direction: column; gap: 10px; }' +
      '.cv-demo-assistant p { margin: 0; font-size: 16px; line-height: 1.65; color: #f1efe9; }' +
      '.cv-demo-chat .presence-message { display: flex; align-items: center; gap: 10px; }' +
      '.cv-demo-composer { display: flex; align-items: center; justify-content: space-between; gap: 12px;' +
      ' border: 1px solid rgba(213,185,113,0.25); border-radius: 12px; padding: 14px 16px;' +
      ' color: #8a9196; font-size: 14px; background: rgba(255,255,255,0.02); }' +
      '.cv-demo-composer em { font-style: normal; font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: #d5b971; }';
    document.head.appendChild(style);
  }

  function injectEntry() {
    if (document.getElementById('cvDemoEntry')) return;
    var form = document.getElementById('loginForm');
    if (!form) return;
    var anchor = form.querySelector('.v1-auth-links') || form;
    var entry = el(
      '<div class="cv-demo-entry" id="cvDemoEntry">' +
        '<div class="cv-demo-kicker">Preview build</div>' +
        '<button type="button" class="btn btn-secondary btn-block" id="cvDemoEnterBtn">Explore the demo</button>' +
        '<p class="cv-demo-note">Sample data only \u2014 no account needed.<br>This entry appears on preview builds, never on askcrump.com.</p>' +
      '</div>'
    );
    if (anchor === form) {
      form.appendChild(entry);
    } else if (anchor.parentNode) {
      anchor.parentNode.insertBefore(entry, anchor.nextSibling);
    }
    var btn = document.getElementById('cvDemoEnterBtn');
    if (btn) btn.addEventListener('click', enterDemo);
  }

  function showBanner() {
    if (document.getElementById('cvDemoBanner')) return;
    var banner = el(
      '<div id="cvDemoBanner" role="status">' +
        '<span class="cv-demo-dot" aria-hidden="true"></span>' +
        '<strong>Demo mode</strong>' +
        '<span>Preview build \u00b7 sample data \u00b7 sign in for your real workspace</span>' +
        '<button type="button" id="cvDemoExit">Exit demo</button>' +
      '</div>'
    );
    document.body.appendChild(banner);
    document.getElementById('cvDemoExit').addEventListener('click', function () {
      try {
        if (window.location.hash === '#demo') window.location.hash = '';
        var url = window.location.pathname;
        window.location.href = url;
      } catch (_) {
        window.location.reload();
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* Demo memory samples (local only, only if the visitor has none)      */
  /* ------------------------------------------------------------------ */

  function seedDemoMemory() {
    try {
      var MEM_KEY = 'cv-memory-v1';
      var raw = JSON.parse(localStorage.getItem(MEM_KEY) || 'null');
      var store = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
      if (!Array.isArray(store.guest) || !store.guest.length) {
        store.guest = DEMO_MEMORIES.slice();
        localStorage.setItem(MEM_KEY, JSON.stringify(store));
      }
    } catch (_) {
      /* private mode etc. — the Memory Console simply starts empty */
    }
  }

  /* ------------------------------------------------------------------ */
  /* Enter demo mode                                                      */
  /* ------------------------------------------------------------------ */

  /* If the URL already asks for the demo, arm it at module execution time.
     This module loads before the vision shell (see the script order in
     app.html), and deferred scripts execute in document order while
     readyState is 'interactive' — so the shell boots and mounts Home during
     its own script evaluation, NOT on DOMContentLoaded. Arming here installs
     the fetch interceptor before any of that happens, so the very first
     render of every view already reads fixtures. Without this the shell
     mounts Home against the real API first and enterDemo has to flip away
     and back, which is what flashed a garbled greeting before the re-render. */
  var demoEntered = false;
  var demoArmedAtLoad = false;
  if (demoRequested()) {
    window.__crumpVisionDemo = true;
    installInterceptor();
    demoArmedAtLoad = true;
  }

  function enterDemo() {
    if (demoEntered) return;
    demoEntered = true;
    window.__crumpVisionDemo = true;
    installInterceptor();
    injectStyles();
    try {
      document.documentElement.setAttribute('data-cv-demo', 'demo');
    } catch (_) {}
    seedDemoMemory();
    registerChatsView();
    // Swap the auth screen for the app shell WITHOUT touching real auth
    // state: no session, no user, no initializeApp. The vision shell owns
    // its stage; the demo stylesheet keeps #authContainer hidden even if the
    // auth controller later tries to show it.
    var auth = document.getElementById('authContainer');
    var app = document.getElementById('appContainer');
    if (auth) auth.style.display = 'none';
    // The runtime gate is released by the auth flow; in demo mode it would
    // sit over the viewport forever, so keep it down (CSS guard above too).
    var gate = document.getElementById('v1RuntimeGate');
    if (gate) gate.hidden = true;
    if (app) {
      app.style.display = 'flex';
      app.removeAttribute('hidden');
    }
    // The real auth flow releases the inert lock on the shell when the
    // workspace is ready; in demo mode that flow never runs, so release it
    // here. Covers both the ?demo=1 path and the post-login entry button
    // path (where the no-session check had already locked the shell).
    var shell = document.querySelector('.v1-shell');
    if (shell) {
      shell.removeAttribute('inert');
      shell.removeAttribute('aria-hidden');
    }
    showBanner();
    // Mid-session entry (the preview entry button) still needs a refresh so
    // views mounted against the real API reload from fixtures. On the
    // ?demo=1 / #demo path the shell booted after the early arm above, so
    // the first mount already used fixtures — navigating away and back
    // would only flash the screen, so skip it.
    if (!demoArmedAtLoad) {
      try {
        var V = window.CrumpVision;
        if (V && typeof V.navigate === 'function') {
          V.navigate('chats');
          V.navigate('home');
        }
      } catch (_) {
        /* the shell will render on first navigation regardless */
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /* Boot                                                                */
  /* ------------------------------------------------------------------ */

  installInterceptor(); // installed early; active only once demo mode is on
  injectStyles();

  function shellReady() {
    try {
      return Boolean(
        window.CrumpVision && typeof window.CrumpVision.registerView === 'function'
      );
    } catch (_) {
      return false;
    }
  }

  function boot() {
    if (demoEntered) return;
    if (demoArmedAtLoad) {
      if (shellReady()) {
        enterDemo();
      } else {
        // This module executes before the vision shell: the interceptor
        // above is already armed (so the shell's first mount reads
        // fixtures), but enterDemo needs the shell registry — wait for its
        // ready signal instead of running half-armed.
        document.addEventListener('crumpvision:ready', enterDemo, { once: true });
        // Safety net: if the shell never signals (failed to load), still
        // enter demo mode once parsing finishes rather than hanging blank.
        document.addEventListener('DOMContentLoaded', function () {
          if (!demoEntered) enterDemo();
        }, { once: true });
      }
      // The real chats view registers after this module now; re-assert the
      // demo renderer once every deferred script has run (DOMContentLoaded
      // always fires after deferred scripts) so the demo keeps its scripted
      // chats view.
      document.addEventListener('DOMContentLoaded', function () {
        try { registerChatsView(); } catch (_) {}
      }, { once: true });
      return;
    }
    injectEntry();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
