
// Account-scoped cache keys. Supabase remains the source of truth; these are offline caches only.
const BASE_STORAGE_KEYS = Object.freeze({
    CHATS: 'crump_chats',
    CURRENT_CHAT: 'crump_current_chat',
    USER_PROFILE: 'crump_user_profile',
    USER_INITIAL: 'crump_user_initial',
    ASSISTANT_NAME: 'crump_assistant_name',
    WORK_MODE: 'crump_work_mode',
    WORK_START: 'crump_work_start',
    WORK_END: 'crump_work_end',
    HAS_ONBOARDED: 'crump_has_onboarded',
    ACTIVATION_RECORDED: 'crump_activation_recorded',
    PROFILE_NUDGE_DISMISSED: 'crump_profile_nudge_dismissed'
});
const STORAGE_KEYS = { ...BASE_STORAGE_KEYS };

window.configureUserStorage = function configureUserStorage(userId) {
    const safeUserId = String(userId || '').replace(/[^a-zA-Z0-9_-]/g, '');
    if (!safeUserId) return;
    for (const [name, base] of Object.entries(BASE_STORAGE_KEYS)) {
        STORAGE_KEYS[name] = `${base}:${safeUserId}`;
    }

    // Migrate a pre-v4 cache only when its stored owner is provably this account.
    try {
        const legacySession = JSON.parse(localStorage.getItem('crump_session') || 'null');
        const legacyOwner = legacySession?.user?.id;
        if (legacyOwner === userId && !localStorage.getItem(STORAGE_KEYS.CHATS)) {
            const legacyChats = localStorage.getItem(BASE_STORAGE_KEYS.CHATS);
            const legacyCurrent = localStorage.getItem(BASE_STORAGE_KEYS.CURRENT_CHAT);
            if (legacyChats) localStorage.setItem(STORAGE_KEYS.CHATS, legacyChats);
            if (legacyCurrent) localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, legacyCurrent);
        }
    } catch (_) {}
};

// In-memory application state
let chats = [];
let currentChatId = null;
let currentProfile = null;
let selectedFiles = [];
let isProcessing = false;
window.chats = chats;
window.currentChatId = currentChatId;
window.STORAGE_KEYS = STORAGE_KEYS;
const previewObjectUrls = new Set();

function asTimestamp(value) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    const parsed = new Date(value || 0).getTime();
    return Number.isFinite(parsed) ? parsed : Date.now();
}

function touchChat(chat) {
    if (!chat) return;
    chat.updatedAt = new Date().toISOString();
    chat.revision = Math.max(1, Number(chat.revision || 0) + 1);
}

function normalizeLocalChat(chat) {
    const id = chat?.chat_id || chat?.id || crypto.randomUUID();
    return {
        ...chat,
        id,
        chat_id: id,
        title: chat?.title || 'New Conversation',
        messages: Array.isArray(chat?.messages) ? chat.messages : [],
        createdAt: chat?.created_at || chat?.createdAt || new Date().toISOString(),
        updatedAt: chat?.updated_at || chat?.updatedAt || chat?.created_at || chat?.createdAt || new Date().toISOString(),
        revision: Math.max(1, Number(chat?.revision || 1)),
    };
}

// Authenticated lifecycle
window.initializeAuthenticatedApp = function(user) {
    // Store user info globally and isolate this account's offline cache.
    window.currentUser = user;
    window.configureUserStorage?.(user.id);

    // Sync subscription from server to profile manager
    if (window.profileManager && typeof window.profileManager.applyServerSubscription === 'function') {
        window.profileManager.applyServerSubscription(user);
    }

    // Sync is server-authoritative. This call is safe before or after initializeApp().
    if (typeof window.syncChatsFromServer === 'function') {
        window.syncChatsFromServer();
    }
    if (typeof window.startAutoSync === 'function') {
        window.startAutoSync();
    }
    if (typeof window.setupTokenRefresh === 'function') {
        window.setupTokenRefresh();
    }
    window.CrumpPresence?.loadPreferences?.();
    window.CrumpPresence?.registerToken?.();

    // Update settings with user's preferences
    if (user.preferences) {
        if (user.preferences.assistantName) {
            SafeStorage.setItem(STORAGE_KEYS.ASSISTANT_NAME, user.preferences.assistantName);
        }
        if (user.preferences.workMode !== undefined) {
            SafeStorage.setItem(STORAGE_KEYS.WORK_MODE, String(!!user.preferences.workMode));
        }
    }
    updateAssistantNameDisplay();
};


