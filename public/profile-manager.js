// ==========================================
// CRUMP AI - USER PROFILE MANAGER v3.1.0
// Complete API Ecosystem + Annual Billing
// ==========================================

class UserProfileManager {
    constructor() {
        this.profile = this.loadProfile();
        this.usage = this.loadUsage();
        this.tiers = {
            free: {
                name: 'Free',
                icon: '🆓',
                price: { monthly: 0, annual: 0 },
                limits: {
                    messages: 100,
                    images: 10,
                    searches: 20,
                    // Free APIs
                    weather: 20,
                    news: 20,
                    sports: 20,
                    stocks: 10,
                    movies: 10,
                    // Unlimited free
                    wikipedia: -1,
                    dictionary: -1,
                    jokes: -1,
                    trivia: -1,
                    currency: -1,
                    qr: -1,
                    urlShortener: -1
                },
                features: [
                    'Basic chat',
                    'File uploads',
                    'Voice I/O',
                    '🌤️ Weather (20/mo)',
                    '📰 News (20/mo)',
                    '🏈 Sports scores (20/mo)',
                    '📈 Stock quotes (10/mo)',
                    '🎬 Movies/TV (10/mo)',
                    '📚 Wikipedia (unlimited)',
                    '📖 Dictionary (unlimited)',
                    '😂 Jokes & Trivia (unlimited)'
                ]
            },
            pro: {
                name: 'Pro',
                icon: '⭐',
                price: { monthly: 9.99, annual: 95 },
                savings: { amount: 24.88, percentage: 21 },
                limits: {
                    messages: 1000,
                    images: 100,
                    searches: 200,
                    // Enhanced APIs
                    weather: 100,
                    news: 100,
                    sports: 100,
                    stocks: 50,
                    movies: 50,
                    youtube: 50,
                    recipes: 50,
                    translation: 100,
                    github: 50,
                    crypto: 100,
                    spotify: 50,
                    googleMaps: 50,
                    googleSearch: 50,
                    // Unlimited free
                    wikipedia: -1,
                    dictionary: -1,
                    jokes: -1,
                    trivia: -1,
                    currency: -1,
                    qr: -1,
                    urlShortener: -1
                },
                features: [
                    'Everything in Free',
                    '1,000 messages/month',
                    '100 images/month',
                    '200 web searches/month',
                    '📺 YouTube search (50/mo)',
                    '🍳 Recipe search (50/mo)',
                    '🌐 Translation (100/mo)',
                    '💻 GitHub search (50/mo)',
                    '₿ Crypto prices (100/mo)',
                    '🎵 Spotify search (50/mo)',
                    '🗺️ Google Maps (50/mo)',
                    '🔍 Enhanced search (50/mo)',
                    'Multi-file uploads',
                    'PDF analysis',
                    'Priority responses',
                    'Advanced memory'
                ]
            },
            premium: {
                name: 'Premium',
                icon: '👑',
                price: { monthly: 24.99, annual: 239 },
                savings: { amount: 60.88, percentage: 20 },
                limits: {
                    messages: -1, // Unlimited
                    images: 500,
                    searches: -1, // Unlimited
                    // All APIs unlimited or high limits
                    weather: -1,
                    news: -1,
                    sports: -1,
                    stocks: -1,
                    movies: -1,
                    youtube: -1,
                    recipes: -1,
                    translation: -1,
                    github: -1,
                    crypto: -1,
                    spotify: -1,
                    googleMaps: -1,
                    googleSearch: -1,
                    wikipedia: -1,
                    dictionary: -1,
                    jokes: -1,
                    trivia: -1,
                    currency: -1,
                    qr: -1,
                    urlShortener: -1,
                    // Premium exclusive
                    gmail: -1,
                    googleCalendar: -1,
                    googleDrive: -1,
                    flightTracking: 500,
                    sportsDataPro: -1,
                    stocksPro: -1
                },
                features: [
                    'Everything in Pro',
                    '∞ Unlimited messages',
                    '500 images/month',
                    '∞ Unlimited searches',
                    '📧 Gmail integration',
                    '📅 Google Calendar',
                    '📁 Google Drive',
                    '✈️ Flight tracking (500/mo)',
                    '🏈 Real-time sports',
                    '📈 Professional stocks',
                    'All APIs unlimited',
                    'Extended memory',
                    'Custom themes',
                    'API access',
                    'Priority support'
                ]
            }
        };
        
        this.initializeProfile();
        console.log('👤 ProfileManager v3.1.0 initialized:', this.getTierInfo());
    }
    
