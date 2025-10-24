// ==========================================
// CRUMP AI - ENGINES v3.0
// Core intelligence engines + NEW Search Detection
// ==========================================

// ==========================================
// SECURITY UTILITY - XSS Protection
// ==========================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==========================================
// MESSAGE DEDUPLICATION ENGINE
// Prevents duplicate message sends
// ==========================================
class MessageDeduplicator {
    constructor(windowMs = 500) {
        this.recentMessages = new Map();
        this.windowMs = windowMs;
        
        this.cleanupInterval = setInterval(() => {
            const now = Date.now();
            for (let [key, timestamp] of this.recentMessages) {
                if (now - timestamp > this.windowMs) {
                    this.recentMessages.delete(key);
                }
            }
            
            if (this.recentMessages.size > 100) {
                console.warn('⚠️ MessageDeduplicator has', this.recentMessages.size, 'entries - cleaning up');
            }
        }, 5000);
        
        console.log('✅ MessageDeduplicator initialized with auto-cleanup');
    }
    
    isDuplicate(message) {
        const hash = this.hashMessage(message);
        const now = Date.now();
        
        if (this.recentMessages.has(hash)) {
            const timestamp = this.recentMessages.get(hash);
            if (now - timestamp < this.windowMs) {
                console.log('🚫 Duplicate message blocked:', message.substring(0, 50));
                return true;
            }
        }
        
        this.recentMessages.set(hash, now);
        return false;
    }
    
    hashMessage(message) {
        let hash = 0;
        for (let i = 0; i < message.length; i++) {
            const char = message.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return hash.toString();
    }
    
    destroy() {
        if (this.cleanupInterval) {
            clearInterval(this.cleanupInterval);
            this.cleanupInterval = null;
        }
        this.recentMessages.clear();
        console.log('🗑️ MessageDeduplicator destroyed');
    }
    
    clear() {
        this.recentMessages.clear();
    }
}

// ==========================================
// SEARCH DETECTION ENGINE (NEW!)
// Intelligent detection of queries needing web search
// ==========================================
class SearchDetectionEngine {
    constructor() {
        this.patterns = {
            // Explicit search requests
            explicit: [
                /search for/i,
                /look up/i,
                /find out about/i,
                /google/i,
                /what.*happening/i
            ],
            
            // Temporal indicators (current/recent info)
            temporal: [
                /today/i,
                /tonight/i,
                /this week/i,
                /this weekend/i,
                /this month/i,
                /this year/i,
                /currently/i,
                /current/i,
                /latest/i,
                /recent/i,
                /now/i,
                /right now/i,
                /at the moment/i
            ],
            
            // Question words suggesting current events
            currentEvents: [
                /who (is|are|won|will win|leading)/i,
                /what (is|are|happened|happening)/i,
                /when (is|are|will)/i,
                /where (is|are)/i,
                /how much (is|are|cost)/i
            ],
            
            // Sports queries
            sports: [
                /\b(nfl|nba|mlb|nhl|fifa|premier league|champions league)\b/i,
                /\b(game|match|score|playoff|championship|tournament)\b/i,
                /who (won|will win|is winning|is playing)/i,
                /\b(team|teams) (play|playing|won|lost)/i
            ],
            
            // Weather queries
            weather: [
                /weather/i,
                /temperature/i,
                /forecast/i,
                /rain/i,
                /snow/i,
                /storm/i
            ],
            
            // News queries
            news: [
                /news about/i,
                /breaking news/i,
                /headlines/i,
                /what.*news/i
            ],
            
            // Stock/finance queries
            finance: [
                /stock price/i,
                /\b(stock|stocks|market|markets)\b/i,
                /\b(nasdaq|dow|s&p)\b/i,
                /share price/i
            ],
            
            // Technology/product queries
            tech: [
                /latest (version|release|update)/i,
                /new (iphone|android|windows|mac)/i,
                /specs for/i,
                /price of.*\d{4}/i // "price of iPhone 16" etc
            ]
        };
        
        // Blacklist - never search for these
        this.blacklist = [
            /how (do|can) i/i,  // "How do I..." = instructions
            /explain/i,          // "Explain..." = concept explanation
            /what (is|are) the (difference|meaning)/i,  // Definitions
            /tell me about (yourself|you|your)/i,       // About the assistant
            /help me (with|understand)/i                // Help requests
        ];
        
        console.log('✅ Search Detection Engine initialized');
    }
    