// Application startup
window.initializeApp = function() {
    try {
        const required = ['chatContainer', 'userInput', 'sendButton', 'newChatBtn', 'chatsList', 'fileInput'];
        const missing = required.filter(id => !document.getElementById(id));
        if (missing.length > 0) {
            throw new Error('Missing elements: ' + missing.join(', '));
        }
        if (typeof window.ProfileManager !== 'undefined') {
            currentProfile = new ProfileManager();
        } else if (typeof window.UserProfileManager !== 'undefined') {
            currentProfile = new UserProfileManager();
        }
        if (currentProfile) {
            window.currentProfile = currentProfile;
            window.profileManager = currentProfile;
            updateUserAvatar();
        }

        // Render the account-scoped cache immediately. Authentication triggers
        // a server-authoritative synchronization after the shell is ready.
        loadChats();

        setupEventListeners();
        setupSidebarToggle();
        loadSettings();
        updateAssistantNameDisplay();


        // Initialize scrolling after the chat shell is ready.
        if (window.crumpScrollManager && typeof window.crumpScrollManager.init === 'function') {
            window.crumpScrollManager.init();
        }

        // A cold start or reload should feel like a clean desk. Conversation
        // history remains intact and deliberately opening one still restores it.
        openFreshConversationAtStartup();

    } catch (error) {
        console.error('[App] Initialization failed:', error);
        showToast('Failed to initialize application', 'error');
    }
};

// Event Listeners
function setupEventListeners() {
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    const newChatBtn = document.getElementById('newChatBtn');
    const attachBtn = document.getElementById('attachBtn');
    const fileInput = document.getElementById('fileInput');

    // Send message
    if (sendButton) {
        sendButton.addEventListener('click', () => sendMessage());
    }

    // Enter to send (Shift+Enter for new line)
    if (userInput) {
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
    }

    // New chat
    if (newChatBtn) {
        newChatBtn.addEventListener('click', () => createNewChat());
    }

    // File attachment
    if (attachBtn && fileInput) {
        attachBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileSelect);
    } else {
        if (!attachBtn) console.warn('[UI] attachBtn not found - file attach disabled on this page');
        if (!fileInput) console.warn('[UI] fileInput not found - file attach disabled on this page');
    }

    const actions = [
        ['clearChatsBtn', () => clearAllChats()],
        ['settingsBtn', () => window.openSettings?.()],
        ['upgradeBtnSidebar', () => window.showUpgradePrompt?.()],
        ['imageQuickAction', () => window.triggerImageGeneration?.()],
        ['searchQuickAction', () => window.triggerWebSearch?.()],
        ['codeQuickAction', () => window.triggerCodeHelp?.()],
        ['closeSettingsBtn', () => window.closeSettings?.()],
        ['saveSettingsBtn', () => window.saveSettings?.()],
        ['signOutBtn', () => window.logoutUser?.()],
        ['devicesBtn', () => window.openDevices?.()],
        ['deleteAccountBtn', () => window.openDeleteAccountDialog?.()],
    ];
    actions.forEach(([id, handler]) => document.getElementById(id)?.addEventListener('click', handler));
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
            menuBtn.setAttribute('aria-expanded', 'true');
        });

        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
            menuBtn.setAttribute('aria-expanded', 'false');
        });

        if (closeSidebarBtn) {
            closeSidebarBtn.addEventListener('click', () => {
                sidebar.classList.remove('active');
                sidebarOverlay.classList.remove('active');
                menuBtn.setAttribute('aria-expanded', 'false');
            });
        }
    }
}

function closeConversationMenu() {
    document.getElementById('sidebar')?.classList.remove('active');
    document.getElementById('sidebarOverlay')?.classList.remove('active');
    document.getElementById('menuBtn')?.setAttribute('aria-expanded', 'false');
}

// Chat Management
function loadChats() {
    let local = [];
    try {
        local = JSON.parse(SafeStorage.getItem(STORAGE_KEYS.CHATS) || '[]');
    } catch (error) {
        console.warn('[Chats] Ignoring corrupt local cache:', error);
    }
    const prefetched = Array.isArray(window.__crumpSyncData?.chats)
        ? window.__crumpSyncData.chats
        : [];
    const source = prefetched.length ? prefetched : local;
    chats = source.filter(chat => !(chat?.deleted_at || chat?.deletedAt)).map(normalizeLocalChat).sort((a, b) => asTimestamp(b.updatedAt) - asTimestamp(a.updatedAt));
    window.chats = chats;
    SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
    renderChatsList();
}

function saveChats({ sync = true } = {}) {
    chats = chats.map(normalizeLocalChat);
    window.chats = chats;
    SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
    if (sync && typeof window.syncChatsToServer === 'function' && window.currentUser) {
        clearTimeout(window.syncDebounceTimer);
        window.syncDebounceTimer = setTimeout(() => window.syncChatsToServer(), 500);
    }
}
window.saveChats = saveChats;

