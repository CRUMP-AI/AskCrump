(function initializeSafeStorage() {
    'use strict';

    class StorageFacade {
        constructor() {
            this.memory = new Map();
            this.persistent = this.detectPersistentStorage();
        }

        detectPersistentStorage() {
            try {
                const key = '__ask_crump_storage_test__';
                window.localStorage.setItem(key, key);
                window.localStorage.removeItem(key);
                return true;
            } catch {
                console.warn('[Storage] Persistent browser storage is unavailable.');
                return false;
            }
        }

        setItem(key, value) {
            const normalized = String(value);
            this.memory.set(key, normalized);
            if (!this.persistent) return;
            try {
                window.localStorage.setItem(key, normalized);
            } catch {
                this.persistent = false;
                console.warn('[Storage] A write was kept in memory only.');
            }
        }

        getItem(key) {
            if (this.persistent) {
                try {
                    const value = window.localStorage.getItem(key);
                    if (value !== null) return value;
                } catch {
                    this.persistent = false;
                    console.warn('[Storage] Persistent reads are unavailable.');
                }
            }
            return this.memory.get(key) ?? null;
        }

        removeItem(key) {
            this.memory.delete(key);
            if (!this.persistent) return;
            try {
                window.localStorage.removeItem(key);
            } catch {
                this.persistent = false;
            }
        }

        clear() {
            this.memory.clear();
            if (!this.persistent) return;
            try {
                window.localStorage.clear();
            } catch {
                this.persistent = false;
            }
        }

        key(index) {
            if (this.persistent) {
                try {
                    return window.localStorage.key(index);
                } catch {
                    this.persistent = false;
                }
            }
            return Array.from(this.memory.keys())[index] ?? null;
        }

        get length() {
            if (this.persistent) {
                try {
                    return window.localStorage.length;
                } catch {
                    this.persistent = false;
                }
            }
            return this.memory.size;
        }
    }

    window.safeStorage = new StorageFacade();
    window.SafeStorage = window.safeStorage;
}());
