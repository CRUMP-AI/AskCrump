// ==========================================
// CRUMP AI - AUTONOMOUS CONTEXT TRACKER v1.0
// Tracks user patterns, topics, and preferences
// ==========================================

class AutonomousContextTracker {
    constructor() {
        this.activityData = this.loadActivityData();
        this.topicData = this.loadTopicData();
        this.preferences = this.loadPreferences();
        this.pendingFollowUps = this.loadPendingFollowUps();
        
        console.log('📊 Autonomous Context Tracker v1.0 initialized');
        console.log('   Activity records:', this.activityData.sessions.length);
        console.log('   Tracked topics:', Object.keys(this.topicData.topics).length);
        console.log('   Pending follow-ups:', this.pendingFollowUps.length);
    }
    
    // ==========================================
    // ACTIVITY PATTERN TRACKING
    // ==========================================
    
    loadActivityData() {
        try {
            const saved = localStorage.getItem('crump_activity_data');
            if (saved) {
                return JSON.parse(saved);
            }
        } catch (e) {
            console.warn('⚠️ Failed to load activity data:', e);
        }
        
        return {
            sessions: [],
            activeHours: {},
            averageSessionLength: 0,
            lastActivityTime: Date.now(),
            focusSessions: [],
            totalMessages: 0
        };
    }
    
    saveActivityData() {
        try {
            localStorage.setItem('crump_activity_data', JSON.stringify(this.activityData));
        } catch (e) {
            console.warn('⚠️ Failed to save activity data:', e);
        }
    }
    
    recordActivity(type = 'message') {
        const now = Date.now();
        const hour = new Date().getHours();
        
        // Track active hours
        this.activityData.activeHours[hour] = (this.activityData.activeHours[hour] || 0) + 1;
        
        // Detect if this is a new session (more than 30 min since last activity)
        const timeSinceLastActivity = now - this.activityData.lastActivityTime;
        const isNewSession = timeSinceLastActivity > 30 * 60 * 1000; // 30 minutes
        
        if (isNewSession) {
            // Start new session
            this.activityData.sessions.push({
                startTime: now,
                endTime: now,
                messageCount: 1,
                type: type
            });
            
            // Keep only last 100 sessions
            if (this.activityData.sessions.length > 100) {
                this.activityData.sessions.shift();
            }
        } else {
            // Continue current session
            if (this.activityData.sessions.length > 0) {
                const currentSession = this.activityData.sessions[this.activityData.sessions.length - 1];
                currentSession.endTime = now;
                currentSession.messageCount++;
            }
        }
        
        this.activityData.lastActivityTime = now;
        this.activityData.totalMessages++;
        
        // Update average session length
        this.calculateAverageSessionLength();
        
        this.saveActivityData();
        
        return {
            isNewSession,
            currentSessionLength: this.getCurrentSessionLength(),
            messagesInSession: this.getMessagesInCurrentSession()
        };
    }
    
    calculateAverageSessionLength() {
        if (this.activityData.sessions.length === 0) {
            this.activityData.averageSessionLength = 0;
            return;
        }
        
        const totalLength = this.activityData.sessions.reduce((sum, session) => {
            return sum + (session.endTime - session.startTime);
        }, 0);
        
        this.activityData.averageSessionLength = totalLength / this.activityData.sessions.length;
    }
    
    getCurrentSessionLength() {
        if (this.activityData.sessions.length === 0) return 0;
        
        const currentSession = this.activityData.sessions[this.activityData.sessions.length - 1];
        return currentSession.endTime - currentSession.startTime;
    }
    
    getMessagesInCurrentSession() {
        if (this.activityData.sessions.length === 0) return 0;
        
        const currentSession = this.activityData.sessions[this.activityData.sessions.length - 1];
        return currentSession.messageCount;
    }
    
    // ==========================================
    // FOCUS SESSION DETECTION
    // ==========================================
    
