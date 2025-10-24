/* ============================================
   CRUMP AI v3.0 - PRODUCTION GRADE
   ============================================ */

console.log('Crump AI v3.0 - Initializing');

let currentChatId = null;
let isSending = false;
let currentProfile = null;
let recognitionActive = false;
let chatsArray = [];

const STORAGE_KEYS = {
    CHATS: 'crump_chats',
    CURRENT_CHAT: 'crump_current_chat',
    PROFILE: 'crump_user_profile',
    USAGE: 'crump_usage',
    NOVA: 'crump_nova_protocol',
    MEMORY: 'crump_universal_memory',
    AUTONOMOUS: 'crump_autonomous_messages',
    AUTONOMOUS_FREQUENCY: 'crump_autonomous_frequency',
    ASSISTANT_NAME: 'crump_assistant_name',
    WORK_MODE: 'crump_work_mode',
    SETTINGS: 'crump_settings',
    HAS_ONBOARDED: 'crump_has_onboarded'
};

// ==========================================
// FILE UPLOAD CONFIGURATION
// ==========================================
const FILE_CONFIG = {
    MAX_SIZE: 5 * 1024 * 1024, // 5MB
    MAX_FILES: 10,
    ALLOWED_TYPES: {
        images: ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'],
        documents: ['application/pdf', 'text/plain', 'text/csv'],
        office: ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    },
    IMAGE_COMPRESSION: {
        maxWidth: 1920,
        maxHeight: 1920,
        quality: 0.85
    }
};

// ==========================================
// ASSISTANT CHARACTER STATE MANAGEMENT
// ==========================================
function setAssistantState(state) {
    const assistant = document.getElementById('assistantCharacter');
    if (!assistant) return;
    
    assistant.classList.remove('idle', 'thinking', 'speaking', 'intro', 'docking');
    assistant.classList.add(state);
    
    console.log('🤖 Assistant state:', state);
}

function initializeAssistant() {
    const assistant = document.getElementById('assistantCharacter');
    if (!assistant) return;
    
    assistant.classList.add('intro');
    
    setTimeout(() => {
        assistant.classList.remove('intro');
        assistant.classList.add('docking');
        
        setTimeout(() => {
            assistant.classList.remove('docking');
            setAssistantState('idle');
        }, 1000);
    }, 1500);
}

window.setAssistantState = setAssistantState;

// ==========================================
// APP INITIALIZATION
// ==========================================
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
            throw new Error('Missing elements: ' + missing.join(', '));
        }

        if (typeof window.messageDeduplicator === 'undefined') {
            window.messageDeduplicator = new MessageDeduplicator();
        }

        // Initialize search detection engine
        if (typeof window.SearchDetectionEngine !== 'undefined') {
            window.searchDetectionEngine = new SearchDetectionEngine();
            console.log('✅ Search Detection Engine initialized');
        }

        if (typeof window.ProfileManager !== 'undefined') {
            currentProfile = new ProfileManager();
            updateUserAvatar();
        } else if (typeof window.UserProfileManager !== 'undefined') {
            currentProfile = new UserProfileManager();
            updateUserAvatar();
        }

        loadChats();
        setupEventListeners();
        setupSidebarToggle();
        loadSettings();
        updateAssistantNameDisplay();
        initializeAssistant();

        const savedChatId = localStorage.getItem(STORAGE_KEYS.CURRENT_CHAT);
        if (savedChatId && getChat(savedChatId)) {
            loadChat(savedChatId);
        } else {
            createNewChat();
        }

        setupAutonomousMessaging();
        console.log('✅ Crump AI v3.0 initialized successfully');

        if (localStorage.getItem(STORAGE_KEYS.HAS_ONBOARDED) === 'true' && !savedChatId) {
            showWelcomeMessage();
        }

    } catch (error) {
        console.error('❌ Initialization error:', error);
        showToast('Failed to initialize application', 'error');
    }
};

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

function updateUserAvatar() {
    const profile = JSON.parse(localStorage.getItem(STORAGE_KEYS.PROFILE) || '{}');
    if (profile.name) {
        window.currentUserName = profile.name;
        window.currentUserInitial = profile.avatarInitial || profile.name.charAt(0).toUpperCase();
    }
}

