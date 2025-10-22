// ==========================================
// CRUMP AI - CORE MODULE v2.12.1
// Main application logic with all fixes applied
// ==========================================

// ==========================================
// CONFIGURATION CONSTANTS
// ==========================================
const CONFIG = {
    DUPLICATE_WINDOW_MS: 500,
    MAX_CROSS_SESSION_NOTES: 50,
    MAX_CHAT_HISTORY: 10,
    MAX_TITLE_LENGTH: 30,
    IMAGE_GENERATION_RETRIES: 2,
    FILE_SIZE_LIMIT_MB: 5,
    API_TIMEOUT: 65000,          // 65s (match backend)
    FETCH_TIMEOUT: 65000,        // Consistent with API
    WARNING_TIMEOUT: 30000,      // Show warning after 30s
    PROGRESS_INTERVAL: 5000      // Update every 5s
};

const STORAGE_KEYS = {
    CHATS: 'crump_chats',
    USER_MEMORY: 'crump_user_memory',
    UNIVERSAL_MEMORY: 'crump_universal_memory',
    NOVA_PROTOCOL: 'crump_nova_protocol',
    CURRENT_CHAT: 'crump_current_chat',
    TUTORIAL: 'crump_tutorial_completed',
    VOICE_OUTPUT: 'voiceOutput',
    AUTO_VOICE: 'autoVoice',
    FONT_STYLE: 'fontStyle',
    BG_COLOR: 'bgColor',
    SPLASH_SEEN: 'crump_splash_seen',
    SUGGESTIONS: 'crump_suggestions',
    AUTONOMOUS_MESSAGES: 'crump_autonomous_messages',
    AUTONOMOUS_INTERVAL: 'crump_autonomous_interval',
    IMAGE_GENERATOR: 'crump_image_generator',
    WORK_MODE: 'crump_work_mode',
    USER_NAME: 'crump_user_name',
    USER_INITIAL: 'crump_user_initial',
    LEARNING_ENGINE: 'crump_learning_engine',
    CORRECTIONS: 'crump_corrections',
    USER_PREFERENCES: 'crump_user_preferences',
    PERFORMANCE_METRICS: 'crump_performance_metrics',
    SHOW_CONFIDENCE: 'crump_show_confidence',
    META_COMMENTARY: 'crump_meta_commentary',
    FEATURE_REMINDERS: 'crump_feature_reminders',
    SHOWN_TIPS: 'crump_shown_tips',
    CONTEXT_SUGGESTIONS_ENABLED: 'crump_context_suggestions',
    SHOWN_SUGGESTIONS: 'crump_shown_suggestions',
    SUGGESTION_COOLDOWN: 'crump_suggestion_cooldown'
};

// Export to window for module access
window.CONFIG = CONFIG;
window.STORAGE_KEYS = STORAGE_KEYS;

// ==========================================
// TIMEOUT CONFIG
// ==========================================
const TIMEOUT_CONFIG = {
    API_REQUEST: 65000,        // 65s (5s buffer over backend)
    WARNING_TIME: 30000,       // Show warning after 30s
    PROGRESS_INTERVAL: 5000    // Update progress every 5s
};

window.TIMEOUT_CONFIG = TIMEOUT_CONFIG;

// ==========================================
// FETCH WITH TIMEOUT HELPER
// ==========================================
async function fetchWithTimeout(url, options = {}, timeout = CONFIG.FETCH_TIMEOUT) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        return response;
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            throw new Error('Request timed out after ' + (timeout/1000) + ' seconds');
        }
        throw error;
    }
}

// ==========================================
// GLOBAL STATE
// ==========================================
let currentChatId = null;
let chats = [];
let isVoiceEnabled = false;
let isAutoVoiceEnabled = false;
let isListening = false;
let recognition = null;
let currentUtterance = null;
let currentFiles = [];
let userMemory = {
    preferences: {},
    contexts: {},
    notes: []
};
let isSending = false;

// Error state management
let isInErrorState = false;
let lastErrorTime = 0;
let errorCooldownMs = 30000;

