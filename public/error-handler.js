// ==========================================
// CRUMP AI - GLOBAL ERROR HANDLER & CONFIG
// Enterprise-grade error handling system
// ==========================================

// Global Configuration
window.CONFIG = {
    APP_NAME: 'Crump AI',
    VERSION: '2.0.0',
    API_TIMEOUT: 30000,
    MAX_RETRIES: 3,
    CACHE_DURATION: 3600000, // 1 hour
    
    // Feature Flags
    FEATURES: {
        AUTONOMOUS_MODE: true,
        DEVELOPER_MODE: true,
        OFFLINE_MODE: true,
        PWA_INSTALL: true,
        VOICE_INPUT: false,
        BACKGROUND_SYNC: false
    },
    
    // API Endpoints
    APIS: {
        ANTHROPIC: 'https://api.anthropic.com/v1',
        OPENAI: 'https://api.openai.com/v1',
        GOOGLE: 'https://www.googleapis.com/v1',
        GITHUB: 'https://api.github.com',
        SPOTIFY: 'https://api.spotify.com/v1',
        WEATHER: 'https://api.openweathermap.org/data/2.5',
        NEWS: 'https://newsapi.org/v2',
        STOCK: 'https://www.alphavantage.co/query',
        MOVIE: 'https://api.themoviedb.org/3',
        CRYPTO: 'https://api.coingecko.com/api/v3',
        FLIGHTS: 'https://api.amadeus.com/v1',
        RECIPES: 'https://api.spoonacular.com',
        MAPS: 'https://maps.googleapis.com/maps/api',
        YOUTUBE: 'https://www.googleapis.com/youtube/v3',
        GMAIL: 'https://gmail.googleapis.com/gmail/v1',
        DRIVE: 'https://www.googleapis.com/drive/v3',
        CALENDAR: 'https://www.googleapis.com/calendar/v3',
        TRANSLATE: 'https://translation.googleapis.com/language/translate/v2',
        SPORTS: 'https://api-football-v1.p.rapidapi.com/v3'
    },
    
    // Storage Keys
    STORAGE: {
        USER: 'crump_user',
        CHATS: 'crump_chats',
        SETTINGS: 'crump_settings',
        CACHE: 'crump_cache',
        AUTH_TOKENS: 'crump_auth_tokens',
        API_KEYS: 'crump_api_keys'
    },
    
    // Error Codes
    ERRORS: {
        AUTH_FAILED: 'AUTH_001',
        API_ERROR: 'API_002',
        NETWORK_ERROR: 'NET_001',
        STORAGE_ERROR: 'STR_001',
        VALIDATION_ERROR: 'VAL_001',
        RATE_LIMIT: 'RATE_001',
        TIMEOUT: 'TIME_001'
    }
};

// ==========================================
// ERROR HANDLER CLASS
// ==========================================
class ErrorHandler {
    constructor() {
        this.errors = [];
        this.maxErrors = 100;
        this.init();
    }
    
    init() {
        // Global error catcher
        window.addEventListener('error', (event) => {
            this.handleError({
                type: 'RUNTIME_ERROR',
                message: event.message,
                source: event.filename,
                line: event.lineno,
                column: event.colno,
                stack: event.error?.stack
            });
        });
        
        // Promise rejection catcher
        window.addEventListener('unhandledrejection', (event) => {
            this.handleError({
                type: 'PROMISE_REJECTION',
                message: event.reason?.message || 'Unhandled Promise Rejection',
                stack: event.reason?.stack
            });
        });
        
        console.log('✅ Global Error Handler initialized');
    }
    
    handleError(error) {
        const errorLog = {
            timestamp: new Date().toISOString(),
            type: error.type || 'UNKNOWN',
            message: error.message || 'Unknown error',
            code: error.code || 'UNKNOWN',
            source: error.source || 'unknown',
            line: error.line || 0,
            column: error.column || 0,
            stack: error.stack || '',
            userAgent: navigator.userAgent,
            url: window.location.href
        };
        
        // Store error
        this.errors.push(errorLog);
        if (this.errors.length > this.maxErrors) {
            this.errors.shift();
        }
        
        // Log to console in development
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            console.error('🚨 Error caught:', errorLog);
        }
        
