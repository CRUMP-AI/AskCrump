// ==========================================
// CRUMP AI - PROFILE MANAGER v1.0
// Unlimited usage - no tier restrictions
// ==========================================
class UserProfileManager {
constructor() {
this.profile = this.loadProfile();
this.usage = this.loadUsage();
this.initializeProfile();
console.log('👤 ProfileManager v1.0 initialized (unlimited)');
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

// Profile Management
updateProfile(updates) {
    if (updates.name !== undefined) {
        if (typeof updates.name === 'string' && updates.name.length > 0) {
            this.profile.name = updates.name.trim();
        }
    }
    
    if (updates.email !== undefined) {
        if (updates.email === '' || this.validateEmail(updates.email)) {
            this.profile.email = updates.email.trim();
        }
    }
    
    if (updates.initial !== undefined) {
        if (typeof updates.initial === 'string' && updates.initial.length === 1) {
            this.profile.initial = updates.initial.toUpperCase();
        }
    }
    
    if (updates.assistantName !== undefined) {
        if (typeof updates.assistantName === 'string' && updates.assistantName.length > 0) {
            this.profile.assistantName = updates.assistantName.trim();
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

// Usage Tracking (no limits enforced)
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
    const usage = this.getUsage();
    
    return {
        messages: usage.messages || 0,
        images: usage.images || 0,
        searches: usage.searches || 0
    };
}

// NO LIMITS - Always return allowed
canSendMessage() {
    return { allowed: true };
}

canGenerateImage() {
    return { allowed: true };
}

canSearchWeb() {
    return { allowed: true };
}

canUseAPI(apiName) {
    return { allowed: true };
}

// Month Management
ensureCurrentMonth() {
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    
    if (this.usage.month !== currentMonth) {
        console.log(`📅 New month: ${currentMonth}`);
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
}

// Persistence
loadProfile() {
    const saved = localStorage.getItem('crump_user_profile');
    if (saved) {
        try {
            return JSON.parse(saved);
        } catch (e) {
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
// Export
window.UserProfileManager = UserProfileManager;
window.ProfileManager = UserProfileManager;
console.log('✅ ProfileManager v1.0 loaded - Unlimited usage');