function getAssistantName() {
    return localStorage.getItem(STORAGE_KEYS.ASSISTANT_NAME) || 'Crump';
}

function updateAssistantNameDisplay() {
    const assistantName = getAssistantName();
    
    const sidebarLogo = document.querySelector('.sidebar-logo');
    if (sidebarLogo) sidebarLogo.textContent = assistantName;
    
    const headerLogo = document.querySelector('.header-logo');
    if (headerLogo) headerLogo.textContent = assistantName;
    
    const splashLogo = document.querySelector('.splash-logo');
    if (splashLogo) splashLogo.textContent = assistantName;
}

function showWelcomeMessage() {
    const profile = JSON.parse(localStorage.getItem(STORAGE_KEYS.PROFILE) || '{}');
    const userName = profile.name || 'there';
    const assistantName = getAssistantName();
    
    const welcomeMessage = {
        role: 'assistant',
        content: 'Hello ' + userName + '. I\'m ' + assistantName + ', your AI virtual assistant. I\'m here to help you with:\n\n• Natural conversations and consultations\n• Image generation and creative tasks\n• Web research and information retrieval\n• Code development and debugging\n• Document analysis and writing\n• Learning and problem-solving\n\nHow may I assist you today?',
        timestamp: Date.now()
    };

    const currentChat = getCurrentChat();
    if (currentChat && currentChat.messages.length === 0) {
        currentChat.messages.push(welcomeMessage);
        saveChats();
        renderMessage(welcomeMessage);
    }
}

// ==========================================
// EVENT LISTENERS
// ==========================================
function setupEventListeners() {
    const sendButton = document.getElementById('sendButton');
    const userInput = document.getElementById('userInput');

    sendButton.addEventListener('click', () => sendMessage());
    
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.shiftKey) {
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
            } else if (typeof showUpgradePrompt === 'function') {
                showUpgradePrompt();
            }
        });
    }
    
    if (headerTierBadge) {
        headerTierBadge.addEventListener('click', () => {
            if (typeof showUpgradeModal === 'function') {
                showUpgradeModal();
            } else if (typeof showUpgradePrompt === 'function') {
                showUpgradePrompt();
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

    const autonomousCheck = document.getElementById('autonomousMessaging');
    if (autonomousCheck) {
        autonomousCheck.addEventListener('change', (e) => {
            const frequencyGroup = document.getElementById('autonomousFrequencyGroup');
            if (frequencyGroup) {
                frequencyGroup.style.display = e.target.checked ? 'block' : 'none';
            }
        });
    }
}

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

// ==========================================
// FILE HANDLING (ENHANCED WITH VALIDATION & COMPRESSION)
// ==========================================
let selectedFiles = [];

async function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    
    // Validate file count
    if (selectedFiles.length + files.length > FILE_CONFIG.MAX_FILES) {
        showToast(`Maximum ${FILE_CONFIG.MAX_FILES} files allowed`, 'error');
        return;
    }
    
    // Validate and process each file
    for (const file of files) {
        try {
            // Check file size
            if (file.size > FILE_CONFIG.MAX_SIZE) {
                showToast(`${file.name} is too large (max 5MB)`, 'error');
                continue;
            }
            
            // Check file type
            const isAllowed = Object.values(FILE_CONFIG.ALLOWED_TYPES).flat().includes(file.type);
            if (!isAllowed) {
                showToast(`${file.name} file type not supported`, 'error');
                continue;
            }
            
            // Compress images if needed
            if (file.type.startsWith('image/')) {
                const compressed = await compressImage(file);
                selectedFiles.push(compressed);
            } else {
                selectedFiles.push(file);
            }
            
        } catch (error) {
            console.error('Error processing file:', file.name, error);
            showToast(`Failed to process ${file.name}`, 'error');
        }
    }
    
    displayFilePreview();
    event.target.value = ''; // Reset input
}

async function compressImage(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        
        reader.onload = (e) => {
            const img = new Image();
            
            img.onload = () => {
                const canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;
                
                // Calculate new dimensions
                if (width > FILE_CONFIG.IMAGE_COMPRESSION.maxWidth || height > FILE_CONFIG.IMAGE_COMPRESSION.maxHeight) {
                    if (width > height) {
                        height = Math.round(height * FILE_CONFIG.IMAGE_COMPRESSION.maxWidth / width);
                        width = FILE_CONFIG.IMAGE_COMPRESSION.maxWidth;
                    } else {
                        width = Math.round(width * FILE_CONFIG.IMAGE_COMPRESSION.maxHeight / height);
                        height = FILE_CONFIG.IMAGE_COMPRESSION.maxHeight;
                    }
                }
                
                canvas.width = width;
                canvas.height = height;
                
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);
                
                // Convert to blob
                canvas.toBlob((blob) => {
                    if (blob) {
                        // Create new file with compressed data
                        const compressedFile = new File([blob], file.name, {
                            type: file.type,
                            lastModified: Date.now()
                        });
                        
                        console.log(`📦 Compressed ${file.name}: ${(file.size / 1024).toFixed(1)}KB → ${(compressedFile.size / 1024).toFixed(1)}KB`);
                        resolve(compressedFile);
                    } else {
                        reject(new Error('Compression failed'));
                    }
                }, file.type, FILE_CONFIG.IMAGE_COMPRESSION.quality);
            };
            
            img.onerror = () => reject(new Error('Image load failed'));
            img.src = e.target.result;
        };
        
        reader.onerror = () => reject(new Error('File read failed'));
        reader.readAsDataURL(file);
    });
}

