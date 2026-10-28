// One auth-boundary owner coordinates private, unsent UI cleanup. Feature
// modules register idempotent scrubbers instead of racing separate auth events.
(() => {
    if (window.CrumpAuthBoundary) return;

    const scrubbers = new Map();
    const USER_CACHE_KEY = 'crump_user_cache_v4';
    let currentUserValue = window.currentUser || null;
    let ownerUserId = String(currentUserValue?.id || '').trim();
    let revision = 0;

    function runScrubbers(reason, nextUserId = '') {
        revision += 1;
        const boundary = Object.freeze({
            reason: String(reason || 'authentication-required'),
            previousUserId: ownerUserId,
            nextUserId: String(nextUserId || '').trim(),
            revision,
        });
        scrubbers.forEach(scrub => {
            try { scrub(boundary); }
            catch (error) { console.warn('[Auth boundary] Private UI cleanup failed:', error); }
        });
    }

    function handleAuthenticationRequired() {
        if (ownerUserId) runScrubbers('authentication-required');
        ownerUserId = '';
    }

    function handleAuthenticatedReady() {
        const nextUserId = String(currentUserValue?.id || '').trim();
        if (!nextUserId) {
            handleAuthenticationRequired();
            return;
        }
        if (ownerUserId && ownerUserId !== nextUserId) {
            runScrubbers('authenticated-user-changed', nextUserId);
        }
        ownerUserId = nextUserId;
    }

    function assignCurrentUser(nextUser) {
        const nextUserId = String(nextUser?.id || '').trim();
        if (ownerUserId && ownerUserId !== nextUserId) {
            runScrubbers(nextUserId ? 'authenticated-user-changed' : 'authenticated-user-cleared', nextUserId);
        }
        currentUserValue = nextUser || null;
        ownerUserId = nextUserId;
    }

    try {
        const descriptor = Object.getOwnPropertyDescriptor(window, 'currentUser');
        if (!descriptor || descriptor.configurable) {
            Object.defineProperty(window, 'currentUser', {
                configurable: true,
                enumerable: true,
                get: () => currentUserValue,
                set: assignCurrentUser,
            });
        }
    } catch (_) {
        // The explicit auth events and cross-tab cache boundary remain active.
    }

    function cachedIdentityId(rawValue) {
        if (!rawValue) return '';
        try { return String(JSON.parse(rawValue)?.id || '').trim(); }
        catch (_) { return ''; }
    }

    window.addEventListener('storage', event => {
        if (event.key !== USER_CACHE_KEY) return;
        const previousId = cachedIdentityId(event.oldValue);
        const nextId = cachedIdentityId(event.newValue);
        if (nextId === ownerUserId && (!previousId || previousId === nextId)) return;
        if (!ownerUserId && !previousId && !nextId) return;
        assignCurrentUser(null);
        // HttpOnly session cookies are shared across tabs. Reload so this tab
        // verifies the new server identity before it can accept another draft.
        window.location.reload();
    });

    window.CrumpAuthBoundary = Object.freeze({
        register(name, scrub) {
            const key = String(name || '').trim();
            if (!key || typeof scrub !== 'function') return () => {};
            scrubbers.set(key, scrub);
            return () => {
                if (scrubbers.get(key) === scrub) scrubbers.delete(key);
            };
        },
        authenticatedUserId: () => ownerUserId,
        revision: () => revision,
        observe: (user) => assignCurrentUser(user),
    });

    window.addEventListener('crump:authentication-required', handleAuthenticationRequired);
    window.addEventListener('crump:authenticated-ready', handleAuthenticatedReady);
})();

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
let freshConversationRequested = false;
let settingsBaselineSignature = '';
let settingsIdentityRequest = null;
let settingsIdentityGeneration = 0;
let settingsSaveController = null;
let settingsReturnFocus = null;
let settingsBackgroundState = [];
window.chats = chats;
window.currentChatId = currentChatId;
window.STORAGE_KEYS = STORAGE_KEYS;
const previewObjectUrls = new Set();

function captureAppAuthBoundary() {
    const boundary = window.CrumpAuthBoundary;
    const ownerId = String(
        typeof boundary?.authenticatedUserId === 'function'
            ? boundary.authenticatedUserId()
            : window.currentUser?.id || ''
    ).trim();
    const rawRevision = typeof boundary?.revision === 'function' ? boundary.revision() : 0;
    const revision = Number(rawRevision);
    return Object.freeze({
        ownerId,
        revision: Number.isFinite(revision) ? revision : 0,
        settingsIdentityGeneration,
    });
}

function captureConversationAuthBoundary() {
    const boundary = window.CrumpAuthBoundary;
    const ownerId = String(
        typeof boundary?.authenticatedUserId === 'function'
            ? boundary.authenticatedUserId()
            : window.currentUser?.id || ''
    ).trim();
    const rawRevision = typeof boundary?.revision === 'function' ? boundary.revision() : 0;
    const revision = Number(rawRevision);
    return Object.freeze({ownerId, revision: Number.isFinite(revision) ? revision : 0});
}

function conversationAuthBoundaryIsCurrent(snapshot) {
    if (!snapshot?.ownerId) return false;
    const current = captureConversationAuthBoundary();
    return current.ownerId === snapshot.ownerId && current.revision === snapshot.revision;
}

function conversationBoundaryAbortError() {
    return Object.assign(
        new Error('This message belongs to a previous authentication session.'),
        {name: 'AbortError', quiet: true},
    );
}

function appAuthBoundaryIsCurrent(snapshot) {
    if (!snapshot?.ownerId || snapshot.settingsIdentityGeneration !== settingsIdentityGeneration) return false;
    const current = captureAppAuthBoundary();
    return current.ownerId === snapshot.ownerId && current.revision === snapshot.revision;
}

function bindProfileManagerToAuthenticatedUser(user) {
    const ownerId = String(user?.id || '').trim();
    const manager = currentProfile || window.profileManager || window.currentProfile || null;
    if (!ownerId || !manager) return manager;
    manager.bindOwner?.(ownerId);
    currentProfile = manager;
    window.currentProfile = manager;
    window.profileManager = manager;
    return manager;
}

function neutralGreetingText() {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning.';
    if (hour < 17) return 'Good afternoon.';
    return 'Good evening.';
}