window.replaceChats = function replaceChats(nextChats) {
    const activeId = currentChatId;
    chats = (Array.isArray(nextChats) ? nextChats : []).map(normalizeLocalChat)
        .sort((a, b) => asTimestamp(b.updatedAt) - asTimestamp(a.updatedAt));
    window.chats = chats;
    SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
    renderChatsList();
    const preferred = chats.find(chat => chat.id === activeId) || chats[0];
    if (preferred) {
        currentChatId = preferred.id;
        window.currentChatId = currentChatId;
        SafeStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, currentChatId);
        window.renderMessages?.(preferred.messages);
    } else {
        currentChatId = null;
        window.currentChatId = null;
        SafeStorage.removeItem(STORAGE_KEYS.CURRENT_CHAT);
        window.renderMessages?.([]);
    }
};

function createNewChat() {
    const now = new Date().toISOString();
    const id = crypto.randomUUID();
    const chat = {
        id,
        chat_id: id,
        title: 'New Conversation',
        messages: [],
        createdAt: now,
        updatedAt: now,
        revision: 1,
    };
    chats.unshift(chat);
    currentChatId = id;
    window.currentChatId = id;
    saveChats();
    SafeStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, id);
    renderChatsList();
    window.renderMessages?.([]);
    closeConversationMenu();
    const input = document.getElementById('userInput');
    if (input) {
        input.value = '';
        input.focus();
    }
}

function openFreshConversationAtStartup() {
    const starter = chats.find(chat =>
        String(chat?.title || '').trim().toLowerCase() === 'new conversation' &&
        Array.isArray(chat?.messages) &&
        chat.messages.length === 0
    );
    if (!starter) {
        createNewChat();
        return;
    }

    // Reuse a pristine starter instead of accumulating empty history rows on
    // every reload, and promote it to the top of the conversation list.
    touchChat(starter);
    chats.sort((a, b) => asTimestamp(b.updatedAt) - asTimestamp(a.updatedAt));
    saveChats();
    loadChat(starter.id);
    const input = document.getElementById('userInput');
    if (input) {
        input.value = '';
        input.focus();
    }
}

function loadChat(chatId) {
    const chat = chats.find(item => item.id === chatId);
    if (!chat) return;
    currentChatId = chatId;
    window.currentChatId = chatId;
    SafeStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, chatId);
    renderChatsList();
    window.renderMessages?.(chat.messages);
    closeConversationMenu();
}

function getChat(chatId) {
    return chats.find(chat => chat.id === chatId);
}

async function deleteChat(chatId) {
    const accepted = await window.confirmAction?.({
        title: 'Delete conversation?',
        message: 'This removes the conversation from every signed-in device. This action cannot be undone.',
        confirmLabel: 'Delete',
        destructive: true,
    });
    if (!accepted) return;
    window.recordChatDeletion?.(chatId);
    chats = chats.filter(chat => chat.id !== chatId);
    saveChats();
    if (currentChatId === chatId) {
        if (chats.length) loadChat(chats[0].id);
        else createNewChat();
    }
    renderChatsList();
}
window.deleteChat = deleteChat;

async function clearAllChats() {
    const accepted = await window.confirmAction?.({
        title: 'Clear all conversations?',
        message: 'Every conversation will be removed from your account and signed-in devices. This action cannot be undone.',
        confirmLabel: 'Clear conversations',
        destructive: true,
    });
    if (!accepted) return;
    chats.forEach(chat => window.recordChatDeletion?.(chat.id));
    chats = [];
    saveChats();
    createNewChat();
    showToast('All conversations cleared', 'success');
}
window.clearAllChats = clearAllChats;

function renderChatsList() {
    const chatsList = document.getElementById('chatsList');
    if (!chatsList) return;
    const fragment = document.createDocumentFragment();
    chats.forEach(chat => {
        const item = document.createElement('div');
        item.className = `chat-item ${chat.id === currentChatId ? 'active' : ''}`;
        item.dataset.chatId = chat.id;
        item.tabIndex = 0;
        item.setAttribute('role', 'button');
        item.addEventListener('click', () => loadChat(chat.id));
        item.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); loadChat(chat.id); }
        });

        const content = document.createElement('div');
        content.className = 'chat-item-content';
        const title = document.createElement('div');
        title.className = 'chat-title';
        title.textContent = chat.title || 'New conversation';
        const preview = document.createElement('div');
        preview.className = 'chat-preview';
        preview.textContent = `${chat.messages.length} messages`;
        content.append(title, preview);

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'delete-chat-btn';
        button.setAttribute('aria-label', 'Delete conversation');
        button.textContent = '×';
        button.addEventListener('click', event => { event.stopPropagation(); deleteChat(chat.id); });
        item.append(content, button);
        fragment.appendChild(item);
    });
    chatsList.replaceChildren(fragment);
}
window.renderChatsList = renderChatsList;
window.loadChat = loadChat;
window.createNewChat = createNewChat;

