// ==========================================
// CRUMP AI - PROFESSIONAL TUTORIAL SYSTEM v2.0
// Interactive feature walkthrough
// ==========================================

class Tutorial {
    constructor() {
        this.currentStep = 0;
        this.isActive = false;
        this.steps = [
            {
                title: "Welcome to Crump AI",
                content: "Your intelligent virtual assistant is ready to help. This tutorial will guide you through all available features.",
                target: null,
                position: "center",
                action: null
            },
            {
                title: "Chat Interface",
                content: "This is your main conversation area. All messages with your assistant appear here in real-time.",
                target: "#chatContainer",
                position: "center",
                action: null
            },
            {
                title: "Sending Messages",
                content: "Type your message in the input field below. Press Enter or click the send button to submit.",
                target: ".input-container",
                position: "top",
                action: () => {
                    const input = document.getElementById('userInput');
                    if (input) {
                        input.focus();
                        input.placeholder = "Try typing a message here...";
                    }
                }
            },
            {
                title: "Quick Actions",
                content: "Access common tasks instantly. Generate images, search the web, or get coding assistance with one click.",
                target: ".quick-actions",
                position: "top",
                action: () => {
                    const quickActions = document.querySelector('.quick-actions');
                    if (quickActions) {
                        quickActions.style.transform = 'scale(1.05)';
                        setTimeout(() => {
                            quickActions.style.transform = '';
                        }, 500);
                    }
                }
            },
            {
                title: "Image Generation",
                content: "Create AI-generated images from text descriptions. Click here and describe what you want to see.",
                target: ".quick-actions button:nth-child(1)",
                position: "top",
                action: null
            },
            {
                title: "Web Search",
                content: "Search the internet for current information, news, or answers to questions requiring real-time data.",
                target: ".quick-actions button:nth-child(2)",
                position: "top",
                action: null
            },
            {
                title: "Code Assistance",
                content: "Get help with programming, debugging, or technical questions. Perfect for developers and learners.",
                target: ".quick-actions button:nth-child(3)",
                position: "top",
                action: null
            },
            {
                title: "File Attachments",
                content: "Upload images, documents, or other files for analysis, transcription, or discussion.",
                target: "#attachBtn",
                position: "top",
                action: () => {
                    const attachBtn = document.getElementById('attachBtn');
                    if (attachBtn) {
                        attachBtn.style.transform = 'scale(1.1)';
                        setTimeout(() => {
                            attachBtn.style.transform = '';
                        }, 500);
                    }
                }
            },
            {
                title: "Voice Input",
                content: "Speak your messages instead of typing. Click the microphone to start voice input.",
                target: "#voiceBtn",
                position: "top",
                action: () => {
                    const voiceBtn = document.getElementById('voiceBtn');
                    if (voiceBtn) {
                        voiceBtn.style.transform = 'scale(1.1)';
                        setTimeout(() => {
                            voiceBtn.style.transform = '';
                        }, 500);
                    }
                }
            },
            {
                title: "Conversation Management",
                content: "Access your saved conversations and create new ones. Open the sidebar menu to see all your chats.",
                target: "#menuBtn",
                position: "right",
                action: () => {
                    const menuBtn = document.getElementById('menuBtn');
                    if (menuBtn) {
                        menuBtn.style.transform = 'scale(1.1)';
                        setTimeout(() => {
                            menuBtn.style.transform = '';
                        }, 500);
                    }
                }
            },
            {
                title: "New Conversations",
                content: "Start fresh conversations for different topics. Each conversation maintains its own context and history.",
                target: ".sidebar-actions",
                position: "right",
                action: () => {
                    // Open sidebar briefly to show the feature
                    const sidebar = document.getElementById('sidebar');
                    const overlay = document.getElementById('sidebarOverlay');
                    if (sidebar && overlay) {
                        sidebar.classList.add('active');
                        overlay.style.display = 'block';
                        setTimeout(() => {
                            sidebar.classList.remove('active');
                            overlay.style.display = 'none';
                        }, 2000);
                    }
                }
            },
            {
                title: "Settings & Preferences",
                content: "Customize your experience, manage your profile, and configure assistant behavior in settings.",
                target: "#settingsBtn",
                position: "right",
                action: null
            },
            {
                title: "Assistant Character",
                content: "Your AI assistant has visual feedback. Watch for animations that indicate thinking or speaking states.",
                target: "#assistantCharacter",
                position: "left",
                action: () => {
                    const character = document.getElementById('assistantCharacter');
                    if (character) {
                        character.classList.remove('idle');
                        character.classList.add('thinking');
                        setTimeout(() => {
                            character.classList.remove('thinking');
                            character.classList.add('idle');
                        }, 2000);
                    }
                }
            },
            {
                title: "Tutorial Complete",
                content: "You're now ready to use Crump AI. Start a conversation or explore the features at your own pace. You can restart this tutorial anytime from settings.",
                target: null,
                position: "center",
                action: null
            }
        ];
    }