function scrubProfileAndSettingsAuthBoundary() {
    settingsIdentityGeneration += 1;
    settingsIdentityRequest = null;
    settingsSaveController?.abort?.();
    settingsSaveController = null;

    const manager = currentProfile || window.profileManager || window.currentProfile || null;
    manager?.scrubOwner?.();
    if (manager) {
        currentProfile = manager;
        window.currentProfile = manager;
        window.profileManager = manager;
    }

    const modal = document.getElementById('settingsModal');
    const focusedInSettings = Boolean(modal?.contains(document.activeElement));
    if (modal) {
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
    }
    restoreSettingsBackground();
    if (focusedInSettings && typeof document.activeElement?.blur === 'function') {
        document.activeElement.blur();
    }
    settingsReturnFocus = null;
    settingsBaselineSignature = '';

    document.querySelectorAll('[data-v1-settings-tab]').forEach(button => {
        const active = button.dataset.v1SettingsTab === 'profile';
        button.classList.toggle('is-active', active);
        if (active) button.setAttribute('aria-current', 'page');
        else button.removeAttribute('aria-current');
    });
    document.querySelectorAll('[data-v1-settings-panel]').forEach(panel => {
        const active = panel.dataset.v1SettingsPanel === 'profile';
        panel.classList.toggle('is-active', active);
        panel.hidden = !active;
    });

    for (const id of SETTINGS_EDITABLE_IDS) {
        const field = document.getElementById(id);
        if (!field) continue;
        if (field.type === 'checkbox') field.checked = false;
        else field.value = '';
        field.removeAttribute('aria-busy');
    }
    const email = document.getElementById('settingsEmail');
    if (email) {
        email.value = '';
        email.readOnly = true;
        email.removeAttribute('aria-busy');
        email.placeholder = 'Sign in to view account email';
    }
    const saveButton = document.getElementById('saveSettingsBtn');
    if (saveButton) {
        delete saveButton.dataset.settingsSaving;
        saveButton.disabled = true;
        saveButton.hidden = false;
        saveButton.removeAttribute('aria-busy');
        saveButton.setAttribute('aria-disabled', 'true');
        saveButton.title = 'No changes to save';
        saveButton.textContent = 'Save changes';
    }
    const workHours = document.getElementById('workHoursGroup');
    if (workHours) workHours.style.display = 'none';

    document.querySelectorAll('.assistant-name').forEach(element => { element.textContent = 'Crump'; });
    const composer = document.getElementById('userInput');
    if (composer) {
        composer.placeholder = 'Message Crump';
        composer.setAttribute('aria-label', 'Message Crump');
    }
    const greeting = document.getElementById('v1Greeting');
    if (greeting) greeting.textContent = neutralGreetingText();

    // These modules own their own private memory and in-flight requests. The
    // direct calls cover the brief interval before their idempotent boundary
    // registrations are established during deferred runtime startup.
    window.CrumpPresence?.scrubAuthBoundary?.();
    window.CrumpAccountBoundary?.scrubAuthBoundary?.();
}

// Authentication changes must clear the live conversation projection without
// touching either account's durable, owner-scoped cache. Projects and other
// private views may remain mounted while a new HttpOnly session becomes
// authoritative, so this API deliberately owns both app.js's lexical state and
// the visible legacy conversation DOM.
function scrubConversationAuthBoundary() {
    scrubProfileAndSettingsAuthBoundary();
    scrubVoiceAuthBoundary();
    chats = [];
    currentChatId = null;
    window.chats = chats;
    window.currentChatId = null;
    window.__crumpSyncData = null;
    if (window.syncDebounceTimer) {
        window.clearTimeout(window.syncDebounceTimer);
        window.syncDebounceTimer = null;
    }
    document.getElementById('chatsList')?.replaceChildren();
    try { window.renderMessages?.([]); } catch (_) {}
    // A renderer may be absent, stale, or layered by an enhancement. Emptying
    // the authoritative container last guarantees no prior owner's messages
    // survive until the next account explicitly opens one of its own chats.
    document.getElementById('chatContainer')?.replaceChildren();
}
window.CrumpConversationState = Object.freeze({
    scrubAuthBoundary: scrubConversationAuthBoundary,
    checkSessionHealth: (...args) => checkSessionHealth(...args),
});
window.CrumpProfileState = Object.freeze({
    bindAuthenticatedUser: bindProfileManagerToAuthenticatedUser,
    scrubAuthBoundary: scrubProfileAndSettingsAuthBoundary,
});
window.CrumpAuthBoundary?.register?.('workspace-conversations', scrubConversationAuthBoundary);

const COMPOSER_SCAFFOLDS = Object.freeze({
    image: 'Generate an image of ',
    research: 'Search the web for ',
});
const USAGE_PREFLIGHT_TIMEOUT_MS = 10_000;

function requirePaidToolAccess(label) {
    const guard = window.CrumpAccess?.requirePaidTool;
    if (typeof guard === 'function') return guard(label);
    window.showToast?.(`${label} is unavailable until account access finishes loading.`, 'info');
    return false;
}
const SETTINGS_EDITABLE_IDS = Object.freeze([
    'settingsName',
    'assistantName',
    'workMode',
    'workStart',
    'workEnd',
    'crumpCheckIns',
    'checkInFrequency',
    'quietStart',
    'quietEnd',
    'crumpNotifications',
    'crumpHaptics',
    'checkInFollowups',
    'checkInReminders',
    'checkInGoals',
    'checkInEncouragement',
]);
const SETTINGS_EDITABLE_ID_SET = new Set(SETTINGS_EDITABLE_IDS);

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

function isPristineChat(chat) {
    const title = String(chat?.title || 'New conversation').trim().toLowerCase();
    return (!Array.isArray(chat?.messages) || chat.messages.length === 0) &&
        (!title || title === 'new conversation');
}

