/* ==========================================
   CRUMP AI - PWA INSTALLER STYLES v2.0
   Professional, minimalistic design
   ========================================== */

/* ==========================================
   INSTALL BANNER (Bottom Banner)
   ========================================== */
.pwa-install-banner {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: linear-gradient(135deg, var(--color-accent-primary) 0%, var(--color-accent-secondary) 100%);
    color: var(--color-bg-primary);
    padding: 1rem 1.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    z-index: 9999;
    box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.4);
    transform: translateY(100%);
    transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    border-top: 1px solid rgba(255, 255, 255, 0.2);
}

.pwa-install-banner.visible {
    transform: translateY(0);
}

.pwa-install-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    background: rgba(255, 255, 255, 0.15);
    border-radius: 12px;
    flex-shrink: 0;
}

.pwa-install-icon svg {
    width: 28px;
    height: 28px;
}

.pwa-install-content {
    flex: 1;
    min-width: 0;
}

.pwa-install-content h3 {
    margin: 0 0 0.25rem 0;
    font-size: 1rem;
    font-weight: 700;
    letter-spacing: -0.01em;
}

.pwa-install-content p {
    margin: 0;
    font-size: 0.875rem;
    opacity: 0.9;
    font-weight: 400;
}

.pwa-install-actions {
    display: flex;
    gap: 0.75rem;
    flex-shrink: 0;
}

.pwa-install-btn {
    padding: 0.625rem 1.25rem;
    border: none;
    border-radius: 8px;
    font-size: 0.9375rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    white-space: nowrap;
    letter-spacing: -0.01em;
}

.pwa-btn-dismiss {
    background: rgba(255, 255, 255, 0.15);
    color: var(--color-bg-primary);
    backdrop-filter: blur(10px);
}

.pwa-btn-dismiss:hover {
    background: rgba(255, 255, 255, 0.25);
    transform: translateY(-1px);
}

.pwa-btn-install {
    background: var(--color-bg-primary);
    color: var(--color-accent-primary);
    font-weight: 700;
}

.pwa-btn-install:hover {
    background: var(--color-bg-secondary);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

/* ==========================================
   SIDEBAR INSTALL BUTTON
   ========================================== */
#install-app-btn {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.875rem 1.25rem;
    background: linear-gradient(135deg, var(--color-accent-primary) 0%, var(--color-accent-secondary) 100%);
    color: var(--color-bg-primary);
    border: none;
    border-radius: 10px;
    font-size: 0.9375rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    width: 100%;
    justify-content: center;
    margin-bottom: 0.75rem;
    letter-spacing: -0.01em;
}

#install-app-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(212, 175, 55, 0.4);
}

#install-app-btn:active {
    transform: translateY(0);
}

#install-app-btn svg {
    flex-shrink: 0;
}

/* ==========================================
   IOS INSTRUCTIONS MODAL
   ========================================== */
#ios-install-modal .modal-content {
    max-width: 440px;
}

#ios-install-modal ol {
    background: var(--color-bg-tertiary);
    border: 1px solid var(--color-border);
    border-radius: 12px;
    padding: 1.5rem 1.5rem 1.5rem 2.5rem;
}

#ios-install-modal ol li {
    margin-bottom: 0.75rem;
    color: var(--color-text-primary);
}

#ios-install-modal ol li:last-child {
    margin-bottom: 0;
}

#ios-install-modal ol strong {
    color: var(--color-accent-primary);
    font-weight: 600;
}

/* ==========================================
   RESPONSIVE DESIGN
   ========================================== */
@media (max-width: 768px) {
    .pwa-install-banner {
        padding: 1rem;
        flex-wrap: wrap;
    }
    
    .pwa-install-icon {
        width: 40px;
        height: 40px;
    }
    
    .pwa-install-icon svg {
        width: 24px;
        height: 24px;
    }
    
    .pwa-install-content h3 {
        font-size: 0.9375rem;
    }
    
    .pwa-install-content p {
        font-size: 0.8125rem;
    }
    
    .pwa-install-actions {
        width: 100%;
        margin-top: 0.5rem;
    }
    
    .pwa-install-btn {
        flex: 1;
        padding: 0.75rem 1rem;
        font-size: 0.875rem;
    }
}

@media (max-width: 480px) {
    .pwa-install-banner {
        padding: 0.875rem;
    }
    
    .pwa-install-content h3 {
        font-size: 0.875rem;
    }
    
    .pwa-install-content p {
        font-size: 0.75rem;
    }
    
    .pwa-install-btn {
        padding: 0.625rem 0.875rem;
        font-size: 0.8125rem;
    }
}

/* ==========================================
   REDUCED MOTION
   ========================================== */
@media (prefers-reduced-motion: reduce) {
    .pwa-install-banner {
        transition: none;
    }
    
    .pwa-install-btn,
    #install-app-btn {
        transition: none;
    }
}

/* ==========================================
   SAFE AREA INSETS (For notched devices)
   ========================================== */
@supports (padding: max(0px)) {
    .pwa-install-banner {
        padding-left: max(1.5rem, env(safe-area-inset-left));
        padding-right: max(1.5rem, env(safe-area-inset-right));
        padding-bottom: max(1rem, env(safe-area-inset-bottom));
    }
}

/* ==========================================
   DARK MODE ADJUSTMENTS
   ========================================== */
@media (prefers-color-scheme: dark) {
    .pwa-install-banner {
        box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.6);
    }
    
    .pwa-btn-dismiss {
        background: rgba(255, 255, 255, 0.12);
    }
    
    .pwa-btn-dismiss:hover {
        background: rgba(255, 255, 255, 0.2);
    }
}

/* ==========================================
   ANIMATIONS
   ========================================== */
@keyframes installSuccess {
    0% {
        transform: scale(1);
        opacity: 1;
    }
    50% {
        transform: scale(1.05);
        opacity: 0.8;
    }
    100% {
        transform: scale(1);
        opacity: 0;
    }
}

.pwa-install-banner.success {
    animation: installSuccess 0.6s ease forwards;
}

/* ==========================================
   PRINT STYLES
   ========================================== */
@media print {
    .pwa-install-banner,
    #install-app-btn {
        display: none !important;
    }
}
