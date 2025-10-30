// ==========================================
// CRUMP AI - GLOBAL ERROR HANDLER v1.0
// Comprehensive error handling and recovery
// ==========================================

class ErrorHandler {
    constructor() {
        this.errors = [];
        this.maxErrors = 100;
        this.initialized = false;
        
        this.errorTypes = {
            NETWORK: 'network',
            API: 'api',
            STORAGE: 'storage',
            RUNTIME: 'runtime',
            VALIDATION: 'validation',
            AUTH: 'auth'
        };
        
        this.init();
    }
    
    init() {
        if (this.initialized) return;
        
        // Global error handler
        window.addEventListener('error', (event) => {
            this.handleError({
                type: this.errorTypes.RUNTIME,
                message: event.message,
                source: event.filename,
                line: event.lineno,
                column: event.colno,
                error: event.error,
                timestamp: new Date().toISOString()
            });
        });
        
        // Promise rejection handler
        window.addEventListener('unhandledrejection', (event) => {
            this.handleError({
                type: this.errorTypes.RUNTIME,
                message: 'Unhandled Promise Rejection',
                reason: event.reason,
                timestamp: new Date().toISOString()
            });
        });
        
        // Network handlers
        window.addEventListener('offline', () => {
            this.showToast('You are offline', 'warning');
        });
        
        window.addEventListener('online', () => {
            this.showToast('Connection restored', 'success');
        });
        
        this.initialized = true;
        console.log('Error handler initialized');
    }
    
    handleError(errorInfo) {
        this.logError(errorInfo);
        
        this.errors.push(errorInfo);
        if (this.errors.length > this.maxErrors) {
            this.errors.shift();
        }
        
        try {
            localStorage.setItem('crump_error_log', 
                JSON.stringify(this.errors.slice(-10)));
        } catch (e) {
            // Storage error - already handling
        }
        
        this.displayErrorToUser(errorInfo);
        this.attemptRecovery(errorInfo);
    }
    
    logError(errorInfo) {
        console.group('Error Logged');
        console.error('Type:', errorInfo.type);
        console.error('Message:', errorInfo.message);
        if (errorInfo.error) {
            console.error('Stack:', errorInfo.error.stack);
        }
        console.groupEnd();
    }
    
    displayErrorToUser(errorInfo) {
        const messages = {
            network: 'Network issue. Check your connection.',
            api: 'Service unavailable. Try again later.',
            storage: 'Storage issue. Try clearing browser data.',
            runtime: 'Something went wrong.',
            validation: 'Invalid input.',
            auth: 'Authentication required.'
        };
        
        const message = messages[errorInfo.type] || 'An error occurred';
        
        if (this.isCritical(errorInfo)) {
            this.showToast(message, 'error');
        }
    }
    
    isCritical(errorInfo) {
        return ['auth', 'storage'].includes(errorInfo.type);
    }
    
    attemptRecovery(errorInfo) {
        switch (errorInfo.type) {
            case 'storage':
                this.recoverStorage();
                break;
            case 'network':
                this.recoverNetwork();
                break;
        }
    }
    
    recoverStorage() {
        try {
            const test = '__test__';
            localStorage.setItem(test, test);
            localStorage.removeItem(test);
        } catch (e) {
            this.cleanupOldData();
        }
    }
    
    recoverNetwork() {
        setTimeout(() => {
            if (navigator.onLine) {
                console.log('Network restored');
            }
        }, 5000);
    }
    
    cleanupOldData() {
        try {
            const chats = JSON.parse(localStorage.getItem('crump_chats') || '[]');
            if (chats.length > 20) {
                localStorage.setItem('crump_chats', JSON.stringify(chats.slice(-20)));
            }
        } catch (e) {
            console.error('Cleanup failed');
        }
    }
    
    showToast(message, type = 'info') {
        if (window.showToast) {
            window.showToast(message, type);
        } else {
            console.log(`[${type}] ${message}`);
        }
    }
    
    captureError(type, message, details = {}) {
        this.handleError({
            type,
            message,
            ...details,
            timestamp: new Date().toISOString()
        });
    }
}

// Initialize
if (typeof window !== 'undefined') {
    window.errorHandler = new ErrorHandler();
    window.captureError = (type, msg, details) => 
        window.errorHandler.captureError(type, msg, details);
}

export default ErrorHandler;
