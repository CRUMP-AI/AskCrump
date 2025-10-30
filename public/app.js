/*
==========================================
CRUMP AI - MAIN APPLICATION v2.0 ULTIMATE
Enhanced with professional-grade error handling,
performance optimizations, and code quality improvements
==========================================
*/

// ==========================================
// CONSTANTS & CONFIGURATION
// ==========================================
const CONFIG = {
    APP_VERSION: '2.0.0',
    APP_NAME: 'Crump AI',
    MAX_MESSAGE_LENGTH: 10000,
    MAX_FILE_SIZE: 10 * 1024 * 1024, // 10MB
    DEBOUNCE_DELAY: 300,
    TOAST_DURATION: 3000,
    AUTOSAVE_INTERVAL: 5000
};

const STORAGE_KEYS = Object.freeze({
    CHATS: 'crump_chats',
    CURRENT_CHAT: 'crump_current_chat',
    USER_PROFILE: 'crump_user_profile',
    USER_INITIAL: 'crump_user_initial',
    ASSISTANT_NAME: 'crump_assistant_name',
    WORK_MODE: 'crump_work_mode',
    AUTONOMOUS_ENABLED: 'crump_autonomous_enabled',
    AUTONOMOUS_FREQUENCY: 'crump_autonomous_frequency',
    HAS_ONBOARDED: 'crump_has_onboarded',
    WORK_START: 'crump_work_start',
    WORK_END: 'crump_work_end'
});

// ==========================================
// GLOBAL STATE
// ==========================================
const AppState = {
    chats: [],
    currentChatId: null,
    currentProfile: null,
    selectedFiles: [],
    isProcessing: false,
    autosaveTimer: null,
    isOnline: navigator.onLine
};

// Expose necessary state to window for backwards compatibility
window.chats = AppState.chats;
window.currentChatId = AppState.currentChatId;
window.STORAGE_KEYS = STORAGE_KEYS;

// ==========================================
// ERROR HANDLING
// ==========================================
class AppError extends Error {
    constructor(message, code, details = {}) {
        super(message);
        this.name = 'AppError';
        this.code = code;
        this.details = details;
        this.timestamp = Date.now();
    }
}

function handleError(error, context = '') {
    console.error(`❌ Error in ${context}:`, error);
    
    // Log to analytics/monitoring service here
    if (window.performanceMonitor) {
        window.performanceMonitor.logError(error, context);
    }
    
    // Show user-friendly message
    const userMessage = error instanceof AppError 
        ? error.message 
        : 'An unexpected error occurred. Please try again.';
    
    showToast(userMessage, 'error');
}

// ==========================================
// STORAGE UTILITIES
// ==========================================
const Storage = {
    isAvailable() {
        try {
            const test = '__storage_test__';
            localStorage.setItem(test, test);
            localStorage.removeItem(test);
            return true;
        } catch {
            return false;
        }
    },
    
    get(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(key);
            return item !== null ? JSON.parse(item) : defaultValue;
        } catch (error) {
            console.warn(`⚠️ Failed to get ${key} from storage:`, error);
            return defaultValue;
        }
    },
    
    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
            return true;
        } catch (error) {
            console.warn(`⚠️ Failed to set ${key} in storage:`, error);
            return false;
        }
    },
    
    remove(key) {
        try {
            localStorage.removeItem(key);
            return true;
        } catch (error) {
            console.warn(`⚠️ Failed to remove ${key} from storage:`, error);
            return false;
        }
    },
    
    clear() {
        try {
            localStorage.clear();
            return true;
        } catch (error) {
            console.warn('⚠️ Failed to clear storage:', error);
            return false;
        }
    }
};

