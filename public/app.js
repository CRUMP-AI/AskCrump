/*
==========================================
CRUMP AI - MAIN APPLICATION v1.0 FIXED
Complete with all fixes + autonomous corrections
==========================================
*/

// Storage Keys
const STORAGE_KEYS = {
    CHATS: 'crump_chats',
    CURRENT_CHAT: 'crump_current_chat',
    USER_PROFILE: 'crump_user_profile',
    USER_INITIAL: 'crump_user_initial',
    ASSISTANT_NAME: 'crump_assistant_name',
    WORK_MODE: 'crump_work_mode',
    AUTONOMOUS_ENABLED: 'crump_autonomous_enabled',
    AUTONOMOUS_FREQUENCY: 'crump_autonomous_frequency',
    HAS_ONBOARDED: 'crump_has_onboarded'
};

// Safari ITP Detection & Fallback Storage
const STORAGE_AVAILABLE = (function() {
    try {
        const test = '__storage_test__';
        localStorage.setItem(test, test);
        localStorage.removeItem(test);
        return true;
    } catch(e) {
        console.warn('⚠️ localStorage blocked by browser - using memory fallback');
        return false;
    }
})();

// Safe Storage Wrapper (handles Safari ITP blocking)
const SafeStorage = {
    _memoryCache: {},
    
    getItem(key) {
        if (STORAGE_AVAILABLE) {
            return localStorage.getItem(key);
        }
        return this._memoryCache[key] || null;
    },
    
    setItem(key, value) {
        if (STORAGE_AVAILABLE) {
            localStorage.setItem(key, value);
        }
        this._memoryCache[key] = value;
    },
    
    removeItem(key) {
        if (STORAGE_AVAILABLE) {
            localStorage.removeItem(key);
        }
        delete this._memoryCache[key];
    },
    
    clear() {
        if (STORAGE_AVAILABLE) {
            localStorage.clear();
        }
        this._memoryCache = {};
    }
};

// Export for global use
window.SafeStorage = SafeStorage;

// Global State
let chats = [];
let currentChatId = null;
let currentProfile = null;
let selectedFiles = [];
let isProcessing = false;
window.chats = chats;
window.currentChatId = currentChatId;
window.STORAGE_KEYS = STORAGE_KEYS;
let activeObjectURLs = [];
window.activeObjectURLs = activeObjectURLs;

// ==========================================
// AUTHENTICATED APP INITIALIZATION
// ==========================================
window.initializeAuthenticatedApp = function(user) {
    console.log('🔐 Initializing app for authenticated user:', user.email);
    
    // Store user info globally
    window.currentUser = user;
    
    // Update universal memory with user profile
    if (typeof window.universalMemory !== 'undefined') {
        window.universalMemory.userProfile = {
            name: user.fullName || user.email.split('@')[0],
            email: user.email,
            userId: user.id,
            assistantName: user.preferences?.assistantName || 'Crump',
            createdAt: user.createdAt
        };
    }
    
    // Update settings with user's preferences
    if (user.preferences) {
        if (user.preferences.assistantName) {
            SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
        }
        if (user.preferences.workMode !== undefined) {
            localStorage.setItem(STORAGE_KEYS.WORK_MODE, user.preferences.workMode);
        }
        if (user.preferences.autonomousEnabled !== undefined) {
            localStorage.setItem(STORAGE_KEYS.AUTONOMOUS_ENABLED, user.preferences.autonomousEnabled);
        }
    }
    
        console.log('✅ User profile loaded into universalMemory');
    
    // Load user's chats from database (cross-device)
    if (typeof syncChatsFromServer === 'function') {
        syncChatsFromServer();
    }
};

// ==========================================
// INITIALIZATION
// ==========================================
window.initializeApp = function() {
    try {
        const required = ['chatContainer', 'userInput', 'sendButton', 'newChatBtn', 'chatsList', 'fileInput'];
        const missing = required.filter(id => !document.getElementById(id));
        if (missing.length > 0) {
            throw new Error('Missing elements: ' + missing.join(', '));
        }
       console.log('🚀 Crump AI v1.0 initializing...');

        // ✅ CRITICAL FIX: Initialize universalMemory FIRST
        if (typeof window.universalMemory === 'undefined') {
            window.universalMemory = {
                autonomousHistory: [],
                userProfile: {},
                crossSessionContext: [],
                conversationHistory: {}
            };
        }
        
        // Load autonomous history from localStorage if it exists
        try {
            const savedAutonomousHistory = localStorage.getItem('crump_autonomous_history');
            if (savedAutonomousHistory) {
                window.universalMemory.autonomousHistory = JSON.parse(savedAutonomousHistory);
                console.log('✅ Loaded autonomous history:', window.universalMemory.autonomousHistory.length, 'messages');
            }
        } catch (e) {
            console.warn('⚠️ Failed to load autonomous history:', e);
        }

      // Initialize profile manager
if (typeof window.ProfileManager !== 'undefined') {
    currentProfile = new ProfileManager();
    window.currentProfile = currentProfile;
    window.profileManager = currentProfile; // alias for upgrade-ui & others
    updateUserAvatar();
} else if (typeof window.UserProfileManager !== 'undefined') {
    currentProfile = new UserProfileManager();
    window.currentProfile = currentProfile;
    window.profileManager = currentProfile; // alias for upgrade-ui & others
    updateUserAvatar();
}

        // Initialize components
        if (typeof window.messageDeduplicator === 'undefined') {
            window.messageDeduplicator = new MessageDeduplicator();
        }

       if (typeof window.WeatherDetectionEngine !== 'undefined') {
            window.weatherDetectionEngine = new WeatherDetectionEngine();
            console.log('✅ Weather Detection Engine initialized');
        }
        
        // Initialize sentiment analyzer
        if (typeof window.SentimentAnalyzer !== 'undefined') {
            window.sentimentAnalyzer = new SentimentAnalyzer();
            console.log('✅ Sentiment Analyzer initialized');
        }
        
        // Initialize context tracker
        if (typeof window.AutonomousContextTracker !== 'undefined') {
            window.contextTracker = new AutonomousContextTracker();
            console.log('✅ Context Tracker initialized');
        }

               loadChats();

        // If user is logged in, pull down cloud chats for cross-device sync
        if (typeof syncChatsFromServer === 'function' && window.currentUser && window.currentUser.id) {
            syncChatsFromServer();
        }

        setupEventListeners();
        setupSidebarToggle();
        loadSettings();
        updateAssistantNameDisplay();
        initializeAssistant();

        
        // CRITICAL: Initialize scroll manager AFTER app is ready
        if (window.crumpScrollManager && typeof window.crumpScrollManager.init === 'function') {
            window.crumpScrollManager.init();
            console.log('✅ Scroll manager initialized');
        }

        const savedChatId = localStorage.getItem(STORAGE_KEYS.CURRENT_CHAT);
        if (savedChatId && getChat(savedChatId)) {
            loadChat(savedChatId);
        } else {
            createNewChat();
        }

       setupAutonomousMessaging();
        setupMobileKeyboardHandler(); // ADDED
        
        console.log('✅ Crump AI v1.0 initialized successfully');
        if (localStorage.getItem(STORAGE_KEYS.HAS_ONBOARDED) === 'true' && !savedChatId) {
            showWelcomeMessage();
        }

    } catch (error) {
        console.error('❌ Initialization error:', error);
        showToast('Failed to initialize application', 'error');
    }
};