// Authenticated lifecycle
window.initializeAuthenticatedApp = function(user) {
    // Store user info globally and isolate this account's offline cache.
    window.currentUser = user;
    window.configureUserStorage?.(user.id);

    // Rebind before any server fallback can read or write the retained
    // manager. A same-document account change must start from this owner's
    // cache (or defaults), never the previous owner's in-memory profile.
    const profileManager = bindProfileManagerToAuthenticatedUser(user);
    if (profileManager && typeof profileManager.applyServerSubscription === 'function') {
        profileManager.applyServerSubscription(user);
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
        attachBtn.addEventListener('click', () => {
            if (!requirePaidToolAccess('File attachments')) return;
            fileInput.click();
        });
        fileInput.addEventListener('change', event => {
            if (!requirePaidToolAccess('File attachments')) {
                event.currentTarget.value = '';
                selectedFiles = [];
                return;
            }
            handleFileSelect(event);
        });
    } else {
        if (!attachBtn) console.warn('[UI] attachBtn not found - file attach disabled on this page');
        if (!fileInput) console.warn('[UI] fileInput not found - file attach disabled on this page');
    }

    const actions = [
        ['clearChatsBtn', () => clearAllChats()],
        ['settingsBtn', event => window.openSettings?.(event.currentTarget)],
        ['upgradeBtnSidebar', () => window.showUpgradePrompt?.()],
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
    chats = source
        .filter(chat => !(chat?.deleted_at || chat?.deletedAt) && !isPristineChat(chat))
        .map(normalizeLocalChat)
        .sort((a, b) => asTimestamp(b.updatedAt) - asTimestamp(a.updatedAt));
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

function announceConversationOpened(chatId, { fresh = false } = {}) {
    window.dispatchEvent(new CustomEvent('crump:conversation-opened', {
        detail: {
            chatId: String(chatId || '').trim(),
            fresh: Boolean(fresh),
        },
    }));
}

window.replaceChats = function replaceChats(nextChats, { preserveActiveRender = false } = {}) {
    const activeId = currentChatId;
    chats = (Array.isArray(nextChats) ? nextChats : []).map(normalizeLocalChat)
        .sort((a, b) => asTimestamp(b.updatedAt) - asTimestamp(a.updatedAt));
    window.chats = chats;
    SafeStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
    renderChatsList();
    if (freshConversationRequested) {
        currentChatId = null;
        window.currentChatId = null;
        SafeStorage.removeItem(STORAGE_KEYS.CURRENT_CHAT);
        window.renderMessages?.([]);
        announceConversationOpened('', { fresh: true });
        return;
    }
    const preferred = chats.find(chat => chat.id === activeId) || chats[0];
    if (preferred) {
        currentChatId = preferred.id;
        window.currentChatId = currentChatId;
        SafeStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, currentChatId);
        if (!preserveActiveRender || preferred.id !== activeId) {
            window.renderMessages?.(preferred.messages);
            announceConversationOpened(currentChatId);
        }
    } else {
        currentChatId = null;
        window.currentChatId = null;
        SafeStorage.removeItem(STORAGE_KEYS.CURRENT_CHAT);
        window.renderMessages?.([]);
        announceConversationOpened('', { fresh: true });
    }
};

function newChatRecord() {
    const now = new Date().toISOString();
    const id = crypto.randomUUID();
    return {
        id,
        chat_id: id,
        title: 'New Conversation',
        messages: [],
        createdAt: now,
        updatedAt: now,
        revision: 1,
    };
}

function beginFreshConversation() {
    freshConversationRequested = true;
    currentChatId = null;
    window.currentChatId = null;
    SafeStorage.removeItem(STORAGE_KEYS.CURRENT_CHAT);
    renderChatsList();
    window.renderMessages?.([]);
    announceConversationOpened('', { fresh: true });
    closeConversationMenu();
    const input = document.getElementById('userInput');
    if (input) {
        input.value = '';
        input.focus();
    }
}

function ensureCurrentChat() {
    const active = chats.find(item => item.id === currentChatId);
    if (active) return active;

    const chat = newChatRecord();
    chats.unshift(chat);
    window.chats = chats;
    currentChatId = chat.id;
    window.currentChatId = chat.id;
    freshConversationRequested = false;
    announceConversationOpened(chat.id, { fresh: true });
    return chat;
}

function createNewChat() {
    beginFreshConversation();
}

function openFreshConversationAtStartup() {
    // A fresh desk is presentation state, not durable conversation data. The
    // first real message materializes the draft through ensureCurrentChat().
    // This prevents each newly signed-in device from syncing its own blank row.
    beginFreshConversation();
}

function loadChat(chatId, expectedBoundary = null) {
    if (expectedBoundary) {
        const ownerId = String(expectedBoundary.ownerId || '').trim();
        const revision = Number(expectedBoundary.revision);
        if (!ownerId || !conversationAuthBoundaryIsCurrent({ownerId, revision})) return false;
    }
    const chat = chats.find(item => item.id === chatId);
    if (!chat) return false;
    freshConversationRequested = false;
    currentChatId = chatId;
    window.currentChatId = chatId;
    SafeStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, chatId);
    renderChatsList();
    window.renderMessages?.(chat.messages);
    announceConversationOpened(chatId);
    closeConversationMenu();
    return true;
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
            if (event.target !== item) return;
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
window.ensureCurrentChat = ensureCurrentChat;

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

async function ensureUsageAvailable(authBoundary = captureConversationAuthBoundary()) {
    if (window.CrumpChatTransport?.ensureUsage) {
        return window.CrumpChatTransport.ensureUsage({expectedOwnerId: authBoundary.ownerId});
    }
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), USAGE_PREFLIGHT_TIMEOUT_MS);
    try {
        const usageResponse = await fetch('/api/usage/check', {
            signal: controller.signal,
            headers: authBoundary.ownerId
                ? {'X-Ask-Crump-Expected-Owner': authBoundary.ownerId}
                : {},
        });
        if (usageResponse.status === 401) throw new Error('Your session expired. Please sign in again.');
        const usageData = await usageResponse.json().catch(() => ({}));
        if (usageResponse.ok && usageData.limits?.messages !== -1 && usageData.usage?.messages >= usageData.limits?.messages) {
            window.showUpgradePrompt?.();
            throw new Error('Your daily message limit has been reached.');
        }
    } catch (error) {
        if (error?.name === 'AbortError') {
            throw new Error('Message check took too long. Your draft is still here — try again.');
        }
        if (['Your session expired. Please sign in again.', 'Your daily message limit has been reached.'].includes(error?.message)) {
            throw error;
        }
        throw new Error('Crump could not check message availability. Check your connection and try again.');
    } finally {
        window.clearTimeout(timeoutId);
    }
}

function syncCompletedReplyInBackground() {
    try {
        void Promise.resolve(window.syncChatsToServer?.()).catch(() => {
            console.warn('Completed reply sync deferred; background sync will retry.');
        });
    } catch (_) {
        console.warn('Completed reply sync deferred; background sync will retry.');
    }
}

