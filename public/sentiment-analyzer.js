// ==========================================
// CRUMP AI - SENTIMENT ANALYZER v1.0
// Detects user emotional state from messages
// ==========================================

class SentimentAnalyzer {
    constructor() {
        // Emotional state patterns
        this.patterns = {
            stress: {
                keywords: ['stressed', 'overwhelmed', 'pressure', 'anxiety', 'worried', 'panic', 'deadline', 'urgent', 'ugh', 'fml', 'can\'t handle'],
                markers: {
                    shortMessages: true,      // Messages under 10 chars
                    capsLock: true,           // EXCESSIVE CAPS
                    repeatedPunctuation: true, // !!!!, ???
                    negativeIntensifiers: ['so', 'really', 'very', 'extremely']
                }
            },
            
            excitement: {
                keywords: ['awesome', 'amazing', 'excited', 'love', 'great', 'perfect', 'yes', 'yay', 'woohoo', 'omg', 'wow'],
                markers: {
                    multipleExclamations: true, // !!!, !!!
                    positiveEmojis: ['😊', '😄', '🎉', '🚀', '❤️', '💪', '🔥', '⭐'],
                    capsPositive: true          // AMAZING!
                }
            },
            
            frustration: {
                keywords: ['frustrated', 'annoying', 'stupid', 'hate', 'angry', 'irritated', 'whatever', 'nevermind', 'forget it', 'ugh', 'seriously'],
                markers: {
                    repeatedQuestions: true,    // Why??? Why????
                    negativeWords: ['not working', 'broken', 'failed', 'error', 'wrong', 'bad'],
                    shortAngryResponses: ['k', 'fine', 'whatever']
                }
            },
            
            sadness: {
                keywords: ['sad', 'depressed', 'down', 'lonely', 'hurt', 'crying', 'miss', 'lost', 'empty', 'hopeless', 'tired'],
                markers: {
                    lowEnergy: true,            // Short, flat responses
                    negativeReflection: ['i don\'t know', 'i guess', 'maybe', 'whatever'],
                    sadEmojis: ['😢', '😔', '😞', '💔', '😪']
                }
            },
            
            neutral: {
                keywords: ['okay', 'fine', 'sure', 'alright', 'yeah'],
                markers: {
                    normalLength: true,
                    noStrongIndicators: true
                }
            }
        };
        
        console.log('🧠 Sentiment Analyzer v1.0 initialized');
    }
    
    // ==========================================
    // MAIN ANALYSIS METHOD
    // ==========================================
    analyze(message) {
        if (!message || typeof message !== 'string') {
            return this.getDefaultState();
        }
        
        const text = message.toLowerCase().trim();
        const scores = {
            stress: 0,
            excitement: 0,
            frustration: 0,
            sadness: 0,
            neutral: 0
        };
        
        // Analyze keywords
        for (const [emotion, data] of Object.entries(this.patterns)) {
            data.keywords.forEach(keyword => {
                if (text.includes(keyword)) {
                    scores[emotion] += 2;
                }
            });
        }
        
        // Analyze markers
        scores.stress += this.analyzeStressMarkers(message, text);
        scores.excitement += this.analyzeExcitementMarkers(message, text);
        scores.frustration += this.analyzeFrustrationMarkers(message, text);
        scores.sadness += this.analyzeSadnessMarkers(message, text);
        
        // If no strong signals, it's neutral
        const maxScore = Math.max(...Object.values(scores));
        if (maxScore < 2) {
            scores.neutral = 5;
        }
        
        // Determine dominant emotion
        const dominantEmotion = Object.entries(scores)
            .reduce((a, b) => scores[a[0]] > scores[b[0]] ? a : b)[0];
        
        const confidence = this.calculateConfidence(scores, dominantEmotion);
        
        return {
            emotion: dominantEmotion,
            confidence: confidence,
            scores: scores,
            timestamp: Date.now(),
            messageLength: message.length
        };
    }
    