    detectFocusSession() {
        const currentSessionLength = this.getCurrentSessionLength();
        const messagesInSession = this.getMessagesInCurrentSession();
        
        // Focus session: Long session (>30 min) with steady activity
        const isFocusSession = currentSessionLength > 30 * 60 * 1000 && messagesInSession > 5;
        
        if (isFocusSession) {
            const existingFocus = this.activityData.focusSessions.find(
                f => f.startTime === this.activityData.sessions[this.activityData.sessions.length - 1].startTime
            );
            
            if (!existingFocus) {
                this.activityData.focusSessions.push({
                    startTime: this.activityData.sessions[this.activityData.sessions.length - 1].startTime,
                    duration: currentSessionLength,
                    messageCount: messagesInSession
                });
                
                // Keep only last 20 focus sessions
                if (this.activityData.focusSessions.length > 20) {
                    this.activityData.focusSessions.shift();
                }
                
                this.saveActivityData();
            }
        }
        
        return isFocusSession;
    }
    
    isInFocusMode() {
        const currentSessionLength = this.getCurrentSessionLength();
        const messagesInSession = this.getMessagesInCurrentSession();
        const recentMessages = messagesInSession / (currentSessionLength / 1000 / 60); // messages per minute
        
        // Focus mode: Long session with consistent activity
        return currentSessionLength > 20 * 60 * 1000 && recentMessages > 0.5;
    }
    
    // ==========================================
    // ACTIVE HOURS ANALYSIS
    // ==========================================
    
    getMostActiveHours(count = 3) {
        const sortedHours = Object.entries(this.activityData.activeHours)
            .sort((a, b) => b[1] - a[1])
            .slice(0, count)
            .map(([hour, _]) => parseInt(hour));
        
        return sortedHours;
    }
    
    isActiveTime() {
        const currentHour = new Date().getHours();
        const mostActiveHours = this.getMostActiveHours(5);
        
        return mostActiveHours.includes(currentHour);
    }
    
    // ==========================================
    // TOPIC TRACKING
    // ==========================================
    
    loadTopicData() {
        try {
            const saved = localStorage.getItem('crump_topic_data');
            if (saved) {
                return JSON.parse(saved);
            }
        } catch (e) {
            console.warn('⚠️ Failed to load topic data:', e);
        }
        
        return {
            topics: {},
            recentTopics: [],
            topicHistory: []
        };
    }
    
    saveTopicData() {
        try {
            localStorage.setItem('crump_topic_data', JSON.stringify(this.topicData));
        } catch (e) {
            console.warn('⚠️ Failed to save topic data:', e);
        }
    }
    
