// ==========================================
// CRUMP AI - MEMORY THREADING SYSTEM v1.0
// Automatically connects related conversations
// ==========================================

class MemoryThreadingSystem {
    constructor() {
        this.threads = new Map();
        this.embeddings = new Map();
        this.minSimilarity = 0.7;
        
        this.init();
    }
    
    init() {
        console.log('🧵 Memory Threading System initialized');
        this.loadThreads();
    }
    
    /**
     * Create a new thread or add to existing thread
     */
    async processMessage(message, chatId, messageId) {
        const keywords = this.extractKeywords(message);
        const topics = this.extractTopics(message);
        
        // Find related threads
        const relatedThreads = this.findRelatedThreads(keywords, topics);
        
        let threadId;
        
        if (relatedThreads.length > 0) {
            // Add to existing thread
            threadId = relatedThreads[0].id;
            this.addToThread(threadId, { chatId, messageId, message, keywords, topics });
        } else {
            // Create new thread
            threadId = this.createThread({ chatId, messageId, message, keywords, topics });
        }
        
        return {
            threadId,
            relatedThreads: relatedThreads.slice(1, 4), // Return top 3 related
            keywords,
            topics
        };
    }
    
    /**
     * Extract keywords from message
     */
    extractKeywords(message) {
        const stopWords = new Set([
            'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but',
            'in', 'with', 'to', 'for', 'of', 'as', 'by', 'from', 'that',
            'this', 'it', 'be', 'are', 'was', 'were', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'can', 'i', 'you', 'he',
            'she', 'they', 'we', 'what', 'when', 'where', 'who', 'how'
        ]);
        
        const words = message.toLowerCase()
            .replace(/[^\w\s]/g, '')
            .split(/\s+/)
            .filter(word => word.length > 3 && !stopWords.has(word));
        
        // Count frequency
        const frequency = {};
        words.forEach(word => {
            frequency[word] = (frequency[word] || 0) + 1;
        });
        
        // Get top keywords
        return Object.entries(frequency)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 10)
            .map(([word]) => word);
    }
    
    /**
     * Extract topics from message
     */
    extractTopics(message) {
        const topicPatterns = {
            business: ['business', 'startup', 'company', 'revenue', 'profit', 'customer', 'market', 'sales'],
            coding: ['code', 'function', 'bug', 'debug', 'script', 'api', 'database', 'server'],
            ai: ['ai', 'model', 'training', 'neural', 'machine learning', 'gpt', 'claude'],
            personal: ['family', 'daughters', 'wife', 'home', 'personal'],
            work: ['work', 'job', 'georgia pacific', 'reliability', 'technician'],
            finance: ['money', 'investment', 'stock', 'portfolio', 'crypto', 'price'],
            product: ['feature', 'design', 'user', 'interface', 'ux', 'ui', 'product']
        };
        
        const lower = message.toLowerCase();
        const detectedTopics = [];
        
        for (const [topic, keywords] of Object.entries(topicPatterns)) {
            const matches = keywords.filter(keyword => lower.includes(keyword));
            if (matches.length > 0) {
                detectedTopics.push({
                    topic,
                    confidence: matches.length / keywords.length,
                    matches
                });
            }
        }
        
        return detectedTopics.sort((a, b) => b.confidence - a.confidence);
    }
    
    /**
     * Find threads related to current message
     */
    findRelatedThreads(keywords, topics) {
        const related = [];
        
        for (const [threadId, thread] of this.threads.entries()) {
            const similarity = this.calculateSimilarity(
                { keywords, topics },
                thread
            );
            
            if (similarity > this.minSimilarity) {
                related.push({
                    id: threadId,
                    similarity,
                    thread
                });
            }
        }
        
        return related.sort((a, b) => b.similarity - a.similarity);
    }
    
    /**
     * Calculate similarity between two message contexts
     */
    calculateSimilarity(context1, context2) {
        // Keyword overlap
        const keywords1 = new Set(context1.keywords);
        const keywords2 = new Set(context2.keywords || []);
        const keywordIntersection = new Set([...keywords1].filter(x => keywords2.has(x)));
        const keywordSimilarity = keywordIntersection.size / Math.max(keywords1.size, keywords2.size);
        
        // Topic overlap
        const topics1 = new Set(context1.topics.map(t => t.topic));
        const topics2 = new Set((context2.topics || []).map(t => t.topic));
        const topicIntersection = new Set([...topics1].filter(x => topics2.has(x)));
        const topicSimilarity = topicIntersection.size / Math.max(topics1.size, topics2.size);
        
        // Weighted average
        return (keywordSimilarity * 0.6) + (topicSimilarity * 0.4);
    }
    
    /**
     * Create a new thread
     */
    createThread(data) {
        const threadId = `thread_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        
        this.threads.set(threadId, {
            id: threadId,
            created: Date.now(),
            updated: Date.now(),
            messages: [data],
            keywords: data.keywords,
            topics: data.topics,
            summary: this.generateThreadSummary([data])
        });
        
        this.saveThreads();
        
        return threadId;
    }
    
    /**
     * Add message to existing thread
     */
    addToThread(threadId, data) {
        const thread = this.threads.get(threadId);
        
        if (!thread) {
            console.warn('Thread not found:', threadId);
            return;
        }
        
        thread.messages.push(data);
        thread.updated = Date.now();
        
        // Update thread keywords/topics
        const allKeywords = [...new Set([...thread.keywords, ...data.keywords])];
        thread.keywords = allKeywords.slice(0, 20); // Keep top 20
        
        // Merge topics
        const topicMap = new Map();
        [...thread.topics, ...data.topics].forEach(t => {
            const existing = topicMap.get(t.topic);
            if (!existing || t.confidence > existing.confidence) {
                topicMap.set(t.topic, t);
            }
        });
        thread.topics = Array.from(topicMap.values());
        
        thread.summary = this.generateThreadSummary(thread.messages);
        
        this.saveThreads();
    }
    
    /**
     * Generate a summary of a thread
     */
    generateThreadSummary(messages) {
        if (messages.length === 0) return '';
        
        // Get most common keywords across all messages
        const allKeywords = messages.flatMap(m => m.keywords);
        const frequency = {};
        allKeywords.forEach(k => {
            frequency[k] = (frequency[k] || 0) + 1;
        });
        
        const topKeywords = Object.entries(frequency)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([word]) => word);
        
        return `Conversation about ${topKeywords.join(', ')} (${messages.length} messages)`;
    }
    
    /**
     * Get thread by ID
     */
    getThread(threadId) {
        return this.threads.get(threadId);
    }
    
    /**
     * Get all threads for a chat
     */
    getThreadsForChat(chatId) {
        const threads = [];
        
        for (const [threadId, thread] of this.threads.entries()) {
            const hasMessages = thread.messages.some(m => m.chatId === chatId);
            if (hasMessages) {
                threads.push(thread);
            }
        }
        
        return threads.sort((a, b) => b.updated - a.updated);
    }
    
    /**
     * Search threads by keyword or topic
     */
    searchThreads(query) {
        const lowerQuery = query.toLowerCase();
        const results = [];
        
        for (const [threadId, thread] of this.threads.entries()) {
            // Search in keywords
            const keywordMatch = thread.keywords.some(k => k.includes(lowerQuery));
            
            // Search in topics
            const topicMatch = thread.topics.some(t => t.topic.includes(lowerQuery));
            
            // Search in summary
            const summaryMatch = thread.summary.toLowerCase().includes(lowerQuery);
            
            if (keywordMatch || topicMatch || summaryMatch) {
                results.push({
                    threadId,
                    thread,
                    relevance: (keywordMatch ? 0.5 : 0) + (topicMatch ? 0.3 : 0) + (summaryMatch ? 0.2 : 0)
                });
            }
        }
        
        return results.sort((a, b) => b.relevance - a.relevance);
    }
    
    /**
     * Get context for current conversation
     */
    getRelevantContext(currentMessage, limit = 3) {
        const keywords = this.extractKeywords(currentMessage);
        const topics = this.extractTopics(currentMessage);
        
        const related = this.findRelatedThreads(keywords, topics);
        
        return related.slice(0, limit).map(r => ({
            threadId: r.id,
            summary: r.thread.summary,
            similarity: r.similarity,
            messageCount: r.thread.messages.length,
            lastUpdated: r.thread.updated
        }));
    }
    
    /**
     * Save threads to localStorage
     */
    saveThreads() {
        try {
            const data = {
                threads: Array.from(this.threads.entries()),
                lastUpdated: Date.now()
            };
            localStorage.setItem('crump_memory_threads', JSON.stringify(data));
        } catch (e) {
            console.warn('Failed to save threads:', e);
        }
    }
    
    /**
     * Load threads from localStorage
     */
    loadThreads() {
        try {
            const data = localStorage.getItem('crump_memory_threads');
            if (data) {
                const parsed = JSON.parse(data);
                this.threads = new Map(parsed.threads);
                console.log(`🧵 Loaded ${this.threads.size} memory threads`);
            }
        } catch (e) {
            console.warn('Failed to load threads:', e);
        }
    }
    
    /**
     * Get analytics
     */
    getAnalytics() {
        const topicCounts = {};
        const keywordCounts = {};
        
        for (const thread of this.threads.values()) {
            thread.topics.forEach(t => {
                topicCounts[t.topic] = (topicCounts[t.topic] || 0) + 1;
            });
            
            thread.keywords.forEach(k => {
                keywordCounts[k] = (keywordCounts[k] || 0) + 1;
            });
        }
        
        return {
            totalThreads: this.threads.size,
            topTopics: Object.entries(topicCounts)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 10),
            topKeywords: Object.entries(keywordCounts)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 20)
        };
    }
}

// Export
window.MemoryThreadingSystem = MemoryThreadingSystem;

console.log('🧵 Memory Threading System loaded');
