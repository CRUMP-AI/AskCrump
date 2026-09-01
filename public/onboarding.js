(() => {
  'use strict';

  const STEPS = Object.freeze([
    {
      destination: 'Ask',
      action: 'ask',
      actionLabel: 'Open Ask',
      eyebrow: 'ASK · CHATS',
      title: 'Start with the conversation.',
      content: 'Ask is where you think, research, and work with Crump. Chats opens your synchronized conversation history without turning it into a second application menu.',
      icon: '✦',
      features: ['Ask naturally', 'Research what changed', 'Return through Chats'],
    },
    {
      destination: 'Projects',
      action: 'projects',
      actionLabel: 'Open Projects',
      eyebrow: 'PROJECTS',
      title: 'Give continuing work a home.',
      content: 'Open Projects, then select a named Project to enter its dedicated workspace. Its conversations, instructions, notes, and reference files stay together so you can return without rebuilding the context.',
      icon: '▣',
      features: ['Open a named Project', 'Continue its conversations', 'Manage files & canon'],
    },
    {
      destination: 'Create',
      action: 'create',
      actionLabel: 'Open Create',
      eyebrow: 'CREATE',
      title: 'Choose the outcome you need.',
      content: 'Create opens the right workspace for documents, presentations, images, and manuscripts. For images, add a reference or choose Edit area after a result. Precision Edit lets you zoom, brush over only what may change, preview local warmth, exposure, and saturation, then save without AI credits or continue into a reviewed generative edit.',
      icon: '+',
      features: ['Editable files', 'Local image adjustments', 'Long-form manuscripts'],
    },
    {
      destination: 'Video',
      action: 'video',
      actionLabel: 'Open Video',
      eyebrow: 'VIDEO',
      title: 'Give motion its own studio.',
      content: 'Video opens a dedicated studio for Quick, Extendable, and Cinematic generation. Add optional visual references, leave while a job runs, then return here to check its saved status and result.',
      icon: '▶',
      features: ['Three generation modes', 'Optional image references', 'Return to active jobs'],
    },
    {
      destination: 'Library',
      action: 'library',
      actionLabel: 'Open Library',
      eyebrow: 'LIBRARY',
      title: 'Keep the things you create.',
      content: 'Library is your private bookshelf for manuscripts and books created with Crump or imported from your files. Documents, images, videos, exports, and uploads stay under Projects → Files. Conversation history remains in Chats.',
      icon: '▱',
      features: ['Private to your account', 'Across your devices', 'Open and reuse'],
    },
    {
      destination: 'You',
      action: 'you',
      actionLabel: 'Open You',
      eyebrow: 'YOU',
      title: 'Your account has one clear home.',
      content: 'You contains your profile, behavior preferences, plan and credits, account controls, product guidance, and legal information.',
      icon: '○',
      features: ['Profile & behavior', 'Plan & credits', 'Account & about'],
    },
  ]);

  const DESTINATIONS = Object.freeze(['Ask', 'Projects', 'Create', 'Video', 'Library', 'You']);

  class Tutorial {
    constructor() {
      this.currentStep = 0;
      this.isActive = false;
      this.lastFocusedElement = null;
      this.boundKeydown = event => this.handleKeydown(event);
    }

    storageKey() {
      const userId = String(window.currentUser?.id || 'guest').replace(/[^a-zA-Z0-9_-]/g, '');
      return `crump_tutorial_completed_v8:${userId || 'guest'}`;
    }

    isComplete() {
      return localStorage.getItem(this.storageKey()) === 'true';
    }

    autoStart() {
      if (this.isActive || this.isComplete() || !window.currentUser?.id) return;
      const app = document.getElementById('appContainer');
      if (!app || getComputedStyle(app).display === 'none') return;
      // The authenticated launchpad is already a task-oriented first-run
      // experience. Do not block a new user with passive tour screens
      // before they can ask their first question. The full tour remains
      // available from Settings and through restart().
      if (document.getElementById('v1Launchpad')) return;
      this.start();
    }

    start({ force = false } = {}) {
      if (this.isActive || (!force && this.isComplete())) return;
      this.currentStep = 0;
      this.isActive = true;
      this.lastFocusedElement = document.activeElement;
      document.body.classList.add('tutorial-open');
      document.addEventListener('keydown', this.boundKeydown);
      this.showStep();
    }

    handleKeydown(event) {
      if (!this.isActive) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        this.skip();
      }
      if (event.key === 'ArrowRight' && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        this.next();
      }
      if (event.key === 'ArrowLeft' && this.currentStep > 0 && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        this.back();
      }
      if (event.key === 'Tab') this.trapFocus(event);
    }

    trapFocus(event) {
      const card = document.getElementById('tutorialCard');
      if (!card) return;
      const items = [...card.querySelectorAll('button:not(:disabled), [href], input:not(:disabled)')];
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    showStep() {
      this.cleanupNodes();
      const step = STEPS[this.currentStep];

      const overlay = document.createElement('div');
      overlay.id = 'tutorialOverlay';
      overlay.className = 'tutorial-overlay';

      const card = document.createElement('section');
      card.id = 'tutorialCard';
      card.className = 'tutorial-card tutorial-card-center';
      card.setAttribute('role', 'dialog');
      card.setAttribute('aria-modal', 'true');
      card.setAttribute('aria-labelledby', 'tutorialTitle');
      card.setAttribute('aria-describedby', 'tutorialDescription');

      const topbar = document.createElement('div');
      topbar.className = 'tutorial-topbar';

      const mark = document.createElement('div');
      mark.className = 'tutorial-brand';
      const markIcon = document.createElement('img');
      markIcon.src = '/assets/brand/crump-mark.png';
      markIcon.alt = '';
      markIcon.className = 'tutorial-brand-icon';
      const brandText = document.createElement('span');
      brandText.textContent = 'Ask Crump';
      mark.append(markIcon, brandText);

      const skip = this.button('Skip', 'tutorial-skip', () => this.skip());
      topbar.append(mark, skip);

      const body = document.createElement('div');
      body.className = 'tutorial-body';

      const visual = document.createElement('div');
      visual.className = 'tutorial-visual';
      visual.textContent = step.icon;
      visual.setAttribute('aria-hidden', 'true');

      const progressLabel = document.createElement('div');
      progressLabel.className = 'tutorial-progress-label';
      progressLabel.textContent = `${this.currentStep + 1} / ${STEPS.length}`;

      const eyebrow = document.createElement('div');
      eyebrow.className = 'tutorial-eyebrow';
      eyebrow.textContent = step.eyebrow;

      const title = document.createElement('h2');
      title.id = 'tutorialTitle';
      title.className = 'tutorial-title';
      title.textContent = step.title;

      const description = document.createElement('p');
      description.id = 'tutorialDescription';
      description.className = 'tutorial-description';
      description.textContent = step.content;

      const destinationMap = document.createElement('div');
      destinationMap.className = 'tutorial-destination-map';
      destinationMap.setAttribute('aria-label', 'Ask Crump destinations');
      for (const destination of DESTINATIONS) {
        const item = document.createElement('span');
        item.textContent = destination;
        if (destination === step.destination) {
          item.classList.add('is-current');
          item.setAttribute('aria-current', 'step');
        }
        destinationMap.appendChild(item);
      }

      const featureGrid = document.createElement('div');
      featureGrid.className = 'tutorial-feature-grid';
      for (const feature of step.features) {
        const item = document.createElement('div');
        item.className = 'tutorial-feature';
        const dot = document.createElement('span');
        dot.className = 'tutorial-feature-dot';
        dot.setAttribute('aria-hidden', 'true');
        const label = document.createElement('span');
        label.textContent = feature;
        item.append(dot, label);
        featureGrid.appendChild(item);
      }

      const openDestination = this.button(
        `${step.actionLabel} →`,
        'tutorial-open-destination',
        () => this.openDestination(step.action),
      );
      openDestination.setAttribute('aria-label', `${step.actionLabel} and close the guide`);

      body.append(visual, progressLabel, eyebrow, title, description, destinationMap, featureGrid, openDestination);

      const footer = document.createElement('div');
      footer.className = 'tutorial-footer';

      const progress = document.createElement('div');
      progress.className = 'tutorial-dots';
      progress.setAttribute('aria-label', `Step ${this.currentStep + 1} of ${STEPS.length}`);
      STEPS.forEach((_item, index) => {
        const dot = document.createElement('span');
        dot.className = `tutorial-dot${index === this.currentStep ? ' active' : ''}`;
        progress.appendChild(dot);
      });

      const actions = document.createElement('div');
      actions.className = 'tutorial-actions';
      if (this.currentStep > 0) {
        actions.append(this.button('Back', 'tutorial-btn tutorial-btn-secondary', () => this.back()));
      }
      actions.append(this.button(
        this.currentStep === STEPS.length - 1 ? 'Enter workspace' : 'Continue',
        'tutorial-btn tutorial-btn-primary',
        () => this.next(),
      ));

      footer.append(progress, actions);
      card.append(topbar, body, footer);
      document.body.append(overlay, card);

      requestAnimationFrame(() => {
        overlay.classList.add('tutorial-visible');
        card.classList.add('tutorial-visible');
        card.querySelector('.tutorial-btn-primary')?.focus({ preventScroll: true });
      });
    }

    button(label, className, handler) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = className;
      button.textContent = label;
      button.addEventListener('click', handler);
      return button;
    }

    next() {
      if (this.currentStep < STEPS.length - 1) {
        this.currentStep += 1;
        this.showStep();
      } else {
        this.complete(false);
      }
    }

    back() {
      if (this.currentStep === 0) return;
      this.currentStep -= 1;
      this.showStep();
    }

    skip() {
      this.complete(true);
    }

    complete(skipped = false) {
      localStorage.setItem(this.storageKey(), 'true');
      this.stop();
      if (!skipped) window.showToast?.('Workspace ready.', 'success');
      document.getElementById('userInput')?.focus({ preventScroll: true });
    }

    openDestination(destination) {
      const normalized = String(destination || '').trim().toLowerCase();
      if (!['ask', 'projects', 'create', 'video', 'library', 'you'].includes(normalized)) return;
      localStorage.setItem(this.storageKey(), 'true');
      this.stop();
      requestAnimationFrame(() => {
        if (typeof window.CrumpNavigation5930?.open === 'function') {
          window.CrumpNavigation5930.open(normalized);
          return;
        }
        if (normalized === 'ask') {
          document.getElementById('userInput')?.focus({ preventScroll: true });
          return;
        }
        document.querySelector(
          `[data-crump5930-destination="${normalized}"], [data-v1-command="${normalized}"]`,
        )?.click();
      });
    }

    restart() {
      localStorage.removeItem(this.storageKey());
      this.stop();
      this.start({ force: true });
    }

    stop() {
      this.isActive = false;
      document.body.classList.remove('tutorial-open');
      document.removeEventListener('keydown', this.boundKeydown);
      this.cleanupNodes();
      if (this.lastFocusedElement?.isConnected) this.lastFocusedElement.focus?.({ preventScroll: true });
      this.lastFocusedElement = null;
    }

    cleanupNodes() {
      document.getElementById('tutorialOverlay')?.remove();
      document.getElementById('tutorialCard')?.remove();
    }
  }

  window.Tutorial = Tutorial;
  window.tutorial = new Tutorial();
})();