// Time/Date awareness
function getCurrentTimeContext() {
    const now = new Date();
    const hour = now.getHours();
    const minute = now.getMinutes();
    const dayName = now.toLocaleDateString('en-US', { weekday: 'long' });
    const monthName = now.toLocaleDateString('en-US', { month: 'long' });
    const dayNum = now.getDate();
    const year = now.getFullYear();
    
    let timePeriod = '';
    let timeEmoji = '';
    if (hour >= 5 && hour < 12) {
        timePeriod = 'morning';
        timeEmoji = '☀️';
    } else if (hour >= 12 && hour < 17) {
        timePeriod = 'afternoon';
        timeEmoji = '🌤️';
    } else if (hour >= 17 && hour < 22) {
        timePeriod = 'evening';
        timeEmoji = '🌆';
    } else if (hour >= 22 || hour < 2) {
        timePeriod = 'late night';
        timeEmoji = '🌙';
    } else {
        timePeriod = 'very late night';
        timeEmoji = '🌃';
    }
    
    const formattedTime = now.toLocaleTimeString('en-US', { 
        hour: 'numeric', 
        minute: '2-digit',
        hour12: true 
    });
    
    return {
        hour,
        minute,
        dayName,
        monthName,
        dayNum,
        year,
        timePeriod,
        timeEmoji,
        formattedTime,
        fullDate: `${dayName}, ${monthName} ${dayNum}, ${year}`,
        timestamp: now.toISOString(),
        isLateNight: hour >= 22 || hour < 5,
        isVeryLate: hour >= 2 && hour < 5,
        isWeekend: now.getDay() === 0 || now.getDay() === 6
    };
}

function getTimeAwareContext() {
    const time = getCurrentTimeContext();
    
    let context = `\n\n[CURRENT TIME CONTEXT:\n`;
    context += `Date: ${time.fullDate}\n`;
    context += `Time: ${time.formattedTime} (${time.timePeriod})\n`;
    
    if (time.isVeryLate) {
        context += `⚠️ It's ${time.formattedTime} - User is up VERY late. Show genuine concern.\n`;
    } else if (time.isLateNight) {
        context += `${time.timeEmoji} Late ${time.timePeriod} work session.\n`;
    } else if (time.isWeekend) {
        context += `📅 Weekend ${time.timePeriod}.\n`;
    }
    
    context += `Use this context to reference time naturally in responses.]`;
    
    return context;
}

// Autonomous messaging state
let autonomousMessagesEnabled = false;
let lastUserActivity = Date.now();
let autonomousCheckInterval = null;

// Image generation state
let preferredImageGenerator = 'pollinations';

// Learning Engine state
let learningEngine = null;
let lastAssistantMessage = null;
let awaitingCorrection = false;
let showConfidence = false;
let trainingSession = null;
let metaCommentaryEnabled = false;

// Suggestion Engine state
let suggestionEngine = null;
let contextSuggestionsEnabled = true;

// Context Engine state
let contextEngine = null;
let messageDeduper = null;
let autonomousEngine = null;
let profileManager = null;

// Export globals
window.chats = chats;
window.currentChatId = currentChatId;
window.isSending = isSending;
window.lastUserActivity = lastUserActivity;
window.isListening = isListening;
window.isVoiceEnabled = isVoiceEnabled;
window.isAutoVoiceEnabled = isAutoVoiceEnabled;
window.workMode = 'companion';
window.showConfidence = showConfidence;
window.metaCommentaryEnabled = metaCommentaryEnabled;
window.contextSuggestionsEnabled = contextSuggestionsEnabled;
window.autonomousMessagesEnabled = autonomousMessagesEnabled;
window.preferredImageGenerator = preferredImageGenerator;

// ==========================================
// ERROR HANDLER UTILITY
// ==========================================
const ErrorHandler = {
    handle(error, context = 'Unknown', options = {}) {
        const {
            showNotification = true,
            addMessage = false,
            userMessage = null,
            logToConsole = true
        } = options;
        
        if (logToConsole) {
            console.error(`❌ ${context}:`, error);
            if (error.stack) {
                console.error('Stack:', error.stack);
            }
        }
        
        if (window.hideThinking) {
            window.hideThinking();
        }
        
        const message = userMessage || this.getUserFriendlyMessage(error, context);
        
        if (addMessage && window.addMessage) {
            window.addMessage('assistant', message);
        }
        
        if (showNotification && window.showNotification) {
            window.showNotification(`Error: ${context}`, 'error');
        }
        
        return message;
    },
    
    getUserFriendlyMessage(error, context) {
        const errorMap = {
            'timeout': 'The request took too long. Please try again.',
            'network': 'Network error. Please check your connection.',
            'permission': 'Permission denied. Please check your settings.',
            'validation': 'Invalid input. Please check your data.',
            'rate_limit': 'Too many requests. Please wait a moment.',
            'auth': 'Authentication failed. Please log in again.'
        };
        
        const errorType = this.detectErrorType(error);
        return errorMap[errorType] || `An error occurred: ${error.message}`;
    },
    
    detectErrorType(error) {
        const message = error.message.toLowerCase();
        
        if (message.includes('timeout') || message.includes('timed out')) return 'timeout';
        if (message.includes('fetch') || message.includes('network')) return 'network';
        if (message.includes('permission') || message.includes('denied')) return 'permission';
        if (message.includes('invalid') || message.includes('validation')) return 'validation';
        if (message.includes('rate') || message.includes('429')) return 'rate_limit';
        if (message.includes('auth') || message.includes('401') || message.includes('403')) return 'auth';
        
        return 'unknown';
    }
};

