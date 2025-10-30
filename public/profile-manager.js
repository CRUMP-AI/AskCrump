// ==========================================
// CRUMP AI - PROFESSIONAL TIER MANAGER v2.0
// Launch-ready with real limits enforcement
// ==========================================

class ProfileManager {
    constructor() {
        this.profile = this.loadProfile();
        this.usage = this.loadUsage();
        this.initializeProfile();
        
        console.log('[ProfileManager] Initialized - Tier:', this.profile.tier || 'free');
    }

    getTierDefinitions() {
        return {
            free: {
                name: 'Free',
                displayName: 'Free Tier',
                price: { monthly: 0, annual: 0 },
                limits: {
                    messages: 100,
                    images: 10,
                    searches: 20,
                    weather: 20,
                    news: 20,
                    sports: 20,
                    stocks: 10,
                    movies: 10,
                    autonomous: false
                },
                features: [
                    '100 AI messages per month',
                    '10 image generations',
                    '20 web searches',
                    'Basic API access',
                    'Standard support'
                ]
            },
            pro: {
                name: 'Pro',
                displayName: 'Professional',
                price: { monthly: 9.99, annual: 95.04 },
                limits: {
                    messages: 1000,
                    images: 100,
                    searches: 200,
                    weather: 100,
                    news: 100,
                    sports: 100,
                    stocks: 50,
                    movies: 50,
                    autonomous: true
                },
                features: [
                    '1,000 AI messages per month',
                    '100 image generations',
                    '200 web searches',
                    'Extended API access',
                    'Autonomous messaging',
                    'Priority support'
                ]
            },
            premium: {
                name: 'Premium',
                displayName: 'Premium',
                price: { monthly: 19.99, annual: 191.04 },
                limits: {
                    messages: -1,
                    images: 500,
                    searches: -1,
                    weather: -1,
                    news: -1,
                    sports: -1,
                    stocks: -1,
                    movies: -1,
                    autonomous: true
                },
                features: [
                    'Unlimited AI messages',
                    '500 image generations',
                    'Unlimited web searches',
                    'Full API access',
                    'Autonomous messaging',
                    'Advanced features',
                    'Premium support',
                    'Early access to new features'
                ]
            },
            developer: {
                name: 'Developer',
                displayName: 'Developer Access',
                price: { monthly: 0, annual: 0 },
                limits: {
                    messages: -1,
                    images: -1,
                    searches: -1,
                    weather: -1,
                    news: -1,
                    sports: -1,
                    stocks: -1,
                    movies: -1,
                    autonomous: true
                },
                features: ['Unlimited access', 'All features', 'No restrictions']
            }
        };
    }

    initializeProfile() {
        if (!this.profile.tier) this.profile.tier = 'free';
        if (!this.profile.created) this.profile.created = Date.now();
        if (!this.profile.name) this.profile.name = 'User';
        if (!this.profile.initial) this.profile.initial = 'U';
        if (!this.profile.billingPeriod) this.profile.billingPeriod = 'monthly';
        this.saveProfile();
    }

    getTier() {
        return this.profile.tier || 'free';
    }

    getTierInfo() {
        const tier = this.getTier();
        const definitions = this.getTierDefinitions();
        const tierData = definitions[tier] || definitions.free;
        
        return {
            current: tier,
            name: tierData.displayName,
            billingPeriod: this.profile.billingPeriod || 'monthly',
            limits: tierData.limits,
            features: tierData.features,
            price: tierData.price
        };
    }

    upgradeTier(newTier, billingPeriod = 'monthly') {
        const definitions = this.getTierDefinitions();
        if (!definitions[newTier]) return false;

        this.profile.tier = newTier;
        this.profile.billingPeriod = billingPeriod;
        this.profile.upgradedAt = Date.now();
        this.saveProfile();
        
        const now = new Date();
        const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        this.resetUsage(currentMonth);
        
        return true;
    }

