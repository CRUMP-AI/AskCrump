// ==========================================
// CRUMP AI - AUTONOMOUS MESSAGING v3.5 ENHANCED
// Human-Natural Autonomous Interactions
// ==========================================

class AutonomousMessaging {
    constructor() {
        this.enabled = this.loadSettings().enabled;
        this.frequency = this.loadSettings().frequency || 'medium';
        this.timerId = null;
        this.lastMessageTime = Date.now();
        this.lastUserActivityTime = Date.now();
        this.autonomousHistory = this.loadAutonomousHistory();
        this.lastAutonomousMessage = null;
        this.consecutiveAutonomous = 0;
        this.userEngagementScore = this.loadEngagementScore();
        
        console.log('🤖 Autonomous Messaging v3.5 ENHANCED initialized');
        console.log('   Enabled:', this.enabled);
        console.log('   Frequency:', this.frequency);
        console.log('   Previous autonomous messages:', this.autonomousHistory.length);
        console.log('   Engagement score:', this.userEngagementScore.toFixed(2));
        
        // Setup activity monitoring
        this.setupActivityMonitoring();
        
        // Auto-start if enabled
        if (this.enabled) {
            this.start();
        }
    }

    // ==========================================
    // ACTIVITY MONITORING
    // ==========================================
    
    setupActivityMonitoring() {
        const events = ['mousedown', 'keydown', 'scroll', 'touchstart'];
        
        events.forEach(event => {
            document.addEventListener(event, () => {
                this.lastUserActivityTime = Date.now();
            }, { passive: true });
        });
        
        window.addEventListener('focus', () => {
            this.lastUserActivityTime = Date.now();
        });
        
        console.log('👀 Activity monitoring enabled');
    }

    // ==========================================
    // INTELLIGENT TIMING
    // ==========================================
    
    shouldSendAutonomousMessage() {
        // Don't interrupt if user is typing or app is processing
        if (window.isProcessing) {
            console.log('⏸️ Skipping - app is busy');
            return false;
        }

        const userInput = document.getElementById('userInput');
        if (userInput && userInput.value.trim().length > 0) {
            console.log('⏸️ Skipping - user is typing');
            return false;
        }

        // Adaptive idle time based on engagement
        const timeSinceLastMessage = Date.now() - this.lastMessageTime;
        const timeSinceLastActivity = Date.now() - this.lastUserActivityTime;
        
        const baseIdleTime = 60000; // 1 minute base
        const adjustedIdleTime = baseIdleTime * (1 + (1 - this.userEngagementScore));
        
        if (timeSinceLastMessage < adjustedIdleTime) {
            console.log('⏸️ Skipping - user recently active in chat');
            return false;
        }
        
        if (timeSinceLastActivity < 30000) { // 30 seconds
            console.log('⏸️ Skipping - user actively using app');
            return false;
        }

        // Prevent spam
        if (this.consecutiveAutonomous >= 2) {
            console.log('⏸️ Skipping - too many consecutive messages');
            return false;
        }

        // Work hours check
        if (this.isInWorkMode() && !this.isWorkHours()) {
            console.log('⏸️ Skipping - outside work hours');
            return false;
        }

        // Night time probability
        const hour = new Date().getHours();
        if (hour >= 23 || hour <= 6) {
            if (Math.random() > 0.2) {
                console.log('⏸️ Skipping - late night (low probability)');
                return false;
            }
        }

        return true;
    }

    // ==========================================
    // CONTEXT ANALYSIS
    // ==========================================
    
    analyzeConversationContext(chat) {
        const recentMessages = chat.messages.slice(-10);
        
        // Check for open topics
        const lastUserMessage = [...recentMessages].reverse()
            .find(m => m.role === 'user');
        
        const hasOpenTopic = lastUserMessage && 
            (lastUserMessage.content.includes('?') || 
             lastUserMessage.content.includes('working on') ||
             lastUserMessage.content.includes('trying to'));
        
        // Extract topic
        let openTopic = null;
        if (hasOpenTopic && window.contextTracker) {
            const topics = window.contextTracker.getRecentTopics(1);
            if (topics.length > 0) {
                openTopic = topics[0].words[0] || null;
            }
        }
        
        // Conversation energy
        const recentAssistantMessages = recentMessages
            .filter(m => m.role === 'assistant')
            .slice(-3);
        
        const averageLength = recentAssistantMessages.reduce((sum, m) => 
            sum + m.content.length, 0) / recentAssistantMessages.length || 0;
        
        return {
            hasOpenTopic,
            openTopic,
            conversationEnergy: averageLength > 200 ? 'high' : 'low',
            messageCount: recentMessages.length,
            timeSinceStart: Date.now() - chat.createdAt
        };
    }

    getRecentSentiment() {
        if (!window.sentimentAnalyzer) return null;
        
        try {
            return window.sentimentAnalyzer.getRecentEmotionalState(3);
        } catch (e) {
            return null;
        }
    }

