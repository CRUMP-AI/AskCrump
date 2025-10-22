/* ============================================
   CRUMP AI - PROFESSIONAL GRADE APPLICATION
   ============================================ */

console.log('Crump AI v2.12.1 - Initializing');

// ===== STATE =====
let currentChatId = null;
let isSending = false;
let currentProfile = null;
let recognitionActive = false;

const STORAGE_KEYS = {
    CHATS: 'crump_chats',
    CURRENT_CHAT: 'crump_current_chat',
    PROFILE: 'crump_user_profile',
    USAGE: 'crump_usage',
    NOVA: 'crump_nova_protocol',
    MEMORY: 'crump_universal_memory',
    AUTONOMOUS: 'crump_autonomous_messages',
    WORK_MODE: 'crump_work_mode',
    SETTINGS: 'crump_settings',
    HAS_ONBOARDED: 'crump_has_onboarded'
};

// ===== INITIALIZATION =====
document.addEventListener('DOMContentLoaded', () => {
    const hasOnboarded = localStorage.getItem(STORAGE_KEYS.HAS_ONBOARDED);
    if (hasOnboarded) {
        initializeApp();
    }
});

window.initializeApp = function() {
    try {
        const required = ['chatContainer', 'userInput', 'sendButton', 'newChatBtn', 'chatsList', 'fileInput'];
        const missing = required.filter(id => !document.getElementById(id));
        if (missing.length > 0) {
            throw new Error(`Missing elements: ${missing.join(', ')}`);
        }

        if (typeof window.messageDeduplicator === 'undefined') {
            window.messageDeduplicator = new MessageDeduplicator();
        }

        if (typeof window.ProfileManager !== 'undefined') {
            currentProfile = new ProfileManager();
            updateUserAvatar();
        }

        loadChats();
        setupEventListeners();
        setupSidebarToggle();
        loadSettings();

        const savedChatId = localStorage.getItem(STORAGE_KEYS.CURRENT_CHAT);
        if (savedChatId && getChat(savedChatId)) {
            loadChat(savedChatId);
        } else {
            createNewChat();
        }

        setupAutonomousMessaging();
        console.log('Crump AI initialized successfully');

        if (localStorage.getItem(STORAGE_KEYS.HAS_ONBOARDED) === 'true' && !savedChatId) {
            showWelcomeMessage();
        }

    } catch (error) {
        console.error('Initialization error:', error);
        showToast('Failed to initialize application', 'error');
    }
};

// ===== SIDEBAR TOGGLE =====
function setupSidebarToggle() {
    const menuBtn = document.getElementById('menuBtn');
    const closeSidebarBtn = document.getElementById('closeSidebarBtn');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');

    if (!menuBtn || !sidebar || !overlay) return;

    menuBtn.addEventListener('click', () => {
        sidebar.classList.add('active');
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    });

    const closeSidebar = () => {
        sidebar.classList.remove('active');
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    };

    if (closeSidebarBtn) {
        closeSidebarBtn.addEventListener('click', closeSidebar);
    }

    overlay.addEventListener('click', closeSidebar);
    window.closeSidebarOnMobile = closeSidebar;
}

// ===== USER AVATAR =====
function updateUserAvatar() {
    const profile = JSON.parse(localStorage.getItem(STORAGE_KEYS.PROFILE) || '{}');
    if (profile.name) {
        window.currentUserName = profile.name;
        window.currentUserInitial = profile.avatarInitial || profile.name.charAt(0).toUpperCase();
    }
}

// ===== WELCOME MESSAGE =====
function showWelcomeMessage() {
    const profile = JSON.parse(localStorage.getItem(STORAGE_KEYS.PROFILE) || '{}');
    const userName = profile.name || 'there';
    
    const welcomeMessage = {
        role: 'assistant',
        content: `Hello ${userName}. I'm Crump, your AI virtual assistant. I'm here to help you with:

• Natural conversations and consultations
• Image generation and creative tasks
• Web research and information retrieval
• Code development and debugging
• Document analysis and writing
• Learning and problem-solving

How may I assist you today?`,
        timestamp: Date.now()
    };

    const currentChat = getCurrentChat();
    if (currentChat && currentChat.messages.length === 0) {
        currentChat.messages.push(welcomeMessage);
        saveChats();
        renderMessage(welcomeMessage);
    }
}

