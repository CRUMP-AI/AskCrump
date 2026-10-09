/* Crump Vision — You view: Memory Console, Privacy, and Crump Credits.
   Memory entries are stored on this device only; plan and credit state is
   read live from the app, never invented. */

(() => {
  'use strict';

  var VIEW_ID = 'you';
  var registered = false;

  var MEM_KEY = 'cv-memory-v1';
  var PRIVACY_KEY = 'cv-privacy-v1';

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

  function userId() {
    return String((window.currentUser && window.currentUser.id) || 'guest');
  }

  /* ---------- Memory Console: local store, empty until the user adds ---------- */

  function readStore() {
    try {
      var raw = JSON.parse(localStorage.getItem(MEM_KEY) || 'null');
      if (raw && typeof raw === 'object' && !Array.isArray(raw)) return raw;
    } catch (_) {}
    return {};
  }

  function writeStore(store) {
    try { localStorage.setItem(MEM_KEY, JSON.stringify(store)); } catch (_) {}
  }

  function loadMemories() {
    var list = readStore()[userId()];
    return Array.isArray(list) ? list : [];
  }

  function saveMemories(list) {
    var store = readStore();
    store[userId()] = list;
    writeStore(store);
  }

  function newId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function formatDate(value) {
    var d = new Date(value);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  /* Real memory preferences the app itself keeps on this device. Read-only
     here; they are owned by the chat preferences module. */
  function readDeviceMemoryPrefs() {
    var key = 'crump_intelligence_v44:' + userId().replace(/[^a-zA-Z0-9_-]/g, '');
    try {
      var raw = JSON.parse(localStorage.getItem(key) || 'null');
      if (!raw || typeof raw !== 'object') return null;
      return {
        memoryEnabled: raw.memoryEnabled === true,
        autoLearn: raw.autoLearn === true
      };
    } catch (_) {
      return null;
    }
  }

  function memoryItemHtml(memory) {
    return '<li class="cv-memory-item" data-memory-id="' + esc(memory.id) + '">' +
      '<div style="flex:1;min-width:0">' +
        '<p class="cv-memory-text">' + esc(memory.text) + '<span class="cv-memory-date">' + esc(formatDate(memory.updatedAt || memory.createdAt) || 'Saved') + '</span></p>' +
      '</div>' +
      '<div class="cv-memory-actions">' +
        '<button type="button" class="cv-mini-btn" data-memory-edit>Edit</button>' +
        '<button type="button" class="cv-mini-btn is-danger" data-memory-delete>Delete</button>' +
      '</div>' +
    '</li>';
  }

  function renderMemorySection(section) {
    var list = section.querySelector('[data-memory-list]');
    var emptyState = section.querySelector('[data-memory-empty]');
    var memories = loadMemories();
    if (!memories.length) {
      list.innerHTML = '';
      list.style.display = 'none';
      emptyState.style.display = '';
    } else {
      emptyState.style.display = 'none';
      list.style.display = '';
      list.innerHTML = memories
        .slice()
        .sort(function (a, b) { return (b.updatedAt || 0) - (a.updatedAt || 0); })
        .map(memoryItemHtml)
        .join('');
    }

    var prefs = readDeviceMemoryPrefs();
    var deviceRows = section.querySelector('[data-device-rows]');
    if (deviceRows) {
      if (!prefs) {
        deviceRows.innerHTML = '<div class="cv-device-row"><span>Memory settings</span><b>Not set on this device</b></div>';
      } else {
        deviceRows.innerHTML =
          '<div class="cv-device-row"><span>Crump remembers this conversation&apos;s context</span><b>' + (prefs.memoryEnabled ? 'On' : 'Off') + '</b></div>' +
          '<div class="cv-device-row"><span>Crump learns preferences automatically</span><b>' + (prefs.autoLearn ? 'On' : 'Off') + '</b></div>';
      }
    }
  }

  function openEditor(section, memory) {
    var editor = section.querySelector('[data-memory-editor]');
    var textarea = section.querySelector('[data-memory-input]');
    var error = section.querySelector('[data-memory-error]');
    var heading = section.querySelector('[data-memory-editor-heading]');
    if (!editor || !textarea) return;
    editor.style.display = '';
    if (heading) heading.textContent = memory ? 'Edit memory' : 'Add a memory';
    textarea.value = memory ? memory.text : '';
    if (error) error.textContent = '';
    textarea.dataset.editingId = memory ? memory.id : '';
    textarea.focus();
  }

  function closeEditor(section) {
    var editor = section.querySelector('[data-memory-editor]');
    var textarea = section.querySelector('[data-memory-input]');
    if (!editor || !textarea) return;
    editor.style.display = 'none';
    textarea.value = '';
    textarea.dataset.editingId = '';
  }

  function wireMemorySection(section) {
    var textarea = section.querySelector('[data-memory-input]');
    var error = section.querySelector('[data-memory-error]');

    section.querySelector('[data-memory-add]').addEventListener('click', function () {
      openEditor(section, null);
    });

    section.querySelector('[data-memory-save]').addEventListener('click', function () {
      var text = String(textarea.value || '').trim();
      if (!text) {
        if (error) error.textContent = 'Write something first — an empty memory is not worth keeping.';
        textarea.focus();
        return;
      }
      var editingId = textarea.dataset.editingId || '';
      var memories = loadMemories();
      if (editingId) {
        memories = memories.map(function (m) {
          return m.id === editingId ? { id: m.id, text: text, createdAt: m.createdAt, updatedAt: Date.now() } : m;
        });
      } else {
        memories.push({ id: newId(), text: text, createdAt: Date.now(), updatedAt: Date.now() });
      }
      saveMemories(memories);
      closeEditor(section);
      renderMemorySection(section);
    });

    section.querySelector('[data-memory-cancel]').addEventListener('click', function () {
      closeEditor(section);
    });

    section.querySelector('[data-memory-list]').addEventListener('click', function (event) {
      var item = event.target.closest('[data-memory-id]');
      if (!item) return;
      var id = item.getAttribute('data-memory-id');
      var memories = loadMemories();
      var memory = memories.find(function (m) { return m.id === id; });
      if (!memory) return;

      if (event.target.closest('[data-memory-edit]')) {
        openEditor(section, memory);
        return;
      }
      if (event.target.closest('[data-memory-delete]')) {
        item.classList.add('is-removing');
        window.setTimeout(function () {
          saveMemories(loadMemories().filter(function (m) { return m.id !== id; }));
          renderMemorySection(section);
        }, 260);
      }
    });

    renderMemorySection(section);
  }

  /* ---------- Privacy toggles: device-local preferences, honestly labeled ---------- */

  var PRIVACY_DEFAULTS = { privateStorage: true, improveCrump: false, syncDevices: true };

  var PRIVACY_ROWS = [
    {
      key: 'privateStorage',
      title: 'Private storage',
      copy: 'Keeps your generations and projects in your own workspace. This switch sets the preference on this device.'
    },
    {
      key: 'improveCrump',
      title: 'Improve Crump with my data',
      copy: 'Off. When on, this would let anonymized usage help improve the product. Nothing is sent while it is off.'
    },
    {
      key: 'syncDevices',
      title: 'Sync across devices',
      copy: 'Keeps your workspace available when you sign in on another device. This switch sets the preference on this device.'
    }
  ];

  function loadPrivacy() {
    var stored = null;
    try { stored = JSON.parse(localStorage.getItem(PRIVACY_KEY) || 'null'); } catch (_) {}
    var prefs = {};
    PRIVACY_ROWS.forEach(function (row) {
      prefs[row.key] = stored && typeof stored[row.key] === 'boolean' ? stored[row.key] : PRIVACY_DEFAULTS[row.key];
    });
    return prefs;
  }

  function savePrivacy(prefs) {
    try { localStorage.setItem(PRIVACY_KEY, JSON.stringify(prefs)); } catch (_) {}
  }

  function wirePrivacySection(section) {
    var prefs = loadPrivacy();
    var list = section.querySelector('[data-privacy-list]');
    list.innerHTML = PRIVACY_ROWS.map(function (row) {
      var on = prefs[row.key] === true;
      return '<div class="cv-toggle-row">' +
        '<div class="cv-toggle-text"><strong>' + esc(row.title) + '</strong><p>' + esc(row.copy) + '</p></div>' +
        '<button type="button" class="cv-switch" role="switch" aria-checked="' + (on ? 'true' : 'false') + '" aria-label="' + esc(row.title) + '" data-privacy-key="' + esc(row.key) + '"></button>' +
      '</div>';
    }).join('');

    list.addEventListener('click', function (event) {
      var toggle = event.target.closest('[data-privacy-key]');
      if (!toggle) return;
      var key = toggle.getAttribute('data-privacy-key');
      prefs[key] = !(prefs[key] === true);
      toggle.setAttribute('aria-checked', prefs[key] ? 'true' : 'false');
      savePrivacy(prefs);
    });
  }

  /* ---------- Credits: live app state only, "—" when unknown ---------- */

  var creditBalance = null;

  function readCreditBalance() {
    return creditBalance;
  }

  function planInfo() {
    var tier = 'free';
    try {
      if (window.profileManager && typeof window.profileManager.getTier === 'function') {
        tier = String(window.profileManager.getTier() || 'free').toLowerCase();
      }
    } catch (_) {}
    var config = window.CRUMP_CONFIG || {};
    if (tier === 'pro' || tier === 'professional') {
      return { name: 'Professional', price: config.webProfessionalPriceLabel || '$20/month' };
    }
    if (tier === 'premium' || tier === 'enterprise') {
      return { name: 'Enterprise', price: config.webEnterprisePriceLabel || '$50/month' };
    }
    return { name: 'Free', price: '$0' };
  }

  function creditPacks() {
    var config = window.CRUMP_CONFIG || {};
    return [
      { credits: 50, price: config.webCredits50PriceLabel || '$4.99' },
      { credits: 150, price: config.webCredits150PriceLabel || '$9.99' },
      { credits: 400, price: config.webCredits400PriceLabel || '$19.99' }
    ];
  }

  function renderCreditsSection(section) {
    var plan = planInfo();
    var balance = readCreditBalance();
    var balanceEl = section.querySelector('[data-credit-balance]');
    if (balanceEl) balanceEl.textContent = balance === null ? '—' : String(balance);

    var planEl = section.querySelector('[data-plan-row]');
    if (planEl) {
      planEl.innerHTML = '<b>' + esc(plan.name) + ' plan</b><span>' + esc(plan.price) + '</span>';
    }

    var packList = section.querySelector('[data-pack-list]');
    if (packList) {
      packList.innerHTML = creditPacks().map(function (pack) {
        return '<li class="cv-pack-row"><b>' + esc(String(pack.credits)) + ' credits</b><span>' + esc(pack.price) + '</span></li>';
      }).join('');
    }
  }

  function watchCredits(section) {
    window.addEventListener('crump:credits-updated', function (event) {
      var detail = event && event.detail ? event.detail : {};
      var value = detail.balance !== undefined ? detail.balance : (detail.credits && detail.credits.balance);
      var num = Number(value);
      if (!isNaN(num)) {
        creditBalance = Math.max(0, Math.floor(num));
        var balanceEl = section.querySelector('[data-credit-balance]');
        if (balanceEl) balanceEl.textContent = String(creditBalance);
      }
    });
  }

  /* ---------- View render ---------- */

  function render(root) {
    root.classList.add('cv-you');
    root.innerHTML =
      '<div class="cv-you-wrap">' +
        '<p class="cv-eyebrow">You</p>' +
        '<h1 class="cv-headline">Your Crump</h1>' +
        '<p class="cv-sub">Everything Crump remembers about you, the privacy choices that shape it, and the wallet that pays for the work.</p>' +

        '<section class="cv-you-section" aria-labelledby="cvMemoryTitle">' +
          '<p class="cv-eyebrow">Memory console</p>' +
          '<h2 class="cv-headline" id="cvMemoryTitle" style="font-size:28px;margin-bottom:12px">Everything Crump remembers. Yours to see, edit, or erase.</h2>' +
          '<div class="cv-you-card">' +
            '<ul class="cv-memory-list" data-memory-list></ul>' +
            '<div class="cv-memory-empty" data-memory-empty>' +
              '<strong>Nothing saved yet</strong>' +
              '<p>Crump has not written down anything about you. When it learns something worth keeping, it will appear here — and you can edit or erase any of it.</p>' +
            '</div>' +
            '<div class="cv-editor-actions" style="margin-top:0;margin-bottom:4px">' +
              '<button type="button" class="cv-btn cv-btn-ghost" data-memory-add>Add memory</button>' +
            '</div>' +
            '<div class="cv-memory-editor" data-memory-editor style="display:none">' +
              '<p class="cv-section-divider-label" data-memory-editor-heading>Add a memory</p>' +
              '<label class="cv-field-label" for="cvMemoryInput" style="position:absolute;left:-9999px">Memory text</label>' +
              '<textarea class="cv-textarea" id="cvMemoryInput" data-memory-input placeholder="e.g. Greg prefers concise answers with the decision first…"></textarea>' +
              '<p class="cv-inline-error" data-memory-error></p>' +
              '<div class="cv-editor-actions">' +
                '<button type="button" class="cv-btn cv-btn-primary" data-memory-save>Save memory</button>' +
                '<button type="button" class="cv-btn cv-btn-ghost" data-memory-cancel>Cancel</button>' +
              '</div>' +
            '</div>' +
            '<p class="cv-device-note">On this device</p>' +
            '<div class="cv-device-rows" data-device-rows></div>' +
          '</div>' +
        '</section>' +

        '<section class="cv-you-section" aria-labelledby="cvPrivacyTitle">' +
          '<p class="cv-eyebrow">Privacy</p>' +
          '<h2 class="cv-headline" id="cvPrivacyTitle" style="font-size:28px;margin-bottom:12px">Private by design.</h2>' +
          '<div class="cv-you-card">' +
            '<div data-privacy-list></div>' +
            '<p class="cv-privacy-footnote">These switches set the privacy preferences on this device. They are stored locally and do not change anything kept on Ask Crump&apos;s servers.</p>' +
          '</div>' +
        '</section>' +

        '<section class="cv-you-section" aria-labelledby="cvCreditsTitle">' +
          '<p class="cv-eyebrow">Crump Credits</p>' +
          '<h2 class="cv-headline" id="cvCreditsTitle" style="font-size:28px;margin-bottom:12px">The wallet.</h2>' +
          '<div class="cv-you-card">' +
            '<div class="cv-wallet">' +
              '<div><p class="cv-balance-label">Balance</p><p class="cv-balance" data-credit-balance>—</p></div>' +
            '</div>' +
            '<div class="cv-plan-row" data-plan-row></div>' +
            '<p class="cv-section-divider-label">Credit packs</p>' +
            '<ul class="cv-pack-list" data-pack-list></ul>' +
          '</div>' +
        '</section>' +
      '</div>';

    var memorySection = root.querySelector('[aria-labelledby="cvMemoryTitle"]');
    var privacySection = root.querySelector('[aria-labelledby="cvPrivacyTitle"]');
    var creditsSection = root.querySelector('[aria-labelledby="cvCreditsTitle"]');

    if (memorySection) wireMemorySection(memorySection);
    if (privacySection) wirePrivacySection(privacySection);
    if (creditsSection) {
      renderCreditsSection(creditsSection);
      watchCredits(creditsSection);
    }
  }

  function tryRegister() {
    if (registered) return true;
    var v = window.CrumpVision;
    if (!v || typeof v.registerView !== 'function') return false;
    try {
      v.registerView(VIEW_ID, { title: 'You', render: render });
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