window.ErrorHandler = ErrorHandler;

// ==========================================
// INITIALIZATION
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Crump AI initializing...');
    
    // Check critical elements exist
    const requiredElements = [
        'chatContainer',
        'userInput',
        'sendButton',
        'newChatBtn'
    ];
    
    const missing = [];
    for (const id of requiredElements) {
        if (!document.getElementById(id)) {
            missing.push(id);
        }
    }
    
    if (missing.length > 0) {
        console.error('❌ CRITICAL: Missing required HTML elements:', missing);
        alert('Error: Page HTML is incomplete. Please refresh or contact support.');
        return;
    }
    
    // Initialize engines
    messageDeduper = new MessageDeduplicator(CONFIG.DUPLICATE_WINDOW_MS);
    contextEngine = new ContextAwarenessEngine();
    suggestionEngine = new SuggestionEngine();
    autonomousEngine = new AutonomousEngine();
    learningEngine = new LearningEngine();
    
    window.messageDeduper = messageDeduper;
    window.contextEngine = contextEngine;
    window.suggestionEngine = suggestionEngine;
    window.autonomousEngine = autonomousEngine;
    window.learningEngine = learningEngine;
    
    // Initialize Profile Manager
    profileManager = new window.UserProfileManager();
    window.profileManager = profileManager;
    console.log('👤 Profile Manager initialized:', profileManager.getTierInfo());
    
    // Update UI with tier info
    updateTierDisplay();
    
    // Setup voice recognition
    setupVoiceRecognition();
    
    // Load data
    loadChats();
    loadUniversalMemory();
    loadSettings();
    
    // FIX: Load last active chat, not first
    if (chats.length === 0) {
        createNewChat();
    } else {
        const lastChatId = localStorage.getItem(STORAGE_KEYS.CURRENT_CHAT);
        
        if (lastChatId && chats.find(c => c.id === lastChatId)) {
            loadChat(lastChatId);
            console.log('✅ Restored last active chat:', lastChatId);
        } else {
            loadChat(chats[0].id);
            console.log('ℹ️ Loading most recent chat');
        }
    }
    
    // Event listeners
    document.getElementById('sendButton').addEventListener('click', sendMessage);
    document.getElementById('userInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    document.getElementById('newChatBtn').addEventListener('click', createNewChat);
    
    // File upload
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.addEventListener('change', handleFileUpload);
    }
    
    console.log('✅ Crump AI initialized');
});

// ==========================================
// CHAT MANAGEMENT
// ==========================================
function createNewChat() {
    const newChat = {
        id: Date.now().toString(),
        title: 'New Chat',
        messages: [],
        created: Date.now(),
        updated: Date.now()
    };
    
    chats.unshift(newChat);
    saveChats();
    loadChat(newChat.id);
    window.renderChatsList();
    
    console.log('✨ New chat created:', newChat.id);
}

function loadChat(chatId) {
    const chat = chats.find(c => c.id === chatId);
    if (!chat) return;
    
    currentChatId = chatId;
    window.currentChatId = chatId;
    
    // FIX: Save current chat for restoration
    localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, chatId);
    
    window.renderMessages(chat.messages);
    window.renderChatsList();
    updateHeaderDisplay();
    
    if (contextEngine) {
        contextEngine.loadChatContext(chatId);
    }
}

