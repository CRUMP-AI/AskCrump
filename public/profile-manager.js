// ==========================================
// CRUMP AI - PROFESSIONAL TIER MANAGER v2.1
// Launch-ready with real limits + trial sync
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
                    messages: 10,  
                    images: 3,    
                    searches: 5,   
                    weather: 5,   
                    news: 5,       
                    sports: 5,    
                    stocks: 3,    
                    movies: 3,    
                    autonomous: false
                },
                features: [
                    'Core chat',
                    'Basic tools',
                    'Limited image generation'
                ]
            },
            pro: {
                name: 'Pro',
                displayName: 'Professional',
                price: { monthly: 15, annual: 144 }, // example
                limits: {
                    messages: 1000,
                    images: 100,
                    searches: 200,
                    weather: 200,
                    news: 200,
                    sports: 200,
                    stocks: 100,
                    movies: 100,
                    autonomous: true
                },
                features: [
                    'Priority access',
                    'Autonomous workflows',
                    'Expanded tools & analytics',
                    'High image generation limits'
                ]
            },
            enterprise: {
                name: 'Enterprise',
                displayName: 'Enterprise',
                price: { monthly: 49, annual: 480 }, // example
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
                features: [
                    'Unlimited usage',
                    'Priority support',
                    'Custom integrations',
                    'Advanced controls'
                ]
            }
        };
    }

    loadProfile() {
        try {
            const raw = localStorage.getItem('crump_user_profile');
            if (!raw) return {};
            return JSON.parse(raw);
        } catch (e) {
            console.warn('[ProfileManager] Failed to load profile:', e);
            return {};
        }
    }

    saveProfile() {
        try {
            localStorage.setItem('crump_user_profile', JSON.stringify(this.profile));
        } catch (e) {
            console.warn('[ProfileManager] Failed to save profile:', e);
        }
    }

    loadUsage() {
        try {
            const raw = localStorage.getItem('crump_usage_v2');
            if (!raw) return this.getDefaultUsage();
            return JSON.parse(raw);
        } catch (e) {
            console.warn('[ProfileManager] Failed to load usage:', e);
            return this.getDefaultUsage();
        }
    }

    saveUsage() {
        try {
            localStorage.setItem('crump_usage_v2', JSON.stringify(this.usage));
        } catch (e) {
            console.warn('[ProfileManager] Failed to save usage:', e);
        }
    }

    initializeProfile() {
        if (!this.profile.tier) this.profile.tier = 'free';
        if (!this.profile.created) this.profile.created = Date.now();
        if (!this.profile.name) this.profile.name = 'User';
        if (!this.profile.initial) this.profile.initial = 'U';
        if (!this.profile.billingPeriod) this.profile.billingPeriod = 'monthly';
        this.saveProfile();
    }

    // ========== TRIAL LOGIC (LOCAL VIEW) ==========

    isInTrial() {
        if (!this.profile.trialEndsAt) return false;

        const end = new Date(this.profile.trialEndsAt);
        if (Number.isNaN(end.getTime())) return false;

        return new Date() < end;
    }

    /**
     * Sync subscription + trial from backend user object
     * Called from auth-ui.js after login / session check
     */
    applyServerSubscription(user) {
        if (!user) return;

        const subscriptionTier =
            user.subscriptionTier || user.subscription_tier || null;
        const subscriptionStatus =
            user.subscriptionStatus || user.subscription_status || null;

        const createdAt = user.createdAt || user.created_at || null;

        // Store raw server info for debugging / future use
        this.profile.serverSubscription = {
            tier: subscriptionTier,
            status: subscriptionStatus,
            createdAt
        };

        let trialEndsAt = null;
        let isTrial = false;

        if (user.trial && typeof user.trial === 'object') {
            // Prefer explicit trial info from /api/auth/check-session
            isTrial = !!user.trial.inTrial;
            trialEndsAt = user.trial.trialEndsAt || null;
        } else if (createdAt) {
            // Fallback: compute from createdAt if needed
            const createdDate = new Date(createdAt);
            if (!Number.isNaN(createdDate.getTime())) {
                const end = new Date(createdDate.getTime() + 7 * 24 * 60 * 60 * 1000);
                trialEndsAt = end.toISOString();
                if (new Date() < end) {
                    isTrial = true;
                }
            }
        }

        this.profile.trialEndsAt = trialEndsAt;
        this.profile.isTrial = isTrial;

        if (isTrial && (!subscriptionTier || subscriptionTier === 'free')) {
            // Treat global 7-day trial as Pro tier locally
            this.profile.tier = 'pro';
        } else {
            // No trial or trial over – fall back to subscription tier or free
            if (subscriptionTier && subscriptionTier !== 'free') {
                // Map backend "professional" to frontend "pro"
                if (subscriptionTier === 'professional') {
                    this.profile.tier = 'pro';
                } else {
                    this.profile.tier = subscriptionTier;
                }
            } else {
                this.profile.tier = this.profile.tier || 'free';
            }
        }

        this.saveProfile();

        console.log('[ProfileManager] Synced subscription from server:', {
            tier: this.profile.tier,
            isTrial: this.profile.isTrial,
            trialEndsAt: this.profile.trialEndsAt
        });
    }

    // ========== TIER INFO ==========

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
            price: tierData.price,
            isTrial: this.isInTrial(),
            trialEndsAt: this.profile.trialEndsAt || null
        };
    }

    getProfile() {
    return {
        ...this.profile,
        tierInfo: this.getTierInfo()
    };
}

// Update user profile information
updateProfile(updates) {
    if (!updates || typeof updates !== 'object') return;
    
    // Update profile fields
    if (updates.name) this.profile.name = updates.name;
    if (updates.email !== undefined) this.profile.email = updates.email;
    if (updates.initial) this.profile.initial = updates.initial;
    
    this.saveProfile();
    
    console.log('[ProfileManager] Profile updated:', updates);
}

// ========== TIER CHANGES ==========

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

    // ========== LIMIT ENFORCEMENT ==========

    checkLimit(type) {
        const tierInfo = this.getTierInfo();
        const limit = tierInfo.limits[type];

        if (limit === -1) return { allowed: true };
        if (limit === 0) {
            return {
                allowed: false,
                message: `${type} not available on current plan`,
                action: 'upgrade'
            };
        }

        this.ensureCurrentMonth();
        const used = this.usage[type] || 0;

        if (used >= limit) {
            return {
                allowed: false,
                message: `Monthly ${type} limit reached (${limit}/${limit})`,
                action: 'upgrade'
            };
        }

        const percentUsed = (used / limit) * 100;
        const warning = percentUsed >= 90
            ? `${limit - used} ${type} remaining this month`
            : null;

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

    // ========== USAGE STORAGE ==========

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
