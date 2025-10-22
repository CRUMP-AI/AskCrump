// ==========================================
// CRUMP AI - ENGINE CLASSES MODULE
// v2.11.0 - Extracted for Vercel optimization
// ==========================================

// Anti-Duplicate System
class MessageDeduplicator {
    constructor(windowMs = 500) {
        this.recentMessages = new Map();
        this.windowMs = windowMs;
    }
    
    isDuplicate(content) {
        const now = Date.now();
        const hash = this.hash(content);
        
        for (let [key, timestamp] of this.recentMessages) {
            if (now - timestamp > this.windowMs) {
                this.recentMessages.delete(key);
            }
        }
        
        if (this.recentMessages.has(hash)) {
            console.log('🚫 DUPLICATE DETECTED - Blocked');
            return true;
        }
        
        this.recentMessages.set(hash, now);
        return false;
    }
    
    hash(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return hash.toString(36);
    }
}

// Context Awareness Engine
class ContextAwarenessEngine {
    constructor() {
        this.contexts = [];
        this.activeContext = null;
        this.conversationTopics = [];
        this.projectState = null;
        this.loadContexts();
    }
    
    loadContexts() {
        const saved = localStorage.getItem('crump_contexts');
        if (saved) {
            const data = JSON.parse(saved);
            this.contexts = data.contexts || [];
            this.activeContext = data.activeContext || null;
            this.conversationTopics = data.conversationTopics || [];
            this.projectState = data.projectState || null;
        }
    }
    
    saveContexts() {
        localStorage.setItem('crump_contexts', JSON.stringify({
            contexts: this.contexts,
            activeContext: this.activeContext,
            conversationTopics: this.conversationTopics,
            projectState: this.projectState
        }));
    }
    
    addContext(label, icon = '📌') {
        const context = {
            id: Date.now().toString(),
            label,
            icon,
            createdAt: new Date().toISOString(),
            messageCount: 0,
            lastUsed: new Date().toISOString()
        };
        
        this.contexts.push(context);
        this.setActiveContext(context.id);
        this.saveContexts();
        this.renderContextCards();
        
        console.log('✅ Context added:', label);
        return context;
    }
    
    removeContext(contextId) {
        this.contexts = this.contexts.filter(c => c.id !== contextId);
        if (this.activeContext === contextId) {
            this.activeContext = this.contexts.length > 0 ? this.contexts[0].id : null;
        }
        this.saveContexts();
        this.renderContextCards();
    }
    
    setActiveContext(contextId) {
        this.activeContext = contextId;
        const context = this.contexts.find(c => c.id === contextId);
        if (context) {
            context.lastUsed = new Date().toISOString();
        }
        this.saveContexts();
        this.renderContextCards();
    }
    
    getActiveContext() {
        return this.contexts.find(c => c.id === this.activeContext);
    }
    
    detectTopicFromMessage(message) {
        const topicKeywords = {
            '🔧 Debugging': ['debug', 'error', 'bug', 'fix', 'issue', 'problem'],
            '💻 Code': ['function', 'code', 'class', 'api', 'algorithm'],
            '🎨 Design': ['design', 'ui', 'ux', 'layout', 'style', 'css'],
            '📊 Data': ['data', 'database', 'sql', 'query', 'analytics'],
            '🚀 Deploy': ['deploy', 'production', 'build', 'release'],
            '📝 Writing': ['write', 'article', 'content', 'blog', 'documentation'],
            '🧪 Testing': ['test', 'testing', 'unit test', 'e2e'],
            '📖 Learning': ['learn', 'understand', 'explain', 'tutorial']
        };
        
        const lower = message.toLowerCase();
        for (const [topic, keywords] of Object.entries(topicKeywords)) {
            if (keywords.some(kw => lower.includes(kw))) {
                return topic;
            }
        }
        return null;
    }
    
    trackMessage(role, content) {
        if (this.activeContext) {
            const context = this.contexts.find(c => c.id === this.activeContext);
            if (context) {
                context.messageCount++;
                context.lastUsed = new Date().toISOString();
                this.saveContexts();
            }
        }
        
        if (role === 'user' && this.contexts.length === 0) {
            const topic = this.detectTopicFromMessage(content);
            if (topic) {
                setTimeout(() => {
                    this.suggestContext(topic);
                }, 1000);
            }
        }
        
        const topic = this.detectTopicFromMessage(content);
        if (topic && !this.conversationTopics.includes(topic)) {
            this.conversationTopics.push(topic);
            this.saveContexts();
        }
    }
    
    suggestContext(topic) {
        const chat = window.chats.find(c => c.id === window.currentChatId);
        if (!chat) return;
        
        const container = document.getElementById('chatContainer');
        const insight = document.createElement('div');
        insight.className = 'context-insight';
        insight.innerHTML = `
            <div class="context-insight-header">
                <span>💡</span>
                <span>Context Suggestion</span>
            </div>
            <div class="context-insight-text">
                It looks like you're working on ${topic}. Would you like to add this as a context for better tracking?
            </div>
            <div class="context-insight-actions">
                <button class="context-insight-action" onclick="window.contextEngine.addContext('${topic.replace(/'/g, "\\'")}'); this.closest('.context-insight').remove();">
                    Add "${topic}"
                </button>
                <button class="context-insight-action" onclick="this.closest('.context-insight').remove();">
                    No thanks
                </button>
            </div>
        `;
        
        container.appendChild(insight);
        container.scrollTop = container.scrollHeight;
    }
    