// Message delivery and response lifecycle.
function messageId() {
    return crypto.randomUUID?.() || `${Date.now()}-${crypto.getRandomValues(new Uint32Array(2)).join('-')}`;
}

function updateMessageState(chat, message, changes, { touch = true } = {}) {
    Object.assign(message, changes, { deliveryUpdatedAt: new Date().toISOString() });
    if (touch) touchChat(chat);
    saveChats();
    window.renderMessages?.(chat.messages);
}

function checkInBeingAnswered(chat, userMessage) {
    const index = chat.messages.indexOf(userMessage);
    for (let position = index - 1; position >= 0; position -= 1) {
        const previous = chat.messages[position];
        if (previous?.role === 'user') return null;
        if (previous?.role === 'assistant' && previous?.origin === 'check_in' && previous?.checkInId) {
            return previous.checkInId;
        }
    }
    return null;
}

async function ensureUsageAvailable() {
    const usageResponse = await fetch('/api/usage/check');
    if (usageResponse.status === 401) throw new Error('Your session expired. Please sign in again.');
    const usageData = await usageResponse.json().catch(() => ({}));
    if (usageResponse.ok && usageData.limits?.messages !== -1 && usageData.usage?.messages >= usageData.limits?.messages) {
        window.showUpgradePrompt?.();
        throw new Error('Your daily message limit has been reached.');
    }
}

async function recordFirstSuccessfulResponse() {
    if (SafeStorage.getItem(STORAGE_KEYS.ACTIVATION_RECORDED) === 'true') return;
    const recorded = await window.CrumpAnalytics?.track?.('ActivationReached', {
        eventKey: 'first-successful-response',
    });
    if (recorded) SafeStorage.setItem(STORAGE_KEYS.ACTIVATION_RECORDED, 'true');
}

async function processUserMessage(chat, userMessage, attachment = null) {
    if (!navigator.onLine || window.CrumpPresence?.online === false) {
        updateMessageState(chat, userMessage, { deliveryStatus: 'queued', replyStatus: 'pending' });
        throw Object.assign(new Error('This message is waiting for a connection.'), { quiet: true });
    }

    const syncResult = await window.syncChatsToServer?.();
    if (syncResult && syncResult.success === false) {
        updateMessageState(chat, userMessage, { deliveryStatus: 'queued', replyStatus: 'pending' });
        throw Object.assign(new Error('This message is waiting to sync.'), { quiet: true });
    }
    updateMessageState(chat, userMessage, { deliveryStatus: 'delivered', replyStatus: 'pending' });
    window.CrumpPresence?.haptic?.('light');

    const ackResponse = await fetch('/api/chat/ack', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            chatId: chat.id,
            messageId: userMessage.id,
            message: userMessage.content || '',
            fileTypes: (userMessage.files || []).map(file => file.type),
        }),
    });
    const ackData = await ackResponse.json().catch(() => ({}));
    if (!ackResponse.ok) throw new Error(ackData.error || 'Crump could not receive the message.');
    updateMessageState(chat, userMessage, {
        deliveryStatus: 'seen',
        deliveredAt: ackData.deliveredAt,
        seenAt: ackData.seenAt,
        replyStatus: 'processing',
        replyError: null,
    });
    window.CrumpPresence?.start?.(ackData.activity || 'thinking');

    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const requestBody = {
        chatId: chat.id,
        messageId: userMessage.id,
        message: userMessage.content || '',
        history: chat.messages.map(item => ({ role: item.role, content: item.content })),
        currentDateTime: {
            iso: new Date().toISOString(),
            timezone: timeZone,
            date: new Date().toLocaleDateString('en-US', { dateStyle: 'full', timeZone }),
            time: new Date().toLocaleTimeString('en-US', { timeStyle: 'medium', timeZone }),
        },
        replyToCheckInId: checkInBeingAnswered(chat, userMessage),
    };
    if (attachment) requestBody.fileData = [attachment];

    let response;
    let data = {};
    for (let attempt = 0; attempt < 2; attempt += 1) {
        response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
        });
        data = await response.json().catch(() => ({}));
        if (response.ok) break;
        if (!(data.shouldRetry && attempt === 0)) break;
        const retryAfter = Math.min(30, Math.max(1, Number(data.retryAfter || 5)));
        window.CrumpPresence?.update?.('thinking');
        await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
    }

    if (!response?.ok) {
        if (response?.status === 401) window.deviceAuth?.clearLocalState?.();
        if (data.upgradeRequired) window.showUpgradePrompt?.();
        throw new Error(data.message || data.error || `Request failed (${response?.status || 'network'})`);
    }

    const assistantMessage = {
        id: messageId(),
        role: 'assistant',
        content: data.response || '',
        timestamp: new Date().toISOString(),
        origin: 'reply',
        inReplyTo: userMessage.id,
    };
    if (data.imageUrl) {
        assistantMessage.imageUrl = data.imageUrl;
        assistantMessage.imagePrompt = data.imagePrompt;
    }
    chat.messages.push(assistantMessage);
    userMessage.replyStatus = 'replied';
    userMessage.replyError = null;
    touchChat(chat);
    saveChats();
    window.CrumpPresence?.stop?.();
    window.renderMessages?.(chat.messages);
    renderChatsList();
    window.CrumpPresence?.haptic?.('success');
    window.syncChatsToServer?.();
    void recordFirstSuccessfulResponse();
    setTimeout(safeScrollToBottom, 80);
}

