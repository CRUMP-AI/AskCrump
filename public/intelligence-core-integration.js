// ==========================================
// CRUMP AI - INTELLIGENCE CORE INTEGRATION
// Wires together: Intent, Memory, Insights
// ==========================================

class IntelligenceCoreIntegration {
    constructor() {
        this.intentEngine = null;
        this.memoryThreading = null;
        this.insightGenerator = null;
        this.isInitialized = false;
        
        this.init();
    }
    
    async init() {
        console.log('🧠 Intelligence Core Integration initializing...');
        
        // Wait for all systems to be available
        await this.waitForSystems();
        
        // Initialize systems
        this.intentEngine = new PredictiveIntentEngine();
        this.memoryThreading = new MemoryThreadingSystem();
        this.insightGenerator = new ProactiveInsightGenerator();
        
        // Make available globally
        window.intentEngine = this.intentEngine;
        window.memoryThreading = this.memoryThreading;
        window.insightGenerator = this.insightGenerator;
        
        // Hook into app events
        this.setupEventListeners();
        
        this.isInitialized = true;
        console.log('✅ Intelligence Core Integration ready');
        
        // Show initialization notification
        this.showWelcomeNotification();
    }
    
    async waitForSystems() {
        let attempts = 0;
        const maxAttempts = 50;
        
        while (attempts < maxAttempts) {
            if (window.PredictiveIntentEngine && 
                window.MemoryThreadingSystem && 
                window.ProactiveInsightGenerator) {
                return;
            }
            
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        
        console.warn('⚠️ Intelligence Core systems not fully loaded');
    }
    
    setupEventListeners() {
        // Hook into input field for intent prediction
        const userInput = document.getElementById('userInput');
        if (userInput) {
            userInput.addEventListener('input', (e) => this.handleInputChange(e));
            userInput.addEventListener('keydown', (e) => this.handleKeyDown(e));
        }
        
        // Listen for messages being sent
        window.addEventListener('crump:message:sent', (e) => this.handleMessageSent(e));
        
        // Listen for messages being received
        window.addEventListener('crump:message:received', (e) => this.handleMessageReceived(e));
        
        // Listen for preload requests
        window.addEventListener('crump:preload', (e) => this.handlePreload(e));
        
        console.log('🔗 Event listeners attached to Intelligence Core');
    }
    
    /**
     * Handle user typing in input field
     */
    handleInputChange(event) {
        const input = event.target.value;
        
        if (!input || input.length < 3) {
            this.hideSuggestions();
            return;
        }
        
        // Analyze intent
        const prediction = this.intentEngine.predictNextAction(input);
        
        if (prediction && prediction.confidence > 0.7) {
            // Preload context if needed
            if (prediction.preload) {
                this.intentEngine.preloadContext(prediction);
            }
            
            // Show suggestions if available
            if (prediction.suggestions && prediction.suggestions.length > 0) {
                this.showSuggestions(prediction.suggestions);
            }
        }
    }
    
    /**
     * Handle keydown events
     */
    handleKeyDown(event) {
        // Tab key to accept suggestion
        if (event.key === 'Tab' && this.currentSuggestion) {
            event.preventDefault();
            this.acceptSuggestion();
        }
    }
    
    /**
     * Handle message being sent
     */
    async handleMessageSent(event) {
        const { message, chatId } = event.detail || {};
        
        if (!message || !chatId) return;
        
        // Process through memory threading
        const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const threadInfo = await this.memoryThreading.processMessage(message, chatId, messageId);
        
        console.log('🧵 Message threaded:', threadInfo);
        
        // Show related threads if any
        if (threadInfo.relatedThreads && threadInfo.relatedThreads.length > 0) {
            this.showRelatedThreads(threadInfo.relatedThreads);
        }
    }
    
    /**
     * Handle message being received
     */
    async handleMessageReceived(event) {
        const { message, chatId } = event.detail || {};
        
        if (!message || !chatId) return;
        
        // Process through memory threading
        const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        await this.memoryThreading.processMessage(message, chatId, messageId);
    }
    
    /**
     * Handle preload request
     */
    handlePreload(event) {
        const { type, context } = event.detail || {};
        
        console.log('⚡ Preloading context:', type, context);
        
        // You can add actual preload logic here
        // For example, warming up API connections, loading relevant data, etc.
    }
    
    /**
     * Show inline suggestions
     */
    showSuggestions(suggestions) {
        // Check if suggestion UI already exists
        let suggestionBox = document.getElementById('crump-suggestions');
        
        if (!suggestionBox) {
            suggestionBox = document.createElement('div');
            suggestionBox.id = 'crump-suggestions';
            suggestionBox.className = 'intent-suggestions';
            
            const inputContainer = document.querySelector('.input-container');
            if (inputContainer) {
                inputContainer.appendChild(suggestionBox);
            }
        }
        
        suggestionBox.innerHTML = suggestions.map(s => `
            <div class="suggestion-item" onclick="window.intelligenceCore.applySuggestion('${s.action}')">
                <span class="suggestion-icon">${s.icon}</span>
                <span class="suggestion-text">${s.text}</span>
            </div>
        `).join('');
        
        suggestionBox.style.display = 'block';
        this.currentSuggestion = suggestions[0];
    }
    
    /**
     * Hide suggestions
     */
    hideSuggestions() {
        const suggestionBox = document.getElementById('crump-suggestions');
        if (suggestionBox) {
            suggestionBox.style.display = 'none';
        }
        this.currentSuggestion = null;
    }
    
    /**
     * Apply a suggestion
     */
    applySuggestion(action) {
        console.log('✨ Applying suggestion:', action);
        
        // You can add custom logic for different actions
        switch (action) {
            case 'web_search':
                // Trigger web search
                if (typeof triggerWebSearch === 'function') {
                    triggerWebSearch();
                }
                break;
            case 'assist':
                // Just send the message
                break;
            case 'debug':
                // Add debug context
                break;
            case 'compose':
                // Switch to professional tone
                break;
        }
        
        this.hideSuggestions();
    }
    
    /**
     * Show related threads notification
     */
    showRelatedThreads(threads) {
        if (threads.length === 0) return;
        
        // Create notification
        const notification = document.createElement('div');
        notification.className = 'related-threads-notification';
        notification.innerHTML = `
            <div class="notification-header">
                <span class="notification-icon">🔗</span>
                <span class="notification-title">Related Conversations</span>
                <button class="notification-close" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
            <div class="notification-body">
                ${threads.slice(0, 3).map(t => `
                    <div class="thread-item" onclick="window.intelligenceCore.loadThread('${t.id}')">
                        <div class="thread-summary">${t.thread.summary}</div>
                        <div class="thread-meta">${this.formatTimeAgo(t.thread.updated)}</div>
                    </div>
                `).join('')}
            </div>
        `;
        
        // Add to page
        const container = document.getElementById('chatContainer');
        if (container) {
            container.appendChild(notification);
            
            // Auto-hide after 10 seconds
            setTimeout(() => {
                notification.style.opacity = '0';
                setTimeout(() => notification.remove(), 300);
            }, 10000);
        }
    }
    
    /**
     * Load a specific thread
     */
    loadThread(threadId) {
        const thread = this.memoryThreading.getThread(threadId);
        
        if (!thread) {
            console.warn('Thread not found:', threadId);
            return;
        }
        
        console.log('📖 Loading thread:', thread);
        
        // You can add UI to show the thread
        // For now, just log it
        if (typeof showToast === 'function') {
            showToast(`Loaded: ${thread.summary}`, 'info');
        }
    }
    
    /**
     * Get relevant context for current message
     */
    getContextForMessage(message) {
        if (!this.isInitialized) return null;
        
        return this.memoryThreading.getRelevantContext(message, 3);
    }
    
    /**
     * Get pending insights
     */
    getPendingInsights() {
        if (!this.isInitialized) return [];
        
        return this.insightGenerator.getPendingInsights(5);
    }
    
    /**
     * Show insights notification
     */
    showInsightsNotification() {
        const insights = this.getPendingInsights();
        
        if (insights.length === 0) return;
        
        // Create notification badge
        let badge = document.getElementById('insights-badge');
        
        if (!badge) {
            badge = document.createElement('div');
            badge.id = 'insights-badge';
            badge.className = 'insights-badge';
            badge.onclick = () => this.showInsightsPanel();
            
            const header = document.querySelector('.header');
            if (header) {
                header.appendChild(badge);
            }
        }
        
        badge.textContent = insights.length;
        badge.style.display = 'flex';
    }
    
    /**
     * Show insights panel
     */
    showInsightsPanel() {
        const insights = this.getPendingInsights();
        
        const panel = document.createElement('div');
        panel.className = 'insights-panel modal';
        panel.innerHTML = `
            <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
            <div class="modal-content" style="max-width: 600px;">
                <div class="modal-header">
                    <h2>💡 Insights</h2>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
                </div>
                <div class="modal-body">
                    ${insights.length === 0 ? `
                        <p style="text-align: center; color: var(--color-text-secondary);">
                            No new insights yet. Keep using Crump and I'll find patterns!
                        </p>
                    ` : insights.map(insight => `
                        <div class="insight-card">
                            <div class="insight-header">
                                <span class="insight-icon">${this.insightGenerator.insightTypes[insight.type]?.icon || '💡'}</span>
                                <span class="insight-title">${insight.title}</span>
                            </div>
                            <div class="insight-message">${insight.message}</div>
                            ${insight.actionable ? `
                                <button class="btn btn-primary btn-sm" onclick="window.intelligenceCore.handleInsightAction('${insight.id}')">
                                    ${insight.action?.label || 'Take Action'}
                                </button>
                            ` : ''}
                            <button class="btn btn-secondary btn-sm" onclick="window.intelligenceCore.dismissInsight('${insight.id}')">
                                Dismiss
                            </button>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        
        document.body.appendChild(panel);
        setTimeout(() => panel.classList.add('active'), 10);
        
        // Mark as viewed
        insights.forEach(i => this.insightGenerator.markViewed(i.id));
        
        // Hide badge
        const badge = document.getElementById('insights-badge');
        if (badge) badge.style.display = 'none';
    }
    
    /**
     * Handle insight action
     */
    handleInsightAction(insightId) {
        const insight = this.insightGenerator.insights.find(i => i.id === insightId);
        
        if (!insight || !insight.action) return;
        
        console.log('⚡ Executing insight action:', insight.action);
        
        // Add custom logic for different action types
        switch (insight.action.type) {
            case 'schedule_insight':
                // Schedule regular updates
                if (typeof showToast === 'function') {
                    showToast('Scheduled regular updates for ' + insight.action.data.topic, 'success');
                }
                break;
            case 'track_topic':
                // Start tracking topic
                if (typeof showToast === 'function') {
                    showToast('Now tracking ' + insight.action.data.topic, 'success');
                }
                break;
            case 'resume_goal':
                // Load context for goal
                if (typeof showToast === 'function') {
                    showToast('Loading context for your goal', 'info');
                }
                break;
            case 'automate':
                // Set up automation
                if (typeof showToast === 'function') {
                    showToast('Automation set up!', 'success');
                }
                break;
        }
        
        this.dismissInsight(insightId);
    }
    
    /**
     * Dismiss insight
     */
    dismissInsight(insightId) {
        this.insightGenerator.dismissInsight(insightId);
        
        // Refresh panel if open
        const panel = document.querySelector('.insights-panel');
        if (panel) {
            panel.remove();
            this.showInsightsPanel();
        }
    }
    
    /**
     * Format time ago
     */
    formatTimeAgo(timestamp) {
        const seconds = Math.floor((Date.now() - timestamp) / 1000);
        
        if (seconds < 60) return 'just now';
        if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
        if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
        if (seconds < 604800) return Math.floor(seconds / 86400) + 'd ago';
        return Math.floor(seconds / 604800) + 'w ago';
    }
    
    /**
     * Show welcome notification
     */
    showWelcomeNotification() {
        setTimeout(() => {
            if (typeof showToast === 'function') {
                showToast('🧠 Intelligence Core activated', 'info');
            }
            
            // Check for insights after 30 seconds
            setTimeout(() => {
                this.insightGenerator.analyzeConversations();
                setTimeout(() => this.showInsightsNotification(), 1000);
            }, 30000);
        }, 2000);
    }
    
    /**
     * Get analytics
     */
    getAnalytics() {
        if (!this.isInitialized) return null;
        
        return {
            intent: this.intentEngine.getAnalytics(),
            memory: this.memoryThreading.getAnalytics(),
            insights: {
                total: this.insightGenerator.insights.length,
                pending: this.insightGenerator.getPendingInsights().length
            }
        };
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.intelligenceCore = new IntelligenceCoreIntegration();
    });
} else {
    window.intelligenceCore = new IntelligenceCoreIntegration();
}

console.log('🧠 Intelligence Core Integration loaded');