    getContextSummary() {
        if (!window.contextTracker) return null;
        
        try {
            const summary = window.contextTracker.getContextSummary();
            return `Activity: ${summary.activity.messagesInSession} messages in session | Topics: ${summary.topics.top.slice(0, 3).map(t => t.topic).join(', ')}`;
        } catch (e) {
            return null;
        }
    }

    determineMessageType(context, sentiment) {
        if (context.hasOpenTopic) {
            return 'followup';
        } else if (sentiment && sentiment !== 'neutral') {
            return 'mood_aware';
        } else {
            return 'casual_checkin';
        }
    }

    // ==========================================
    // MESSAGE GENERATION
    // ==========================================

    async sendAutonomousMessage() {
        try {
            if (!this.shouldSendAutonomousMessage()) {
                return;
            }

            console.log('🤖 Generating autonomous message...');

            const currentChat = window.chats?.find(c => c.id === window.currentChatId);
            if (!currentChat) {
                console.warn('⚠️ No current chat found');
                return;
            }

            // Analyze context
            const context = this.analyzeConversationContext(currentChat);
            const sentiment = this.getRecentSentiment();
            const contextSummary = this.getContextSummary();
            const messageType = this.determineMessageType(context, sentiment);

            // Get conversation context
            const recentMessages = currentChat.messages.slice(-10);
            const conversationContext = recentMessages.map(m => 
                `${m.role}: ${m.content}`
            ).join('\n');

            // Get autonomous history
            const autonomousContext = this.getRecentAutonomousContext(5);

            // Call API
            const response = await fetch('/api/autonomous', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    conversationContext: conversationContext,
                    autonomousContext: autonomousContext,
                    chatHistory: recentMessages,
                    currentDateTime: {
                        date: new Date().toLocaleDateString('en-US', { 
                            weekday: 'long', 
                            year: 'numeric', 
                            month: 'long', 
                            day: 'numeric' 
                        }),
                        time: new Date().toLocaleTimeString('en-US', { 
                            hour: 'numeric', 
                            minute: '2-digit',
                            hour12: true 
                        }),
                        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
                    },
                    userSentiment: sentiment,
                    contextSummary: contextSummary,
                    messageType: messageType
                })
            });

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            const data = await response.json();
            
            if (!data.message) {
                console.warn('⚠️ No message generated');
                return;
            }

            // Add to chat
            const autonomousMsg = {
                role: 'assistant',
                content: data.message,
                timestamp: Date.now(),
                autonomous: true
            };

            currentChat.messages.push(autonomousMsg);
            currentChat.updatedAt = Date.now();

            // Save
            if (typeof window.saveChats === 'function') {
                window.saveChats();
            }

            // Render
            if (typeof window.renderMessages === 'function') {
                window.renderMessages(currentChat.messages);
            }

            if (typeof window.renderChatsList === 'function') {
                window.renderChatsList();
            }

            // Scroll
            if (window.crumpScrollManager) {
                setTimeout(() => {
                    window.crumpScrollManager.scrollToBottom('smooth');
                }, 200);
            }

            // Sound
            this.playNotificationSound();

            // Track
            this.lastAutonomousMessage = {
                message: data.message,
                timestamp: Date.now()
            };

            this.consecutiveAutonomous++;

            // Record
            this.recordAutonomousMessage(data.message);

            // Sync to universal memory
            if (typeof window.universalMemory === 'undefined') {
                window.universalMemory = {
                    autonomousHistory: [],
                    userProfile: {},
                    crossSessionContext: [],
                    conversationHistory: {}
                };
            }
            window.universalMemory.autonomousHistory = this.autonomousHistory;

            console.log('✅ Autonomous message sent:', data.message.substring(0, 50) + '...');

        } catch (error) {
            console.error('❌ Autonomous message error:', error);
        }
    }

    // ==========================================
    // USER ENGAGEMENT
    // ==========================================
    
    onUserResponse(userMessage) {
        this.consecutiveAutonomous = 0;
        
        if (this.lastAutonomousMessage && 
            (Date.now() - this.lastAutonomousMessage.timestamp) < 300000) {
            
            this.recordAutonomousMessage(
                this.lastAutonomousMessage.message,
                userMessage
            );
            
            this.userEngagementScore = Math.min(1.0, this.userEngagementScore + 0.1);
            this.saveEngagementScore();
            
            this.lastAutonomousMessage = null;
            
            console.log('✅ User responded to autonomous message');
            console.log('📈 Engagement score:', this.userEngagementScore.toFixed(2));
        } else {
            this.userEngagementScore = Math.min(1.0, this.userEngagementScore + 0.05);
            this.saveEngagementScore();
        }
        
        this.lastMessageTime = Date.now();
    }

    // ==========================================
    // HISTORY TRACKING
    // ==========================================
    
    loadAutonomousHistory() {
        try {
            const saved = localStorage.getItem('crump_autonomous_history');
            if (saved) {
                return JSON.parse(saved).slice(-50);
            }
        } catch (e) {
            console.warn('⚠️ Failed to load autonomous history:', e);
        }
        return [];
    }
    
    saveAutonomousHistory() {
        try {
            localStorage.setItem('crump_autonomous_history', JSON.stringify(this.autonomousHistory));
        } catch (e) {
            console.warn('⚠️ Failed to save autonomous history:', e);
        }
    }
    
    recordAutonomousMessage(message, response = null) {
        const record = {
            timestamp: Date.now(),
            message: message,
            response: response,
            chatId: window.currentChatId,
            responseTime: response ? Date.now() : null
        };
        
        const lastMsg = this.autonomousHistory[this.autonomousHistory.length - 1];
        
        if (response && lastMsg && lastMsg.message === message && !lastMsg.response) {
            lastMsg.response = response;
            lastMsg.responseTime = Date.now();
        } else if (!response) {
            this.autonomousHistory.push(record);
        }
        
        if (this.autonomousHistory.length > 50) {
            this.autonomousHistory.shift();
        }
        
        this.saveAutonomousHistory();
        
        console.log('📝 Autonomous message recorded');
    }   
    
    getRecentAutonomousContext(limit = 5) {
        const recent = this.autonomousHistory.slice(-limit);
        
        if (recent.length === 0) {
            return null;
        }
        
        return recent.map(record => {
            const timeAgo = this.getTimeAgo(record.timestamp);
            return `[${timeAgo}] I said: "${record.message}"${record.response ? `\nYour response: "${record.response}"` : ''}`;
        }).join('\n\n');
    }
    
    getTimeAgo(timestamp) {
        const seconds = Math.floor((Date.now() - timestamp) / 1000);
        
        if (seconds < 60) return `${seconds}s ago`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
        return `${Math.floor(seconds / 86400)}d ago`;
    }

    // ==========================================
    // ENGAGEMENT SCORE
    // ==========================================
    
    loadEngagementScore() {
        try {
            const saved = localStorage.getItem('crump_user_engagement');
            return saved ? parseFloat(saved) : 0.5;
        } catch (e) {
            return 0.5;
        }
    }

    saveEngagementScore() {
        try {
            localStorage.setItem('crump_user_engagement', this.userEngagementScore.toString());
        } catch (e) {
            console.warn('⚠️ Failed to save engagement score');
        }
    }

    // ==========================================
    // WORK MODE
    // ==========================================
    
    isWorkHours() {
        const hour = new Date().getHours();
        const workStart = parseInt(localStorage.getItem('crump_work_start') || '9');
        const workEnd = parseInt(localStorage.getItem('crump_work_end') || '17');
        return hour >= workStart && hour < workEnd;
    }

    isInWorkMode() {
        return localStorage.getItem('crump_work_mode') === 'true';
    }

    // ==========================================
    // SETTINGS
    // ==========================================

    loadSettings() {
        try {
            const enabled = localStorage.getItem('crump_autonomous_enabled') === 'true';
            const frequency = localStorage.getItem('crump_autonomous_frequency') || 'medium';
            return { enabled, frequency };
        } catch (e) {
            return { enabled: false, frequency: 'medium' };
        }
    }

    saveSettings() {
        localStorage.setItem('crump_autonomous_enabled', this.enabled.toString());
        localStorage.setItem('crump_autonomous_frequency', this.frequency);
    }

    start() {
        if (this.enabled && !this.timerId) {
            this.scheduleNext();
            console.log('✅ Autonomous messaging started');
        }
    }

    stop() {
        if (this.timerId) {
            clearTimeout(this.timerId);
            this.timerId = null;
            console.log('⏸️ Autonomous messaging stopped');
        }
    }

    toggle(enabled) {
        this.enabled = enabled;
        this.saveSettings();
        
        if (enabled) {
            this.start();
        } else {
            this.stop();
        }
    }

    setFrequency(frequency) {
        this.frequency = frequency;
        this.saveSettings();
        
        if (this.enabled) {
            this.stop();
            this.start();
        }
    }

    getInterval() {
        const intervals = {
            relaxed: 15 * 60 * 1000,
            medium: 10 * 60 * 1000,
            active: 5 * 60 * 1000
        };
        return intervals[this.frequency] || intervals.medium;
    }

    scheduleNext() {
        if (!this.enabled) return;
        
        const interval = this.getInterval();
        const variance = interval * 0.3;
        const delay = interval + (Math.random() * variance * 2 - variance);
        
        this.timerId = setTimeout(() => {
            this.sendAutonomousMessage();
            this.scheduleNext();
        }, delay);
        
        console.log(`⏰ Next autonomous check in ${Math.round(delay / 1000)}s`);
    }

    playNotificationSound() {
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);

            oscillator.frequency.value = 800;
            oscillator.type = 'sine';
            
            gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);

            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.3);
        } catch (e) {
            // Fail silently
        }
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.autonomousMessaging = new AutonomousMessaging();

window.addEventListener('userMessageSent', (event) => {
    if (window.autonomousMessaging && event.detail?.message) {
        window.autonomousMessaging.onUserResponse(event.detail.message);
    }
});

window.AutonomousMessaging = AutonomousMessaging;

console.log('✅ Autonomous Messaging v3.5 ENHANCED loaded - Maximum human naturality!');