async function sendMessage() {
    if (isProcessing) return;
    const userInput = document.getElementById('userInput');
    const message = userInput?.value.trim() || '';
    if (!message && selectedFiles.length === 0) return;
    const chat = chats.find(item => item.id === currentChatId);
    if (!chat) return;
    isProcessing = true;
    let userMessage = null;

    try {
        await ensureUsageAvailable();
        let attachment = null;
        if (selectedFiles.length) {
            const file = selectedFiles[0];
            attachment = { type: file.type, name: file.name, data: await readFileAsBase64(file) };
        }

        userMessage = {
            id: messageId(),
            role: 'user',
            content: message,
            timestamp: new Date().toISOString(),
            deliveryStatus: 'sending',
            replyStatus: 'pending',
        };
        if (attachment) userMessage.files = [{ type: attachment.type, name: attachment.name }];
        chat.messages.push(userMessage);
        touchChat(chat);
        if (chat.messages.length === 1 && message) chat.title = message.slice(0, 50) + (message.length > 50 ? '…' : '');
        saveChats();
        window.renderMessages?.(chat.messages);
        renderChatsList();

        userInput.value = '';
        userInput.style.height = 'auto';
        const fileInput = document.getElementById('fileInput');
        if (fileInput) fileInput.value = '';
        selectedFiles = [];
        displayFilePreview();

        await processUserMessage(chat, userMessage, attachment);
    } catch (error) {
        console.error('[Chat]', error);
        window.CrumpPresence?.stop?.();
        if (userMessage) {
            if (error.quiet) {
                updateMessageState(chat, userMessage, {
                    deliveryStatus: 'queued',
                    replyStatus: 'pending',
                    replyError: null,
                });
            } else {
                const state = userMessage.deliveryStatus === 'sending' ? 'failed' : userMessage.deliveryStatus;
                updateMessageState(chat, userMessage, {
                    deliveryStatus: state,
                    replyStatus: state === 'failed' ? 'pending' : 'failed',
                    replyError: error.message || 'Reply failed.',
                });
                window.CrumpPresence?.haptic?.('error');
                showToast(error.message || 'Failed to send message.', 'error');
            }
        }
    } finally {
        isProcessing = false;
    }
}

window.retryMessage = async function retryMessage(id) {
    if (isProcessing || !id) return;
    const chat = chats.find(item => item.id === currentChatId);
    const message = chat?.messages.find(item => item.id === id && item.role === 'user');
    if (!chat || !message) return;
    if (message.files?.length) {
        showToast('Reattach the file before retrying this message.', 'warning');
        return;
    }
    isProcessing = true;
    try {
        await ensureUsageAvailable();
        updateMessageState(chat, message, { deliveryStatus: 'sending', replyStatus: 'pending', replyError: null });
        await processUserMessage(chat, message, null);
    } catch (error) {
        console.error('[Chat retry]', error);
        window.CrumpPresence?.stop?.();
        if (error.quiet) {
            updateMessageState(chat, message, {
                deliveryStatus: 'queued',
                replyStatus: 'pending',
                replyError: null,
            });
        } else {
            updateMessageState(chat, message, {
                deliveryStatus: message.deliveryStatus === 'sending' ? 'failed' : message.deliveryStatus,
                replyStatus: message.deliveryStatus === 'sending' ? 'pending' : 'failed',
                replyError: error.message || 'Reply failed.',
            });
            window.CrumpPresence?.haptic?.('error');
            showToast(error.message || 'Retry failed.', 'error');
        }
    } finally {
        isProcessing = false;
    }
};
window.sendMessage = sendMessage;