    shouldSearch(message) {
        if (!message || typeof message !== 'string') return false;
        
        const lowerMessage = message.toLowerCase().trim();
        
        // Check blacklist first
        for (const pattern of this.blacklist) {
            if (pattern.test(message)) {
                console.log('🚫 Blacklisted query pattern - no search');
                return false;
            }
        }
        
        // Check each category
        let score = 0;
        let reasons = [];
        
        // Explicit search requests = instant trigger
        for (const pattern of this.patterns.explicit) {
            if (pattern.test(message)) {
                console.log('🔍 Explicit search request detected');
                return true;
            }
        }
        
        // Temporal indicators
        for (const pattern of this.patterns.temporal) {
            if (pattern.test(message)) {
                score += 2;
                reasons.push('temporal');
                break;
            }
        }
        
        // Current events question structure
        for (const pattern of this.patterns.currentEvents) {
            if (pattern.test(message)) {
                score += 2;
                reasons.push('current-events');
                break;
            }
        }
        
        // Sports
        for (const pattern of this.patterns.sports) {
            if (pattern.test(message)) {
                score += 2;
                reasons.push('sports');
                break;
            }
        }
        
        // Weather
        for (const pattern of this.patterns.weather) {
            if (pattern.test(message)) {
                score += 3; // Weather almost always needs search
                reasons.push('weather');
                break;
            }
        }
        
        // News
        for (const pattern of this.patterns.news) {
            if (pattern.test(message)) {
                score += 3;
                reasons.push('news');
                break;
            }
        }
        
        // Finance
        for (const pattern of this.patterns.finance) {
            if (pattern.test(message)) {
                score += 2;
                reasons.push('finance');
                break;
            }
        }
        
        // Tech
        for (const pattern of this.patterns.tech) {
            if (pattern.test(message)) {
                score += 2;
                reasons.push('tech');
                break;
            }
        }
        
        // Decision threshold
        const shouldSearch = score >= 2;
        
        if (shouldSearch) {
            console.log(`🔍 Search triggered (score: ${score}, reasons: ${reasons.join(', ')})`);
        } else {
            console.log(`📚 No search needed (score: ${score})`);
        }
        
        return shouldSearch;
    }
    
    // For testing/debugging
    analyzeQuery(message) {
        const result = {
            shouldSearch: this.shouldSearch(message),
            message: message,
            patterns: []
        };
        
        // Check which patterns matched
        for (const [category, patterns] of Object.entries(this.patterns)) {
            for (const pattern of patterns) {
                if (pattern.test(message)) {
                    result.patterns.push(category);
                    break;
                }
            }
        }
        
        return result;
    }
}

// ==========================================
// CONTEXT AWARENESS ENGINE
// Tracks conversation topics and suggests relevant contexts
// ==========================================
class ContextAwarenessEngine {
    constructor() {
        this.activeContexts = new Map();
        this.conversationTopics = [];
        this.maxTopics = 20;
        this.maxContexts = 10;
    }
    
    analyzeMessage(message) {
        const words = message.toLowerCase()
            .replace(/[^\w\s]/g, ' ')
            .split(/\s+/)
            .filter(word => word.length > 4);
        
        const stopWords = new Set(['about', 'would', 'could', 'should', 'there', 'their', 'which', 'where', 'these', 'those']);
        
        const topics = words.filter(word => !stopWords.has(word));
        
        topics.forEach(topic => {
            if (!this.conversationTopics.includes(topic)) {
                this.conversationTopics.unshift(topic);
                if (this.conversationTopics.length > this.maxTopics) {
                    this.conversationTopics.pop();
                }
            }
        });
        
        return topics;
    }
    