// ==========================================
// EVENT LISTENERS
// ==========================================
function setupEventListeners() {
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    const newChatBtn = document.getElementById('newChatBtn');
    const attachBtn = document.getElementById('attachBtn');
    const fileInput = document.getElementById('fileInput');
    const voiceBtn = document.getElementById('voiceBtn');

    // Send message
    sendButton.addEventListener('click', () => sendMessage());

    // Enter to send (Shift+Enter for new line)
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = userInput.scrollHeight + 'px';
    });

    // New chat
    newChatBtn.addEventListener('click', () => createNewChat());

    // File attachment
    attachBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileSelect);

    // Voice input
    if (voiceBtn) {
        voiceBtn.addEventListener('click', handleVoiceInput);
    }
}

function setupSidebarToggle() {
    const menuBtn = document.getElementById('menuBtn');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const closeSidebarBtn = document.getElementById('closeSidebarBtn');

    if (menuBtn && sidebar && sidebarOverlay) {
        menuBtn.addEventListener('click', () => {
            sidebar.classList.add('active');
            sidebarOverlay.classList.add('active');
        });

        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
        });

        if (closeSidebarBtn) {
            closeSidebarBtn.addEventListener('click', () => {
                sidebar.classList.remove('active');
                sidebarOverlay.classList.remove('active');
            });
        }
    }
}

// ==========================================
// CHAT MANAGEMENT
// ==========================================
function loadChats() {
    try {
        const saved = SafeStorage.getItem(STORAGE_KEYS.CHATS);
        if (saved) {
            try {
                chats = JSON.parse(saved);
                window.chats = chats;
            } catch (e) {
                console.error('Failed to parse chats:', e);
                chats = [];
                window.chats = chats;
            }
        }
    } catch (storageError) {
        console.warn('⚠️ localStorage unavailable (private browsing?)');
        chats = [];
        window.chats = chats;
    }
    renderChatsList();
}

function saveChats() {
    // Always keep the local copy for offline / guest mode
    try {
        SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
    } catch (storageError) {
        console.warn('⚠️ Failed to save chats (localStorage unavailable)', storageError);
    }

    // If the user is logged in, also sync to the server
    if (window.currentUser && window.currentUser.id && typeof syncChatsToServer === 'function') {
        // fire-and-forget: don't block the UI
        try {
            syncChatsToServer();
        } catch (e) {
            console.warn('⚠️ syncChatsToServer threw synchronously:', e);
        }
    }
}
window.saveChats = saveChats;

// ==========================================
// CHAT SYNC HELPERS (Supabase-backed)
// ==========================================
async function syncChatsFromServer() {
    if (!window.currentUser || !window.currentUser.id) {
        console.log('ℹ️ No authenticated user; skipping server chat load');
        return;
    }

    try {
        console.log('☁️ Pulling chats from server...');
       const res = await fetch('/api/chats', {
    method: 'GET',
    headers: {
        'Content-Type': 'application/json'
    },
    credentials: 'include'
});

        if (!res.ok) {
            console.warn('⚠️ /api/chats GET failed with status', res.status);
            return;
        }

        const data = await res.json();
        const serverChats = data?.chats || [];

        // If server has no chats but local does, push local up instead
        if (serverChats.length === 0 && Array.isArray(chats) && chats.length > 0) {
            console.log('☁️ No server chats yet, pushing local chats up...');
            await syncChatsToServer();
            return;
        }

        // Replace local chats with server copy
        chats = serverChats;
        window.chats = chats;

        // Decide which chat to open
        const savedChatId = localStorage.getItem(STORAGE_KEYS.CURRENT_CHAT);
        let targetChatId = null;

        if (savedChatId && serverChats.some(c => c.id === savedChatId)) {
            targetChatId = savedChatId;
        } else if (serverChats[0]) {
            targetChatId = serverChats[0].id;
        }

        currentChatId = targetChatId;
        window.currentChatId = currentChatId || null;

        // Mirror chats into localStorage for offline usage
        try {
            SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
            if (currentChatId) {
                localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, currentChatId);
            }
        } catch (e) {
            console.warn('⚠️ Failed to persist server chats to localStorage', e);
        }

        // Update UI
        renderChatsList();
        if (currentChatId) {
            const chat = chats.find(c => c.id === currentChatId);
            if (chat) {
                if (window.renderMessages) {
                    window.renderMessages(chat.messages || []);
                } else {
                    legacyRenderMessages(chat.messages || []);
                }
            }
        }

        console.log(`✅ Synced ${chats.length} chats from server`);
    } catch (err) {
        console.error('❌ Error syncing chats from server:', err);
    }
}
window.syncChatsFromServer = syncChatsFromServer;