async function readFileAsBase64(file) {
    if (!file.type.startsWith('image/') || (file.size <= 2.5 * 1024 * 1024 && !file.type.includes('heic'))) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }
    try {
        const bitmap = await createImageBitmap(file);
        const scale = Math.min(1, 2048 / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(bitmap.width * scale));
        canvas.height = Math.max(1, Math.round(bitmap.height * scale));
        canvas.getContext('2d', { alpha: false }).drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        bitmap.close?.();
        return canvas.toDataURL('image/jpeg', 0.84);
    } catch (_) {
        if (file.size > 3 * 1024 * 1024) throw new Error('This image could not be compressed. Choose an image smaller than 3 MB.');
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }
}

// File Handling
function handleFileSelect(e) {
    const file = Array.from(e.target.files || [])[0];
    e.target.value = '';
    if (!file) return;
    const supported = file.type.startsWith('image/') || file.type === 'application/pdf';
    if (!supported) {
        showToast('Ask Crump currently supports images and PDF attachments.', 'error');
        return;
    }
    if (file.type === 'application/pdf' && file.size > 3 * 1024 * 1024) {
        showToast('PDF attachments must be 3 MB or smaller.', 'error');
        return;
    }
    selectedFiles = [file];
    displayFilePreview();
}

function fileTypeLabel(file) {
    const name = file.name.toLowerCase();
    if (file.type.startsWith('image/')) return 'IMG';
    if (file.type === 'application/pdf') return 'PDF';
    if (name.endsWith('.zip') || name.endsWith('.7z') || name.endsWith('.rar') || name.endsWith('.tar.gz')) return 'ZIP';
    const extension = name.includes('.') ? name.split('.').pop() : 'FILE';
    return extension.slice(0, 4).toUpperCase();
}

function clearPreviewObjectUrls() {
    for (const url of previewObjectUrls) URL.revokeObjectURL(url);
    previewObjectUrls.clear();
}

function displayFilePreview() {
    const preview = document.getElementById('filePreview');
    if (!preview) return;

    clearPreviewObjectUrls();
    preview.replaceChildren();
    preview.hidden = selectedFiles.length === 0;
    preview.style.display = selectedFiles.length ? 'grid' : 'none';
    if (!selectedFiles.length) return;

    for (const [index, file] of selectedFiles.entries()) {
        const item = document.createElement('article');
        item.className = 'attachment-preview';

        if (file.type.startsWith('image/')) {
            const image = document.createElement('img');
            const objectUrl = URL.createObjectURL(file);
            previewObjectUrls.add(objectUrl);
            image.className = 'attachment-preview__image';
            image.src = objectUrl;
            image.alt = '';
            image.addEventListener('error', () => {
                image.remove();
                item.classList.add('attachment-preview--unavailable');
            }, { once: true });
            item.appendChild(image);
        } else {
            const type = document.createElement('span');
            type.className = 'attachment-preview__type';
            type.textContent = fileTypeLabel(file);
            type.setAttribute('aria-hidden', 'true');
            item.appendChild(type);
        }

        const details = document.createElement('div');
        details.className = 'attachment-preview__details';

        const name = document.createElement('strong');
        name.className = 'attachment-preview__name';
        name.textContent = file.name;
        name.title = file.name;

        const size = document.createElement('span');
        size.className = 'attachment-preview__size';
        size.textContent = file.size >= 1024 * 1024
            ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
            : `${(file.size / 1024).toFixed(1)} KB`;

        details.append(name, size);
        item.appendChild(details);

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'attachment-preview__remove';
        remove.setAttribute('aria-label', `Remove ${file.name}`);
        remove.textContent = 'Remove';
        remove.addEventListener('click', () => window.removeFile(index));
        item.appendChild(remove);

        preview.appendChild(item);
    }

    const summary = document.createElement('p');
    summary.className = 'attachment-preview__summary';
    summary.textContent = `${selectedFiles.length} file${selectedFiles.length === 1 ? '' : 's'} ready to send`;
    preview.appendChild(summary);
}

window.removeFile = function removeFile(index) {
    selectedFiles.splice(index, 1);
    displayFilePreview();
};

let activeVoiceAudio = null;
let activeVoiceObjectUrl = '';
let voiceRequestSequence = 0;
let premiumVoiceCapability = {available: false, checkedAt: 0};

function clearPremiumVoice() {
    if (activeVoiceAudio) {
        activeVoiceAudio.pause();
        activeVoiceAudio.src = '';
        activeVoiceAudio = null;
    }
    if (activeVoiceObjectUrl) {
        URL.revokeObjectURL(activeVoiceObjectUrl);
        activeVoiceObjectUrl = '';
    }
}

function speakWithDeviceVoice(text, notice = 'Reading response...') {
    if (!('speechSynthesis' in window)) {
        showToast('Text-to-speech not supported in this browser', 'error');
        return false;
    }

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);

    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.volume = 1.0; // Volume

    // Use a better voice if available
    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(voice =>
        voice.lang === 'en-US' && (voice.name.includes('Google') || voice.name.includes('Microsoft'))
    );
    if (preferredVoice) {
        utterance.voice = preferredVoice;
    }

    window.speechSynthesis.speak(utterance);
    showToast(notice, 'info');
    return true;
}