    generateInsight() {
        const context = this.getActiveContext();
        if (!context) return null;
        
        const insights = [
            {
                text: `You've sent ${context.messageCount} messages about ${context.label}. Would you like me to summarize our progress?`,
                actions: ['Summarize progress', 'Continue working']
            },
            {
                text: `We're discussing ${context.label}. Need help with something specific?`,
                actions: ['Get suggestions', 'Ask a question', 'Switch context']
            },
            {
                text: `Working on ${context.label}. I can help with related tasks.`,
                actions: ['Show related topics', 'Get best practices', 'Continue']
            }
        ];
        
        if (context.messageCount % 5 === 0 && context.messageCount > 0) {
            return insights[Math.floor(Math.random() * insights.length)];
        }
        
        return null;
    }
    
    renderContextCards() {
        const container = document.getElementById('contextCards');
        if (!container) return;
        
        if (this.contexts.length === 0) {
            container.innerHTML = '';
            return;
        }
        
        container.innerHTML = this.contexts.map(context => `
            <div class="context-card ${context.id === this.activeContext ? 'active' : ''}">
                <div class="context-card-content" onclick="window.contextEngine.setActiveContext('${context.id}')">
                    <span class="context-card-icon">${context.icon}</span>
                    <span class="context-card-label">${context.label}</span>
                </div>
                <div class="context-card-actions">
                    <button class="context-card-btn" onclick="event.stopPropagation(); window.contextEngine.removeContext('${context.id}')" title="Remove">
                        ×
                    </button>
                </div>
            </div>
        `).join('');
    }
    
    showContinueBanner() {
        if (this.contexts.length === 0) return;
        
        const lastContext = this.contexts[this.contexts.length - 1];
        const banner = document.getElementById('continueContextBanner');
        if (!banner) return;
        
        banner.className = 'continue-context-banner';
        banner.style.display = 'flex';
        banner.innerHTML = `
            <div class="continue-context-text">
                💬 Continue working on <strong>${lastContext.label}</strong>?
            </div>
            <div class="continue-context-actions">
                <button class="continue-context-btn" onclick="window.contextEngine.setActiveContext('${lastContext.id}'); this.closest('.continue-context-banner').style.display='none'">
                    Yes, continue
                </button>
                <button class="continue-context-btn secondary" onclick="this.closest('.continue-context-banner').style.display='none'">
                    Start fresh
                </button>
            </div>
        `;
    }
}

// Context Suggestion Engine
class ContextSuggestionEngine {
    constructor() {
        this.shownSuggestions = [];
        this.lastSuggestionTime = 0;
        this.suggestionCooldowns = new Map();
        this.loadState();
    }
    
    loadState() {
        const STORAGE_KEYS = window.STORAGE_KEYS;
        const shown = localStorage.getItem(STORAGE_KEYS.SHOWN_SUGGESTIONS);
        const cooldown = localStorage.getItem(STORAGE_KEYS.SUGGESTION_COOLDOWN);
        
        if (shown) this.shownSuggestions = JSON.parse(shown);
        if (cooldown) this.lastSuggestionTime = parseInt(cooldown);
        
        window.contextSuggestionsEnabled = localStorage.getItem(STORAGE_KEYS.CONTEXT_SUGGESTIONS_ENABLED) === 'true';
    }
    
    saveState() {
        const STORAGE_KEYS = window.STORAGE_KEYS;
        localStorage.setItem(STORAGE_KEYS.SHOWN_SUGGESTIONS, JSON.stringify(this.shownSuggestions));
        localStorage.setItem(STORAGE_KEYS.SUGGESTION_COOLDOWN, this.lastSuggestionTime.toString());
    }
    