async function syncChatsToServer() {
    if (!window.currentUser || !window.currentUser.id) {
        // Not logged in; nothing to sync
        return;
    }

    try {
        const payload = {
            chats: Array.isArray(chats) ? chats : []
        };

        const res = await fetch('/api/chats', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    credentials: 'include',
    body: JSON.stringify(payload)
});

        if (!res.ok) {
            console.warn('⚠️ /api/chats POST failed with status', res.status);
            return;
        }

        const data = await res.json();
        if (!data.success) {
            console.warn('⚠️ Chat sync API returned error:', data.error);
        } else {
            console.log('☁️ Chats synced to server for user', window.currentUser.email);
        }
    } catch (err) {
        console.warn('⚠️ Error syncing chats to server:', err);
    }
}
window.syncChatsToServer = syncChatsToServer;
window.syncChatsFromServer = syncChatsFromServer;

function createNewChat() {
    const chat = {
        id: 'chat_' + Date.now(),
        title: 'New Conversation',
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now()
    };

    chats.unshift(chat);
    currentChatId = chat.id;
    window.currentChatId = currentChatId;

    // CRITICAL FIX: Reset image generation state for new chat
if (window.resetImageGenerationState) {
    window.resetImageGenerationState();
    console.log('🔄 Image generation state reset for new chat');
}

    saveChats();
    localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, currentChatId);

   renderChatsList();
if (window.renderMessages) {
    window.renderMessages([]);
} else {
    legacyRenderMessages([]);
}


    document.getElementById('userInput').value = '';
    document.getElementById('userInput').focus();

    console.log('✅ New chat created:', chat.id);
}

function loadChat(chatId) {
    const chat = chats.find(c => c.id === chatId);
    if (!chat) return;

    currentChatId = chatId;
    window.currentChatId = currentChatId;
    localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, chatId);

    // CRITICAL FIX: Reset image generation state when switching chats
if (window.resetImageGenerationState) {
    window.resetImageGenerationState();
    console.log('🔄 Image generation state reset for new chat');
}

   renderChatsList();
if (window.renderMessages) {
    window.renderMessages(chat.messages);
} else {
    legacyRenderMessages(chat.messages);
}


    console.log('📖 Chat loaded:', chatId);
}

function getChat(chatId) {
    return chats.find(c => c.id === chatId);
}

function deleteChat(chatId) {
    if (!confirm('Delete this conversation?')) return;

    chats = chats.filter(c => c.id !== chatId);
    window.chats = chats;
    saveChats();

    if (currentChatId === chatId) {
        if (chats.length > 0) {
            loadChat(chats[0].id);
        } else {
            createNewChat();
        }
    }

    renderChatsList();
    console.log('🗑️ Chat deleted:', chatId);
}
window.deleteChat = deleteChat;

function clearAllChats() {
    if (!confirm('Clear all conversations? This cannot be undone.')) return;

    chats = [];
    window.chats = chats;
    saveChats();
    createNewChat();

    showToast('All conversations cleared', 'success');
}
window.clearAllChats = clearAllChats;

function renderChatsList() {
    const chatsList = document.getElementById('chatsList');
    if (!chatsList) return;
    
    chatsList.innerHTML = chats.map(chat => `
        <div class="chat-item ${chat.id === currentChatId ? 'active' : ''}" onclick="loadChat('${chat.id}')">
            <div class="chat-item-content">
                <div class="chat-title">${escapeHtml(chat.title)}</div>
                <div class="chat-preview">${chat.messages.length} messages</div>
            </div>
            <button class="delete-chat-btn" onclick="event.stopPropagation(); deleteChat('${chat.id}')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                </svg>
            </button>
        </div>
    `).join('');
}

// ==========================================
// MESSAGE RENDERING (LEGACY - fallback only)
// ==========================================
function legacyRenderMessages(messages) {
    const container = document.getElementById('chatContainer');
    if (!container) return;
    
    container.innerHTML = '';
    
    messages.forEach((msg, index) => {
        const messageEl = legacyCreateMessageElement(msg, index);
        container.appendChild(messageEl);
    });
    
    // Scroll to bottom after render
    setTimeout(() => {
        if (window.crumpScrollManager) {
            window.crumpScrollManager.scrollToBottom(true);
        } else {
            container.scrollTop = container.scrollHeight;
        }
    }, 100);
}


function legacyCreateMessageElement(msg, index) {
    const div = document.createElement('div');
    div.className = `message ${msg.role}`;
    div.dataset.index = index;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    
    if (msg.role === 'user') {
        const initial = currentProfile?.profile?.initial || localStorage.getItem(STORAGE_KEYS.USER_INITIAL) || 'U';
        avatar.textContent = initial;
    } else {
        avatar.innerHTML = '<img src="/assets/logo-c.png" alt="Assistant" style="width: 100%; height: 100%; object-fit: contain;">';
    }
    
    const content = document.createElement('div');
    content.className = 'message-content';
    
    // Handle uploaded images (from user fileData)
    if (msg.fileData && Array.isArray(msg.fileData) && msg.fileData.length > 0) {
        msg.fileData.forEach(file => {
            if (file.type && file.type.startsWith('image/') && file.data) {
                const img = document.createElement('img');
                img.src = file.data;
                img.style.cssText = 'max-width: 300px; border-radius: 8px; margin-bottom: 0.5rem; display: block;';
                img.alt = file.name || 'Uploaded image';
                content.appendChild(img);
            }
        });
    }
    
    // Handle old imageData format (backward compatibility)
    if (msg.imageData) {
        const img = document.createElement('img');
        img.src = msg.imageData;
        img.style.maxWidth = '300px';
        img.style.borderRadius = '8px';
        img.style.marginBottom = '0.5rem';
        content.appendChild(img);
    }
    
    const text = document.createElement('div');
    text.className = 'message-text';
    
    if (msg.role === 'assistant' && window.renderMarkdown) {
        text.innerHTML = window.renderMarkdown(msg.content);
    } else {
        text.textContent = msg.content;
    }
    
    content.appendChild(text);

   // Handle generated images with better error feedback and loading states
    if (msg.imageUrl) {
        const imgWrapper = document.createElement('div');
        imgWrapper.className = 'generated-image-wrapper';
        imgWrapper.style.cssText = 'margin-top: 0.5rem; position: relative;';
        
        // Add loading indicator
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'image-loading';
        loadingDiv.textContent = 'Loading image...';
        loadingDiv.style.cssText = 'padding: 2rem; background: var(--color-surface); border-radius: 8px; text-align: center; color: var(--color-text-secondary);';
        imgWrapper.appendChild(loadingDiv);
        
        const img = document.createElement('img');
        img.style.cssText = 'max-width: 100%; border-radius: 8px; display: none;';
        img.alt = 'Generated image';
        img.crossOrigin = 'anonymous'; // CORS fix
        
        img.onload = function() {
            loadingDiv.remove();
            this.style.display = 'block';
            console.log('✅ Image rendered successfully');
        };
        
        img.onerror = function() {
            loadingDiv.innerHTML = `
                <div style="color: var(--color-error); padding: 1rem;">
                    ❌ Image failed to load
                    <br><small>This may be a temporary issue with the image service.</small>
                    <br><button onclick="location.reload()" style="margin-top: 0.5rem; padding: 0.5rem 1rem; cursor: pointer; background: var(--color-primary); color: white; border: none; border-radius: 4px;">Retry</button>
                </div>
            `;
        };
        
        img.src = msg.imageUrl;
        imgWrapper.appendChild(img);
        content.appendChild(imgWrapper);
    }
    
    div.appendChild(avatar);
    div.appendChild(content);
    
    return div;
}