function displayFilePreview() {
    const preview = document.getElementById('filePreview');
    
    if (selectedFiles.length === 0) {
        preview.style.display = 'none';
        return;
    }

    preview.style.display = 'flex';
    preview.innerHTML = selectedFiles.map((file, index) => {
        let previewContent = '';
        
        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const thumb = document.querySelector(`[data-file-index="${index}"] .file-thumbnail`);
                if (thumb) {
                    thumb.innerHTML = '<img src="' + e.target.result + '" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px;">';
                }
            };
            reader.readAsDataURL(file);
            previewContent = '<div class="file-thumbnail" data-file-index="' + index + '">📷</div>';
        } else {
            previewContent = '<div class="file-icon">📄</div>';
        }
        
        const sizeKB = (file.size / 1024).toFixed(1);
        
        return '<div class="file-preview-item" data-file-index="' + index + '">' + 
               previewContent +
               '<div style="flex: 1;"><span style="display: block;">' + escapeHtml(file.name) + '</span><span style="font-size: 11px; color: var(--color-text-tertiary);">' + sizeKB + ' KB</span></div>' +
               '<button class="remove-file" onclick="removeFile(' + index + ')">×</button>' +
               '</div>';
    }).join('');
}

window.removeFile = function(index) {
    selectedFiles.splice(index, 1);
    displayFilePreview();
};

// ==========================================
// QUICK ACTIONS
// ==========================================
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

// ==========================================
// CHAT MANAGEMENT
// ==========================================
function createNewChat() {
    const chatId = Date.now().toString();
    const newChat = {
        id: chatId,
        title: 'New Conversation',
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now()
    };

    chatsArray.unshift(newChat);
    saveChats();

    if (window.resetImageGenerationState) {
        window.resetImageGenerationState();
    }

    loadChat(chatId);
}

function loadChat(chatId) {
    const chat = getChat(chatId);
    if (!chat) return;

    currentChatId = chatId;
    localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, chatId);

    if (window.resetImageGenerationState) {
        window.resetImageGenerationState();
    }

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
    chatsArray = JSON.parse(localStorage.getItem(STORAGE_KEYS.CHATS) || '[]');
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
        
        return '<div class="chat-item ' + (isActive ? 'active' : '') + '" onclick="loadChat(\'' + chat.id + '\')"><div class="chat-item-content"><div class="chat-item-title">' + escapeHtml(chat.title) + '</div><div class="chat-item-time">' + time + '</div></div><button class="delete-chat-btn" onclick="event.stopPropagation(); deleteChat(\'' + chat.id + '\')">×</button></div>';
    }).join('');
}

window.deleteChat = function(chatId) {
    if (!confirm('Delete this conversation?')) return;

    chatsArray = chatsArray.filter(c => c.id !== chatId);
    saveChats();

    if (chatId === currentChatId) {
        if (chatsArray.length > 0) {
            loadChat(chatsArray[0].id);
        } else {
            createNewChat();
        }
    } else {
        updateChatsList();
    }
};

