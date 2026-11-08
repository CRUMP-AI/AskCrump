(() => {
  'use strict';

  const STEPS = Object.freeze([
    {
      destination: 'Home', action: 'home', actionLabel: 'Open Home', eyebrow: 'HOME',
      title: 'Start with the outcome.',
      content: 'Home brings your recent work, useful starts, and the Ask Crump composer into one calm place. You can ask, research, create, or return to work without choosing a technical tool first.',
      icon: '⌂', features: ['Ask naturally', 'Research with sources', 'Continue recent work'],
    },
    {
      destination: 'Chats', action: 'chats', actionLabel: 'Open Chats', eyebrow: 'CHATS',
      title: 'Every conversation, easy to find.',
      content: 'Chats opens your private conversation history without taking you away from the work. Select a conversation, start a new one, or close the drawer and keep going.',
      icon: '◫', features: ['Recent conversations', 'Open and return', 'Private to your account'],
    },
    {
      destination: 'Projects', action: 'projects', actionLabel: 'Open Projects', eyebrow: 'PROJECTS',
      title: 'Give continuing work a home.',
      content: 'Projects keep conversations, files, context, outputs, and longer-running work together so you can return without rebuilding the brief.',
      icon: '▣', features: ['Named workspaces', 'Context and files together', 'Durable activity'],
    },
    {
      destination: 'Library', action: 'library', actionLabel: 'Open Library', eyebrow: 'LIBRARY',
      title: 'Keep manuscripts organized.',
      content: 'Library is the calm shelf for your books and manuscripts. Open a title and return to the current manuscript without digging through old conversations.',
      icon: '▱', features: ['Books and manuscripts', 'Private reading shelf', 'Open the current manuscript'],
    },
    {
      destination: 'Studios', action: 'studios', actionLabel: 'Open Studios', eyebrow: 'STUDIOS',
      title: 'Make visuals in one place.',
      content: 'Studios opens the real Image and Video tools. Create or edit an image, generate motion, and return to saved jobs without crowding the main workspace. Choose Apply changes to return to the conversation with the edited image.',
      icon: '✦', features: ['Image creation and editing', 'Video generation', 'Saved results'],
    },
    {
      destination: 'You', action: 'you', actionLabel: 'Open You', eyebrow: 'YOU',
      title: 'Your account has one clear home.',
      content: 'You opens your profile, preferences, plan and credits, account controls, product guidance, and legal information.',
      icon: '○', features: ['Profile and preferences', 'Plan and credits', 'Privacy and account controls'],
    },
  ]);

  const DESKTOP_DESTINATIONS = Object.freeze(['Home', 'Chats', 'Projects', 'Library', 'Studios', 'You']);
  const MOBILE_DESTINATIONS = Object.freeze(['Home', 'Chats', 'Projects', 'Library', 'Studios', 'You']);
  const MOBILE_MORE_DESTINATIONS = Object.freeze([]);

  class Tutorial {
    constructor() {
      this.currentStep = 0;
      this.isActive = false;
      this.lastFocusedElement = null;
      this.boundKeydown = event => this.handleKeydown(event);
    }

    storageKey() {
      const userId = String(window.currentUser?.id || 'guest').replace(/[^a-zA-Z0-9_-]/g, '');
      return `crump_tutorial_completed_v9:${userId || 'guest'}`;
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
      markIcon.src = '/assets/brand/crump-mark-320.webp';
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

      const destinationMaps = document.createElement('div');
      destinationMaps.className = 'tutorial-destination-maps';
      const destinationMap = this.destinationMap('Desktop', DESKTOP_DESTINATIONS, step.destination);
      const mobileDestination = MOBILE_MORE_DESTINATIONS.includes(step.destination) ? 'More' : step.destination;
      const mobileDestinationMap = this.destinationMap('Mobile', MOBILE_DESTINATIONS, mobileDestination);
      destinationMaps.append(destinationMap, mobileDestinationMap);

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

      body.append(visual, progressLabel, eyebrow, title, description, destinationMaps, featureGrid, openDestination);

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

    destinationMap(label, destinations, current) {
      const group = document.createElement('div');
      group.className = 'tutorial-destination-group';
      const groupLabel = document.createElement('strong');
      groupLabel.textContent = label;
      const map = document.createElement('div');
      map.className = 'tutorial-destination-map';
      map.setAttribute('aria-label', `${label} Ask Crump destinations`);
      for (const destination of destinations) {
        const item = document.createElement('span');
        item.textContent = destination;
        if (destination === current) {
          item.classList.add('is-current');
          item.setAttribute('aria-current', 'step');
        }
        map.appendChild(item);
      }
      group.append(groupLabel, map);
      return group;
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
      if (!['home', 'chats', 'projects', 'library', 'studios', 'you'].includes(normalized)) return;
      localStorage.setItem(this.storageKey(), 'true');
      this.stop();
      requestAnimationFrame(() => {
        if (typeof window.CrumpVision?.navigate === 'function') {
          window.CrumpVision.navigate(normalized);
          return;
        }
        if (typeof window.CrumpNavigation5930?.open === 'function') {
          if (normalized === 'chats') {
            document.getElementById('menuBtn')?.click();
            return;
          }
          const legacyDestination = {home: 'ask', studios: 'video', you: 'you'}[normalized] || normalized;
          window.CrumpNavigation5930.open(legacyDestination);
          return;
        }
        if (normalized === 'home') {
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
