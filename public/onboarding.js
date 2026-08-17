(() => {
  'use strict';

  const STEPS = Object.freeze([
    {
      eyebrow: 'WELCOME TO ASK CRUMP',
      title: 'One place for work that keeps moving.',
      content: 'Ask naturally, keep the conversation, and come back later without treating every session like a blank page.',
      icon: '✦',
      features: ['Natural conversation', 'Account sync', 'Persistent history'],
    },
    {
      eyebrow: 'PROJECTS',
      title: 'Give important work its own world.',
      content: 'Projects keep instructions, canon, reference files, manuscripts, conversations, and decisions together so unrelated work stays separate.',
      icon: '▣',
      features: ['Project context', 'Canon & notes', 'Reference files'],
    },
    {
      eyebrow: 'CREATE WITH CRUMP',
      title: 'Move from an answer to a deliverable.',
      content: 'Research current information, create or edit images, build documents, and develop long-form manuscripts without leaving the workspace.',
      icon: '+',
      features: ['Research', 'Images & documents', 'Long-form manuscripts'],
    },
    {
      eyebrow: 'VIDEO STUDIO',
      title: 'Create a scene. Then keep directing it.',
      content: 'Choose Quick, Extendable, or Cinematic video. Extendable scenes can continue from their ending, while finished work is saved privately to your Library.',
      icon: '▶',
      features: ['Quick video', 'Continue scenes', 'Cinematic generation'],
    },
    {
      eyebrow: 'SAVED LIBRARY',
      title: 'Keep what you make.',
      content: 'Generated videos, images, documents, manuscript exports, and uploads stay attached to your account so you can open them again across devices.',
      icon: '▱',
      features: ['Private storage', 'Cross-device access', 'Reusable creations'],
    },
    {
      eyebrow: 'YOU ARE READY',
      title: 'Start messy. Crump can help organize the rest.',
      content: 'Ask a question, attach a file, start a Project, or create something. You can replay this tour from Settings whenever you want a refresher.',
      icon: '→',
      features: ['No special commands', 'Your controls stay visible', 'Keep building'],
    },
  ]);

  class Tutorial {
    constructor() {
      this.currentStep = 0;
      this.isActive = false;
      this.lastFocusedElement = null;
      this.boundKeydown = event => this.handleKeydown(event);
    }

    storageKey() {
      const userId = String(window.currentUser?.id || 'guest').replace(/[^a-zA-Z0-9_-]/g, '');
      return `crump_tutorial_completed_v5:${userId || 'guest'}`;
    }

    isComplete() {
      return localStorage.getItem(this.storageKey()) === 'true';
    }

    autoStart() {
      if (this.isActive || this.isComplete() || !window.currentUser?.id) return;
      const app = document.getElementById('appContainer');
      if (!app || getComputedStyle(app).display === 'none') return;
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

      body.append(visual, progressLabel, eyebrow, title, description, featureGrid);

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