window.clearAllChats = function() {
    if (!confirm('Are you sure you want to delete ALL conversations? This cannot be undone.')) return;
    
    chatsArray = [];
    saveChats();
    createNewChat();
    showToast('All conversations cleared', 'success');
};

// ==========================================
// SEND MESSAGE (FIXED EXECUTION ORDER + SMART SEARCH)
// ==========================================
async function sendMessage(messageOverride) {
    const userInput = document.getElementById('userInput');
    const message = messageOverride || userInput.value.trim();

    if (!message && selectedFiles.length === 0) return;
    if (isSending) return;

    // CRITICAL FIX #1: CHECK FILES FIRST, BEFORE IMAGE GENERATION
    const hasFiles = selectedFiles.length > 0;
    
    // CRITICAL FIX #2: Only check image generation if NO files attached
    if (!hasFiles && window.shouldGenerateImage && window.shouldGenerateImage(message)) {
        console.log('🎨 Image generation request detected');
        if (window.handleImageGeneration) {
            userInput.value = '';
            userInput.style.height = 'auto';
            setAssistantState('thinking');
            await window.handleImageGeneration(message);
            setAssistantState('idle');
        } else {
            console.error('❌ handleImageGeneration not found');
            showToast('Image generation not available', 'error');
        }
        return;
    }

    // Check for duplicate messages
    if (window.messageDeduplicator && !messageOverride) {
        if (window.messageDeduplicator.isDuplicate(message)) {
            showToast('Message already sent', 'warning');
            return;
        }
    }

    // Check usage limits
    if (currentProfile) {
        const canSend = currentProfile.canSendMessage();
        if (!canSend.allowed) {
            showToast(canSend.message || canSend.reason, 'error');
            if (typeof showUpgradeModal === 'function') {
                setTimeout(() => showUpgradeModal(), 1000);
            } else if (typeof showUpgradePrompt === 'function') {
                setTimeout(() => showUpgradePrompt(), 1000);
            }
            return;
        }
    }

    isSending = true;
    const sendButton = document.getElementById('sendButton');
    sendButton.disabled = true;

    try {
        const filesToProcess = [...selectedFiles];
        
        const userMessage = {
            role: 'user',
            content: message,
            timestamp: Date.now(),
            files: filesToProcess.length > 0 ? filesToProcess.map(f => f.name) : undefined
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

        setAssistantState('thinking');
        showThinking();

        // Get current date and time
        const now = new Date();
        const currentDateTime = {
            date: now.toLocaleDateString('en-US', { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
            }),
            time: now.toLocaleTimeString('en-US', { 
                hour: 'numeric', 
                minute: '2-digit',
                hour12: true 
            }),
            timestamp: now.toISOString(),
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
        };

        // CRITICAL FIX #3: Smart search detection
        let needsSearch = false;
        if (window.searchDetectionEngine) {
            needsSearch = window.searchDetectionEngine.shouldSearch(message);
            console.log('🔍 Search detection:', needsSearch ? 'YES' : 'NO');
        } else {
            // Fallback to basic detection
            needsSearch = message.toLowerCase().includes('search') || 
                         message.toLowerCase().includes('latest');
        }

        const requestData = {
            message: message,
            history: currentChat.messages.slice(-10),
            currentDateTime: currentDateTime,
            fileData: filesToProcess.length > 0 ? await processFilesForUpload(filesToProcess) : undefined,
            needsSearch: needsSearch,
            universalMemory: JSON.parse(localStorage.getItem(STORAGE_KEYS.MEMORY) || '{}'),
            workMode: localStorage.getItem(STORAGE_KEYS.WORK_MODE) || 'companion'
        };

        const novaActive = localStorage.getItem(STORAGE_KEYS.NOVA);
        if (novaActive) {
            requestData.novaActive = true;
            requestData.novaProtocol = JSON.parse(novaActive);
        }

        console.log('📤 Sending request to API...');
        console.log('📅 Current date/time:', currentDateTime.date, currentDateTime.time);
        if (needsSearch) console.log('🔍 Search enabled for this query');
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 60000);
        
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData),
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        console.log('📥 Response received:', response.status);

        if (!response.ok) {
            const errorText = await response.text();
            console.error('❌ API Error:', errorText);
            throw new Error('API returned ' + response.status);
        }

        const data = await response.json();
        console.log('✅ Response parsed successfully');

        hideThinking();
        setAssistantState('speaking');

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

        setTimeout(() => setAssistantState('idle'), 2000);

        // CRITICAL FIX #4: Fixed usage tracking method names
        if (currentProfile) {
            if (currentProfile.incrementMessageUsage) {
                currentProfile.incrementMessageUsage();
            } else if (currentProfile.incrementUsage) {
                currentProfile.incrementUsage('messages');
            }
            
            // Track image generation if it happened
            if (data.imageCount) {
                if (currentProfile.incrementImageUsage) {
                    for (let i = 0; i < data.imageCount; i++) {
                        currentProfile.incrementImageUsage();
                    }
                } else if (currentProfile.incrementUsage) {
                    currentProfile.incrementUsage('images', data.imageCount);
                }
            }
            
            // Track web search if it happened
            if (needsSearch || data.usedSearch) {
                if (currentProfile.incrementSearchUsage) {
                    currentProfile.incrementSearchUsage();
                } else if (currentProfile.incrementUsage) {
                    currentProfile.incrementUsage('searches');
                }
            }
            
            updateTierBadge();
        }

        updateChatsList();
        
        // Clear files after successful send
        selectedFiles = [];
        displayFilePreview();

    } catch (error) {
        console.error('❌ Send error:', error);
        
        hideThinking();
        setAssistantState('idle');
        
        let errorMessage = 'Failed to send message';
        
        if (error.name === 'AbortError') {
            errorMessage = 'Request timed out - please try again';
        } else if (error.message.includes('NetworkError') || error.message.includes('Failed to fetch')) {
            errorMessage = 'Network error - check your connection';
        } else if (error.message.includes('API returned')) {
            errorMessage = error.message;
        } else {
            errorMessage = 'Error: ' + error.message;
        }
        
        showToast(errorMessage, 'error');
    } finally {
        isSending = false;
        sendButton.disabled = false;
        scrollToBottom();
    }
}

