(() => {
  'use strict';
  let appStarted = false;
  let activeUser = null;
  let planIntentDispatched = false;
  const TERMS_VERSION = '2026-07-30';
  const PLAN_INTENT_KEY = 'askcrump.pending-plan-intent';
  const ACQUISITION_KEY = 'askcrump.acquisition-source';
  const PLAN_INTENT_TTL_MS = 7 * 24 * 60 * 60 * 1000;
  const PAID_PLAN_INTENTS = new Set(['professional', 'enterprise']);
  const LEGACY_ACQUISITION_SOURCES = new Set([
    'instagram', 'facebook', 'facebook-pinned', 'linkedin', 'tiktok',
    'youtube', 'x', 'referral', 'clevercrump',
  ]);

  window.va = window.va || function queueVercelAnalytics() {
    (window.vaq = window.vaq || []).push(arguments);
  };

  const byId = id => document.getElementById(id);
  const show = (id, display = 'block') => { const node = byId(id); if (node) node.style.display = display; };
  const hide = id => { const node = byId(id); if (node) node.style.display = 'none'; };
  const setText = (id, text, visible = true) => { const node = byId(id); if (!node) return; node.textContent = text || ''; node.style.display = visible ? 'block' : 'none'; };

  function funnelValue(value, fallback) {
    const normalized = String(value || '').trim().toLowerCase();
    return /^[a-z0-9_-]{1,32}$/.test(normalized) ? normalized : fallback;
  }

  function funnelContext() {
    const params = new URLSearchParams(location.search);
    const locationSource = funnelValue(params.get('source'), 'direct');
    const explicitAcquisition = funnelValue(
      params.get('acquisition') || params.get('utm_source'),
      '',
    );
    // Older social links used `source=<channel>` before the dedicated
    // `acquisition` parameter existed. Recover only known external channels;
    // on-site CTA locations such as hero, pricing, and footer stay locations.
    const legacyAcquisition = LEGACY_ACQUISITION_SOURCES.has(locationSource)
      ? locationSource
      : '';
    const currentAcquisition = explicitAcquisition || legacyAcquisition;
    if (currentAcquisition) {
      try { sessionStorage.setItem(ACQUISITION_KEY, currentAcquisition); } catch (_) {}
    }
    let storedAcquisition = '';
    try { storedAcquisition = funnelValue(sessionStorage.getItem(ACQUISITION_KEY), ''); } catch (_) {}
    return {
      source: locationSource,
      acquisition: currentAcquisition || storedAcquisition || 'direct',
      plan: funnelValue(params.get('plan'), 'unspecified'),
    };
  }

  function trackFunnel(name, data = {}) {
    window.va('event', {name, data: {...funnelContext(), ...data}});
  }

  function capturePlanIntent() {
    const context = funnelContext();
    if (!PAID_PLAN_INTENTS.has(context.plan)) return;
    try {
      localStorage.setItem(PLAN_INTENT_KEY, JSON.stringify({
        plan: context.plan,
        source: context.acquisition,
        location: context.source,
        capturedAt: Date.now(),
      }));
    } catch (_) {}
  }

  function pendingPlanIntent() {
    try {
      const intent = JSON.parse(localStorage.getItem(PLAN_INTENT_KEY) || 'null');
      const capturedAt = Number(intent?.capturedAt || 0);
      if (!PAID_PLAN_INTENTS.has(intent?.plan) || !capturedAt || Date.now() - capturedAt > PLAN_INTENT_TTL_MS) {
        localStorage.removeItem(PLAN_INTENT_KEY);
        return null;
      }
      return {
        plan: intent.plan,
        source: funnelValue(intent.source, 'direct'),
        location: funnelValue(intent.location, 'unknown'),
        capturedAt,
      };
    } catch (_) {
      try { localStorage.removeItem(PLAN_INTENT_KEY); } catch (_) {}
      return null;
    }
  }

  function dispatchPendingPlanIntent() {
    if (planIntentDispatched) return;
    const intent = pendingPlanIntent();
    if (!intent) return;

    const deliver = () => {
      if (planIntentDispatched) return;
      planIntentDispatched = true;
      window.addEventListener('crump:plan-intent-consumed', event => {
        if (event.detail?.plan !== intent.plan) return;
        try { localStorage.removeItem(PLAN_INTENT_KEY); } catch (_) {}
      }, {once: true});
      window.dispatchEvent(new CustomEvent('crump:plan-intent', {detail: intent}));
    };

    if (document.documentElement.dataset.crumpBodyRuntime === 'ready') {
      queueMicrotask(deliver);
    } else {
      window.addEventListener('crump:body-runtime-ready', deliver, {once: true});
    }
  }

  function applyServerSettings(settings) {
    if (!settings || typeof settings !== 'object') return;
    const keys = window.STORAGE_KEYS || {};
    const mappings = [
      ['assistant_name', keys.ASSISTANT_NAME || 'crump_assistant_name'],
      ['work_mode', keys.WORK_MODE || 'crump_work_mode'],
      ['work_start', keys.WORK_START || 'crump_work_start'],
      ['work_end', keys.WORK_END || 'crump_work_end'],
    ];
    for (const [field, key] of mappings) {
      if (settings[field] !== undefined && settings[field] !== null) {
        localStorage.setItem(key, String(settings[field]));
      }
    }
  }

  async function pullServerState() {
    if (!navigator.onLine || !window.SyncManager) return null;
    try {
      const result = await window.SyncManager.pull(null, { full: true });
      if (result?.success) {
        window.__crumpSyncData = result.data;
        applyServerSettings(result.data?.settings);
        return result.data;
      }
    } catch (error) {
      console.warn('[Bootstrap] Initial sync failed:', error);
    }
    return null;
  }

  function startApp() {
    hide('authContainer');
    hide('tosModal');
    hide('onboardingModal');
    show('appContainer', 'flex');
    if (!appStarted) {
      window.initializeApp?.();
      appStarted = true;
    }
    if (activeUser) window.initializeAuthenticatedApp?.(activeUser);
    if (activeUser) {
      const day = new Date().toISOString().slice(0, 10);
      void window.CrumpAnalytics?.track('WorkspaceOpened', {eventKey: `workspace-open:${day}`});
    }
    setTimeout(() => window.tutorial?.autoStart?.(), 450);
    dispatchPendingPlanIntent();
  }

  function routeAuthenticatedUser(user) {
    activeUser = user;
    window.currentUser = user;
    window.configureUserStorage?.(user.id);
    window.profileManager?.applyServerSubscription?.(user);
    if (!user.termsAcceptedAt) {
      hide('authContainer');
      show('tosModal', 'flex');
      return;
    }
    if (user.fullName) {
      localStorage.setItem(window.STORAGE_KEYS?.HAS_ONBOARDED || 'crump_has_onboarded', 'true');
      window.profileManager?.updateProfile?.({ name: user.fullName, email: user.email });
    }
    if (!user.fullName) {
      hide('authContainer');
      show('onboardingModal', 'flex');
      return;
    }
    startApp();
  }

  function showAuth(view = 'login') {
    hide('appContainer');
    hide('tosModal');
    hide('onboardingModal');
    show('authContainer', 'flex');
    ['loginForm', 'registerForm', 'forgotPasswordForm', 'resetPasswordForm'].forEach(hide);
    show(view === 'register' ? 'registerForm' : 'loginForm');
  }

  function showVerificationResult(value) {
    const messages = {
      success: 'Email verified. You can sign in now.',
      already_verified: 'This email is already verified.',
      failed: 'That verification link is invalid or expired.',
    };
    if (!messages[value]) return;
    setText(value === 'failed' ? 'loginError' : 'loginSuccess', messages[value]);
  }

  async function bootstrap() {
    capturePlanIntent();
    await window.CrumpAPI?.ready;
    const params = new URLSearchParams(location.search);
    const signupRequested = params.get('signup') === '1';
    const resetToken = params.get('token');
    if (resetToken) {
      show('authContainer', 'flex');
      hide('loginForm');
      show('resetPasswordForm');
      byId('resetPasswordForm').dataset.token = resetToken;
      return;
    }

    const verification = params.get('verification');
    if (verification) {
      history.replaceState({}, document.title, location.pathname);
    }

    const session = await window.deviceAuth.checkSession();
    if (session.unavailable) {
      showAuth(signupRequested ? 'register' : 'login');
      setText(
        'loginError',
        'Ask Crump could not verify your existing session right now. Your saved sign-in was preserved; try again in a moment.',
      );
      if (verification) showVerificationResult(verification);
      return;
    }
    if (!session.authenticated || !session.data?.user) {
      showAuth(signupRequested ? 'register' : 'login');
      if (signupRequested) trackFunnel('SignupIntent', {location: 'deep-link'});
      if (verification) showVerificationResult(verification);
      return;
    }
    activeUser = session.data.user;
    window.currentUser = activeUser;
    window.configureUserStorage?.(activeUser.id);
    applyServerSettings(session.data.settings);
    if (!session.offline) await pullServerState();
    routeAuthenticatedUser(activeUser);
    if (verification) showVerificationResult(verification);
  }

  function wireNavigation() {
    byId('showRegisterLink')?.addEventListener('click', event => {
      event.preventDefault();
      hide('loginForm');
      show('registerForm');
      trackFunnel('SignupIntent', {location: 'auth-link'});
    });
    byId('showLoginLink')?.addEventListener('click', event => { event.preventDefault(); hide('registerForm'); show('loginForm'); });
    byId('showForgotPasswordLink')?.addEventListener('click', event => { event.preventDefault(); hide('loginForm'); show('forgotPasswordForm'); });
    byId('showLoginFromForgot')?.addEventListener('click', event => { event.preventDefault(); hide('forgotPasswordForm'); show('loginForm'); });
    byId('showLoginFromReset')?.addEventListener('click', event => { event.preventDefault(); history.replaceState({}, document.title, location.pathname); hide('resetPasswordForm'); show('loginForm'); });
  }

  function wireTerms() {
    byId('tosAccept')?.addEventListener('change', event => {
      const button = byId('tosAcceptBtn');
      if (!button) return;
      button.disabled = !event.target.checked;
      button.style.opacity = event.target.checked ? '1' : '.5';
    });
    byId('tosAcceptBtn')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      const original = button.textContent;
      button.textContent = 'Saving…';
      try {
        const response = await fetch('/api/account/accept-terms', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version: TERMS_VERSION }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) throw new Error(data.error || 'Could not save your acceptance.');
        activeUser = data.user || { ...activeUser, termsAcceptedAt: new Date().toISOString(), termsVersion: TERMS_VERSION };
        window.currentUser = activeUser;
        hide('tosModal');
        if (activeUser.fullName) startApp();
        else show('onboardingModal', 'flex');
      } catch (error) {
        window.showToast?.(error.message, 'error');
        button.disabled = false;
        button.textContent = original;
      }
    });
  }

  function setBusy(form, busy, label) {
    const button = form?.querySelector('button[type="submit"]');
    if (!button) return () => {};
    const original = button.dataset.originalText || button.textContent;
    button.dataset.originalText = original;
    button.disabled = busy;
    button.textContent = busy ? label : original;
    return () => { button.disabled = false; button.textContent = original; };
  }

  function validatePasswordInput(password) {
    if (password.length < 10) return 'Password must be at least 10 characters long.';
    if (password.length > 256) return 'Password is too long.';
    if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      return 'Password must contain at least one letter and one number.';
    }
    return null;
  }

  function applyPasswordPolicyMarkup() {
    const ids = ['registerPassword', 'newPassword', 'confirmNewPassword'];
    for (const id of ids) {
      const input = byId(id);
      if (!input) continue;
      input.setAttribute('minlength', '10');
      input.setAttribute('maxlength', '256');
    }

    const registerPassword = byId('registerPassword');
    const resetPassword = byId('newPassword');
    if (registerPassword) registerPassword.placeholder = '10+ characters with a letter and number';
    if (resetPassword) resetPassword.placeholder = '10+ characters with a letter and number';

    for (const input of [registerPassword, resetPassword]) {
      const hint = input?.parentElement?.querySelector('.form-hint');
      if (hint) hint.textContent = 'At least 10 characters with a letter and a number';
    }
  }

  function wirePasswordVisibility() {
    document.querySelectorAll('[data-password-target]').forEach(button => {
      if (button.dataset.passwordVisibilityWired === 'true') return;
      const input = byId(button.dataset.passwordTarget);
      if (!input) return;
      button.dataset.passwordVisibilityWired = 'true';
      button.addEventListener('click', () => {
        const showing = input.type === 'text';
        input.type = showing ? 'password' : 'text';
        button.textContent = showing ? 'Show' : 'Hide';
        button.setAttribute('aria-pressed', String(!showing));
        input.focus({preventScroll: true});
      });
    });
  }

  function wireLogin() {
    byId('loginFormElement')?.addEventListener('submit', async event => {
      event.preventDefault();
      setText('loginError', '', false);
      hide('verificationNeeded');
      const restore = setBusy(event.currentTarget, true, 'Signing in…');
      try {
        const result = await window.deviceAuth.login(byId('loginEmail').value.trim(), byId('loginPassword').value);
        if (!result.success || !result.data?.user) throw Object.assign(new Error(result.error || 'Sign in failed.'), { result });
        activeUser = result.data.user;
        window.currentUser = activeUser;
        window.configureUserStorage?.(activeUser.id);
        applyServerSettings(result.data.settings);
        await pullServerState();
        setText('loginSuccess', 'Signed in.');
        routeAuthenticatedUser(activeUser);
      } catch (error) {
        setText('loginError', error.message || 'Network error. Try again.');
        if (error.result?.needsVerification) show('verificationNeeded');
      } finally {
        restore();
      }
    });
  }

  function wireRegistration() {
    const form = byId('registerFormElement');
    if (!form) return;
    let nativeValidationTracked = false;
    form.addEventListener('invalid', event => {
      if (nativeValidationTracked) return;
      nativeValidationTracked = true;
      setTimeout(() => { nativeValidationTracked = false; }, 0);
      const field = event.target;
      let reason = 'required_field';
      if (field?.id === 'registerEmail' && field.validity?.typeMismatch) reason = 'email_format';
      if (field?.id === 'registerPassword') reason = 'password_length';
      trackFunnel('SignupValidationFailed', {reason});
    }, true);

    form.addEventListener('submit', async event => {
      event.preventDefault();
      setText('registerError', '', false);
      setText('registerSuccess', '', false);
      const password = byId('registerPassword').value;
      const passwordError = validatePasswordInput(password);
      if (passwordError) {
        const reason = password.length < 10 ? 'password_length' : 'password_rules';
        trackFunnel('SignupValidationFailed', {reason});
        return setText('registerError', passwordError);
      }
      trackFunnel('SignupSubmitted');
      const restore = setBusy(event.currentTarget, true, 'Creating account…');
      try {
        const email = byId('registerEmail').value.trim();
        const response = await fetch('/api/auth/register', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email,
            password,
            fullName: byId('registerName').value.trim(),
            source: funnelContext().acquisition,
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
          if (data.accountCreated && data.needsVerification) {
            setText(
              'registerSuccess',
              data.error || 'Account created, but verification email delivery is temporarily unavailable.',
            );
            if (byId('loginEmail')) byId('loginEmail').value = email;
            setTimeout(() => {
              hide('registerForm');
              show('loginForm');
              show('verificationNeeded');
              setText(
                'loginError',
                'Your account exists but still needs email verification. Use Resend verification to try delivery again.',
              );
            }, 2200);
            return;
          }
          throw new Error(data.error || 'Registration failed.');
        }
        trackFunnel('AccountCreated');
        setText('registerSuccess', data.message || 'Account created. Check your email.');
        setTimeout(() => { hide('registerForm'); show('loginForm'); }, 1800);
      } catch (error) {
        setText('registerError', error.message);
      } finally { restore(); }
    });
  }

  function wireRecovery() {
    byId('forgotPasswordFormElement')?.addEventListener('submit', async event => {
      event.preventDefault();
      setText('forgotPasswordError', '', false);
      const restore = setBusy(event.currentTarget, true, 'Sending…');
      try {
        const response = await fetch('/api/auth/forgot-password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: byId('forgotPasswordEmail').value.trim() }) });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Could not send the reset email.');
        setText('forgotPasswordSuccess', data.message);
      } catch (error) { setText('forgotPasswordError', error.message); }
      finally { restore(); }
    });

    byId('resetPasswordFormElement')?.addEventListener('submit', async event => {
      event.preventDefault();
      setText('resetPasswordError', '', false);
      const password = byId('newPassword').value;
      const passwordError = validatePasswordInput(password);
      if (passwordError) return setText('resetPasswordError', passwordError);
      if (password !== byId('confirmNewPassword').value) return setText('resetPasswordError', 'Passwords do not match.');
      const restore = setBusy(event.currentTarget, true, 'Updating…');
      try {
        const response = await fetch('/api/auth/reset-password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: byId('resetPasswordForm').dataset.token, newPassword: password }) });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Password reset failed.');
        setText('resetPasswordSuccess', data.message);
        setTimeout(() => { history.replaceState({}, document.title, location.pathname); hide('resetPasswordForm'); show('loginForm'); }, 1800);
      } catch (error) { setText('resetPasswordError', error.message); }
      finally { restore(); }
    });

    byId('resendVerificationBtn')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      const email = byId('loginEmail').value.trim();
      if (!email) return setText('loginError', 'Enter your email first.');
      button.disabled = true;
      try {
        const response = await fetch('/api/auth/resend-verification', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) });
        const data = await response.json().catch(() => ({}));
        setText(response.ok ? 'loginSuccess' : 'loginError', data.message || data.error || 'Request completed.');
      } finally { button.disabled = false; }
    });
  }

  window.completeOnboarding = async function completeOnboarding() {
    const name = byId('onboardingName').value.trim();
    if (!name) return;
    try {
      const response = await fetch('/api/account/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fullName: name }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.success) throw new Error(data.error || 'Could not save your profile.');
      activeUser = data.user || { ...activeUser, fullName: name };
      window.currentUser = activeUser;
      window.profileManager?.updateProfile?.({ name, email: activeUser.email, initial: name.charAt(0).toUpperCase() });
      localStorage.setItem(window.STORAGE_KEYS?.HAS_ONBOARDED || 'crump_has_onboarded', 'true');
      startApp();
    } catch (error) {
      window.showToast?.(error.message, 'error');
    }
  };

  window.exportChats = function exportChats() {
    const chats = window.chats || JSON.parse(localStorage.getItem(window.STORAGE_KEYS?.CHATS || 'crump_chats') || '[]');
    const url = URL.createObjectURL(new Blob([JSON.stringify(chats, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `ask-crump-conversations-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  window.logoutUser = async function logoutUser() {
    await window.deviceAuth.logout();
    location.replace('/app');
  };

  window.restartTutorial = function restartTutorial() {
    window.closeSettings?.();
    window.tutorial?.restart?.();
  };

  document.addEventListener('DOMContentLoaded', () => {
    applyPasswordPolicyMarkup();
    wirePasswordVisibility();
    byId('onboardingContinueBtn')?.addEventListener('click', () => window.completeOnboarding());
    byId('onboardingName')?.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        window.completeOnboarding();
      }
    });
    wireNavigation();
    wireTerms();
    wireLogin();
    wireRegistration();
    wireRecovery();
    bootstrap().catch(error => { console.error('[Bootstrap]', error); showAuth(); });
  });
})();
