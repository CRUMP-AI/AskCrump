// ==========================================
// CRUMP AI - PROFESSIONAL TUTORIAL v3.0
// First-time only, matches navy/gold aesthetic
// ==========================================

class Tutorial {
    constructor() {
        this.currentStep = 0;
        this.steps = [
            {
                title: "Welcome to Crump AI",
                content: "Your personal AI assistant powered by the <strong>N² Engine</strong>. Let's show you around.",
                icon: "👋",
                highlight: null
            },
            {
                title: "Send Messages",
                content: "Type your message in the input box and press <strong>Send</strong> or <strong>Shift + Enter</strong>. Ask me anything!",
                icon: "💬",
                highlight: ".input-container"
            },
            {
                title: "Quick Actions",
                content: "Use quick action buttons for common tasks like <strong>Image Generation</strong>, <strong>Web Search</strong>, and <strong>Code Assistance</strong>.",
                icon: "⚡",
                highlight: ".quick-actions"
            },
            {
                title: "File Uploads",
                content: "Click the <strong>attach button</strong> to upload images, PDFs, or documents for analysis. Max 5MB per file.",
                icon: "📎",
                highlight: "#attachBtn"
            },
            {
                title: "Voice Input",
                content: "Use the <strong>microphone button</strong> to speak your messages instead of typing.",
                icon: "🎤",
                highlight: "#voiceBtn"
            },
            {
                title: "Conversations",
                content: "All your chats are saved in the <strong>sidebar</strong>. Create new conversations anytime with the <strong>New Conversation</strong> button.",
                icon: "💾",
                highlight: ".sidebar-actions"
            },
            {
                title: "Settings & Upgrades",
                content: "Access <strong>Settings</strong> to customize your experience and view your <strong>tier limits</strong>. Upgrade anytime for more features!",
                icon: "⚙️",
                highlight: "#settingsBtn"
            },
            {
                title: "You're All Set!",
                content: "You're ready to start using Crump AI. Remember: you have <strong>100 messages</strong>, <strong>10 images</strong>, and <strong>20 searches</strong> per month on the free tier. Enjoy!",
                icon: "🚀",
                highlight: null
            }
        ];
    }

    start() {
        // Check if tutorial already completed
        if (localStorage.getItem('crump_tutorial_completed') === 'true') {
            console.log('📚 Tutorial already completed');
            return;
        }

        console.log('📚 Starting tutorial...');
        this.currentStep = 0;
        this.showStep();
    }

    showStep() {
        const step = this.steps[this.currentStep];
        
        // Remove existing tutorial
        this.removeTutorial();
        
        // Create tutorial overlay
        const overlay = document.createElement('div');
        overlay.id = 'tutorialOverlay';
        overlay.style.cssText = `
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(4px);
            z-index: 9998;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.3s ease;
        `;

        // Create tutorial card
        const card = document.createElement('div');
        card.style.cssText = `
            background: var(--color-surface);
            border: 2px solid var(--color-accent-primary);
            border-radius: 20px;
            padding: 3rem 2.5rem;
            max-width: 500px;
            width: 90%;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            animation: slideUp 0.4s ease;
            text-align: center;
        `;

        card.innerHTML = `
            <div style="font-size: 4rem; margin-bottom: 1rem;">${step.icon}</div>
            <h2 style="font-family: var(--font-display); font-size: 2rem; color: var(--color-accent-primary); margin-bottom: 1rem;">${step.title}</h2>
            <p style="color: var(--color-text-secondary); font-size: 1.125rem; line-height: 1.7; margin-bottom: 2rem;">${step.content}</p>
            
            <div style="display: flex; gap: 1rem; align-items: center; justify-content: center;">
                ${this.currentStep > 0 ? `
                    <button id="tutorialBack" style="
                        padding: 0.75rem 1.5rem;
                        background: var(--color-bg-tertiary);
                        border: 1px solid var(--color-border);
                        border-radius: 8px;
                        color: var(--color-text-primary);
                        font-size: 1rem;
                        font-weight: 600;
                        cursor: pointer;
                        transition: all 0.2s ease;
                    ">← Back</button>
                ` : ''}
                
                <button id="tutorialNext" style="
                    padding: 0.75rem 2rem;
                    background: var(--color-accent-primary);
                    border: none;
                    border-radius: 8px;
                    color: var(--color-bg-primary);
                    font-size: 1rem;
                    font-weight: 700;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    flex: 1;
                    max-width: 200px;
                ">${this.currentStep === this.steps.length - 1 ? 'Get Started!' : 'Next →'}</button>
            </div>
            
            <div style="margin-top: 1.5rem; color: var(--color-text-tertiary); font-size: 0.875rem;">
                Step ${this.currentStep + 1} of ${this.steps.length}
            </div>
            
            <button id="tutorialSkip" style="
                margin-top: 1rem;
                padding: 0.5rem;
                background: transparent;
                border: none;
                color: var(--color-text-tertiary);
                font-size: 0.875rem;
                cursor: pointer;
                text-decoration: underline;
            ">Skip tutorial</button>
        `;

        overlay.appendChild(card);
        document.body.appendChild(overlay);

        // Highlight element if specified
        if (step.highlight) {
            this.highlightElement(step.highlight);
        }

        // Add event listeners
        const nextBtn = document.getElementById('tutorialNext');
        const backBtn = document.getElementById('tutorialBack');
        const skipBtn = document.getElementById('tutorialSkip');

        if (nextBtn) {
            nextBtn.addEventListener('click', () => this.next());
        }
        if (backBtn) {
            backBtn.addEventListener('click', () => this.back());
        }
        if (skipBtn) {
            skipBtn.addEventListener('click', () => this.skip());
        }

        // Add animations
        const style = document.createElement('style');
        style.textContent = `
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes slideUp {
                from { transform: translateY(30px); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }
            @keyframes pulse {
                0%, 100% { box-shadow: 0 0 0 0 rgba(201, 184, 146, 0.7); }
                50% { box-shadow: 0 0 0 15px rgba(201, 184, 146, 0); }
            }
        `;
        document.head.appendChild(style);
    }

