// ==========================================
// CRUMP AI - PROFESSIONAL UPGRADE UI v2.0
// Minimalist design, no emojis
// ==========================================

function showUpgradePrompt() {
    const existing = document.querySelector('.upgrade-modal');
    if (existing) existing.remove();
    
    const tierInfo = window.profileManager?.getTierInfo() || { current: 'free', billingPeriod: 'monthly' };
    
    const modal = document.createElement('div');
    modal.className = 'upgrade-modal';
    modal.innerHTML = `
        <div class="upgrade-overlay" onclick="this.parentElement.remove()"></div>
        <div class="upgrade-content">
            <button class="upgrade-close" onclick="this.closest('.upgrade-modal').remove()">×</button>
            
            <div class="upgrade-header">
                <h2>Upgrade Your Plan</h2>
                <p>Choose the plan that fits your needs</p>
            </div>
            
            <div class="billing-toggle-container">
                <div class="billing-toggle">
                    <button class="billing-option ${tierInfo.billingPeriod === 'monthly' ? 'active' : ''}" 
                            onclick="switchBillingView('monthly')">Monthly</button>
                    <button class="billing-option ${tierInfo.billingPeriod === 'annual' ? 'active' : ''}" 
                            onclick="switchBillingView('annual')">Annual <span class="save-badge">SAVE 20%</span></button>
                </div>
            </div>
            
            <div class="tier-comparison" id="tierComparison">
                ${generateTierCards(tierInfo.current, tierInfo.billingPeriod)}
            </div>
            
            <div class="upgrade-footer">
                <p>All plans include access to the N² Engine</p>
                <p>Cancel anytime • No hidden fees • Instant activation</p>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('active'), 10);
}

function generateTierCards(currentTier, billingPeriod) {
    const tiers = [
        { 
            id: 'free', 
            name: 'Free', 
            monthly: 0, 
            annual: 0, 
            features: [
                '10 messages/month',
                '3 images/month',
                '5 searches/month',
                'Basic features'
            ] 
        },
        { 
            id: 'pro', 
            name: 'Professional', 
            monthly: 20,
            annual: 192,
            features: [
                '1,000 messages/month', 
                '100 images/month', 
                '200 searches/month', 
                'Extended features', 
                'Autonomous messaging'
            ], 
            popular: true 
        },
        { 
            id: 'premium', 
            name: 'Premium', 
            monthly: 50,
            annual: 480,
            features: [
                'Unlimited messages', 
                '500 images/month', 
                'Unlimited searches', 
                'Full API access', 
                'Priority support'
            ] 
        }
    ];
    
    return tiers.map(tier => {
        const price = billingPeriod === 'annual' ? (tier.annual / 12).toFixed(2) : tier.monthly.toFixed(2);
        const totalAnnual = tier.monthly * 12;
        const savings = billingPeriod === 'annual' && tier.monthly > 0 ? (totalAnnual - tier.annual).toFixed(2) : 0;
        
        return `
            <div class="tier-card-premium ${tier.popular ? 'tier-featured' : ''} ${currentTier === tier.id ? 'tier-current' : ''}">
                ${tier.popular ? '<div class="tier-badge-popular">MOST POPULAR</div>' : ''}
                
                <div class="tier-card-header">
                    <h3 class="tier-name">${tier.name}</h3>
                    ${currentTier === tier.id ? '<div class="tier-badge-current">Current Plan</div>' : ''}
                </div>
                
                <div class="tier-price-section">
                    ${tier.monthly === 0 ? `
                        <div class="tier-price-free">
                            <span class="price-main">Free</span>
                            <span class="price-sub">Forever</span>
                        </div>
                    ` : `
                        <div class="tier-price-paid">
                            <span class="price-currency">$</span>
                            <span class="price-main">${price}</span>
                            <span class="price-period">/mo</span>
                        </div>
                        ${savings > 0 ? `<div class="price-savings">Save $${savings}/year</div>` : ''}
                        ${billingPeriod === 'annual' && tier.monthly > 0 ? `<div class="price-detail">Billed ${tier.annual > 0 ? '$' + tier.annual : ''} annually</div>` : ''}
                    `}
                </div>
                
                <ul class="tier-features-list">
                    ${tier.features.map(feature => `
                        <li class="tier-feature-item">
                            <svg class="feature-check" width="20" height="20" viewBox="0 0 24 24" fill="none">
                                <path d="M20 6L9 17L4 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                            <span>${feature}</span>
                        </li>
                    `).join('')}
                </ul>
                
                <div class="tier-card-footer">
                    ${renderButtonPremium(tier.id, currentTier, billingPeriod)}
                </div>
            </div>
        `;
    }).join('');
}

function renderButtonPremium(tier, currentTier, billing) {
    if (tier === 'free') {
        return `<button class="tier-btn tier-btn-disabled" disabled>Free Plan</button>`;
    }
    
    if (tier === currentTier) {
        return `<button class="tier-btn tier-btn-current" disabled>Current Plan</button>`;
    }
    
    return `<button class="tier-btn tier-btn-upgrade" onclick="initiateCheckout('${tier}', '${billing}')">
        Upgrade Now
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
    </button>`;
}

function renderButton(tier, currentTier, billing) {
    if (tier === currentTier) return '<button class="tier-button disabled">Current Plan</button>';
    if (tier === 'free') return '<button class="tier-button secondary" onclick="downgradePlan()">Downgrade</button>';
    return `<button class="tier-button primary" onclick="upgradePlan('${tier}', '${billing}')">Upgrade to ${tier === 'pro' ? 'Pro' : 'Premium'}</button>`;
}

function switchBillingView(period) {
    document.querySelectorAll('.billing-option').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.toLowerCase().includes(period));
    });
    const current = window.profileManager?.getTier() || 'free';
    document.getElementById('tierComparison').innerHTML = generateTierCards(current, period);
}

function upgradePlan(tier, billing) {
    // Map tier names to proper format
    const tierMap = {
        'pro': 'professional',
        'professional': 'professional',
        'premium': 'enterprise',
        'enterprise': 'enterprise'
    };

    const normalizedTier = tierMap[tier.toLowerCase()] || 'professional';

    // Show loading state
    const button = event.target;
    if (button) {
        button.disabled = true;
        button.textContent = 'Loading...';
    }

    // 🔑 Send the same auth token used elsewhere so verifyAuth can see you
    const headers = {
        'Content-Type': 'application/json'
    };

    fetch('/api/stripe/create-checkout-session', {
        method: 'POST',
        headers,
        credentials: 'include', // send auth cookies
        body: JSON.stringify({
            tier: normalizedTier,
            billingPeriod: billing || 'monthly'
        })

    })
        .then(response => response.json())
        .then(data => {
            if (data.success && data.url) {
                // Go to Stripe checkout
                window.location.href = data.url;
            } else {
                throw new Error(data.error || 'Failed to create checkout session');
            }
        })
        .catch(error => {
            console.error('Checkout error:', error);
            showNotification(error.message || 'Failed to start checkout', 'error');
            if (button) {
                button.disabled = false;
                button.textContent = `Upgrade to ${tier}`;
            }
        });
}

function downgradePlan() {
    if (!confirm('Are you sure you want to cancel your subscription? Your benefits will continue until the end of your billing period.')) {
        return;
    }
    
    // Open Stripe customer portal for subscription management
    // Authentication is handled via cookies on the server
    fetch('/api/stripe/customer-portal', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.url) {
            window.location.href = data.url;
        } else {
            throw new Error(data.error || 'Failed to open customer portal');
        }
    })
    .catch(error => {
        console.error('Customer portal error:', error);
        showNotification(error.message || 'Failed to open subscription management', 'error');
    });
}

function manageSubscription() {
    // Open Stripe customer portal
    // Authentication is handled via cookies on the server
    fetch('/api/stripe/customer-portal', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.url) {
            window.location.href = data.url;
        } else {
            throw new Error(data.error || 'Failed to open customer portal');
        }
    })
    .catch(error => {
        console.error('Customer portal error:', error);
        showNotification(error.message || 'Failed to open subscription management', 'error');
    });
}

function showUsageStats() {
    if (!window.profileManager) return;
    
    const stats = window.profileManager.getUsageStats();
    const tierInfo = window.profileManager.getTierInfo();
    
    const modal = document.createElement('div');
    modal.className = 'usage-stats-modal active';
    modal.innerHTML = `
        <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
        <div class="modal-content">
            <button class="modal-close" onclick="this.closest('.usage-stats-modal').remove()">×</button>
            <h2>Usage Statistics</h2>
            <div class="tier-badge">${tierInfo.name}</div>
            <div class="stats-grid">
                ${Object.entries(stats).map(([key, data]) => `
                    <div class="stat-card">
                        <div class="stat-label">${key}</div>
                        <div class="stat-bar">
                            <div class="stat-fill ${(data.used/data.limit)*100 > 90 ? 'warning' : ''}" 
                                 style="width: ${data.limit === -1 ? 100 : Math.min(100, (data.used/data.limit)*100)}%"></div>
                        </div>
                        <div class="stat-numbers">
                            <span>${data.used}</span> / <span>${data.limit === -1 ? 'Unlimited' : data.limit}</span>
                        </div>
                    </div>
                `).join('')}
            </div>
            ${needsUpgrade(stats) ? '<button class="btn-primary" onclick="showUpgradePrompt()">Upgrade Plan</button>' : ''}
        </div>
    `;
    document.body.appendChild(modal);
}

function needsUpgrade(stats) {
    return Object.values(stats).some(s => s.limit !== -1 && (s.used / s.limit) >= 0.9);
}

function showNotification(msg, type) {
    const toast = document.createElement('div');
    toast.className = `notification ${type}`;
    toast.textContent = msg;
    toast.style.cssText = `position:fixed;top:20px;right:20px;padding:14px 24px;background:${type==='success'?'#10b981':type==='error'?'#ef4444':'#3b82f6'};color:white;border-radius:8px;z-index:10001;`;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

window.showUpgradePrompt = showUpgradePrompt;
window.showUsageStats = showUsageStats;
window.switchBillingView = switchBillingView;
window.manageSubscription = manageSubscription;

// Handle Stripe checkout success/cancel redirects
window.addEventListener('load', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const upgrade = urlParams.get('upgrade');
    const tier = urlParams.get('tier');
    
    if (upgrade === 'success' && tier) {
        // Clean URL
        window.history.replaceState({}, document.title, window.location.pathname);
        
        showNotification(`Successfully upgraded to ${tier}! 🎉`, 'success');
        
        // Reload user data after short delay
        setTimeout(() => {
            if (typeof window.checkSession === 'function') {
                window.checkSession();
            } else {
                location.reload();
            }
        }, 2000);
    } else if (upgrade === 'cancelled') {
        window.history.replaceState({}, document.title, window.location.pathname);
        showNotification('Upgrade cancelled', 'info');
    } else if (urlParams.get('portal') === 'returned') {
        window.history.replaceState({}, document.title, window.location.pathname);
        
        // Reload user data
        if (typeof window.checkSession === 'function') {
            window.checkSession();
        } else {
            location.reload();
        }
    }
});

console.log('[UpgradeUI] Professional system ready with Stripe integration');