    addContext(contextName, metadata = {}) {
        if (this.activeContexts.size >= this.maxContexts) {
            const firstKey = this.activeContexts.keys().next().value;
            this.activeContexts.delete(firstKey);
        }
        
        this.activeContexts.set(contextName, {
            added: Date.now(),
            metadata,
            mentions: 1
        });
        
        console.log('📍 Context added:', contextName);
        if (window.showNotification) {
            window.showNotification(`📍 Added context: ${contextName}`, 'success');
        }
        
        this.saveContexts();
    }
    
    removeContext(contextName) {
        this.activeContexts.delete(contextName);
        console.log('🗑️ Context removed:', contextName);
        this.saveContexts();
    }
    
    getActiveContexts() {
        return Array.from(this.activeContexts.keys());
    }
    
    suggestContext(topic) {
        const chat = window.chats?.find(c => c.id === window.currentChatId);
        if (!chat) return;
        
        const container = document.getElementById('chatContainer');
        if (!container) return;
        
        const insight = document.createElement('div');
        insight.className = 'context-insight';
        
        const escapedTopic = escapeHtml(topic);
        const safeTopic = topic.replace(/'/g, "\\'").replace(/"/g, '\\"');
        
        insight.innerHTML = `
            <div class="context-insight-header">
                <span>💡</span>
                <span>Context Suggestion</span>
            </div>
            <div class="context-insight-text">
                It looks like you're working on <strong>${escapedTopic}</strong>. Would you like to add this as a context for better tracking?
            </div>
            <div class="context-insight-actions">
                <button class="context-insight-action" onclick="window.contextEngine.addContext('${safeTopic}'); this.closest('.context-insight').remove();">
                    Add "${escapedTopic}"
                </button>
                <button class="context-insight-action" onclick="this.closest('.context-insight').remove();">
                    No thanks
                </button>
            </div>
        `;
        
        container.appendChild(insight);
        container.scrollTop = container.scrollHeight;
    }
    
    loadChatContext(chatId) {
        const saved = localStorage.getItem(`crump_context_${chatId}`);
        if (saved) {
            try {
                this.activeContexts = new Map(JSON.parse(saved));
                console.log('📍 Loaded contexts:', this.getActiveContexts());
            } catch (e) {
                console.error('Failed to load contexts:', e);
            }
        }
    }
    
    saveContexts() {
        if (window.currentChatId) {
            const serialized = JSON.stringify(Array.from(this.activeContexts.entries()));
            localStorage.setItem(`crump_context_${window.currentChatId}`, serialized);
        }
    }
}

// ==========================================
// SUGGESTION ENGINE
// Provides contextual suggestions and tips
// ==========================================
class SuggestionEngine {
    constructor() {
        this.suggestions = [
            {
                trigger: ['code', 'program', 'script', 'function'],
                suggestion: '💡 Tip: I can help debug code, explain algorithms, or write complete programs in any language.',
                cooldown: 3600000
            },
            {
                trigger: ['image', 'picture', 'generate', 'create'],
                suggestion: '🎨 Tip: Try "generate an image of [description]" to create AI artwork!',
                cooldown: 3600000
            },
            {
                trigger: ['search', 'find', 'look up', 'google'],
                suggestion: '🔍 Tip: I can search the web for current information. Just ask naturally!',
                cooldown: 3600000
            },
            {
                trigger: ['remember', 'recall', 'mentioned'],
                suggestion: '🧠 Tip: I have unlimited memory and remember all our conversations!',
                cooldown: 7200000
            }
        ];
        
        this.shownSuggestions = this.loadShownSuggestions();
        this.cooldownTimers = new Map();
    }
    
    checkAndShowSuggestion(message, chat) {
        if (!window.contextSuggestionsEnabled) return;
        
        const lowerMessage = message.toLowerCase();
        
        for (const suggestion of this.suggestions) {
            const hasMatch = suggestion.trigger.some(trigger => lowerMessage.includes(trigger));
            
            if (hasMatch && !this.isOnCooldown(suggestion)) {
                const suggestionKey = suggestion.suggestion;
                const lastShown = this.shownSuggestions.get(suggestionKey);
                
                if (!lastShown || Date.now() - lastShown > suggestion.cooldown) {
                    this.showSuggestion(suggestion);
                    this.markAsShown(suggestionKey);
                    this.startCooldown(suggestion);
                    break;
                }
            }
        }
    }
    
