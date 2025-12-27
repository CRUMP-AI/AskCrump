// ==========================================
// CRUMP AI - PROACTIVE INSIGHT GENERATOR v1.0
// Finds valuable insights without being asked
// ==========================================

class ProactiveInsightGenerator {
    constructor() {
        this.insights = [];
        this.patterns = new Map();
        this.lastAnalysis = null;
        this.analysisInterval = 30 * 60 * 1000; // 30 minutes
        
        this.insightTypes = {
            pattern: {
                name: 'Pattern Detection',
                priority: 'medium',
                icon: '📊'
            },
            opportunity: {
                name: 'Opportunity Alert',
                priority: 'high',
                icon: '💡'
            },
            reminder: {
                name: 'Smart Reminder',
                priority: 'medium',
                icon: '🔔'
            },
            connection: {
                name: 'Connected Ideas',
                priority: 'low',
                icon: '🔗'
            },
            trend: {
                name: 'Trend Analysis',
                priority: 'medium',
                icon: '📈'
            },
            warning: {
                name: 'Heads Up',
                priority: 'high',
                icon: '⚠️'
            }
        };
        
        this.init();
    }
    
    init() {
        console.log('💡 Proactive Insight Generator initialized');
        this.loadInsights();
        
        // Start periodic analysis
        this.startPeriodicAnalysis();
    }
    
    /**
     * Analyze conversation history for patterns and insights
     */
    async analyzeConversations() {
        if (!window.memoryThreading) {
            console.warn('Memory Threading System not available');
            return;
        }
        
        const analytics = window.memoryThreading.getAnalytics();
        const threads = Array.from(window.memoryThreading.threads.values());
        
        const newInsights = [];
        
        // Pattern detection
        newInsights.push(...this.detectPatterns(analytics, threads));
        
        // Opportunity detection
        newInsights.push(...this.detectOpportunities(threads));
        
        // Reminder generation
        newInsights.push(...this.generateReminders(threads));
        
        // Connection finding
        newInsights.push(...this.findConnections(threads));
        
        // Trend analysis
        newInsights.push(...this.analyzeTrends(threads));
        
        // Add new insights
        newInsights.forEach(insight => this.addInsight(insight));
        
        this.lastAnalysis = Date.now();
        this.saveInsights();
        
        return newInsights;
    }
    
    /**
     * Detect patterns in user behavior
     */
    detectPatterns(analytics, threads) {
        const insights = [];
        
        // Time-based patterns
        const timePatterns = this.analyzeTimePatterns(threads);
        if (timePatterns.length > 0) {
            timePatterns.forEach(pattern => {
                insights.push({
                    type: 'pattern',
                    title: `${pattern.topic} Pattern Detected`,
                    message: `You often ask about ${pattern.topic} ${pattern.timeDescription}`,
                    data: pattern,
                    actionable: true,
                    action: {
                        type: 'schedule_insight',
                        label: 'Get regular updates',
                        data: pattern
                    }
                });
            });
        }
        
        // Topic frequency
        if (analytics.topTopics && analytics.topTopics.length > 0) {
            const [topTopic, count] = analytics.topTopics[0];
            if (count > 5) {
                insights.push({
                    type: 'pattern',
                    title: `High Interest: ${topTopic}`,
                    message: `You've discussed ${topTopic} ${count} times. Want me to track developments in this area?`,
                    data: { topic: topTopic, frequency: count },
                    actionable: true,
                    action: {
                        type: 'track_topic',
                        label: 'Start tracking',
                        data: { topic: topTopic }
                    }
                });
            }
        }
        
        return insights;
    }
    
    /**
     * Analyze time-based patterns
     */
    analyzeTimePatterns(threads) {
        const hourlyTopics = {};
        const dailyTopics = {};
        
        threads.forEach(thread => {
            thread.messages.forEach(msg => {
                const date = new Date(msg.timestamp || Date.now());
                const hour = date.getHours();
                const day = date.getDay();
                
                thread.topics.forEach(topic => {
                    // Hourly
                    if (!hourlyTopics[topic.topic]) hourlyTopics[topic.topic] = {};
                    hourlyTopics[topic.topic][hour] = (hourlyTopics[topic.topic][hour] || 0) + 1;
                    
                    // Daily
                    if (!dailyTopics[topic.topic]) dailyTopics[topic.topic] = {};
                    dailyTopics[topic.topic][day] = (dailyTopics[topic.topic][day] || 0) + 1;
                });
            });
        });
        
        const patterns = [];
        
        // Find strong time patterns
        for (const [topic, hours] of Object.entries(hourlyTopics)) {
            const entries = Object.entries(hours);
            if (entries.length === 0) continue;
            
            const [peakHour, peakCount] = entries.sort((a, b) => b[1] - a[1])[0];
            const total = entries.reduce((sum, [_, count]) => sum + count, 0);
            
            if (peakCount / total > 0.4) { // 40%+ of activity in one hour
                patterns.push({
                    topic,
                    peakHour: parseInt(peakHour),
                    timeDescription: `around ${this.formatHour(peakHour)}`,
                    confidence: peakCount / total
                });
            }
        }
        
        return patterns;
    }
    