    start() {
        if (localStorage.getItem('crump_tutorial_completed') === 'true') {
            console.log('[Tutorial] Already completed');
            return;
        }

        console.log('[Tutorial] Starting interactive walkthrough');
        this.isActive = true;
        this.currentStep = 0;
        this.showStep();
    }

    showStep() {
        const step = this.steps[this.currentStep];
        
        // Clean up previous step
        this.cleanup();
        
        // Execute step action if defined
        if (step.action && typeof step.action === 'function') {
            setTimeout(() => step.action(), 300);
        }

        // Create overlay
        const overlay = document.createElement('div');
        overlay.id = 'tutorialOverlay';
        overlay.className = 'tutorial-overlay';
        
        // Create tooltip/card
        const card = document.createElement('div');
        card.id = 'tutorialCard';
        card.className = 'tutorial-card';
        
        // Position the card based on target element
        if (step.target) {
            this.positionCard(card, step.target, step.position);
            this.highlightElement(step.target);
        } else {
            card.classList.add('tutorial-card-center');
        }

        card.innerHTML = `
            <div class="tutorial-card-content">
                <div class="tutorial-header">
                    <h3 class="tutorial-title">${step.title}</h3>
                    <button class="tutorial-close" onclick="tutorial.skip()" aria-label="Close tutorial">×</button>
                </div>
                <p class="tutorial-description">${step.content}</p>
                <div class="tutorial-progress">
                    <div class="tutorial-progress-bar">
                        <div class="tutorial-progress-fill" style="width: ${((this.currentStep + 1) / this.steps.length) * 100}%"></div>
                    </div>
                    <span class="tutorial-step-counter">Step ${this.currentStep + 1} of ${this.steps.length}</span>
                </div>
                <div class="tutorial-actions">
                    ${this.currentStep > 0 ? 
                        '<button class="tutorial-btn tutorial-btn-secondary" onclick="tutorial.back()">Previous</button>' : 
                        '<button class="tutorial-btn tutorial-btn-secondary" onclick="tutorial.skip()">Skip Tutorial</button>'
                    }
                    <button class="tutorial-btn tutorial-btn-primary" onclick="tutorial.next()">
                        ${this.currentStep === this.steps.length - 1 ? 'Get Started' : 'Next'}
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);
        document.body.appendChild(card);

        // Animate in
        requestAnimationFrame(() => {
            overlay.classList.add('tutorial-visible');
            card.classList.add('tutorial-visible');
        });
    }

    positionCard(card, targetSelector, position) {
        const target = document.querySelector(targetSelector);
        if (!target) {
            card.classList.add('tutorial-card-center');
            return;
        }

        const rect = target.getBoundingClientRect();
        const cardWidth = 400;
        const cardHeight = 300;
        const spacing = 20;

        card.style.position = 'fixed';
        card.style.maxWidth = `${cardWidth}px`;

        switch (position) {
            case 'top':
                card.style.left = `${rect.left + rect.width / 2}px`;
                card.style.top = `${rect.top - cardHeight - spacing}px`;
                card.style.transform = 'translateX(-50%)';
                break;
            case 'bottom':
                card.style.left = `${rect.left + rect.width / 2}px`;
                card.style.top = `${rect.bottom + spacing}px`;
                card.style.transform = 'translateX(-50%)';
                break;
            case 'left':
                card.style.left = `${rect.left - cardWidth - spacing}px`;
                card.style.top = `${rect.top + rect.height / 2}px`;
                card.style.transform = 'translateY(-50%)';
                break;
            case 'right':
                card.style.left = `${rect.right + spacing}px`;
                card.style.top = `${rect.top + rect.height / 2}px`;
                card.style.transform = 'translateY(-50%)';
                break;
            default:
                card.classList.add('tutorial-card-center');
        }

        // Adjust if card goes off-screen
        this.adjustCardPosition(card);
    }

    adjustCardPosition(card) {
        setTimeout(() => {
            const rect = card.getBoundingClientRect();
            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;
            const padding = 20;

            if (rect.right > viewportWidth - padding) {
                card.style.left = `${viewportWidth - rect.width - padding}px`;
                card.style.transform = 'none';
            }
            if (rect.left < padding) {
                card.style.left = `${padding}px`;
                card.style.transform = 'none';
            }
            if (rect.bottom > viewportHeight - padding) {
                card.style.top = `${viewportHeight - rect.height - padding}px`;
                card.style.transform = card.style.transform.includes('translateX') ? 'translateX(-50%)' : 'none';
            }
            if (rect.top < padding) {
                card.style.top = `${padding}px`;
                card.style.transform = card.style.transform.includes('translateX') ? 'translateX(-50%)' : 'none';
            }
        }, 10);
    }

    highlightElement(selector) {
        const element = document.querySelector(selector);
        if (!element) return;

        const highlight = document.createElement('div');
        highlight.id = 'tutorialHighlight';
        highlight.className = 'tutorial-highlight';

        const rect = element.getBoundingClientRect();
        highlight.style.position = 'fixed';
        highlight.style.top = `${rect.top - 8}px`;
        highlight.style.left = `${rect.left - 8}px`;
        highlight.style.width = `${rect.width + 16}px`;
        highlight.style.height = `${rect.height + 16}px`;
        highlight.style.pointerEvents = 'none';

        document.body.appendChild(highlight);
        
        // Make highlighted element interactive
        element.style.position = 'relative';
        element.style.zIndex = '10001';
    }

    cleanup() {
        // Remove overlay
        const overlay = document.getElementById('tutorialOverlay');
        if (overlay) overlay.remove();

        // Remove card
        const card = document.getElementById('tutorialCard');
        if (card) card.remove();

        // Remove highlight
        const highlight = document.getElementById('tutorialHighlight');
        if (highlight) highlight.remove();

        // Reset highlighted element
        document.querySelectorAll('[style*="z-index: 10001"]').forEach(el => {
            el.style.position = '';
            el.style.zIndex = '';
        });
    }

    next() {
        if (this.currentStep < this.steps.length - 1) {
            this.currentStep++;
            this.showStep();
        } else {
            this.complete();
        }
    }

    back() {
        if (this.currentStep > 0) {
            this.currentStep--;
            this.showStep();
        }
    }

    skip() {
        const confirmSkip = confirm('Are you sure you want to skip the tutorial? You can restart it anytime from Settings.');
        if (confirmSkip) {
            this.complete(true);
        }
    }

    complete(skipped = false) {
        this.cleanup();
        this.isActive = false;
        localStorage.setItem('crump_tutorial_completed', 'true');
        
        if (!skipped) {
            console.log('[Tutorial] Completed successfully');
            if (window.showToast) {
                window.showToast('Welcome to Crump AI! You\'re all set.', 'success');
            }
        } else {
            console.log('[Tutorial] Skipped by user');
        }
    }

    restart() {
        localStorage.removeItem('crump_tutorial_completed');
        this.currentStep = 0;
        this.start();
    }
}

// Initialize tutorial system
window.Tutorial = Tutorial;
window.tutorial = new Tutorial();

// Auto-start logic
window.addEventListener('load', () => {
    const hasOnboarded = localStorage.getItem('crump_has_onboarded');
    const tutorialCompleted = localStorage.getItem('crump_tutorial_completed');
    const appContainer = document.getElementById('appContainer');
    
    if (hasOnboarded === 'true' && tutorialCompleted !== 'true') {
        // Wait for app to be visible
        const checkAppVisible = setInterval(() => {
            if (appContainer && appContainer.style.display !== 'none') {
                clearInterval(checkAppVisible);
                setTimeout(() => {
                    window.tutorial.start();
                }, 1500);
            }
        }, 100);
        
        // Timeout after 10 seconds
        setTimeout(() => clearInterval(checkAppVisible), 10000);
    }
});

console.log('[Tutorial] Professional tutorial system v2.0 loaded');
