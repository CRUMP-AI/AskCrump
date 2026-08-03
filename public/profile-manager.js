(() => {
  'use strict';
  const BASE_KEY = 'crump_user_profile_v4';
  const key = () => `${BASE_KEY}:${window.currentUser?.id || 'anonymous'}`;

  class ProfileManager {
    constructor() {
      this.profile = this.load();
    }

    load() {
      try {
        const cached = JSON.parse(localStorage.getItem(key()) || '{}');
        return {
          name: cached.name || '',
          email: cached.email || '',
          initial: cached.initial || 'U',
          tier: cached.tier || 'free',
          subscriptionStatus: cached.subscriptionStatus || 'inactive',
        };
      } catch (_) {
        return { name: '', email: '', initial: 'U', tier: 'free', subscriptionStatus: 'inactive' };
      }
    }

    saveProfile() {
      try { localStorage.setItem(key(), JSON.stringify(this.profile)); } catch (_) {}
    }

    getProfile() {
      return { ...this.profile };
    }

    updateProfile(values = {}) {
      this.profile = {
        ...this.profile,
        ...values,
        initial: values.initial || values.name?.trim()?.charAt(0)?.toUpperCase() || this.profile.initial || 'U',
      };
      this.saveProfile();
      return this.getProfile();
    }

    applyServerSubscription(user = {}) {
      const tier = user.subscriptionTier || user.tier || 'free';
      this.updateProfile({
        name: user.fullName || this.profile.name,
        email: user.email || this.profile.email,
        tier: tier === 'professional' ? 'pro' : tier === 'enterprise' ? 'premium' : tier,
        subscriptionStatus: user.subscriptionStatus || 'inactive',
      });
    }

    getTier() {
      return this.profile.tier || 'free';
    }

    getTierInfo() {
      return { current: this.getTier(), billingPeriod: 'monthly' };
    }

    // The Python API is authoritative for usage. Never block a message using stale device data.
    canSendMessage() {
      return { allowed: true };
    }

    incrementUsage() {}
  }

  window.ProfileManager = ProfileManager;
  window.UserProfileManager = ProfileManager;
})();