// ==========================================
// INITIALIZATION
// ==========================================
window.initializeApp = async function() {
    try {
        console.log(`🚀 ${CONFIG.APP_NAME} v${CONFIG.APP_VERSION} initializing...`);
        
        // Validate required DOM elements
        validateRequiredElements();
        
        // Check storage availability
        if (!Storage.isAvailable()) {
            showToast('Warning: Storage unavailable. Data will not persist.', 'warning');
        }
        
        // Initialize profile manager
        await initializeProfileManager();
        
        // Initialize core components
        await initializeComponents();
        
        // Load saved data
        loadChats();
        loadSettings();
        
        // Setup event listeners
        setupEventListeners();
        setupSidebarToggle();
        setupNetworkListeners();
        
        // Initialize UI
        updateAssistantNameDisplay();
        initializeAssistant();
        
        // Initialize scroll manager
        initializeScrollManager();
        
        // Load or create chat
        await loadInitialChat();
        
        // Setup autonomous messaging
        setupAutonomousMessaging();
        
        // Setup mobile keyboard handler
        setupMobileKeyboardHandler();
        
        // Setup autosave
        setupAutosave();
        
        console.log(`✅ ${CONFIG.APP_NAME} v${CONFIG.APP_VERSION} initialized successfully`);
        
        // Show welcome message for new users
        if (Storage.get(STORAGE_KEYS.HAS_ONBOARDED) && !AppState.currentChatId) {
            showWelcomeMessage();
        }
        
    } catch (error) {
        handleError(error, 'initializeApp');
        // Show critical error UI
        showCriticalError();
    }
};

function validateRequiredElements() {
    const required = [
        'chatContainer',
        'userInput',
        'sendButton',
        'newChatBtn',
        'chatsList',
        'fileInput'
    ];
    
    const missing = required.filter(id => !document.getElementById(id));
    
    if (missing.length > 0) {
        throw new AppError(
            'Failed to initialize: Missing required elements',
            'MISSING_ELEMENTS',
            { missing }
        );
    }
}

async function initializeProfileManager() {
    try {
        if (typeof window.ProfileManager !== 'undefined') {
            AppState.currentProfile = new ProfileManager();
            updateUserAvatar();
            console.log('✅ ProfileManager initialized');
        } else if (typeof window.UserProfileManager !== 'undefined') {
            AppState.currentProfile = new UserProfileManager();
            updateUserAvatar();
            console.log('✅ UserProfileManager initialized');
        }
    } catch (error) {
        console.warn('⚠️ Failed to initialize profile manager:', error);
    }
}

async function initializeComponents() {
    try {
        // Initialize message deduplicator
        if (typeof window.messageDeduplicator === 'undefined') {
            window.messageDeduplicator = new MessageDeduplicator();
        }
        
        // Initialize search detection engine
        if (typeof window.SearchDetectionEngine !== 'undefined') {
            window.searchDetectionEngine = new SearchDetectionEngine();
            console.log('✅ Search Detection Engine initialized');
        }
        
        // Initialize weather detection engine
        if (typeof window.WeatherDetectionEngine !== 'undefined') {
            window.weatherDetectionEngine = new WeatherDetectionEngine();
            console.log('✅ Weather Detection Engine initialized');
        }
        
        // Initialize performance monitor
        if (typeof window.PerformanceMonitor !== 'undefined') {
            window.performanceMonitor = new PerformanceMonitor();
            console.log('✅ Performance Monitor initialized');
        }
        
    } catch (error) {
        console.warn('⚠️ Failed to initialize some components:', error);
    }
}

function initializeScrollManager() {
    try {
        if (window.crumpScrollManager && typeof window.crumpScrollManager.init === 'function') {
            window.crumpScrollManager.init();
            console.log('✅ Scroll manager initialized');
        }
    } catch (error) {
        console.warn('⚠️ Failed to initialize scroll manager:', error);
    }
}

async function loadInitialChat() {
    const savedChatId = Storage.get(STORAGE_KEYS.CURRENT_CHAT);
    
    if (savedChatId && getChat(savedChatId)) {
        loadChat(savedChatId);
    } else {
        createNewChat();
    }
}

