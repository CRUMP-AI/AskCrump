// ==========================================
// CRUMP AI - SCROLL MANAGER v2.0 PROPER
// Intelligent scroll management with auto-scroll
// ==========================================

class CrumpScrollManager {
    constructor() {
        this.container = null;
        this.autoScroll = true;
        this.isScrolledToBottom = true;
        this.lastScrollTop = 0;
        this.userScrolling = false;
        this.scrollThreshold = 150; // px from bottom to trigger auto-scroll
        
        console.log('📜 Scroll Manager v2.0 initializing...');
    }

    init(containerId = 'chatContainer') {
        this.container = document.getElementById(containerId);
        
        if (!this.container) {
            console.warn('⚠️ Scroll container not found:', containerId);
            return false;
        }

        // Setup scroll listener
        this.container.addEventListener('scroll', () => this.handleScroll());
        
        // Setup mutation observer to detect new messages
        this.setupMutationObserver();
        
        console.log('✅ Scroll Manager initialized');
        return true;
    }

    setupMutationObserver() {
        if (!this.container) return;

        const observer = new MutationObserver((mutations) => {
            // Check if new messages were added
            const hasNewContent = mutations.some(mutation => 
                mutation.addedNodes.length > 0
            );

            if (hasNewContent && this.autoScroll && this.isScrolledToBottom) {
                // Delay slightly to ensure content is rendered
                requestAnimationFrame(() => {
                    this.scrollToBottom('smooth');
                });
            }
        });

        observer.observe(this.container, {
            childList: true,
            subtree: true
        });

        this.observer = observer;
    }

    handleScroll() {
        if (!this.container) return;

        const { scrollTop, scrollHeight, clientHeight } = this.container;
        
        // Check if user is scrolled to bottom (with threshold)
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
        this.isScrolledToBottom = distanceFromBottom < this.scrollThreshold;

        // Detect if user is scrolling up
        this.userScrolling = scrollTop < this.lastScrollTop;
        this.lastScrollTop = scrollTop;

        // Disable auto-scroll if user scrolls up
        if (this.userScrolling && !this.isScrolledToBottom) {
            this.autoScroll = false;
            this.showScrollToBottomButton();
        } else if (this.isScrolledToBottom) {
            this.autoScroll = true;
            this.hideScrollToBottomButton();
        }
    }

    scrollToBottom(behavior = 'smooth') {
        if (!this.container) return;

        this.container.scrollTo({
            top: this.container.scrollHeight,
            behavior: behavior
        });

        this.isScrolledToBottom = true;
        this.autoScroll = true;
    }

    scrollToTop(behavior = 'smooth') {
        if (!this.container) return;

        this.container.scrollTo({
            top: 0,
            behavior: behavior
        });
    }

    scrollToElement(element, behavior = 'smooth') {
        if (!this.container || !element) return;

        element.scrollIntoView({
            behavior: behavior,
            block: 'nearest'
        });
    }

    enableAutoScroll() {
        this.autoScroll = true;
        this.scrollToBottom('smooth');
    }

    disableAutoScroll() {
        this.autoScroll = false;
    }

    showScrollToBottomButton() {
        let button = document.getElementById('scrollToBottomBtn');
        
        if (!button) {
            button = document.createElement('button');
            button.id = 'scrollToBottomBtn';
            button.className = 'scroll-to-bottom-btn';
            button.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 5v14M19 12l-7 7-7-7"/>
                </svg>
                <span>New messages</span>
            `;
            button.onclick = () => this.enableAutoScroll();

            button.style.cssText = `
                position: fixed;
                bottom: 120px;
                right: 24px;
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 10px 16px;
                background: var(--color-accent-primary);
                color: var(--color-bg-primary);
                border: none;
                border-radius: 24px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
                z-index: 90;
                animation: slideInBottom 0.3s ease;
                transition: all 0.2s ease;
            `;

            document.body.appendChild(button);
        }

        button.style.display = 'flex';
    }

    hideScrollToBottomButton() {
        const button = document.getElementById('scrollToBottomBtn');
        if (button) {
            button.style.display = 'none';
        }
    }

    getScrollPosition() {
        if (!this.container) return 0;
        return this.container.scrollTop;
    }

    setScrollPosition(position) {
        if (!this.container) return;
        this.container.scrollTop = position;
    }

    isAtBottom() {
        return this.isScrolledToBottom;
    }

    isAtTop() {
        if (!this.container) return false;
        return this.container.scrollTop === 0;
    }

    // Get scroll percentage (0-100)
    getScrollPercentage() {
        if (!this.container) return 0;
        const { scrollTop, scrollHeight, clientHeight } = this.container;
        return (scrollTop / (scrollHeight - clientHeight)) * 100;
    }

    // Save scroll position (useful for maintaining position after refresh)
    saveScrollPosition() {
        if (!this.container) return;
        const position = this.getScrollPosition();
        sessionStorage.setItem('crump_scroll_position', position.toString());
    }

    // Restore saved scroll position
    restoreScrollPosition() {
        const savedPosition = sessionStorage.getItem('crump_scroll_position');
        if (savedPosition) {
            this.setScrollPosition(parseInt(savedPosition));
            sessionStorage.removeItem('crump_scroll_position');
        }
    }

    destroy() {
        if (this.observer) {
            this.observer.disconnect();
        }
        this.hideScrollToBottomButton();
        console.log('🗑️ Scroll Manager destroyed');
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.crumpScrollManager = new CrumpScrollManager();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.crumpScrollManager.init();
    });
} else {
    // DOM already loaded
    setTimeout(() => {
        window.crumpScrollManager.init();
    }, 100);
}

// Export for other modules
window.CrumpScrollManager = CrumpScrollManager;

console.log('✅ Scroll Manager v2.0 loaded');

// ==========================================
// CSS FOR SCROLL TO BOTTOM BUTTON
// ==========================================
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInBottom {
        from {
            transform: translateY(100px);
            opacity: 0;
        }
        to {
            transform: translateY(0);
            opacity: 1;
        }
    }

    .scroll-to-bottom-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
    }

    .scroll-to-bottom-btn:active {
        transform: translateY(0);
    }

    @media (max-width: 768px) {
        .scroll-to-bottom-btn {
            bottom: 140px !important;
            right: 16px !important;
            font-size: 13px !important;
            padding: 8px 14px !important;
        }
    }
`;
document.head.appendChild(style);
