// =====================================================
// CHAT SYNC MODULE - Cross-Device Synchronization
// =====================================================

// Sync chats FROM server
window.syncChatsFromServer = async function() {
    if (!navigator.onLine) {
        console.log('[Sync] Offline - will retry when connection restored');
        window.addEventListener('online', () => {
            console.log('[Sync] Connection restored - syncing now');
            syncChatsFromServer();
        }, { once: true });
        return;
    }

    if (!window.currentUser) {
        console.log('[Sync] Not authenticated, skipping sync');
        return;
    }


    try {
        console.log('[Sync] Fetching chats from server...');
        
       const deviceId = window.deviceAuth?.getDeviceId?.();
const result = await window.SyncManager.pull(deviceId);

if (!result?.success || !Array.isArray(result.data?.chats)) {
    console.warn('[Sync] Invalid sync response:', result);
    return;
}

const serverChatsRaw = result.data.chats;

 console.log('[Sync] Received', serverChatsRaw.length, 'chats from server');

        // Merge server chats with local chats
        const localChats = JSON.parse(SafeStorage.getItem(STORAGE_KEYS.CHATS) || '[]');
       const normalizeISO = (v) => {
    if (!v) return new Date().toISOString();
    if (typeof v === 'number') return new Date(v).toISOString();
    const t = new Date(v).getTime();
    return Number.isFinite(t) ? new Date(t).toISOString() : new Date().toISOString();
};

const serverChats = serverChatsRaw.map(chat => ({
    id: chat.chat_id || chat.id,
    chat_id: chat.chat_id || chat.id,
    messages: chat.messages || [],
    title: chat.title || 'Chat',
    createdAt: normalizeISO(chat.created_at || chat.createdAt),
    updatedAt: normalizeISO(chat.updated_at || chat.updatedAt || chat.created_at || chat.createdAt)
}));


        // Create a map of chat IDs for quick lookup
        const chatMap = new Map();
        
        // Add local chats first
       localChats.forEach(chat => {
    const key = chat.chat_id || chat.id;
    if (key) chatMap.set(key, chat);
});

       // Merge server chats (server takes precedence if newer)
const toTime = (v) => {
    if (!v) return 0;
    if (typeof v === 'number') return v;
    const t = new Date(v).getTime();
    return Number.isFinite(t) ? t : 0;
};

serverChats.forEach(serverChat => {
    const key = serverChat.chat_id || serverChat.id;
    const localChat = chatMap.get(key);

    if (!localChat) {
        chatMap.set(key, serverChat);
        return;
    }

    const localTime = toTime(localChat.updatedAt || localChat.updated_at || localChat.createdAt || localChat.created_at);
    const serverTime = toTime(serverChat.updatedAt || serverChat.updated_at || serverChat.createdAt || serverChat.created_at);

    if (serverTime > localTime) {
        chatMap.set(key, serverChat);
    }
});

        // Convert map back to array
        const mergedChats = Array.from(chatMap.values());
        
        // Sort by updated time
       mergedChats.sort((a, b) => {
    const timeA = new Date(a.updatedAt || a.createdAt).getTime();
    const timeB = new Date(b.updatedAt || b.createdAt).getTime();
    return timeB - timeA; // newest first
});

        // Update global chats array
        window.chats = mergedChats;
        chats = mergedChats;
        
        // Save merged chats to localStorage
        SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(mergedChats));
        
       // Update UI
if (typeof window.renderChatsList === 'function') {
    window.renderChatsList();
}
        
        // If no current chat, load the first one
        if (!currentChatId && mergedChats.length > 0) {
            if (typeof loadChat === 'function') {
                loadChat(mergedChats[0].id);
            }
        }

        console.log('[Sync] ✅ Chats synced successfully:', mergedChats.length, 'total chats');
        
    } catch (error) {
        console.error('[Sync] Failed to sync chats from server:', error);
    }
};

// Sync chats TO server
window.syncChatsToServer = async function() {
    // 🔥 MOBILE PWA FIX: Check network before syncing
    if (!navigator.onLine) {
        console.log('[Sync] Offline - upload queued for when online');
        return;
    }

    if (!window.currentUser) {
        console.log('[Sync] Not authenticated, skipping upload');
        return;
    }


    try {
        const localChats = JSON.parse(SafeStorage.getItem(STORAGE_KEYS.CHATS) || '[]');
        
        if (localChats.length === 0) {
            console.log('[Sync] No chats to sync');
            return;
        }

        console.log('[Sync] Uploading', localChats.length, 'chats to server...');
        
        const deviceId = window.deviceAuth?.getDeviceId?.();

const normalizeISO = (v) => {
    if (!v) return new Date().toISOString();
    if (typeof v === 'number') return new Date(v).toISOString();
    const t = new Date(v).getTime();
    return Number.isFinite(t) ? new Date(t).toISOString() : new Date().toISOString();
};

await window.SyncManager.push(deviceId, {
    chats: localChats.map(chat => ({
        chat_id: chat.chat_id || chat.id,
        title: chat.title || 'Chat',
        messages: chat.messages || [],
        created_at: normalizeISO(chat.createdAt || chat.created_at),
        updated_at: normalizeISO(chat.updatedAt || chat.updated_at || chat.createdAt || chat.created_at)
    }))
});


       console.log('[Sync] ✅ Chats uploaded successfully');

    } catch (error) {
        console.error('[Sync] Failed to sync chats to server:', error);
    }
};

// Auto-sync with adaptive intervals for mobile
let syncInterval = null;

window.startAutoSync = function() {
    if (syncInterval) {
        clearInterval(syncInterval);
    }
    
    const getOptimalSyncInterval = () => {
        const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        
        if (connection) {
            const effectiveType = connection.effectiveType;
            
            if (effectiveType === 'slow-2g' || effectiveType === '2g') {
                return 5 * 60 * 1000;
            }
            
            if (connection.type === 'cellular') {
                return 2 * 60 * 1000;
            }
        }
        
        return 60 * 1000;
    };
    
    const interval = getOptimalSyncInterval();
    
    syncInterval = setInterval(() => {
        if (window.currentUser) {
    syncChatsToServer();
}
    }, interval);
    
    console.log(`[Sync] Auto-sync started (${interval/1000}s intervals)`);
};

window.stopAutoSync = function() {
    if (syncInterval) {
        clearInterval(syncInterval);
        syncInterval = null;
        console.log('[Sync] Auto-sync stopped');
    }
};

window.addEventListener('beforeunload', () => {
    if (!window.currentUser) return;

    const chats = JSON.parse(SafeStorage.getItem(STORAGE_KEYS.CHATS) || '[]');
    if (!chats.length) return;

    const deviceId = window.deviceAuth?.getDeviceId?.();

    const payload = {
        deviceId,
        chats: chats.map(chat => ({
            chat_id: chat.chat_id || chat.id,
            title: chat.title || 'Chat',
            messages: chat.messages || [],
            updated_at: chat.updatedAt || new Date().toISOString()
        }))
    };

    const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
    navigator.sendBeacon('/api/sync/push', blob);
});