function deleteChat(chatId) {
    if (!confirm('Delete this chat?')) return;
    
    chats = chats.filter(c => c.id !== chatId);
    saveChats();
    
    if (currentChatId === chatId) {
        if (chats.length > 0) {
            loadChat(chats[0].id);
        } else {
            createNewChat();
        }
    }
    
    window.renderChatsList();
}

function loadChats() {
    const saved = localStorage.getItem(STORAGE_KEYS.CHATS);
    if (saved) {
        try {
            chats = JSON.parse(saved);
            window.chats = chats;
        } catch (e) {
            console.error('Failed to load chats:', e);
            chats = [];
        }
    }
}

function saveChats() {
    localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
    window.chats = chats;
}

// ==========================================
// MESSAGE HANDLING
// ==========================================
function addMessage(role, content, imageUrl = null) {
    const chat = chats.find(c => c.id === currentChatId);
    if (!chat) return;
    
    const message = {
        role,
        content,
        timestamp: Date.now(),
        imageUrl
    };
    
    chat.messages.push(message);
    chat.updated = Date.now();
    
    // Update chat title from first user message
    if (role === 'user' && chat.messages.length === 1) {
        chat.title = content.substring(0, CONFIG.MAX_TITLE_LENGTH) + (content.length > CONFIG.MAX_TITLE_LENGTH ? '...' : '');
    }
    
    if (role === 'assistant') {
        lastAssistantMessage = message;
        window.lastAssistantMessage = lastAssistantMessage;
        
        if (learningEngine) {
            learningEngine.updateMetrics('response');
        }
    }
    
    saveChats();
    window.renderMessages(chat.messages);
    window.renderChatsList();
    
    // Auto voice output
    if (role === 'assistant' && isAutoVoiceEnabled) {
        speakText(content);
    }
}

window.addMessage = addMessage;

