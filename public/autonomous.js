// ==========================================
// CRUMP AI - AUTONOMOUS MESSAGING v3.0
// Actually sends messages (FIXED)
// ==========================================

class AutonomousMessaging {
    constructor() {
        this.enabled = false;
        this.frequency = 'balanced';
        this.intervalId = null;
        this.lastMessageTime = null;
        
        this.prompts = [
            "Just checking in! How's your day going?",
            "Is there anything I can help you with right now?",
            "Need any assistance with your current tasks?",
            "I'm here if you need anything!",
            "Would you like me to help with anything?",
            "How are things progressing?",
            "Let me know if you need any support!",
            "Ready to assist whenever you need me.",
            "Checking in - anything on your mind?",
            "I'm available if you'd like to chat or need help with something."
        ];
        
        this.loadSettings();
        console.log('🤖 Autonomous Messaging v3.0 initialized');
    }
    
    loadSettings() {
        const enabled = localStorage.getItem('crump_autonomous') === 'true';
        const frequency = localStorage.getItem('crump_autonomous_frequency') || 'balanced';
        
        this.enabled = enabled;
        this.frequency = frequency;
        
        if (this.enabled) {
            this.start();
        }
    }
    
    start() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
        }
        
        const intervals = {
            'relaxed': 15 * 60 * 1000,    // 15 minutes
            'balanced': 10 * 60 * 1000,   // 10 minutes
            'active': 5 * 60 * 1000,      // 5 minutes
            'very-active': 3 * 60 * 1000  // 3 minutes
        };
        
        const interval = intervals[this.frequency] || intervals.balanced;
        
        this.enabled = true;
        this.intervalId = setInterval(() => {
            this.sendAutonomousMessage();
        }, interval);
        
        console.log(`🤖 Autonomous messaging started: ${this.frequency} (${interval / 1000 / 60} minutes)`);
    }
    
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        this.enabled = false;
        console.log('🤖 Autonomous messaging stopped');
    }
    
    toggle(enabled) {
        if (enabled) {
            this.start();
        } else {
            this.stop();
        }
        
        localStorage.setItem('crump_autonomous', enabled.toString());
    }
    
    setFrequency(frequency) {
        this.frequency = frequency;
        localStorage.setItem('crump_autonomous_frequency', frequency);
        
        if (this.enabled) {
            this.start(); // Restart with new interval
        }
        
        console.log(`🤖 Frequency updated: ${frequency}`);
    }
    
    async sendAutonomousMessage() {
        try {
            // Don't send if user recently sent a message (within last 2 minutes)
            if (this.lastMessageTime && (Date.now() - this.lastMessageTime) < 2 * 60 * 1000) {
                console.log('🤖 Skipping autonomous message - user recently active');
                return;
            }
            
            // Don't send if user is currently typing
            const userInput = document.getElementById('userInput');
            if (userInput && userInput.value.trim().length > 0) {
                console.log('🤖 Skipping autonomous message - user is typing');
                return;
            }
            
            // Check if there's an active chat
            if (!window.currentChatId) {
                console.log('🤖 No active chat - skipping autonomous message');
                return;
            }
            
            // Get current chat
            const currentChat = window.crumpDebug?.getCurrentChat?.();
            if (!currentChat) {
                console.log('🤖 Cannot get current chat');
                return;
            }
            
            // Pick a random prompt
            const prompt = this.prompts[Math.floor(Math.random() * this.prompts.length)];
            
            console.log('🤖 Sending autonomous message:', prompt);
            
            // Add autonomous message to chat
            const autonomousMessage = {
                role: 'assistant',
                content: prompt,
                timestamp: Date.now(),
                autonomous: true
            };
            
            currentChat.messages.push(autonomousMessage);
            currentChat.updatedAt = Date.now();
            
            // Save chat
            if (typeof window.saveChats === 'function') {
                window.saveChats();
            } else {
                const chats = JSON.parse(localStorage.getItem('crump_chats') || '[]');
                const chatIndex = chats.findIndex(c => c.id === currentChat.id);
                if (chatIndex !== -1) {
                    chats[chatIndex] = currentChat;
                    localStorage.setItem('crump_chats', JSON.stringify(chats));
                }
            }
            
            // Render message
            if (typeof window.renderMessage === 'function') {
                window.renderMessage(autonomousMessage);
            }
            
            // Update last message time
            this.lastMessageTime = Date.now();
            
            // Show notification (optional)
            if (window.showNotification) {
                window.showNotification('💬 Autonomous check-in', 'info');
            }
            
        } catch (error) {
            console.error('❌ Autonomous message error:', error);
        }
    }
    
    // Called when user sends a message (to prevent immediate autonomous messages)
    onUserMessage() {
        this.lastMessageTime = Date.now();
    }
}

// ==========================================
// INITIALIZE
// ==========================================
window.AutonomousMessaging = AutonomousMessaging;
window.autonomousMessaging = new AutonomousMessaging();

// Hook into sendMessage to track user activity
if (window.sendMessage) {
    const originalSendMessage = window.sendMessage;
    window.sendMessage = function(...args) {
        if (window.autonomousMessaging) {
            window.autonomousMessaging.onUserMessage();
        }
        return originalSendMessage.apply(this, args);
    };
}

console.log('✅ Autonomous Messaging v3.0 loaded - Actually works now!');