// ===== EVENT LISTENERS =====
function setupEventListeners() {
    const sendButton = document.getElementById('sendButton');
    const userInput = document.getElementById('userInput');

    sendButton.addEventListener('click', () => sendMessage());
    
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = userInput.scrollHeight + 'px';
    });

    document.getElementById('newChatBtn').addEventListener('click', createNewChat);

    const settingsBtn = document.getElementById('settingsBtn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', openSettings);
    }

    const tierBadge = document.getElementById('tierBadge');
    const headerTierBadge = document.getElementById('headerTierBadge');
    
    if (tierBadge) {
        tierBadge.addEventListener('click', () => {
            if (typeof showUpgradeModal === 'function') {
                showUpgradeModal();
            }
        });
    }
    
    if (headerTierBadge) {
        headerTierBadge.addEventListener('click', () => {
            if (typeof showUpgradeModal === 'function') {
                showUpgradeModal();
            }
        });
    }

    const attachBtn = document.getElementById('attachBtn');
    const fileInput = document.getElementById('fileInput');
    
    if (attachBtn && fileInput) {
        attachBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileSelect);
    }

    const voiceBtn = document.getElementById('voiceBtn');
    if (voiceBtn) {
        voiceBtn.addEventListener('click', toggleVoiceRecognition);
    }
}

// ===== VOICE RECOGNITION =====
function toggleVoiceRecognition() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        showToast('Voice recognition not supported', 'error');
        return;
    }

    if (recognitionActive) {
        if (window.recognition) {
            window.recognition.stop();
        }
        recognitionActive = false;
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
        recognitionActive = true;
        showToast('Listening...', 'info');
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        document.getElementById('userInput').value = transcript;
        showToast('Voice input captured', 'success');
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        showToast('Voice recognition error', 'error');
        recognitionActive = false;
    };

    recognition.onend = () => {
        recognitionActive = false;
    };

    window.recognition = recognition;
    recognition.start();
}

// ===== FILE HANDLING =====
let selectedFiles = [];

function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    selectedFiles = [...selectedFiles, ...files];
    displayFilePreview();
}

function displayFilePreview() {
    const preview = document.getElementById('filePreview');
    
    if (selectedFiles.length === 0) {
        preview.style.display = 'none';
        return;
    }

    preview.style.display = 'flex';
    preview.innerHTML = selectedFiles.map((file, index) => `
        <div class="file-preview-item">
            <span>${escapeHtml(file.name)}</span>
            <button class="remove-file" onclick="removeFile(${index})">×</button>
        </div>
    `).join('');
}

window.removeFile = function(index) {
    selectedFiles.splice(index, 1);
    displayFilePreview();
};

// ===== QUICK ACTIONS =====
window.triggerImageGeneration = function() {
    document.getElementById('userInput').value = 'Generate an image of ';
    document.getElementById('userInput').focus();
    const input = document.getElementById('userInput');
    input.setSelectionRange(input.value.length, input.value.length);
};

window.triggerWebSearch = function() {
    document.getElementById('userInput').value = 'Search the web for ';
    document.getElementById('userInput').focus();
    const input = document.getElementById('userInput');
    input.setSelectionRange(input.value.length, input.value.length);
};

window.triggerCodeHelp = function() {
    document.getElementById('userInput').value = 'Help me with this code:\n\n';
    document.getElementById('userInput').focus();
    const input = document.getElementById('userInput');
    input.setSelectionRange(input.value.length, input.value.length);
};

// ===== CHAT MANAGEMENT =====
function createNewChat() {
    const chatId = Date.now().toString();
    const newChat = {
        id: chatId,
        title: 'New Conversation',
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now()
    };

    const chats = getChats();
    chats.unshift(newChat);
    localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));

    loadChat(chatId);
}

function loadChat(chatId) {
    const chat = getChat(chatId);
    if (!chat) return;

    currentChatId = chatId;
    localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, chatId);

    const container = document.getElementById('chatContainer');
    container.innerHTML = '';
    
    chat.messages.forEach(msg => renderMessage(msg));
    
    updateChatsList();
    scrollToBottom();

    if (window.innerWidth <= 768 && typeof window.closeSidebarOnMobile === 'function') {
        window.closeSidebarOnMobile();
    }
}

function loadChats() {
    updateChatsList();
}

