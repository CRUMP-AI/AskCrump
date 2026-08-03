(() => {
  'use strict';

  const STEPS = Object.freeze([
    {
      title: 'Welcome to Ask Crump',
      content: 'Your conversations now follow your account across devices. Here is a quick tour of the controls you will use most.',
      target: null,
      position: 'center',
    },
    {
      title: 'Start a conversation',
      content: 'Type a message here. Press Enter to send, or Shift+Enter for a new line.',
      target: '.input-container',
      position: 'top',
    },
    {
      title: 'Use quick actions',
      content: 'Generate an image, search current information, or begin a coding request without writing the full prompt yourself.',
      target: '.quick-actions',
      position: 'top',
    },
    {
      title: 'Attach a file',
      content: 'Add an image or PDF for analysis. Files are sent only with the message where you attach them.',
      target: '#attachBtn',
      position: 'top',
    },
    {
      title: 'Find every conversation',
      content: 'Open the sidebar to create, rename, search, or return to synchronized conversations.',
      target: '#menuBtn',
      position: 'right',
    },
    {
      title: 'Control your account',
      content: 'Settings includes preferences, billing, signed-in devices, export, sign out, and permanent account deletion.',
      target: '#settingsBtn',
      position: 'right',
    },
    {
      title: 'You are ready',
      content: 'Ask a question, continue a conversation from another device, or explore at your own pace. You can restart this tour from Settings.',
      target: null,
      position: 'center',
    },
  ]);

  class Tutorial {
    constructor() {
      this.currentStep = 0;
      this.isActive = false;
      this.highlightedElement = null;
      this.boundReposition = () => this.renderCurrentPosition();
    }

    storageKey() {
      const userId = String(window.currentUser?.id || 'guest').replace(/[^a-zA-Z0-9_-]/g, '');
      return `crump_tutorial_completed_v3:${userId || 'guest'}`;
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
      window.addEventListener('resize', this.boundReposition, { passive: true });
      window.addEventListener('orientationchange', this.boundReposition, { passive: true });
      this.showStep();
    }

    showStep() {
      this.cleanupNodes();
      const step = STEPS[this.currentStep];
      const overlay = document.createElement('div');
      overlay.id = 'tutorialOverlay';
      overlay.className = 'tutorial-overlay';
      overlay.addEventListener('click', event => {
        if (event.target === overlay) this.skip();
      });

      const card = document.createElement('section');
      card.id = 'tutorialCard';
      card.className = 'tutorial-card';
      card.setAttribute('role', 'dialog');
      card.setAttribute('aria-modal', 'true');
      card.setAttribute('aria-labelledby', 'tutorialTitle');

      const sheet = document.createElement('div');
      sheet.className = 'tutorial-card-content tutorial-sheet';

      const header = document.createElement('div');
      header.className = 'tutorial-sheet-header';
      const headerLeft = document.createElement('div');
      headerLeft.className = 'tutorial-header-left';
      const title = document.createElement('h3');
      title.id = 'tutorialTitle';
      title.className = 'tutorial-title';
      title.textContent = step.title;
      const counter = document.createElement('span');
      counter.className = 'tutorial-step-counter';
      counter.textContent = `Step ${this.currentStep + 1} of ${STEPS.length}`;
      headerLeft.append(title, counter);
      const close = this.button('×', 'tutorial-close', () => this.skip());
      close.setAttribute('aria-label', 'Close tutorial');
      header.append(headerLeft, close);

      const body = document.createElement('div');
      body.className = 'tutorial-sheet-body';
      const description = document.createElement('p');
      description.className = 'tutorial-description';
      description.textContent = step.content;
      const progress = document.createElement('div');
      progress.className = 'tutorial-progress';
      progress.setAttribute('aria-hidden', 'true');
      const track = document.createElement('div');
      track.className = 'tutorial-progress-bar';
      const fill = document.createElement('div');
      fill.className = 'tutorial-progress-fill';
      fill.style.width = `${((this.currentStep + 1) / STEPS.length) * 100}%`;
      track.append(fill);
      progress.append(track);
      body.append(description, progress);

      const actions = document.createElement('div');
      actions.className = 'tutorial-actions tutorial-sheet-actions';
      if (this.currentStep > 0) {
        actions.append(this.button('Previous', 'tutorial-btn tutorial-btn-secondary', () => this.back()));
      } else {
        actions.append(this.button('Skip', 'tutorial-btn tutorial-btn-secondary', () => this.skip()));
      }
      actions.append(this.button(
        this.currentStep === STEPS.length - 1 ? 'Get Started' : 'Next',
        'tutorial-btn tutorial-btn-primary',
        () => this.next(),
      ));

      sheet.append(header, body, actions);
      card.append(sheet);
      document.body.append(overlay, card);
      this.positionCard(card, step);
      requestAnimationFrame(() => {
        overlay.classList.add('tutorial-visible');
        card.classList.add('tutorial-visible');
        close.focus({ preventScroll: true });
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

    positionCard(card, step) {
      const target = step.target ? document.querySelector(step.target) : null;
      if (!target || !target.getClientRects().length) {
        card.classList.add('tutorial-card-center');
        return;
      }

      this.highlight(target);
      const rect = target.getBoundingClientRect();
      const margin = 16;
      const cardWidth = Math.min(560, window.innerWidth - (margin * 2));
      card.style.width = `${cardWidth}px`;
      card.style.maxWidth = `${cardWidth}px`;
      card.style.position = 'fixed';
      card.style.transform = 'none';

      requestAnimationFrame(() => {
        const measured = card.getBoundingClientRect();
        let left = rect.left + (rect.width - measured.width) / 2;
        let top;
        if (step.position === 'right' && rect.right + margin + measured.width <= window.innerWidth) {
          left = rect.right + margin;
          top = rect.top + (rect.height - measured.height) / 2;
        } else if (step.position === 'top' && rect.top - margin - measured.height >= 0) {
          top = rect.top - margin - measured.height;
        } else {
          top = Math.min(rect.bottom + margin, window.innerHeight - measured.height - margin);
        }
        left = Math.max(margin, Math.min(left, window.innerWidth - measured.width - margin));
        top = Math.max(margin, Math.min(top, window.innerHeight - measured.height - margin));
        card.style.left = `${left}px`;
        card.style.top = `${top}px`;
      });
    }

    highlight(element) {
      this.highlightedElement = element;
      element.classList.add('tutorial-target-active');
      const highlight = document.createElement('div');
      highlight.id = 'tutorialHighlight';
      highlight.className = 'tutorial-highlight';
      const rect = element.getBoundingClientRect();
      highlight.style.top = `${Math.max(0, rect.top - 8)}px`;
      highlight.style.left = `${Math.max(0, rect.left - 8)}px`;
      highlight.style.width = `${Math.min(window.innerWidth, rect.width + 16)}px`;
      highlight.style.height = `${Math.min(window.innerHeight, rect.height + 16)}px`;
      document.body.append(highlight);
    }

    renderCurrentPosition() {
      if (!this.isActive) return;
      this.showStep();
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
      if (!skipped) window.showToast?.('Ask Crump is ready.', 'success');
    }

    restart() {
      localStorage.removeItem(this.storageKey());
      this.stop();
      this.start({ force: true });
    }

    stop() {
      this.isActive = false;
      window.removeEventListener('resize', this.boundReposition);
      window.removeEventListener('orientationchange', this.boundReposition);
      this.cleanupNodes();
    }

    cleanupNodes() {
      document.getElementById('tutorialOverlay')?.remove();
      document.getElementById('tutorialCard')?.remove();
      document.getElementById('tutorialHighlight')?.remove();
      this.highlightedElement?.classList.remove('tutorial-target-active');
      this.highlightedElement = null;
    }
  }

  window.Tutorial = Tutorial;
  window.tutorial = new Tutorial();
})();
