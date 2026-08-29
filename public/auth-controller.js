(() => {
  'use strict';
  let appStarted = false;
  let activeUser = null;
  let planIntentDispatched = false;
  let authFlowRevision = 0;
  let signupIntentTracked = false;
  let workspaceRuntimeGateTimer = 0;
  let workspaceRuntimeGateWaiting = false;
  const TERMS_VERSION = '2026-07-30';
  const PLAN_INTENT_KEY = 'askcrump.pending-plan-intent';
  const CREATION_INTENT_KEY = 'askcrump.pending-creation-intent';
  const ACQUISITION_KEY = 'askcrump.acquisition-source';
  const PLAN_INTENT_TTL_MS = 7 * 24 * 60 * 60 * 1000;
  const CREATION_INTENT_TTL_MS = 24 * 60 * 60 * 1000;
  const PAID_PLAN_INTENTS = new Set(['professional', 'enterprise']);
  const CREATION_INTENTS = new Set(['document', 'presentation', 'resume', 'video']);
  const LEGACY_ACQUISITION_SOURCES = new Set([
    'instagram', 'facebook', 'facebook-pinned', 'linkedin', 'tiktok',
    'youtube', 'x', 'referral', 'organic', 'clevercrump',
  ]);

  window.va = window.va || function queueVercelAnalytics() {
    (window.vaq = window.vaq || []).push(arguments);
  };

  const byId = id => document.getElementById(id);
  const show = (id, display = 'block') => { const node = byId(id); if (node) node.style.display = display; };
  const hide = id => { const node = byId(id); if (node) node.style.display = 'none'; };
  const setText = (id, text, visible = true) => { const node = byId(id); if (!node) return; node.textContent = text || ''; node.style.display = visible ? 'block' : 'none'; };
  const AUTH_VIEWS = Object.freeze({
    login: {containerId: 'loginForm', fieldId: 'loginEmail'},
    register: {containerId: 'registerForm', fieldId: 'registerEmail'},
    forgot: {containerId: 'forgotPasswordForm', fieldId: 'forgotPasswordEmail'},
    reset: {containerId: 'resetPasswordForm', fieldId: 'newPassword'},
  });

  function authRequest(url, options, timeoutMessage) {
    return window.CrumpAuthTransport.request(url, options, {timeoutMessage});
  }

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
      intent: creationIntentValue(params.get('intent')) || pendingCreationIntent()?.kind || 'unspecified',
    };
  }

  function trackFunnel(name, data = {}) {
    window.va('event', {name, data: {...funnelContext(), ...data}});
  }

  function trackSignupIntent(locationName) {
    if (signupIntentTracked) return;
    signupIntentTracked = true;
    trackFunnel('SignupIntent', {location: locationName});
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

  function creationIntentValue(value) {
    const normalized = String(value || '').trim().toLowerCase();
    return CREATION_INTENTS.has(normalized) ? normalized : '';
  }

  function captureCreationIntent() {
    const params = new URLSearchParams(location.search);
    const kind = creationIntentValue(params.get('intent'));
    if (!kind) return;
    const context = funnelContext();
    try {
      localStorage.setItem(CREATION_INTENT_KEY, JSON.stringify({
        kind,
        source: context.source,
        acquisition: context.acquisition,
        capturedAt: Date.now(),
      }));
    } catch (_) {}
  }

  function pendingCreationIntent() {
    try {
      const intent = JSON.parse(localStorage.getItem(CREATION_INTENT_KEY) || 'null');
      const capturedAt = Number(intent?.capturedAt || 0);
      const kind = creationIntentValue(intent?.kind);
      if (!kind || !capturedAt || Date.now() - capturedAt > CREATION_INTENT_TTL_MS) {
        localStorage.removeItem(CREATION_INTENT_KEY);
        return null;
      }
      return {
        kind,
        source: funnelValue(intent.source, 'unknown'),
        acquisition: funnelValue(intent.acquisition, 'direct'),
        capturedAt,
      };
    } catch (_) {
      try { localStorage.removeItem(CREATION_INTENT_KEY); } catch (_) {}
      return null;
    }
  }

  function dispatchPendingCreationIntent() {
    const intent = pendingCreationIntent();
    if (!intent) return;

    const deliver = () => {
      window.addEventListener('crump:creation-intent-consumed', event => {
        if (event.detail?.kind !== intent.kind) return;
        try { localStorage.removeItem(CREATION_INTENT_KEY); } catch (_) {}
      }, {once: true});
      window.dispatchEvent(new CustomEvent('crump:creation-intent', {detail: intent}));
    };

    if (document.documentElement.dataset.crumpBodyRuntime === 'ready') {
      queueMicrotask(deliver);
    } else {
      window.addEventListener('crump:body-runtime-ready', deliver, {once: true});
    }
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

  function releaseWorkspaceRuntimeGate() {
    if (workspaceRuntimeGateTimer) window.clearTimeout(workspaceRuntimeGateTimer);
    workspaceRuntimeGateTimer = 0;
    workspaceRuntimeGateWaiting = false;
    window.removeEventListener('crump:body-runtime-ready', releaseWorkspaceRuntimeGate);
    byId('appContainer')?.removeAttribute('aria-busy');
    document.querySelector('.v1-shell')?.removeAttribute('inert');
    const gate = byId('v1RuntimeGate');
    if (!gate || gate.hidden) return;
    gate.classList.add('is-ready');
    gate.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => {
      if (gate.classList.contains('is-ready')) gate.hidden = true;
    }, 220);
  }

  function holdWorkspaceForRuntime() {
    if (document.documentElement.dataset.crumpBodyRuntime === 'ready') {
      releaseWorkspaceRuntimeGate();
      return;
    }
    const gate = byId('v1RuntimeGate');
    const shell = document.querySelector('.v1-shell');
    if (gate) {
      gate.hidden = false;
      gate.classList.remove('is-ready');
      gate.removeAttribute('aria-hidden');
    }
    byId('appContainer')?.setAttribute('aria-busy', 'true');
    shell?.setAttribute('inert', '');
    if (!workspaceRuntimeGateWaiting) {
      workspaceRuntimeGateWaiting = true;
      window.addEventListener('crump:body-runtime-ready', releaseWorkspaceRuntimeGate, {once: true});
    }
    if (workspaceRuntimeGateTimer) window.clearTimeout(workspaceRuntimeGateTimer);
    workspaceRuntimeGateTimer = window.setTimeout(releaseWorkspaceRuntimeGate, 5000);
  }

  function showReturningVisitorGate() {
    hide('authContainer');
    hide('tosModal');
    hide('onboardingModal');
    const gate = byId('v1RuntimeGate');
    const shell = document.querySelector('.v1-shell');
    if (gate) {
      gate.hidden = false;
      gate.classList.remove('is-ready');
      gate.removeAttribute('aria-hidden');
    }
    byId('appContainer')?.setAttribute('aria-busy', 'true');
    shell?.setAttribute('inert', '');
    show('appContainer', 'flex');
  }

  function startApp() {
    hide('authContainer');
    hide('tosModal');
    hide('onboardingModal');
    holdWorkspaceForRuntime();
    show('appContainer', 'flex');
    if (!appStarted) {
      window.initializeApp?.();
      appStarted = true;
    }
    if (activeUser) {
      window.initializeAuthenticatedApp?.(activeUser);
      window.dispatchEvent(new Event('crump:authenticated-ready'));
    }
    if (activeUser) {
      const day = new Date().toISOString().slice(0, 10);
      void window.CrumpAnalytics?.track('WorkspaceOpened', {eventKey: `workspace-open:${day}`});
    }
    setTimeout(() => window.tutorial?.autoStart?.(), 450);
    dispatchPendingCreationIntent();
    dispatchPendingPlanIntent();
  }

  function profileNudgeKey() {
    return window.STORAGE_KEYS?.PROFILE_NUDGE_DISMISSED || 'crump_profile_nudge_dismissed';
  }

  function profileNudgeDismissed() {
    try { return localStorage.getItem(profileNudgeKey()) === 'true'; } catch (_) { return false; }
  }

  function maybeOfferProfileSetup() {
    const nudge = byId('v1ProfileNudge');
    if (!nudge) return;
    nudge.hidden = Boolean(window.currentUser?.fullName || activeUser?.fullName) || profileNudgeDismissed();
  }

  function openProfileSetup() {
    const nudge = byId('v1ProfileNudge');
    if (nudge) nudge.hidden = true;
    setText('onboardingError', '', false);
    show('onboardingModal', 'flex');
    requestAnimationFrame(() => byId('onboardingName')?.focus());
  }

  function dismissProfileSetup() {
    try { localStorage.setItem(profileNudgeKey(), 'true'); } catch (_) {}
    hide('onboardingModal');
    const nudge = byId('v1ProfileNudge');
    if (nudge) nudge.hidden = true;
    byId('userInput')?.focus({preventScroll: true});
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
    startApp();
    if (!user.fullName) maybeOfferProfileSetup();
  }

  function focusAuthView(view) {
    const fieldId = AUTH_VIEWS[view]?.fieldId;
    if (!fieldId) return;
    requestAnimationFrame(() => byId(fieldId)?.focus({preventScroll: true}));
  }

  function showAuth(view = 'login') {
    const normalizedView = AUTH_VIEWS[view] ? view : 'login';
    hide('appContainer');
    hide('tosModal');
    hide('onboardingModal');
    show('authContainer', 'flex');
    Object.values(AUTH_VIEWS).forEach(({containerId}) => hide(containerId));
    if (normalizedView === 'register') resetRegistrationView();
    show(AUTH_VIEWS[normalizedView].containerId);
    focusAuthView(normalizedView);
  }

  function resetRegistrationView() {
    hide('registrationPending');
    show('registerEntry');
    setText('registrationPendingSuccess', '', false);
    setText('registrationPendingError', '', false);
  }

  function showRegistrationPending(email, message, {deliveryFailed = false} = {}) {
    const loginEmail = byId('loginEmail');
    if (loginEmail) loginEmail.value = email;
    const forgotEmail = byId('forgotPasswordEmail');
    if (forgotEmail) forgotEmail.value = email;
    const pendingEmail = byId('registrationPendingEmail');
    if (pendingEmail) pendingEmail.textContent = email;
    setText('registerError', '', false);
    setText('registerSuccess', '', false);
    setText('registrationPendingSuccess', deliveryFailed ? '' : message, !deliveryFailed);
    setText('registrationPendingError', deliveryFailed ? message : '', deliveryFailed);
    hide('registerEntry');
    show('registrationPending');
    byId('registrationPending')?.focus();
  }

  async function resendVerificationEmail(email, {button, successId, errorId}) {
    setText(successId, '', false);
    setText(errorId, '', false);
    if (!email) {
      setText(errorId, 'Enter your email first.');
      return;
    }
    button.disabled = true;
    try {
      const {response, data} = await authRequest('/api/auth/resend-verification', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email}),
      }, 'Sending the verification email took too long. Check your inbox before retrying.');
      const message = data.message || data.error || 'Request completed.';
      setText(response.ok ? successId : errorId, message);
    } catch (error) {
      setText(errorId, error.message || 'Verification email could not be sent. Check your connection and try again.');
    } finally {
      button.disabled = false;
    }
  }

  function showVerificationResult(value) {
    const messages = {
      success: 'Email verified. You can sign in now.',
      already_verified: 'This email is already verified.',
      failed: 'That verification link is invalid, expired, or already used. Enter your email below to resend verification, or sign in if verification already completed.',
    };
    if (!messages[value]) return;
    setText(value === 'failed' ? 'loginError' : 'loginSuccess', messages[value]);
    if (value === 'failed') {
      show('verificationNeeded');
      byId('loginEmail')?.focus({preventScroll: true});
    }
  }

  async function bootstrap() {
    captureCreationIntent();
    capturePlanIntent();
    const params = new URLSearchParams(location.search);
    const signupRequested = params.get('signup') === '1';
    const resetToken = params.get('token');
    if (resetToken) {
      showAuth('reset');
      byId('resetPasswordForm').dataset.token = resetToken;
      history.replaceState({}, document.title, location.pathname);
      return;
    }

    const verification = params.get('verification');
    if (verification) {
      history.replaceState({}, document.title, location.pathname);
    }

    if (signupRequested) {
      showAuth('register');
    } else {
      showReturningVisitorGate();
    }

    const bootstrapAuthFlowRevision = authFlowRevision;
    await window.CrumpAPI?.ready;
    const session = await window.deviceAuth.checkSession();
    if (authFlowRevision !== bootstrapAuthFlowRevision) return;
    if (session.unavailable) {
      if (!signupRequested) {
        showAuth('login');
        setText(
          'loginError',
          'Ask Crump could not verify your existing session right now. Your saved sign-in was preserved; try again in a moment.',
        );
      }
      if (verification) showVerificationResult(verification);
      return;
    }
    if (!session.authenticated || !session.data?.user) {
      if (!signupRequested) showAuth('login');
      if (signupRequested) trackSignupIntent('deep-link');
      if (verification) showVerificationResult(verification);
      return;
    }
    activeUser = session.data.user;
    window.currentUser = activeUser;
    window.configureUserStorage?.(activeUser.id);
    applyServerSettings(session.data.settings);
    routeAuthenticatedUser(activeUser);
    if (verification) showVerificationResult(verification);
  }

  function wireNavigation() {
    byId('showRegisterLink')?.addEventListener('click', event => {
      event.preventDefault();
      showAuth('register');
      trackSignupIntent('auth-link');
    });
    byId('showLoginLink')?.addEventListener('click', event => { event.preventDefault(); showAuth('login'); });
    byId('showForgotPasswordLink')?.addEventListener('click', event => { event.preventDefault(); showAuth('forgot'); });
    byId('showLoginFromForgot')?.addEventListener('click', event => { event.preventDefault(); showAuth('login'); });
    byId('showLoginFromReset')?.addEventListener('click', event => {
      event.preventDefault();
      const resetForm = byId('resetPasswordForm');
      if (resetForm) delete resetForm.dataset.token;
      history.replaceState({}, document.title, location.pathname);
      showAuth('login');
    });
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
        const {response, data} = await authRequest('/api/account/accept-terms', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version: TERMS_VERSION }),
        }, 'Saving your acceptance took too long. Try Continue again.');
        if (!response.ok || !data.success) throw new Error(data.error || 'Could not save your acceptance.');
        activeUser = data.user || { ...activeUser, termsAcceptedAt: new Date().toISOString(), termsVersion: TERMS_VERSION };
        window.currentUser = activeUser;
        hide('tosModal');
        startApp();
        if (!activeUser.fullName) maybeOfferProfileSetup();
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

  function passwordRuleState(password) {
    return {
      length: password.length >= 10,
      withinLimit: password.length <= 256,
      letter: /[A-Za-z]/.test(password),
      number: /\d/.test(password),
    };
  }

  function validatePasswordInput(password) {
    const rules = passwordRuleState(password);
    if (!rules.length) return 'Password must be at least 10 characters long.';
    if (!rules.withinLimit) return 'Password is too long.';
    if (!rules.letter || !rules.number) {
      return 'Password must contain at least one letter and one number.';
    }
    return null;
  }

  function updateRegistrationPasswordGuidance({ touched = false } = {}) {
    const input = byId('registerPassword');
    const hint = byId('registerPasswordHint');
    const status = byId('registerPasswordStatus');
    if (!input || !hint || !status) return;

    if (touched) input.dataset.passwordTouched = 'true';
    const value = input.value || '';
    const rules = passwordRuleState(value);
    const ruleNames = {
      length: '10 or more characters',
      letter: 'one letter',
      number: 'one number',
    };
    const missing = [];

    for (const [rule, label] of Object.entries(ruleNames)) {
      const item = hint.querySelector(`[data-password-rule="${rule}"]`);
      const met = rules[rule];
      item?.classList.toggle('is-met', met);
      const marker = item?.querySelector('i');
      if (marker) marker.textContent = met ? '✓' : '○';
      if (!met) missing.push(label);
    }

    const complete = missing.length === 0 && rules.withinLimit;
    if (!value) input.removeAttribute('aria-invalid');
    else if (input.dataset.passwordTouched === 'true') input.setAttribute('aria-invalid', String(!complete));

    const stateKey = `${Number(rules.length)}${Number(rules.letter)}${Number(rules.number)}${Number(rules.withinLimit)}`;
    if (input.dataset.passwordRuleState === stateKey) return;
    input.dataset.passwordRuleState = stateKey;
    if (!value) status.textContent = 'Password requires 10 or more characters, one letter, and one number.';
    else if (!rules.withinLimit) status.textContent = 'Password is too long.';
    else if (complete) status.textContent = 'Password meets all requirements.';
    else status.textContent = `Password still needs ${missing.join(', ')}.`;
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
    if (registerPassword) registerPassword.placeholder = 'Create a password';
    if (resetPassword) resetPassword.placeholder = '10+ characters with a letter and number';

    const resetHint = resetPassword?.parentElement?.querySelector('.form-hint');
    if (resetHint) resetHint.textContent = 'At least 10 characters with a letter and a number';
    updateRegistrationPasswordGuidance();
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
    const form = byId('loginFormElement');
    if (!form) return;
    let nativeValidationTracked = false;

    form.addEventListener('invalid', event => {
      if (nativeValidationTracked) return;
      nativeValidationTracked = true;
      setTimeout(() => { nativeValidationTracked = false; }, 0);
      const field = event.target;
      const isEmail = field?.id === 'loginEmail';
      const reason = isEmail
        ? (field.validity?.typeMismatch ? 'email_format' : 'email_required')
        : 'password_required';
      const message = reason === 'email_format'
        ? 'Enter a valid email address.'
        : (isEmail ? 'Enter your email.' : 'Enter your password.');
      field?.setAttribute('aria-invalid', 'true');
      setText('loginError', message);
      trackFunnel('LoginValidationFailed', {reason});
    }, true);

    form.addEventListener('input', event => {
      event.target?.removeAttribute('aria-invalid');
    }, {passive: true});

    form.addEventListener('submit', async event => {
      event.preventDefault();
      authFlowRevision += 1;
      setText('loginError', '', false);
      hide('verificationNeeded');
      trackFunnel('LoginSubmitted');
      const restore = setBusy(event.currentTarget, true, 'Signing in…');
      try {
        const result = await window.deviceAuth.login(byId('loginEmail').value.trim(), byId('loginPassword').value);
        if (!result.success || !result.data?.user) throw Object.assign(new Error(result.error || 'Sign in failed.'), { result });
        activeUser = result.data.user;
        window.currentUser = activeUser;
        window.configureUserStorage?.(activeUser.id);
        applyServerSettings(result.data.settings);
        setText('loginSuccess', 'Signed in.');
        trackFunnel('LoginCompleted');
        routeAuthenticatedUser(activeUser);
      } catch (error) {
        setText('loginError', error.message || 'Network error. Try again.');
        trackFunnel('LoginFailed', {
          reason: error.result?.needsVerification ? 'verification_required' : 'request_failed',
        });
        if (error.result?.needsVerification) show('verificationNeeded');
      } finally {
        restore();
      }
    });
  }

  function wireRegistration() {
    const form = byId('registerFormElement');
    if (!form) return;
    const passwordInput = byId('registerPassword');
    let signupStartedTracked = false;
    let credentialsReadyTracked = false;
    let nativeValidationTracked = false;

    const trackSignupStarted = () => {
      if (signupStartedTracked) return;
      signupStartedTracked = true;
      const deepLinked = new URLSearchParams(location.search).get('signup') === '1';
      trackSignupIntent(deepLinked ? 'deep-link' : 'registration');
      trackFunnel('SignupStarted');
    };

    const trackCredentialsReady = () => {
      trackSignupStarted();
      updateRegistrationPasswordGuidance();
      if (credentialsReadyTracked) return;
      const email = byId('registerEmail');
      const password = byId('registerPassword');
      if (!email?.value.trim() || !email.validity.valid || validatePasswordInput(password?.value || '')) return;
      credentialsReadyTracked = true;
      trackFunnel('SignupCredentialsReady');
    };

    // showAuth() deliberately moves focus to the first field for keyboard and
    // screen-reader users. Focus alone therefore is not evidence that a person
    // began registration. The first input (or a direct autofill submit below)
    // records the milestone without collecting field values.
    form.addEventListener('input', trackCredentialsReady, {passive: true});

    passwordInput?.addEventListener('blur', () => updateRegistrationPasswordGuidance({touched: true}));

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
      authFlowRevision += 1;
      setText('registerError', '', false);
      setText('registerSuccess', '', false);
      const password = byId('registerPassword').value;
      const passwordError = validatePasswordInput(password);
      if (passwordError) {
        updateRegistrationPasswordGuidance({touched: true});
        const reason = password.length < 10 ? 'password_length' : 'password_rules';
        trackFunnel('SignupValidationFailed', {reason});
        return setText('registerError', passwordError);
      }
      trackCredentialsReady();
      trackFunnel('SignupSubmitted');
      const restore = setBusy(event.currentTarget, true, 'Creating account…');
      try {
        const email = byId('registerEmail').value.trim();
        const {response, data} = await authRequest('/api/auth/register', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email,
            password,
            fullName: byId('registerName')?.value.trim() || '',
            source: funnelContext().acquisition,
          }),
        }, 'Creating your account took too long to confirm. Check your inbox before retrying; the account may already exist.');
        if (!response.ok || !data.success) {
          if (data.accountCreated && data.needsVerification) {
            trackFunnel('AccountCreated', {verification_delivery: 'failed'});
            showRegistrationPending(
              email,
              data.error || 'Your account exists, but the verification email could not be delivered. Use Resend verification email to try again.',
              {deliveryFailed: true},
            );
            return;
          }
          throw new Error(data.error || 'Registration failed.');
        }
        trackFunnel('AccountCreated', {verification_delivery: 'sent'});
        showRegistrationPending(email, data.message || 'Verification email sent.');
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
        const {response, data} = await authRequest('/api/auth/forgot-password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: byId('forgotPasswordEmail').value.trim() }) }, 'Sending the reset email took too long. Check your inbox before retrying.');
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
        const {response, data} = await authRequest('/api/auth/reset-password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: byId('resetPasswordForm').dataset.token, newPassword: password }) }, 'Updating your password took too long to confirm. Try signing in before submitting it again.');
        if (!response.ok) throw new Error(data.error || 'Password reset failed.');
        const resetForm = byId('resetPasswordForm');
        if (resetForm) delete resetForm.dataset.token;
        history.replaceState({}, document.title, location.pathname);
        showAuth('login');
        setText('loginSuccess', data.message || 'Password updated. Sign in with your new password.');
      } catch (error) { setText('resetPasswordError', error.message); }
      finally { restore(); }
    });

    byId('resendVerificationBtn')?.addEventListener('click', event => {
      void resendVerificationEmail(byId('loginEmail').value.trim(), {
        button: event.currentTarget,
        successId: 'loginSuccess',
        errorId: 'loginError',
      });
    });

    byId('registrationPendingResendBtn')?.addEventListener('click', event => {
      void resendVerificationEmail(byId('registrationPendingEmail').textContent.trim(), {
        button: event.currentTarget,
        successId: 'registrationPendingSuccess',
        errorId: 'registrationPendingError',
      });
    });

    byId('registrationPendingSigninBtn')?.addEventListener('click', () => {
      showAuth('login');
      hide('verificationNeeded');
      setText('loginError', '', false);
      setText('loginSuccess', 'Email ready. Sign in after completing verification.');
    });
  }

  window.completeOnboarding = async function completeOnboarding() {
    const name = byId('onboardingName').value.trim();
    setText('onboardingError', '', false);
    if (!name) {
      setText('onboardingError', 'Enter a name or choose Not now.');
      byId('onboardingName')?.focus();
      return;
    }
    const button = byId('onboardingContinueBtn');
    const skip = byId('onboardingSkipBtn');
    const original = button?.textContent || 'Save name';
    if (button) {
      button.disabled = true;
      button.textContent = 'Saving…';
    }
    if (skip) skip.disabled = true;
    try {
      const {response, data} = await authRequest('/api/account/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fullName: name }),
      }, 'Saving your profile took too long. Try again or choose Not now.');
      if (!response.ok || !data.success) throw new Error(data.error || 'Could not save your profile.');
      activeUser = data.user || { ...activeUser, fullName: name };
      window.currentUser = activeUser;
      window.profileManager?.updateProfile?.({ name, email: activeUser.email, initial: name.charAt(0).toUpperCase() });
      localStorage.setItem(window.STORAGE_KEYS?.HAS_ONBOARDED || 'crump_has_onboarded', 'true');
      try { localStorage.removeItem(profileNudgeKey()); } catch (_) {}
      startApp();
    } catch (error) {
      setText('onboardingError', error.message || 'Could not save your name. Try again or choose Not now.');
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = original;
      }
      if (skip) skip.disabled = false;
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
    try {
      await window.deviceAuth.logout();
    } catch (error) {
      console.warn('[Auth] Sign-out confirmation unavailable:', error);
    } finally {
      location.replace('/app');
    }
  };

  window.restartTutorial = function restartTutorial() {
    window.closeSettings?.();
    window.tutorial?.restart?.();
  };

  document.addEventListener('DOMContentLoaded', () => {
    applyPasswordPolicyMarkup();
    wirePasswordVisibility();
    byId('onboardingContinueBtn')?.addEventListener('click', () => window.completeOnboarding());
    byId('onboardingSkipBtn')?.addEventListener('click', dismissProfileSetup);
    byId('v1ProfileNudgeAdd')?.addEventListener('click', openProfileSetup);
    byId('v1ProfileNudgeDismiss')?.addEventListener('click', dismissProfileSetup);
    window.addEventListener('crump:profile-updated', maybeOfferProfileSetup);
    byId('onboardingModal')?.addEventListener('keydown', event => {
      if (event.key === 'Escape') dismissProfileSetup();
    });
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
