// ==========================================
// CRUMP AI - UPGRADE PROMPT UI v3.1.0
// Annual/Monthly billing with savings display
// ==========================================

function showUpgradePrompt() {
    // Remove existing modal if any
    const existing = document.querySelector('.upgrade-modal');
    if (existing) existing.remove();
    
    const tierInfo = window.profileManager ? window.profileManager.getTierInfo() : null;
    const currentTier = tierInfo ? tierInfo.current : 'free';
    const currentBilling = tierInfo ? tierInfo.billingPeriod : 'monthly';
    
    const modal = document.createElement('div');
    modal.className = 'upgrade-modal';
    modal.innerHTML = `
        <div class="upgrade-overlay" onclick="this.parentElement.remove()"></div>
        <div class="upgrade-content">
            <button class="upgrade-close" onclick="this.closest('.upgrade-modal').remove()">✕</button>
            
            <div class="upgrade-header">
                <h2>🚀 Upgrade Your Experience</h2>
                <p>Choose the plan that fits your needs</p>
            </div>
            
            <!-- Billing Period Toggle -->
            <div class="billing-toggle-container">
                <div class="billing-toggle">
                    <button class="billing-option ${currentBilling === 'monthly' ? 'active' : ''}" data-period="monthly" onclick="switchBillingView('monthly')">
                        Monthly
                    </button>
                    <button class="billing-option ${currentBilling === 'annual' ? 'active' : ''}" data-period="annual" onclick="switchBillingView('annual')">
                        Annual
                        <span class="save-badge">SAVE 20%</span>
                    </button>
                </div>
                <div class="billing-note">
                    <span id="billingNote">💰 Save up to $60 with annual billing</span>
                </div>
            </div>
            
            <div class="tier-comparison" id="tierComparison">
                <!-- FREE TIER -->
                <div class="tier-card ${currentTier === 'free' ? 'current' : ''}">
                    <div class="tier-header">
                        <div class="tier-icon-large">🆓</div>
                        <h3>Free</h3>
                        ${currentTier === 'free' ? '<div class="current-badge">Current Plan</div>' : ''}
                    </div>
                    
                    <div class="tier-price">
                        <span class="price-amount">$0</span>
                        <span class="price-period">/forever</span>
                    </div>
                    
                    <ul class="tier-features">
                        <li><span class="feature-icon">💬</span> 100 messages/month</li>
                        <li><span class="feature-icon">🎨</span> 10 images/month</li>
                        <li><span class="feature-icon">🔍</span> 20 web searches/month</li>
                        <li><span class="feature-icon">🌤️</span> Weather (20/mo)</li>
                        <li><span class="feature-icon">📰</span> News (20/mo)</li>
                        <li><span class="feature-icon">🏈</span> Sports scores (20/mo)</li>
                        <li><span class="feature-icon">📈</span> Stock quotes (10/mo)</li>
                        <li><span class="feature-icon">🎬</span> Movies/TV (10/mo)</li>
                        <li><span class="feature-icon">📚</span> Wikipedia (unlimited)</li>
                        <li><span class="feature-icon">📖</span> Dictionary (unlimited)</li>
                        <li><span class="feature-icon">😂</span> Jokes & Fun (unlimited)</li>
                    </ul>
                    
                    ${currentTier !== 'free' ? '<button class="tier-button secondary" onclick="downgradePlan(\'free\')">Downgrade</button>' : '<div class="tier-button disabled">Current Plan</div>'}
                </div>
                
                <!-- PRO TIER -->
                <div class="tier-card featured ${currentTier === 'pro' ? 'current' : ''}" id="proTierCard">
                    <div class="popular-badge">MOST POPULAR</div>
                    <div class="tier-header">
                        <div class="tier-icon-large">⭐</div>
                        <h3>Pro</h3>
                        ${currentTier === 'pro' ? '<div class="current-badge">Current Plan</div>' : ''}
                    </div>
                    
                    <div class="tier-price">
                        <span class="price-amount" id="proPrice">$9.99</span>
                        <span class="price-period" id="proPeriod">/month</span>
                        <div class="price-savings" id="proSavings" style="display: none;">
                            <span class="savings-text">Save $24.88/year</span>
                            <span class="monthly-equivalent">Just $7.92/month</span>
                        </div>
                    </div>
                    
                    <ul class="tier-features">
                        <li><span class="feature-icon">💬</span> <strong>1,000 messages/month</strong></li>
                        <li><span class="feature-icon">🎨</span> <strong>100 images/month</strong></li>
                        <li><span class="feature-icon">🔍</span> <strong>200 searches/month</strong></li>
                        <li><span class="feature-icon">🌤️</span> Weather (100/mo)</li>
                        <li><span class="feature-icon">📰</span> News (100/mo)</li>
                        <li><span class="feature-icon">🏈</span> Sports (100/mo)</li>
                        <li><span class="feature-icon">📈</span> Stocks (50/mo)</li>
                        <li><span class="feature-icon">🎬</span> Movies (50/mo)</li>
                        <li><span class="feature-icon">📺</span> YouTube (50/mo)</li>
                        <li><span class="feature-icon">🍳</span> Recipes (50/mo)</li>
                        <li><span class="feature-icon">🌐</span> Translation (100/mo)</li>
                        <li><span class="feature-icon">💻</span> GitHub (50/mo)</li>
                        <li><span class="feature-icon">₿</span> Crypto (100/mo)</li>
                        <li><span class="feature-icon">🎵</span> Spotify (50/mo)</li>
                        <li><span class="feature-icon">🗺️</span> Google Maps (50/mo)</li>
                        <li><span class="feature-icon">⚡</span> Priority responses</li>
                        <li><span class="feature-icon">🎯</span> Advanced memory</li>
                    </ul>
                    
                    ${currentTier !== 'pro' ? '<button class="tier-button primary" onclick="upgradePlan(\'pro\', getCurrentBillingPeriod())">Upgrade to Pro</button>' : '<div class="tier-button disabled">Current Plan</div>'}
                </div>
                
                <!-- PREMIUM TIER -->
                <div class="tier-card ${currentTier === 'premium' ? 'current' : ''}" id="premiumTierCard">
                    <div class="tier-header">
                        <div class="tier-icon-large">👑</div>
                        <h3>Premium</h3>
                        ${currentTier === 'premium' ? '<div class="current-badge">Current Plan</div>' : ''}
                    </div>
                    
                    <div class="tier-price">
                        <span class="price-amount" id="premiumPrice">$24.99</span>
                        <span class="price-period" id="premiumPeriod">/month</span>
                        <div class="price-savings" id="premiumSavings" style="display: none;">
                            <span class="savings-text">Save $60.88/year</span>
                            <span class="monthly-equivalent">Just $19.92/month</span>
                        </div>
                    </div>
                    
                    <ul class="tier-features">
                        <li><span class="feature-icon">💬</span> <strong>∞ Unlimited messages</strong></li>
                        <li><span class="feature-icon">🎨</span> <strong>500 images/month</strong></li>
                        <li><span class="feature-icon">🔍</span> <strong>∞ Unlimited searches</strong></li>
                        <li><span class="feature-icon">✨</span> Everything in Pro</li>
                        <li><span class="feature-icon">📧</span> <strong>Gmail integration</strong></li>
                        <li><span class="feature-icon">📅</span> <strong>Google Calendar</strong></li>
                        <li><span class="feature-icon">📁</span> <strong>Google Drive</strong></li>
                        <li><span class="feature-icon">✈️</span> Flight tracking (500/mo)</li>
                        <li><span class="feature-icon">🏈</span> Real-time sports</li>
                        <li><span class="feature-icon">📈</span> Professional stocks</li>
                        <li><span class="feature-icon">🧠</span> Extended memory</li>
                        <li><span class="feature-icon">🎨</span> Custom themes</li>
                        <li><span class="feature-icon">🔌</span> API access</li>
                        <li><span class="feature-icon">👨‍💻</span> Priority support</li>
                        <li><span class="feature-icon">⚡</span> All APIs unlimited</li>
                    </ul>
                    
                    ${currentTier !== 'premium' ? '<button class="tier-button primary" onclick="upgradePlan(\'premium\', getCurrentBillingPeriod())">Upgrade to Premium</button>' : '<div class="tier-button disabled">Current Plan</div>'}
                </div>
            </div>
            
            <div class="upgrade-footer">
                <p>💳 <strong>Secure payment</strong> powered by Stripe (coming soon)</p>
                <p>🔄 <strong>Cancel anytime</strong> · No questions asked</p>
                <p>✅ <strong>Money-back guarantee</strong> · 14 days</p>
                <p>🎉 <strong>Special Launch Offer:</strong> Full features unlocked for testing!</p>
            </div>
            
            <button class="maybe-later-btn" onclick="this.closest('.upgrade-modal').remove()">
                Maybe Later
            </button>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Add CSS for new elements
    addBillingToggleStyles();
    
    // Set initial billing view
    switchBillingView(currentBilling);
    
    // Animate in
    requestAnimationFrame(() => {
        modal.classList.add('active');
    });
}

// ==========================================
// BILLING PERIOD SWITCHING
// ==========================================
function switchBillingView(period) {
    // Update toggle buttons
    document.querySelectorAll('.billing-option').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.period === period) {
            btn.classList.add('active');
        }
    });
    
    // Update Pro tier pricing
    const proPrice = document.getElementById('proPrice');
    const proPeriod = document.getElementById('proPeriod');
    const proSavings = document.getElementById('proSavings');
    
    if (period === 'annual') {
        proPrice.textContent = '$95';
        proPeriod.textContent = '/year';
        proSavings.style.display = 'block';
    } else {
        proPrice.textContent = '$9.99';
        proPeriod.textContent = '/month';
        proSavings.style.display = 'none';
    }
    
    // Update Premium tier pricing
    const premiumPrice = document.getElementById('premiumPrice');
    const premiumPeriod = document.getElementById('premiumPeriod');
    const premiumSavings = document.getElementById('premiumSavings');
    
    if (period === 'annual') {
        premiumPrice.textContent = '$239';
        premiumPeriod.textContent = '/year';
        premiumSavings.style.display = 'block';
    } else {
        premiumPrice.textContent = '$24.99';
        premiumPeriod.textContent = '/month';
        premiumSavings.style.display = 'none';
    }
    
    // Update billing note
    const billingNote = document.getElementById('billingNote');
    if (period === 'annual') {
        billingNote.textContent = '🎉 2+ months FREE with annual billing!';
        billingNote.style.color = 'var(--color-success)';
    } else {
        billingNote.textContent = '💰 Save up to $60 with annual billing';
        billingNote.style.color = 'var(--color-text-secondary)';
    }
    
    // Store current selection
    window.currentBillingSelection = period;
}

function getCurrentBillingPeriod() {
    return window.currentBillingSelection || 'monthly';
}

// ==========================================
// ADD BILLING TOGGLE STYLES
// ==========================================
function addBillingToggleStyles() {
    if (document.getElementById('billingToggleStyles')) return;
    
    const style = document.createElement('style');
    style.id = 'billingToggleStyles';
    style.textContent = `
        .billing-toggle-container {
            text-align: center;
            margin: 2rem 0;
        }
        
        .billing-toggle {
            display: inline-flex;
            background: var(--color-bg-tertiary);
            border: 2px solid var(--color-border);
            border-radius: 50px;
            padding: 4px;
            gap: 4px;
        }
        
        .billing-option {
            position: relative;
            padding: 12px 32px;
            border: none;
            background: transparent;
            color: var(--color-text-secondary);
            font-size: 14px;
            font-weight: 600;
            border-radius: 50px;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .billing-option:hover {
            color: var(--color-text-primary);
        }
        
        .billing-option.active {
            background: var(--color-accent-primary);
            color: var(--color-bg-primary);
            box-shadow: 0 4px 12px rgba(212, 175, 55, 0.3);
        }
        
        .save-badge {
            display: inline-block;
            padding: 2px 8px;
            background: var(--color-success);
            color: white;
            font-size: 9px;
            font-weight: 700;
            border-radius: 12px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }
        
        .billing-option.active .save-badge {
            background: rgba(255, 255, 255, 0.3);
            color: var(--color-bg-primary);
        }
        
        .billing-note {
            margin-top: 12px;
            font-size: 14px;
            font-weight: 500;
            color: var(--color-text-secondary);
            transition: color 0.3s ease;
        }
        
        .price-savings {
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid var(--color-border);
        }
        
        .savings-text {
            display: block;
            font-size: 14px;
            color: var(--color-success);
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .monthly-equivalent {
            display: block;
            font-size: 12px;
            color: var(--color-text-tertiary);
        }
        
        @media (max-width: 768px) {
            .billing-option {
                padding: 10px 20px;
                font-size: 13px;
            }
            
            .save-badge {
                font-size: 8px;
                padding: 2px 6px;
            }
        }
    `;
    
    document.head.appendChild(style);
}

// ==========================================
// UPGRADE/DOWNGRADE FUNCTIONS
// ==========================================
function upgradePlan(tier, billingPeriod = 'monthly') {
    console.log(`🚀 Upgrading to ${tier} (${billingPeriod})`);
    
    // Show notification about payment integration
    const tierName = tier.charAt(0).toUpperCase() + tier.slice(1);
    const price = billingPeriod === 'annual' 
        ? (tier === 'pro' ? '$95/year' : '$239/year')
        : (tier === 'pro' ? '$9.99/month' : '$24.99/month');
    
    window.showNotification(
        `🔧 Payment integration coming soon! Upgrading to ${tierName} (${price}) for testing.`,
        'info'
    );
    
    // FOR TESTING: Actually upgrade the user
    if (window.profileManager) {
        window.profileManager.upgradeTier(tier, billingPeriod);
        updateTierDisplay();
        document.querySelector('.upgrade-modal').remove();
        
        const savingsMsg = billingPeriod === 'annual' 
            ? ` You're saving ${tier === 'pro' ? '$24.88' : '$60.88'}/year! 💰`
            : '';
        
        window.showNotification(
            `✅ Upgraded to ${tierName} (${billingPeriod})!${savingsMsg}`,
            'success'
        );
        
        // Reload page to apply new limits
        setTimeout(() => window.location.reload(), 1500);
    }
}

function downgradePlan(tier) {
    if (!confirm('Are you sure you want to downgrade? You\'ll lose access to premium features and your billing will be cancelled.')) {
        return;
    }
    
    if (window.profileManager) {
        window.profileManager.downgradeTier('user_request');
        updateTierDisplay();
        document.querySelector('.upgrade-modal').remove();
        window.showNotification('✅ Downgraded to Free tier', 'info');
        
        setTimeout(() => window.location.reload(), 1500);
    }
}

// ==========================================
// USAGE STATS MODAL
// ==========================================
function showUsageStats() {
    if (!window.profileManager) return;
    
    const stats = window.profileManager.getUsageStats();
    const tierInfo = window.profileManager.getTierInfo();
    const usage = window.profileManager.getUsage();
    
    const modal = document.createElement('div');
    modal.className = 'usage-stats-modal';
    modal.innerHTML = `
        <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
        <div class="modal-content">
            <button class="modal-close" onclick="this.closest('.usage-stats-modal').remove()">✕</button>
            
            <h2>📊 Your Usage This Month</h2>
            <div class="tier-info">
                <span class="tier-badge-large">
                    <span class="tier-icon">${tierInfo.icon}</span>
                    <span class="tier-name">${tierInfo.name}</span>
                </span>
                ${tierInfo.billingPeriod === 'annual' ? '<span class="annual-badge">Annual Plan 💰</span>' : ''}
            </div>
            
            <div class="stats-grid">
                ${createStatCard('💬', 'Messages', usage.messages || 0, tierInfo.limits.messages)}
                ${createStatCard('🎨', 'Images', usage.images || 0, tierInfo.limits.images)}
                ${createStatCard('🔍', 'Searches', usage.searches || 0, tierInfo.limits.searches)}
                ${createStatCard('🌤️', 'Weather', usage.weather || 0, tierInfo.limits.weather)}
                ${createStatCard('📰', 'News', usage.news || 0, tierInfo.limits.news)}
                ${createStatCard('🏈', 'Sports', usage.sports || 0, tierInfo.limits.sports)}
                ${tierInfo.current !== 'free' ? createStatCard('🎵', 'Spotify', usage.spotify || 0, tierInfo.limits.spotify) : ''}
                ${tierInfo.current !== 'free' ? createStatCard('📺', 'YouTube', usage.youtube || 0, tierInfo.limits.youtube) : ''}
                ${tierInfo.current === 'premium' ? createStatCard('📧', 'Gmail', usage.gmail || 0, tierInfo.limits.gmail) : ''}
            </div>
            
            ${tierInfo.current === 'free' ? `
                <div class="upgrade-cta">
                    <p><strong>Need more?</strong> Upgrade for 10x the limits!</p>
                    <button class="btn-primary" onclick="this.closest('.usage-stats-modal').remove(); showUpgradePrompt();">
                        View Plans
                    </button>
                </div>
            ` : ''}
            
            <button class="btn-secondary" onclick="this.closest('.usage-stats-modal').remove()">
                Close
            </button>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    requestAnimationFrame(() => {
        modal.classList.add('active');
    });
}

function createStatCard(icon, label, used, limit) {
    const unlimited = limit === -1;
    const percentage = unlimited ? 0 : Math.min(100, (used / limit) * 100);
    const isWarning = percentage > 90 && !unlimited;
    
    return `
        <div class="stat-card">
            <div class="stat-header">
                <span class="stat-icon">${icon}</span>
                <span class="stat-label">${label}</span>
            </div>
            <div class="stat-bar">
                <div class="stat-fill ${isWarning ? 'warning' : ''}" style="width: ${percentage}%"></div>
            </div>
            <div class="stat-numbers">
                <span class="stat-used">${used}</span>
                <span class="stat-separator">/</span>
                <span class="stat-limit">${unlimited ? '∞' : limit}</span>
            </div>
            ${isWarning ? '<div class="stat-warning">⚠️ Running low!</div>' : ''}
        </div>
    `;
}

// ==========================================
// UPDATE TIER DISPLAY
// ==========================================
function updateTierDisplay() {
    if (!window.profileManager) return;
    
    const tierInfo = window.profileManager.getTierInfo();
    
    // Update sidebar
    const sidebarTier = document.getElementById('tierName');
    if (sidebarTier) {
        sidebarTier.innerHTML = `${tierInfo.icon} ${tierInfo.name}`;
    }
    
    // Update header
    const headerTier = document.getElementById('headerTierName');
    if (headerTier) {
        headerTier.textContent = tierInfo.name;
    }
    
    // Update tier badge
    const tierBadge = document.getElementById('tierBadge');
    if (tierBadge) {
        tierBadge.innerHTML = `
            <span class="tier-icon">${tierInfo.icon}</span>
            <span class="tier-name">${tierInfo.name}</span>
        `;
    }
}

// ==========================================
// EXPORT FUNCTIONS
// ==========================================
window.showUpgradePrompt = showUpgradePrompt;
window.showUsageStats = showUsageStats;
window.upgradePlan = upgradePlan;
window.downgradePlan = downgradePlan;
window.switchBillingView = switchBillingView;
window.getCurrentBillingPeriod = getCurrentBillingPeriod;
window.updateTierDisplay = updateTierDisplay;

console.log('✅ Upgrade UI v3.1.0 loaded - Annual billing enabled');
