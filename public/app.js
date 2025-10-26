<artifact identifier="crump-app-js" type="application/vnd.ant.code" language="javascript" title="app.js - Main Application v1.0">
// ==========================================
// CRUMP AI - MAIN APPLICATION v1.0
// Complete with all fixes
// ==========================================
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
// Global State
let chats = [];
let currentChatId = null;
let currentProfile = null;
let selectedFiles = [];
let isProcessing = false;
window.chats = chats;
window.currentChatId = currentChatId;
window.STORAGE_KEYS = STORAGE_KEYS;
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

    // Initialize profile manager
    if (typeof window.ProfileManager !== 'undefined') {
        currentProfile = new ProfileManager();
        updateUserAvatar();
    } else if (typeof window.UserProfileManager !== 'undefined') {
        currentProfile = new UserProfileManager();
        updateUserAvatar();
    }

    // Initialize components
    if (typeof window.messageDeduplicator === 'undefined') {
        window.messageDeduplicator = new MessageDeduplicator();
    }

    if (typeof window.SearchDetectionEngine !== 'undefined') {
        window.searchDetectionEngine = new SearchDetectionEngine();
        console.log('✅ Search Detection Engine initialized');
    }

    loadChats();
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
const saved = localStorage.getItem(STORAGE_KEYS.CHATS);
if (saved) {
try {
chats = JSON.parse(saved);
window.chats = chats;
} catch (e) {
console.error('Failed to load chats:', e);
chats = [];
window.chats = chats;
}
}
renderChatsList();
}
function saveChats() {
localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
}
window.saveChats = saveChats;
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

saveChats();
localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, currentChatId);

renderChatsList();
renderMessages([]);

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

renderChatsList();
renderMessages(chat.messages);

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
if (!confirm('Delete ALL conversations? This cannot be undone.')) return;
chats = [];
window.chats = chats;
saveChats();
localStorage.removeItem(STORAGE_KEYS.CURRENT_CHAT);

createNewChat();
showToast('All conversations deleted', 'info');
}
window.clearAllChats = clearAllChats;
function renderChatsList() {
const chatsList = document.getElementById('chatsList');
if (!chatsList) return;
if (chats.length === 0) {
    chatsList.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--color-text-tertiary); font-size: 0.875rem;">No conversations yet</div>';
    return;
}

chatsList.innerHTML = chats.map(chat => {
    const isActive = chat.id === currentChatId;
    const time = formatTime(chat.updatedAt);
    
    return `
        <div class="chat-item ${isActive ? 'active' : ''}" onclick="loadChat('${chat.id}')">
            <div class="chat-item-content">
                <div class="chat-item-title">${escapeHtml(chat.title)}</div>
                <div class="chat-item-time">${time}</div>
            </div>
            <button class="delete-chat-btn" onclick="event.stopPropagation(); deleteChat('${chat.id}')">×</button>
        </div>
    `;
}).join('');
}
// ==========================================
// MESSAGE HANDLING
// ==========================================
async function sendMessage(messageText) {
const userInput = document.getElementById('userInput');
const message = messageText || userInput.value.trim();
if (!message && selectedFiles.length === 0) return;
if (isProcessing) return;

const chat = chats.find(c => c.id === currentChatId);
if (!chat) return;

isProcessing = true;

// User message
const userMessage = {
    role: 'user',
    content: message,
    timestamp: Date.now(),
    fileData: selectedFiles.length > 0 ? [...selectedFiles] : null
};

chat.messages.push(userMessage);
chat.updatedAt = Date.now();

// Update title from first message
if (chat.messages.length === 1) {
    chat.title = message.substring(0, 50) + (message.length > 50 ? '...' : '');
}

saveChats();
renderChatsList();
renderMessages(chat.messages);

// Clear input
userInput.value = '';
userInput.style.height = 'auto';
selectedFiles = [];
displayFilePreview();

// Show thinking
showThinking();
setAssistantState('thinking');

// Track usage
if (currentProfile) {
    currentProfile.incrementMessageUsage();
}

try {
    // Get AI response
    const response = await getAIResponse(chat.messages);

    // Assistant message
    const assistantMessage = {
        role: 'assistant',
        content: response,
        timestamp: Date.now()
    };

    chat.messages.push(assistantMessage);
    chat.updatedAt = Date.now();
    
    saveChats();
    hideThinking();
    setAssistantState('idle');
    renderMessages(chat.messages);

    // CRITICAL: Scroll to TOP of new Crump message
    setTimeout(() => {
        const messages = document.querySelectorAll('.message');
        const lastMessage = messages[messages.length - 1];
        if (lastMessage && window.crumpScrollManager) {
            window.crumpScrollManager.scrollToMessageTop(lastMessage);
        }
    }, 100);

} catch (error) {
    console.error('❌ Error getting response:', error);
    hideThinking();
    setAssistantState('idle');
    showToast('Failed to get response. Please try again.', 'error');
} finally {
    isProcessing = false;
}
}
window.sendMessage = sendMessage;
async function getAIResponse(messages) {
const workMode = localStorage.getItem(STORAGE_KEYS.WORK_MODE) === 'true';
const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        message: messages[messages.length - 1].content,
        history: messages.slice(0, -1),
        currentDateTime: {
            date: new Date().toLocaleDateString('en-US'),
            time: new Date().toLocaleTimeString('en-US'),
            timestamp: new Date().toISOString(),
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
        },
        universalMemory: buildMemoryContext(messages),
        workMode: workMode,
        needsSearch: false
    })
});

