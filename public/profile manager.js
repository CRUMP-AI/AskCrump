// ==========================================
// CRUMP AI - USER PROFILE MANAGER v2.12.0
// Tier management, usage tracking, limits
// ==========================================

class UserProfileManager {
    constructor() {
        this.profile = this.loadProfile();
        this.TIER_LIMITS = {
            free: {
                messagesPerMonth: 100,
                imagesPerMonth: 10,
                searchesPerMonth: 20,
                maxChatHistory: 10,
                fileUploads: true,
                voiceEnabled: true,
                pdfAnalysis: true
            },
            pro: {
                messagesPerMonth: 1000,
                imagesPerMonth: 100,
                searchesPerMonth: 200,
                maxChatHistory: 50,
                fileUploads: true,
                voiceEnabled: true,
                pdfAnalysis: true
            },
            premium: {
                messagesPerMonth: -1,  // unlimited
                imagesPerMonth: 500,
                searchesPerMonth: -1,  // unlimited
                maxChatHistory: -1,    // unlimited
                fileUploads: true,
                voiceEnabled: true,
                pdfAnalysis: true
            }
        };
    }
    
    loadProfile() {
        const stored = localStorage.getItem('crump_user_profile');
        if (stored) {
            try {
                const profile = JSON.parse(stored);
                // Check if month has passed, reset usage
                if (this.shouldResetUsage(profile.usage.lastReset)) {
                    console.log('📅 New month detected - resetting usage counters');
                    profile.usage = this.resetUsage();
                    this.saveProfile(profile);
                }
                return profile;
            } catch (e) {
                console.error('Error loading profile, creating new:', e);
                return this.createNewProfile();
            }
        }
        
        // Create new profile
        return this.createNewProfile();
    }
    
    createNewProfile() {
        const profile = {
            userId: this.generateUUID(),
            createdAt: Date.now(),
            tier: 'free',
            name: localStorage.getItem('crump_user_name') || '',
            email: '',
            initial: localStorage.getItem('crump_user_initial') || 'U',
            avatar: null,
            usage: this.resetUsage(),
            limits: { ...this.TIER_LIMITS.free },
            preferences: this.loadPreferences(),
            subscription: {
                status: 'inactive',
                plan: 'free',
                startDate: null,
                endDate: null,
                stripeCustomerId: null,
                stripeSubscriptionId: null
            }
        };
        
        console.log('✨ Created new user profile:', profile.userId);
        this.saveProfile(profile);
        return profile;
    }
    
    resetUsage() {
        return {
            messagesThisMonth: 0,
            imagesThisMonth: 0,
            searchesThisMonth: 0,
            lastReset: Date.now()
        };
    }
    
    shouldResetUsage(lastReset) {
        const now = new Date();
        const last = new Date(lastReset);
        return now.getMonth() !== last.getMonth() || now.getFullYear() !== last.getFullYear();
    }
    
    // ==========================================
    // USAGE LIMIT CHECKS
    // ==========================================
    
    canSendMessage() {
        const limit = this.profile.limits.messagesPerMonth;
        if (limit === -1) return { allowed: true }; // unlimited
        
        const used = this.profile.usage.messagesThisMonth;
        const remaining = limit - used;
        
        if (remaining <= 0) {
            return {
                allowed: false,
                reason: 'monthly_limit',
                message: `🚫 **Monthly Message Limit Reached**\n\nYou've used all ${limit} messages this month.\n\n**Upgrade to Pro:**\n• 1,000 messages/month\n• 100 images/month\n• Priority support\n\nOnly $9.99/month!`,
                action: 'upgrade'
            };
        }
        
        // Warn at 90%
        if (remaining <= limit * 0.1) {
            return {
                allowed: true,
                warning: `⚠️ Only ${remaining} messages left this month. Consider upgrading to Pro!`
            };
        }
        
        return { allowed: true };
    }
    