    highlightElement(selector) {
        const element = document.querySelector(selector);
        if (!element) return;

        // Add highlight effect
        const originalPosition = element.style.position;
        const originalZIndex = element.style.zIndex;
        
        element.style.position = 'relative';
        element.style.zIndex = '9999';
        element.style.boxShadow = '0 0 0 4px var(--color-accent-primary)';
        element.style.borderRadius = '8px';
        element.style.animation = 'pulse 2s infinite';

        // Store for cleanup
        element.dataset.tutorialHighlight = 'true';
        element.dataset.originalPosition = originalPosition;
        element.dataset.originalZIndex = originalZIndex;
    }

    removeHighlights() {
        document.querySelectorAll('[data-tutorial-highlight="true"]').forEach(el => {
            el.style.position = el.dataset.originalPosition || '';
            el.style.zIndex = el.dataset.originalZIndex || '';
            el.style.boxShadow = '';
            el.style.animation = '';
            delete el.dataset.tutorialHighlight;
            delete el.dataset.originalPosition;
            delete el.dataset.originalZIndex;
        });
    }

    next() {
        this.removeHighlights();
        
        if (this.currentStep < this.steps.length - 1) {
            this.currentStep++;
            this.showStep();
        } else {
            this.complete();
        }
    }

    back() {
        this.removeHighlights();
        
        if (this.currentStep > 0) {
            this.currentStep--;
            this.showStep();
        }
    }

    skip() {
        if (confirm('Are you sure you want to skip the tutorial? You can restart it anytime from Settings.')) {
            this.complete();
        }
    }

    complete() {
        this.removeTutorial();
        this.removeHighlights();
        localStorage.setItem('crump_tutorial_completed', 'true');
        console.log('✅ Tutorial completed');
        
        // Show completion toast
        if (window.showNotification) {
            window.showNotification('🎉 Tutorial completed! Welcome to Crump AI', 'success');
        }
    }

    removeTutorial() {
        const overlay = document.getElementById('tutorialOverlay');
        if (overlay) {
            overlay.remove();
        }
    }

    restart() {
        localStorage.removeItem('crump_tutorial_completed');
        this.currentStep = 0;
        this.start();
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.Tutorial = Tutorial;
window.tutorial = new Tutorial();

// Auto-start on first load (after onboarding)
window.addEventListener('load', () => {
    const hasOnboarded = localStorage.getItem('crump_has_onboarded');
    const tutorialCompleted = localStorage.getItem('crump_tutorial_completed');
    
    // Start tutorial after onboarding, but only once
    if (hasOnboarded === 'true' && tutorialCompleted !== 'true') {
        setTimeout(() => {
            window.tutorial.start();
        }, 1000);
    }
});

console.log('✅ Tutorial System v3.0 loaded - First-time only');