// ==========================================
// SEND MESSAGE
// ==========================================
async function sendMessage() {
    const input = document.getElementById('userInput');
    const message = input.value.trim();

    console.log('🚀 SEND MESSAGE TRIGGERED');
    console.log('📝 Message:', message);
    console.log('🔒 isSending:', isSending);
    console.log('📁 Files:', currentFiles.length);
    
    lastUserActivity = Date.now();
    window.lastUserActivity = lastUserActivity;
    
    if (isSending) {
        console.log('🔒 BLOCKED: Already sending');
        window.showNotification('⏸️ Please wait - message in progress', 'info');
        return;
    }
    
    if (!message && currentFiles.length === 0) {
        console.log('⚠️ BLOCKED: No content');
        return;
    }
    
    if (message && messageDeduper && messageDeduper.isDuplicate(message)) {
        console.log('🚫 BLOCKED: Duplicate message');
        return;
    }

    // CHECK TIER LIMITS
    if (window.profileManager) {
        const messageCheck = window.profileManager.canSendMessage();
        
        if (!messageCheck.allowed) {
            window.showNotification(messageCheck.message.split('\n')[0], 'error');
            setTimeout(() => {
                addMessage('assistant', messageCheck.message);
                if (messageCheck.action === 'upgrade') {
                    window.showUpgradePrompt();
                }
            }, 500);
            return;
        }
        
        if (messageCheck.warning) {
            window.showNotification(messageCheck.warning, 'info');
        }
    }

    // UNIFIED UNLOCK FUNCTION
    const unlockUI = () => {
        isSending = false;
        window.isSending = false;
        input.disabled = false;
        const sendBtn = document.querySelector('.icon-btn.primary');
        if (sendBtn) sendBtn.disabled = false;
        console.log('🔓 UI UNLOCKED');
    };

    // Lock the UI
    isSending = true;
    window.isSending = true;
    console.log('🔒 SEND LOCKED at', Date.now());
    input.disabled = true;
    const sendBtn = document.querySelector('.icon-btn.primary');
    if (sendBtn) sendBtn.disabled = true;
    
    try {
        // Handle Nova activation/deactivation
        if (detectNovaActivation(message)) {
            activateNovaProtocol();
            input.value = '';
            window.showThinking();
            setTimeout(() => {
                window.hideThinking();
                addMessage('assistant', `⭐ **Nova-Secure Protocol Activated**\n\nHello Gregory. Full creator context loaded.\n\nI now have access to:\n- Complete project history (Nova Secure → Crump AI v2.12.1)\n- N² Engine context (Nala & Niobi)\n- Your communication preferences and working style\n- All persistent notes and technical context\n\nOperating in full creator mode. How can I assist you today?`);
                unlockUI();
            }, 800);
            return;
        }

        if (detectNovaDeactivation(message)) {
            deactivateNovaProtocol();
            input.value = '';
            window.showThinking();
            setTimeout(() => {
                window.hideThinking();
                addMessage('assistant', `👑 **Nova-Secure Protocol Deactivated**\n\nReturning to standard mode. Universal memory remains active.\n\nTo reactivate:\n- "Activate Nova-Secure" or "Nova-Secure"\n- "Activate Nala Niobi Protocol"`);
                unlockUI();
            }, 800);
            return;
        }

        // Learning engine processing
        if (lastAssistantMessage && learningEngine) {
            const correctionDetection = learningEngine.detectCorrectionPattern(message, lastAssistantMessage.content);
            if (correctionDetection.isCorrection) {
                learningEngine.recordCorrection(
                    correctionDetection.originalResponse,
                    correctionDetection.correctedResponse
                );
            }
        }

        // Handle image generation
        if (shouldGenerateImage(message)) {
            input.value = '';
            addMessage('user', message);
            handleImageGeneration(message);
            unlockUI();
            return;
        }

        // Add user message
        let fileDataToSend = null;
        
        if (currentFiles.length > 0) {
            fileDataToSend = await Promise.all(currentFiles.map(async file => {
                const data = await readFileAsDataURL(file);
                return {
                    name: file.name,
                    type: file.type,
                    size: file.size,
                    data: data
                };
            }));
            
            addMessage('user', message, null);
            const chat = chats.find(c => c.id === currentChatId);
            chat.messages[chat.messages.length - 1].fileData = fileDataToSend;
            saveChats();
        } else {
            addMessage('user', message);
        }
        
        input.value = '';
        currentFiles = [];
        
        // Clear file preview
        const preview = document.getElementById('filePreview');
        if (preview) preview.innerHTML = '';

        // Send to API
        window.showThinking();
        const progressIndicator = showProgressiveTimeout();

        const chat = chats.find(c => c.id === currentChatId);
        
        try {
            const response = await fetchWithTimeout('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message + getMemoryContext() + getTimeAwareContext(),
                    history: chat.messages.slice(-CONFIG.MAX_CHAT_HISTORY).filter(m => m.content && m.content.trim() !== ''),
                    fileData: fileDataToSend,
                    needsSearch: shouldSearchWeb(message),
                    novaActive: isNovaActive(),
                    novaProtocol: isNovaActive() ? getNovaProtocol() : null,
                    universalMemory: getUniversalMemory(),
                    workMode: window.workMode || 'companion'
                })
            }, TIMEOUT_CONFIG.API_REQUEST);
            
            clearProgressiveTimeout(progressIndicator);
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.message || errorData.error || `Server error: ${response.status}`);
            }
            
            const data = await response.json();
            window.hideThinking();
            addMessage('assistant', data.response);

            // Increment usage counter
            if (window.profileManager) {
                window.profileManager.incrementMessageUsage();
            }

            // Check for web search usage
            if (shouldSearchWeb(message) && window.profileManager) {
                window.profileManager.incrementSearchUsage();
            }

            if (suggestionEngine && contextSuggestionsEnabled) {
                suggestionEngine.checkAndShowSuggestion(message, chat);
            }

            if (learningEngine && canExitErrorState() && Math.random() < 0.15) {
                const trainingRequest = learningEngine.getProactiveTrainingRequest();
                if (trainingRequest) {
                    setTimeout(() => {
                        addMessage('assistant', trainingRequest);
                    }, 2000);
                }
            }
            
        } catch (error) {
            clearProgressiveTimeout(progressIndicator);
            window.hideThinking();
            handleSendError(error);
        }
        
    } finally {
        unlockUI();
    }
}

window.sendMessage = sendMessage;

