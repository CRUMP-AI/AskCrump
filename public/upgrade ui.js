// ==========================================
// CRUMP AI - UPGRADE PROMPT UI v2.12.0
// Tier comparison and upgrade modal
// ==========================================

function showUpgradePrompt() {
    // Remove existing modal if any
    const existing = document.querySelector('.upgrade-modal');
    if (existing) existing.remove();
    
    const tierInfo = window.profileManager ? window.profileManager.getTierInfo() : null;
    const currentTier = tierInfo ? tierInfo.current : 'free';
    
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
            
            <div class="tier-comparison">
                <div class="tier-card ${currentTier === 'free' ? 'current' : ''}">
                    <div class="tier-header">
                        <div class="tier-icon-large">🆓</div>
                        <h3>Free</h3>
                        ${currentTier === 'free' ? '<div class="current-badge">Current Plan</div>' : ''}
                    </div>
                    
                    <div class="tier-price">
                        <span class="price-amount">$0</span>
                        <span class="price-period">/month</span>
                    </div>
                    
                    <ul class="tier-features">
                        <li><span class="feature-icon">💬</span> 100 messages/month</li>
                        <li><span class="feature-icon">🎨</span> 10 images/month</li>
                        <li><span class="feature-icon">🔍</span> 20 web searches/month</li>
                        <li><span class="feature-icon">📁</span> File uploads</li>
                        <li><span class="feature-icon">🎙️</span> Voice I/O</li>
                        <li><span class="feature-icon">📝</span> Basic features</li>
                    </ul>
                    
                    ${currentTier !== 'free' ? '<button class="tier-button secondary" onclick="downgradePlan(\'free\')">Downgrade</button>' : '<div class="tier-button disabled">Current Plan</div>'}
                </div>
                
                <div class="tier-card featured ${currentTier === 'pro' ? 'current' : ''}">
                    <div class="popular-badge">MOST POPULAR</div>
                    <div class="tier-header">
                        <div class="tier-icon-large">⭐</div>
                        <h3>Pro</h3>
                        ${currentTier === 'pro' ? '<div class="current-badge">Current Plan</div>' : ''}
                    </div>
                    
                    <div class="tier-price">
                        <span class="price-amount">$9.99</span>
                        <span class="price-period">/month</span>
                    </div>
                    
                    <ul class="tier-features">
                        <li><span class="feature-icon">💬</span> <strong>1,000 messages/month</strong></li>
                        <li><span class="feature-icon">🎨</span> <strong>100 images/month</strong></li>
                        <li><span class="feature-icon">🔍</span> <strong>200 searches/month</strong></li>
                        <li><span class="feature-icon">📁</span> Multi-file uploads</li>
                        <li><span class="feature-icon">📄</span> PDF analysis</li>
                        <li><span class="feature-icon">🎙️</span> Enhanced voice</li>
                        <li><span class="feature-icon">⚡</span> Priority responses</li>
                        <li><span class="feature-icon">🎯</span> Advanced memory</li>
                    </ul>
                    
                    ${currentTier !== 'pro' ? '<button class="tier-button primary" onclick="upgradePlan(\'pro\')">Upgrade to Pro</button>' : '<div class="tier-button disabled">Current Plan</div>'}
                </div>
                
                <div class="tier-card ${currentTier === 'premium' ? 'current' : ''}">
                    <div class="tier-header">
                        <div class="tier-icon-large">👑</div>
                        <h3>Premium</h3>
                        ${currentTier === 'premium' ? '<div class="current-badge">Current Plan</div>' : ''}
                    </div>
                    
                    <div class="tier-price">
                        <span class="price-amount">$24.99</span>
                        <span class="price-period">/month</span>
                    </div>
                    
                    <ul class="tier-features">
                        <li><span class="feature-icon">💬</span> <strong>Unlimited messages</strong></li>
                        <li><span class="feature-icon">🎨</span> <strong>500 images/month</strong></li>
                        <li><span class="feature-icon">🔍</span> <strong>Unlimited searches</strong></li>
                        <li><span class="feature-icon">✨</span> Everything in Pro</li>
                        <li><span class="feature-icon">🧠</span> Extended memory</li>
                        <li><span class="feature-icon">🎨</span> Custom themes</li>
                        <li><span class="feature-icon">🔌</span> API access</li>
                        <li><span class="feature-icon">👨‍💻</span> Priority support</li>
                    </ul>
                    
                    ${currentTier !== 'premium' ? '<button class="tier-button primary" onclick="upgradePlan(\'premium\')">Upgrade to Premium</button>' : '<div class="tier-button disabled">Current Plan</div>'}
                </div>
            </div>
            
            <div class="upgrade-footer">
                <p>💳 <strong>Secure payment</strong> powered by Stripe</p>
                <p>🔄 <strong>Cancel anytime</strong> · No questions asked</p>
                <p>✅ <strong>Money-back guarantee</strong> · 14 days</p>
            </div>
            
            <button class="maybe-later-btn" onclick="this.closest('.upgrade-modal').remove()">
                Maybe Later
            </button>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Animate in
    requestAnimationFrame(() => {
        modal.classList.add('active');
    });
}