// ==========================================
// SEND MESSAGE (CRITICAL FUNCTION)
// ==========================================
async function sendMessage() {
    if (isProcessing) return;

    const userInput = document.getElementById('userInput');
    const message = userInput.value.trim();

    if (!message && selectedFiles.length === 0) return;

    // Enforce plan message limits before sending
    if (window.currentProfile && typeof window.currentProfile.canSendMessage === 'function') {
        const canSend = window.currentProfile.canSendMessage();

        if (!canSend.allowed) {
            if (window.showToast) {
                window.showToast(
                    canSend.message || 'Message limit reached for your current plan',
                    'error'
                );
            }
            if (typeof window.showUpgradePrompt === 'function') {
                setTimeout(() => window.showUpgradePrompt(), 300);
            }
            return;
        }

        if (canSend.warning && window.showToast) {
            window.showToast(canSend.warning, 'warning');
        }
    }

    const chat = chats.find(c => c.id === currentChatId);
    if (!chat) {
        console.error('No active chat');
        return;
    }


    // ========================================
    // CONSCIOUSNESS COMMAND DETECTION (NEW)
    // ========================================
    if (window.isConsciousnessCommand && window.isConsciousnessCommand(message)) {
        console.log('🧠 Consciousness command detected');
        
        const consciousness = new window.ConsciousnessIntegration();
        const result = consciousness.handleConsciousnessCommand(message);
        
        // Add user message
        chat.messages.push({
            role: 'user',
            content: message,
            timestamp: Date.now()
        });
        
        // Add consciousness response
        chat.messages.push({
            role: 'assistant',
            content: result.message,
            timestamp: Date.now()
        });
        
        // Update UI
saveChats();
if (window.renderMessages) {
    window.renderMessages(chat.messages);
} else {
    legacyRenderMessages(chat.messages);
}

        
        // Clear input
        userInput.value = '';
        userInput.style.height = 'auto';
        
        // Exit early - don't process as normal message
        return;
    }
    // ========================================
    // END CONSCIOUSNESS COMMAND DETECTION
    // ========================================
    
    isProcessing = true;
    
    try {
        // Create user message
        const userMessage = {
            role: 'user',
            content: message || '',
            timestamp: Date.now()
        };
        
        // Handle file attachment FIRST (before clearing)
        let fileData = null;
        let fileType = null;
        let fileName = null;
        
        if (selectedFiles.length > 0) {
            const file = selectedFiles[0];
            console.log('📎 Processing file:', file.name, file.type, file.size);
            fileData = await readFileAsBase64(file);
            fileType = file.type;
            fileName = file.name;
            console.log('✅ File data captured:', fileType, fileName);
        }
        
        // CRITICAL FIX: Always use array structure, even for single file
        if (fileData && fileType) {
            userMessage.fileData = [{
                type: fileType,
                data: fileData,
                name: fileName
            }];
        }
        
              // Add user message to chat
        chat.messages.push(userMessage);
        saveChats();

        // Track message usage against current plan
        if (window.currentProfile && typeof window.currentProfile.incrementUsage === 'function') {
            try {
                window.currentProfile.incrementUsage('messages');
            } catch (e) {
                console.warn('[App] Failed to increment message usage:', e);
            }
        }

if (window.renderMessages) {
    window.renderMessages(chat.messages);
} else {
    legacyRenderMessages(chat.messages);
}

        
        // Scroll to user's message immediately
        setTimeout(() => {
            if (window.crumpScrollManager) {
                window.crumpScrollManager.scrollToBottom('auto');
            }
        }, 100);
        
        // Show read receipt on user's message
        setTimeout(() => {
            const messages = document.querySelectorAll('.message.user');
            const lastUserMessage = messages[messages.length - 1];
            if (lastUserMessage) {
                showReadReceipt(lastUserMessage);
            }
        }, 300);
        
        // Clear input and files
        userInput.value = '';
        userInput.style.height = 'auto';

        // CRITICAL FIX: Reset file input element
        const fileInput = document.getElementById('fileInput');
        if (fileInput) {
            fileInput.value = '';
            console.log('🧹 File input reset');
        }

        selectedFiles = [];
        displayFilePreview();
        
        // Show thinking
        showThinking();
        setAssistantState('thinking');
        
        // Detect if search is needed
        let needsSearch = false;
        if (window.searchDetectionEngine) {
            needsSearch = window.searchDetectionEngine.needsSearch(message);
        }
        
        // Detect if weather is needed
        let needsWeather = false;
        if (window.weatherDetectionEngine) {
            needsWeather = window.weatherDetectionEngine.needsWeather(message);
        }

        // Prepare request with accurate time awareness
        const timeInfo = window.timeAwareness ? window.timeAwareness.getCurrentDateTime() : null;
        
        const requestBody = {
            message: message,
            history: chat.messages.map(m => ({
                role: m.role,
                content: m.content
            })),
            currentDateTime: timeInfo ? {
                date: timeInfo.date,
                time: timeInfo.time,
                timezone: timeInfo.timezone,
                timezoneAbbr: timeInfo.timezoneAbbr,
                dayOfWeek: timeInfo.dayOfWeek,
                period: timeInfo.period,
                hour: timeInfo.hour,
                iso: timeInfo.iso,
                timestamp: timeInfo.timestamp,
                fullContext: timeInfo.fullContext
            } : {
                date: new Date().toLocaleDateString('en-US', { 
                    weekday: 'long', 
                    year: 'numeric', 
                    month: 'long', 
                    day: 'numeric',
                    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
                }),
                time: new Date().toLocaleTimeString('en-US', { 
                    hour: 'numeric', 
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: true,
                    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
                }),
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                iso: new Date().toISOString(),
                timestamp: Date.now()
            },
            needsSearch: needsSearch,
            needsWeather: needsWeather,
            workMode: localStorage.getItem(STORAGE_KEYS.WORK_MODE) === 'true' ? 'work' : 'companion',
            universalMemory: window.universalMemory || {},
            
            // PASS USER DATA FOR CRUMP TO KNOW WHO'S TALKING
            user: window.currentUser ? {
                id: window.currentUser.id,
                email: window.currentUser.email,
                name: window.currentUser.fullName || window.currentUser.email.split('@')[0]
            } : null,
            
            // CHECK FOR RECENT UPGRADE
            recentUpgrade: (() => {
                const upgradeStr = localStorage.getItem('crump_recent_upgrade');
                if (!upgradeStr) return null;
                
                const upgrade = JSON.parse(upgradeStr);
                const ageMinutes = (Date.now() - upgrade.timestamp) / 60000;
                
                if (ageMinutes < 10) {
                    localStorage.removeItem('crump_recent_upgrade');
                    return upgrade;
                }
                
                localStorage.removeItem('crump_recent_upgrade');
                return null;
            })(),
            
            // PASS RECENT CHANGES FOR ACKNOWLEDGMENT
            recentChanges: (() => {
                const changesStr = localStorage.getItem('crump_recent_changes');
                if (!changesStr) return null;
                
                const changes = JSON.parse(changesStr);
                const ageMinutes = (Date.now() - changes.timestamp) / 60000;
                
                if (ageMinutes < 5) {
                    localStorage.removeItem('crump_recent_changes');
                    return changes;
                }
                
                localStorage.removeItem('crump_recent_changes');
                return null;
            })()
        };
        
        // Add file data if present
        if (fileData && fileType) {
            console.log('📤 Sending file to API:', fileType, fileName);
            
            let cleanBase64 = fileData;
            if (fileData.includes(',')) {
                cleanBase64 = fileData.split(',')[1];
                console.log('✂️ Stripped data URL prefix, clean base64 ready');
            }
            
            requestBody.fileData = [{
                type: fileType,
                data: `data:${fileType};base64,${cleanBase64}`,
                name: fileName
            }];
            
            console.log('✅ File data formatted for API:', fileType, fileName, `${cleanBase64.substring(0, 50)}...`);
        }
        
        // Call API
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();

        // ⭐ AUTO-RETRY LOGIC FOR FAILED REQUESTS
        if (!response.ok && data.shouldRetry) {
            const retryAfter = data.retryAfter || 10;
            console.log(`🔄 Error ${data.code}, retrying in ${retryAfter}s...`);
            
            // Show retry message to user
            const retryMessage = document.createElement('div');
            retryMessage.className = 'message assistant-message';
            retryMessage.innerHTML = `<div class="message-content">⚠️ ${data.message} Retrying in ${retryAfter} seconds...</div>`;
            chatContainer.appendChild(retryMessage);
            scrollToBottom();
            
            // Wait and retry
            await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
            
            // Remove retry message
            retryMessage.remove();
            
            // Retry the request (recursive call)
            return sendMessage();
        }
        
        // If error and shouldn't retry, throw
        if (!response.ok) {
            throw new Error(data.message || data.error || 'Request failed');
        }

        console.log('📥 API Response:', {
            hasResponse: !!data.response,
            hasImage: !!data.imageUrl,
            model: data.model,
            responseLength: data.response?.length
        });
        
        // Add assistant response
        const assistantMessage = {
            role: 'assistant',
            content: data.response,
            timestamp: Date.now()
        };
        
        // Add image data if present
        if (data.imageUrl) {
            console.log('🎨 Response includes generated image');
            assistantMessage.imageUrl = data.imageUrl;
            assistantMessage.imagePrompt = data.imagePrompt;
        }
        
        chat.messages.push(assistantMessage);
        chat.updatedAt = Date.now();
        
        // Update chat title if first exchange
        if (chat.messages.length <= 2 && message) {
            chat.title = message.substring(0, 50) + (message.length > 50 ? '...' : '');
        }
        
        saveChats();
if (window.renderMessages) {
    window.renderMessages(chat.messages);
} else {
    legacyRenderMessages(chat.messages);
}
renderChatsList();


        // Notify autonomous system that user sent a message
        if (window.autonomousMessaging) {
            window.autonomousMessaging.onUserResponse(message);
            
            // Check if this is a response to an autonomous message
            const lastAssistantMsg = chat.messages.slice().reverse().find(m => m.role === 'assistant' && m.autonomous);
            if (lastAssistantMsg) {
                // User is responding to Crump's autonomous message - record the response
                window.autonomousMessaging.recordAutonomousMessage(lastAssistantMsg.content, message);
            }
        }
        
        // Track sentiment and context
        if (window.sentimentAnalyzer && window.contextTracker && message) {
            // Analyze emotional state
            const sentiment = window.sentimentAnalyzer.analyze(message);
            window.sentimentAnalyzer.trackEmotionHistory(sentiment);
            
            // Track activity and topics
            window.contextTracker.recordActivity('message');
            window.contextTracker.trackTopics(message);
            
            // Sync to universalMemory
            if (!window.universalMemory) {
                window.universalMemory = {};
            }
            window.universalMemory.sentimentState = sentiment;
            window.universalMemory.contextSummary = window.contextTracker.getContextSummary();
            
            console.log('📊 Sentiment:', sentiment.emotion, '| Confidence:', sentiment.confidence.toFixed(2));
        }
        
        // Scroll to show new assistant message
        setTimeout(() => {
            if (window.crumpScrollManager) {
                window.crumpScrollManager.scrollToBottom('smooth');
            } else {
                const container = document.getElementById('chatContainer');
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
            }
        }, 200);  
        
        // Hide thinking
        hideThinking();
        setAssistantState('idle');
        
    } catch (error) {
        console.error('Error sending message:', error);
        hideThinking();
        setAssistantState('idle');
        showToast('Failed to send message: ' + error.message, 'error');
    } finally {
        isProcessing = false;
    }
}
window.sendMessage = sendMessage;

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// ==========================================
// FILE HANDLING
// ==========================================
function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    selectedFiles = files;
    displayFilePreview();
    e.target.value = '';
}