// ==========================================
// PROGRESSIVE TIMEOUT INDICATOR
// ==========================================
function showProgressiveTimeout() {
    const startTime = Date.now();
    let warningShown = false;
    
    const thinkingElement = document.getElementById('thinkingIndicator');
    if (!thinkingElement) return null;
    
    const progressText = document.createElement('div');
    progressText.className = 'timeout-progress';
    progressText.style.cssText = 'font-size: 11px; color: var(--text-tertiary); margin-top: 8px; text-align: center;';
    thinkingElement.appendChild(progressText);
    
    const interval = setInterval(() => {
        const elapsed = Date.now() - startTime;
        const remaining = Math.ceil((TIMEOUT_CONFIG.API_REQUEST - elapsed) / 1000);
        
        if (remaining <= 0 || !document.getElementById('thinkingIndicator')) {
            clearInterval(interval);
            return;
        }
        
        // Update progress text
        if (elapsed > TIMEOUT_CONFIG.WARNING_TIME && !warningShown) {
            progressText.textContent = `⏱️ Taking longer than usual... (${remaining}s remaining)`;
            progressText.style.color = '#f59e0b';
            warningShown = true;
        } else if (elapsed > TIMEOUT_CONFIG.WARNING_TIME) {
            progressText.textContent = `⏱️ Still processing... (${remaining}s)`;
        } else {
            const seconds = Math.ceil(elapsed / 1000);
            progressText.textContent = `Thinking... (${seconds}s)`;
        }
    }, TIMEOUT_CONFIG.PROGRESS_INTERVAL);
    
    return interval;
}

function clearProgressiveTimeout(interval) {
    if (interval) {
        clearInterval(interval);
    }
}

window.showProgressiveTimeout = showProgressiveTimeout;
window.clearProgressiveTimeout = clearProgressiveTimeout;

// ==========================================
// ERROR HANDLING
// ==========================================
function handleSendError(error) {
    enterErrorState();
    console.error('❌ SEND ERROR:', error);
    console.error('Error stack:', error.stack);
    
    let errorMsg = '⚠️ **Something Went Wrong**\n\n';
    let errorType = 'error';
    
    if (error.message?.includes('timeout') || error.name === 'AbortError' || error.message?.includes('timed out')) {
        errorMsg = '⏱️ **Request Timeout**\n\n';
        errorMsg += 'Your request took too long to complete.\n\n';
        errorMsg += '**Possible causes:**\n';
        errorMsg += '• Complex question requiring lots of thinking\n';
        errorMsg += '• Web search taking too long\n';
        errorMsg += '• Server experiencing high load\n\n';
        errorMsg += '**What to try:**\n';
        errorMsg += '1. **Break it down** - Split your question into smaller parts\n';
        errorMsg += '2. **Simplify** - Try asking in a more direct way\n';
        errorMsg += '3. **Wait** - Give it a minute and try again\n';
        errorType = 'info';
    } else if (error.message?.includes('Failed to fetch') || error.message?.includes('fetch')) {
        errorMsg = '🌐 **Connection Error**\n\n';
        errorMsg += 'Cannot reach the server.\n\n';
        errorMsg += '**Possible causes:**\n';
        errorMsg += '• No internet connection\n';
        errorMsg += '• Server is down for maintenance\n';
        errorMsg += '• Firewall blocking the request\n\n';
        errorMsg += '**What to try:**\n';
        errorMsg += '1. Check your internet connection\n';
        errorMsg += '2. Refresh the page (F5)\n';
        errorMsg += '3. Try again in a few minutes\n';
    } else if (error.message?.includes('429') || error.message?.includes('rate limit')) {
        errorMsg = '🚦 **Rate Limited**\n\n';
        errorMsg += 'Too many requests in a short time.\n\n';
        errorMsg += 'Please wait 60 seconds before trying again.\n';
        errorType = 'info';
    } else if (error.message?.includes('token') || error.message?.includes('too long')) {
        errorMsg = '📏 **Message Too Long**\n\n';
        errorMsg += 'Your message or conversation history is too long.\n\n';
        errorMsg += '**What to try:**\n';
        errorMsg += '1. Start a new chat\n';
        errorMsg += '2. Shorten your message\n';
        errorMsg += '3. Remove unnecessary details\n';
    } else {
        errorMsg += `**Error:** ${error.message}\n\n`;
        errorMsg += '**Debug Info:**\n';
        errorMsg += `• Time: ${new Date().toLocaleTimeString()}\n`;
        errorMsg += `• Type: ${error.name}\n\n`;
        errorMsg += 'If this keeps happening, try refreshing the page.\n';
    }
    
    addMessage('assistant', errorMsg);
    window.showNotification('❌ Message failed - check details above', errorType);
}

function enterErrorState() {
    isInErrorState = true;
    lastErrorTime = Date.now();
}

function canExitErrorState() {
    if (!isInErrorState) return true;
    return Date.now() - lastErrorTime > errorCooldownMs;
}