    showSuggestion(suggestion) {
        const container = document.getElementById('chatContainer');
        if (!container) return;
        
        const div = document.createElement('div');
        div.className = 'context-insight';
        div.innerHTML = `
            <div class="context-insight-header">
                <span>💡</span>
                <span>Suggestion</span>
            </div>
            <div class="context-insight-text">
                ${escapeHtml(suggestion.suggestion)}
            </div>
            <div class="context-insight-actions">
                <button class="context-insight-action" onclick="this.closest('.context-insight').remove();">
                    Got it!
                </button>
            </div>
        `;
        
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }
    
    isOnCooldown(suggestion) {
        return this.cooldownTimers.has(suggestion.suggestion);
    }
    
    startCooldown(suggestion) {
        const timer = setTimeout(() => {
            this.cooldownTimers.delete(suggestion.suggestion);
        }, suggestion.cooldown);
        
        this.cooldownTimers.set(suggestion.suggestion, timer);
    }
    
    markAsShown(suggestionKey) {
        this.shownSuggestions.set(suggestionKey, Date.now());
        this.saveShownSuggestions();
    }
    
    loadShownSuggestions() {
        const saved = localStorage.getItem('crump_shown_suggestions');
        if (saved) {
            try {
                return new Map(JSON.parse(saved));
            } catch (e) {
                return new Map();
            }
        }
        return new Map();
    }
    
    saveShownSuggestions() {
        const serialized = JSON.stringify(Array.from(this.shownSuggestions.entries()));
        localStorage.setItem('crump_shown_suggestions', serialized);
    }
}

// ==========================================
// AUTONOMOUS MESSAGING ENGINE
// Sends proactive messages based on user activity
// ==========================================
class AutonomousEngine {
    constructor() {
        this.enabled = false;
        this.checkInterval = null;
        this.intervalPresets = {
            'relaxed': 900000,
            'balanced': 600000,
            'active': 300000,
            'very-active': 180000
        };
        this.currentInterval = this.intervalPresets.balanced;
        this.lastCheck = Date.now();
        
        this.messages = [
            "Still here if you need anything! 😊",
            "Working on something interesting?",
            "Need help with anything? I'm ready when you are.",
            "Just checking in - everything going okay?",
            "Taking a break? Let me know if you need assistance!",
            "I'm here whenever you're ready to continue.",
            "Got any questions? I'm all ears! 👂",
            "Feel free to ask me anything - I don't bite! 😄"
        ];
    }
    
    start() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
        }
        
        this.enabled = true;
        this.checkInterval = setInterval(() => this.checkActivity(), 30000);
        console.log('🤖 Autonomous messaging enabled');
    }
    
    stop() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
            this.checkInterval = null;
        }
        this.enabled = false;
        console.log('🤖 Autonomous messaging disabled');
    }
    
    checkActivity() {
        if (!this.enabled || !window.lastUserActivity) return;
        
        const timeSinceActivity = Date.now() - window.lastUserActivity;
        
        if (timeSinceActivity > this.currentInterval) {
            this.sendAutonomousMessage();
            window.lastUserActivity = Date.now();
        }
    }
    
    sendAutonomousMessage() {
        const message = this.messages[Math.floor(Math.random() * this.messages.length)];
        
        if (window.addMessage) {
            window.addMessage('assistant', `*[Autonomous Message]*\n\n${message}`);
            console.log('🤖 Sent autonomous message');
        }
    }
    
    setIntervalPreset(preset) {
        if (this.intervalPresets[preset]) {
            this.currentInterval = this.intervalPresets[preset];
            console.log(`🤖 Autonomous interval set to: ${preset} (${this.currentInterval}ms)`);
            
            if (this.enabled) {
                this.stop();
                this.start();
            }
        }
    }
}

// ==========================================
// LEARNING ENGINE
// Learns from user corrections and preferences
// ==========================================
class LearningEngine {
    constructor() {
        this.corrections = this.loadCorrections();
        this.preferences = this.loadPreferences();
        this.performanceMetrics = {
            totalResponses: 0,
            corrections: 0,
            thumbsUp: 0,
            thumbsDown: 0
        };
        this.loadMetrics();
    }
    