function displayFilePreview() {
    const preview = document.getElementById('filePreview');
    if (!preview) return;
    
    // Clean up previous object URLs
    if (window.activeObjectURLs) {
        window.activeObjectURLs.forEach(url => {
            try {
                URL.revokeObjectURL(url);
            } catch (e) {
                console.warn('Failed to revoke URL:', e);
            }
        });
        window.activeObjectURLs = [];
    }
    
    if (selectedFiles.length === 0) {
        preview.style.display = 'none';
        return;
    }
    
    preview.style.display = 'block';
    preview.innerHTML = '';
    
    selectedFiles.forEach((file, index) => {
    const fileDiv = document.createElement('div');
    fileDiv.className = 'file-preview-item';
    fileDiv.style.cssText = `
        display: flex;
        align-items: center;
        padding: 0.75rem;
        background: var(--color-bg-secondary);
        border-radius: 8px;
        margin-bottom: 0.5rem;
    `;
    
    // File icon based on type
    let icon = '📄';
    if (file.type.startsWith('image/')) icon = '🖼️';
    else if (file.type === 'application/pdf') icon = '📕';
    else if (file.type.includes('zip') || file.name.endsWith('.zip')) icon = '🗜️';
    else if (file.name.endsWith('.7z')) icon = '📦';
    else if (file.name.endsWith('.tar.gz')) icon = '📦';
    else if (file.name.endsWith('.rar')) icon = '📦';
    
    // Format file size
    const sizeKB = (file.size / 1024).toFixed(1);
    const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
    const displaySize = file.size > 1024 * 1024 ? `${sizeMB} MB` : `${sizeKB} KB`;
    
    fileDiv.innerHTML = `
        <span style="font-size: 1.5rem; margin-right: 0.75rem;">${icon}</span>
        <div style="flex: 1; min-width: 0;">
            <div style="font-weight: 500; color: var(--color-text-primary); 
                        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                ${file.name}
            </div>
            <div style="font-size: 0.875rem; color: var(--color-text-secondary);">
                ${displaySize}
            </div>
        </div>
        <button onclick="removeFile(${index})" 
                style="background: none; border: none; color: var(--color-text-secondary); 
                       cursor: pointer; font-size: 1.25rem; padding: 0.25rem 0.5rem;">
            ×
        </button>
    `;
    
    preview.appendChild(fileDiv);
});
        
        // If it's an image, show LARGE preview
        if (file.type.startsWith('image/')) {
            const imgWrapper = document.createElement('div');
            imgWrapper.style.cssText = 'position: relative; width: 200px; height: 200px; overflow: hidden; display: flex; align-items: center; justify-content: center; background: var(--color-bg-tertiary);';
            
            const img = document.createElement('img');
            img.style.cssText = 'max-width: 100%; max-height: 100%; object-fit: contain;';
            img.alt = file.name;
            
            const objectURL = URL.createObjectURL(file);
            if (!window.activeObjectURLs) window.activeObjectURLs = [];
            window.activeObjectURLs.push(objectURL);
            img.src = objectURL;
            
            const cleanup = () => {
                const urlIndex = window.activeObjectURLs.indexOf(objectURL);
                if (urlIndex > -1) {
                    try {
                        URL.revokeObjectURL(objectURL);
                        window.activeObjectURLs.splice(urlIndex, 1);
                    } catch (e) {
                        console.warn('Failed to revoke URL:', e);
                    }
                }
            };
            
            img.onload = cleanup;
            img.onerror = () => {
                cleanup();
                imgWrapper.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--color-text-secondary);">❌<br>Preview failed</div>';
            };
            
            imgWrapper.appendChild(img);
            
            // File name overlay
            const nameOverlay = document.createElement('div');
            nameOverlay.style.cssText = 'position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(transparent, rgba(0,0,0,0.7)); color: white; padding: 0.5rem; font-size: 0.75rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
            nameOverlay.textContent = file.name;
            nameOverlay.title = file.name;
            imgWrapper.appendChild(nameOverlay);
            
            container.appendChild(imgWrapper);
        } else {
            // For non-images, show file icon
            const fileDisplay = document.createElement('div');
            fileDisplay.style.cssText = 'width: 200px; height: 200px; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 1rem; text-align: center;';
            
            const iconDiv = document.createElement('div');
            iconDiv.style.cssText = 'font-size: 4rem; margin-bottom: 1rem;';
            iconDiv.textContent = file.type.includes('pdf') ? '📄' : '📎';
            
            const nameDiv = document.createElement('div');
            nameDiv.style.cssText = 'font-size: 0.875rem; font-weight: 500; word-break: break-word; color: var(--color-text-primary);';
            nameDiv.textContent = file.name;
            
            const sizeDiv = document.createElement('div');
            sizeDiv.style.cssText = 'font-size: 0.75rem; color: var(--color-text-tertiary); margin-top: 0.25rem;';
            sizeDiv.textContent = `${(file.size / 1024).toFixed(1)} KB`;
            
            fileDisplay.appendChild(iconDiv);
            fileDisplay.appendChild(nameDiv);
            fileDisplay.appendChild(sizeDiv);
            container.appendChild(fileDisplay);
        }
        
        // BIG RED DELETE BUTTON
        const removeBtn = document.createElement('button');
        removeBtn.innerHTML = '×';
        removeBtn.title = 'Remove file';
        removeBtn.style.cssText = `
            position: absolute;
            top: 8px;
            right: 8px;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: rgba(239, 68, 68, 0.9);
            color: white;
            border: 2px solid white;
            font-size: 1.5rem;
            line-height: 1;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            z-index: 10;
        `;
        
        removeBtn.onmouseover = () => {
            removeBtn.style.background = 'rgba(220, 38, 38, 1)';
            removeBtn.style.transform = 'scale(1.1)';
        };
        
        removeBtn.onmouseout = () => {
            removeBtn.style.background = 'rgba(239, 68, 68, 0.9)';
            removeBtn.style.transform = 'scale(1)';
        };
        
        removeBtn.onclick = (e) => {
            e.stopPropagation();
            removeFile(index);
        };
        
        container.appendChild(removeBtn);
        preview.appendChild(container);
    });
    
    // Status text
    if (selectedFiles.length > 0) {
        const helpText = document.createElement('div');
        helpText.style.cssText = 'padding: 0.5rem 1rem; font-size: 0.875rem; color: var(--color-text-secondary); text-align: center;';
        helpText.innerHTML = `
            <span style="color: var(--color-accent-primary); font-weight: 500;">${selectedFiles.length} file${selectedFiles.length > 1 ? 's' : ''} ready to send</span>
            <br><small>Click × to remove • Press Send to upload</small>
        `;
        preview.appendChild(helpText);
    }
}