    initializeProfile() {
        if (!this.profile.tier) {
            this.profile.tier = 'free';
        }
        if (!this.profile.billingPeriod) {
            this.profile.billingPeriod = 'monthly';
        }
        if (!this.profile.created) {
            this.profile.created = Date.now();
        }
        if (!this.profile.name) {
            this.profile.name = 'User';
        }
        if (!this.profile.initial) {
            this.profile.initial = 'U';
        }
        this.saveProfile();
    }
    
    // ==========================================
    // PROFILE MANAGEMENT
    // ==========================================
    
    updateProfile(updates) {
        if (updates.name !== undefined) {
            if (typeof updates.name === 'string' && updates.name.length > 0 && updates.name.length <= 100) {
                this.profile.name = updates.name.trim();
            } else {
                throw new Error('Invalid name: must be 1-100 characters');
            }
        }
        
        if (updates.email !== undefined) {
            if (updates.email === '' || this.validateEmail(updates.email)) {
                this.profile.email = updates.email.trim();
            } else {
                throw new Error('Invalid email format');
            }
        }
        
        if (updates.initial !== undefined) {
            if (typeof updates.initial === 'string' && updates.initial.length === 1) {
                this.profile.initial = updates.initial.toUpperCase();
            } else {
                throw new Error('Invalid initial: must be a single character');
            }
        }
        
        if (updates.avatar !== undefined) {
            if (updates.avatar === null || updates.avatar.startsWith('data:image/')) {
                this.profile.avatar = updates.avatar;
            } else {
                throw new Error('Invalid avatar: must be a data URL');
            }
        }
        
        if (updates.assistantName !== undefined) {
            if (typeof updates.assistantName === 'string' && updates.assistantName.length > 0 && updates.assistantName.length <= 50) {
                this.profile.assistantName = updates.assistantName.trim();
            } else {
                throw new Error('Invalid assistant name: must be 1-50 characters');
            }
        }
        
        this.saveProfile();
        console.log('✏️ Profile updated');
    }
    
    validateEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }
    
    getProfile() {
        return { ...this.profile };
    }
    
    // ==========================================
    // TIER MANAGEMENT
    // ==========================================
    
    getTier() {
        return this.profile.tier || 'free';
    }
    
    getBillingPeriod() {
        return this.profile.billingPeriod || 'monthly';
    }
    
    getTierInfo() {
        const tier = this.getTier();
        const tierData = this.tiers[tier];
        const billingPeriod = this.getBillingPeriod();
        
        return {
            current: tier,
            name: tierData.name,
            icon: tierData.icon,
            limits: tierData.limits,
            features: tierData.features,
            billingPeriod: billingPeriod,
            price: tierData.price,
            savings: tierData.savings || null
        };
    }
    
    upgradeTier(newTier, billingPeriod = 'monthly') {
        if (!this.tiers[newTier]) {
            throw new Error('Invalid tier');
        }
        
        if (billingPeriod !== 'monthly' && billingPeriod !== 'annual') {
            throw new Error('Invalid billing period');
        }
        
        this.profile.tier = newTier;
        this.profile.billingPeriod = billingPeriod;
        this.profile.upgraded = Date.now();
        
        // Calculate next billing date
        const now = new Date();
        if (billingPeriod === 'annual') {
            now.setFullYear(now.getFullYear() + 1);
        } else {
            now.setMonth(now.getMonth() + 1);
        }
        this.profile.nextBillingDate = now.getTime();
        
        this.saveProfile();
        
        console.log(`✨ Upgraded to ${newTier} (${billingPeriod})`);
        return true;
    }
    
    switchBillingPeriod(newPeriod) {
        if (this.profile.tier === 'free') {
            console.warn('Cannot change billing period for free tier');
            return false;
        }
        
        if (newPeriod !== 'monthly' && newPeriod !== 'annual') {
            throw new Error('Invalid billing period');
        }
        
        this.profile.billingPeriod = newPeriod;
        
        // Recalculate next billing date
        const now = new Date();
        if (newPeriod === 'annual') {
            now.setFullYear(now.getFullYear() + 1);
        } else {
            now.setMonth(now.getMonth() + 1);
        }
        this.profile.nextBillingDate = now.getTime();
        
        this.saveProfile();
        console.log(`🔄 Switched to ${newPeriod} billing`);
        return true;
    }
    
    downgradeTier(reason = 'user_request') {
        this.profile.tier = 'free';
        this.profile.billingPeriod = 'monthly';
        this.profile.downgraded = Date.now();
        this.profile.downgradeReason = reason;
        delete this.profile.nextBillingDate;
        this.saveProfile();
        
        console.log('📉 Downgraded to free tier');
        return true;
    }
    
    // ==========================================
    // USAGE TRACKING (ALL API METHODS)
    // ==========================================
    
    // Core usage
    incrementMessageUsage() {
        this.ensureCurrentMonth();
        this.usage.messages++;
        this.saveUsage();
    }
    
    incrementImageUsage() {
        this.ensureCurrentMonth();
        this.usage.images++;
        this.saveUsage();
    }
    
    incrementSearchUsage() {
        this.ensureCurrentMonth();
        this.usage.searches++;
        this.saveUsage();
    }
    
    // API usage - Free tier
    incrementWeatherUsage() {
        this.ensureCurrentMonth();
        this.usage.weather = (this.usage.weather || 0) + 1;
        this.saveUsage();
    }
    
    incrementNewsUsage() {
        this.ensureCurrentMonth();
        this.usage.news = (this.usage.news || 0) + 1;
        this.saveUsage();
    }
    
    incrementSportsUsage() {
        this.ensureCurrentMonth();
        this.usage.sports = (this.usage.sports || 0) + 1;
        this.saveUsage();
    }
    
    incrementStocksUsage() {
        this.ensureCurrentMonth();
        this.usage.stocks = (this.usage.stocks || 0) + 1;
        this.saveUsage();
    }
    
    incrementMoviesUsage() {
        this.ensureCurrentMonth();
        this.usage.movies = (this.usage.movies || 0) + 1;
        this.saveUsage();
    }
    
    // API usage - Pro tier
    incrementYoutubeUsage() {
        this.ensureCurrentMonth();
        this.usage.youtube = (this.usage.youtube || 0) + 1;
        this.saveUsage();
    }
    
    incrementRecipesUsage() {
        this.ensureCurrentMonth();
        this.usage.recipes = (this.usage.recipes || 0) + 1;
        this.saveUsage();
    }
    
    incrementTranslationUsage() {
        this.ensureCurrentMonth();
        this.usage.translation = (this.usage.translation || 0) + 1;
        this.saveUsage();
    }
    
    incrementGithubUsage() {
        this.ensureCurrentMonth();
        this.usage.github = (this.usage.github || 0) + 1;
        this.saveUsage();
    }
    
    incrementCryptoUsage() {
        this.ensureCurrentMonth();
        this.usage.crypto = (this.usage.crypto || 0) + 1;
        this.saveUsage();
    }
    
    incrementSpotifyUsage() {
        this.ensureCurrentMonth();
        this.usage.spotify = (this.usage.spotify || 0) + 1;
        this.saveUsage();
    }
    
    incrementGoogleMapsUsage() {
        this.ensureCurrentMonth();
        this.usage.googleMaps = (this.usage.googleMaps || 0) + 1;
        this.saveUsage();
    }
    
    incrementGoogleSearchUsage() {
        this.ensureCurrentMonth();
        this.usage.googleSearch = (this.usage.googleSearch || 0) + 1;
        this.saveUsage();
    }
    
    // API usage - Premium tier
    incrementGmailUsage() {
        this.ensureCurrentMonth();
        this.usage.gmail = (this.usage.gmail || 0) + 1;
        this.saveUsage();
    }
    
    incrementGoogleCalendarUsage() {
        this.ensureCurrentMonth();
        this.usage.googleCalendar = (this.usage.googleCalendar || 0) + 1;
        this.saveUsage();
    }
    
    incrementGoogleDriveUsage() {
        this.ensureCurrentMonth();
        this.usage.googleDrive = (this.usage.googleDrive || 0) + 1;
        this.saveUsage();
    }
    
    incrementFlightTrackingUsage() {
        this.ensureCurrentMonth();
        this.usage.flightTracking = (this.usage.flightTracking || 0) + 1;
        this.saveUsage();
    }
    
    // Legacy compatibility method
    incrementUsage(type, count = 1) {
        this.ensureCurrentMonth();
        
        const validTypes = [
            'messages', 'images', 'searches', 'weather', 'news', 'sports',
            'stocks', 'movies', 'youtube', 'recipes', 'translation', 'github',
            'crypto', 'spotify', 'googleMaps', 'googleSearch', 'gmail',
            'googleCalendar', 'googleDrive', 'flightTracking'
        ];
        
        if (validTypes.includes(type)) {
            this.usage[type] = (this.usage[type] || 0) + count;
            this.saveUsage();
        } else {
            console.warn(`Unknown usage type: ${type}`);
        }
    }
    
    getUsage() {
        this.ensureCurrentMonth();
        return { ...this.usage };
    }
    
    getUsageStats() {
        const tier = this.getTier();
        const limits = this.tiers[tier].limits;
        const usage = this.getUsage();
        
        const stats = {
            messages: usage.messages || 0,
            images: usage.images || 0,
            searches: usage.searches || 0,
            limits: limits
        };
        
        return stats;
    }
    
    // ==========================================
    // LIMIT CHECKING - CORE
    // ==========================================
    
    canSendMessage() {
        const tier = this.getTier();
        const limits = this.tiers[tier].limits;
        const usage = this.getUsage();
        
        if (limits.messages === -1) {
            return { allowed: true };
        }
        
        if (usage.messages >= limits.messages) {
            return {
                allowed: false,
                action: 'upgrade',
                message: `🚫 **Message Limit Reached**\n\nYou've used all ${limits.messages} messages this month.\n\n**Upgrade to Pro** for 1,000 messages/month or **Premium** for unlimited!`
            };
        }
        
        const percentage = (usage.messages / limits.messages) * 100;
        if (percentage >= 90) {
            return {
                allowed: true,
                warning: `⚠️ ${limits.messages - usage.messages} messages remaining this month`
            };
        }
        
        return { allowed: true };
    }
    
    canGenerateImage() {
        const tier = this.getTier();
        const limits = this.tiers[tier].limits;
        const usage = this.getUsage();
        
        if (limits.images === -1) {
            return { allowed: true };
        }
        
        if (usage.images >= limits.images) {
            return {
                allowed: false,
                action: 'upgrade',
                message: `🚫 **Image Limit Reached**\n\nYou've used all ${limits.images} images this month.\n\n**Upgrade to Pro** for 100 images/month or **Premium** for 500 images/month!`
            };
        }
        
        return { allowed: true };
    }
    
    canSearchWeb() {
        const tier = this.getTier();
        const limits = this.tiers[tier].limits;
        const usage = this.getUsage();
        
        if (limits.searches === -1) {
            return { allowed: true };
        }
        
        if (usage.searches >= limits.searches) {
            return {
                allowed: false,
                action: 'upgrade',
                message: `🚫 **Search Limit Reached**\n\nYou've used all ${limits.searches} searches this month.\n\nUpgrade for more!`
            };
        }
        
        return { allowed: true };
    }
    
    // ==========================================
    // LIMIT CHECKING - APIs
    // ==========================================
    
    canUseAPI(apiName) {
        const tier = this.getTier();
        const limits = this.tiers[tier].limits;
        const usage = this.getUsage();
        
        // Check if API exists in limits
        if (!(apiName in limits)) {
            return {
                allowed: false,
                message: `🚫 **${apiName} API Not Available**\n\nThis API is not available in your current tier.`,
                action: 'upgrade'
            };
        }
        
        const limit = limits[apiName];
        const used = usage[apiName] || 0;
        
        // Unlimited
        if (limit === -1) {
            return { allowed: true };
        }
        
        // Check limit
        if (used >= limit) {
            return {
                allowed: false,
                action: 'upgrade',
                message: `🚫 **${apiName} Limit Reached**\n\nYou've used all ${limit} ${apiName} calls this month.\n\nUpgrade for more!`
            };
        }
        
        // Warning at 90%
        const percentage = (used / limit) * 100;
        if (percentage >= 90) {
            return {
                allowed: true,
                warning: `⚠️ ${limit - used} ${apiName} calls remaining this month`
            };
        }
        
        return { allowed: true };
    }
    
    // Specific API checkers
    canUseWeather() { return this.canUseAPI('weather'); }
    canUseNews() { return this.canUseAPI('news'); }
    canUseSports() { return this.canUseAPI('sports'); }
    canUseStocks() { return this.canUseAPI('stocks'); }
    canUseMovies() { return this.canUseAPI('movies'); }
    canUseYoutube() { return this.canUseAPI('youtube'); }
    canUseRecipes() { return this.canUseAPI('recipes'); }
    canUseTranslation() { return this.canUseAPI('translation'); }
    canUseGithub() { return this.canUseAPI('github'); }
    canUseCrypto() { return this.canUseAPI('crypto'); }
    canUseSpotify() { return this.canUseAPI('spotify'); }
    canUseGoogleMaps() { return this.canUseAPI('googleMaps'); }
    canUseGoogleSearch() { return this.canUseAPI('googleSearch'); }
    canUseGmail() { return this.canUseAPI('gmail'); }
    canUseGoogleCalendar() { return this.canUseAPI('googleCalendar'); }
    canUseGoogleDrive() { return this.canUseAPI('googleDrive'); }
    canUseFlightTracking() { return this.canUseAPI('flightTracking'); }
    
    // ==========================================
    // MONTH MANAGEMENT
    // ==========================================
    
    ensureCurrentMonth() {
        const now = new Date();
        const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        
        if (this.usage.month !== currentMonth) {
            console.log(`📅 New month detected: ${currentMonth} (was ${this.usage.month})`);
            this.resetUsage(currentMonth);
        }
    }
    
    resetUsage(month) {
        this.usage = {
            month: month,
            messages: 0,
            images: 0,
            searches: 0,
            // All API usage counters
            weather: 0,
            news: 0,
            sports: 0,
            stocks: 0,
            movies: 0,
            youtube: 0,
            recipes: 0,
            translation: 0,
            github: 0,
            crypto: 0,
            spotify: 0,
            googleMaps: 0,
            googleSearch: 0,
            gmail: 0,
            googleCalendar: 0,
            googleDrive: 0,
            flightTracking: 0,
            resetAt: Date.now()
        };
        this.saveUsage();
        console.log('🔄 Usage reset for new month');
    }
    
    // ==========================================
    // PERSISTENCE
    // ==========================================
    
    loadProfile() {
        const saved = localStorage.getItem('crump_user_profile');
        if (saved) {
            try {
                return JSON.parse(saved);
            } catch (e) {
                console.error('Failed to load profile:', e);
                return {};
            }
        }
        return {};
    }
    
    saveProfile() {
        localStorage.setItem('crump_user_profile', JSON.stringify(this.profile));
    }
    
    loadUsage() {
        const saved = localStorage.getItem('crump_usage');
        if (saved) {
            try {
                return JSON.parse(saved);
            } catch (e) {
                console.error('Failed to load usage:', e);
                return this.getDefaultUsage();
            }
        }
        return this.getDefaultUsage();
    }
    
    saveUsage() {
        localStorage.setItem('crump_usage', JSON.stringify(this.usage));
    }
    
    getDefaultUsage() {
        const now = new Date();
        const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        
        return {
            month: currentMonth,
            messages: 0,
            images: 0,
            searches: 0,
            weather: 0,
            news: 0,
            sports: 0,
            stocks: 0,
            movies: 0,
            youtube: 0,
            recipes: 0,
            translation: 0,
            github: 0,
            crypto: 0,
            spotify: 0,
            googleMaps: 0,
            googleSearch: 0,
            gmail: 0,
            googleCalendar: 0,
            googleDrive: 0,
            flightTracking: 0,
            resetAt: Date.now()
        };
    }
}

// ==========================================
// EXPORT
// ==========================================
window.UserProfileManager = UserProfileManager;
window.ProfileManager = UserProfileManager; // Alias for compatibility

console.log('✅ ProfileManager v3.1.0 loaded - Complete API ecosystem ready');
