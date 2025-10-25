// ==========================================
// CRUMP AI - USER PROFILE MANAGER v3.2.0
// CLEANED - Only Real APIs (13 total)
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
                    // Core features
                    messages: 100,
                    images: 10,
                    searches: 20,
                    
                    // APIs with keys (limited)
                    weather: 20,
                    news: 20,
                    
                    // Free APIs (unlimited)
                    wikipedia: -1,
                    dictionary: -1,
                    jokes: -1,
                    trivia: -1,
                    currency: -1,
                    qr: -1,
                    urlShortener: -1
                },
                features: [
                    '100 messages/month',
                    '10 images/month',
                    '20 web searches/month',
                    '🌤️ Weather (20/mo)',
                    '📰 News (20/mo)',
                    '📚 Wikipedia (unlimited)',
                    '📖 Dictionary (unlimited)',
                    '😂 Jokes & Trivia (unlimited)',
                    '💱 Currency converter (unlimited)',
                    '📱 QR codes (unlimited)',
                    '🔗 URL shortener (unlimited)',
                    'File uploads',
                    'Voice I/O'
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
                    weather: 100,
                    news: 100,
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
                    '🌤️ Weather (100/mo)',
                    '📰 News (100/mo)',
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
                    weather: -1,
                    news: -1,
                    wikipedia: -1,
                    dictionary: -1,
                    jokes: -1,
                    trivia: -1,
                    currency: -1,
                    qr: -1,
                    urlShortener: -1
                },
                features: [
                    'Everything in Pro',
                    '∞ Unlimited messages',
                    '500 images/month',
                    '∞ Unlimited searches',
                    '🌤️ Weather (unlimited)',
                    '📰 News (unlimited)',
                    'Extended memory',
                    'Custom themes (soon)',
                    'API access (soon)',
                    'Priority support'
                ]
            }
        };
        
        this.initializeProfile();
        console.log('👤 ProfileManager v3.2.0 initialized:', this.getTierInfo());
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
    // USAGE TRACKING - CORE FEATURES
    // ==========================================
    
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
    
    // ==========================================
    // USAGE TRACKING - APIs
    // ==========================================
    
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
    
    // Wikipedia, dictionary, jokes, trivia, currency, qr, urlShortener are unlimited
    // No need to track usage for unlimited APIs
    
    // Legacy compatibility method
    incrementUsage(type, count = 1) {
        this.ensureCurrentMonth();
        
        const validTypes = [
            'messages', 'images', 'searches', 
            'weather', 'news'
            // Unlimited APIs don't need tracking
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
            weather: usage.weather || 0,
            news: usage.news || 0,
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
    
    // Specific API checkers (only real APIs)
    canUseWeather() { return this.canUseAPI('weather'); }
    canUseNews() { return this.canUseAPI('news'); }
    
    // Unlimited APIs always return true
    canUseWikipedia() { return { allowed: true }; }
    canUseDictionary() { return { allowed: true }; }
    canUseJokes() { return { allowed: true }; }
    canUseTrivia() { return { allowed: true }; }
    canUseCurrency() { return { allowed: true }; }
    canUseQR() { return { allowed: true }; }
    canUseUrlShortener() { return { allowed: true }; }
    
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
            weather: 0,
            news: 0,
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
            resetAt: Date.now()
        };
    }
}

// ==========================================
// EXPORT
// ==========================================
window.UserProfileManager = UserProfileManager;
window.ProfileManager = UserProfileManager; // Alias for compatibility

console.log('✅ ProfileManager v3.2.0 loaded - 13 Real APIs only');