        // Send to monitoring service (if configured)
        this.sendToMonitoring(errorLog);
        
        // Show user-friendly message for critical errors
        if (this.isCritical(error)) {
            this.showUserNotification(error);
        }
    }
    
    isCritical(error) {
        const criticalTypes = ['AUTH_FAILED', 'STORAGE_ERROR', 'FATAL_ERROR'];
        return criticalTypes.includes(error.type) || criticalTypes.includes(error.code);
    }
    
    showUserNotification(error) {
        // Only show user-friendly messages
        const userMessage = this.getUserFriendlyMessage(error);
        
        if (window.showToast) {
            window.showToast(userMessage, 'error');
        } else {
            console.error(userMessage);
        }
    }
    
    getUserFriendlyMessage(error) {
        const messages = {
            'AUTH_FAILED': 'Authentication failed. Please sign in again.',
            'API_ERROR': 'Service temporarily unavailable. Please try again.',
            'NETWORK_ERROR': 'Network connection issue. Check your internet.',
            'STORAGE_ERROR': 'Storage error. Try clearing browser cache.',
            'RATE_LIMIT': 'Too many requests. Please wait a moment.',
            'TIMEOUT': 'Request timed out. Please try again.'
        };
        
        return messages[error.code] || 'Something went wrong. Please try again.';
    }
    
    sendToMonitoring(errorLog) {
        // TODO: Integrate with monitoring service (Sentry, LogRocket, etc.)
        // For now, just store locally
        try {
            const stored = JSON.parse(localStorage.getItem('crump_error_logs') || '[]');
            stored.push(errorLog);
            // Keep last 50 errors
            if (stored.length > 50) {
                stored.splice(0, stored.length - 50);
            }
            localStorage.setItem('crump_error_logs', JSON.stringify(stored));
        } catch (e) {
            console.warn('Failed to store error log:', e);
        }
    }
    
    getErrors(limit = 10) {
        return this.errors.slice(-limit);
    }
    
    clearErrors() {
        this.errors = [];
        localStorage.removeItem('crump_error_logs');
        console.log('✅ Error logs cleared');
    }
    
    exportErrors() {
        return {
            version: CONFIG.VERSION,
            timestamp: new Date().toISOString(),
            errors: this.errors,
            userAgent: navigator.userAgent,
            url: window.location.href
        };
    }
}

// Initialize global error handler
window.ErrorHandler = new ErrorHandler();

// ==========================================
// SAFE API WRAPPER
// ==========================================
class SafeAPI {
    static async call(fn, fallback = null, context = 'API') {
        try {
            return await fn();
        } catch (error) {
            window.ErrorHandler.handleError({
                type: 'API_ERROR',
                code: CONFIG.ERRORS.API_ERROR,
                message: error.message,
                context: context,
                stack: error.stack
            });
            return fallback;
        }
    }
    
    static async fetch(url, options = {}, context = 'Fetch') {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), CONFIG.API_TIMEOUT);
        
        try {
            const response = await fetch(url, {
                ...options,
                signal: controller.signal
            });
            
            clearTimeout(timeout);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            clearTimeout(timeout);
            
            const errorType = error.name === 'AbortError' ? 'TIMEOUT' : 'NETWORK_ERROR';
            const errorCode = error.name === 'AbortError' ? CONFIG.ERRORS.TIMEOUT : CONFIG.ERRORS.NETWORK_ERROR;
            
            window.ErrorHandler.handleError({
                type: errorType,
                code: errorCode,
                message: error.message,
                context: context,
                url: url
            });
            
            throw error;
        }
    }
    
    static async retry(fn, maxRetries = CONFIG.MAX_RETRIES, delay = 1000) {
        for (let i = 0; i < maxRetries; i++) {
            try {
                return await fn();
            } catch (error) {
                if (i === maxRetries - 1) throw error;
                await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)));
            }
        }
    }
}

window.SafeAPI = SafeAPI;

// ==========================================
// STORAGE WRAPPER WITH ERROR HANDLING
// ==========================================
class SafeStorage {
    static get(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch (error) {
            window.ErrorHandler.handleError({
                type: 'STORAGE_ERROR',
                code: CONFIG.ERRORS.STORAGE_ERROR,
                message: 'Failed to read from storage',
                key: key
            });
            return defaultValue;
        }
    }
    
