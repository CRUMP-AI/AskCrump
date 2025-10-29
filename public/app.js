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
        
        if (typeof window.WeatherDetectionEngine !== 'undefined') {
            window.weatherDetectionEngine = new WeatherDetectionEngine();
            console.log('✅ Weather Detection Engine initialized');
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
        const saved = localStorage.getItem(STORAGE_KEYS.CHATS);
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
    try {
        localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
    } catch (storageError) {
        console.warn('⚠️ Failed to save chats (localStorage unavailable)');
        // Continue without saving - app still works in-memory
    }
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
// MESSAGE RENDERING
// ==========================================
function renderMessages(messages) {
    const container = document.getElementById('chatContainer');
    if (!container) return;
    
    container.innerHTML = '';
    
    messages.forEach((msg, index) => {
        const messageEl = createMessageElement(msg, index);
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

function createMessageElement(msg, index) {
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

    // Handle generated images
if (msg.imageUrl) {
    const imgWrapper = document.createElement('div');
    imgWrapper.className = 'generated-image-wrapper';
    imgWrapper.style.cssText = 'margin-top: 0.5rem;';
    
    const img = document.createElement('img');
    img.src = msg.imageUrl;
    img.style.cssText = 'max-width: 100%; border-radius: 8px; display: block;';
    img.alt = 'Generated image';
    img.onerror = function() {
        this.parentElement.innerHTML = '<div style="color: var(--color-error);">❌ Image failed to load</div>';
    };
    
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
    
    const chat = chats.find(c => c.id === currentChatId);
    if (!chat) {
        console.error('No active chat');
        return;
    }
    
    isProcessing = true;
    
    try {
        // Create user message
        const userMessage = {
            role: 'user',
            content: message || '(attached file)',
            timestamp: Date.now()
        };
        
        // Handle file attachment
        let fileData = null;
        if (selectedFiles.length > 0) {
            const file = selectedFiles[0];
            fileData = await readFileAsBase64(file);
            userMessage.imageData = fileData;
        }
        
       // Add user message to chat
        chat.messages.push(userMessage);
        saveChats();
        renderMessages(chat.messages);
        
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
        
       // CHECK FOR IMAGE GENERATION REQUEST (must be BEFORE API call)
if (message && !fileData && window.shouldGenerateImage && window.shouldGenerateImage(message)) {
    console.log('🎨 Image generation detected, routing to image handler');
    
    // REMOVE the user message we just added (line 175) to prevent duplication
    chat.messages.pop();
    saveChats();
    
    // Hide thinking
    hideThinking();
    setAssistantState('idle');
    isProcessing = false;
    
    // Call image generation handler (it will add message itself)
    await window.handleImageGeneration(message);
    return; // EXIT - don't call chat API
}
        
        // Prepare request
        const requestBody = {
            message: message,
            history: chat.messages.map(m => ({
                role: m.role,
                content: m.content
            })),
            currentDateTime: {
                date: new Date().toLocaleDateString('en-US', { 
                    weekday: 'long', 
                    year: 'numeric', 
                    month: 'long', 
                    day: 'numeric' 
                }),
                time: new Date().toLocaleTimeString('en-US', { 
                    hour: 'numeric', 
                    minute: '2-digit',
                    hour12: true 
                }),
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
            },
            needsSearch: needsSearch,
            needsWeather: needsWeather,
            workMode: localStorage.getItem(STORAGE_KEYS.WORK_MODE) === 'true' ? 'work' : 'companion'
        };
        
        if (fileData) {
            requestBody.fileData = {
                type: selectedFiles[0].type,
                data: fileData
            };
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
        
        // Add assistant response
        const assistantMessage = {
            role: 'assistant',
            content: data.response,
            timestamp: Date.now()
        };
        
        chat.messages.push(assistantMessage);
        chat.updatedAt = Date.now();
        
        // Update chat title if first exchange
        if (chat.messages.length <= 2 && message) {
            chat.title = message.substring(0, 50) + (message.length > 50 ? '...' : '');
        }
        
        saveChats();
        renderMessages(chat.messages);
        renderChatsList();

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
    
    if (selectedFiles.length === 0) {
        preview.style.display = 'none';
        return;
    }
    
    preview.style.display = 'block';
    preview.innerHTML = selectedFiles.map((file, index) => `
        <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background: var(--color-bg-secondary); border-radius: 8px;">
            <div style="width: 40px; height: 40px; background: var(--color-accent-primary); border-radius: 6px; display: flex; align-items: center; justify-content: center; color: var(--color-bg-primary); font-weight: 600;">
                ${file.type.startsWith('image/') ? '🖼️' : '📄'}
            </div>
            <div style="flex: 1; min-width: 0;">
                <div style="font-size: 0.875rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(file.name)}</div>
                <div style="font-size: 0.75rem; color: var(--color-text-tertiary);">${(file.size / 1024).toFixed(1)} KB</div>
            </div>
            <button class="remove-file" onclick="removeFile(${index})">×</button>
        </div>
    `).join('');
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
    version: '1.0.0-FIXED'
};

console.log('✅ Crump AI v1.0 loaded (FIXED VERSION - API Connected)');
