<artifact identifier="crump-tutorial-js" type="application/vnd.ant.code" language="javascript" title="tutorial.js - Tutorial System v1.0">
// ==========================================
// CRUMP AI - TUTORIAL SYSTEM v1.0
// First-time user onboarding
// ==========================================
class Tutorial {
constructor() {
this.currentStep = 0;
this.steps = [
{
title: "Welcome to Crump",
content: "Your personal AI assistant. Let's show you around.",
icon: "👋",
highlight: null
},
{
title: "Send Messages",
content: "Type your message and press <strong>Send</strong> or <strong>Enter</strong>. Ask me anything!",
icon: "💬",
highlight: ".input-container"
},
{
title: "Quick Actions",
content: "Use quick buttons for <strong>Image Generation</strong>, <strong>Web Search</strong>, and <strong>Code Help</strong>.",
icon: "⚡",
highlight: ".quick-actions"
},
{
title: "File Uploads",
content: "Click the <strong>attach button</strong> to upload images or documents.",
icon: "📎",
highlight: "#attachBtn"
},
{
title: "Voice Input",
content: "Use the <strong>microphone</strong> to speak your messages.",
icon: "🎤",
highlight: "#voiceBtn"
},
{
title: "Conversations",
content: "All your chats are saved. Create new conversations with the <strong>New Conversation</strong> button.",
icon: "💾",
highlight: ".sidebar-actions"
},
{
title: "You're All Set!",
content: "You're ready to start using Crump. Ask me anything!",
icon: "🚀",
highlight: null
}
];
}
start() {
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
    
    this.removeTutorial();
    
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

    if (step.highlight) {
        this.highlightElement(step.highlight);
    }

    const nextBtn = document.getElementById('tutorialNext');
    const backBtn = document.getElementById('tutorialBack');
    const skipBtn = document.getElementById('tutorialSkip');

    if (nextBtn) nextBtn.addEventListener('click', () => this.next());
    if (backBtn) backBtn.addEventListener('click', () => this.back());
    if (skipBtn) skipBtn.addEventListener('click', () => this.skip());
}

highlightElement(selector) {
    const element = document.querySelector(selector);
    if (!element) return;

    element.style.position = 'relative';
    element.style.zIndex = '9999';
    element.style.boxShadow = '0 0 0 4px var(--color-accent-primary)';
    element.style.borderRadius = '8px';
    element.dataset.tutorialHighlight = 'true';
}

removeHighlights() {
    document.querySelectorAll('[data-tutorial-highlight="true"]').forEach(el => {
        el.style.position = '';
        el.style.zIndex = '';
        el.style.boxShadow = '';
        delete el.dataset.tutorialHighlight;
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
    if (confirm('Skip tutorial?')) {
        this.complete();
    }
}

complete() {
    this.removeTutorial();
    this.removeHighlights();
    localStorage.setItem('crump_tutorial_completed', 'true');
    console.log('✅ Tutorial completed');
    
    if (window.showToast) {
        window.showToast('🎉 Welcome to Crump AI!', 'success');
    }
}

removeTutorial() {
    const overlay = document.getElementById('tutorialOverlay');
    if (overlay) overlay.remove();
}

restart() {
    localStorage.removeItem('crump_tutorial_completed');
    this.currentStep = 0;
    this.start();
}
}
window.Tutorial = Tutorial;
window.tutorial = new Tutorial();
window.addEventListener('load', () => {
const hasOnboarded = localStorage.getItem('crump_has_onboarded');
const tutorialCompleted = localStorage.getItem('crump_tutorial_completed');
if (hasOnboarded === 'true' && tutorialCompleted !== 'true') {
    setTimeout(() => {
        window.tutorial.start();
    }, 1000);
}
});
console.log('✅ Tutorial System v1.0 loaded');
</artifact>