    downgradeTier() {
        this.profile.tier = 'free';
        this.profile.billingPeriod = 'monthly';
        delete this.profile.upgradedAt;
        this.saveProfile();
        return true;
    }

    checkLimit(type) {
        const tierInfo = this.getTierInfo();
        const limit = tierInfo.limits[type];
        
        if (limit === -1) return { allowed: true };
        if (limit === 0) return { allowed: false, message: `${type} not available on current plan`, action: 'upgrade' };
        
        this.ensureCurrentMonth();
        const used = this.usage[type] || 0;
        
        if (used >= limit) {
            return { allowed: false, message: `Monthly ${type} limit reached (${limit}/${limit})`, action: 'upgrade' };
        }
        
        const percentUsed = (used / limit) * 100;
        const warning = percentUsed >= 90 ? `${limit - used} ${type} remaining this month` : null;
        
        return { allowed: true, warning };
    }

    canSendMessage() { return this.checkLimit('messages'); }
    canGenerateImage() { return this.checkLimit('images'); }
    canSearchWeb() { return this.checkLimit('searches'); }
    canUseAutonomous() { return this.getTierInfo().limits.autonomous === true; }

    incrementUsage(type) {
        this.ensureCurrentMonth();
        if (!this.usage[type]) this.usage[type] = 0;
        this.usage[type]++;
        this.saveUsage();
    }

    getUsageStats() {
        const usage = this.getUsage();
        const tierInfo = this.getTierInfo();
        
        return {
            messages: { used: usage.messages || 0, limit: tierInfo.limits.messages },
            images: { used: usage.images || 0, limit: tierInfo.limits.images },
            searches: { used: usage.searches || 0, limit: tierInfo.limits.searches },
            weather: { used: usage.weather || 0, limit: tierInfo.limits.weather },
            news: { used: usage.news || 0, limit: tierInfo.limits.news },
            sports: { used: usage.sports || 0, limit: tierInfo.limits.sports }
        };
    }

    ensureCurrentMonth() {
        const now = new Date();
        const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        if (this.usage.month !== currentMonth) {
            this.resetUsage(currentMonth);
        }
    }

    resetUsage(month) {
        this.usage = {
            month,
            messages: 0,
            images: 0,
            searches: 0,
            weather: 0,
            news: 0,
            sports: 0,
            stocks: 0,
            movies: 0,
            resetAt: Date.now()
        };
        this.saveUsage();
    }

    getUsage() {
        this.ensureCurrentMonth();
        return { ...this.usage };
    }

    updateProfile(updates) {
        if (updates.name) this.profile.name = updates.name.trim();
        if (updates.email !== undefined) this.profile.email = updates.email.trim();
        if (updates.initial) this.profile.initial = updates.initial.toUpperCase();
        if (updates.assistantName) this.profile.assistantName = updates.assistantName.trim();
        this.saveProfile();
    }

    getProfile() {
        return { ...this.profile };
    }

    loadProfile() {
        try {
            const saved = localStorage.getItem('crump_user_profile');
            return saved ? JSON.parse(saved) : {};
        } catch (e) {
            return {};
        }
    }

    saveProfile() {
        try {
            localStorage.setItem('crump_user_profile', JSON.stringify(this.profile));
        } catch (e) {
            console.error('[ProfileManager] Save failed:', e);
        }
    }

    loadUsage() {
        try {
            const saved = localStorage.getItem('crump_usage');
            return saved ? JSON.parse(saved) : this.getDefaultUsage();
        } catch (e) {
            return this.getDefaultUsage();
        }
    }

    saveUsage() {
        try {
            localStorage.setItem('crump_usage', JSON.stringify(this.usage));
        } catch (e) {
            console.error('[ProfileManager] Save failed:', e);
        }
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
            resetAt: Date.now()
        };
    }
}

window.ProfileManager = ProfileManager;
window.UserProfileManager = ProfileManager;

console.log('[ProfileManager] Professional tier system ready');