// ==========================================
// MESSAGE RENDERING (ENHANCED)
// ==========================================
function renderMessage(message) {
    const container = document.getElementById('chatContainer');
    const messageEl = document.createElement('div');
    messageEl.className = 'message ' + message.role;

    const profile = JSON.parse(localStorage.getItem(STORAGE_KEYS.PROFILE) || '{}');
    const userInitial = profile.avatarInitial || (profile.name && profile.name.charAt(0).toUpperCase()) || 'U';
    const assistantName = getAssistantName();
    
    const avatar = message.role === 'user' ? userInitial : 'AI';
    const sender = message.role === 'user' ? (profile.name || 'You') : assistantName;
    const time = formatTime(message.timestamp);

    let contentHtml = '<div class="message-content">' + formatMessageContent(message.content) + '</div>';
    
    // Show uploaded files in user messages
    if (message.role === 'user' && message.files && message.files.length > 0) {
        contentHtml += '<div class="uploaded-files">';
        message.files.forEach(fileName => {
            contentHtml += '<div class="file-badge">📎 ' + escapeHtml(fileName) + '</div>';
        });
        contentHtml += '</div>';
    }
    
    // Show generated images
    if (message.imageUrl) {
        contentHtml += '<div class="generated-image-container"><img src="' + message.imageUrl + '" class="generated-image" onclick="enlargeImage(this)" alt="Generated image" onerror="this.parentElement.innerHTML=\'<p style=color:var(--color-text-tertiary);>Failed to load image</p>\'"></div>';
    }

    messageEl.innerHTML = '<div class="message-header"><div class="message-avatar">' + escapeHtml(avatar) + '</div><div><div class="message-sender">' + escapeHtml(sender) + '</div><div class="message-time">' + time + '</div></div></div>' + contentHtml;

    container.appendChild(messageEl);
    
    if (window.Prism) {
        Prism.highlightAllUnder(messageEl);
    }
    
    scrollToBottom();
}

