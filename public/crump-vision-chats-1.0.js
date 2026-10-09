/*
 * Crump Vision — Chats screen (1.0)
 *
 * Enhancement layer for the Director's-Cut chats vision, laid over the real
 * chat engine. This module never rewrites the engine: it decorates rendered
 * assistant messages, restyles the existing presence (thinking) row, and
 * exposes plan + keepsake components under window.CrumpVision.chats.
 *
 * Depends on: #chatContainer, window.renderMessages (any version),
 * window.CrumpPresence. All optional — everything feature-detects.
 */

(() => {
  'use strict';

  var MASCOT_SRC = '/assets/crump-mascot-official.jpg';
  var DEFAULT_VERBS = [
    'Reading your notes…',
    'Finding the story…',
    'Building your keepsake…',
  ];
  var VERB_INTERVAL_MS = 2600;
  var VERB_FADE_MS = 240;
  var RE_REGISTER_MS = 500;
  var RE_REGISTER_ATTEMPTS = 10;

  // ---------------------------------------------------------------------------
  // CrumpVision shell: use the real one if it arrives, otherwise carry a
  // small fallback so the chats namespace works standalone. Never clobber
  // helpers the shell already provides.
  // ---------------------------------------------------------------------------

  function fallbackNavigate(view) {
    document.dispatchEvent(
      new CustomEvent('crump:vision-navigate', { detail: { view: view } })
    );
  }

  function ensureVision() {
    var vision = window.CrumpVision;
    if (!vision || typeof vision !== 'object') {
      vision = {};
      window.CrumpVision = vision;
    }
    if (typeof vision.registerView !== 'function') {
      vision.registerView = function () {};
    }
    if (typeof vision.navigate !== 'function') {
      vision.navigate = fallbackNavigate;
    }
    if (typeof vision.esc !== 'function') {
      vision.esc = function (value) {
        var probe = document.createElement('span');
        probe.textContent = value == null ? '' : String(value);
        return probe.innerHTML;
      };
    }
    if (typeof vision.el !== 'function') {
      vision.el = function (tag, className, text) {
        var node = document.createElement(tag || 'div');
        if (className) node.className = className;
        if (text != null) node.textContent = String(text);
        return node;
      };
    }
    if (typeof vision.eyebrow !== 'function') {
      vision.eyebrow = function (text) {
        return vision.el('div', 'cv-eyebrow', text);
      };
    }
    if (typeof vision.mascot !== 'function') {
      vision.mascot = function (size) {
        var img = document.createElement('img');
        img.src = MASCOT_SRC;
        img.alt = 'Crump';
        img.className = 'cv-mascot';
        var px = Number(size) || 32;
        img.width = px;
        img.height = px;
        return img;
      };
    }
    if (typeof vision.card !== 'function') {
      vision.card = function (className) {
        return vision.el('div', 'cv-card' + (className ? ' ' + className : ''));
      };
    }
    return vision;
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  var chatsApi = {
    __cvChats: true,
    showThinking: showThinking,
    hideThinking: hideThinking,
    showPlan: showPlan,
    updatePlanStep: updatePlanStep,
    completePlan: completePlan,
    addKeepsakeCard: addKeepsakeCard,
  };

  function attachChats(vision) {
    if (!vision) return;
    if (!vision.chats || vision.chats.__cvChats !== true) {
      vision.chats = chatsApi;
    }
  }

  var vision = ensureVision();
  attachChats(vision);

  // The real shell may replace window.CrumpVision wholesale after this file
  // loads. Re-attach the chats namespace so it survives.
  var reRegisterAttempts = 0;
  var reRegisterTimer = setInterval(function () {
    reRegisterAttempts += 1;
    if (window.CrumpVision && window.CrumpVision !== vision) {
      vision = ensureVision();
      attachChats(vision);
    }
    if (reRegisterAttempts >= RE_REGISTER_ATTEMPTS) {
      clearInterval(reRegisterTimer);
    }
  }, RE_REGISTER_MS);

  function visionNavigate(viewName) {
    var current = window.CrumpVision;
    if (current && typeof current.navigate === 'function' && current.navigate !== fallbackNavigate) {
      try {
        current.navigate(viewName);
        return;
      } catch (_) {
        /* fall through to the event */
      }
    }
    fallbackNavigate(viewName);
  }

  // ---------------------------------------------------------------------------
  // Message identity: mascot avatar + "Crump" nameplate on every assistant row.
  // The base renderer already inserts .crump-message-meta on most rows; this is
  // the backstop for any render path that skips it. Never double-decorates.
  // ---------------------------------------------------------------------------

  function chatContainer() {
    return document.getElementById('chatContainer');
  }

  function isAssistantRow(node) {
    return (
      node &&
      node.nodeType === 1 &&
      node.classList &&
      node.classList.contains('assistant-message')
    );
  }

  function decorateAssistantRow(row) {
    if (!isAssistantRow(row)) return;
    if (row.classList.contains('presence-message')) return; // handled as thinking
    if (row.dataset.cvIdentity === '1') return;
    var wrapper = row.querySelector('.message-wrapper');
    if (!wrapper) return;
    row.dataset.cvIdentity = '1';
    var meta = wrapper.querySelector('.crump-message-meta');
    if (!meta) {
      meta = document.createElement('div');
      meta.className = 'crump-message-meta cv-identity';
      var avatar = document.createElement('span');
      avatar.className = 'crump-message-avatar';
      avatar.setAttribute('aria-hidden', 'true');
      var nameplate = document.createElement('span');
      nameplate.className = 'crump-message-name';
      nameplate.textContent = 'Crump';
      meta.appendChild(avatar);
      meta.appendChild(nameplate);
      wrapper.insertBefore(meta, wrapper.firstChild);
    } else {
      meta.classList.add('cv-identity');
      if (!meta.querySelector('.crump-message-name')) {
        var name = document.createElement('span');
        name.className = 'crump-message-name';
        name.textContent = 'Crump';
        meta.appendChild(name);
      }
    }
  }

  function rescanIdentities() {
    var container = chatContainer();
    if (!container) return;
    var rows = container.querySelectorAll('.assistant-message');
    for (var i = 0; i < rows.length; i++) decorateAssistantRow(rows[i]);
  }

  // ---------------------------------------------------------------------------
  // Thinking state: vision treatment over the existing presence row.
  // The row itself comes from window.CrumpPresence; this module only restyles
  // it and drives the warm-verb label. The real send flow already calls
  // CrumpPresence.start on send and .stop on response/error, so the treatment
  // follows automatically via the observer below.
  // ---------------------------------------------------------------------------

  var verbTimer = null;
  var verbIndex = 0;
  var customVerbs = null;

  function findPresenceRow() {
    var container = chatContainer();
    if (!container) return null;
    return container.querySelector('.presence-message');
  }

  function ensureThinkingLabel(row) {
    var bubble = row.querySelector('.presence-bubble');
    if (!bubble) return null;
    var label = bubble.querySelector('.cv-thinking-label');
    if (!label) {
      label = document.createElement('span');
      label.className = 'cv-thinking-label';
      label.setAttribute('aria-hidden', 'true');
      bubble.appendChild(label);
    }
    return label;
  }

  function setVerb(label, text) {
    if (!label) return;
    label.classList.add('cv-fade');
    setTimeout(function () {
      label.textContent = text;
      label.classList.remove('cv-fade');
    }, VERB_FADE_MS);
  }

  function startVerbCycle(row) {
    stopVerbCycle();
    var label = ensureThinkingLabel(row);
    if (!label) return;
    var verbs = customVerbs && customVerbs.length ? customVerbs : DEFAULT_VERBS;
    verbIndex = 0;
    setVerb(label, verbs[0]);
    verbIndex = 1;
    verbTimer = setInterval(function () {
      setVerb(label, verbs[verbIndex % verbs.length]);
      verbIndex += 1;
    }, VERB_INTERVAL_MS);
  }

  function stopVerbCycle() {
    if (verbTimer) {
      clearInterval(verbTimer);
      verbTimer = null;
    }
  }

  function applyThinkingRow(row, forceVerbs) {
    if (!row || row.nodeType !== 1) return;
    var decorated = row.dataset.cvThinking === '1';
    row.classList.add('cv-thinking');
    row.dataset.cvThinking = '1';
    if (!decorated || forceVerbs) startVerbCycle(row);
  }

  function showThinking(verbs) {
    customVerbs = Array.isArray(verbs) && verbs.length ? verbs.slice() : null;
    try {
      if (window.CrumpPresence && typeof window.CrumpPresence.start === 'function') {
        window.CrumpPresence.start('thinking');
      }
    } catch (_) {
      /* presence unavailable; observer still styles any row that appears */
    }
    var row = findPresenceRow();
    if (row) applyThinkingRow(row, true);
  }

  function clearThinkingVisual() {
    customVerbs = null;
    stopVerbCycle();
    var row = findPresenceRow();
    if (row) {
      row.classList.remove('cv-thinking');
      delete row.dataset.cvThinking;
    }
  }

  function hideThinking() {
    clearThinkingVisual();
    try {
      if (window.CrumpPresence && typeof window.CrumpPresence.stop === 'function') {
        window.CrumpPresence.stop();
      }
    } catch (_) {
      /* presence already gone */
    }
  }

  // Route the app's own show/hide helpers through the vision treatment so a
  // plain start/stop still gets the gold dots and warm verbs.
  function wrapAppThinkingHelpers() {
    try {
      if (typeof window.showThinking === 'function' && !window.showThinking.__cvWrapped) {
        var originalShow = window.showThinking;
        var wrappedShow = function (activity) {
          var result = originalShow.apply(this, arguments);
          if (!activity || activity === 'thinking') showThinking();
          return result;
        };
        wrappedShow.__cvWrapped = true;
        window.showThinking = wrappedShow;
      }
      if (typeof window.hideThinking === 'function' && !window.hideThinking.__cvWrapped) {
        var originalHide = window.hideThinking;
        var wrappedHide = function () {
          var result = originalHide.apply(this, arguments);
          clearThinkingVisual();
          return result;
        };
        wrappedHide.__cvWrapped = true;
        window.hideThinking = wrappedHide;
      }
    } catch (_) {
      /* non-critical */
    }
  }

  // ---------------------------------------------------------------------------
  // Plan card: visible multi-step plan with animated checkpoints.
  // ---------------------------------------------------------------------------

  var planEl = null;

  function removePlan() {
    if (planEl && planEl.parentNode) planEl.parentNode.removeChild(planEl);
    planEl = null;
  }

  function showPlan(steps) {
    var container = chatContainer();
    if (!container) return null;
    removePlan();
    var list = Array.isArray(steps) ? steps : [];
    planEl = document.createElement('section');
    planEl.className = 'cv-plan';
    planEl.setAttribute('role', 'status');
    planEl.setAttribute('aria-label', 'Crump’s plan');
    planEl.appendChild(vision.eyebrow('Plan'));
    var stepsList = document.createElement('ol');
    stepsList.className = 'cv-plan-steps';
    for (var i = 0; i < list.length; i++) {
      var item = document.createElement('li');
      item.className = 'cv-plan-step cv-plan-pending';
      item.setAttribute('data-step-index', String(i));
      var dot = document.createElement('span');
      dot.className = 'cv-plan-dot';
      dot.setAttribute('aria-hidden', 'true');
      var label = document.createElement('span');
      label.className = 'cv-plan-label';
      label.textContent = String(list[i]);
      item.appendChild(dot);
      item.appendChild(label);
      stepsList.appendChild(item);
    }
    planEl.appendChild(stepsList);
    var presence = container.querySelector('.presence-message');
    if (presence && presence.parentNode === container && presence.nextSibling) {
      container.insertBefore(planEl, presence.nextSibling);
    } else {
      container.appendChild(planEl);
    }
    return planEl;
  }

  function planStepAt(index) {
    if (!planEl) return null;
    return planEl.querySelector('[data-step-index="' + index + '"]');
  }

  function setStepState(item, state) {
    if (!item) return;
    item.classList.remove('cv-plan-pending', 'cv-plan-active', 'cv-plan-done');
    var dot = item.querySelector('.cv-plan-dot');
    if (state === 'done') {
      item.classList.add('cv-plan-done');
      if (dot) dot.textContent = '✓';
    } else if (state === 'active') {
      item.classList.add('cv-plan-active');
      if (dot) dot.textContent = '';
    } else {
      item.classList.add('cv-plan-pending');
      if (dot) dot.textContent = '';
    }
  }

  function updatePlanStep(index, state) {
    setStepState(planStepAt(index), state === 'active' ? 'active' : state === 'done' ? 'done' : 'pending');
  }

  function completePlan() {
    if (!planEl) return;
    var items = planEl.querySelectorAll('.cv-plan-step');
    for (var i = 0; i < items.length; i++) setStepState(items[i], 'done');
    planEl.classList.add('cv-plan-complete');
    var settled = planEl;
    setTimeout(function () {
      if (settled && settled.parentNode) settled.classList.add('cv-plan-settled');
    }, 1500);
  }

  // ---------------------------------------------------------------------------
  // Keepsake card: the artifact that ends an answer.
  // addKeepsakeCard is called explicitly by the backend or by UI code that
  // owns an artifact payload. Real artifact payloads (message.artifact,
  // rendered by the chat engine as .crump50-artifact) are picked up by the
  // observer below and restyled in place instead.
  // ---------------------------------------------------------------------------

  function upgradeRealArtifact(card) {
    if (!card || card.nodeType !== 1) return;
    if (card.dataset.cvKeepsake === '1') return;
    card.dataset.cvKeepsake = '1';
    card.classList.add('cv-keepsake-real');
  }

  function slug(value) {
    return (
      String(value == null || value === '' ? 'keepsake' : value)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'keepsake'
    );
  }

  // Real client-side download: the keepsake content becomes a markdown file
  // and is handed to the browser's download flow with a sensible name.
  function downloadKeepsakeFile(info) {
    var title = info && info.title ? String(info.title) : 'Untitled keepsake';
    var kind = String((info && info.kind) || 'PDF').toUpperCase();
    var version = info && info.version ? 'v' + info.version : '';
    var lines = ['# ' + title, ''];
    if (version) {
      lines.push('Version: ' + version, '');
    }
    lines.push('Kind: ' + kind);
    lines.push('Saved from Ask Crump', '');
    var content = info && info.content != null ? String(info.content).trim() : '';
    if (content) {
      lines.push(content);
    } else {
      lines.push('The full keepsake content lives in your Library — open it there to read and share the finished piece.');
    }
    var blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = slug(title) + (version ? '-' + version.toLowerCase() : '') + '.md';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(function () {
      try {
        URL.revokeObjectURL(url);
      } catch (_) {}
    }, 5000);
  }

  function addKeepsakeCard(options) {
    var opts = options || {};
    var container = chatContainer();
    if (!container) return null;
    var title = opts.title != null && String(opts.title).trim()
      ? String(opts.title).trim()
      : 'Untitled keepsake';
    var version = opts.version != null && String(opts.version).trim()
      ? String(opts.version).trim()
      : '';
    var kind = opts.kind != null && String(opts.kind).trim()
      ? String(opts.kind).trim().toUpperCase()
      : 'PDF';

    var card = document.createElement('article');
    card.className = 'cv-keepsake';
    card.setAttribute('aria-label', 'Keepsake: ' + title);

    card.appendChild(vision.eyebrow('Keepsake'));

    var heading = document.createElement('h3');
    heading.className = 'cv-keepsake-title';
    heading.textContent = title;
    card.appendChild(heading);

    var meta = document.createElement('div');
    meta.className = 'cv-keepsake-meta';
    var metaText = version ? 'v' + version + ' · ' + kind : kind;
    meta.textContent = metaText;
    card.appendChild(meta);

    var actions = document.createElement('div');
    actions.className = 'cv-keepsake-actions';

    var openButton = document.createElement('button');
    openButton.type = 'button';
    openButton.className = 'cv-keepsake-btn cv-keepsake-btn-primary';
    openButton.textContent = 'Open in Library';
    openButton.addEventListener('click', function () {
      if (typeof opts.onOpen === 'function') {
        try {
          opts.onOpen();
        } catch (_) {
          /* caller-owned */
        }
      }
      visionNavigate('library');
    });

    var downloadButton = document.createElement('button');
    downloadButton.type = 'button';
    downloadButton.className = 'cv-keepsake-btn';
    downloadButton.textContent = 'Download';
    downloadButton.addEventListener('click', function () {
      if (typeof opts.onDownload === 'function') {
        try {
          opts.onDownload();
        } catch (_) {
          /* caller-owned */
        }
        return;
      }
      if (opts.url) {
        var anchor = document.createElement('a');
        anchor.href = String(opts.url);
        anchor.download = opts.filename ? String(opts.filename) : '';
        anchor.rel = 'noopener';
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        return;
      }
      downloadKeepsakeFile({
        title: title,
        version: version,
        kind: kind,
        content: opts.content,
      });
    });

    actions.appendChild(openButton);
    actions.appendChild(downloadButton);
    card.appendChild(actions);

    var anchors = container.querySelectorAll('.assistant-message .message-wrapper');
    var lastWrapper = anchors.length ? anchors[anchors.length - 1] : null;
    if (lastWrapper) lastWrapper.appendChild(card);
    else container.appendChild(card);
    return card;
  }

  // ---------------------------------------------------------------------------
  // Observer: decorate rows as they render, restyle the thinking row, and
  // upgrade real artifact cards. renderMessages rebuilds every node on each
  // call, so dataset flags keep this idempotent.
  // ---------------------------------------------------------------------------

  function handleAddedNode(node) {
    if (!node || node.nodeType !== 1) return;
    if (node.classList.contains('presence-message')) {
      applyThinkingRow(node, false);
      return;
    }
    if (node.classList.contains('crump50-artifact')) {
      upgradeRealArtifact(node);
      return;
    }
    if (node.classList.contains('assistant-message')) {
      decorateAssistantRow(node);
    }
    var presenceRows = node.querySelectorAll ? node.querySelectorAll('.presence-message') : [];
    for (var i = 0; i < presenceRows.length; i++) applyThinkingRow(presenceRows[i], false);
    var artifactCards = node.querySelectorAll ? node.querySelectorAll('.crump50-artifact:not([data-cv-keepsake])') : [];
    for (var j = 0; j < artifactCards.length; j++) upgradeRealArtifact(artifactCards[j]);
    var assistantRows = node.querySelectorAll ? node.querySelectorAll('.assistant-message:not(.presence-message):not([data-cv-identity])') : [];
    for (var k = 0; k < assistantRows.length; k++) decorateAssistantRow(assistantRows[k]);
  }

  function initObserver() {
    try {
      var observer = new MutationObserver(function (mutations) {
        for (var m = 0; m < mutations.length; m++) {
          var added = mutations[m].addedNodes;
          for (var n = 0; n < added.length; n++) handleAddedNode(added[n]);
        }
      });
      var target = chatContainer() || document.body;
      observer.observe(target, { childList: true, subtree: true });
    } catch (_) {
      /* observer unsupported; identities still applied on rescan */
    }
  }

  function init() {
    wrapAppThinkingHelpers();
    initObserver();
    rescanIdentities();
    window.addEventListener('crump:conversation-opened', function () {
      rescanIdentities();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