async function canUsePremiumVoice() {
    const now = Date.now();
    if (now - premiumVoiceCapability.checkedAt < 5 * 60 * 1000) {
        return premiumVoiceCapability.available;
    }
    try {
        const response = await fetch('/api/features', {credentials: 'same-origin'});
        const data = response.ok ? await response.json() : {};
        const feature = data?.features?.premium_voice || {};
        premiumVoiceCapability = {
            available: Boolean(feature.configured && feature.entitled),
            checkedAt: now,
        };
    } catch (_) {
        premiumVoiceCapability = {available: false, checkedAt: now};
    }
    return premiumVoiceCapability.available;
}

// Read assistant responses aloud. Premium voice is requested only after this
// explicit click; long responses and unavailable accounts stay on-device.
window.speakText = async function(text) {
    const readable = String(text || '').trim();
    if (!readable) return;
    voiceRequestSequence += 1;
    const requestId = voiceRequestSequence;
    clearPremiumVoice();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (readable.length > 4000) {
        speakWithDeviceVoice(readable, 'Using your device voice for this longer response.');
        return;
    }
    const premiumAvailable = await canUsePremiumVoice();
    if (requestId !== voiceRequestSequence) return;
    if (!premiumAvailable) {
        speakWithDeviceVoice(readable);
        return;
    }
    showToast('Creating Crump Voice...', 'info');
    try {
        const response = await fetch('/api/voice/synthesize', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: readable}),
        });
        if (!response.ok) {
            if ([401, 403, 503].includes(response.status)) {
                premiumVoiceCapability = {available: false, checkedAt: Date.now()};
            }
            throw new Error(`Premium voice unavailable (${response.status})`);
        }
        const audioBlob = await response.blob();
        if (requestId !== voiceRequestSequence || !audioBlob.size) return;
        activeVoiceObjectUrl = URL.createObjectURL(audioBlob);
        activeVoiceAudio = new Audio(activeVoiceObjectUrl);
        activeVoiceAudio.addEventListener('ended', clearPremiumVoice, {once: true});
        activeVoiceAudio.addEventListener('error', clearPremiumVoice, {once: true});
        await activeVoiceAudio.play();
        showToast('Reading with Crump Voice...', 'info');
    } catch (_) {
        if (requestId === voiceRequestSequence) {
            clearPremiumVoice();
            speakWithDeviceVoice(readable, 'Using your device voice.');
        }
    }
};

window.stopSpeaking = function() {
    voiceRequestSequence += 1;
    clearPremiumVoice();
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
    }
};

// Quick Actions
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

// Settings
window.openSettings = function() {
    document.getElementById('settingsModal').style.display = 'flex';
    loadSettingsValues();
};

window.closeSettings = function() {
    document.getElementById('settingsModal').style.display = 'none';
};

function loadSettings() {
    // Settings are loaded from the synchronized cache by the auth controller.
}

function loadSettingsValues() {
    const profile = currentProfile?.getProfile?.() || {};
    const user = window.currentUser || {};
    document.getElementById('settingsName').value = user.fullName || profile.name || '';
    document.getElementById('settingsEmail').value = user.email || profile.email || '';
    document.getElementById('settingsEmail').readOnly = true;
    document.getElementById('assistantName').value = SafeStorage.getItem(STORAGE_KEYS.ASSISTANT_NAME) || 'Crump';

    const workStartSelect = document.getElementById('workStart');
    const workEndSelect = document.getElementById('workEnd');
    const quietStartSelect = document.getElementById('quietStart');
    const quietEndSelect = document.getElementById('quietEnd');
    const timeSelects = [workStartSelect, workEndSelect, quietStartSelect, quietEndSelect].filter(Boolean);
    if (timeSelects.some(select => select.options.length === 0)) {
        const label = hour => `${((hour + 11) % 12) + 1} ${hour >= 12 ? 'PM' : 'AM'}`;
        for (const select of timeSelects) {
            if (select.options.length) continue;
            for (let hour = 0; hour < 24; hour += 1) select.add(new Option(label(hour), String(hour)));
        }
    }
    const workModeToggle = document.getElementById('workMode');
    const workHoursGroup = document.getElementById('workHoursGroup');
    workModeToggle.checked = SafeStorage.getItem(STORAGE_KEYS.WORK_MODE) === 'true';
    workStartSelect.value = SafeStorage.getItem(STORAGE_KEYS.WORK_START) || '9';
    workEndSelect.value = SafeStorage.getItem(STORAGE_KEYS.WORK_END) || '17';
    const updateVisibility = () => { workHoursGroup.style.display = workModeToggle.checked ? 'block' : 'none'; };
    updateVisibility();
    workModeToggle.onchange = updateVisibility;
    window.CrumpPresence?.applyPreferencesToForm?.();
}