    // ==========================================
    // STRESS MARKERS
    // ==========================================
    analyzeStressMarkers(message, text) {
        let score = 0;
        
        // Very short messages (under 10 chars) might indicate stress
        if (message.length < 10 && message.length > 0) {
            score += 0.5;
        }
        
        // Excessive caps (more than 30% of message)
        const capsCount = (message.match(/[A-Z]/g) || []).length;
        const capsRatio = capsCount / message.length;
        if (capsRatio > 0.3 && message.length > 5) {
            score += 1.5;
        }
        
        // Multiple punctuation
        if (/[!?]{3,}/.test(message)) {
            score += 1;
        }
        
        // Stress intensifiers
        const intensifiers = ['so', 'really', 'very', 'extremely'];
        intensifiers.forEach(word => {
            if (text.includes(word)) {
                score += 0.5;
            }
        });
        
        // Time pressure words
        if (/(asap|urgent|now|hurry|quick)/i.test(text)) {
            score += 1;
        }
        
        return score;
    }
    
    // ==========================================
    // EXCITEMENT MARKERS
    // ==========================================
    analyzeExcitementMarkers(message, text) {
        let score = 0;
        
        // Multiple exclamation marks
        const exclamations = (message.match(/!/g) || []).length;
        if (exclamations >= 2) {
            score += 1.5;
        }
        
        // Positive emojis
        const positiveEmojis = ['😊', '😄', '🎉', '🚀', '❤️', '💪', '🔥', '⭐', '✨', '🎊'];
        positiveEmojis.forEach(emoji => {
            if (message.includes(emoji)) {
                score += 1;
            }
        });
        
        // Caps with positive words
        const positiveWords = ['AWESOME', 'AMAZING', 'GREAT', 'YES', 'PERFECT', 'LOVE'];
        positiveWords.forEach(word => {
            if (message.includes(word)) {
                score += 1;
            }
        });
        
        // Multiple positive words
        const positiveCount = (text.match(/\b(awesome|amazing|great|love|excited|perfect|excellent|wonderful)\b/g) || []).length;
        score += positiveCount * 0.5;
        
        return score;
    }
    
    // ==========================================
    // FRUSTRATION MARKERS
    // ==========================================
    analyzeFrustrationMarkers(message, text) {
        let score = 0;
        
        // Repeated questions
        const questionMarks = (message.match(/\?/g) || []).length;
        if (questionMarks >= 3) {
            score += 1.5;
        }
        
        // Short angry responses
        const shortAngry = ['k', 'fine', 'whatever', 'nvm'];
        if (shortAngry.includes(text)) {
            score += 2;
        }
        
        // Negative intensifiers
        if (/(not working|broken|failed|error|wrong|stupid|hate)/i.test(text)) {
            score += 1.5;
        }
        
        // Frustration expressions
        if (/(ugh|argh|grr|ffs|wtf)/i.test(text)) {
            score += 2;
        }
        
        // "Why" questions (often indicate frustration)
        const whyCount = (text.match(/\bwhy\b/g) || []).length;
        if (whyCount >= 2) {
            score += 1;
        }
        
        return score;
    }
    