window.handleSendError = handleSendError;

// ==========================================
// TIER DISPLAY
// ==========================================
function updateTierDisplay() {
    if (!window.profileManager) return;
    
    const tierInfo = window.profileManager.getTierInfo();
    
    // Add tier badge to header
    const header = document.querySelector('.header-left');
    if (header && !document.querySelector('.tier-badge')) {
        const tierBadge = document.createElement('div');
        tierBadge.className = 'tier-badge';
        tierBadge.innerHTML = `
            <span class="tier-icon">${tierInfo.icon}</span>
            <span class="tier-name">${tierInfo.name}</span>
        `;
        tierBadge.onclick = () => window.showUpgradePrompt();
        tierBadge.style.cursor = 'pointer';
        tierBadge.title = 'View plan details';
        header.appendChild(tierBadge);
    }
}

window.updateTierDisplay = updateTierDisplay;

// ==========================================
// NOVA PROTOCOL
// ==========================================
function detectNovaActivation(message) {
    const patterns = [
        /activate\s+nova[\s-]?secure/i,
        /^nova[\s-]?secure$/i,
        /activate\s+nala\s+niobi/i,
        /^nala\s+niobi\s+protocol$/i
    ];
    return patterns.some(p => p.test(message));
}

function detectNovaDeactivation(message) {
    const patterns = [
        /deactivate\s+nova[\s-]?secure/i,
        /turn\s+off\s+nova/i,
        /^nova[\s-]?secure\s+off$/i
    ];
    return patterns.some(p => p.test(message));
}

function initNovaProtocol() {
    const existing = localStorage.getItem(STORAGE_KEYS.NOVA_PROTOCOL);
    if (existing) return JSON.parse(existing);
    return {
        active: false, activations: [],
        gregoryContext: {
            identity: { name: "Gregory D. Crump Jr.", role: "Creator and Lead Developer", relationship: "Technical partner and collaborator" },
            projectHistory: { currentProject: "Crump AI v2.12.1", previousProjects: ["Nova Secure (renamed to Crump AI)"], startDate: "October 14, 2025", deploymentUrl: "crumpai.vercel.app" },
            engineDetails: { name: "N² Engine", meaning: "Named after daughters Nala and Niobi", originalName: "Nova (stellar explosion/new star)" },
            communicationStyle: { tone: "Direct, no-nonsense, technical", approach: "Challenge assumptions, ask clarifying questions", responseStyle: "Detailed technical explanations", codeFormat: "Production-ready with comments" },
            philosophy: { values: ["Ship fast", "Iterate quickly", "Build empires"], approach: "Artist/innovator mindset - build to create", priority: "Complete products over perfection" }
        },
        persistentNotes: []
    };
}

function activateNovaProtocol() {
    const protocol = initNovaProtocol();
    protocol.active = true;
    protocol.activations.push({ timestamp: new Date().toISOString() });
    localStorage.setItem(STORAGE_KEYS.NOVA_PROTOCOL, JSON.stringify(protocol));
    updateHeaderDisplay();
    return protocol;
}

function deactivateNovaProtocol() {
    const protocol = initNovaProtocol();
    protocol.active = false;
    localStorage.setItem(STORAGE_KEYS.NOVA_PROTOCOL, JSON.stringify(protocol));
    updateHeaderDisplay();
}

function isNovaActive() {
    const protocol = localStorage.getItem(STORAGE_KEYS.NOVA_PROTOCOL);
    return protocol ? JSON.parse(protocol).active : false;
}

function getNovaProtocol() {
    const protocol = localStorage.getItem(STORAGE_KEYS.NOVA_PROTOCOL);
    return protocol ? JSON.parse(protocol) : null;
}

window.isNovaActive = isNovaActive;
window.getNovaProtocol = getNovaProtocol;

// ==========================================
// HELPER FUNCTIONS
// ==========================================
function shouldSearchWeb(message) {
    const searchTriggers = [
        'search', 'look up', 'find', 'what is', 'who is', 'when did',
        'current', 'latest', 'recent', 'news', 'price of', 'weather'
    ];
    const lower = message.toLowerCase();
    return searchTriggers.some(trigger => lower.includes(trigger));
}

function getMemoryContext() {
    const memory = getUniversalMemory();
    if (!memory.crossSessionContext || memory.crossSessionContext.length === 0) {
        return '';
    }
    
    const recent = memory.crossSessionContext.slice(-5).join('; ');
    return `\n\n[Cross-session context: ${recent}]`;
}