    canGenerateImage() {
        const limit = this.profile.limits.imagesPerMonth;
        if (limit === -1) return { allowed: true };
        
        const used = this.profile.usage.imagesThisMonth;
        const remaining = limit - used;
        
        if (remaining <= 0) {
            return {
                allowed: false,
                reason: 'monthly_limit',
                message: `🚫 **Monthly Image Limit Reached**\n\nYou've generated all ${limit} images this month.\n\n**Upgrade to Pro:**\n• 100 images/month\n• Better image quality\n• Faster generation\n\nOnly $9.99/month!`,
                action: 'upgrade'
            };
        }
        
        if (remaining <= 2) {
            return {
                allowed: true,
                warning: `⚠️ Only ${remaining} images left this month!`
            };
        }
        
        return { allowed: true };
    }
    
    canSearch() {
        const limit = this.profile.limits.searchesPerMonth;
        if (limit === -1) return { allowed: true };
        
        const used = this.profile.usage.searchesThisMonth;
        const remaining = limit - used;
        
        if (remaining <= 0) {
            return {
                allowed: false,
                reason: 'monthly_limit',
                message: `🚫 **Monthly Search Limit Reached**\n\nYou've used all ${limit} web searches this month.\n\n**Upgrade to Pro:**\n• 200 searches/month\n• Better search results\n\nOnly $9.99/month!`,
                action: 'upgrade'
            };
        }
        
        return { allowed: true };
    }
    
    canUploadFile() {
        return {
            allowed: this.profile.limits.fileUploads,
            message: !this.profile.limits.fileUploads 
                ? 'File uploads are available on Pro and Premium plans.'
                : null
        };
    }
    
    canUsePDFAnalysis() {
        return {
            allowed: this.profile.limits.pdfAnalysis,
            message: !this.profile.limits.pdfAnalysis
                ? 'PDF analysis is available on Pro and Premium plans.'
                : null
        };
    }
    
    // ==========================================
    // INCREMENT USAGE
    // ==========================================
    
    incrementMessageUsage() {
        this.profile.usage.messagesThisMonth++;
        this.saveProfile();
    }
    
    incrementImageUsage() {
        this.profile.usage.imagesThisMonth++;
        this.saveProfile();
    }
    
    incrementSearchUsage() {
        this.profile.usage.searchesThisMonth++;
        this.saveProfile();
    }
    
    // ==========================================
    // TIER MANAGEMENT
    // ==========================================
    
    upgradeTier(newTier, subscriptionData = null) {
        if (!['free', 'pro', 'premium'].includes(newTier)) {
            throw new Error('Invalid tier: ' + newTier);
        }
        
        console.log(`⬆️ Upgrading from ${this.profile.tier} to ${newTier}`);
        
        this.profile.tier = newTier;
        this.profile.limits = { ...this.TIER_LIMITS[newTier] };
        this.profile.subscription.plan = newTier;
        this.profile.subscription.status = newTier === 'free' ? 'inactive' : 'active';
        
        if (subscriptionData) {
            this.profile.subscription.startDate = subscriptionData.startDate || Date.now();
            this.profile.subscription.endDate = subscriptionData.endDate;
            this.profile.subscription.stripeCustomerId = subscriptionData.stripeCustomerId;
            this.profile.subscription.stripeSubscriptionId = subscriptionData.stripeSubscriptionId;
        }
        
        this.saveProfile();
        console.log(`✅ Upgraded to ${newTier}`);
        
        return this.profile;
    }
    
    downgradeTier(reason = 'user_request') {
        console.log(`⬇️ Downgrading to free tier. Reason: ${reason}`);
        
        this.profile.tier = 'free';
        this.profile.limits = { ...this.TIER_LIMITS.free };
        this.profile.subscription.plan = 'free';
        this.profile.subscription.status = 'cancelled';
        
        this.saveProfile();
        return this.profile;
    }
    
    // ==========================================
    // PROFILE MANAGEMENT
    // ==========================================
    
    updateProfile(updates) {
        if (updates.name !== undefined) this.profile.name = updates.name;
        if (updates.email !== undefined) this.profile.email = updates.email;
        if (updates.initial !== undefined) this.profile.initial = updates.initial;
        if (updates.avatar !== undefined) this.profile.avatar = updates.avatar;
        
        this.saveProfile();
        console.log('✏️ Profile updated');
    }
    
