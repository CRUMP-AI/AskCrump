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
            
            console.log('📡 Detected APIs:', detectedAPIs);
            
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
                            error: canUse.reason || 'API limit reached',
                            needsUpgrade: true
                        };
                    }
                    
                    continue; // Try next API
                }
                
                console.log(`📡 Routing to ${apiName} API...`);
                const result = await this.callAPI(apiName, message, context, detection);
                
                if (result && result.success) {
                    return {
                        ...result,
                        usedAPI: apiName
                    };
                } else {
                    console.warn(`⚠️ ${apiName} API failed, trying next...`);
                }
            }
            
            // All APIs failed
            return {
                success: false,
                error: 'All API calls failed',
                needsAPI: true
            };
            
        } catch (error) {
            console.error('❌ API routing error:', error);
            return {
                success: false,
                error: 'API routing error',
                details: error.message
            };
        }
    }
    
    // ==========================================
    // API LIMIT CHECKING
    // ==========================================
    checkAPILimit(apiName) {
        try {
            const profile = window.currentProfile || window.profileManager?.getProfile();
            if (!profile) {
                return { allowed: false, reason: 'No profile loaded' };
            }
            
            // Free unlimited APIs
            if (this.freeAPIs.includes(apiName)) {
                return { allowed: true };
            }
            
            // Check specific API limits based on tier
            const tier = profile.subscription?.tier || 'free';
            const usage = profile.apiUsage || {};
            const apiUsage = usage[apiName] || { count: 0 };
            
            // Define limits per tier
            const limits = {
                free: 10,
                pro: 100,
                enterprise: Infinity
            };
            
            const limit = limits[tier] ?? 10;
            
            if (apiUsage.count >= limit) {
                return {
                    allowed: false,
                    reason: `API limit reached for ${apiName} on ${tier} tier`
                };
            }
            
            return { allowed: true };
        } catch (error) {
            console.warn('⚠️ API limit check failed:', error);
            return { allowed: true }; // Fail open
        }
    }
    
    // ==========================================
    // API CALL HANDLER
    // ==========================================
    async callAPI(apiName, message, context, detection) {
        try {
            const endpoint = this.apiEndpoints[apiName];
            
            if (!endpoint) {
                console.warn(`⚠️ No endpoint configured for API: ${apiName}`);
                
                // Handle free APIs that don't need endpoints
                if (this.freeAPIs.includes(apiName)) {
                    return await this.callFreeAPI(apiName, message);
                }
                
                return { success: false, error: 'API not configured' };
            }
            
            const payload = {
                message,
                context,
                detection
            };
            
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                const text = await response.text();
                console.warn(`⚠️ ${apiName} API error:`, response.status, text);
                
                return {
                    success: false,
                    error: `API error: ${response.status}`,
                    details: text
                };
            }
            
            const data = await response.json();
            return {
                success: true,
                data,
                raw: data
            };
            
        } catch (error) {
            console.error(`❌ Error calling ${apiName} API:`, error);
            return {
                success: false,
                error: 'API call failed',
                details: error.message
            };
        }
    }
    
    // ==========================================
    // FREE API HANDLER
    // ==========================================
    async callFreeAPI(apiName, message) {
        try {
            console.log(`📡 Calling free API: ${apiName}`);
            
            // Example: Wikipedia, dictionary, etc.
            // Here you'd implement the logic for free APIs that don't require backend endpoints
            
            return {
                success: true,
                data: {
                    message: `Free API (${apiName}) would handle: "${message}"`
                }
            };
            
        } catch (error) {
            console.error(`❌ Free API error (${apiName}):`, error);
            return {
                success: false,
                error: 'Free API call failed',
                details: error.message
            };
        }
    }
}

// ==========================================
// MESSAGE ENHANCEMENT
// ==========================================
async function enhanceMessageWithAPIs(message, context = {}) {
    if (!window.apiRouter) {
        console.warn('⚠️ API Router not initialized');
        return message;
    }
    
    const result = await window.apiRouter.routeRequest(message, context);
    
    if (!result.success) {
        // If upgrade is needed, show upgrade prompt
        if (result.needsUpgrade) {
            console.log('💳 Upgrade needed for API:', result);
            if (typeof showUpgradePrompt === 'function') {
                setTimeout(() => showUpgradePrompt(), 1000);
            }
        }
        
        return message;
    }
    
    // Append API result to message
    if (result.data && result.data.message) {
        return `${message}\n\n---\n\n${result.data.message}`;
    }
    
    return message;
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
