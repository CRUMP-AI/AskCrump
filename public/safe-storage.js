// ==========================================
// SAFE STORAGE WRAPPER - Safari ITP Compatible
// ==========================================
// This wrapper handles Safari's Intelligent Tracking Prevention
// by providing graceful fallbacks when storage is blocked

class SafeStorage {
    constructor() {
        this.memoryStore = new Map();
        this.storageAvailable = this.testStorage();
        
        if (!this.storageAvailable) {
            console.warn('⚠️ localStorage blocked (Safari ITP) - using in-memory fallback');
        }
    }
    
    testStorage() {
        try {
            const test = '__storage_test__';
            localStorage.setItem(test, test);
            localStorage.removeItem(test);
            return true;
        } catch (e) {
            return false;
        }
    }
    
    setItem(key, value) {
        try {
            if (this.storageAvailable) {
                localStorage.setItem(key, value);
            }
        } catch (e) {
            console.warn(`[SafeStorage] localStorage.setItem blocked for key: ${key}`);
            this.storageAvailable = false;
        }
        
        // Always store in memory as backup
        this.memoryStore.set(key, value);
    }
    
    getItem(key) {
        try {
            if (this.storageAvailable) {
                const value = localStorage.getItem(key);
                if (value !== null) {
                    return value;
                }
            }
        } catch (e) {
            console.warn(`[SafeStorage] localStorage.getItem blocked for key: ${key}`);
            this.storageAvailable = false;
        }
        
        // Fallback to memory
        return this.memoryStore.get(key) || null;
    }
    
    removeItem(key) {
        try {
            if (this.storageAvailable) {
                localStorage.removeItem(key);
            }
        } catch (e) {
            console.warn(`[SafeStorage] localStorage.removeItem blocked for key: ${key}`);
        }
        
        this.memoryStore.delete(key);
    }
    
    clear() {
        try {
            if (this.storageAvailable) {
                localStorage.clear();
            }
        } catch (e) {
            console.warn('[SafeStorage] localStorage.clear blocked');
        }
        
        this.memoryStore.clear();
    }
    
    key(index) {
        try {
            if (this.storageAvailable) {
                return localStorage.key(index);
            }
        } catch (e) {
            console.warn('[SafeStorage] localStorage.key blocked');
        }
        
        const keys = Array.from(this.memoryStore.keys());
        return keys[index] || null;
    }
    
    get length() {
        try {
            if (this.storageAvailable) {
                return localStorage.length;
            }
        } catch (e) {
            console.warn('[SafeStorage] localStorage.length blocked');
        }
        
        return this.memoryStore.size;
    }
}

// Create global instance
window.safeStorage = new SafeStorage();
window.SafeStorage = window.safeStorage; // Capital S alias for compatibility

// Optionally, override localStorage globally (careful!)
// This makes ALL localStorage calls safe automatically
if (typeof window !== 'undefined') {
    // Store original for fallback
    window._originalLocalStorage = window.localStorage;
    
    // You can uncomment this to replace localStorage globally:
    /*
    Object.defineProperty(window, 'localStorage', {
        get() {
            return window.safeStorage;
        }
    });
    */
}

console.log('✅ SafeStorage loaded - Safari ITP protected');