window.removeFile = function(index) {
    // CRITICAL FIX: Clean up object URL for removed file if it's an image
    if (selectedFiles[index] && selectedFiles[index].type.startsWith('image/')) {
        if (window.activeObjectURLs && window.activeObjectURLs[index]) {
            try {
                URL.revokeObjectURL(window.activeObjectURLs[index]);
                window.activeObjectURLs.splice(index, 1);
                console.log('🧹 Object URL cleaned up for removed file');
            } catch (e) {
                console.warn('Failed to revoke URL:', e);
            }
        }
    }
    
    selectedFiles.splice(index, 1);
    displayFilePreview();
};

// ==========================================
// VOICE INPUT
// ==========================================
function handleVoiceInput() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        showToast('Voice input not supported in this browser', 'error');
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();

    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
        showToast('Listening...', 'info');
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        document.getElementById('userInput').value = transcript;
        showToast('Speech recognized', 'success');
    };

    recognition.onerror = (event) => {
        showToast('Speech recognition error', 'error');
    };

    recognition.start();
}

// ==========================================
// QUICK ACTIONS
// ==========================================
window.triggerImageGeneration = function() {
    document.getElementById('userInput').value = 'Generate an image of ';
    document.getElementById('userInput').focus();
};

window.triggerWebSearch = function() {
    document.getElementById('userInput').value = 'Search the web for ';
    document.getElementById('userInput').focus();
};