function updateChatsList() {
    const chats = getChats();
    const chatsList = document.getElementById('chatsList');
    
    if (chats.length === 0) {
        chatsList.innerHTML = '<div style="text-align: center; color: var(--color-text-muted); padding: 2rem; font-size: 0.875rem;">No conversations yet</div>';
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

window.deleteChat = function(chatId) {
    if (!confirm('Delete this conversation?')) return;

    const chats = getChats();
    const filtered = chats.filter(c => c.id !== chatId);
    localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(filtered));

    if (chatId === currentChatId) {
        if (filtered.length > 0) {
            loadChat(filtered[0].id);
        } else {
            createNewChat();
        }
    } else {
        updateChatsList();
    }
};

// ===== MESSAGE SENDING =====
async function sendMessage(messageOverride = null) {
    const userInput = document.getElementById('userInput');
    const message = messageOverride || userInput.value.trim();

    if (!message && selectedFiles.length === 0) return;
    if (isSending) return;

    if (window.messageDeduplicator && !messageOverride) {
        if (window.messageDeduplicator.isDuplicate(message)) {
            showToast('Message already sent', 'warning');
            return;
        }
        window.messageDeduplicator.addMessage(message);
    }

    if (currentProfile) {
        const canSend = currentProfile.canSendMessage();
        if (!canSend.allowed) {
            showToast(canSend.reason, 'error');
            if (typeof showUpgradeModal === 'function') {
                setTimeout(() => showUpgradeModal(), 1000);
            }
            return;
        }
    }

    isSending = true;
    const sendButton = document.getElementById('sendButton');
    sendButton.disabled = true;

    try {
        const userMessage = {
            role: 'user',
            content: message,
            timestamp: Date.now(),
            files: selectedFiles.length > 0 ? selectedFiles.map(f => f.name) : undefined
        };

        const currentChat = getCurrentChat();
        currentChat.messages.push(userMessage);
        currentChat.updatedAt = Date.now();
        
        if (currentChat.messages.filter(m => m.role === 'user').length === 1) {
            currentChat.title = message.substring(0, 50) + (message.length > 50 ? '...' : '');
        }
        
        saveChats();
        renderMessage(userMessage);

        userInput.value = '';
        userInput.style.height = 'auto';
        selectedFiles = [];
        displayFilePreview();

        showThinking();

        const requestData = {
            message: message,
            history: currentChat.messages.slice(-10),
            fileData: selectedFiles.length > 0 ? selectedFiles : undefined,
            needsSearch: message.toLowerCase().includes('search') || message.toLowerCase().includes('latest'),
            universalMemory: JSON.parse(localStorage.getItem(STORAGE_KEYS.MEMORY) || '{}'),
            workMode: localStorage.getItem(STORAGE_KEYS.WORK_MODE) || 'companion'
        };

        const novaActive = localStorage.getItem(STORAGE_KEYS.NOVA);
        if (novaActive) {
            requestData.novaActive = true;
            requestData.novaProtocol = JSON.parse(novaActive);
        }

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const data = await response.json();

        hideThinking();

        const assistantMessage = {
            role: 'assistant',
            content: data.response,
            timestamp: Date.now(),
            model: data.model
        };

        currentChat.messages.push(assistantMessage);
        currentChat.updatedAt = Date.now();
        saveChats();
        renderMessage(assistantMessage);

        if (currentProfile) {
            currentProfile.incrementUsage('messages');
            if (data.imageCount) {
                currentProfile.incrementUsage('images', data.imageCount);
            }
            updateTierBadge();
        }

        updateChatsList();

    } catch (error) {
        console.error('Send error:', error);
        hideThinking();
        showToast('Failed to send message', 'error');
    } finally {
        isSending = false;
        sendButton.disabled = false;
        scrollToBottom();
    }
}

// ===== MESSAGE RENDERING =====
function renderMessage(message) {
    const container = document.getElementById('chatContainer');
    const messageEl = document.createElement('div');
    messageEl.className = `message ${message.role}`;

    const profile = JSON.parse(localStorage.getItem(STORAGE_KEYS.PROFILE) || '{}');
    const userInitial = profile.avatarInitial || profile.name?.charAt(0).toUpperCase() || 'U';
    
    const avatar = message.role === 'user' ? userInitial : 'AI';
    const sender = message.role === 'user' ? (profile.name || 'You') : 'Crump';
    const time = formatTime(message.timestamp);

    messageEl.innerHTML = `
        <div class="message-header">
            <div class="message-avatar">${escapeHtml(avatar)}</div>
            <div>
                <div class="message-sender">${escapeHtml(sender)}</div>
                <div class="message-time">${time}</div>
            </div>
        </div>
        <div class="message-content">
            ${formatMessageContent(message.content)}
        </div>
    `;

    container.appendChild(messageEl);
    
    if (window.Prism) {
        Prism.highlightAllUnder(messageEl);
    }
    
    scrollToBottom();
}

function formatMessageContent(content) {
    let formatted = escapeHtml(content);
    
    formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/\*(.+?)\*/g, '<em>$1</em>');
    formatted = formatted.replace(/```(\w+)?\n([\s\S]+?)```/g, (match, lang, code) => {
        const language = lang || 'plaintext';
        return `<pre><code class="language-${language}">${code.trim()}</code></pre>`;
    });
    formatted = formatted.replace(/`(.+?)`/g, '<code>$1</code>');
    formatted = formatted.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank">$1</a>');
    formatted = formatted.replace(/\n/g, '<br>');
    
    return formatted;
}