    analyzeContext(userMessage, chat) {
        if (!chat) return {};
        
        const context = {
            messageLength: userMessage.length,
            hasCode: /```|function|const|let|var|class|import/.test(userMessage),
            hasUploadedImage: window.currentFiles.length > 0,
            askingQuestion: /\?|what|how|why|when|where|can you|could you/i.test(userMessage),
            messageCount: chat.messages.filter(m => m.role === 'user').length,
            responseCount: chat.messages.filter(m => m.role === 'assistant').length,
            userCorrected: window.learningEngine ? window.learningEngine.corrections.length > 0 : false,
            feedbackGiven: window.learningEngine ? (window.learningEngine.metrics.thumbsUp + window.learningEngine.metrics.thumbsDown) : 0,
            confidenceEnabled: window.showConfidence,
            novaActive: window.isNovaActive(),
            activeContexts: window.contextEngine ? window.contextEngine.contexts.length : 0,
            hasMemoryNotes: window.userMemory.notes.length > 0,
            hasLearnedStyle: window.learningEngine?.preferences?.codingStyle !== undefined,
            isTechnical: /code|function|api|debug|error|bug|algorithm|database|deploy/.test(userMessage.toLowerCase()),
            topicChanged: this.detectTopicShift(chat),
            repeatedInfo: this.detectRepeatedInfo(chat),
            askedToGenerate: /generate|create|make.*image/.test(userMessage.toLowerCase()),
            totalChats: window.chats.length
        };
        
        return context;
    }
    
    detectTopicShift(chat) {
        if (chat.messages.length < 4) return false;
        const recentMessages = chat.messages.slice(-4);
        const topics = recentMessages.map(m => this.extractTopic(m.content));
        const lastTopic = topics[topics.length - 1];
        const previousTopics = topics.slice(0, -1);
        return lastTopic && !previousTopics.includes(lastTopic);
    }
    
    extractTopic(message) {
        const topicPatterns = {
            'code': /code|function|program|algorithm/i,
            'image': /image|picture|photo|visual/i,
            'data': /data|database|query|analytics/i,
            'design': /design|ui|ux|layout/i,
            'debug': /bug|error|fix|debug/i
        };
        
        for (const [topic, pattern] of Object.entries(topicPatterns)) {
            if (pattern.test(message)) return topic;
        }
        return null;
    }
    
    detectRepeatedInfo(chat) {
        if (chat.messages.length < 6) return false;
        const userMessages = chat.messages.filter(m => m.role === 'user').map(m => m.content.toLowerCase()).slice(-5);
        const wordCounts = {};
        userMessages.forEach(msg => {
            const words = msg.split(/\s+/).filter(w => w.length > 5);
            words.forEach(word => {
                wordCounts[word] = (wordCounts[word] || 0) + 1;
            });
        });
        return Object.values(wordCounts).some(count => count >= 3);
    }
    
    shouldShowSuggestion() {
        if (!window.contextSuggestionsEnabled) return false;
        const now = Date.now();
        const SUGGESTION_COOLDOWN_MS = 5 * 60 * 1000;
        if (now - this.lastSuggestionTime < SUGGESTION_COOLDOWN_MS) return false;
        return true;
    }
    
    findRelevantSuggestion(userMessage, chat) {
        if (!this.shouldShowSuggestion()) return null;
        const context = this.analyzeContext(userMessage, chat);
        const now = Date.now();
        
        const contextSuggestions = window.contextSuggestions || [];
        const eligibleSuggestions = contextSuggestions.filter(suggestion => {
            const lastShown = this.suggestionCooldowns.get(suggestion.id) || 0;
            if (now - lastShown < suggestion.cooldown) return false;
            if (!suggestion.condition(context)) return false;
            return true;
        });
        
        if (eligibleSuggestions.length === 0) return null;
        
        const priorityOrder = { high: 3, medium: 2, low: 1 };
        eligibleSuggestions.sort((a, b) => priorityOrder[b.priority] - priorityOrder[a.priority]);
        
        return eligibleSuggestions[0];
    }
    
    showSuggestion(suggestion) {
        if (!suggestion) return;
        
        const now = Date.now();
        this.lastSuggestionTime = now;
        this.suggestionCooldowns.set(suggestion.id, now);
        this.shownSuggestions.push({ id: suggestion.id, timestamp: now });
        
        if (this.shownSuggestions.length > 50) {
            this.shownSuggestions = this.shownSuggestions.slice(-50);
        }
        
        this.saveState();
        this.displaySuggestion(suggestion);
    }
    
    displaySuggestion(suggestion) {
        const container = document.getElementById('chatContainer');
        if (!container) return;
        
        const suggestionEl = document.createElement('div');
        suggestionEl.className = 'context-suggestion-bubble';
        suggestionEl.style.cssText = `
            margin: 16px auto;
            max-width: 500px;
            padding: 16px 20px;
            background: linear-gradient(135deg, rgba(212, 175, 55, 0.1), rgba(184, 148, 31, 0.05));
            border: 1px solid var(--accent-primary);
            border-radius: 12px;
            animation: slideIn 0.3s ease;
            position: relative;
        `;
        
        suggestionEl.innerHTML = `
            <div style="display: flex; align-items: start; gap: 12px;">
                <div style="font-size: 24px; flex-shrink: 0;">💡</div>
                <div style="flex: 1;">
                    <div style="font-size: 14px; font-weight: 600; color: var(--accent-primary); margin-bottom: 6px;">
                        Suggestion
                    </div>
                    <div style="font-size: 13px; color: var(--text-primary); margin-bottom: 8px; line-height: 1.5;">
                        ${suggestion.message}
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); padding: 8px 12px; background: rgba(255,255,255,0.05); border-radius: 6px; border-left: 2px solid var(--accent-primary);">
                        ${suggestion.action}
                    </div>
                </div>
                <button 
                    onclick="this.closest('.context-suggestion-bubble').remove()"
                    style="background: transparent; border: none; color: var(--text-tertiary); font-size: 18px; cursor: pointer; padding: 4px; flex-shrink: 0; transition: color 0.2s;"
                    onmouseover="this.style.color='var(--accent-primary)'"
                    onmouseout="this.style.color='var(--text-tertiary)'"
                >×</button>
            </div>
        `;
        
        container.appendChild(suggestionEl);
        container.scrollTop = container.scrollHeight;
        console.log('💡 Suggestion shown:', suggestion.id);
    }
    
    checkAndShowSuggestion(userMessage, chat) {
        if (!window.contextSuggestionsEnabled) return;
        const suggestion = this.findRelevantSuggestion(userMessage, chat);
        if (suggestion) {
            setTimeout(() => {
                this.showSuggestion(suggestion);
            }, 2000);
        }
    }
}

// Autonomous Message Engine
class AutonomousMessageEngine {
    constructor() {
        this.lastAutonomousMessage = null;
        this.intervalPreset = 'balanced';
        this.updateIntervals();
        this.checkInterval = null;
    }
    
    updateIntervals() {
        const presets = {
            'relaxed': { min: 15, idle: 15, check: 60 },
            'balanced': { min: 5, idle: 5, check: 30 },
            'active': { min: 2, idle: 2, check: 15 },
            'very-active': { min: 1, idle: 1, check: 10 }
        };
        
        const preset = presets[this.intervalPreset] || presets['balanced'];
        this.MIN_INTERVAL = preset.min * 60 * 1000;
        this.IDLE_THRESHOLD = preset.idle * 60 * 1000;
        this.CHECK_FREQUENCY = preset.check * 1000;
    }
    
    setIntervalPreset(preset) {
        this.intervalPreset = preset;
        this.updateIntervals();
        
        if (this.checkInterval) {
            this.stop();
            this.start();
        }
    }
    
    start() {
        if (this.checkInterval) return;
        console.log(`🤖 Autonomous messages activated (${this.intervalPreset} mode)`);
        
        this.checkInterval = setInterval(() => {
            this.checkForAutonomousMessage();
        }, this.CHECK_FREQUENCY);
    }
    
    stop() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
            this.checkInterval = null;
            console.log('🤖 Autonomous messages deactivated');
        }
    }
    
    checkForAutonomousMessage() {
        if (!window.canExitErrorState()) {
            console.log('⏸️ Autonomous message blocked - error cooldown active');
            return;
        }
        
        const now = Date.now();
        const timeSinceLastActivity = now - window.lastUserActivity;
        const timeSinceLastAutonomous = this.lastAutonomousMessage ? now - this.lastAutonomousMessage : Infinity;
        
        if (timeSinceLastAutonomous < this.MIN_INTERVAL) return;
        
        // Get current chat for context awareness
        const currentChat = window.chats && window.chats.find(c => c.id === window.currentChatId);
        const messages = currentChat ? currentChat.messages : [];
        
        // Check if user is stuck
        if (messages.length >= 3 && this.detectIfStuck(messages)) {
            const topic = this.detectConversationTopic(messages);
            this.sendAutonomousMessage(this.getStuckMessage(topic));
            return;
        }
        
        // Feature tips (when idle)
        if (window.shouldShowFeatureTip && window.shouldShowFeatureTip() && timeSinceLastActivity >= this.IDLE_THRESHOLD) {
            const tip = window.getRandomFeatureTip && window.getRandomFeatureTip();
            if (tip) {
                this.sendAutonomousMessage(tip.message);
                return;
            }
        }
        
        // Late night check (highest priority after stuck detection)
        const hour = new Date().getHours();
        if (hour >= 2 && hour < 5) {
            this.sendAutonomousMessage(this.getLateNightMessage());
            return;
        }
        
        // Long session check
        const memory = window.getUniversalMemory && window.getUniversalMemory();
        if (memory && memory.conversationHistory.lastInteraction) {
            const sessionStart = new Date(memory.conversationHistory.lastInteraction);
            const sessionDuration = (now - sessionStart.getTime()) / (1000 * 60 * 60);
            
            if (sessionDuration >= 2 && timeSinceLastActivity < 5 * 60 * 1000) {
                this.sendAutonomousMessage(this.getLongSessionMessage());
                return;
            }
        }
        
        // Context-aware or idle message
        if (timeSinceLastActivity >= this.IDLE_THRESHOLD) {
            const topic = messages.length > 0 ? this.detectConversationTopic(messages) : null;
            const message = topic ? this.getTopicMessage(topic) : this.getIdleMessage();
            this.sendAutonomousMessage(message);
            return;
        }
    }
    
    sendAutonomousMessage(message) {
        if (!message) return;
        
        this.lastAutonomousMessage = Date.now();
        
        if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
            new Notification('Crump AI', {
                body: message,
                icon: '/assets/icon-192.png',
                badge: '/assets/icon-192.png',
                tag: 'autonomous-message'
            });
        }
        
        if (window.addMessage) {
            window.addMessage('assistant', '💭 ' + message);
        }
    }
    
    getIdleMessage() {
        const messages = [
            "Still around?",
            "Need anything?",
            "Everything good?",
            "Want to continue?",
            "Break time or keep going?"
        ];
        return messages[Math.floor(Math.random() * messages.length)];
    }
    
    getLateNightMessage() {
        const messages = [
            "Past 2am. Seriously, get some sleep.",
            "It's very late. This can wait till morning.",
            "2am grind? Your health matters more.",
            "Consider wrapping up. You'll think clearer after rest.",
            "Late night work session. Don't forget to sleep."
        ];
        return messages[Math.floor(Math.random() * messages.length)];
    }
    
    getLongSessionMessage() {
        const messages = [
            "2+ hours in. Quick break?",
            "Long session. Stretch and hydrate?",
            "Been at this a while. 5-minute break?",
            "Solid focus. Consider a quick reset.",
            "Long grind. Pause to recharge?"
        ];
        return messages[Math.floor(Math.random() * messages.length)];
    }
    
    // NEW: Context-aware messages
    detectConversationTopic(messages) {
        const allText = messages.map(m => m.content).join(' ').toLowerCase();
        
        const topics = {
            'debugging': ['debug', 'error', 'bug', 'fix', 'broken', 'not working'],
            'coding': ['function', 'code', 'class', 'implement', 'algorithm', 'api'],
            'design': ['design', 'ui', 'ux', 'layout', 'style', 'colors'],
            'writing': ['write', 'content', 'article', 'blog', 'story'],
            'learning': ['learn', 'understand', 'explain', 'how does', 'what is'],
            'planning': ['plan', 'strategy', 'approach', 'should i', 'roadmap']
        };
        
        for (const [topic, keywords] of Object.entries(topics)) {
            if (keywords.some(kw => allText.includes(kw))) {
                return topic;
            }
        }
        
        return null;
    }
    
    detectIfStuck(messages) {
        // Check if last 3 messages are similar (user asking same thing different ways)
        if (messages.length < 3) return false;
        
        const last3 = messages.slice(-3).map(m => m.content.toLowerCase());
        const similarities = [];
        
        for (let i = 0; i < last3.length - 1; i++) {
            const words1 = last3[i].split(' ').filter(w => w.length > 4);
            const words2 = last3[i + 1].split(' ').filter(w => w.length > 4);
            const commonWords = words1.filter(w => words2.includes(w));
            
            if (commonWords.length >= 2) {
                similarities.push(true);
            }
        }
        
        return similarities.length >= 2;
    }
    
    getStuckMessage(topic) {
        const messages = [
            "Seems like you're hitting a wall. Want me to look at this from a different angle?",
            "Notice you're circling back. Need a fresh perspective?",
            "Stuck on something? Let's try a different approach.",
            "This feels like a tough one. Want to step back and reassess?",
            "Need a break or want to brainstorm alternatives?"
        ];
        
        return messages[Math.floor(Math.random() * messages.length)];
    }
    
    getTopicMessage(topic) {
        const topicMessages = {
            'debugging': [
                "Still tracking down that bug?",
                "How's the debugging going?",
                "Find the issue yet?",
                "Want me to look at it with fresh eyes?"
            ],
            'coding': [
                "How's the code coming along?",
                "Making progress on that implementation?",
                "Need a code review?",
                "Want to refactor anything?"
            ],
            'design': [
                "Liking how the design is shaping up?",
                "How's the UI feeling?",
                "Want feedback on the design?",
                "Ready to see how it looks?"
            ],
            'writing': [
                "How's the writing flow?",
                "Need a fresh set of eyes on your draft?",
                "Want to workshop any sections?",
                "Making good progress?"
            ],
            'learning': [
                "Making sense so far?",
                "Want me to explain any part differently?",
                "Need more examples?",
                "Ready to test your understanding?"
            ],
            'planning': [
                "How's the plan looking?",
                "Ready to move forward?",
                "Want to refine the approach?",
                "Need to think through any edge cases?"
            ]
        };
        
        const messages = topicMessages[topic] || [
            "How's it going?",
            "Need anything?",
            "Making progress?"
        ];
        
        return messages[Math.floor(Math.random() * messages.length)];
    }
}

// Learning Engine - Cognition System
class LearningEngine {
    constructor() {
        this.corrections = [];
        this.preferences = {
            responseLength: 'adaptive',
            codeStyle: 'modern',
            tone: 'direct',
            explanationLevel: 'medium'
        };
        this.metrics = {
            totalInteractions: 0,
            correctionsReceived: 0,
            thumbsUp: 0,
            thumbsDown: 0,
            topicsLearned: [],
            improvementRate: 0
        };
        this.loadLearningData();
    }
    
    loadLearningData() {
        const STORAGE_KEYS = window.STORAGE_KEYS;
        const savedCorrections = localStorage.getItem(STORAGE_KEYS.CORRECTIONS);
        if (savedCorrections) this.corrections = JSON.parse(savedCorrections);
        
        const savedPreferences = localStorage.getItem(STORAGE_KEYS.USER_PREFERENCES);
        if (savedPreferences) this.preferences = { ...this.preferences, ...JSON.parse(savedPreferences) };
        
        const savedMetrics = localStorage.getItem(STORAGE_KEYS.PERFORMANCE_METRICS);
        if (savedMetrics) this.metrics = { ...this.metrics, ...JSON.parse(savedMetrics) };
    }
    
    saveLearningData() {
        const STORAGE_KEYS = window.STORAGE_KEYS;
        localStorage.setItem(STORAGE_KEYS.CORRECTIONS, JSON.stringify(this.corrections));
        localStorage.setItem(STORAGE_KEYS.USER_PREFERENCES, JSON.stringify(this.preferences));
        localStorage.setItem(STORAGE_KEYS.PERFORMANCE_METRICS, JSON.stringify(this.metrics));
    }
    
    recordCorrection(originalResponse, correction, context) {
        const correctionEntry = {
            id: Date.now().toString(),
            timestamp: new Date().toISOString(),
            original: originalResponse,
            corrected: correction,
            context: context,
            applied: false,
            frequency: 0
        };
        
        this.corrections.push(correctionEntry);
        this.metrics.correctionsReceived++;
        this.metrics.totalInteractions++;
        this.saveLearningData();
        
        console.log('📚 Learning: Correction recorded', correctionEntry);
        return correctionEntry;
    }
    
    detectCorrectionPattern(userMessage, lastResponse) {
        const correctionIndicators = [
            'no, actually', 'incorrect', 'wrong', 'not quite',
            'actually it should be', 'the correct', 'fix:',
            'instead do', 'better approach', 'should be'
        ];
        
        const lowerMsg = userMessage.toLowerCase();
        const isCorrection = correctionIndicators.some(indicator => lowerMsg.includes(indicator));
        
        if (isCorrection && lastResponse) {
            return {
                isCorrection: true,
                original: lastResponse,
                correction: userMessage,
                confidence: 0.8
            };
        }
        
        return { isCorrection: false };
    }
    
    recordFeedback(messageId, feedbackType) {
        if (feedbackType === 'thumbsUp') {
            this.metrics.thumbsUp++;
        } else {
            this.metrics.thumbsDown++;
        }
        
        this.metrics.totalInteractions++;
        this.calculateImprovementRate();
        this.saveLearningData();
    }
    
    learnPreference(key, value) {
        this.preferences[key] = value;
        this.saveLearningData();
        console.log(`📚 Learning: Preference updated - ${key}: ${value}`);
    }
    
    detectPreferenceFromMessage(message) {
        const lower = message.toLowerCase();
        
        if (lower.includes('too long') || lower.includes('be brief')) {
            this.learnPreference('responseLength', 'brief');
        } else if (lower.includes('more detail') || lower.includes('explain more')) {
            this.learnPreference('responseLength', 'detailed');
        }
        
        if (lower.includes('more casual') || lower.includes('less formal')) {
            this.learnPreference('tone', 'casual');
        } else if (lower.includes('more professional') || lower.includes('formal')) {
            this.learnPreference('tone', 'professional');
        }
    }
    
    calculateImprovementRate() {
        if (this.metrics.totalInteractions === 0) {
            this.metrics.improvementRate = 0;
            return;
        }
        
        const positiveRate = this.metrics.thumbsUp / this.metrics.totalInteractions;
        const correctionRate = this.metrics.correctionsReceived / this.metrics.totalInteractions;
        
        this.metrics.improvementRate = Math.round((positiveRate * 0.7 + (1 - correctionRate) * 0.3) * 100);
    }
    
    getRelevantCorrections(context) {
        return this.corrections.filter(c => 
            c.context && context && c.context.toLowerCase().includes(context.toLowerCase())
        ).slice(-5);
    }
    
    getLearningStats() {
        return {
            totalCorrections: this.corrections.length,
            totalInteractions: this.metrics.totalInteractions,
            positiveRate: this.metrics.totalInteractions > 0 
                ? Math.round((this.metrics.thumbsUp / this.metrics.totalInteractions) * 100) 
                : 0,
            improvementRate: this.metrics.improvementRate,
            preferences: this.preferences,
            recentCorrections: this.corrections.slice(-10)
        };
    }
    
    calculateConfidence(context, hasSearched = false) {
        let confidence = 50;
        
        const relevantCorrections = this.getRelevantCorrections(context);
        if (relevantCorrections.length > 0) {
            confidence += 15;
        }
        
        if (hasSearched) {
            confidence += 20;
        }
        
        if (this.metrics.totalInteractions > 0) {
            const successRate = this.metrics.thumbsUp / this.metrics.totalInteractions;
            confidence += Math.round(successRate * 15);
        }
        
        confidence = Math.min(confidence, 95);
        
        return {
            score: confidence,
            level: this.getConfidenceLevel(confidence),
            reason: this.getConfidenceReason(confidence, relevantCorrections, hasSearched)
        };
    }
    
    getConfidenceLevel(score) {
        if (score >= 80) return 'Very High';
        if (score >= 65) return 'High';
        if (score >= 50) return 'Medium';
        if (score >= 35) return 'Low';
        return 'Very Low';
    }
    
    getConfidenceReason(score, corrections, searched) {
        const reasons = [];
        
        if (corrections.length > 0) {
            reasons.push(`Learned from ${corrections.length} similar correction${corrections.length > 1 ? 's' : ''}`);
        }
        
        if (searched) {
            reasons.push('Verified with web search');
        }
        
        if (this.metrics.thumbsUp > 0) {
            const rate = Math.round((this.metrics.thumbsUp / this.metrics.totalInteractions) * 100);
            reasons.push(`${rate}% positive feedback rate`);
        }
        
        if (reasons.length === 0) {
            return 'Based on training data';
        }
        
        return reasons.join(' • ');
    }
    
    identifyKnowledgeGaps() {
        const topicCounts = {};
        
        this.corrections.forEach(correction => {
            const context = correction.context || 'general';
            topicCounts[context] = (topicCounts[context] || 0) + 1;
        });
        
        const gaps = Object.entries(topicCounts)
            .filter(([topic, count]) => count >= 2)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([topic, count]) => ({ topic, corrections: count }));
        
        return gaps;
    }
    
    startTrainingSession(topic) {
        return {
            topic: topic,
            startTime: Date.now(),
            questionsAsked: 0,
            correctAnswers: 0,
            active: true
        };
    }
    
    recordTrainingAnswer(session, wasCorrect) {
        session.questionsAsked++;
        if (wasCorrect) session.correctAnswers++;
        
        const accuracy = session.correctAnswers / session.questionsAsked;
        return {
            accuracy: Math.round(accuracy * 100),
            progress: session.questionsAsked
        };
    }
    
    endTrainingSession(session) {
        session.active = false;
        session.endTime = Date.now();
        session.duration = Math.round((session.endTime - session.startTime) / 1000);
        
        const accuracy = session.correctAnswers / session.questionsAsked;
        
        if (accuracy >= 0.7) {
            this.metrics.topicsLearned.push({
                topic: session.topic,
                accuracy: Math.round(accuracy * 100),
                timestamp: new Date().toISOString()
            });
            this.saveLearningData();
        }
        
        return session;
    }
    
    recognizePattern(input, category = 'code') {
        const patterns = {
            code: {
                reactComponent: /function\s+\w+\s*\(.*\)\s*{|const\s+\w+\s*=\s*\(.*\)\s*=>/,
                asyncFunction: /async\s+function|async\s+\(|await\s+/,
                arrowFunction: /=>\s*{|=>\s*\(/,
                classDefinition: /class\s+\w+/,
                apiCall: /fetch\(|axios\.|\.get\(|\.post\(/,
                useState: /useState\(/,
                useEffect: /useEffect\(/
            },
            preference: {
                wantsDetail: /explain|detail|how does|why|elaborate/i,
                wantsBrief: /brief|quick|tldr|summary|short/i,
                wantsCasual: /casual|friendly|relax/i,
                wantsFormal: /formal|professional|business/i
            }
        };
        
        const detected = [];
        const categoryPatterns = patterns[category] || {};
        
        for (const [name, regex] of Object.entries(categoryPatterns)) {
            if (regex.test(input)) {
                detected.push(name);
            }
        }
        
        return detected;
    }
    
    getMetaCommentary(messageContent, confidence) {
        const commentary = {
            approach: this.explainApproach(messageContent),
            confidence: `I'm ${confidence.level.toLowerCase()} confidence (${confidence.score}%) because ${confidence.reason.toLowerCase()}`,
            sources: this.identifySources(messageContent),
            alternatives: this.suggestAlternatives(messageContent)
        };
        