    /**
     * Format hour for display
     */
    formatHour(hour) {
        const h = parseInt(hour);
        if (h === 0) return 'midnight';
        if (h === 12) return 'noon';
        if (h < 12) return `${h}am`;
        return `${h - 12}pm`;
    }
    
    /**
     * Detect opportunities
     */
    detectOpportunities(threads) {
        const insights = [];
        
        // Find incomplete tasks or goals
        const goals = this.extractGoals(threads);
        goals.forEach(goal => {
            if (!goal.completed && this.daysSince(goal.timestamp) > 7) {
                insights.push({
                    type: 'opportunity',
                    title: 'Unfinished Goal',
                    message: `You mentioned wanting to ${goal.description} ${this.timeAgo(goal.timestamp)}. Ready to tackle it?`,
                    data: goal,
                    actionable: true,
                    action: {
                        type: 'resume_goal',
                        label: 'Continue',
                        data: goal
                    }
                });
            }
        });
        
        // Find repeated questions (might need automation)
        const repeated = this.findRepeatedQuestions(threads);
        repeated.forEach(question => {
            insights.push({
                type: 'opportunity',
                title: 'Automation Opportunity',
                message: `You've asked about ${question.topic} ${question.count} times. Want me to track this automatically?`,
                data: question,
                actionable: true,
                action: {
                    type: 'automate',
                    label: 'Set up automation',
                    data: question
                }
            });
        });
        
        return insights;
    }
    
    /**
     * Extract goals from conversations
     */
    extractGoals(threads) {
        const goalKeywords = ['want to', 'need to', 'should', 'plan to', 'goal', 'objective'];
        const goals = [];
        
        threads.forEach(thread => {
            thread.messages.forEach(msg => {
                const lower = msg.message.toLowerCase();
                if (goalKeywords.some(kw => lower.includes(kw))) {
                    goals.push({
                        description: msg.message.substring(0, 100),
                        timestamp: msg.timestamp || Date.now(),
                        threadId: thread.id,
                        completed: false
                    });
                }
            });
        });
        
        return goals;
    }
    
    /**
     * Find repeated questions
     */
    findRepeatedQuestions(threads) {
        const questions = {};
        
        threads.forEach(thread => {
            if (thread.keywords.length > 0) {
                const key = thread.keywords.slice(0, 3).join('_');
                questions[key] = (questions[key] || 0) + 1;
            }
        });
        
        return Object.entries(questions)
            .filter(([_, count]) => count >= 3)
            .map(([key, count]) => ({
                topic: key.replace(/_/g, ' '),
                count
            }));
    }
    
    /**
     * Generate smart reminders
     */
    generateReminders(threads) {
        const insights = [];
        
        // Find time-sensitive mentions
        const timeSensitive = this.findTimeSensitiveMentions(threads);
        timeSensitive.forEach(item => {
            insights.push({
                type: 'reminder',
                title: 'Time-Sensitive Item',
                message: item.message,
                data: item,
                actionable: true,
                action: {
                    type: 'set_reminder',
                    label: 'Set reminder',
                    data: item
                }
            });
        });
        
        return insights;
    }
    
    /**
     * Find time-sensitive mentions
     */
    findTimeSensitiveMentions(threads) {
        const timeKeywords = ['deadline', 'due', 'tomorrow', 'next week', 'monday', 'friday', 'meeting', 'call'];
        const mentions = [];
        
        threads.forEach(thread => {
            thread.messages.forEach(msg => {
                const lower = msg.message.toLowerCase();
                if (timeKeywords.some(kw => lower.includes(kw))) {
                    mentions.push({
                        message: msg.message.substring(0, 100),
                        timestamp: msg.timestamp || Date.now(),
                        threadId: thread.id
                    });
                }
            });
        });
        
        return mentions;
    }
    
    /**
     * Find connections between different topics
     */
    findConnections(threads) {
        const insights = [];
        
        // Find threads with overlapping keywords
        const connections = this.findOverlappingThreads(threads);
        connections.forEach(conn => {
            insights.push({
                type: 'connection',
                title: 'Connected Ideas',
                message: `Your discussions about ${conn.topic1} and ${conn.topic2} might be related`,
                data: conn,
                actionable: false
            });
        });
        
        return insights;
    }
    
    /**
     * Find threads with overlapping topics/keywords
     */
    findOverlappingThreads(threads) {
        const connections = [];
        
        for (let i = 0; i < threads.length; i++) {
            for (let j = i + 1; j < threads.length; j++) {
                const thread1 = threads[i];
                const thread2 = threads[j];
                
                const keywords1 = new Set(thread1.keywords);
                const keywords2 = new Set(thread2.keywords);
                const intersection = new Set([...keywords1].filter(x => keywords2.has(x)));
                
                if (intersection.size >= 2) {
                    connections.push({
                        topic1: thread1.summary,
                        topic2: thread2.summary,
                        sharedKeywords: Array.from(intersection),
                        thread1Id: thread1.id,
                        thread2Id: thread2.id
                    });
                }
            }
        }
        
        return connections.slice(0, 5); // Top 5 connections
    }
    
