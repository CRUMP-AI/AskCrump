// ==========================================
// CRUMP AI - AUTONOMOUS MESSAGING v2.0 FIXED
// Fixed: Crump remembers what he said autonomously
// ==========================================

class AutonomousMessaging {
    constructor() {
        this.enabled = this.loadSettings().enabled;
        this.frequency = this.loadSettings().frequency || 'medium';
        this.timerId = null;
        this.lastMessageTime = Date.now();
        this.autonomousHistory = this.loadAutonomousHistory();
        
        console.log('🤖 Autonomous Messaging v2.0 initialized');
        console.log('   Enabled:', this.enabled);
        console.log('   Frequency:', this.frequency);
        console.log('   Previous autonomous messages:', this.autonomousHistory.length);
    }

    // ==========================================
    // AUTONOMOUS HISTORY TRACKING
    // ==========================================
    
    loadAutonomousHistory() {
        try {
            const saved = localStorage.getItem('crump_autonomous_history');
            if (saved) {
                const history = JSON.parse(saved);
                // Keep only last 50 autonomous messages
                return history.slice(-50);
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
        
        // If updating existing message with response
        const lastMsg = this.autonomousHistory[this.autonomousHistory.length - 1];
        
        if (response && lastMsg && lastMsg.message === message && !lastMsg.response) {
            // Update last message with user's response
            lastMsg.response = response;
            lastMsg.responseTime = Date.now();
        } else if (!response) {
            // Add new autonomous message
            this.autonomousHistory.push(record);
        }
        
        // Keep only last 50
        if (this.autonomousHistory.length > 50) {
            this.autonomousHistory.shift();
        }
        
        this.saveAutonomousHistory();
        
        // CRITICAL: Update universal memory for main chat API
        if (typeof window.universalMemory === 'undefined') {
            window.universalMemory = {};
        }
        window.universalMemory.autonomousHistory = this.autonomousHistory;
        
        console.log('📝 Autonomous message recorded:', message.substring(0, 50));
    }
    
    getRecentAutonomousContext(limit = 5) {
        // Get the last N autonomous messages for context
        const recent = this.autonomousHistory.slice(-limit);
        
        if (recent.length === 0) {
            return null;
        }
        
        return recent.map(record => {
            const timeAgo = this.getTimeAgo(record.timestamp);
            return `[${timeAgo}] I said autonomously: "${record.message}"\nYour response: "${record.response}"`;
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

    // ==========================================
    // CONTROL
    // ==========================================

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

    // ==========================================
    // SCHEDULING
    // ==========================================

    getInterval() {
        const intervals = {
            low: 10 * 60 * 1000,      // 10 minutes
            medium: 5 * 60 * 1000,     // 5 minutes
            high: 2 * 60 * 1000        // 2 minutes
        };
        return intervals[this.frequency] || intervals.medium;
    }

    scheduleNext() {
        if (!this.enabled) return;
        
        const interval = this.getInterval();
        const variance = interval * 0.3; // ±30% randomness
        const delay = interval + (Math.random() * variance * 2 - variance);
        
        this.timerId = setTimeout(() => {
            this.sendAutonomousMessage();
            this.scheduleNext();
        }, delay);
        
        console.log(`⏰ Next autonomous message in ${Math.round(delay / 1000)}s`);
    }

    // ==========================================
    // MESSAGE GENERATION (FIXED WITH MEMORY)
    // ==========================================

    async sendAutonomousMessage() {
        try {
            // Don't interrupt if user is typing or app is processing
            if (window.isProcessing) {
                console.log('⏸️ Skipping autonomous message - app is busy');
                return;
            }

            const userInput = document.getElementById('userInput');
            if (userInput && userInput.value.trim().length > 0) {
                console.log('⏸️ Skipping autonomous message - user is typing');
                return;
            }

            // Check if user has been idle long enough
            const timeSinceLastMessage = Date.now() - this.lastMessageTime;
            const minIdleTime = 60000; // 1 minute minimum idle
            
            if (timeSinceLastMessage < minIdleTime) {
                console.log('⏸️ Skipping autonomous message - user was recently active');
                return;
            }

            console.log('🤖 Generating autonomous message...');

            const currentChat = window.chats?.find(c => c.id === window.currentChatId);
            if (!currentChat) {
                console.warn('⚠️ No current chat found');
                return;
            }

            // Get recent conversation context
            const recentMessages = currentChat.messages.slice(-10);
            const conversationContext = recentMessages.map(m => 
                `${m.role}: ${m.content}`
            ).join('\n');

            // FIXED: Get autonomous message history for context
            const autonomousContext = this.getRecentAutonomousContext(5);

            // Generate autonomous message using API
            const response = await fetch('/api/autonomous.js', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    conversationContext: conversationContext,
                    autonomousContext: autonomousContext, // NEW: Previous autonomous messages
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
                        })
                    }
                })
            });

            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }

            const data = await response.json();
            
            if (!data.message) {
                console.warn('⚠️ No autonomous message generated');
                return;
            }

            // Add autonomous message to chat
            const autonomousMsg = {
                role: 'assistant',
                content: data.message,
                timestamp: Date.now(),
                autonomous: true
            };

            currentChat.messages.push(autonomousMsg);
            currentChat.updatedAt = Date.now();

            // Save to chat history
            if (typeof window.saveChats === 'function') {
                window.saveChats();
            }

            // Render the message
            if (typeof window.renderMessages === 'function') {
                window.renderMessages(currentChat.messages);
            }

            // Update chat list
            if (typeof window.renderChatsList === 'function') {
                window.renderChatsList();
            }

            // Scroll to show the message
            if (window.crumpScrollManager) {
                setTimeout(() => {
                    window.crumpScrollManager.scrollToBottom('smooth');
                }, 200);
            }

            // Play notification sound (optional)
            this.playNotificationSound();

           // FIXED: Record this autonomous message so Crump remembers it
            // Note: We'll record the user's response when they reply
            this.lastAutonomousMessage = {
                message: data.message,
                timestamp: Date.now()
            };

            // CRITICAL: Store in universalMemory for main chat API
            if (typeof window.universalMemory === 'undefined') {
                window.universalMemory = {};
            }
            window.universalMemory.autonomousHistory = this.autonomousHistory;

            // Record this autonomous message (without response yet)
            this.recordAutonomousMessage(data.message);

            console.log('✅ Autonomous message sent:', data.message.substring(0, 50) + '...');


        } catch (error) {
            console.error('❌ Autonomous message error:', error);
            
            // Don't show error to user - fail silently
            // But log for debugging
        }
    }

    // ==========================================
    // HOOK INTO USER RESPONSES
    // ==========================================
    
    onUserResponse(userMessage) {
        // If user is responding to an autonomous message, record the full exchange
        if (this.lastAutonomousMessage && 
            (Date.now() - this.lastAutonomousMessage.timestamp) < 300000) { // 5 minutes
            
            this.recordAutonomousMessage(
                this.lastAutonomousMessage.message,
                userMessage
            );
            
            this.lastAutonomousMessage = null;
        }
        
        // Update last message time
        this.lastMessageTime = Date.now();
    }

    // ==========================================
    // UI FEEDBACK
    // ==========================================

    playNotificationSound() {
        // Gentle notification sound
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
            // Fail silently if audio not supported
        }
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.autonomousMessaging = new AutonomousMessaging();

// ==========================================
// HOOK INTO APP'S SEND MESSAGE
// ==========================================
// This should be called from app.js after user sends a message
window.addEventListener('userMessageSent', (event) => {
    if (window.autonomousMessaging && event.detail?.message) {
        window.autonomousMessaging.onUserResponse(event.detail.message);
    }
});

// ==========================================
// PUBLIC API
// ==========================================
window.AutonomousMessaging = AutonomousMessaging;

console.log('✅ Autonomous Messaging v2.0 loaded - Now with memory!');
