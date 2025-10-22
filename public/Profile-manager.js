// ==========================================
// CRUMP AI - USER PROFILE MANAGER v2.12.1
// Tier management, usage tracking, and limits
// ==========================================

class UserProfileManager {
    constructor() {
        this.profile = this.loadProfile();
        this.usage = this.loadUsage();
        this.tiers = {
            free: {
                name: 'Free',
                icon: '🆓',
                limits: {
                    messages: 100,
                    images: 10,
                    searches: 20
                },
                features: ['Basic chat', 'File uploads', 'Voice I/O']
            },
            pro: {
                name: 'Pro',
                icon: '⭐',
                limits: {
                    messages: 1000,
                    images: 100,
                    searches: 200
                },
                features: ['Everything in Free', 'Multi-file uploads', 'PDF analysis', 'Priority responses', 'Advanced memory']
            },
            premium: {
                name: 'Premium',
                icon: '👑',
                limits: {
                    messages: -1, // Unlimited
                    images: 500,
                    searches: -1  // Unlimited
                },
                features: ['Everything in Pro', 'Unlimited messages & searches', 'Extended memory', 'Custom themes', 'API access', 'Priority support']
            }
        };
        
        this.initializeProfile();
        console.log('👤 ProfileManager initialized:', this.getTierInfo());
    }
    
    initializeProfile() {
        if (!this.profile.tier) {
            this.profile.tier = 'free';
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
        // VALIDATION FIX: Proper input validation
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
            // Validate avatar is a data URL or null
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
    
    getTierInfo() {
        const tier = this.getTier();
        const tierData = this.tiers[tier];
        
        return {
            current: tier,
            name: tierData.name,
            icon: tierData.icon,
            limits: tierData.limits,
            features: tierData.features
        };
    }
    
    upgradeTier(newTier) {
        if (!this.tiers[newTier]) {
            throw new Error('Invalid tier');
        }
        
        this.profile.tier = newTier;
        this.profile.upgraded = Date.now();
        this.saveProfile();
        
        console.log(`✨ Upgraded to ${newTier}`);
        return true;
    }
    
    downgradeTier(reason = 'user_request') {
        this.profile.tier = 'free';
        this.profile.downgraded = Date.now();
        this.profile.downgradeReason = reason;
        this.saveProfile();
        
        console.log('📉 Downgraded to free tier');
        return true;
    }
    
    // ==========================================
    // USAGE TRACKING
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
    
    getUsage() {
        this.ensureCurrentMonth();
        return { ...this.usage };
    }
    
    getUsageStats() {
        const tier = this.getTier();
        const limits = this.tiers[tier].limits;
        const usage = this.getUsage();
        
        const stats = [
            {
                label: 'Messages',
                icon: '💬',
                used: usage.messages,
                limit: limits.messages,
                unlimited: limits.messages === -1,
                percentage: limits.messages === -1 ? 0 : Math.min(100, (usage.messages / limits.messages) * 100)
            },
            {
                label: 'Images Generated',
                icon: '🎨',
                used: usage.images,
                limit: limits.images,
                unlimited: limits.images === -1,
                percentage: limits.images === -1 ? 0 : Math.min(100, (usage.images / limits.images) * 100)
            },
            {
                label: 'Web Searches',
                icon: '🔍',
                used: usage.searches,
                limit: limits.searches,
                unlimited: limits.searches === -1,
                percentage: limits.searches === -1 ? 0 : Math.min(100, (usage.searches / limits.searches) * 100)
            }
        ];
        
        return stats;
    }
    
    // ==========================================
    // LIMIT CHECKING
    // ==========================================
    
    canSendMessage() {
        const tier = this.getTier();
        const limits = this.tiers[tier].limits;
        const usage = this.getUsage();
        
        // Unlimited
        if (limits.messages === -1) {
            return { allowed: true };
        }
        
        // Check limit
        if (usage.messages >= limits.messages) {
            return {
                allowed: false,
                action: 'upgrade',
                message: `🚫 **Message Limit Reached**\n\nYou've used all ${limits.messages} messages this month.\n\n**Upgrade to Pro** for 1,000 messages/month or **Premium** for unlimited!`
            };
        }
        
        // Warning at 90%
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
        
        // Unlimited
        if (limits.images === -1) {
            return { allowed: true };
        }
        
        // Check limit
        if (usage.images >= limits.images) {
            return {
                allowed: false,
                action: 'upgrade',
                message: `🚫 **Image Limit Reached**\n\nYou've used all ${limits.images} images this month.\n\n**Upgrade to Pro** for 100 images/month or **Premium** for 500 images/month!`
            };
        }
        
        // Warning at 90%
        const percentage = (usage.images / limits.images) * 100;
        if (percentage >= 90) {
            return {
                allowed: true,
                warning: `⚠️ ${limits.images - usage.images} images remaining this month`
            };
        }
        
        return { allowed: true };
    }
    
    canSearchWeb() {
        const tier = this.getTier();
        const limits = this.tiers[tier].limits;
        const usage = this.getUsage();
        
        // Unlimited
        if (limits.searches === -1) {
            return { allowed: true };
        }
        
        // Check limit
        if (usage.searches >= limits.searches) {
            return {
                allowed: false,
                action: 'upgrade',
                message: `🚫 **Search Limit Reached**\n\nYou've used all ${limits.searches} searches this month.\n\nUpgrade for more!`
            };
        }
        
        // Warning at 90%
        const percentage = (usage.searches / limits.searches) * 100;
        if (percentage >= 90) {
            return {
                allowed: true,
                warning: `⚠️ ${limits.searches - usage.searches} searches remaining this month`
            };
        }
        
        return { allowed: true };
    }
    
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
            resetAt: Date.now()
        };
    }
}

// ==========================================
// EXPORT
// ==========================================
window.UserProfileManager = UserProfileManager;

console.log('✅ ProfileManager v2.12.1 loaded - Validation fixes applied');