window.triggerCodeHelp = function() {
    document.getElementById('userInput').value = 'Help me with code: ';
    document.getElementById('userInput').focus();
};

// ==========================================
// SETTINGS
// ==========================================
window.openSettings = function() {
    document.getElementById('settingsModal').style.display = 'flex';
    loadSettingsValues();
};

window.closeSettings = function() {
    document.getElementById('settingsModal').style.display = 'none';
};

// FIXED: Changed setEnabled → toggle, 'balanced' → 'medium'
function loadSettings() {
    const autonomousEnabled = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_ENABLED) === 'true';
    const autonomousFrequency = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_FREQUENCY) || 'medium';

    if (window.autonomousMessaging) {
        window.autonomousMessaging.toggle(autonomousEnabled);
        window.autonomousMessaging.setFrequency(autonomousFrequency);
    }
}

function loadSettingsValues() {
    const profile = currentProfile?.getProfile() || {};

    document.getElementById('settingsName').value = profile.name || '';
    document.getElementById('settingsEmail').value = profile.email || '';
    document.getElementById('assistantName').value = localStorage.getItem(STORAGE_KEYS.ASSISTANT_NAME) || 'Crump';
    document.getElementById('autonomousMessaging').checked = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_ENABLED) === 'true';
    document.getElementById('autonomousFrequency').value = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_FREQUENCY) || 'balanced';
    document.getElementById('workMode').checked = localStorage.getItem(STORAGE_KEYS.WORK_MODE) === 'true';
    document.getElementById('workStart').value = localStorage.getItem('crump_work_start') || '9';
    document.getElementById('workEnd').value = localStorage.getItem('crump_work_end') || '17';
    
    const freqGroup = document.getElementById('autonomousFrequencyGroup');
    freqGroup.style.display = document.getElementById('autonomousMessaging').checked ? 'block' : 'none';

    document.getElementById('autonomousMessaging').addEventListener('change', (e) => {
        freqGroup.style.display = e.target.checked ? 'block' : 'none';
    });
}

window.saveSettings = function() {
    const name = document.getElementById('settingsName').value.trim();
    const email = document.getElementById('settingsEmail').value.trim();
    const assistantName = document.getElementById('assistantName').value.trim() || 'Crump';
    const autonomousEnabled = document.getElementById('autonomousMessaging').checked;
    const autonomousFrequency = document.getElementById('autonomousFrequency').value;
    const workMode = document.getElementById('workMode').checked;
    const workStart = document.getElementById('workStart').value;
    const workEnd = document.getElementById('workEnd').value;
    
    // TRACK CHANGES FOR CRUMP TO ACKNOWLEDGE
    const previousAutonomous = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_ENABLED) === 'true';
    const previousWorkMode = localStorage.getItem(STORAGE_KEYS.WORK_MODE) === 'true';
    
    const changes = {
        autonomousJustEnabled: !previousAutonomous && autonomousEnabled,
        autonomousJustDisabled: previousAutonomous && !autonomousEnabled,
        workModeJustEnabled: !previousWorkMode && workMode,
        workModeJustDisabled: previousWorkMode && !workMode,
        timestamp: Date.now()
    };
    
    // Store recent changes so next message can acknowledge them
    if (changes.autonomousJustEnabled || changes.autonomousJustDisabled || 
        changes.workModeJustEnabled || changes.workModeJustDisabled) {
        localStorage.setItem('crump_recent_changes', JSON.stringify(changes));
    }
    
    if (currentProfile && name) {
        currentProfile.updateProfile({
            name: name,
            email: email,
            initial: name.charAt(0).toUpperCase()
        });
    }

    localStorage.setItem(STORAGE_KEYS.ASSISTANT_NAME, assistantName);
    localStorage.setItem(STORAGE_KEYS.AUTONOMOUS_ENABLED, autonomousEnabled);
    localStorage.setItem(STORAGE_KEYS.AUTONOMOUS_FREQUENCY, autonomousFrequency);
    localStorage.setItem(STORAGE_KEYS.WORK_MODE, workMode);
    localStorage.setItem('crump_work_start', workStart);
    localStorage.setItem('crump_work_end', workEnd);

    if (window.autonomousMessaging) {
        window.autonomousMessaging.toggle(autonomousEnabled);
        window.autonomousMessaging.setFrequency(autonomousFrequency);
    }

    updateAssistantNameDisplay();
    updateUserAvatar();
    closeSettings();
    showToast('Settings saved', 'success');
};