function showCriticalError() {
    const appContainer = document.getElementById('appContainer');
    if (appContainer) {
        appContainer.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 100vh; padding: 2rem; text-align: center;">
                <div>
                    <h1 style="color: var(--color-accent-primary); margin-bottom: 1rem;">⚠️ Initialization Failed</h1>
                    <p style="margin-bottom: 1.5rem;">We encountered a problem starting the application.</p>
                    <button onclick="location.reload()" class="btn btn-primary">Reload Application</button>
                </div>
            </div>
        `;
    }
}

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
    
    // Auto-resize textarea with debounce
    let resizeTimeout;
    userInput.addEventListener('input', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            userInput.style.height = 'auto';
            userInput.style.height = Math.min(userInput.scrollHeight, 200) + 'px';
        }, 50);
    });
    
    // New chat
    newChatBtn.addEventListener('click', () => createNewChat());
    
    // File attachment
    attachBtn?.addEventListener('click', () => fileInput.click());
    fileInput?.addEventListener('change', handleFileSelect);
    
    // Voice input
    voiceBtn?.addEventListener('click', handleVoiceInput);
    
    // Prevent accidental page unload
    window.addEventListener('beforeunload', (e) => {
        if (AppState.isProcessing) {
            e.preventDefault();
            e.returnValue = '';
        }
    });
}

function setupSidebarToggle() {
    const menuBtn = document.getElementById('menuBtn');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const closeSidebarBtn = document.getElementById('closeSidebarBtn');
    
    if (!menuBtn || !sidebar || !sidebarOverlay) return;
    
    const openSidebar = () => {
        sidebar.classList.add('active');
        sidebarOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    };
    
    const closeSidebar = () => {
        sidebar.classList.remove('active');
        sidebarOverlay.classList.remove('active');
        document.body.style.overflow = '';
    };
    
    menuBtn.addEventListener('click', openSidebar);
    sidebarOverlay.addEventListener('click', closeSidebar);
    closeSidebarBtn?.addEventListener('click', closeSidebar);
    
    // Close on escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sidebar.classList.contains('active')) {
            closeSidebar();
        }
    });
}

function setupNetworkListeners() {
    window.addEventListener('online', () => {
        AppState.isOnline = true;
        showToast('Connection restored', 'success');
        console.log('🌐 Back online');
    });
    
    window.addEventListener('offline', () => {
        AppState.isOnline = false;
        showToast('Connection lost - Working offline', 'warning');
        console.log('📴 Offline');
    });
}

// ==========================================
// CHAT MANAGEMENT
// ==========================================
function loadChats() {
    try {
        const saved = Storage.get(STORAGE_KEYS.CHATS, []);
        AppState.chats = Array.isArray(saved) ? saved : [];
        window.chats = AppState.chats;
        
        console.log(`📚 Loaded ${AppState.chats.length} chats`);
    } catch (error) {
        console.error('❌ Failed to load chats:', error);
        AppState.chats = [];
        window.chats = AppState.chats;
    }
    
    renderChatsList();
}

function saveChats() {
    try {
        const success = Storage.set(STORAGE_KEYS.CHATS, AppState.chats);
        
        if (!success) {
            console.warn('⚠️ Failed to save chats');
        }
        
        return success;
    } catch (error) {
        console.error('❌ Error saving chats:', error);
        return false;
    }
}
window.saveChats = saveChats;

function setupAutosave() {
    // Auto-save every 5 seconds if there are changes
    AppState.autosaveTimer = setInterval(() => {
        if (AppState.chats.length > 0) {
            saveChats();
        }
    }, CONFIG.AUTOSAVE_INTERVAL);
}

function createNewChat() {
    try {
        const chat = {
            id: `chat_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            title: 'New Conversation',
            messages: [],
            createdAt: Date.now(),
            updatedAt: Date.now()
        };
        
        AppState.chats.unshift(chat);
        AppState.currentChatId = chat.id;
        window.currentChatId = chat.id;
        
        saveChats();
        Storage.set(STORAGE_KEYS.CURRENT_CHAT, chat.id);
        
        renderChatsList();
        renderMessages([]);
        
        const userInput = document.getElementById('userInput');
        userInput.value = '';
        userInput.style.height = 'auto';
        userInput.focus();
        
        console.log('✅ New chat created:', chat.id);
        
        return chat;
    } catch (error) {
        handleError(error, 'createNewChat');
        return null;
    }
}

function loadChat(chatId) {
    try {
        const chat = AppState.chats.find(c => c.id === chatId);
        
        if (!chat) {
            console.warn(`⚠️ Chat not found: ${chatId}`);
            createNewChat();
            return;
        }
        
        AppState.currentChatId = chatId;
        window.currentChatId = chatId;
        Storage.set(STORAGE_KEYS.CURRENT_CHAT, chatId);
        
        renderMessages(chat.messages);
        renderChatsList();
        
        // Update chat title in UI
        updateChatTitle(chat.title);
        
        console.log(`📖 Loaded chat: ${chatId}`);
    } catch (error) {
        handleError(error, 'loadChat');
    }
}