function runCompletedCreationHandoffInBackground(data) {
    try {
        let pending = null;
        if (data.manuscriptWorkspace?.autoOpen) {
            pending = window.CrumpProduct53?.handleCreationHandoff?.({kind: 'manuscript', workspace: data.manuscriptWorkspace});
        } else if (data.creationHandoff) {
            pending = window.CrumpProduct53?.handleCreationHandoff?.(data.creationHandoff);
        } else {
            return;
        }
        void Promise.resolve(pending).catch(() => {
            console.warn('Completed creation handoff deferred; the saved reply remains available.');
        });
    } catch (_) {
        console.warn('Completed creation handoff deferred; the saved reply remains available.');
    }
}

function completeUserMessage(chat, userMessage, data) {
    const serverAssistant = data.assistantMessage && typeof data.assistantMessage === 'object'
        ? data.assistantMessage
        : {};
    const assistantMessage = {
        ...serverAssistant,
        id: serverAssistant.id || messageId(),
        role: 'assistant',
        content: serverAssistant.content ?? data.response ?? '',
        timestamp: serverAssistant.timestamp || new Date().toISOString(),
        origin: 'reply',
        inReplyTo: userMessage.id,
    };
    for (const key of ['imageUrl', 'imagePrompt', 'imageFile', 'referencePlan', 'referenceReview', 'artifact', 'artifactRecovery', 'projectAttachments', 'manuscriptWorkspace', 'creationHandoff', 'intelligence']) {
        if (assistantMessage[key] == null && data[key] != null) assistantMessage[key] = data[key];
    }
    const existingIndex = chat.messages.findIndex(item =>
        item.role === 'assistant' && item.inReplyTo === userMessage.id
    );
    if (existingIndex >= 0) chat.messages[existingIndex] = {...chat.messages[existingIndex], ...assistantMessage};
    else chat.messages.push(assistantMessage);
    userMessage.deliveryStatus = 'seen';
    userMessage.replyStatus = 'replied';
    userMessage.replyError = null;
    if (data.conversationRevision) {
        chat.revision = Math.max(Number(chat.revision || 1), Number(data.conversationRevision || 1));
    }
    touchChat(chat);
    saveChats();
    window.CrumpPresence?.stop?.();
    window.renderMessages?.(chat.messages);
    renderChatsList();
    window.CrumpPresence?.haptic?.('success');
    runCompletedCreationHandoffInBackground(data);
    syncCompletedReplyInBackground();
    setTimeout(() => { void window.CrumpLifecycle?.evaluate?.({force: true}); }, 1200);
}

function applyCompletedReplySafely(chat, userMessage, data) {
    try {
        completeUserMessage(chat, userMessage, data);
        return true;
    } catch (_) {
        try { window.CrumpPresence?.stop?.(); } catch (_) {}
        try {
            console.warn('Completed reply presentation deferred; the saved reply remains authoritative.');
        } catch (_) {}
        try {
            showToast(
                'Your reply was saved, but this screen could not finish updating. Refresh this conversation to load the saved reply.',
                'warning',
            );
        } catch (_) {}
        return false;
    }
}

async function processUserMessage(chat, userMessage, attachment = null, authBoundary = captureConversationAuthBoundary()) {
    if (!conversationAuthBoundaryIsCurrent(authBoundary)) throw conversationBoundaryAbortError();
    if (!navigator.onLine || window.CrumpPresence?.online === false) {
        updateMessageState(chat, userMessage, { deliveryStatus: 'queued', replyStatus: 'pending' });
        throw Object.assign(new Error('This message is waiting for a connection.'), { quiet: true });
    }

    const syncResult = await window.syncChatsToServer?.();
    if (!conversationAuthBoundaryIsCurrent(authBoundary)) throw conversationBoundaryAbortError();
    if (syncResult && syncResult.success === false) {
        updateMessageState(chat, userMessage, { deliveryStatus: 'queued', replyStatus: 'pending' });
        throw Object.assign(new Error('This message is waiting to sync.'), { quiet: true });
    }
    updateMessageState(chat, userMessage, { deliveryStatus: 'delivered', replyStatus: 'pending' });
    window.CrumpPresence?.haptic?.('light');

    const transport = window.CrumpChatTransport;
    if (!transport) throw new Error('Message delivery is still loading. Try again.');
    const ackData = await transport.acknowledge({
        chatId: chat.id,
        messageId: userMessage.id,
        message: userMessage.content || '',
        fileTypes: (userMessage.files || []).map(file => file.type),
    }, {expectedOwnerId: authBoundary.ownerId});
    if (!conversationAuthBoundaryIsCurrent(authBoundary)) throw conversationBoundaryAbortError();
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

    const data = await transport.send(requestBody, {expectedOwnerId: authBoundary.ownerId});
    if (!conversationAuthBoundaryIsCurrent(authBoundary)) throw conversationBoundaryAbortError();
    applyCompletedReplySafely(chat, userMessage, data);
    window.CrumpAccess?.applyServerAllowance?.(data);
}

async function sendMessage() {
    if (isProcessing) return;
    const authBoundary = captureConversationAuthBoundary();
    if (!authBoundary.ownerId) return;
    const userInput = document.getElementById('userInput');
    const message = userInput?.value.trim() || '';
    if (!message && selectedFiles.length === 0) return;
    if (selectedFiles.length && !requirePaidToolAccess('File attachments')) return;
    const incompleteScaffold = Object.entries(COMPOSER_SCAFFOLDS)
        .find(([, scaffold]) => message.toLowerCase() === scaffold.trim().toLowerCase());
    if (incompleteScaffold) {
        const guidance = {
            image: 'Add what you want Crump to create.',
            research: 'Add what you want Crump to research.',
        }[incompleteScaffold[0]];
        showToast(guidance, 'info');
        userInput?.focus({ preventScroll: true });
        return;
    }
    let chat = chats.find(item => item.id === currentChatId) || null;
    isProcessing = true;
    window.CrumpLifecycle?.suppressActiveWork?.();
    let userMessage = null;

    try {
        await ensureUsageAvailable(authBoundary);
        if (!conversationAuthBoundaryIsCurrent(authBoundary)) throw conversationBoundaryAbortError();
        let attachment = null;
        if (selectedFiles.length) {
            const file = selectedFiles[0];
            attachment = { type: file.type, name: file.name, data: await readFileAsBase64(file) };
            if (!conversationAuthBoundaryIsCurrent(authBoundary)) throw conversationBoundaryAbortError();
        }
        if (!conversationAuthBoundaryIsCurrent(authBoundary)) throw conversationBoundaryAbortError();
        chat = chats.find(item => item.id === currentChatId) || ensureCurrentChat();

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

        await processUserMessage(chat, userMessage, attachment, authBoundary);
    } catch (error) {
        if (!conversationAuthBoundaryIsCurrent(authBoundary)) return;
        console.error('[Chat]', error);
        window.CrumpAccess?.onChatError?.(error);
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
                    replyError: error.message || 'Crump’s reply didn’t come through.',
                });
                window.CrumpPresence?.haptic?.('error');
                showToast(error.message || 'That didn’t send — let’s try that again.', 'error');
            }
        } else {
            window.CrumpPresence?.haptic?.('error');
            showToast(error.message || 'Hmm, that didn’t go through — want to try again?', 'error');
            userInput?.focus({ preventScroll: true });
        }
    } finally {
        isProcessing = false;
    }
}

