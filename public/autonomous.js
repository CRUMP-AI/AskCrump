// ==========================================
// CRUMP AI - AUTONOMOUS MESSAGING v3.0 ULTIMATE
// Frontend: Advanced context gathering & prediction
// ==========================================

class AutonomousMessaging {
constructor() {
this.enabled = this.loadSettings().enabled;
this.frequency = this.loadSettings().frequency || ‘medium’;
this.timerId = null;
this.lastMessageTime = Date.now();
this.autonomousHistory = this.loadAutonomousHistory();
this.activityTracker = new ActivityTracker(); // NEW: Track user activity

```
    console.log('🚀 Autonomous Messaging v3.0 ULTIMATE initialized');
    console.log('   Enabled:', this.enabled);
    console.log('   Frequency:', this.frequency);
    console.log('   Advanced features: ✅ Pattern analysis ✅ Need prediction ✅ Emotional AI');
}

// ==========================================
// AUTONOMOUS HISTORY TRACKING
// ==========================================

loadAutonomousHistory() {
    try {
        const saved = localStorage.getItem('crump_autonomous_history');
        if (saved) {
            const history = JSON.parse(saved);
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

recordAutonomousMessage(message, response) {
    const record = {
        timestamp: Date.now(),
        message: message,
        response: response,
        chatId: window.currentChatId
    };
    
    this.autonomousHistory.push(record);
    
    if (this.autonomousHistory.length > 50) {
        this.autonomousHistory.shift();
    }
    
    this.saveAutonomousHistory();
    console.log('📝 Autonomous message recorded:', message);
}

getRecentAutonomousContext(limit = 5) {
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
        this.activityTracker.start();
        console.log('✅ Autonomous messaging started (v3.0 ULTIMATE)');
    }
}

stop() {
    if (this.timerId) {
        clearTimeout(this.timerId);
        this.timerId = null;
        this.activityTracker.stop();
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
    const variance = interval * 0.3;
    const delay = interval + (Math.random() * variance * 2 - variance);
    
    this.timerId = setTimeout(() => {
        this.sendAutonomousMessage();
        this.scheduleNext();
    }, delay);
    
    console.log(`⏰ Next autonomous check-in in ${Math.round(delay / 1000)}s`);
}

// ==========================================
// MESSAGE GENERATION - v3.0 ULTIMATE
// ==========================================

async sendAutonomousMessage() {
    try {
        // Don't interrupt if user is typing or app is processing
        if (window.isProcessing) {
            console.log('⏸️ Skipping - app is busy');
            return;
        }

        const userInput = document.getElementById('userInput');
        if (userInput && userInput.value.trim().length > 0) {
            console.log('⏸️ Skipping - user is typing');
            return;
        }

        // Check if user has been idle long enough
        const timeSinceLastMessage = Date.now() - this.lastMessageTime;
        const minIdleTime = 60000; // 1 minute minimum idle
        
        if (timeSinceLastMessage < minIdleTime) {
            console.log('⏸️ Skipping - user was recently active');
            return;
        }

        console.log('🧠 Generating advanced autonomous message...');

        const currentChat = window.chats?.find(c => c.id === window.currentChatId);
        if (!currentChat) {
            console.warn('⚠️ No current chat found');
            return;
        }

        // Get recent conversation context
        const recentMessages = currentChat.messages.slice(-15);
        const conversationContext = recentMessages.map(m => 
            `${m.role}: ${m.content}`
        ).join('\n');

        // Get autonomous message history
        const autonomousContext = this.getRecentAutonomousContext(5);

        // NEW: Get user profile
        const userProfile = this.getUserProfile();

        // NEW: Get recent activity data
        const recentActivity = this.activityTracker.getActivitySummary();

        // Generate autonomous message using v3.0 API
        const response = await fetch('/api/autonomous.js', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                conversationContext: conversationContext,
                autonomousContext: autonomousContext,
                chatHistory: recentMessages, // Full message objects for analysis
                userProfile: userProfile,
                recentActivity: recentActivity,
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

        // Log metadata if available
        if (data.metadata) {
            console.log('📊 Message metadata:', data.metadata);
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

        // Play notification sound
        this.playNotificationSound();

        // Record this message
        this.lastAutonomousMessage = {
            message: data.message,
            timestamp: Date.now()
        };

        console.log('✅ Advanced autonomous message sent');

    } catch (error) {
        console.error('❌ Autonomous message error:', error);
    }
}

// ==========================================
// NEW: USER PROFILE GATHERING
// ==========================================

getUserProfile() {
    try {
        const profile = JSON.parse(localStorage.getItem('crump_user_profile') || '{}');
        return {
            name: profile.name || 'User',
            preferences: profile.preferences || {},
            workMode: profile.workMode || 'companion'
        };
    } catch (e) {
        return { name: 'User', preferences: {}, workMode: 'companion' };
    }
}

// ==========================================
// HOOK INTO USER RESPONSES
// ==========================================

onUserResponse(userMessage) {
    if (this.lastAutonomousMessage && 
        (Date.now() - this.lastAutonomousMessage.timestamp) < 300000) {
        
        this.recordAutonomousMessage(
            this.lastAutonomousMessage.message,
            userMessage
        );
        
        this.lastAutonomousMessage = null;
    }
    
    this.lastMessageTime = Date.now();
    this.activityTracker.recordActivity('message');
}

// ==========================================
// UI FEEDBACK
// ==========================================

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
        // Fail silently if audio not supported
    }
}
```

}

// ==========================================
// NEW: ACTIVITY TRACKER CLASS
// ==========================================

class ActivityTracker {
constructor() {
this.activities = [];
this.isTracking = false;
this.maxActivities = 100;
}

```
start() {
    if (this.isTracking) return;
    this.isTracking = true;
    
    // Track various user activities
    document.addEventListener('keydown', this.handleActivity.bind(this, 'typing'));
    document.addEventListener('click', this.handleActivity.bind(this, 'click'));
    document.addEventListener('scroll', this.handleActivity.bind(this, 'scroll'));
    
    console.log('📊 Activity tracking started');
}

stop() {
    this.isTracking = false;
    document.removeEventListener('keydown', this.handleActivity);
    document.removeEventListener('click', this.handleActivity);
    document.removeEventListener('scroll', this.handleActivity);
}

handleActivity(type, event) {
    if (!this.isTracking) return;
    
    // Throttle to avoid too many events
    const now = Date.now();
    const lastActivity = this.activities[this.activities.length - 1];
    
    if (lastActivity && now - lastActivity.timestamp < 1000 && lastActivity.type === type) {
        return; // Skip if same type within 1 second
    }

    this.recordActivity(type);
}

recordActivity(type) {
    this.activities.push({
        type: type,
        timestamp: Date.now()
    });

    // Keep only recent activities
    if (this.activities.length > this.maxActivities) {
        this.activities.shift();
    }
}

getActivitySummary() {
    const now = Date.now();
    const last5Min = this.activities.filter(a => now - a.timestamp < 300000);
    const last15Min = this.activities.filter(a => now - a.timestamp < 900000);

    return {
        recentActivityCount: last5Min.length,
        last5MinuteActivity: last5Min.length,
        last15MinuteActivity: last15Min.length,
        isActive: last5Min.length > 0,
        lastActivityTime: this.activities.length > 0 ? 
            this.activities[this.activities.length - 1].timestamp : null
    };
}
```

}

// ==========================================
// INITIALIZE
// ==========================================
window.autonomousMessaging = new AutonomousMessaging();

// ==========================================
// HOOK INTO APP’S SEND MESSAGE
// ==========================================
window.addEventListener(‘userMessageSent’, (event) => {
if (window.autonomousMessaging && event.detail?.message) {
window.autonomousMessaging.onUserResponse(event.detail.message);
}
});

// ==========================================
// PUBLIC API
// ==========================================
window.AutonomousMessaging = AutonomousMessaging;

console.log(‘✅ Autonomous Messaging v3.0 ULTIMATE loaded’);
console.log(’   Features: 🧠 Pattern Analysis | 🎯 Need Prediction | 💭 Emotional AI | 📊 Activity Tracking’);
