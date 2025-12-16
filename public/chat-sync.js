// =====================================================
// CHAT SYNC MODULE - Cross-Device Synchronization
// =====================================================

// Sync chats FROM server
window.syncChatsFromServer = async function() {
    if (!window.currentUser) {
        console.log('[Sync] Not authenticated, skipping sync');
        return;
    }

    // Add retry mechanism
    let retries = 3;
    while (retries > 0) {
        try {
            console.log('[Sync] Fetching chats from server... (attempt ' + (4 - retries) + '/3)');
        
        const response = await fetch('/api/chats/sync', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include'
        });


        if (!response.ok) {
            if (response.status === 401 || response.status === 403) {
                console.warn('[Sync] Auth failed, attempting session refresh...');
                
                // Try to refresh session
                if (window.authUI && typeof window.authUI.trySilentRefresh === 'function') {
                    const refreshed = await window.authUI.trySilentRefresh();
                    if (refreshed && retries > 1) {
                        retries--;
                        await new Promise(resolve => setTimeout(resolve, 1000));
                        continue; // Retry with fresh auth
                    }
                }
            }
            
            console.warn('[Sync] Failed to fetch chats:', response.status);
            return;
        }

        const data = await response.json();
        
        if (!data.success || !data.chats) {
            console.warn('[Sync] Invalid sync response:', data);
            return;
        }

        console.log('[Sync] Received', data.chats.length, 'chats from server');

        // Merge server chats with local chats
        const localChats = JSON.parse(SafeStorage.getItem(STORAGE_KEYS.CHATS) || '[]');
        const serverChats = data.chats.map(chat => ({
            id: chat.id,
            messages: chat.messages || [],
            title: chat.title || 'Chat',
            createdAt: chat.created_at,
            updatedAt: chat.updated_at
        }));

        // Create a map of chat IDs for quick lookup
        const chatMap = new Map();
        
        // Add local chats first
        localChats.forEach(chat => {
            chatMap.set(chat.id, chat);
        });
        
        // Merge server chats (server takes precedence if newer)
        serverChats.forEach(serverChat => {
            const localChat = chatMap.get(serverChat.id);
            
            if (!localChat) {
                // New chat from server
                chatMap.set(serverChat.id, serverChat);
            } else {
                // Chat exists locally - keep the newer version
                const localTime = new Date(localChat.updatedAt || localChat.createdAt).getTime();
                const serverTime = new Date(serverChat.updatedAt).getTime();
                
                if (serverTime > localTime) {
                    chatMap.set(serverChat.id, serverChat);
                }
            }
        });

        // Convert map back to array
        const mergedChats = Array.from(chatMap.values());
        
        // Sort by updated time
        mergedChats.sort((a, b) => {
            const timeA = new Date(b.updatedAt || b.createdAt).getTime();
            const timeB = new Date(a.updatedAt || a.createdAt).getTime();
            return timeA - timeB;
        });

        // Update global chats array
        window.chats = mergedChats;
        chats = mergedChats;
        
        // Save merged chats to localStorage
        SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(mergedChats));
        
        // Update UI
        if (typeof updateChatsList === 'function') {
            updateChatsList();
        }
        
        // If no current chat, load the first one
        if (!currentChatId && mergedChats.length > 0) {
            if (typeof loadChat === 'function') {
                loadChat(mergedChats[0].id);
            }
        }

        console.log('[Sync] ✅ Chats synced successfully:', mergedChats.length, 'total chats');
        return; // Success, exit retry loop
        
    } catch (error) {
        console.error('[Sync] Failed to sync chats from server:', error);
        
        if (retries > 1) {
            retries--;
            console.log('[Sync] Retrying in 2 seconds...');
            await new Promise(resolve => setTimeout(resolve, 2000));
        } else {
            console.error('[Sync] All retry attempts failed');
            return;
        }
    }
    } // end while loop
};

// Sync chats TO server
window.syncChatsToServer = async function() {
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
        
        const response = await fetch('/api/chats/sync', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ chats: localChats })
        });


        if (!response.ok) {
            console.warn('[Sync] Failed to upload chats:', response.status);
            return;
        }

        const data = await response.json();
        console.log('[Sync] ✅ Chats uploaded successfully:', data.count, 'chats');
        
    } catch (error) {
        console.error('[Sync] Failed to sync chats to server:', error);
    }
};

// Auto-sync every 30 seconds
let syncInterval = null;

window.startAutoSync = function() {
    if (syncInterval) {
        clearInterval(syncInterval);
    }
    
    syncInterval = setInterval(() => {
        if (window.currentUser && window.authToken) {
            syncChatsToServer();
        }
    }, 30000); // 30 seconds
    
    console.log('[Sync] Auto-sync started (30s intervals)');
};

window.stopAutoSync = function() {
    if (syncInterval) {
        clearInterval(syncInterval);
        syncInterval = null;
        console.log('[Sync] Auto-sync stopped');
    }
};

// Sync on page unload
window.addEventListener('beforeunload', () => {
    if (window.currentUser && window.authToken) {
        const chats = JSON.parse(SafeStorage.getItem(STORAGE_KEYS.CHATS) || '[]');
        if (chats.length > 0) {
            const blob = new Blob([JSON.stringify({ chats })], { type: 'application/json' });
            navigator.sendBeacon('/api/chats/sync', blob);
        }
    }
});