window.retryMessage = async function retryMessage(id) {
    if (isProcessing || !id) return;
    const authBoundary = captureConversationAuthBoundary();
    if (!authBoundary.ownerId) return;
    const chat = chats.find(item => item.id === currentChatId);
    const message = chat?.messages.find(item => item.id === id && item.role === 'user');
    if (!chat || !message) return;
    if (message.files?.length) {
        showToast('Reattach the file before retrying this message.', 'warning');
        return;
    }
    isProcessing = true;
    window.CrumpLifecycle?.suppressActiveWork?.();
    try {
        const recovered = await window.CrumpChatTransport?.recover?.(id, {
            expectedOwnerId: authBoundary.ownerId,
        });
        if (!conversationAuthBoundaryIsCurrent(authBoundary)) return;
        if (recovered) {
            applyCompletedReplySafely(chat, message, recovered);
            return;
        }
        await ensureUsageAvailable(authBoundary);
        if (!conversationAuthBoundaryIsCurrent(authBoundary)) return;
        updateMessageState(chat, message, { deliveryStatus: 'sending', replyStatus: 'pending', replyError: null });
        await processUserMessage(chat, message, null, authBoundary);
    } catch (error) {
        if (!conversationAuthBoundaryIsCurrent(authBoundary)) return;
        console.error('[Chat retry]', error);
        window.CrumpAccess?.onChatError?.(error);
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
                replyError: error.message || 'Crump’s reply didn’t come through.',
            });
            window.CrumpPresence?.haptic?.('error');
            showToast(error.message || 'The retry didn’t land — one more try?', 'error');
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
let activeVoiceController = null;
let premiumVoiceCapability = {available: false, checkedAt: 0, ownerId: ''};

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

function scrubVoiceAuthBoundary() {
    voiceRequestSequence += 1;
    activeVoiceController?.abort?.();
    activeVoiceController = null;
    premiumVoiceCapability = {available: false, checkedAt: 0, ownerId: ''};
    clearPremiumVoice();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
}

function voiceOperationIsCurrent(requestId, authBoundary, controller) {
    return requestId === voiceRequestSequence
        && controller === activeVoiceController
        && !controller?.signal?.aborted
        && conversationAuthBoundaryIsCurrent(authBoundary);
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

async function canUsePremiumVoice(authBoundary, controller) {
    if (!conversationAuthBoundaryIsCurrent(authBoundary)) return false;
    const now = Date.now();
    if (premiumVoiceCapability.ownerId === authBoundary.ownerId
        && now - premiumVoiceCapability.checkedAt < 5 * 60 * 1000) {
        return premiumVoiceCapability.available;
    }
    try {
        const response = await fetch('/api/features', {
            credentials: 'same-origin',
            headers: {'X-Ask-Crump-Expected-Owner': authBoundary.ownerId},
            signal: controller.signal,
        });
        const data = response.ok ? await response.json() : {};
        if (!conversationAuthBoundaryIsCurrent(authBoundary) || controller.signal.aborted) return false;
        const feature = data?.features?.premium_voice || {};
        premiumVoiceCapability = {
            available: Boolean(feature.configured && feature.entitled),
            checkedAt: now,
            ownerId: authBoundary.ownerId,
        };
    } catch (_) {
        if (!controller.signal.aborted && conversationAuthBoundaryIsCurrent(authBoundary)) {
            premiumVoiceCapability = {available: false, checkedAt: now, ownerId: authBoundary.ownerId};
        }
    }
    return conversationAuthBoundaryIsCurrent(authBoundary)
        && premiumVoiceCapability.ownerId === authBoundary.ownerId
        && premiumVoiceCapability.available;
}

// Read assistant responses aloud. Premium voice is requested only after this
// explicit click; long responses and unavailable accounts stay on-device.
window.speakText = async function(text) {
    const readable = String(text || '').trim();
    if (!readable) return;
    const authBoundary = captureConversationAuthBoundary();
    if (!conversationAuthBoundaryIsCurrent(authBoundary)) return;
    voiceRequestSequence += 1;
    const requestId = voiceRequestSequence;
    activeVoiceController?.abort?.();
    const controller = new AbortController();
    activeVoiceController = controller;
    clearPremiumVoice();
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (readable.length > 4000) {
        if (voiceOperationIsCurrent(requestId, authBoundary, controller)) {
            speakWithDeviceVoice(readable, 'Using your device voice for this longer response.');
        }
        return;
    }
    const premiumAvailable = await canUsePremiumVoice(authBoundary, controller);
    if (!voiceOperationIsCurrent(requestId, authBoundary, controller)) return;
    if (!premiumAvailable) {
        speakWithDeviceVoice(readable);
        return;
    }
    showToast('Creating Crump Voice...', 'info');
    const idempotencyKey = crypto.randomUUID?.() || `${Date.now()}-${requestId}`;
    try {
        const execute = async creditConfirmation => {
            const response = await fetch('/api/voice/synthesize', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Ask-Crump-Expected-Owner': authBoundary.ownerId,
                },
                body: JSON.stringify({
                    text: readable,
                    idempotencyKey,
                    ...(creditConfirmation ? {creditConfirmation} : {}),
                }),
                signal: controller.signal,
            });
            if (!voiceOperationIsCurrent(requestId, authBoundary, controller)) {
                throw conversationBoundaryAbortError();
            }
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                if ([401, 403, 503].includes(response.status)) {
                    premiumVoiceCapability = {
                        available: false,
                        checkedAt: Date.now(),
                        ownerId: authBoundary.ownerId,
                    };
                }
                const error = new Error(data.error || `Premium voice unavailable (${response.status})`);
                error.code = data.code;
                error.data = data;
                error.status = response.status;
                throw error;
            }
            return response;
        };
        const response = window.CrumpCreditConfirmation?.run
            ? await window.CrumpCreditConfirmation.run(execute, authBoundary)
            : await execute(null);
        const audioBlob = await response.blob();
        if (!voiceOperationIsCurrent(requestId, authBoundary, controller) || !audioBlob.size) return;
        activeVoiceObjectUrl = URL.createObjectURL(audioBlob);
        activeVoiceAudio = new Audio(activeVoiceObjectUrl);
        activeVoiceAudio.addEventListener('ended', clearPremiumVoice, {once: true});
        activeVoiceAudio.addEventListener('error', clearPremiumVoice, {once: true});
        await activeVoiceAudio.play();
        if (!voiceOperationIsCurrent(requestId, authBoundary, controller)) {
            clearPremiumVoice();
            return;
        }
        showToast('Reading with Crump Voice...', 'info');
    } catch (_) {
        if (voiceOperationIsCurrent(requestId, authBoundary, controller)) {
            clearPremiumVoice();
            speakWithDeviceVoice(readable, 'Using your device voice.');
        }
    } finally {
        if (activeVoiceController === controller) activeVoiceController = null;
    }
};