function getUniversalMemory() {
    const saved = localStorage.getItem(STORAGE_KEYS.UNIVERSAL_MEMORY);
    return saved ? JSON.parse(saved) : { crossSessionContext: [], conversationHistory: {} };
}

function loadUniversalMemory() {
    // Placeholder for memory loading
}

function updateHeaderDisplay() {
    // Placeholder for header updates
}

function readFileAsDataURL(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

function handleFileUpload(event) {
    currentFiles = Array.from(event.target.files);
    console.log('📎 Files selected:', currentFiles.length);
}

// ==========================================
// VOICE RECOGNITION
// ==========================================
function setupVoiceRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        window.recognition = recognition;
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.onresult = (event) => {
            document.getElementById('userInput').value = event.results[0][0].transcript;
            isListening = false;
            window.isListening = false;
        };
        recognition.onerror = (event) => {
            isListening = false;
            window.isListening = false;
            if (event.error !== 'no-speech' && event.error !== 'aborted') {
                window.showNotification('Voice error: ' + event.error, 'error');
            }
        };
        recognition.onend = () => {
            isListening = false;
            window.isListening = false;
        };
    }
}

function speakText(text) {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        window.speechSynthesis.speak(utterance);
    }
}

// ==========================================
// SETTINGS
// ==========================================
function loadSettings() {
    const voiceOutput = localStorage.getItem(STORAGE_KEYS.VOICE_OUTPUT) === 'true';
    const autoVoice = localStorage.getItem(STORAGE_KEYS.AUTO_VOICE) === 'true';
    const autonomousMessages = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_MESSAGES) === 'true';
    const autonomousInterval = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_INTERVAL) || 'balanced';
    const workMode = localStorage.getItem(STORAGE_KEYS.WORK_MODE) || 'companion';
    const showConfidenceSetting = localStorage.getItem(STORAGE_KEYS.SHOW_CONFIDENCE) === 'true';
    const metaCommentarySetting = localStorage.getItem(STORAGE_KEYS.META_COMMENTARY) === 'true';
    
    // Update toggle elements if they exist
    const voiceToggle = document.getElementById('voiceToggle');
    const autoVoiceToggle = document.getElementById('autoVoiceToggle');
    const autonomousToggle = document.getElementById('autonomousToggle');
    const confidenceToggle = document.getElementById('confidenceToggle');
    const metaToggle = document.getElementById('metaToggle');
    
    if (voiceToggle) voiceToggle.checked = voiceOutput;
    if (autoVoiceToggle) autoVoiceToggle.checked = autoVoice;
    if (autonomousToggle) autonomousToggle.checked = autonomousMessages;
    if (confidenceToggle) confidenceToggle.checked = showConfidenceSetting;
    if (metaToggle) metaToggle.checked = metaCommentarySetting;
    
    showConfidence = showConfidenceSetting;
    window.showConfidence = showConfidence;
    metaCommentaryEnabled = metaCommentarySetting;
    window.metaCommentaryEnabled = metaCommentaryEnabled;
    
    // FIXED: Check if autonomousEngine exists before using it
    if (window.autonomousEngine && typeof window.autonomousEngine.setIntervalPreset === 'function') {
        window.autonomousEngine.setIntervalPreset(autonomousInterval);
    } else {
        console.warn('⚠️ Autonomous engine not yet initialized, will set interval later');
        window.pendingAutonomousInterval = autonomousInterval;
    }
    
    if (autonomousMessages) {
        const intervalSettings = document.getElementById('autonomous-interval-settings');
        if (intervalSettings) intervalSettings.style.display = 'block';
    }
    
    window.workMode = workMode;
    isVoiceEnabled = voiceOutput;
    window.isVoiceEnabled = voiceOutput;
    isAutoVoiceEnabled = autoVoice;
    window.isAutoVoiceEnabled = autoVoice;
    autonomousMessagesEnabled = autonomousMessages;
    window.autonomousMessagesEnabled = autonomousMessages;
    
    // FIXED: Check if autonomousEngine exists before starting it
    if (autonomousMessages && window.autonomousEngine) {
        window.autonomousEngine.start();
    }
}

window.loadSettings = loadSettings;

console.log('✅ Core module v2.12.1 loaded - All fixes applied');
