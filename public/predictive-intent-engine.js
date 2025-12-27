// ==========================================
// CRUMP AI - PREDICTIVE INTENT ENGINE v1.0
// Makes conversations feel telepathic
// ==========================================

class PredictiveIntentEngine {
    constructor() {
        this.typingPatterns = [];
        this.intentCache = new Map();
        this.predictionThreshold = 0.75;
        this.isAnalyzing = false;
        
        // Common intent patterns
        this.intentPatterns = {
            question: {
                triggers: ['what', 'how', 'why', 'when', 'where', 'who', 'can you', 'could you', 'would you'],
                confidence: 0.8,
                preload: ['search', 'knowledge']
            },
            task: {
                triggers: ['create', 'make', 'build', 'generate', 'write', 'draft', 'design'],
                confidence: 0.9,
                preload: ['generation', 'creative']
            },
            search: {
                triggers: ['search', 'find', 'look up', 'latest', 'current', 'news about'],
                confidence: 0.95,
                preload: ['web_search', 'current_events']
            },
            code: {
                triggers: ['code', 'function', 'script', 'debug', 'fix', 'error', 'bug'],
                confidence: 0.85,
                preload: ['coding', 'technical']
            },
            analysis: {
                triggers: ['analyze', 'review', 'compare', 'evaluate', 'assess'],
                confidence: 0.8,
                preload: ['analytical', 'detailed']
            },
            email: {
                triggers: ['email', 'message', 'reply', 'respond to', 'draft'],
                confidence: 0.9,
                preload: ['communication', 'professional']
            }
        };
        
        this.init();
    }
    
    init() {
        console.log('🧠 Predictive Intent Engine initialized');
        this.loadPatterns();
    }
    
    /**
     * Analyze user input in real-time as they type
     */
    analyzeIntent(input) {
        if (!input || input.length < 3) return null;
        
        const lowerInput = input.toLowerCase();
        const words = lowerInput.split(' ');
        
        // Detect intent based on patterns
        let highestConfidence = 0;
        let detectedIntent = null;
        
        for (const [intentType, pattern] of Object.entries(this.intentPatterns)) {
            for (const trigger of pattern.triggers) {
                if (lowerInput.includes(trigger)) {
                    if (pattern.confidence > highestConfidence) {
                        highestConfidence = pattern.confidence;
                        detectedIntent = {
                            type: intentType,
                            confidence: pattern.confidence,
                            preload: pattern.preload,
                            trigger: trigger
                        };
                    }
                }
            }
        }
        
        // Track typing pattern
        this.trackTypingPattern(input, detectedIntent);
        
        return detectedIntent;
    }
    
    /**
     * Track typing patterns to improve predictions
     */
    trackTypingPattern(input, intent) {
        const pattern = {
            timestamp: Date.now(),
            length: input.length,
            wordCount: input.split(' ').length,
            intent: intent?.type || 'unknown',
            confidence: intent?.confidence || 0
        };
        
        this.typingPatterns.push(pattern);
        
        // Keep only last 100 patterns
        if (this.typingPatterns.length > 100) {
            this.typingPatterns.shift();
        }
        
        this.savePatterns();
    }
    
    /**
     * Predict what the user wants before they finish typing
     */
    predictNextAction(currentInput) {
        const intent = this.analyzeIntent(currentInput);
        
        if (!intent) return null;
        
        // Check if we've seen this pattern before
        const similar = this.findSimilarPatterns(currentInput);
        
        return {
            intent: intent.type,
            confidence: intent.confidence,
            suggestions: this.generateSuggestions(intent, similar),
            preload: intent.preload
        };
    }
    
    /**
     * Find similar patterns from history
     */
    findSimilarPatterns(input) {
        const lowerInput = input.toLowerCase();
        const words = new Set(lowerInput.split(' '));
        
        return this.typingPatterns
            .filter(p => {
                const patternWords = new Set(p.input?.split(' ') || []);
                const intersection = new Set([...words].filter(x => patternWords.has(x)));
                return intersection.size > 0;
            })
            .slice(-5); // Last 5 similar patterns
    }
    
    /**
     * Generate helpful suggestions based on intent
     */
    generateSuggestions(intent, similar) {
        const suggestions = [];
        
        switch (intent.type) {
            case 'search':
                suggestions.push({
                    text: 'Search the web for current information',
                    action: 'web_search',
                    icon: '🔍'
                });
                break;
                
            case 'task':
                suggestions.push({
                    text: 'I can help create that',
                    action: 'assist',
                    icon: '✨'
                });
                break;
                
            case 'code':
                suggestions.push({
                    text: 'Need help debugging?',
                    action: 'debug',
                    icon: '🐛'
                });
                break;
                
            case 'email':
                suggestions.push({
                    text: 'Draft professional message',
                    action: 'compose',
                    icon: '✉️'
                });
                break;
        }
        
        return suggestions;
    }
    
    /**
     * Preload context based on predicted intent
     */
    preloadContext(intent) {
        if (!intent || !intent.preload) return;
        
        // Signal to the main app to prepare context
        window.dispatchEvent(new CustomEvent('crump:preload', {
            detail: {
                type: intent.type,
                context: intent.preload
            }
        }));
    }
    
    /**
     * Save patterns to localStorage
     */
    savePatterns() {
        try {
            const data = {
                patterns: this.typingPatterns.slice(-50), // Keep last 50
                lastUpdated: Date.now()
            };
            localStorage.setItem('crump_intent_patterns', JSON.stringify(data));
        } catch (e) {
            console.warn('Failed to save intent patterns:', e);
        }
    }
    
    /**
     * Load patterns from localStorage
     */
    loadPatterns() {
        try {
            const data = localStorage.getItem('crump_intent_patterns');
            if (data) {
                const parsed = JSON.parse(data);
                this.typingPatterns = parsed.patterns || [];
                console.log(`📊 Loaded ${this.typingPatterns.length} intent patterns`);
            }
        } catch (e) {
            console.warn('Failed to load intent patterns:', e);
        }
    }
    
    /**
     * Get typing analytics
     */
    getAnalytics() {
        const intentCounts = {};
        
        this.typingPatterns.forEach(p => {
            intentCounts[p.intent] = (intentCounts[p.intent] || 0) + 1;
        });
        
        return {
            totalPatterns: this.typingPatterns.length,
            intentBreakdown: intentCounts,
            averageConfidence: this.typingPatterns.reduce((sum, p) => sum + p.confidence, 0) / this.typingPatterns.length || 0
        };
    }
}

// Export
window.PredictiveIntentEngine = PredictiveIntentEngine;

console.log('🧠 Predictive Intent Engine loaded');
