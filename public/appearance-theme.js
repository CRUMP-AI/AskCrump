(function initializeCrumpAppearance() {
  'use strict';

  const STORAGE_KEY = 'askcrump.appearance';
  const DEFAULT_THEME = 'light';
  const THEMES = Object.freeze(['light', 'dark']);
  const THEME_COLORS = Object.freeze({
    light: '#f6f4ee',
    dark: '#101216',
  });
  let themeSwitchToken = 0;

  function normalizeTheme(value) {
    return THEMES.includes(value) ? value : DEFAULT_THEME;
  }

  function readStoredTheme() {
    try {
      return normalizeTheme(window.localStorage.getItem(STORAGE_KEY));
    } catch (_) {
      return DEFAULT_THEME;
    }
  }

  function updateBrowserChrome(theme) {
    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) themeColor.setAttribute('content', THEME_COLORS[theme]);
  }

  function beginAtomicThemeSwitch() {
    const root = document.documentElement;
    const token = ++themeSwitchToken;
    root.classList.add('crump-theme-switching');
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      if (token !== themeSwitchToken) return;
      root.classList.remove('crump-theme-switching');
    }));
  }

  function syncControls() {
    const theme = normalizeTheme(document.documentElement.dataset.theme);
    document.querySelectorAll('input[name="appearanceTheme"]').forEach(control => {
      const selected = control.value === theme;
      control.checked = selected;
      control.closest('.appearance-choice')?.classList.toggle('is-selected', selected);
    });
  }

  function applyTheme(nextTheme, options = {}) {
    const theme = normalizeTheme(nextTheme);
    const previous = normalizeTheme(document.documentElement.dataset.theme);

    if (previous !== theme) beginAtomicThemeSwitch();
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    updateBrowserChrome(theme);

    if (options.persist !== false) {
      try { window.localStorage.setItem(STORAGE_KEY, theme); }
      catch (_) { /* The active session still keeps the chosen appearance. */ }
    }

    syncControls();
    if (options.announce !== false && previous !== theme) {
      window.dispatchEvent(new CustomEvent('crump:appearance-changed', {
        detail: Object.freeze({theme}),
      }));
    }
    return theme;
  }

  function wireControls() {
    document.querySelectorAll('input[name="appearanceTheme"]').forEach(control => {
      if (control.dataset.appearanceWired === 'true') return;
      control.dataset.appearanceWired = 'true';
      control.addEventListener('change', () => {
        if (control.checked) applyTheme(control.value);
      });
    });
    syncControls();
  }

  const initialTheme = readStoredTheme();
  applyTheme(initialTheme, {persist: false, announce: false});

  window.CrumpAppearance = Object.freeze({
    storageKey: STORAGE_KEY,
    get: () => normalizeTheme(document.documentElement.dataset.theme),
    set: theme => applyTheme(theme),
    syncControls,
  });

  window.addEventListener('storage', event => {
    if (event.key !== STORAGE_KEY) return;
    applyTheme(event.newValue, {persist: false});
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wireControls, {once: true});
  } else {
    wireControls();
  }
}());
