// ==========================================
// CRUMP AI - ENGINES v2.12.1
// Core intelligence engines with memory leak fixes
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
        
        // CRITICAL FIX: Periodic cleanup to prevent memory leak
        this.cleanupInterval = setInterval(() => {
            const now = Date.now();
            for (let [key, timestamp] of this.recentMessages) {
                if (now - timestamp > this.windowMs) {
                    this.recentMessages.delete(key);
                }
            }
            
            // Log warning if Map grows too large
            if (this.recentMessages.size > 100) {
                console.warn('⚠️ MessageDeduplicator has', this.recentMessages.size, 'entries - cleaning up');
            }
        }, 5000); // Cleanup every 5 seconds
        
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
        // Simple hash function
        let hash = 0;
        for (let i = 0; i < message.length; i++) {
            const char = message.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32bit integer
        }
        return hash.toString();
    }
    
    // Cleanup method for proper disposal
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
        // Extract potential topics (basic NLP)
        const words = message.toLowerCase()
            .replace(/[^\w\s]/g, ' ')
            .split(/\s+/)
            .filter(word => word.length > 4);
        
        // Common words to ignore
        const stopWords = new Set(['about', 'would', 'could', 'should', 'there', 'their', 'which', 'where', 'these', 'those']);
        
        const topics = words.filter(word => !stopWords.has(word));
        
        // Add to recent topics
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
        window.showNotification(`📍 Added context: ${contextName}`, 'success');
        
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
        const chat = window.chats.find(c => c.id === window.currentChatId);
        if (!chat) return;
        
        const container = document.getElementById('chatContainer');
        const insight = document.createElement('div');
        insight.className = 'context-insight';
        
        // SECURITY FIX: Proper XSS protection
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
                cooldown: 3600000 // 1 hour
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
            // Check if any trigger word is in message
            const hasMatch = suggestion.trigger.some(trigger => lowerMessage.includes(trigger));
            
            if (hasMatch && !this.isOnCooldown(suggestion)) {
                // Don't show if recently shown
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
        const saved = localStorage.getItem(window.STORAGE_KEYS.SHOWN_SUGGESTIONS);
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
        localStorage.setItem(window.STORAGE_KEYS.SHOWN_SUGGESTIONS, serialized);
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
            'relaxed': 900000,      // 15 minutes
            'balanced': 600000,     // 10 minutes
            'active': 300000,       // 5 minutes
            'very-active': 180000   // 3 minutes
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
        this.checkInterval = setInterval(() => this.checkActivity(), 30000); // Check every 30s
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
            window.lastUserActivity = Date.now(); // Reset timer
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
            
            // Restart with new interval if already running
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
        window.showNotification('✅ Thanks! I\'ll learn from this.', 'success');
    }
    
    recordFeedback(messageIndex, feedbackType) {
        this.updateMetrics(feedbackType);
        
        const emoji = feedbackType === 'thumbsUp' ? '👍' : '👎';
        window.showNotification(`${emoji} Feedback recorded`, 'success');
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
        const saved = localStorage.getItem(window.STORAGE_KEYS.CORRECTIONS);
        return saved ? JSON.parse(saved) : [];
    }
    
    saveCorrections() {
        localStorage.setItem(window.STORAGE_KEYS.CORRECTIONS, JSON.stringify(this.corrections));
    }
    
    loadPreferences() {
        const saved = localStorage.getItem(window.STORAGE_KEYS.USER_PREFERENCES);
        return saved ? JSON.parse(saved) : {};
    }
    
    savePreferences() {
        localStorage.setItem(window.STORAGE_KEYS.USER_PREFERENCES, JSON.stringify(this.preferences));
    }
    
    loadMetrics() {
        const saved = localStorage.getItem(window.STORAGE_KEYS.PERFORMANCE_METRICS);
        if (saved) {
            Object.assign(this.performanceMetrics, JSON.parse(saved));
        }
    }
    
    saveMetrics() {
        localStorage.setItem(window.STORAGE_KEYS.PERFORMANCE_METRICS, JSON.stringify(this.performanceMetrics));
    }
}

// ==========================================
// EXPORT TO WINDOW
// ==========================================
window.MessageDeduplicator = MessageDeduplicator;
window.ContextAwarenessEngine = ContextAwarenessEngine;
window.SuggestionEngine = SuggestionEngine;
window.AutonomousEngine = AutonomousEngine;
window.LearningEngine = LearningEngine;
window.escapeHtml = escapeHtml;

console.log('✅ Engines v2.12.1 loaded - Memory leak fixes applied');