    updatePreferences(preferences) {
        this.profile.preferences = {
            ...this.profile.preferences,
            ...preferences
        };
        this.saveProfile();
    }
    
    // ==========================================
    // PERSISTENCE
    // ==========================================
    
    saveProfile(profile = this.profile) {
        try {
            localStorage.setItem('crump_user_profile', JSON.stringify(profile));
            this.profile = profile;
        } catch (e) {
            console.error('Error saving profile:', e);
        }
    }
    
    loadPreferences() {
        try {
            return {
                workMode: localStorage.getItem('crump_work_mode') || 'companion',
                voiceOutput: localStorage.getItem('voiceOutput') === 'true',
                autoVoice: localStorage.getItem('autoVoice') === 'true',
                fontStyle: localStorage.getItem('fontStyle') || 'modern',
                bgColor: localStorage.getItem('bgColor') || '#0a1628',
                assistantName: this.getAssistantName()
            };
        } catch (e) {
            console.error('Error loading preferences:', e);
            return {};
        }
    }
    
    getAssistantName() {
        try {
            const memory = localStorage.getItem('crump_universal_memory');
            if (memory) {
                const parsed = JSON.parse(memory);
                return parsed.userProfile?.assistantName || 'Crump';
            }
        } catch (e) {
            // Ignore
        }
        return 'Crump';
    }
    
    // ==========================================
    // UTILITY
    // ==========================================
    
    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }
    
    // ==========================================
    // UI HELPERS
    // ==========================================
    
    getUsageStats() {
        const stats = [];
        const limits = this.profile.limits;
        const usage = this.profile.usage;
        
        if (limits.messagesPerMonth !== -1) {
            stats.push({
                label: 'Messages',
                icon: '💬',
                used: usage.messagesThisMonth,
                limit: limits.messagesPerMonth,
                percentage: Math.min((usage.messagesThisMonth / limits.messagesPerMonth) * 100, 100)
            });
        } else {
            stats.push({
                label: 'Messages',
                icon: '💬',
                used: usage.messagesThisMonth,
                limit: 'Unlimited',
                percentage: 0,
                unlimited: true
            });
        }
        
        if (limits.imagesPerMonth !== -1) {
            stats.push({
                label: 'Images',
                icon: '🎨',
                used: usage.imagesThisMonth,
                limit: limits.imagesPerMonth,
                percentage: Math.min((usage.imagesThisMonth / limits.imagesPerMonth) * 100, 100)
            });
        }
        
        if (limits.searchesPerMonth !== -1) {
            stats.push({
                label: 'Searches',
                icon: '🔍',
                used: usage.searchesThisMonth,
                limit: limits.searchesPerMonth,
                percentage: Math.min((usage.searchesThisMonth / limits.searchesPerMonth) * 100, 100)
            });
        } else if (this.profile.tier !== 'free') {
            stats.push({
                label: 'Searches',
                icon: '🔍',
                used: usage.searchesThisMonth,
                limit: 'Unlimited',
                percentage: 0,
                unlimited: true
            });
        }
        
        return stats;
    }
    
    getTierInfo() {
        return {
            current: this.profile.tier,
            icon: this.profile.tier === 'premium' ? '👑' : this.profile.tier === 'pro' ? '⭐' : '🆓',
            name: this.profile.tier.toUpperCase(),
            limits: this.profile.limits,
            subscription: this.profile.subscription
        };
    }
    
    getProfile() {
        return { ...this.profile };
    }
    
    // ==========================================
    // DEBUG
    // ==========================================
    
    debug() {
        console.log('🔍 USER PROFILE DEBUG:');
        console.log('Tier:', this.profile.tier);
        console.log('Usage:', this.profile.usage);
        console.log('Limits:', this.profile.limits);
        console.log('Subscription:', this.profile.subscription);
    }
}

// Export to window
window.UserProfileManager = UserProfileManager;

console.log('✅ UserProfileManager loaded');
