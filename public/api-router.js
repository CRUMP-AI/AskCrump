// ==========================================
// CRUMP AI - API ROUTER v3.1.0
// Master routing system for all APIs
// ==========================================

class APIRouter {
    constructor() {
        this.apiEndpoints = {
            weather: '/api/weather',
            sports: '/api/sports',
            stocks: '/api/stocks',
            news: '/api/news',
            movies: '/api/movies',
            youtube: '/api/youtube',
            spotify: '/api/spotify',
            googleMaps: '/api/google-maps',
            googleSearch: '/api/google-search',
            recipes: '/api/recipes',
            translation: '/api/translation',
            github: '/api/github',
            crypto: '/api/crypto',
            wikipedia: '/api/wikipedia',
            dictionary: '/api/dictionary',
            gmail: '/api/gmail',
            googleCalendar: '/api/google-calendar',
            googleDrive: '/api/google-drive',
            flightTracking: '/api/flights'
        };
        
        // Free APIs that work without keys
        this.freeAPIs = [
            'wikipedia',
            'dictionary',
            'currency',
            'qr',
            'urlShortener',
            'jokes',
            'trivia'
        ];
        
        console.log('🔌 API Router v3.1.0 initialized');
    }
    
    // ==========================================
    // MAIN ROUTING METHOD
    // ==========================================
    async routeRequest(message, context = {}) {
        try {
            // Detect which API to use
            if (!window.apiDetectionEngine) {
                console.warn('⚠️ API Detection Engine not found');
                return { success: false, error: 'API detection not available' };
            }
            
            const detectedAPIs = window.apiDetectionEngine.detectAPI(message);
            
            if (detectedAPIs.length === 0) {
                return { success: false, error: 'No API detected', needsAPI: false };
            }
            
            console.log('🎯 Detected APIs:', detectedAPIs.map(d => d.api).join(', '));
            
            // Try each detected API in order of confidence
            for (const detection of detectedAPIs) {
                const apiName = detection.api;
                
                // Check if user can use this API
                const canUse = this.checkAPILimit(apiName);
                
                if (!canUse.allowed) {
                    console.warn(`❌ ${apiName} API limit reached`);
                    
                    // If this was the only/best option, return error
                    if (detection === detectedAPIs[0]) {
                        return {
                            success: false,
                            error: canUse.message,
                            limitReached: true,
                            action: canUse.action
                        };
                    }
                    
                    // Otherwise try next API
                    continue;
                }
                
                // Route to specific API handler
                console.log(`📡 Routing to ${apiName} API...`);
                const result = await this.callAPI(apiName, message, context);
                
                if (result.success) {
                    // Track usage
                    this.trackAPIUsage(apiName);
                    
                    // Show warning if provided
                    if (canUse.warning) {
                        result.warning = canUse.warning;
                    }
                    
                    return result;
                }
                
                // If API call failed, try next one
                console.warn(`⚠️ ${apiName} API failed, trying next...`);
            }
            
            // All APIs failed
            return {
                success: false,
                error: 'All detected APIs failed to respond'
            };
            
        } catch (error) {
            console.error('❌ API Router error:', error);
            return {
                success: false,
                error: error.message || 'API routing failed'
            };
        }
    }
    
    // ==========================================
    // CHECK API LIMITS
    // ==========================================
    checkAPILimit(apiName) {
        if (!window.profileManager) {
            return { allowed: true }; // Allow if no profile manager
        }
        
        // Free unlimited APIs
        if (this.freeAPIs.includes(apiName)) {
            return { allowed: true };
        }
        
        // Check specific API limit
        return window.profileManager.canUseAPI(apiName);
    }
    
    // ==========================================
    // TRACK API USAGE
    // ==========================================
    trackAPIUsage(apiName) {
        if (!window.profileManager) return;
        
        // Map API names to increment methods
        const methodMap = {
            weather: 'incrementWeatherUsage',
            sports: 'incrementSportsUsage',
            stocks: 'incrementStocksUsage',
            news: 'incrementNewsUsage',
            movies: 'incrementMoviesUsage',
            youtube: 'incrementYoutubeUsage',
            spotify: 'incrementSpotifyUsage',
            googleMaps: 'incrementGoogleMapsUsage',
            googleSearch: 'incrementGoogleSearchUsage',
            recipes: 'incrementRecipesUsage',
            translation: 'incrementTranslationUsage',
            github: 'incrementGithubUsage',
            crypto: 'incrementCryptoUsage',
            gmail: 'incrementGmailUsage',
            googleCalendar: 'incrementGoogleCalendarUsage',
            googleDrive: 'incrementGoogleDriveUsage',
            flightTracking: 'incrementFlightTrackingUsage'
        };
        
        const method = methodMap[apiName];
        
        if (method && typeof window.profileManager[method] === 'function') {
            window.profileManager[method]();
            console.log(`📊 Tracked ${apiName} usage`);
        } else {
            console.warn(`⚠️ No tracking method for ${apiName}`);
        }
    }
    