    /**
     * Analyze trends over time
     */
    analyzeTrends(threads) {
        const insights = [];
        
        // Topic growth/decline
        const trends = this.calculateTopicTrends(threads);
        trends.forEach(trend => {
            if (trend.growth > 0.5) {
                insights.push({
                    type: 'trend',
                    title: `Growing Interest: ${trend.topic}`,
                    message: `Your interest in ${trend.topic} has increased ${Math.round(trend.growth * 100)}%`,
                    data: trend,
                    actionable: false
                });
            }
        });
        
        return insights;
    }
    
    /**
     * Calculate topic trends
     */
    calculateTopicTrends(threads) {
        const now = Date.now();
        const thirtyDaysAgo = now - (30 * 24 * 60 * 60 * 1000);
        
        const recent = threads.filter(t => t.updated > thirtyDaysAgo);
        const older = threads.filter(t => t.updated <= thirtyDaysAgo);
        
        const recentTopics = {};
        const olderTopics = {};
        
        recent.forEach(t => {
            t.topics.forEach(topic => {
                recentTopics[topic.topic] = (recentTopics[topic.topic] || 0) + 1;
            });
        });
        
        older.forEach(t => {
            t.topics.forEach(topic => {
                olderTopics[topic.topic] = (olderTopics[topic.topic] || 0) + 1;
            });
        });
        
        const trends = [];
        
        for (const [topic, recentCount] of Object.entries(recentTopics)) {
            const olderCount = olderTopics[topic] || 0;
            if (olderCount > 0) {
                const growth = (recentCount - olderCount) / olderCount;
                trends.push({ topic, growth, recentCount, olderCount });
            }
        }
        
        return trends.sort((a, b) => b.growth - a.growth);
    }
    
    /**
     * Add new insight
     */
    addInsight(insight) {
        // Check for duplicates
        const isDuplicate = this.insights.some(i => 
            i.type === insight.type && 
            i.title === insight.title
        );
        
        if (isDuplicate) return;
        
        this.insights.push({
            ...insight,
            id: `insight_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            created: Date.now(),
            viewed: false,
            dismissed: false
        });
    }
    
    /**
     * Get pending insights
     */
    getPendingInsights(limit = 10) {
        return this.insights
            .filter(i => !i.viewed && !i.dismissed)
            .sort((a, b) => {
                // Sort by priority
                const priorities = { high: 3, medium: 2, low: 1 };
                const aPriority = priorities[this.insightTypes[a.type]?.priority] || 1;
                const bPriority = priorities[this.insightTypes[b.type]?.priority] || 1;
                return bPriority - aPriority;
            })
            .slice(0, limit);
    }
    
    /**
     * Mark insight as viewed
     */
    markViewed(insightId) {
        const insight = this.insights.find(i => i.id === insightId);
        if (insight) {
            insight.viewed = true;
            this.saveInsights();
        }
    }
    
    /**
     * Dismiss insight
     */
    dismissInsight(insightId) {
        const insight = this.insights.find(i => i.id === insightId);
        if (insight) {
            insight.dismissed = true;
            this.saveInsights();
        }
    }
    
    /**
     * Start periodic analysis
     */
    startPeriodicAnalysis() {
        // Run analysis every 30 minutes
        setInterval(() => {
            this.analyzeConversations();
        }, this.analysisInterval);
        
        // Run initial analysis after 1 minute
        setTimeout(() => {
            this.analyzeConversations();
        }, 60000);
    }
    
    /**
     * Helper: Days since timestamp
     */
    daysSince(timestamp) {
        return Math.floor((Date.now() - timestamp) / (24 * 60 * 60 * 1000));
    }
    
    /**
     * Helper: Time ago string
     */
    timeAgo(timestamp) {
        const days = this.daysSince(timestamp);
        if (days === 0) return 'today';
        if (days === 1) return 'yesterday';
        if (days < 7) return `${days} days ago`;
        if (days < 30) return `${Math.floor(days / 7)} weeks ago`;
        return `${Math.floor(days / 30)} months ago`;
    }
    
    /**
     * Save insights
     */
    saveInsights() {
        try {
            const data = {
                insights: this.insights.slice(-100), // Keep last 100
                lastAnalysis: this.lastAnalysis
            };
            localStorage.setItem('crump_proactive_insights', JSON.stringify(data));
        } catch (e) {
            console.warn('Failed to save insights:', e);
        }
    }
    
    /**
     * Load insights
     */
    loadInsights() {
        try {
            const data = localStorage.getItem('crump_proactive_insights');
            if (data) {
                const parsed = JSON.parse(data);
                this.insights = parsed.insights || [];
                this.lastAnalysis = parsed.lastAnalysis;
                console.log(`💡 Loaded ${this.insights.length} insights`);
            }
        } catch (e) {
            console.warn('Failed to load insights:', e);
        }
    }
}

// Export
window.ProactiveInsightGenerator = ProactiveInsightGenerator;

console.log('💡 Proactive Insight Generator loaded');