function getChat(chatId) {
    return AppState.chats.find(c => c.id === chatId);
}
window.getChat = getChat;

function updateChatTitle(title) {
    const titleElement = document.querySelector('.chat-title');
    if (titleElement) {
        titleElement.textContent = title || 'New Conversation';
    }
}

function deleteChat(chatId) {
    try {
        const index = AppState.chats.findIndex(c => c.id === chatId);
        
        if (index === -1) return;
        
        AppState.chats.splice(index, 1);
        saveChats();
        
        if (AppState.currentChatId === chatId) {
            if (AppState.chats.length > 0) {
                loadChat(AppState.chats[0].id);
            } else {
                createNewChat();
            }
        }
        
        renderChatsList();
        showToast('Chat deleted', 'success');
        
        console.log(`🗑️ Deleted chat: ${chatId}`);
    } catch (error) {
        handleError(error, 'deleteChat');
    }
}
window.deleteChat = deleteChat;

function renderChatsList() {
    const chatsList = document.getElementById('chatsList');
    if (!chatsList) return;
    
    if (AppState.chats.length === 0) {
        chatsList.innerHTML = `
            <div class="empty-state">
                <p>No conversations yet</p>
                <p class="text-secondary">Start a new chat to begin</p>
            </div>
        `;
        return;
    }
    
    chatsList.innerHTML = AppState.chats.map(chat => {
        const isActive = chat.id === AppState.currentChatId;
        const preview = chat.messages.length > 0 
            ? chat.messages[chat.messages.length - 1].content.substring(0, 50) + '...'
            : 'No messages yet';
        
        return `
            <div class="chat-item ${isActive ? 'active' : ''}" 
                 onclick="loadChat('${chat.id}')"
                 data-chat-id="${chat.id}">
                <div class="chat-item-content">
                    <div class="chat-item-title">${escapeHtml(chat.title)}</div>
                    <div class="chat-item-preview">${escapeHtml(preview)}</div>
                </div>
                <div class="chat-item-actions">
                    <button class="btn-icon" onclick="event.stopPropagation(); deleteChat('${chat.id}')" 
                            title="Delete chat" aria-label="Delete chat">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function renderMessages(messages) {
    const container = document.getElementById('chatContainer');
    if (!container) return;
    
    container.innerHTML = messages.map(msg => {
        const isUser = msg.role === 'user';
        const initial = isUser 
            ? (AppState.currentProfile?.profile?.initial || Storage.get(STORAGE_KEYS.USER_INITIAL, 'U'))
            : (Storage.get(STORAGE_KEYS.ASSISTANT_NAME, 'Crump')[0]);
        
        return `
            <div class="message ${isUser ? 'user-message' : 'assistant-message'}">
                <div class="message-avatar">${initial}</div>
                <div class="message-content">
                    <div class="message-text">${formatMessageContent(msg.content)}</div>
                    ${msg.timestamp ? `<div class="message-time">${formatTime(msg.timestamp)}</div>` : ''}
                </div>
            </div>
        `;
    }).join('');
    
    scrollToBottom();
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        const container = document.getElementById('chatContainer');
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
    });
}

function formatMessageContent(content) {
    // Escape HTML
    content = escapeHtml(content);
    
    // Format code blocks
    content = content.replace(/```(\w+)?\n([\s\S]+?)```/g, (_, lang, code) => {
        return `<pre><code class="language-${lang || 'text'}">${code.trim()}</code></pre>`;
    });
    
    // Format inline code
    content = content.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Format bold
    content = content.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    
    // Format italic
    content = content.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    
    // Format links
    content = content.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    
    // Format line breaks
    content = content.replace(/\n/g, '<br>');
    
    return content;
}

// ==========================================
// MESSAGE SENDING
// ==========================================
async function sendMessage() {
    const userInput = document.getElementById('userInput');
    const message = userInput.value.trim();
    
    if (!message || AppState.isProcessing) return;
    
    // Validate message length
    if (message.length > CONFIG.MAX_MESSAGE_LENGTH) {
        showToast(`Message too long (max ${CONFIG.MAX_MESSAGE_LENGTH} characters)`, 'error');
        return;
    }
    
    try {
        AppState.isProcessing = true;
        setAssistantState('listening');
        
        // Clear input
        userInput.value = '';
        userInput.style.height = 'auto';
        
        // Add user message
        const userMessage = {
            role: 'user',
            content: message,
            timestamp: Date.now()
        };
        
        const chat = getChat(AppState.currentChatId);
        if (!chat) {
            throw new AppError('Chat not found', 'CHAT_NOT_FOUND');
        }
        
        chat.messages.push(userMessage);
        chat.updatedAt = Date.now();
        
        // Update title from first message
        if (chat.messages.length === 1) {
            chat.title = message.substring(0, 30) + (message.length > 30 ? '...' : '');
        }
        
        saveChats();
        renderMessages(chat.messages);
        renderChatsList();
        
        // Show thinking indicator
        showThinking();
        setAssistantState('thinking');
        
        // Get AI response
        const response = await getAIResponse(message, chat.messages);
        
        // Add assistant message
        const assistantMessage = {
            role: 'assistant',
            content: response,
            timestamp: Date.now()
        };
        
        chat.messages.push(assistantMessage);
        chat.updatedAt = Date.now();
        
        saveChats();
        renderMessages(chat.messages);
        renderChatsList();
        
        setAssistantState('idle');
        
    } catch (error) {
        handleError(error, 'sendMessage');
        setAssistantState('error');
        
        // Show error message in chat
        const chat = getChat(AppState.currentChatId);
        if (chat) {
            chat.messages.push({
                role: 'assistant',
                content: 'Sorry, I encountered an error. Please try again.',
                timestamp: Date.now(),
                isError: true
            });
            renderMessages(chat.messages);
        }
    } finally {
        AppState.isProcessing = false;
        hideThinking();
        userInput.focus();
    }
}
window.sendMessage = sendMessage;

async function getAIResponse(message, chatHistory) {
    // This function should be implemented in chat.js
    if (typeof window.getAIResponse === 'function') {
        return await window.getAIResponse(message, chatHistory);
    }
    
    // Fallback
    throw new AppError('AI response handler not available', 'NO_AI_HANDLER');
}

// ==========================================
// FILE HANDLING
// ==========================================
async function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    
    if (files.length === 0) return;
    
    try {
        // Validate file sizes
        const oversized = files.filter(f => f.size > CONFIG.MAX_FILE_SIZE);
        if (oversized.length > 0) {
            showToast(`Files too large (max ${CONFIG.MAX_FILE_SIZE / 1024 / 1024}MB)`, 'error');
            return;
        }
        
        AppState.selectedFiles = files;
        
        // Show file preview
        showFilePreview(files);
        
        showToast(`${files.length} file(s) selected`, 'success');
        
    } catch (error) {
        handleError(error, 'handleFileSelect');
    }
    
    // Clear input
    event.target.value = '';
}

function showFilePreview(files) {
    // Implementation for file preview UI
    console.log('📎 Files selected:', files.map(f => f.name));
}

function handleVoiceInput() {
    // Voice input implementation
    if (typeof window.startVoiceInput === 'function') {
        window.startVoiceInput();
    } else {
        showToast('Voice input not available', 'error');
    }
}

// ==========================================
// SETTINGS
// ==========================================
function loadSettings() {
    try {
        document.getElementById('settingsName')?.setAttribute('value', 
            AppState.currentProfile?.profile?.name || '');
        document.getElementById('settingsEmail')?.setAttribute('value',
            AppState.currentProfile?.profile?.email || '');
        document.getElementById('assistantName')?.setAttribute('value',
            Storage.get(STORAGE_KEYS.ASSISTANT_NAME, 'Crump'));
        
        const autonomousEnabled = Storage.get(STORAGE_KEYS.AUTONOMOUS_ENABLED, false);
        const autonomousFrequency = Storage.get(STORAGE_KEYS.AUTONOMOUS_FREQUENCY, 'medium');
        const workMode = Storage.get(STORAGE_KEYS.WORK_MODE, false);
        
        const autonomousCheckbox = document.getElementById('autonomousMessaging');
        const workModeCheckbox = document.getElementById('workMode');
        const frequencySelect = document.getElementById('autonomousFrequency');
        const freqGroup = document.getElementById('autonomousFrequencyGroup');
        
        if (autonomousCheckbox) autonomousCheckbox.checked = autonomousEnabled;
        if (workModeCheckbox) workModeCheckbox.checked = workMode;
        if (frequencySelect) frequencySelect.value = autonomousFrequency;
        
        document.getElementById('workStart')?.setAttribute('value',
            Storage.get(STORAGE_KEYS.WORK_START, '9'));
        document.getElementById('workEnd')?.setAttribute('value',
            Storage.get(STORAGE_KEYS.WORK_END, '17'));
        
        if (freqGroup) {
            freqGroup.style.display = autonomousEnabled ? 'block' : 'none';
        }
        
        // Setup autonomous toggle listener
        autonomousCheckbox?.addEventListener('change', (e) => {
            if (freqGroup) {
                freqGroup.style.display = e.target.checked ? 'block' : 'none';
            }
        });
        
    } catch (error) {
        console.error('❌ Failed to load settings:', error);
    }
}

window.saveSettings = function() {
    try {
        const name = document.getElementById('settingsName')?.value.trim();
        const email = document.getElementById('settingsEmail')?.value.trim();
        const assistantName = document.getElementById('assistantName')?.value.trim() || 'Crump';
        const autonomousEnabled = document.getElementById('autonomousMessaging')?.checked;
        const autonomousFrequency = document.getElementById('autonomousFrequency')?.value;
        const workMode = document.getElementById('workMode')?.checked;
        const workStart = document.getElementById('workStart')?.value;
        const workEnd = document.getElementById('workEnd')?.value;
        
        // Update profile
        if (AppState.currentProfile && name) {
            AppState.currentProfile.updateProfile({
                name: name,
                email: email,
                initial: name.charAt(0).toUpperCase()
            });
        }
        
        // Save settings
        Storage.set(STORAGE_KEYS.ASSISTANT_NAME, assistantName);
        Storage.set(STORAGE_KEYS.AUTONOMOUS_ENABLED, autonomousEnabled);
        Storage.set(STORAGE_KEYS.AUTONOMOUS_FREQUENCY, autonomousFrequency);
        Storage.set(STORAGE_KEYS.WORK_MODE, workMode);
        Storage.set(STORAGE_KEYS.WORK_START, workStart);
        Storage.set(STORAGE_KEYS.WORK_END, workEnd);
        
        // Update autonomous messaging
        if (window.autonomousMessaging) {
            window.autonomousMessaging.toggle(autonomousEnabled);
            window.autonomousMessaging.setFrequency(autonomousFrequency);
        }
        
        updateAssistantNameDisplay();
        updateUserAvatar();
        closeSettings();
        showToast('Settings saved successfully', 'success');
        
        console.log('✅ Settings saved');
        
    } catch (error) {
        handleError(error, 'saveSettings');
    }
};

window.closeSettings = function() {
    const modal = document.getElementById('settingsModal');
    if (modal) {
        modal.style.display = 'none';
    }
};

// ==========================================
// UI HELPERS
// ==========================================
function updateAssistantNameDisplay() {
    const name = Storage.get(STORAGE_KEYS.ASSISTANT_NAME, 'Crump');
    document.querySelectorAll('.assistant-name').forEach(el => {
        el.textContent = name;
    });
}

function updateUserAvatar() {
    const initial = AppState.currentProfile?.profile?.initial ||
        Storage.get(STORAGE_KEYS.USER_INITIAL, 'U');
    Storage.set(STORAGE_KEYS.USER_INITIAL, initial);
    
    // Update avatar elements
    document.querySelectorAll('.user-avatar').forEach(el => {
        el.textContent = initial;
    });
}

function initializeAssistant() {
    setAssistantState('idle');
}

function setAssistantState(state) {
    const character = document.getElementById('assistantCharacter');
    if (character) {
        character.className = `assistant-character ${state}`;
    }
}
window.setAssistantState = setAssistantState;

function showThinking() {
    const indicator = document.getElementById('thinkingIndicator');
    if (indicator) {
        indicator.style.display = 'flex';
    }
}

function hideThinking() {
    const indicator = document.getElementById('thinkingIndicator');
    if (indicator) {
        indicator.style.display = 'none';
    }
}
window.showThinking = showThinking;
window.hideThinking = hideThinking;

function showWelcomeMessage() {
    try {
        const userName = AppState.currentProfile?.profile?.name || 'there';
        const assistantName = Storage.get(STORAGE_KEYS.ASSISTANT_NAME, 'Crump');
        
        const welcomeMessage = {
            role: 'assistant',
            content: `Hey ${userName}! I'm ${assistantName}, your AI assistant. I'm here to help with anything you need - from answering questions to helping with projects. What can I help you with today?`,
            timestamp: Date.now()
        };
        
        const chat = getChat(AppState.currentChatId);
        if (chat && chat.messages.length === 0) {
            chat.messages.push(welcomeMessage);
            saveChats();
            renderMessages(chat.messages);
        }
    } catch (error) {
        console.error('❌ Failed to show welcome message:', error);
    }
}

function setupAutonomousMessaging() {
    try {
        const enabled = Storage.get(STORAGE_KEYS.AUTONOMOUS_ENABLED, false);
        const frequency = Storage.get(STORAGE_KEYS.AUTONOMOUS_FREQUENCY, 'medium');
        
        if (window.autonomousMessaging) {
            window.autonomousMessaging.toggle(enabled);
            window.autonomousMessaging.setFrequency(frequency);
            console.log('✅ Autonomous messaging configured');
        }
    } catch (error) {
        console.warn('⚠️ Failed to setup autonomous messaging:', error);
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) {
        console.warn('Toast container not found');
        return;
    }
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    // Add icon based on type
    const icon = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    }[type] || 'ℹ';
    
    toast.innerHTML = `<span class="toast-icon">${icon}</span><span>${message}</span>`;
    
    container.appendChild(toast);
    
    // Trigger animation
    requestAnimationFrame(() => {
        toast.classList.add('toast-show');
    });
    
    // Remove after duration
    setTimeout(() => {
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 300);
    }, CONFIG.TOAST_DURATION);
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
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    
    return date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric',
        year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
    });
}

function escapeHtml(text) {
    if (typeof text !== 'string') return '';
    
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
window.escapeHtml = escapeHtml;

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ==========================================
// MOBILE KEYBOARD HANDLER
// ==========================================
function setupMobileKeyboardHandler() {
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    if (!isMobile) return;
    
    console.log('📱 Mobile detected - setting up keyboard handler');
    
    if ('visualViewport' in window) {
        const inputArea = document.querySelector('.input-area');
        if (!inputArea) return;
        
        let originalHeight = window.visualViewport.height;
        
        const handleResize = debounce(() => {
            const currentHeight = window.visualViewport.height;
            const heightDiff = originalHeight - currentHeight;
            
            if (heightDiff > 150) {
                inputArea.style.transform = `translateY(-${heightDiff}px)`;
                inputArea.style.transition = 'transform 0.2s ease';
            } else {
                inputArea.style.transform = 'translateY(0)';
            }
        }, 50);
        
        window.visualViewport.addEventListener('resize', handleResize);
        
        window.visualViewport.addEventListener('scroll', debounce(() => {
            const currentHeight = window.visualViewport.height;
            if (currentHeight === originalHeight) {
                inputArea.style.transform = 'translateY(0)';
            }
        }, 50));
    }
}

// ==========================================
// DEBUG & MONITORING
// ==========================================
window.crumpDebug = {
    getChats: () => AppState.chats,
    getCurrentChat: () => getChat(AppState.currentChatId),
    getProfile: () => AppState.currentProfile?.getProfile(),
    getState: () => ({ ...AppState }),
    clearStorage: () => Storage.clear(),
    version: CONFIG.APP_VERSION,
    config: CONFIG
};

// ==========================================
// CLEANUP
// ==========================================
window.addEventListener('unload', () => {
    // Clear autosave timer
    if (AppState.autosaveTimer) {
        clearInterval(AppState.autosaveTimer);
    }
    
    // Final save
    saveChats();
});

console.log(`✅ ${CONFIG.APP_NAME} v${CONFIG.APP_VERSION} loaded`);