// ===== THINKING INDICATOR =====
function showThinking() {
    const indicator = document.getElementById('thinkingIndicator');
    if (indicator) {
        indicator.style.display = 'flex';
        scrollToBottom();
    }
}

function hideThinking() {
    const indicator = document.getElementById('thinkingIndicator');
    if (indicator) {
        indicator.style.display = 'none';
    }
}

// ===== SETTINGS =====
function openSettings() {
    const modal = document.getElementById('settingsModal');
    const profile = currentProfile ? currentProfile.getProfile() : {};
    
    document.getElementById('settingsName').value = profile.name || '';
    document.getElementById('settingsEmail').value = profile.email || '';
    document.getElementById('autonomousMessaging').checked = 
        localStorage.getItem(STORAGE_KEYS.AUTONOMOUS) === 'true';
    document.getElementById('workMode').checked = 
        localStorage.getItem(STORAGE_KEYS.WORK_MODE) === 'work';
    
    if (currentProfile) {
        const stats = currentProfile.getUsageStats();
        document.getElementById('usageStats').innerHTML = `
            <p>Messages: ${stats.messages}/${stats.limits.messages === -1 ? '∞' : stats.limits.messages}</p>
            <p>Images: ${stats.images}/${stats.limits.images === -1 ? '∞' : stats.limits.images}</p>
            <p>Searches: ${stats.searches}/${stats.limits.searches === -1 ? '∞' : stats.limits.searches}</p>
            <p>Resets: ${new Date(stats.resetDate).toLocaleDateString()}</p>
        `;
    }
    
    modal.style.display = 'flex';
}

window.closeSettings = function() {
    document.getElementById('settingsModal').style.display = 'none';
};

window.saveSettings = function() {
    const name = document.getElementById('settingsName').value.trim();
    const email = document.getElementById('settingsEmail').value.trim();
    const autonomous = document.getElementById('autonomousMessaging').checked;
    const workMode = document.getElementById('workMode').checked;
    
    if (currentProfile && name) {
        currentProfile.updateProfile({ name, email });
        updateUserAvatar();
    }
    
    localStorage.setItem(STORAGE_KEYS.AUTONOMOUS, autonomous);
    localStorage.setItem(STORAGE_KEYS.WORK_MODE, workMode ? 'work' : 'companion');
    
    window.closeSettings();
    showToast('Settings saved', 'success');
    updateChatsList();
};

function loadSettings() {
    // Settings loaded in openSettings()
}

// ===== TIER BADGE =====
function updateTierBadge() {
    if (!currentProfile) return;
    
    const profile = currentProfile.getProfile();
    const tierName = profile.tier.charAt(0).toUpperCase() + profile.tier.slice(1);
    
    const sidebarTier = document.getElementById('tierName');
    const headerTier = document.getElementById('headerTierName');
    
    if (sidebarTier) sidebarTier.textContent = tierName;
    if (headerTier) headerTier.textContent = tierName;
}

// ===== AUTONOMOUS MESSAGING =====
let autonomousInterval;

function setupAutonomousMessaging() {
    const enabled = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS) === 'true';
    
    if (autonomousInterval) {
        clearInterval(autonomousInterval);
    }
    
    if (enabled) {
        autonomousInterval = setInterval(sendAutonomousMessage, 15 * 60 * 1000);
    }
}

function sendAutonomousMessage() {
    const currentChat = getCurrentChat();
    if (!currentChat) return;
    
    const lastMessage = currentChat.messages[currentChat.messages.length - 1];
    if (!lastMessage) return;
    
    const timeSinceLastMessage = Date.now() - lastMessage.timestamp;
    if (timeSinceLastMessage < 10 * 60 * 1000) return;
    
    const messages = [
        "Is there anything I can assist you with?",
        "I'm here if you need help with anything.",
        "Do you have any questions I can help answer?",
        "Ready to assist whenever you need."
    ];
    
    const randomMessage = messages[Math.floor(Math.random() * messages.length)];
    sendMessage(randomMessage);
}

// ===== UTILITY FUNCTIONS =====
function getChats() {
    return JSON.parse(localStorage.getItem(STORAGE_KEYS.CHATS) || '[]');
}

function getChat(chatId) {
    return getChats().find(c => c.id === chatId);
}

function getCurrentChat() {
    return getChat(currentChatId);
}

function saveChats() {
    const chats = getChats();
    localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
}

function scrollToBottom() {
    const container = document.getElementById('chatContainer');
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 100);
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    
    if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    }
    
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'toastSlide 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ===== DEBUG =====
window.crumpDebug = {
    getCurrentChat,
    getChats,
    currentProfile,
    sendMessage,
    createNewChat,
    loadChat
};