    recordCorrection(originalResponse, correctedResponse, context = '') {
        const correction = {
            timestamp: Date.now(),
            original: originalResponse,
            corrected: correctedResponse,
            context: context
        };
        
        this.corrections.push(correction);
        if (this.corrections.length > 100) {
            this.corrections.shift();
        }
        
        this.saveCorrections();
        this.updateMetrics('correction');
        
        console.log('📝 Correction recorded');
        if (window.showNotification) {
            window.showNotification('✅ Thanks! I\'ll learn from this.', 'success');
        }
    }
    
    recordFeedback(messageIndex, feedbackType) {
        this.updateMetrics(feedbackType);
        
        const emoji = feedbackType === 'thumbsUp' ? '👍' : '👎';
        if (window.showNotification) {
            window.showNotification(`${emoji} Feedback recorded`, 'success');
        }
    }
    
    detectCorrectionPattern(userMessage, lastAssistantMessage) {
        const correctionPhrases = [
            'no,', 'actually,', 'wrong', 'incorrect', 'not quite',
            'fix that', 'correction:', 'should be', 'meant to',
            'not right', 'that\'s wrong', 'you\'re wrong'
        ];
        
        const lowerMessage = userMessage.toLowerCase();
        const hasCorrection = correctionPhrases.some(phrase => lowerMessage.includes(phrase));
        
        return {
            isCorrection: hasCorrection && lastAssistantMessage,
            originalResponse: lastAssistantMessage,
            correctedResponse: userMessage
        };
    }
    
    updateMetrics(type) {
        if (type === 'response') {
            this.performanceMetrics.totalResponses++;
        } else if (type === 'correction') {
            this.performanceMetrics.corrections++;
        } else if (type === 'thumbsUp') {
            this.performanceMetrics.thumbsUp++;
        } else if (type === 'thumbsDown') {
            this.performanceMetrics.thumbsDown++;
        }
        
        this.saveMetrics();
    }
    
    getAccuracyScore() {
        const total = this.performanceMetrics.thumbsUp + this.performanceMetrics.thumbsDown;
        if (total === 0) return 100;
        return Math.round((this.performanceMetrics.thumbsUp / total) * 100);
    }
    
    getProactiveTrainingRequest() {
        if (Math.random() < 0.3) {
            const requests = [
                "By the way, if I ever make a mistake, just correct me directly - I learn from it! 📝",
                "Feel free to give me feedback (👍/👎) on my responses - it helps me improve!",
                "If something I said wasn't quite right, let me know - I want to get better! 🎯"
            ];
            return requests[Math.floor(Math.random() * requests.length)];
        }
        return null;
    }
    
    loadCorrections() {
        const saved = localStorage.getItem('crump_corrections');
        return saved ? JSON.parse(saved) : [];
    }
    
    saveCorrections() {
        localStorage.setItem('crump_corrections', JSON.stringify(this.corrections));
    }
    
    loadPreferences() {
        const saved = localStorage.getItem('crump_user_preferences');
        return saved ? JSON.parse(saved) : {};
    }
    
    savePreferences() {
        localStorage.setItem('crump_user_preferences', JSON.stringify(this.preferences));
    }
    
    loadMetrics() {
        const saved = localStorage.getItem('crump_performance_metrics');
        if (saved) {
            Object.assign(this.performanceMetrics, JSON.parse(saved));
        }
    }
    
    saveMetrics() {
        localStorage.setItem('crump_performance_metrics', JSON.stringify(this.performanceMetrics));
    }
}

// ==========================================
// EXPORT TO WINDOW
// ==========================================
window.MessageDeduplicator = MessageDeduplicator;
window.SearchDetectionEngine = SearchDetectionEngine; // NEW!
window.ContextAwarenessEngine = ContextAwarenessEngine;
window.SuggestionEngine = SuggestionEngine;
window.AutonomousEngine = AutonomousEngine;
window.LearningEngine = LearningEngine;
window.escapeHtml = escapeHtml;

console.log('✅ Engines v3.0 loaded - Search Detection Engine added');