    // ==========================================
    // SADNESS MARKERS
    // ==========================================
    analyzeSadnessMarkers(message, text) {
        let score = 0;
        
        // Low energy phrases
        const lowEnergy = ['i don\'t know', 'i guess', 'maybe', 'whatever', 'i don\'t care'];
        lowEnergy.forEach(phrase => {
            if (text.includes(phrase)) {
                score += 1;
            }
        });
        
        // Sad emojis
        const sadEmojis = ['😢', '😔', '😞', '💔', '😪', '😭', '🥺'];
        sadEmojis.forEach(emoji => {
            if (message.includes(emoji)) {
                score += 1.5;
            }
        });
        
        // Negative self-talk
        if (/(i'm terrible|i can't|i'm bad|i'm worthless|i'm stupid)/i.test(text)) {
            score += 2;
        }
        
        // Hopelessness indicators
        if (/(give up|no point|doesn't matter|what's the point)/i.test(text)) {
            score += 1.5;
        }
        
        return score;
    }
    
    // ==========================================
    // CONFIDENCE CALCULATION
    // ==========================================
    calculateConfidence(scores, dominantEmotion) {
        const maxScore = scores[dominantEmotion];
        const totalScore = Object.values(scores).reduce((a, b) => a + b, 0);
        
        if (totalScore === 0) return 0.5; // Neutral default
        
        // Confidence is the ratio of dominant score to total
        const confidence = maxScore / totalScore;
        
        // Normalize to 0-1 range
        return Math.min(Math.max(confidence, 0), 1);
    }
    
    // ==========================================
    // EMOTION HISTORY TRACKING
    // ==========================================
    trackEmotionHistory(analysis) {
        try {
            let history = this.loadEmotionHistory();
            
            // Add new analysis
            history.push({
                emotion: analysis.emotion,
                confidence: analysis.confidence,
                timestamp: analysis.timestamp
            });
            
            // Keep only last 50 emotions
            if (history.length > 50) {
                history = history.slice(-50);
            }
            
            // Save
            localStorage.setItem('crump_emotion_history', JSON.stringify(history));
            
            return history;
        } catch (e) {
            console.warn('⚠️ Failed to track emotion history:', e);
            return [];
        }
    }
    
    loadEmotionHistory() {
        try {
            const saved = localStorage.getItem('crump_emotion_history');
            return saved ? JSON.parse(saved) : [];
        } catch (e) {
            return [];
        }
    }
    
    // ==========================================
    // RECENT EMOTIONAL STATE
    // ==========================================
    getRecentEmotionalState(limit = 5) {
        const history = this.loadEmotionHistory();
        if (history.length === 0) return 'neutral';
        
        // Get last N emotions
        const recent = history.slice(-limit);
        
        // Count occurrences
        const counts = {};
        recent.forEach(item => {
            counts[item.emotion] = (counts[item.emotion] || 0) + 1;
        });
        
        // Return most common recent emotion
        return Object.entries(counts)
            .reduce((a, b) => counts[a[0]] > counts[b[0]] ? a : b)[0];
    }
    
    // ==========================================
    // EMOTION TREND ANALYSIS
    // ==========================================
    getEmotionTrend() {
        const history = this.loadEmotionHistory();
        if (history.length < 5) {
            return {
                trend: 'insufficient_data',
                direction: 'stable',
                recentEmotion: 'neutral'
            };
        }
        
        // Compare first half to second half
        const midpoint = Math.floor(history.length / 2);
        const firstHalf = history.slice(0, midpoint);
        const secondHalf = history.slice(midpoint);
        
        const getPositivity = (emotions) => {
            const positiveCount = emotions.filter(e => 
                e.emotion === 'excitement' || e.emotion === 'neutral'
            ).length;
            return positiveCount / emotions.length;
        };
        
        const firstPositivity = getPositivity(firstHalf);
        const secondPositivity = getPositivity(secondHalf);
        
        let direction = 'stable';
        if (secondPositivity > firstPositivity + 0.2) {
            direction = 'improving';
        } else if (secondPositivity < firstPositivity - 0.2) {
            direction = 'declining';
        }
        
        return {
            trend: direction,
            direction: direction,
            recentEmotion: this.getRecentEmotionalState(),
            firstHalfPositivity: firstPositivity,
            secondHalfPositivity: secondPositivity
        };
    }
    
    // ==========================================
    // DEFAULT STATE
    // ==========================================
    getDefaultState() {
        return {
            emotion: 'neutral',
            confidence: 0.5,
            scores: { stress: 0, excitement: 0, frustration: 0, sadness: 0, neutral: 5 },
            timestamp: Date.now(),
            messageLength: 0
        };
    }
    
    // ==========================================
    // SUMMARY FOR CONTEXT
    // ==========================================
    getSummaryForContext() {
        const recentEmotion = this.getRecentEmotionalState();
        const trend = this.getEmotionTrend();
        const history = this.loadEmotionHistory();
        
        return {
            currentEmotion: recentEmotion,
            trend: trend.direction,
            historyCount: history.length,
            summary: this.generateEmotionalSummary(recentEmotion, trend)
        };
    }
    
    generateEmotionalSummary(emotion, trend) {
        const summaries = {
            stress: 'User appears stressed. Be efficient and supportive.',
            excitement: 'User is excited! Match their energy.',
            frustration: 'User seems frustrated. Be solution-focused.',
            sadness: 'User may be feeling down. Be gentle and supportive.',
            neutral: 'User is in a neutral state. Normal interaction.'
        };
        
        let summary = summaries[emotion] || summaries.neutral;
        
        if (trend.direction === 'declining') {
            summary += ' Note: Mood has been declining recently.';
        } else if (trend.direction === 'improving') {
            summary += ' Note: Mood has been improving recently.';
        }
        
        return summary;
    }
}

// ==========================================
// EXPORT TO GLOBAL
// ==========================================
window.SentimentAnalyzer = SentimentAnalyzer;

console.log('✅ Sentiment Analyzer v1.0 loaded');
