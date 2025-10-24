// ==========================================
// CRUMP AI - DETECTION ENGINES v3.1.0
// Smart API routing and image generation
// ==========================================

// ==========================================
// MESSAGE DEDUPLICATION ENGINE
// ==========================================
class MessageDeduplicator {
    constructor() {
        this.recentMessages = [];
        this.maxHistory = 10;
        this.timeWindow = 5000; // 5 seconds
    }
    
    isDuplicate(message) {
        const now = Date.now();
        const normalized = message.trim().toLowerCase();
        
        // Clean old messages
        this.recentMessages = this.recentMessages.filter(
            msg => now - msg.timestamp < this.timeWindow
        );
        
        // Check for duplicate
        const isDupe = this.recentMessages.some(
            msg => msg.content === normalized
        );
        
        if (!isDupe) {
            this.recentMessages.push({
                content: normalized,
                timestamp: now
            });
            
            if (this.recentMessages.length > this.maxHistory) {
                this.recentMessages.shift();
            }
        }
        
        return isDupe;
    }
}

// ==========================================
// IMAGE GENERATION DETECTION
// ==========================================
class ImageGenerationDetector {
    constructor() {
        this.triggers = [
            // Direct commands
            /^(generate|create|make|draw|paint|design|build|show me)\s+(an?|some|the)?\s*(image|picture|photo|pic|drawing|illustration|artwork|visual|graphic)/i,
            
            // Image of/for patterns
            /^(generate|create|make|draw|design|show me)\s+.*\s+(image|picture|photo|illustration)\s+of/i,
            
            // Specific requests
            /^(can you|could you|please)\s+(generate|create|make|draw)\s+.*\s+(image|picture|photo)/i,
            
            // Art styles
            /^(generate|create|make|draw)\s+.*\s+(in the style of|like|similar to|as if|photorealistic|realistic|cartoon|anime|pixel art|oil painting|watercolor)/i,
            
            // Visualize
            /^(visualize|show|display|render)/i,
            
            // I want/need
            /^(i want|i need|i'd like)\s+(an?|some)?\s*(image|picture|photo|illustration)/i
        ];
        
        this.exclusions = [
            /upload/i,
            /attach/i,
            /send me/i,
            /show me (how|what|where|when|why)/i,
            /analyze/i,
            /describe/i,
            /what (is|are|does)/i
        ];
    }
    
    shouldGenerateImage(message) {
        const text = message.trim();
        
        // Check exclusions first
        if (this.exclusions.some(pattern => pattern.test(text))) {
            return false;
        }
        
        // Check triggers
        return this.triggers.some(pattern => pattern.test(text));
    }
    
    extractPrompt(message) {
        // Remove trigger words to get clean prompt
        let prompt = message.trim();
        
        // Remove common prefixes
        prompt = prompt.replace(/^(generate|create|make|draw|paint|design|show me|visualize|i want|i need|i'd like)\s+(an?|some|the)?\s*(image|picture|photo|pic|drawing|illustration|artwork|visual|graphic)\s+(of|for|with|showing)?\s*/i, '');
        
        return prompt.trim();
    }
}

// ==========================================
// SEARCH DETECTION ENGINE
// ==========================================
class SearchDetectionEngine {
    constructor() {
        this.triggers = [
            /^(search|google|look up|find|research|investigate)/i,
            /what (is|are) the (latest|current|recent)/i,
            /what happened/i,
            /who (is|are|was|were)/i,
            /when (is|was|did)/i,
            /tell me about (recent|current|latest)/i
        ];
    }
    
    shouldSearch(message) {
        return this.triggers.some(pattern => pattern.test(message.trim()));
    }
}

// ==========================================
// API DETECTION ENGINE (NEW - COMPREHENSIVE)
// ==========================================
class APIDetectionEngine {
    constructor() {
        this.apiPatterns = {
            // Weather API
            weather: {
                keywords: ['weather', 'temperature', 'forecast', 'rain', 'snow', 'sunny', 'cloudy', 'hot', 'cold', 'humidity', 'wind'],
                patterns: [
                    /what'?s? the weather/i,
                    /weather (in|for|at)/i,
                    /how (hot|cold|warm)/i,
                    /will it rain/i,
                    /temperature (in|at)/i,
                    /forecast for/i
                ],
                examples: ['What\'s the weather in Atlanta?', 'Will it rain tomorrow?', 'Temperature in NYC']
            },
            
            // Sports API
            sports: {
                keywords: ['game', 'score', 'match', 'nfl', 'nba', 'mlb', 'nhl', 'soccer', 'football', 'basketball', 'baseball', 'hockey', 'team', 'player', 'win', 'lose', 'playoff'],
                patterns: [
                    /(who won|score of|result of).*(game|match)/i,
                    /(nfl|nba|mlb|nhl|football|basketball|baseball|hockey)\s+(score|game|match|schedule)/i,
                    /when (is|does).*(play|playing)/i,
                    /(team|player)\s+stats/i,
                    /(cowboys|lakers|yankees|patriots|chiefs|warriors)/i // Popular teams
                ],
                examples: ['Who won the Cowboys game?', 'NBA scores today', 'When do the Lakers play?']
            },
            
            // Stocks API
            stocks: {
                keywords: ['stock', 'share', 'price', 'market', 'nasdaq', 'dow', 'trading', 'ticker', 'tsla', 'aapl', 'googl', 'msft', 'amzn'],
                patterns: [
                    /(stock|share) price/i,
                    /(what'?s?|what is) (tesla|apple|google|microsoft|amazon|meta|netflix|nvidia)/i,
                    /\b(tsla|aapl|googl|msft|amzn|meta|nflx|nvda)\b/i,
                    /market (status|close|open)/i,
                    /stock market/i
                ],
                examples: ['Tesla stock price', 'What\'s AAPL trading at?', 'Market status']
            },
            
            // News API
            news: {
                keywords: ['news', 'headline', 'breaking', 'latest', 'article', 'story', 'report'],
                patterns: [
                    /latest news/i,
                    /breaking news/i,
                    /news about/i,
                    /what'?s? happening (in|with)/i,
                    /headlines (about|for|on)/i
                ],
                examples: ['Latest news about AI', 'Breaking news today', 'Headlines about politics']
            },
            
            // Movies/TV API
            movies: {
                keywords: ['movie', 'film', 'tv show', 'series', 'actor', 'director', 'imdb', 'rating', 'review', 'cinema', 'netflix', 'streaming'],
                patterns: [
                    /(movie|film|show)\s+(about|starring|with|by)/i,
                    /who (directed|starred in|played)/i,
                    /(rating|review) for/i,
                    /best (movies|films|shows)/i,
                    /when (was|did).*(release|come out)/i
                ],
                examples: ['Movies starring Tom Cruise', 'Best sci-fi films', 'When was Inception released?']
            },
            
            // YouTube API
            youtube: {
                keywords: ['youtube', 'video', 'watch', 'tutorial', 'vlog', 'channel', 'subscribe'],
                patterns: [
                    /(search|find).*(youtube|video)/i,
                    /youtube (video|channel)/i,
                    /(tutorial|how to).*(video|youtube)/i,
                    /watch (video|tutorial)/i
                ],
                examples: ['Search YouTube for Python tutorials', 'Find cooking videos', 'Best tech channels']
            },
            
            // Spotify API
            spotify: {
                keywords: ['song', 'music', 'artist', 'album', 'playlist', 'spotify', 'track', 'listen', 'play'],
                patterns: [
                    /(find|search|play|show me)\s+(song|music|artist|album|track)/i,
                    /spotify (song|playlist|artist)/i,
                    /songs? (by|from|like)/i,
                    /music (by|like|similar to)/i,
                    /(who sang|who sings)/i
                ],
                examples: ['Find songs by Drake', 'Music like Bohemian Rhapsody', 'Who sang Hotel California?']
            },
            
            // Google Maps API
            googleMaps: {
                keywords: ['directions', 'navigate', 'route', 'nearby', 'location', 'address', 'map', 'restaurant', 'store', 'coffee', 'gas station', 'parking'],
                patterns: [
                    /(directions|navigate|route|how to get) (to|from)/i,
                    /(nearby|near me|closest|nearest)/i,
                    /(find|show|locate)\s+.*(restaurant|store|coffee|gas|hotel|hospital|bank)/i,
                    /where (is|are|can i find)/i,
                    /address (of|for)/i
                ],
                examples: ['Directions to nearest Starbucks', 'Find Italian restaurants nearby', 'Where is the closest gas station?']
            },
            
            // Recipes API
            recipes: {
                keywords: ['recipe', 'cook', 'cooking', 'bake', 'baking', 'ingredient', 'meal', 'dish', 'cuisine', 'food'],
                patterns: [
                    /(recipe|recipes) (for|with)/i,
                    /how to (cook|make|bake|prepare)/i,
                    /(find|show|give me)\s+(recipe|recipes)/i,
                    /ingredients (for|to make)/i,
                    /(italian|mexican|chinese|japanese|indian)\s+(food|dish|recipe)/i
                ],
                examples: ['Recipe for chocolate chip cookies', 'How to make pasta carbonara', 'Find chicken recipes']
            },
            
            // Translation API
            translation: {
                keywords: ['translate', 'translation', 'spanish', 'french', 'german', 'chinese', 'japanese', 'italian', 'language'],
                patterns: [
                    /translate.*(to|into|in)/i,
                    /how do you say.*(in|spanish|french|german)/i,
                    /what (is|does).*(mean in|spanish|french|german)/i,
                    /(spanish|french|german|chinese|japanese|italian)\s+(for|word for|translation)/i
                ],
                examples: ['Translate hello to Spanish', 'How do you say thank you in French?', 'What does bonjour mean?']
            },
            
            // GitHub API
            github: {
                keywords: ['github', 'repository', 'repo', 'code', 'open source', 'library', 'framework', 'package'],
                patterns: [
                    /(search|find).*(github|repository|repo)/i,
                    /github (repository|repo|project)/i,
                    /(open source|library|framework|package)\s+(for|in)/i
                ],
                examples: ['Search GitHub for React hooks', 'Find open source image libraries', 'Best Python packages']
            },
            
            // Crypto API
            crypto: {
                keywords: ['bitcoin', 'ethereum', 'crypto', 'cryptocurrency', 'btc', 'eth', 'blockchain', 'coin'],
                patterns: [
                    /(bitcoin|ethereum|crypto|btc|eth)\s+(price|value|rate)/i,
                    /cryptocurrency (price|market)/i,
                    /what'?s?.*(bitcoin|ethereum|btc|eth)/i
                ],
                examples: ['Bitcoin price', 'What\'s Ethereum worth?', 'Crypto market status']
            },
            
            // Wikipedia (Unlimited)
            wikipedia: {
                keywords: ['wikipedia', 'wiki', 'what is', 'who is', 'define', 'explain', 'tell me about'],
                patterns: [
                    /wikipedia (article|page|entry)/i,
                    /(what|who) (is|are|was|were)/i,
                    /(tell me|explain).*(about|what is)/i,
                    /information (about|on)/i
                ],
                examples: ['Wikipedia article on quantum physics', 'Who is Albert Einstein?', 'Tell me about the Roman Empire']
            },
            
            // Dictionary (Unlimited)
            dictionary: {
                keywords: ['define', 'definition', 'meaning', 'what does', 'dictionary'],
                patterns: [
                    /(define|definition of|meaning of)/i,
                    /what does.*(mean|means)/i,
                    /dictionary (for|of)/i
                ],
                examples: ['Define ephemeral', 'What does serendipity mean?', 'Meaning of ubiquitous']
            },
            
            // Gmail (Premium)
            gmail: {
                keywords: ['email', 'gmail', 'inbox', 'send', 'mail', 'message'],
                patterns: [
                    /(check|read|show|get)\s+(my\s+)?(email|gmail|inbox|mail)/i,
                    /(send|write|compose)\s+(email|mail)/i,
                    /emails? from/i
                ],
                examples: ['Check my Gmail', 'Send email to boss', 'Show emails from yesterday']
            },
            
            // Google Calendar (Premium)
            googleCalendar: {
                keywords: ['calendar', 'schedule', 'appointment', 'meeting', 'event', 'remind', 'reminder'],
                patterns: [
                    /(check|show|get)\s+(my\s+)?(calendar|schedule|appointments|meetings)/i,
                    /(add|create|schedule)\s+(meeting|appointment|event)/i,
                    /when (is|do i have|am i)/i,
                    /(set|create)\s+reminder/i
                ],
                examples: ['Check my calendar', 'Schedule meeting for tomorrow', 'When is my next appointment?']
            },
            
            // Google Drive (Premium)
            googleDrive: {
                keywords: ['drive', 'file', 'document', 'folder', 'upload', 'download', 'share'],
                patterns: [
                    /(find|search|get|show)\s+.*\s+(file|document|folder)/i,
                    /(upload|save|store).*(drive|document|file)/i,
                    /google drive/i,
                    /share (file|document|folder)/i
                ],
                examples: ['Find files in my Drive', 'Upload document to Drive', 'Search for Q4 report']
            },
            
            // Flight Tracking (Premium)
            flightTracking: {
                keywords: ['flight', 'plane', 'airline', 'airport', 'departure', 'arrival', 'layover'],
                patterns: [
                    /flight (status|number|from|to)/i,
                    /(track|check)\s+flight/i,
                    /(departure|arrival)\s+time/i,
                    /(airport|airline)\s+(status|delay)/i
                ],
                examples: ['Flight status for AA123', 'Track flight from NYC to LAX', 'Airport delays today']
            }
        };
    }
    
    detectAPI(message) {
        const text = message.toLowerCase().trim();
        const detectedAPIs = [];
        
        // Check each API type
        for (const [apiName, config] of Object.entries(this.apiPatterns)) {
            // Check patterns first (more specific)
            const patternMatch = config.patterns.some(pattern => pattern.test(message));
            
            // Check keywords (more general)
            const keywordMatch = config.keywords.some(keyword => 
                text.includes(keyword.toLowerCase())
            );
            
            if (patternMatch || keywordMatch) {
                detectedAPIs.push({
                    api: apiName,
                    confidence: patternMatch ? 'high' : 'medium',
                    matchType: patternMatch ? 'pattern' : 'keyword'
                });
            }
        }
        
        // Sort by confidence
        detectedAPIs.sort((a, b) => {
            if (a.confidence === 'high' && b.confidence !== 'high') return -1;
            if (a.confidence !== 'high' && b.confidence === 'high') return 1;
            return 0;
        });
        
        return detectedAPIs;
    }
    
    getBestAPI(message) {
        const detected = this.detectAPI(message);
        return detected.length > 0 ? detected[0].api : null;
    }
    
    needsAPI(message) {
        return this.detectAPI(message).length > 0;
    }
}

// ==========================================
// LEARNING ENGINE (Basic pattern learning)
// ==========================================
class LearningEngine {
    constructor() {
        this.corrections = this.loadCorrections();
        this.feedback = this.loadFeedback();
    }
    
    recordCorrection(original, corrected) {
        this.corrections.push({
            original: original,
            corrected: corrected,
            timestamp: Date.now()
        });
        
        // Keep last 100 corrections
        if (this.corrections.length > 100) {
            this.corrections.shift();
        }
        
        this.saveCorrections();
        console.log('📝 Correction recorded');
    }
    
    recordFeedback(messageIndex, type) {
        this.feedback.push({
            messageIndex: messageIndex,
            type: type,
            timestamp: Date.now()
        });
        
        // Keep last 100 feedback items
        if (this.feedback.length > 100) {
            this.feedback.shift();
        }
        
        this.saveFeedback();
        console.log('👍 Feedback recorded:', type);
    }
    
    loadCorrections() {
        try {
            const saved = localStorage.getItem('crump_corrections');
            return saved ? JSON.parse(saved) : [];
        } catch (e) {
            return [];
        }
    }
    
    saveCorrections() {
        localStorage.setItem('crump_corrections', JSON.stringify(this.corrections));
    }
    
    loadFeedback() {
        try {
            const saved = localStorage.getItem('crump_feedback');
            return saved ? JSON.parse(saved) : [];
        } catch (e) {
            return [];
        }
    }
    
    saveFeedback() {
        localStorage.setItem('crump_feedback', JSON.stringify(this.feedback));
    }
}

// ==========================================
// EXPORTS
// ==========================================
window.MessageDeduplicator = MessageDeduplicator;
window.ImageGenerationDetector = ImageGenerationDetector;
window.SearchDetectionEngine = SearchDetectionEngine;
window.APIDetectionEngine = APIDetectionEngine;
window.LearningEngine = LearningEngine;

// Create global instances
window.messageDeduplicator = new MessageDeduplicator();
window.imageGenerationDetector = new ImageGenerationDetector();
window.searchDetectionEngine = new SearchDetectionEngine();
window.apiDetectionEngine = new APIDetectionEngine();
window.learningEngine = new LearningEngine();

// Helper functions for backward compatibility
window.shouldGenerateImage = function(message) {
    return window.imageGenerationDetector.shouldGenerateImage(message);
};

console.log('✅ Detection Engines v3.1.0 loaded');
console.log('🧠 APIs supported:', Object.keys(window.apiDetectionEngine.apiPatterns).length);