function formatMessageContent(content) {
    let formatted = escapeHtml(content);
    
    // Handle image markdown
    formatted = formatted.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, function(match, alt, url) {
        return `<div class="message-image"><img src="${url}" alt="${alt}" onclick="enlargeImage(this)" style="max-width: 100%; border-radius: 8px; margin: 1rem 0; cursor: pointer;" onerror="this.parentElement.innerHTML='<p style=\\'color: var(--color-text-tertiary);\\'>Failed to load image</p>'"></div>`;
    });
    
    formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/\*(.+?)\*/g, '<em>$1</em>');
    formatted = formatted.replace(/```(\w+)?\n([\s\S]+?)```/g, function(match, lang, code) {
        const language = lang || 'plaintext';
        return '<pre><code class="language-' + language + '">' + code.trim() + '</code></pre>';
    });
    formatted = formatted.replace(/`(.+?)`/g, '<code>$1</code>');
    formatted = formatted.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank">$1</a>');
    formatted = formatted.replace(/\n/g, '<br>');
    
    return formatted;
}

// ==========================================
// IMAGE ENLARGE
// ==========================================
window.enlargeImage = function(img) {
    const overlay = document.createElement('div');
    overlay.className = 'image-overlay';
    overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.9); z-index: 9998; cursor: pointer;';
    
    const enlargedImg = img.cloneNode(true);
    enlargedImg.style.cssText = 'position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); max-width: 90vw; max-height: 90vh; z-index: 9999; cursor: zoom-out; box-shadow: 0 8px 32px rgba(0,0,0,0.5); border-radius: 8px;';
    enlargedImg.onclick = closeEnlargedImage;
    
    overlay.onclick = closeEnlargedImage;
    
    document.body.appendChild(overlay);
    document.body.appendChild(enlargedImg);
    document.body.style.overflow = 'hidden';
    
    window.currentEnlargedImage = enlargedImg;
    window.currentOverlay = overlay;
};

function closeEnlargedImage() {
    if (window.currentEnlargedImage) {
        window.currentEnlargedImage.remove();
        window.currentEnlargedImage = null;
    }
    if (window.currentOverlay) {
        window.currentOverlay.remove();
        window.currentOverlay = null;
    }
    document.body.style.overflow = '';
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && window.currentEnlargedImage) {
        closeEnlargedImage();
    }
});

// ==========================================
// THINKING INDICATOR
// ==========================================
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

// ==========================================
// SETTINGS
// ==========================================
function openSettings() {
    const modal = document.getElementById('settingsModal');
    const profile = currentProfile ? currentProfile.getProfile() : {};
    
    document.getElementById('settingsName').value = profile.name || '';
    document.getElementById('settingsEmail').value = profile.email || '';
    document.getElementById('assistantName').value = getAssistantName();
    
    const autonomousEnabled = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS) === 'true';
    document.getElementById('autonomousMessaging').checked = autonomousEnabled;
    
    const frequencyGroup = document.getElementById('autonomousFrequencyGroup');
    if (frequencyGroup) {
        frequencyGroup.style.display = autonomousEnabled ? 'block' : 'none';
    }
    
    const frequency = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_FREQUENCY) || 'balanced';
    document.getElementById('autonomousFrequency').value = frequency;
    
    document.getElementById('workMode').checked = 
        localStorage.getItem(STORAGE_KEYS.WORK_MODE) === 'work';
    
    if (currentProfile) {
        const stats = currentProfile.getUsageStats();
        document.getElementById('usageStats').innerHTML = '<p>Messages: ' + stats.messages + '/' + (stats.limits.messages === -1 ? '∞' : stats.limits.messages) + '</p><p>Images: ' + stats.images + '/' + (stats.limits.images === -1 ? '∞' : stats.limits.images) + '</p><p>Searches: ' + stats.searches + '/' + (stats.limits.searches === -1 ? '∞' : stats.limits.searches) + '</p>';
    }
    
    modal.style.display = 'flex';
}

window.closeSettings = function() {
    document.getElementById('settingsModal').style.display = 'none';
};