if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
}

const data = await response.json();
return data.response || 'I apologize, but I encountered an error processing your request.';
}
function buildMemoryContext(messages) {
// Build comprehensive memory from all conversations
const allMessages = chats.flatMap(chat => chat.messages);
const memory = {
    conversationCount: chats.length,
    totalMessages: allMessages.length,
    recentTopics: extractRecentTopics(messages),
    userPreferences: getUserPreferences()
};

return memory;
}
function extractRecentTopics(messages) {
// Extract key topics from recent messages
const recentMessages = messages.slice(-10);
const topics = new Set();
const keywords = ['code', 'project', 'work', 'help', 'learn', 'create', 
                 'build', 'design', 'problem', 'question'];

recentMessages.forEach(msg => {
    keywords.forEach(keyword => {
        if (msg.content.toLowerCase().includes(keyword)) {
            topics.add(keyword);
        }
    });
});

return Array.from(topics);
}
function getUserPreferences() {
return {
name: currentProfile?.profile?.name || 'User',
workMode: localStorage.getItem(STORAGE_KEYS.WORK_MODE) === 'true',
assistantName: localStorage.getItem(STORAGE_KEYS.ASSISTANT_NAME) || 'Crump'
};
}
// ==========================================
// MESSAGE RENDERING
// ==========================================
function renderMessages(messages) {
const container = document.getElementById('chatContainer');
if (!container) return;
const userInitial = localStorage.getItem(STORAGE_KEYS.USER_INITIAL) || 
                   currentProfile?.profile?.initial || 'U';

container.innerHTML = messages.map((msg, index) => {
    const isUser = msg.role === 'user';
    const avatar = isUser ? userInitial : 'C';
    
    let content = msg.content || '';
    
    if (!isUser && typeof window.processMarkdown === 'function') {
        content = window.processMarkdown(content);
    } else {
        content = escapeHtml(content);
    }

    return `
        <div class="message ${isUser ? 'user' : ''}">
            <div class="message-header">
                <div class="message-avatar ${isUser ? 'user' : 'assistant'}">${avatar}</div>
                <div class="message-sender">${isUser ? 'You' : (localStorage.getItem(STORAGE_KEYS.ASSISTANT_NAME) || 'Crump')}</div>
                <div class="message-time">${formatTime(msg.timestamp)}</div>
            </div>
            <div class="message-content">${content}</div>
        </div>
    `;
}).join('');

// Scroll to bottom initially
container.scrollTop = container.scrollHeight;
}
window.renderMessages = renderMessages;
// ==========================================
// FILE HANDLING (FIXED)
// ==========================================
function handleFileSelect(e) {
const files = Array.from(e.target.files);
files.forEach(file => {
    if (file.size > 5 * 1024 * 1024) {
        showToast(`${file.name} is too large (max 5MB)`, 'error');
        return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
        selectedFiles.push({
            name: file.name,
            type: file.type,
            size: file.size,
            data: event.target.result
        });
        displayFilePreview();
    };
    reader.readAsDataURL(file);
});

e.target.value = '';
}
function displayFilePreview() {
const preview = document.getElementById('filePreview');
// CRITICAL FIX: Check if element exists
if (!preview) {
    console.error('❌ filePreview element not found');
    return;
}

if (selectedFiles.length === 0) {
    preview.style.display = 'none';
    return;
}

preview.style.display = 'flex';
preview.innerHTML = selectedFiles.map((file, index) => {
    const isImage = file.type.startsWith('image/');
    
    return `
        <div class="file-preview-item">
            ${isImage ? `<img src="${file.data}" class="file-thumbnail" alt="${file.name}">` : '<div class="file-icon">📄</div>'}
            <div style="flex: 1; min-width: 0;">
                <div style="font-size: 0.875rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(file.name)}</div>
                <div style="font-size: 0.75rem; color: var(--color-text-tertiary);">${(file.size / 1024).toFixed(1)} KB</div>
            </div>
            <button class="remove-file" onclick="removeFile(${index})">×</button>
        </div>
    `;
}).join('');
}
window.removeFile = function(index) {
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
function loadSettings() {
const autonomousEnabled = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_ENABLED) === 'true';
const autonomousFrequency = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_FREQUENCY) || 'balanced';
if (window.autonomousMessaging) {
    window.autonomousMessaging.setEnabled(autonomousEnabled);
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

if (window.autonomousMessaging) {
    window.autonomousMessaging.setEnabled(autonomousEnabled);
    window.autonomousMessaging.setFrequency(autonomousFrequency);
}

updateAssistantNameDisplay();
updateUserAvatar();
closeSettings();
showToast('Settings saved', 'success');
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
character.className = assistant-character ${state};
}
}
window.setAssistantState = setAssistantState;
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
    content: `Hey ${userName}! I'm ${assistantName}, your AI assistant. I'm here to help with anything you need - from answering questions to helping with projects. What can I help you with today?`,
    timestamp: Date.now()
};

const chat = chats.find(c => c.id === currentChatId);
if (chat && chat.messages.length === 0) {
    chat.messages.push(welcomeMessage);
    saveChats();
    renderMessages(chat.messages);
}
}
function setupAutonomousMessaging() {
const enabled = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_ENABLED) === 'true';
const frequency = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_FREQUENCY) || 'balanced';
if (window.autonomousMessaging) {
    window.autonomousMessaging.setEnabled(enabled);
    window.autonomousMessaging.setFrequency(frequency);
}
}
function showToast(message, type = 'info') {
const container = document.getElementById('toastContainer');
if (!container) return;
const toast = document.createElement('div');
toast.className = `toast ${type}`;
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
if (diffMins < 60) return `${diffMins}m ago`;
if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;

return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
function escapeHtml(text) {
const div = document.createElement('div');
div.textContent = text;
return div.innerHTML;
}
window.escapeHtml = escapeHtml;
// ==========================================
// DEVELOPER DEBUG ACCESS
// ==========================================
window.crumpDebug = {
getChats: () => chats,
getCurrentChat: () => chats.find(c => c.id === currentChatId),
getProfile: () => currentProfile?.getProfile(),
version: '1.0.0'
};
console.log('✅ Crump AI v1.0 loaded');
</artifact>