window.stopSpeaking = function() {
    scrubVoiceAuthBoundary();
};

// Quick Actions
function primeComposer(scaffold) {
    const input = document.getElementById('userInput');
    if (!input) return false;
    const draft = input.value.trim();
    const normalizedScaffold = scaffold.trim().toLowerCase();
    const normalizedDraft = draft.toLowerCase();
    const alreadyPrimed = normalizedDraft === normalizedScaffold
        || normalizedDraft.startsWith(`${normalizedScaffold} `);
    if (!draft) input.value = scaffold;
    else if (!alreadyPrimed) input.value = `${scaffold}${draft}`;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus({ preventScroll: true });
    input.setSelectionRange?.(input.value.length, input.value.length);
    return true;
}

window.triggerImageGeneration = function() {
    if (!window.CrumpAccess?.requirePaidTool?.('Image Studio')) return false;
    return primeComposer(COMPOSER_SCAFFOLDS.image);
};

window.triggerWebSearch = function() {
    if (!window.CrumpAccess?.requirePaidTool?.('Research')) return false;
    window.dispatchEvent(new CustomEvent('crump:requested-tool', {
        detail: { tool: 'web' },
    }));
    return primeComposer(COMPOSER_SCAFFOLDS.research);
};

// Settings
function settingsDialog(modal = document.getElementById('settingsModal')) {
    return modal?.querySelector('[role="dialog"]') || null;
}

function settingsFocusableElements(dialog) {
    if (!dialog) return [];
    const selector = [
        'a[href]',
        'button:not([disabled])',
        'input:not([disabled])',
        'select:not([disabled])',
        'textarea:not([disabled])',
        '[tabindex]:not([tabindex="-1"])',
    ].join(',');
    return Array.from(dialog.querySelectorAll(selector)).filter(element => {
        if (element.hidden || element.closest('[hidden]') || element.getAttribute('aria-hidden') === 'true') return false;
        const style = getComputedStyle(element);
        return style.display !== 'none' && style.visibility !== 'hidden' && element.getClientRects().length > 0;
    });
}

function setSettingsBackgroundInert(modal) {
    if (settingsBackgroundState.length) return;
    settingsBackgroundState = Array.from(document.body.children)
        .filter(element => element !== modal
            && element.id !== 'toastContainer'
            && !['SCRIPT', 'STYLE', 'LINK', 'TEMPLATE'].includes(element.tagName))
        .map(element => ({ element, wasInert: element.hasAttribute('inert') }));
    settingsBackgroundState.forEach(({element}) => element.setAttribute('inert', ''));
}

function restoreSettingsBackground() {
    settingsBackgroundState.forEach(({element, wasInert}) => {
        if (!wasInert) element.removeAttribute('inert');
    });
    settingsBackgroundState = [];
}

function wireSettingsModalAccessibility(modal) {
    if (!modal || modal.dataset.accessibilityWired === 'true') return;
    modal.dataset.accessibilityWired = 'true';
    modal.addEventListener('click', event => {
        if (event.target === modal) window.closeSettings?.();
    });
    modal.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            window.closeSettings?.();
            return;
        }
        if (event.key !== 'Tab') return;
        const dialog = settingsDialog(modal);
        const focusable = settingsFocusableElements(dialog);
        if (!focusable.length) {
            event.preventDefault();
            document.getElementById('settingsTitle')?.focus({preventScroll: true});
            return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus({preventScroll: true});
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus({preventScroll: true});
        }
    });
}

window.openSettings = function(opener = null) {
    const modal = document.getElementById('settingsModal');
    if (!modal) return;
    const wasOpen = getComputedStyle(modal).display !== 'none';
    if (!wasOpen && !modal.contains(document.activeElement)) settingsReturnFocus = opener || document.activeElement;
    wireSettingsModalAccessibility(modal);
    setSettingsBackgroundInert(modal);
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
    loadSettingsValues();
    scheduleSettingsIdentityPresentation();
    window.requestAnimationFrame(() => document.getElementById('settingsTitle')?.focus({preventScroll: true}));
};

window.closeSettings = function() {
    const modal = document.getElementById('settingsModal');
    if (!modal) return;
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
    restoreSettingsBackground();
    const returnFocus = settingsReturnFocus;
    settingsReturnFocus = null;
    const isVisibleControl = element => Boolean(
        element?.isConnected
        && typeof element.focus === 'function'
        && !element.disabled
        && !element.hidden
        && !element.closest?.('[hidden], [inert], [aria-hidden="true"]')
        && element.getClientRects?.().length
    );
    const fallback = Array.from(document.querySelectorAll(
        '[data-cv-destination="profile"], [data-cv-destination="more"], #settingsBtn, [data-crump5930-destination="you"]'
    )).find(isVisibleControl);
    const focusTarget = isVisibleControl(returnFocus) ? returnFocus : fallback;
    focusTarget?.focus({preventScroll: true});
};

function loadSettings() {
    // Settings are loaded from the synchronized cache by the auth controller.
}

function settingsFormSignature() {
    return SETTINGS_EDITABLE_IDS.map(id => {
        const field = document.getElementById(id);
        if (!field) return `${id}:missing`;
        const value = field.type === 'checkbox' ? String(field.checked) : String(field.value || '');
        return `${id}:${value}`;
    }).join('|');
}