window.saveSettings = function() {
    const name = document.getElementById('settingsName').value.trim();
    const email = document.getElementById('settingsEmail').value.trim();
    const assistantName = document.getElementById('assistantName').value.trim() || 'Crump';
    const autonomous = document.getElementById('autonomousMessaging').checked;
    const frequency = document.getElementById('autonomousFrequency').value;
    const workMode = document.getElementById('workMode').checked;
    
    if (currentProfile && name) {
        currentProfile.updateProfile({ name: name, email: email });
        updateUserAvatar();
    }
    
    localStorage.setItem(STORAGE_KEYS.ASSISTANT_NAME, assistantName);
    localStorage.setItem(STORAGE_KEYS.AUTONOMOUS, autonomous);
    localStorage.setItem(STORAGE_KEYS.AUTONOMOUS_FREQUENCY, frequency);
    localStorage.setItem(STORAGE_KEYS.WORK_MODE, workMode ? 'work' : 'companion');
    
    updateAssistantNameDisplay();
    setupAutonomousMessaging();
    
    window.closeSettings();
    showToast('Settings saved', 'success');
    updateChatsList();
};

function loadSettings() {}

function updateTierBadge() {
    if (!currentProfile) return;
    
    const profile = currentProfile.getProfile();
    const tierName = profile.tier.charAt(0).toUpperCase() + profile.tier.slice(1);
    
    const sidebarTier = document.getElementById('tierName');
    const headerTier = document.getElementById('headerTierName');
    
    if (sidebarTier) sidebarTier.textContent = tierName;
    if (headerTier) headerTier.textContent = tierName;
}

// ==========================================
// AUTONOMOUS MESSAGING
// ==========================================
let autonomousInterval;

function setupAutonomousMessaging() {
    const enabled = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS) === 'true';
    
    if (autonomousInterval) {
        clearInterval(autonomousInterval);
    }
    
    if (enabled) {
        const frequency = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_FREQUENCY) || 'balanced';
        const intervals = {
            'relaxed': 15 * 60 * 1000,
            'balanced': 10 * 60 * 1000,
            'active': 5 * 60 * 1000,
            'very-active': 3 * 60 * 1000
        };
        
        const interval = intervals[frequency] || intervals.balanced;
        autonomousInterval = setInterval(sendAutonomousMessage, interval);
        console.log('Autonomous messaging enabled: ' + frequency);
    }
}

async function sendAutonomousMessage() {
    console.log('Autonomous message triggered');
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function getChats() {
    return chatsArray;
}

function getChat(chatId) {
    return chatsArray.find(c => c.id === chatId);
}

function getCurrentChat() {
    return chatsArray.find(c => c.id === currentChatId);
}

function saveChats() {
    localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chatsArray));
    if (currentChatId) {
        localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, currentChatId);
    }
}

function scrollToBottom() {
    const container = document.getElementById('chatContainer');
    setTimeout(function() {
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

function showToast(message, type) {
    type = type || 'info';
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    setTimeout(function() {
        toast.style.animation = 'toastSlide 0.3s ease reverse';
        setTimeout(function() {
            toast.remove();
        }, 300);
    }, 3000);
}

async function processFilesForUpload(files) {
    const processedFiles = [];
    
    for (const file of files) {
        try {
            if (file.type.startsWith('image/')) {
                const base64 = await fileToBase64(file);
                processedFiles.push({
                    name: file.name,
                    type: file.type,
                    size: file.size,
                    data: base64
                });
            } else {
                processedFiles.push({
                    name: file.name,
                    type: file.type,
                    size: file.size
                });
            }
        } catch (error) {
            console.error('Error processing file:', file.name, error);
        }
    }
    
    return processedFiles;
}

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// ==========================================
// DEBUG HELPERS
// ==========================================
window.crumpDebug = {
    getCurrentChat: getCurrentChat,
    getChats: getChats,
    currentProfile: currentProfile,
    sendMessage: sendMessage,
    createNewChat: createNewChat,
    loadChat: loadChat,
    getAssistantName: getAssistantName,
    setupAutonomousMessaging: setupAutonomousMessaging,
    setAssistantState: setAssistantState,
    testAPI: async function() {
        console.log('🧪 Testing API connection...');
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: 'test',
                    history: [],
                    currentDateTime: {
                        date: new Date().toLocaleDateString('en-US'),
                        time: new Date().toLocaleTimeString('en-US'),
                        timezone: 'UTC'
                    },
                    universalMemory: {},
                    workMode: 'companion'
                })
            });
            console.log('Response status:', response.status);
            const data = await response.text();
            console.log('Response:', data);
            return { status: response.status, data: data };
        } catch (error) {
            console.error('API test failed:', error);
            return { error: error.message };
        }
    }
};

console.log('✅ Crump AI v3.0 loaded - All systems operational');