        return commentary;
    }
    
    explainApproach(content) {
        if (content.includes('```')) {
            return "I analyzed the code structure and provided a technical solution based on best practices.";
        }
        if (content.length > 500) {
            return "I provided a detailed explanation to ensure clarity and completeness.";
        }
        if (content.includes('?')) {
            return "I addressed your question directly with relevant information.";
        }
        return "I crafted a response based on the context of your message.";
    }
    
    identifySources(content) {
        const sources = [];
        
        if (this.corrections.length > 0) {
            sources.push("previous corrections you've given me");
        }
        if (this.metrics.totalInteractions > 10) {
            sources.push("our conversation history");
        }
        sources.push("my training data");
        
        return sources;
    }
    
    suggestAlternatives(content) {
        const alternatives = [];
        
        if (content.includes('```')) {
            alternatives.push("I could provide more detailed comments in the code");
            alternatives.push("I could explain the logic step-by-step");
        } else if (content.length > 300) {
            alternatives.push("I could make this more concise");
            alternatives.push("I could break this into bullet points");
        }
        
        return alternatives;
    }
    
    shouldRequestTraining() {
        const gaps = this.identifyKnowledgeGaps();
        const lowConfidenceResponses = this.metrics.thumbsDown;
        const totalResponses = this.metrics.totalInteractions;
        
        if (gaps.length >= 3 || (totalResponses > 5 && lowConfidenceResponses / totalResponses > 0.3)) {
            return {
                shouldAsk: true,
                reason: gaps.length >= 3 ? 'knowledge_gaps' : 'low_confidence',
                gaps: gaps
            };
        }
        
        return { shouldAsk: false };
    }
    
    getProactiveTrainingRequest() {
        const request = this.shouldRequestTraining();
        if (!request.shouldAsk) return null;
        
        if (request.reason === 'knowledge_gaps') {
            const topGap = request.gaps[0];
            return `📚 **Learning Request**\n\nI've noticed I've been corrected ${topGap.corrections} times on **${topGap.topic}**. Would you mind training me on this? Say "train me on ${topGap.topic}" to start a quick training session.`;
        } else {
            return `📚 **Learning Request**\n\nI've received some negative feedback recently. Could we do a quick training session to help me improve? What topic would you like to train me on?`;
        }
    }
    
    learnCodingStyle(codeSnippet) {
        const style = {
            indentation: this.detectIndentation(codeSnippet),
            quotes: this.detectQuoteStyle(codeSnippet),
            semicolons: this.detectSemicolonUsage(codeSnippet),
            namingConvention: this.detectNamingConvention(codeSnippet),
            timestamp: new Date().toISOString()
        };
        
        this.preferences.codingStyle = style;
        this.saveLearningData();
        
        console.log('🎨 Coding style learned:', style);
        return style;
    }
    
    detectIndentation(code) {
        const lines = code.split('\n');
        let spaces = 0;
        let tabs = 0;
        
        lines.forEach(line => {
            if (line.startsWith('    ')) spaces++;
            if (line.startsWith('\t')) tabs++;
        });
        
        if (spaces > tabs) return spaces >= 4 ? '4 spaces' : '2 spaces';
        if (tabs > 0) return 'tabs';
        return 'unknown';
    }
    
    detectQuoteStyle(code) {
        const single = (code.match(/'/g) || []).length;
        const double = (code.match(/"/g) || []).length;
        const backtick = (code.match(/`/g) || []).length;
        
        if (backtick > single && backtick > double) return 'backticks';
        if (single > double) return 'single';
        if (double > single) return 'double';
        return 'mixed';
    }
    
    detectSemicolonUsage(code) {
        const lines = code.split('\n').filter(l => l.trim().length > 0);
        const withSemi = lines.filter(l => l.trim().endsWith(';')).length;
        const ratio = withSemi / lines.length;
        
        if (ratio > 0.7) return 'always';
        if (ratio < 0.3) return 'never';
        return 'sometimes';
    }
    
    detectNamingConvention(code) {
        const camelCase = (code.match(/[a-z][A-Z]/g) || []).length;
        const snake_case = (code.match(/[a-z]_[a-z]/g) || []).length;
        
        if (camelCase > snake_case) return 'camelCase';
        if (snake_case > camelCase) return 'snake_case';
        return 'mixed';
    }
    
    getLearningHistory() {
        const history = [];
        
        if (this.corrections.length > 0) {
            const firstCorrection = this.corrections[0];
            history.push({
                type: 'correction',
                timestamp: firstCorrection.timestamp,
                description: 'First correction received',
                icon: '📝'
            });
            
            if (this.corrections.length >= 5) {
                const fifthCorrection = this.corrections[4];
                history.push({
                    type: 'milestone',
                    timestamp: fifthCorrection.timestamp,
                    description: '5 corrections learned',
                    icon: '🎓'
                });
            }
            
            if (this.corrections.length >= 10) {
                const tenthCorrection = this.corrections[9];
                history.push({
                    type: 'milestone',
                    timestamp: tenthCorrection.timestamp,
                    description: '10 corrections learned',
                    icon: '🏆'
                });
            }
        }
        
        this.metrics.topicsLearned.forEach(topic => {
            history.push({
                type: 'training',
                timestamp: topic.timestamp,
                description: `Completed training on ${topic.topic} (${topic.accuracy}% accuracy)`,
                icon: '✅'
            });
        });
        
        history.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        
        return history;
    }
    
    verifyKnowledge(topic) {
        const relevantCorrections = this.corrections.filter(c => 
            c.context && c.context.toLowerCase().includes(topic.toLowerCase())
        );
        
        const learnedTopics = this.metrics.topicsLearned.filter(t =>
            t.topic.toLowerCase().includes(topic.toLowerCase())
        );
        
        const confidence = {
            hasCorrections: relevantCorrections.length > 0,
            hasTraining: learnedTopics.length > 0,
            correctionCount: relevantCorrections.length,
            trainingAccuracy: learnedTopics.length > 0 ? learnedTopics[0].accuracy : 0,
            verified: relevantCorrections.length === 0 && learnedTopics.length > 0
        };
        
        return confidence;
    }
}

// Export all classes to window
window.MessageDeduplicator = MessageDeduplicator;
window.ContextAwarenessEngine = ContextAwarenessEngine;
window.ContextSuggestionEngine = ContextSuggestionEngine;
window.AutonomousMessageEngine = AutonomousMessageEngine;
window.LearningEngine = LearningEngine;

console.log('✅ Engines module loaded');