function syncSettingsSaveState() {
    const saveButton = document.getElementById('saveSettingsBtn');
    if (!saveButton || saveButton.dataset.settingsSaving === 'true') return;
    const dirty = Boolean(settingsBaselineSignature) && settingsFormSignature() !== settingsBaselineSignature;
    saveButton.disabled = !dirty;
    saveButton.setAttribute('aria-disabled', dirty ? 'false' : 'true');
    saveButton.title = dirty ? 'Save your changes' : 'No changes to save';
}

function resetSettingsSaveState() {
    settingsBaselineSignature = settingsFormSignature();
    syncSettingsSaveState();
}

function wireSettingsSaveState() {
    const modal = document.getElementById('settingsModal');
    if (!modal || modal.dataset.settingsDirtyWired === 'true') return;
    modal.dataset.settingsDirtyWired = 'true';
    const update = event => {
        if (SETTINGS_EDITABLE_ID_SET.has(event.target?.id)) syncSettingsSaveState();
    };
    modal.addEventListener('input', update);
    modal.addEventListener('change', update);
}

function syncSettingsIdentityPresentation() {
    const emailField = document.getElementById('settingsEmail');
    if (!emailField) return;
    const displayedEmail = String(emailField.value || '').trim();
    emailField.value = displayedEmail;
    emailField.readOnly = true;
    emailField.placeholder = displayedEmail ? 'you@email.com' : 'Sign in to view account email';
}

function scheduleSettingsIdentityPresentation() {
    [0, 250, 1000].forEach(delay => {
        window.setTimeout(() => {
            const modal = document.getElementById('settingsModal');
            if (modal && getComputedStyle(modal).display !== 'none') syncSettingsIdentityPresentation();
        }, delay);
    });
}

async function restoreSettingsIdentity() {
    const emailField = document.getElementById('settingsEmail');
    if (!emailField || String(emailField.value || '').trim() || settingsIdentityRequest) return settingsIdentityRequest;
    const authBoundary = captureAppAuthBoundary();
    if (!authBoundary.ownerId) return null;
    emailField.setAttribute('aria-busy', 'true');
    emailField.placeholder = 'Confirming account email…';
    const request = Promise.resolve()
        // This identity fill is speculative UI work, not an authentication
        // transition. A delayed response must never commit an old account into
        // DeviceAuth's shared session/cache after another tab or login switched
        // the authoritative browser cookie.
        .then(() => window.deviceAuth?.checkSession?.({commit: false}))
        .then(result => {
            const user = result?.authenticated ? result.data?.user : null;
            const userEmail = String(user?.email || '').trim();
            if (!userEmail || String(user?.id || '').trim() !== authBoundary.ownerId
                || !appAuthBoundaryIsCurrent(authBoundary)) return;
            window.currentUser = { ...(window.currentUser || {}), ...user };
            window.configureUserStorage?.(user.id);
            const profileManager = bindProfileManagerToAuthenticatedUser(user);
            if (!appAuthBoundaryIsCurrent(authBoundary)) return;
            profileManager?.updateProfile?.({
                ...(user.fullName ? { name: user.fullName } : {}),
                email: userEmail,
            });
            if (!appAuthBoundaryIsCurrent(authBoundary)) return;
            emailField.value = userEmail;
        })
        .catch(() => {})
        .finally(() => {
            if (settingsIdentityRequest !== request) return;
            settingsIdentityRequest = null;
            if (!appAuthBoundaryIsCurrent(authBoundary)) return;
            emailField.removeAttribute('aria-busy');
            syncSettingsIdentityPresentation();
        });
    settingsIdentityRequest = request;
    return settingsIdentityRequest;
}

function loadSettingsValues() {
    const sessionUser = window.deviceAuth?.session?.user || {};
    const activeUser = window.currentUser || {};
    const sameSessionOwner = String(sessionUser.id || '').trim()
        && String(sessionUser.id || '').trim() === String(activeUser.id || '').trim();
    const user = sameSessionOwner ? { ...sessionUser, ...activeUser } : { ...activeUser };
    const profileManager = bindProfileManagerToAuthenticatedUser(user);
    const profile = profileManager?.getProfile?.() || {};
    const settingsEmail = document.getElementById('settingsEmail');
    document.getElementById('settingsName').value = user.fullName || profile.name || '';
    settingsEmail.value = String(user.email || profile.email || '').trim();
    syncSettingsIdentityPresentation();
    if (!String(settingsEmail.value || '').trim()) void restoreSettingsIdentity();
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
    try {
        window.CrumpPresence?.applyPreferencesToForm?.();
    } catch (error) {
        console.warn('[Settings] Optional presence preferences could not be loaded:', error);
    }
    wireSettingsSaveState();
    resetSettingsSaveState();
}

window.addEventListener('crump:authenticated-ready', () => {
    const modal = document.getElementById('settingsModal');
    if (modal && getComputedStyle(modal).display !== 'none') scheduleSettingsIdentityPresentation();
});