    extractTopics(message) {
        if (!message || typeof message !== 'string') return [];
        
        const text = message.toLowerCase();
        
        // Simple keyword extraction (can be enhanced with NLP later)
        const commonWords = new Set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'can', 'will', 'just', 'should', 'now', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'me', 'him', 'them', 'us']);
        
        // Extract words (3+ chars, not common words)
        const words = text.match(/\b[a-z]{3,}\b/g) || [];
        const meaningfulWords = words.filter(word => !commonWords.has(word));
        
        // Also detect specific topic categories
        const topicCategories = {
            coding: ['code', 'programming', 'debug', 'function', 'variable', 'bug', 'error', 'javascript', 'python', 'react', 'api', 'database'],
            work: ['project', 'meeting', 'deadline', 'presentation', 'boss', 'colleague', 'work', 'office', 'client'],
            personal: ['family', 'friend', 'relationship', 'hobby', 'vacation', 'weekend', 'birthday'],
            learning: ['learn', 'study', 'course', 'tutorial', 'book', 'research', 'understand'],
            creative: ['design', 'art', 'music', 'write', 'create', 'build', 'make'],
            health: ['exercise', 'workout', 'diet', 'sleep', 'health', 'doctor', 'sick'],
            entertainment: ['movie', 'show', 'game', 'watch', 'play', 'fun', 'entertainment']
        };
        
        const detectedCategories = [];
        for (const [category, keywords] of Object.entries(topicCategories)) {
            if (keywords.some(keyword => text.includes(keyword))) {
                detectedCategories.push(category);
            }
        }
        
        return {
            words: meaningfulWords.slice(0, 5), // Top 5 meaningful words
            categories: detectedCategories
        };
    }
    
    trackTopics(message) {
        const extracted = this.extractTopics(message);
        const timestamp = Date.now();
        
        // Track individual words
        extracted.words.forEach(word => {
            if (!this.topicData.topics[word]) {
                this.topicData.topics[word] = {
                    count: 0,
                    firstMentioned: timestamp,
                    lastMentioned: timestamp,
                    category: 'general'
                };
            }
            
            this.topicData.topics[word].count++;
            this.topicData.topics[word].lastMentioned = timestamp;
        });
        
        // Track categories
        extracted.categories.forEach(category => {
            if (!this.topicData.topics[category]) {
                this.topicData.topics[category] = {
                    count: 0,
                    firstMentioned: timestamp,
                    lastMentioned: timestamp,
                    category: 'category'
                };
            }
            
            this.topicData.topics[category].count++;
            this.topicData.topics[category].lastMentioned = timestamp;
        });
        
        // Add to recent topics
        this.topicData.recentTopics.push({
            words: extracted.words,
            categories: extracted.categories,
            timestamp: timestamp
        });
        
        // Keep only last 50 recent topics
        if (this.topicData.recentTopics.length > 50) {
            this.topicData.recentTopics.shift();
        }
        
        this.saveTopicData();
    }
    
    getTopTopics(count = 10) {
        return Object.entries(this.topicData.topics)
            .sort((a, b) => b[1].count - a[1].count)
            .slice(0, count)
            .map(([topic, data]) => ({
                topic,
                count: data.count,
                lastMentioned: data.lastMentioned,
                category: data.category
            }));
    }
    
    getRecentTopics(limit = 5) {
        return this.topicData.recentTopics.slice(-limit);
    }
    
    hasDiscussedTopic(topic) {
        return this.topicData.topics[topic.toLowerCase()] !== undefined;
    }
    
    // ==========================================
    // USER PREFERENCES
    // ==========================================
    
    loadPreferences() {
        try {
            const saved = localStorage.getItem('crump_user_preferences');
            if (saved) {
                return JSON.parse(saved);
            }
        } catch (e) {
            console.warn('⚠️ Failed to load preferences:', e);
        }
        
        return {
            communicationStyle: 'casual', // casual, formal, mixed
            boundaries: [],
            avoidTopics: [],
            insideJokes: [],
            relationshipMilestones: []
        };
    }
    
    savePreferences() {
        try {
            localStorage.setItem('crump_user_preferences', JSON.stringify(this.preferences));
        } catch (e) {
            console.warn('⚠️ Failed to save preferences:', e);
        }
    }
    
    addBoundary(boundary, timestamp = Date.now()) {
        this.preferences.boundaries.push({
            text: boundary,
            timestamp: timestamp,
            active: true
        });
        
        this.savePreferences();
    }
    
    removeBoundary(index) {
        if (index >= 0 && index < this.preferences.boundaries.length) {
            this.preferences.boundaries.splice(index, 1);
            this.savePreferences();
        }
    }
    
    hasBoundary(text) {
        return this.preferences.boundaries.some(b => 
            b.active && b.text.toLowerCase().includes(text.toLowerCase())
        );
    }
    
    // ==========================================
    // PENDING FOLLOW-UPS
    // ==========================================
    
    loadPendingFollowUps() {
        try {
            const saved = localStorage.getItem('crump_pending_followups');
            if (saved) {
                return JSON.parse(saved);
            }
        } catch (e) {
            console.warn('⚠️ Failed to load follow-ups:', e);
        }
        
        return [];
    }
    
    savePendingFollowUps() {
        try {
            localStorage.setItem('crump_pending_followups', JSON.stringify(this.pendingFollowUps));
        } catch (e) {
            console.warn('⚠️ Failed to save follow-ups:', e);
        }
    }
    
    addFollowUp(topic, message, dueTime = null) {
        this.pendingFollowUps.push({
            topic: topic,
            message: message,
            createdAt: Date.now(),
            dueTime: dueTime,
            completed: false
        });
        
        this.savePendingFollowUps();
    }
    
    markFollowUpComplete(index) {
        if (index >= 0 && index < this.pendingFollowUps.length) {
            this.pendingFollowUps[index].completed = true;
            this.pendingFollowUps[index].completedAt = Date.now();
            this.savePendingFollowUps();
        }
    }
    
    getPendingFollowUps() {
        return this.pendingFollowUps.filter(f => !f.completed);
    }
    
    getDueFollowUps() {
        const now = Date.now();
        return this.pendingFollowUps.filter(f => 
            !f.completed && f.dueTime && f.dueTime <= now
        );
    }
    
    // ==========================================
    // CONTEXT SUMMARY FOR AUTONOMOUS MESSAGING
    // ==========================================
    
    getContextSummary() {
        const mostActiveHours = this.getMostActiveHours(3);
        const topTopics = this.getTopTopics(5);
        const recentTopics = this.getRecentTopics(3);
        const pendingFollowUps = this.getPendingFollowUps();
        const isInFocus = this.isInFocusMode();
        
        return {
            activity: {
                totalMessages: this.activityData.totalMessages,
                averageSessionLength: Math.round(this.activityData.averageSessionLength / 1000 / 60), // minutes
                mostActiveHours: mostActiveHours,
                isActiveTime: this.isActiveTime(),
                isInFocusMode: isInFocus,
                currentSessionLength: Math.round(this.getCurrentSessionLength() / 1000 / 60), // minutes
                messagesInSession: this.getMessagesInCurrentSession()
            },
            topics: {
                top: topTopics,
                recent: recentTopics,
                totalTracked: Object.keys(this.topicData.topics).length
            },
            preferences: {
                communicationStyle: this.preferences.communicationStyle,
                boundaries: this.preferences.boundaries.filter(b => b.active),
                avoidTopics: this.preferences.avoidTopics
            },
            followUps: {
                pending: pendingFollowUps,
                count: pendingFollowUps.length
            }
        };
    }
    
    // ==========================================
    // OPEN CONVERSATION DETECTION
    // ==========================================
    
    detectOpenConversations(chatMessages) {
        if (!Array.isArray(chatMessages) || chatMessages.length === 0) {
            return [];
        }
        
        const openConversations = [];
        
        // Check last few messages for questions or unresolved topics
        const recentMessages = chatMessages.slice(-10);
        
        recentMessages.forEach((msg, index) => {
            if (msg.role === 'user') {
                // User asked a question but got a short response
                if (msg.content.includes('?')) {
                    const nextMsg = recentMessages[index + 1];
                    if (nextMsg && nextMsg.role === 'assistant' && nextMsg.content.length < 100) {
                        openConversations.push({
                            type: 'question',
                            message: msg.content,
                            timestamp: msg.timestamp
                        });
                    }
                }
                
                // User mentioned doing something later
                if (/(later|tomorrow|next week|soon|eventually)/i.test(msg.content)) {
                    openConversations.push({
                        type: 'future_action',
                        message: msg.content,
                        timestamp: msg.timestamp
                    });
                }
            }
        });
        
        return openConversations;
    }
}

// ==========================================
// EXPORT TO GLOBAL
// ==========================================
window.AutonomousContextTracker = AutonomousContextTracker;

console.log('✅ Autonomous Context Tracker v1.0 loaded');