// Placeholder functions (will be implemented with Stripe later)
function upgradePlan(tier) {
    window.showNotification('🔧 Payment integration coming soon! You can use full features for now.', 'info');
    
    // FOR TESTING: Actually upgrade the user
    if (window.profileManager) {
        window.profileManager.upgradeTier(tier);
        window.updateTierDisplay();
        document.querySelector('.upgrade-modal').remove();
        window.showNotification(`✅ Upgraded to ${tier.toUpperCase()} for testing!`, 'success');
        
        // Reload page to apply new limits
        setTimeout(() => window.location.reload(), 1500);
    }
}

function downgradePlan(tier) {
    if (!confirm('Are you sure you want to downgrade? You\'ll lose access to premium features.')) {
        return;
    }
    
    if (window.profileManager) {
        window.profileManager.downgradeTier('user_request');
        window.updateTierDisplay();
        document.querySelector('.upgrade-modal').remove();
        window.showNotification('✅ Downgraded to Free tier', 'info');
        
        setTimeout(() => window.location.reload(), 1500);
    }
}

// Show usage stats modal
function showUsageStats() {
    if (!window.profileManager) return;
    
    const stats = window.profileManager.getUsageStats();
    const tierInfo = window.profileManager.getTierInfo();
    
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
            </div>
            
            <div class="stats-grid">
                ${stats.map(stat => `
                    <div class="stat-card">
                        <div class="stat-header">
                            <span class="stat-icon">${stat.icon}</span>
                            <span class="stat-label">${stat.label}</span>
                        </div>
                        <div class="stat-bar">
                            <div class="stat-fill ${stat.percentage > 90 ? 'warning' : ''}" 
                                 style="width: ${stat.unlimited ? '0' : stat.percentage}%"></div>
                        </div>
                        <div class="stat-numbers">
                            <span class="stat-used">${stat.used}</span>
                            <span class="stat-separator">/</span>
                            <span class="stat-limit">${stat.unlimited ? 'Unlimited' : stat.limit}</span>
                        </div>
                        ${stat.percentage > 90 && !stat.unlimited ? '<div class="stat-warning">⚠️ Running low!</div>' : ''}
                    </div>
                `).join('')}
            </div>
            
            ${tierInfo.current === 'free' ? `
                <div class="upgrade-cta">
                    <p>Need more? Upgrade for 10x the limits!</p>
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

// Export functions
window.showUpgradePrompt = showUpgradePrompt;
window.showUsageStats = showUsageStats;
window.upgradePlan = upgradePlan;
window.downgradePlan = downgradePlan;

console.log('✅ Upgrade UI loaded');