    // ==========================================
    // CALL SPECIFIC API
    // ==========================================
    async callAPI(apiName, message, context) {
        const endpoint = this.apiEndpoints[apiName];
        
        if (!endpoint) {
            // Handle free APIs that don't need endpoints
            if (this.freeAPIs.includes(apiName)) {
                return await this.callFreeAPI(apiName, message);
            }
            
            return {
                success: false,
                error: `No endpoint configured for ${apiName}`
            };
        }
        
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: message,
                    context: context
                })
            });
            
            if (!response.ok) {
                // Check if it's a missing API key
                if (response.status === 503) {
                    const data = await response.json();
                    return {
                        success: false,
                        error: data.error || 'API key not configured',
                        missingKey: true
                    };
                }
                
                throw new Error(`API returned ${response.status}`);
            }
            
            const data = await response.json();
            
            return {
                success: true,
                api: apiName,
                data: data,
                formattedResponse: this.formatAPIResponse(apiName, data)
            };
            
        } catch (error) {
            console.error(`❌ ${apiName} API error:`, error);
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    // ==========================================
    // FREE API HANDLERS (No backend needed)
    // ==========================================
    async callFreeAPI(apiName, message) {
        switch (apiName) {
            case 'wikipedia':
                return await this.callWikipedia(message);
            
            case 'dictionary':
                return await this.callDictionary(message);
            
            case 'jokes':
                return await this.callJokesAPI();
            
            case 'trivia':
                return await this.callTriviaAPI();
            
            case 'currency':
                return await this.callCurrencyAPI(message);
            
            case 'qr':
                return await this.callQRAPI(message);
            
            case 'urlShortener':
                return await this.callURLShortener(message);
            
            default:
                return { success: false, error: 'Unknown free API' };
        }
    }
    
    // Wikipedia API (free, no key)
    async callWikipedia(message) {
        try {
            // Extract search term
            const searchTerm = message
                .replace(/wikipedia|wiki|tell me about|what is|who is/gi, '')
                .trim();
            
            const url = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(searchTerm)}`;
            
            const response = await fetch(url);
            if (!response.ok) throw new Error('Wikipedia lookup failed');
            
            const data = await response.json();
            
            return {
                success: true,
                api: 'wikipedia',
                data: data,
                formattedResponse: `**${data.title}**\n\n${data.extract}\n\n[Read more](${data.content_urls.desktop.page})`
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }
    
    // Dictionary API (free, no key)
    async callDictionary(message) {
        try {
            // Extract word
            const word = message
                .replace(/define|definition|meaning|what does|mean/gi, '')
                .trim()
                .split(' ')[0];
            
            const url = `https://api.dictionaryapi.dev/api/v2/entries/en/${encodeURIComponent(word)}`;
            
            const response = await fetch(url);
            if (!response.ok) throw new Error('Word not found');
            
            const data = await response.json();
            const entry = data[0];
            
            let formatted = `**${entry.word}** ${entry.phonetic || ''}\n\n`;
            
            entry.meanings.forEach(meaning => {
                formatted += `*${meaning.partOfSpeech}*\n`;
                meaning.definitions.slice(0, 2).forEach((def, i) => {
                    formatted += `${i + 1}. ${def.definition}\n`;
                    if (def.example) {
                        formatted += `   *Example: "${def.example}"*\n`;
                    }
                });
                formatted += '\n';
            });
            
            return {
                success: true,
                api: 'dictionary',
                data: entry,
                formattedResponse: formatted
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }
    
    // Jokes API (free, no key)
    async callJokesAPI() {
        try {
            const url = 'https://icanhazdadjoke.com/';
            
            const response = await fetch(url, {
                headers: { 'Accept': 'application/json' }
            });
            
            if (!response.ok) throw new Error('Joke API failed');
            
            const data = await response.json();
            
            return {
                success: true,
                api: 'jokes',
                data: data,
                formattedResponse: `😄 ${data.joke}`
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }
    
    // Trivia API (free, no key)
    async callTriviaAPI() {
        try {
            const url = 'https://opentdb.com/api.php?amount=1&type=multiple';
            
            const response = await fetch(url);
            if (!response.ok) throw new Error('Trivia API failed');
            
            const data = await response.json();
            const question = data.results[0];
            
            const allAnswers = [...question.incorrect_answers, question.correct_answer]
                .sort(() => Math.random() - 0.5);
            
            let formatted = `**${this.decodeHTML(question.category)}**\n\n`;
            formatted += `${this.decodeHTML(question.question)}\n\n`;
            
            allAnswers.forEach((answer, i) => {
                const letter = String.fromCharCode(65 + i);
                formatted += `${letter}. ${this.decodeHTML(answer)}\n`;
            });
            
            formatted += `\n*Difficulty: ${question.difficulty}*`;
            
            return {
                success: true,
                api: 'trivia',
                data: question,
                formattedResponse: formatted,
                correctAnswer: this.decodeHTML(question.correct_answer)
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }
    
    // Currency Converter API (free, no key)
    async callCurrencyAPI(message) {
        try {
            // Extract currencies and amount
            const match = message.match(/(\d+\.?\d*)\s*(\w{3})\s*to\s*(\w{3})/i);
            
            if (!match) {
                return {
                    success: false,
                    error: 'Please specify: amount FROM_CURRENCY to TO_CURRENCY (e.g., 100 USD to EUR)'
                };
            }
            
            const [, amount, from, to] = match;
            
            const url = `https://api.exchangerate-api.com/v4/latest/${from.toUpperCase()}`;
            
            const response = await fetch(url);
            if (!response.ok) throw new Error('Currency API failed');
            
            const data = await response.json();
            const rate = data.rates[to.toUpperCase()];
            
            if (!rate) {
                throw new Error(`Currency ${to.toUpperCase()} not found`);
            }
            
            const converted = (parseFloat(amount) * rate).toFixed(2);
            
            return {
                success: true,
                api: 'currency',
                data: { from, to, rate, amount, converted },
                formattedResponse: `💱 **${amount} ${from.toUpperCase()} = ${converted} ${to.toUpperCase()}**\n\nExchange rate: 1 ${from.toUpperCase()} = ${rate.toFixed(4)} ${to.toUpperCase()}`
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }
    
    // QR Code API (free, no key)
    async callQRAPI(message) {
        try {
            // Extract text to encode
            const text = message
                .replace(/generate|create|make|qr code|qr/gi, '')
                .trim();
            
            if (!text || text.length < 1) {
                return {
                    success: false,
                    error: 'Please provide text to encode in QR code'
                };
            }
            
            const url = `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(text)}`;
            
            return {
                success: true,
                api: 'qr',
                data: { text, url },
                formattedResponse: `**QR Code Generated**\n\n![QR Code](${url})\n\n*Encoding: ${text}*`
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }
    
    // URL Shortener API (free, no key)
    async callURLShortener(message) {
        try {
            // Extract URL
            const urlMatch = message.match(/(https?:\/\/[^\s]+)/);
            
            if (!urlMatch) {
                return {
                    success: false,
                    error: 'Please provide a valid URL to shorten'
                };
            }
            
            const longUrl = urlMatch[1];
            
            const response = await fetch(`https://tinyurl.com/api-create.php?url=${encodeURIComponent(longUrl)}`);
            
            if (!response.ok) throw new Error('URL shortening failed');
            
            const shortUrl = await response.text();
            
            return {
                success: true,
                api: 'urlShortener',
                data: { longUrl, shortUrl },
                formattedResponse: `🔗 **URL Shortened**\n\nOriginal: ${longUrl}\n\nShort: ${shortUrl}`
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    }
    
    // ==========================================
    // RESPONSE FORMATTING
    // ==========================================
    formatAPIResponse(apiName, data) {
        // This will be customized per API
        // For now, return raw data
        return JSON.stringify(data, null, 2);
    }
    
    // ==========================================
    // UTILITY
    // ==========================================
    decodeHTML(text) {
        const div = document.createElement('div');
        div.innerHTML = text;
        return div.textContent;
    }
    
    // ==========================================
    // CHECK IF MESSAGE NEEDS API
    // ==========================================
    messageNeedsAPI(message) {
        if (!window.apiDetectionEngine) return false;
        return window.apiDetectionEngine.needsAPI(message);
    }
}

// ==========================================
// ENHANCED API INTEGRATION
// ==========================================
async function enhanceMessageWithAPIs(message, context = {}) {
    if (!window.apiRouter) {
        console.warn('⚠️ API Router not initialized');
        return null;
    }
    
    // Check if message needs any API
    if (!window.apiRouter.messageNeedsAPI(message)) {
        return null;
    }
    
    console.log('🔍 Message needs API enhancement');
    
    // Route the request
    const result = await window.apiRouter.routeRequest(message, context);
    
    if (result.success) {
        console.log('✅ API call successful:', result.api);
        return result;
    } else {
        console.warn('⚠️ API call failed:', result.error);
        
        // If limit reached, show upgrade prompt
        if (result.limitReached && result.action === 'upgrade') {
            if (typeof showUpgradePrompt === 'function') {
                setTimeout(() => showUpgradePrompt(), 1000);
            }
        }
        
        return result;
    }
}

// ==========================================
// EXPORTS
// ==========================================
window.APIRouter = APIRouter;
window.apiRouter = new APIRouter();
window.enhanceMessageWithAPIs = enhanceMessageWithAPIs;

console.log('✅ API Router v3.1.0 loaded');
console.log('🔌 Endpoints configured:', Object.keys(window.apiRouter.apiEndpoints).length);
console.log('🆓 Free APIs available:', window.apiRouter.freeAPIs.length);
