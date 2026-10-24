(() => {
  'use strict';
  const BASE_KEY = 'crump_user_profile_v4';
  const ownerId = value => String(value || '').trim();
  const key = value => `${BASE_KEY}:${ownerId(value)}`;
  const emptyProfile = () => ({
    name: '',
    email: '',
    initial: 'U',
    tier: 'free',
    subscriptionStatus: 'inactive',
  });

  class ProfileManager {
    constructor(initialOwnerId = window.currentUser?.id) {
      this.ownerId = '';
      this.profile = emptyProfile();
      this.bindOwner(initialOwnerId);
    }

    load(boundOwnerId = this.ownerId) {
      const resolvedOwnerId = ownerId(boundOwnerId);
      if (!resolvedOwnerId) return emptyProfile();
      try {
        const cached = JSON.parse(localStorage.getItem(key(resolvedOwnerId)) || '{}');
        return {
          name: cached.name || '',
          email: cached.email || '',
          initial: cached.initial || 'U',
          tier: cached.tier || 'free',
          subscriptionStatus: cached.subscriptionStatus || 'inactive',
        };
      } catch (_) {
        return emptyProfile();
      }
    }

    bindOwner(nextOwnerId) {
      const resolvedOwnerId = ownerId(nextOwnerId);
      if (this.ownerId === resolvedOwnerId) return this.getProfile();
      this.ownerId = resolvedOwnerId;
      this.profile = this.load(resolvedOwnerId);
      return this.getProfile();
    }

    scrubOwner() {
      this.ownerId = '';
      this.profile = emptyProfile();
      return this.getProfile();
    }

    isCurrentOwner() {
      const activeOwnerId = ownerId(window.currentUser?.id);
      return Boolean(this.ownerId && activeOwnerId && this.ownerId === activeOwnerId);
    }

    saveProfile() {
      if (!this.isCurrentOwner()) return false;
      try {
        localStorage.setItem(key(this.ownerId), JSON.stringify(this.profile));
        return true;
      } catch (_) {
        return false;
      }
    }

    getProfile() {
      return { ...this.profile };
    }

    updateProfile(values = {}) {
      if (!this.isCurrentOwner()) return this.getProfile();
      this.profile = {
        ...this.profile,
        ...values,
        initial: values.initial || values.name?.trim()?.charAt(0)?.toUpperCase() || this.profile.initial || 'U',
      };
      this.saveProfile();
      return this.getProfile();
    }

    applyServerSubscription(user = {}) {
      const activeOwnerId = ownerId(window.currentUser?.id);
      const suppliedOwnerId = ownerId(user.id);
      if (!activeOwnerId || (suppliedOwnerId && suppliedOwnerId !== activeOwnerId)) {
        return this.getProfile();
      }
      // Rebind before reading any fallback. A retained manager from another
      // same-document session must never supply that account's name or email
      // while writing the new owner's cache.
      this.bindOwner(activeOwnerId);
      const tier = user.subscriptionTier || user.tier || 'free';
      return this.updateProfile({
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
