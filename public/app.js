/*
==========================================
CRUMP AI - MAIN APPLICATION v1.0 FIXED
Complete with all fixes
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
if (!confirm('Clear all conversations? This cannot be undone.')) return;

chats = [];
window.chats = chats;
saveChats();
createNewChat();

console.log('🗑️ All chats cleared');
showToast('All conversations cleared', 'success');
}
window.clearAllChats = clearAllChats;

function renderChatsList() {
const chatsList = document.getElementById('chatsList');
if (!chatsList) return;

if (chats.length === 0) {
    chatsList.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--color-text-tertiary);">No conversations yet</div>';
    return;
}

chatsList.innerHTML = chats.map(chat => {
    const isActive = chat.id === currentChatId;
    return `
        <div class="chat-item ${isActive ? 'active' : ''}" onclick="loadChat('${chat.id}')">
            <div style="flex: 1; min-width: 0;">
                <div class="chat-title">${escapeHtml(chat.title)}</div>
                <div class="chat-preview">${formatTime(chat.updatedAt)}</div>
            </div>
            <button class="delete-chat" onclick="event.stopPropagation(); deleteChat('${chat.id}')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"></path>
                </svg>
            </button>
        </div>
    `;
}).join('');
}

// ==========================================
// MESSAGE HANDLING
// ==========================================
function renderMessages(messages) {
const container = document.getElementById('chatContainer');
if (!container) return;

if (messages.length === 0) {
    container.innerHTML = '';
    return;
}

container.innerHTML = messages.map((msg, index) => {
    const isUser = msg.role === 'user';
    const messageId = 'msg_' + index;
    
    return `
        <div class="message ${isUser ? 'user' : 'assistant'}" id="${messageId}">
            <div class="message-avatar">
                ${isUser ? 
                    '<div class="avatar-circle">' + (currentProfile?.profile?.initial || 'U') + '</div>' :
                    '<div class="avatar-circle assistant-avatar">C</div>'
                }
            </div>
            <div class="message-content">
                ${formatMessageContent(msg.content, msg.images)}
            </div>
        </div>
    `;
}).join('');

// Scroll to bottom
setTimeout(() => {
    container.scrollTop = container.scrollHeight;
}, 100);
}

function formatMessageContent(content, images) {
let html = '';

// Add images if present
if (images && images.length > 0) {
    html += '<div class="message-images">';
    images.forEach(img => {
        html += `<img src="${img.data}" alt="${escapeHtml(img.name)}" class="message-image">`;
    });
    html += '</div>';
}

// Format text content
html += '<div class="message-text">' + formatText(content) + '</div>';

return html;
}

function formatText(text) {
// Convert markdown-like formatting
text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
text = text.replace(/`(.*?)`/g, '<code>$1</code>');
text = text.replace(/\n/g, '<br>');

return text;
}

async function sendMessage() {
const input = document.getElementById('userInput');
const message = input.value.trim();

if (!message && selectedFiles.length === 0) return;
if (isProcessing) return;

const chat = chats.find(c => c.id === currentChatId);
if (!chat) return;

isProcessing = true;
showThinking();
setAssistantState('thinking');

// Create user message
const userMessage = {
    role: 'user',
    content: message,
    timestamp: Date.now(),
    images: selectedFiles.length > 0 ? [...selectedFiles] : undefined
};

chat.messages.push(userMessage);
chat.updatedAt = Date.now();

// Update title if first message
if (chat.messages.length === 1 || chat.title === 'New Conversation') {
    chat.title = message.substring(0, 50) + (message.length > 50 ? '...' : '');
}

saveChats();
renderChatsList();
renderMessages(chat.messages);

input.value = '';
input.style.height = 'auto';
selectedFiles = [];
displayFilePreview();

try {
    const response = await getAIResponse(message, selectedFiles, chat.messages);
    
    const assistantMessage = {
        role: 'assistant',
        content: response,
        timestamp: Date.now()
    };
    
    chat.messages.push(assistantMessage);
    chat.updatedAt = Date.now();
    
    saveChats();
    renderMessages(chat.messages);
    
} catch (error) {
    console.error('Error getting AI response:', error);
    showToast('Failed to get response. Please try again.', 'error');
    
    // Remove the user message if we couldn't get a response
    chat.messages.pop();
    saveChats();
    renderMessages(chat.messages);
}

hideThinking();
setAssistantState('idle');
isProcessing = false;
}

// ==========================================
// AI RESPONSE - FIXED VERSION
// ==========================================
async function getAIResponse(message, files, conversationHistory) {
    console.log('📤 Sending message to API...');
    
    try {
        // Prepare the request body
        const requestBody = {
            message: message,
            history: conversationHistory || [],
            currentDateTime: {
                date: new Date().toLocaleDateString('en-US', { 
                    weekday: 'long', 
                    year: 'numeric', 
                    month: 'long', 
                    day: 'numeric' 
                }),
                time: new Date().toLocaleTimeString('en-US', { 
                    hour: '2-digit', 
                    minute: '2-digit', 
                    second: '2-digit',
                    hour12: true
                }),
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
            },
            fileData: files && files.length > 0 ? files : undefined,
            needsSearch: window.searchDetectionEngine?.needsSearch(message) || false,
            workMode: localStorage.getItem(STORAGE_KEYS.WORK_MODE) || 'companion'
        };

        // Check for image generation request
        if (window.shouldGenerateImage && window.shouldGenerateImage(message)) {
            console.log('🎨 Image generation requested');
            await window.handleImageGeneration(message);
            return 'Generating your image...';
        }

        // Make API call
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `API returned ${response.status}`);
        }

        const data = await response.json();
        console.log('✅ Response received from API');
        
        // Track usage
        if (currentProfile) {
            currentProfile.incrementMessageUsage();
            if (requestBody.needsSearch) {
                currentProfile.incrementSearchUsage();
            }
        }

        return data.response || 'Sorry, I received an empty response.';
        
    } catch (error) {
        console.error('❌ API Error:', error);
        
        // Provide user-friendly error messages
        if (error.message.includes('timeout')) {
            throw new Error('Request timed out. Please try a shorter message.');
        } else if (error.message.includes('too long')) {
            throw new Error('Message is too long. Please shorten it and try again.');
        } else {
            throw new Error('Failed to get response: ' + error.message);
        }
    }
}

// ==========================================
// FILE HANDLING
// ==========================================
function handleFileSelect(event) {
const files = Array.from(event.target.files);

files.forEach(file => {
    if (file.size > 10 * 1024 * 1024) {
        showToast('File too large: ' + file.name, 'error');
        return;
    }
    
    const reader = new FileReader();
    reader.onload = (e) => {
        selectedFiles.push({
            name: file.name,
            type: file.type,
            size: file.size,
            data: e.target.result
        });
        displayFilePreview();
    };
    reader.readAsDataURL(file);
});

event.target.value = '';
}

function displayFilePreview() {
const preview = document.getElementById('filePreview');
if (!preview) return;

if (selectedFiles.length === 0) {
    preview.style.display = 'none';
    return;
}

preview.style.display = 'flex';
preview.innerHTML = selectedFiles.map((file, index) => {
    const isImage = file.type.startsWith('image/');
    
    return `
        <div class="file-preview-item">
            ${isImage ? '<img src="' + file.data + '" class="file-thumbnail" alt="' + file.name + '">' : '<div class="file-icon">📄</div>'}
            <div style="flex: 1; min-width: 0;">
                <div style="font-size: 0.875rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(file.name)}</div>
                <div style="font-size: 0.75rem; color: var(--color-text-tertiary);">${(file.size / 1024).toFixed(1)} KB</div>
            </div>
            <button class="remove-file" onclick="removeFile(' + index + ')">×</button>
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
character.className = 'assistant-character ' + state;
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
    content: 'Hey ' + userName + '! I\'m ' + assistantName + ', your AI assistant. I\'m here to help with anything you need - from answering questions to helping with projects. What can I help you with today?',
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
// DEVELOPER DEBUG ACCESS
// ==========================================
window.crumpDebug = {
getChats: () => chats,
getCurrentChat: () => chats.find(c => c.id === currentChatId),
getProfile: () => currentProfile?.getProfile(),
version: '1.0.0-FIXED'
};

console.log('✅ Crump AI v1.0 loaded (FIXED VERSION - API Connected)');