window.saveSettings = async function() {
    const name = document.getElementById('settingsName').value.trim();
    const assistantName = document.getElementById('assistantName').value.trim() || 'Crump';
    const workMode = document.getElementById('workMode').checked;
    const workStart = document.getElementById('workStart').value;
    const workEnd = document.getElementById('workEnd').value;
    SafeStorage.setItem(STORAGE_KEYS.ASSISTANT_NAME, assistantName);
    SafeStorage.setItem(STORAGE_KEYS.WORK_MODE, String(workMode));
    SafeStorage.setItem(STORAGE_KEYS.WORK_START, workStart);
    SafeStorage.setItem(STORAGE_KEYS.WORK_END, workEnd);
    try {
        if (window.currentUser && name && name !== window.currentUser.fullName) {
            const response = await fetch('/api/account/profile', {
                method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fullName: name }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.success || !data.user) {
                throw new Error(data.error || 'Your name could not be saved. Try again.');
            }
            window.currentUser = data.user;
        }
        if (currentProfile && name) currentProfile.updateProfile({ name, initial: name.charAt(0).toUpperCase() });
        if (name) window.dispatchEvent(new CustomEvent('crump:profile-updated'));
    } catch (error) {
        console.warn('[Profile settings]', error);
        showToast(error.message || 'Your name could not be saved. Try again.', 'error');
        return;
    }
    try {
        await window.SyncManager?.push(null, {
            chats: [],
            settings: {
                assistant_name: assistantName,
                work_mode: workMode,
                work_start: Number(workStart),
                work_end: Number(workEnd),
            },
        });
        await window.CrumpPresence?.savePreferences?.();
        updateAssistantNameDisplay();
        updateUserAvatar();
        closeSettings();
        showToast('Settings saved', 'success');
    } catch (error) {
        console.warn('[Settings]', error);
        showToast('Settings saved on this device; server sync will retry.', 'warning');
        closeSettings();
    }
};

// UI helpers
function updateAssistantNameDisplay() {
    const name = SafeStorage.getItem(STORAGE_KEYS.ASSISTANT_NAME) || 'Crump';
    document.querySelectorAll('.assistant-name').forEach(el => {
        el.textContent = name;
    });
    const input = document.getElementById('userInput');
    if (input) {
        input.placeholder = `Message ${name}`;
        input.setAttribute('aria-label', `Message ${name}`);
    }
    window.dispatchEvent(new CustomEvent('crump:assistant-name-changed', { detail: { name } }));
}
window.getAssistantName = () => SafeStorage.getItem(STORAGE_KEYS.ASSISTANT_NAME) || 'Crump';

function updateUserAvatar() {
    const initial = currentProfile?.profile?.initial ||
        localStorage.getItem(STORAGE_KEYS.USER_INITIAL) || 'U';
    localStorage.setItem(STORAGE_KEYS.USER_INITIAL, initial);
}

// UI helpers
function showThinking(activity = 'thinking') {
    window.CrumpPresence?.start?.(activity);
}

function hideThinking() {
    window.CrumpPresence?.stop?.();
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
        window.renderMessages?.(chat.messages);
    }
}

// Utilities
function getChatContainerEl() {
    return document.getElementById('chatContainer');
}

function safeScrollToBottom() {
    if (window.crumpScrollManager && typeof window.crumpScrollManager.scrollToBottom === 'function') {
        window.crumpScrollManager.scrollToBottom('smooth');
        return;
    }
    const c = getChatContainerEl();
    if (c) c.scrollTop = c.scrollHeight;
}
window.addEventListener('beforeunload', clearPreviewObjectUrls);

// Session Health Check
let tokenRefreshTimer = null;

async function setupTokenRefresh() {
    if (tokenRefreshTimer) clearInterval(tokenRefreshTimer);
    tokenRefreshTimer = setInterval(async () => {
        if (document.hidden || !window.currentUser) return;
        try {
            const response = await fetch('/api/auth/check-session');
            const data = await response.json().catch(() => ({}));
            if (response.ok && data.authenticated && data.data?.user) {
                window.currentUser = data.data.user;
            } else if (response.status === 401) {
                await window.deviceAuth?.clearLocalState?.();
                window.location.href = '/app';
            }
        } catch (error) {
            console.warn('[Auth] Session health check failed:', error);
        }
    }, 12 * 60 * 60 * 1000);
}
window.setupTokenRefresh = setupTokenRefresh;