    static set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
            return true;
        } catch (error) {
            window.ErrorHandler.handleError({
                type: 'STORAGE_ERROR',
                code: CONFIG.ERRORS.STORAGE_ERROR,
                message: 'Failed to write to storage',
                key: key,
                error: error.message
            });
            return false;
        }
    }
    
    static remove(key) {
        try {
            localStorage.removeItem(key);
            return true;
        } catch (error) {
            window.ErrorHandler.handleError({
                type: 'STORAGE_ERROR',
                code: CONFIG.ERRORS.STORAGE_ERROR,
                message: 'Failed to remove from storage',
                key: key
            });
            return false;
        }
    }
    
    static clear() {
        try {
            localStorage.clear();
            return true;
        } catch (error) {
            window.ErrorHandler.handleError({
                type: 'STORAGE_ERROR',
                code: CONFIG.ERRORS.STORAGE_ERROR,
                message: 'Failed to clear storage'
            });
            return false;
        }
    }
    
    static isAvailable() {
        try {
            const test = '__storage_test__';
            localStorage.setItem(test, test);
            localStorage.removeItem(test);
            return true;
        } catch (error) {
            return false;
        }
    }
}

window.SafeStorage = SafeStorage;

// ==========================================
// PERFORMANCE MONITOR
// ==========================================
class PerformanceMonitor {
    constructor() {
        this.metrics = {};
    }
    
    start(label) {
        this.metrics[label] = {
            start: performance.now()
        };
    }
    
    end(label) {
        if (this.metrics[label]) {
            this.metrics[label].end = performance.now();
            this.metrics[label].duration = this.metrics[label].end - this.metrics[label].start;
            
            if (this.metrics[label].duration > 1000) {
                console.warn(`⚠️ Slow operation: ${label} took ${this.metrics[label].duration.toFixed(2)}ms`);
            }
            
            return this.metrics[label].duration;
        }
    }
    
    getMetrics() {
        return this.metrics;
    }
    
    clear() {
        this.metrics = {};
    }
}

window.PerformanceMonitor = new PerformanceMonitor();

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
window.Utils = {
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },
    
    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },
    
    async sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    },
    
    formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    },
    
    isOnline() {
        return navigator.onLine;
    },
    
    isMobile() {
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    },
    
    isPWA() {
        return window.matchMedia('(display-mode: standalone)').matches ||
               window.navigator.standalone === true;
    },
    
    copyToClipboard(text) {
        if (navigator.clipboard) {
            return navigator.clipboard.writeText(text);
        } else {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            return Promise.resolve();
        }
    }
};

// ==========================================
// TOAST NOTIFICATION SYSTEM
// ==========================================
window.showToast = function(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: ${type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : '#3b82f6'};
        color: white;
        padding: 12px 24px;
        border-radius: 8px;
        z-index: 10000;
        animation: slideUp 0.3s ease;
        font-family: 'Inter', sans-serif;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideDown 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duration);
};

// Add animation styles
if (!document.getElementById('toast-styles')) {
    const style = document.createElement('style');
    style.id = 'toast-styles';
    style.textContent = `
        @keyframes slideUp {
            from { transform: translateX(-50%) translateY(100px); opacity: 0; }
            to { transform: translateX(-50%) translateY(0); opacity: 1; }
        }
        @keyframes slideDown {
            from { transform: translateX(-50%) translateY(0); opacity: 1; }
            to { transform: translateX(-50%) translateY(100px); opacity: 0; }
        }
    `;
    document.head.appendChild(style);
}

console.log('✅ Crump AI Core Systems Initialized');
console.log('📊 Version:', CONFIG.VERSION);
console.log('🛡️ Error Handler: Active');
console.log('💾 Safe Storage:', SafeStorage.isAvailable() ? 'Available' : 'Unavailable');
console.log('📱 Device:', Utils.isMobile() ? 'Mobile' : 'Desktop');
console.log('🌐 Network:', Utils.isOnline() ? 'Online' : 'Offline');
console.log('📦 PWA Mode:', Utils.isPWA() ? 'Yes' : 'No');