// Track when user upgrades (for future use)
window.notifyUpgrade = function(tier) {
    const upgrade = {
        tier: tier, // 'pro', 'pro-plus', etc.
        timestamp: Date.now()
    };
    
    localStorage.setItem('crump_recent_upgrade', JSON.stringify(upgrade));
    
    console.log('🎉 Upgrade detected:', tier);
    
    // Show Crump's excitement in next message
    if (window.universalMemory) {
        window.universalMemory.justUpgraded = upgrade;
    }
};

// ==========================================
// UI HELPERS
// ==========================================
function updateAssistantNameDisplay() {
    const name = localStorage.getItem(STORAGE_KEYS.ASSISTANT_NAME) || 'Crump';
    document.querySelectorAll('.assistant-name').forEach(el => {
        el.textContent = name;
    });
}

function updateUserAvatar() {
    const initial = currentProfile?.profile?.initial ||
        localStorage.getItem(STORAGE_KEYS.USER_INITIAL) || 'U';
    localStorage.setItem(STORAGE_KEYS.USER_INITIAL, initial);
}

function initializeAssistant() {
    setAssistantState('idle');
}

function setAssistantState(state) {
    const character = document.getElementById('assistantCharacter');
    if (character) {
        character.className = 'assistant-character ' + state;
    }
}
window.setAssistantState = setAssistantState;

// ==========================================
// READ RECEIPTS
// ==========================================
function showReadReceipt(messageElement) {
    if (!messageElement) return;
    
    const messageContent = messageElement.querySelector('.message-content');
    if (!messageContent) return;
    
    // Check if status already exists
    if (messageContent.querySelector('.message-status')) return;
    
    const status = document.createElement('div');
    status.className = 'message-status read';
    status.innerHTML = `
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M2 8l4 4 8-8"/>
        </svg>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M2 8l4 4 8-8"/>
        </svg>
        <span>Read</span>
    `;
    messageContent.appendChild(status);
}

// ==========================================
// UI HELPERS
// ==========================================
function showThinking() {
    const indicator = document.getElementById('thinkingIndicator');
    if (indicator) indicator.style.display = 'flex';
}

function hideThinking() {
    const indicator = document.getElementById('thinkingIndicator');
    if (indicator) indicator.style.display = 'none';
}
window.showThinking = showThinking;
window.hideThinking = hideThinking;

function showWelcomeMessage() {
    const userName = currentProfile?.profile?.name || 'there';
    const assistantName = localStorage.getItem(STORAGE_KEYS.ASSISTANT_NAME) || 'Crump';

    const welcomeMessage = {
        role: 'assistant',
        content: 'Hey ' + userName + '! I\'m ' + assistantName + ', your AI assistant. I\'m here to help with anything you need - from answering questions to helping with projects. What can I help you with today?',
        timestamp: Date.now()
    };

        const chat = chats.find(c => c.id === currentChatId);
    if (chat && chat.messages.length === 0) {
        chat.messages.push(welcomeMessage);
        saveChats();
        if (window.renderMessages) {
            window.renderMessages(chat.messages);
        } else {
            legacyRenderMessages(chat.messages);
        }
    }
}

// FIXED: Changed setEnabled → toggle, 'balanced' → 'medium'
function setupAutonomousMessaging() {
    const enabled = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_ENABLED) === 'true';
    const frequency = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_FREQUENCY) || 'balanced';

    if (window.autonomousMessaging) {
        window.autonomousMessaging.toggle(enabled);
        window.autonomousMessaging.setFrequency(frequency);
    }
}

function showToast(message, type) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}
window.showToast = showToast;

// ==========================================
// UTILITIES
// ==========================================
function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return diffMins + 'm ago';
    if (diffMins < 1440) return Math.floor(diffMins / 60) + 'h ago';

    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
window.escapeHtml = escapeHtml;

// ==========================================
// MOBILE KEYBOARD HANDLER
// ==========================================
function setupMobileKeyboardHandler() {
    // Only run on mobile devices
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    if (!isMobile) return;
    
    console.log('📱 Mobile detected - setting up keyboard handler');
    
    // Use Visual Viewport API if available
    if ('visualViewport' in window) {
        const inputArea = document.querySelector('.input-area');
        if (!inputArea) return;
        
        let originalHeight = window.visualViewport.height;
        
        window.visualViewport.addEventListener('resize', () => {
            const currentHeight = window.visualViewport.height;
            const heightDiff = originalHeight - currentHeight;
            
            // Keyboard is open if viewport shrunk significantly
            if (heightDiff > 150) {
                inputArea.style.transform = `translateY(-${heightDiff}px)`;
                inputArea.style.transition = 'transform 0.2s ease';
            } else {
                inputArea.style.transform = 'translateY(0)';
            }
        });
        
        // Reset on scroll
        window.visualViewport.addEventListener('scroll', () => {
            const currentHeight = window.visualViewport.height;
            if (currentHeight === originalHeight) {
                inputArea.style.transform = 'translateY(0)';
            }
        });
    }
}

window.crumpDebug = {
    getChats: () => chats,
    getCurrentChat: () => chats.find(c => c.id === currentChatId),
    getProfile: () => currentProfile?.getProfile(),
    version: '1.0.0-FIXED-AUTONOMOUS'
};

console.log('✅ Crump AI v1.0 loaded (FIXED VERSION - Autonomous corrected)');

// CRITICAL FIX: Clean up all object URLs when page unloads
window.addEventListener('beforeunload', () => {
    if (window.activeObjectURLs) {
        window.activeObjectURLs.forEach(url => {
            try {
                URL.revokeObjectURL(url);
            } catch (e) {
                // Ignore errors during cleanup
            }
        });
    }
    console.log('🧹 Cleaned up all object URLs on page unload');
});