window.saveSettings = async function() {
    const saveButton = document.getElementById('saveSettingsBtn');
    if (saveButton?.disabled || saveButton?.dataset.settingsSaving === 'true') return;
    const authBoundary = captureAppAuthBoundary();
    if (!authBoundary.ownerId || !appAuthBoundaryIsCurrent(authBoundary)) return;
    const syncAuthBoundary = Object.freeze({
        userId: authBoundary.ownerId,
        revision: authBoundary.revision,
    });
    settingsSaveController?.abort?.();
    const saveController = new AbortController();
    settingsSaveController = saveController;
    const saveIsCurrent = () => (
        settingsSaveController === saveController
        && !saveController.signal.aborted
        && appAuthBoundaryIsCurrent(authBoundary)
    );
    if (saveButton) {
        saveButton.dataset.settingsSaving = 'true';
        saveButton.disabled = true;
        saveButton.setAttribute('aria-busy', 'true');
        saveButton.textContent = 'Saving…';
    }
    const finishSaveAttempt = () => {
        if (!saveButton || !saveIsCurrent()) return;
        delete saveButton.dataset.settingsSaving;
        saveButton.removeAttribute('aria-busy');
        saveButton.textContent = 'Save changes';
    };
    const name = document.getElementById('settingsName').value.trim();
    const assistantName = document.getElementById('assistantName').value.trim() || 'Crump';
    const workMode = document.getElementById('workMode').checked;
    const workStart = document.getElementById('workStart').value;
    const workEnd = document.getElementById('workEnd').value;
    const capturedStorageKeys = Object.freeze({
        assistantName: STORAGE_KEYS.ASSISTANT_NAME,
        workMode: STORAGE_KEYS.WORK_MODE,
        workStart: STORAGE_KEYS.WORK_START,
        workEnd: STORAGE_KEYS.WORK_END,
    });
    if (!saveIsCurrent()) return;
    SafeStorage.setItem(capturedStorageKeys.assistantName, assistantName);
    SafeStorage.setItem(capturedStorageKeys.workMode, String(workMode));
    SafeStorage.setItem(capturedStorageKeys.workStart, workStart);
    SafeStorage.setItem(capturedStorageKeys.workEnd, workEnd);
    let profileError = null;
    let syncError = null;
    let presenceError = null;
    try {
        if (window.currentUser && name && name !== window.currentUser.fullName) {
            const response = await fetch('/api/account/profile', {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Ask-Crump-Expected-Owner': authBoundary.ownerId,
                },
                body: JSON.stringify({ fullName: name }),
                signal: saveController.signal,
            });
            const data = await response.json().catch(() => ({}));
            if (!saveIsCurrent()) return;
            if (!response.ok || !data.success || !data.user) {
                throw new Error(data.error || 'Your name could not be saved. Try again.');
            }
            window.currentUser = data.user;
        }
        if (!saveIsCurrent()) return;
        if (currentProfile && name) currentProfile.updateProfile({ name, initial: name.charAt(0).toUpperCase() });
        if (name) window.dispatchEvent(new CustomEvent('crump:profile-updated'));
    } catch (error) {
        if (!saveIsCurrent()) return;
        console.warn('[Profile settings]', error);
        profileError = error;
    }
    if (!saveIsCurrent()) return;
    try {
        if (typeof window.SyncManager?.push !== 'function') {
            throw new Error('Cross-device settings sync is unavailable.');
        }
        const syncResult = await window.SyncManager.push(null, {
            chats: [],
            settings: {
                assistant_name: assistantName,
                work_mode: workMode,
                work_start: Number(workStart),
                work_end: Number(workEnd),
            },
        }, {authBoundary: syncAuthBoundary});
        if (!saveIsCurrent()) return;
        if (syncResult?.success === false) {
            throw new Error(syncResult.error || 'Cross-device settings sync is pending.');
        }
    } catch (error) {
        if (!saveIsCurrent()) return;
        console.warn('[Settings sync]', error);
        syncError = error;
    }
    if (!saveIsCurrent()) return;
    try {
        if (typeof window.CrumpPresence?.savePreferences !== 'function') {
            throw new Error('Check-in preferences are unavailable.');
        }
        await window.CrumpPresence.savePreferences({
            ownerId: authBoundary.ownerId,
            revision: authBoundary.revision,
        });
        if (!saveIsCurrent()) return;
    } catch (error) {
        if (!saveIsCurrent()) return;
        console.warn('[Presence settings]', error);
        presenceError = error;
    }

    if (!saveIsCurrent()) return;
    updateAssistantNameDisplay();
    updateUserAvatar();
    const unsavedAreas = [];
    if (profileError) unsavedAreas.push('Your name');
    if (presenceError) unsavedAreas.push('Check-in preferences');
    if (unsavedAreas.length) {
        const subject = unsavedAreas.join(' and ');
        showToast(`${subject} could not be saved. Your unsaved changes remain here—try again.`, 'error');
    } else {
        resetSettingsSaveState();
        closeSettings();
        showToast(
            syncError ? 'Settings saved on this device; cross-device sync is still pending.' : 'Settings saved',
            syncError ? 'warning' : 'success',
        );
    }
    finishSaveAttempt();
    if (settingsSaveController === saveController) settingsSaveController = null;
    syncSettingsSaveState();
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
window.addEventListener('crump:server-settings-applied', () => {
    updateAssistantNameDisplay();
    const modal = document.getElementById('settingsModal');
    if (!modal || getComputedStyle(modal).display === 'none') return;
    const hasLocalDraft = Boolean(settingsBaselineSignature)
        && settingsFormSignature() !== settingsBaselineSignature;
    if (!hasLocalDraft) loadSettingsValues();
});
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

window.addEventListener('beforeunload', clearPreviewObjectUrls);

// Session Health Check
let tokenRefreshTimer = null;

function scrubAndReloadForOwnerMismatch(reload = () => window.location.reload()) {
    // The shared identity cache/native token may already belong to the next
    // account. Scrub only this document's memory/DOM, then reload; do not
    // clear another tab's or a just-completed native login's credentials.
    window.CrumpAuthBoundary?.observe?.(null);
    reload();
}

async function checkSessionHealth({reload} = {}) {
    if (document.hidden || !window.currentUser) return {skipped: true};
    const authBoundary = captureConversationAuthBoundary();
    if (!conversationAuthBoundaryIsCurrent(authBoundary)) return {skipped: true};
    try {
        const response = await fetch('/api/auth/check-session', {
            headers: {'X-Ask-Crump-Expected-Owner': authBoundary.ownerId},
        });
        const data = await response.json().catch(() => ({}));
        if (!conversationAuthBoundaryIsCurrent(authBoundary)) return {stale: true};
        if (response.ok && data.authenticated && data.data?.user) {
            if (String(data.data.user.id || '') !== authBoundary.ownerId) return {stale: true};
            window.currentUser = data.data.user;
            return {authenticated: true};
        }
        if (
            response.status === 409
            && (data.code === 'AUTH_OWNER_MISMATCH' || data.staleAuth === true)
        ) {
            scrubAndReloadForOwnerMismatch(reload);
            return {stale: true, reloading: true};
        }
        if (response.status === 401) {
            const cleared = await window.deviceAuth?.clearLocalState?.(authBoundary.ownerId);
            if (cleared === false) return {stale: true};
            window.location.href = '/app';
            return {authenticated: false, reloading: true};
        }
        return {authenticated: false};
    } catch (error) {
        console.warn('[Auth] Session health check failed:', error);
        return {error: true};
    }
}

async function setupTokenRefresh() {
    if (tokenRefreshTimer) clearInterval(tokenRefreshTimer);
    tokenRefreshTimer = setInterval(() => { void checkSessionHealth(); }, 12 * 60 * 60 * 1000);
}
window.setupTokenRefresh = setupTokenRefresh;
