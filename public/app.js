// ==========================================
// CRUMP AI - CORE MODULE v2.11.0
// Main application logic - optimized for Vercel
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
    FILE_SIZE_LIMIT_MB: 5
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
// FETCH WITH TIMEOUT HELPER
// ==========================================
async function fetchWithTimeout(url, options = {}, timeout = 9000) {
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
        context += `⚠️ It's ${time.formattedTime} - Gregory is up VERY late. Show genuine concern.\n`;
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

// Context Engine state
let contextEngine = null;
let messageDeduper = null;
let autonomousEngine = null;

// Tutorial state
let currentTutorialStep = 1;
const tutorialSteps = [
    {
        icon: "👋",
        title: "Welcome, Gregory",
        text: "I'm Crump, your personal AI assistant powered by the N² Engine. Let me show you around."
    },
    {
        icon: "💬",
        title: "Powerful Conversations",
        text: "I can help with technical work, creative projects, analysis, and more. Just type your question and hit send."
    },
    {
        icon: "🎤",
        title: "Voice & Vision",
        text: "Use voice input to speak naturally, upload images for analysis, or ask me to generate images for you."
    },
    {
        icon: "🧠",
        title: "Smart Memory",
        text: "Tell me to 'Remember that...' and I'll store important information. I learn from every conversation to serve you better."
    }
];

const welcomeMessages = [
    "Good to see you, Gregory. Ready when you are.",
    "What's on your mind today?",
    "Let's build something legendary.",
    "Another day, another empire move. What's first?",
    "Back at it. What do you need?",
    "Ready to make things happen. What's the play?",
    "Let's get to work. What are we tackling?",
    "What's the mission today?",
    "Time to turn ideas into reality. What's up?",
    "Let's do this. What's on the agenda?"
];

const featureTips = [
    {
        id: 'image-generation',
        message: "Just thinking—you can ask me to generate images anytime. Just say 'create an image of...' and I'll handle it.",
        category: 'creative'
    },
    {
        id: 'image-analysis',
        message: "Quick tip: You can upload images and ask me questions about them. I can analyze, describe, or extract text.",
        category: 'analysis'
    },
    {
        id: 'voice-input',
        message: "By the way, see that microphone button? You can talk to me instead of typing. Makes long messages easier.",
        category: 'interface'
    },
    {
        id: 'memory-system',
        message: "Heads up: Tell me to 'Remember that...' and I'll store important info permanently. I can recall it anytime.",
        category: 'memory'
    },
    {
        id: 'context-cards',
        message: "Notice those context cards at the top? You can organize conversations by project. Helps me stay focused on what you're working on.",
        category: 'organization'
    },
    {
        id: 'learning-feedback',
        message: "Saw those 👍👎 buttons? Use them to help me learn your preferences. I actually get smarter from your feedback.",
        category: 'learning'
    },
    {
        id: 'nova-protocol',
        message: "For deep technical work, type 'Nova-Secure' to activate my full creator context. I'll have access to your complete project history.",
        category: 'advanced'
    },
    {
        id: 'corrections',
        message: "If I get something wrong, just say 'no, actually...' and I'll learn from it. I track corrections to improve over time.",
        category: 'learning'
    },
    {
        id: 'code-style',
        message: "Fun fact: I learn your coding style automatically. Show me code a few times and I'll match your formatting preferences.",
        category: 'technical'
    },
    {
        id: 'multi-chat',
        message: "You can have multiple conversations going. Create new chats to separate different projects or topics.",
        category: 'organization'
    }
];

let featureRemindersEnabled = false;
let shownTips = [];

let contextSuggestionsEnabled = false;
let shownSuggestions = [];
let lastSuggestionTime = 0;
const SUGGESTION_COOLDOWN_MS = 5 * 60 * 1000;

const contextSuggestions = [
    {
        id: 'image-generation-after-upload',
        trigger: 'image_upload',
        condition: (context) => context.hasUploadedImage && !context.askedToGenerate,
        message: "I can also generate similar images if you describe what you want.",
        action: "Try: 'Create an image of...'",
        priority: 'high',
        cooldown: 10 * 60 * 1000
    },
    {
        id: 'code-style-learning',
        trigger: 'code_in_message',
        condition: (context) => context.hasCode && !context.hasLearnedStyle,
        message: "I can learn your coding style from the code you share with me.",
        action: "Keep sharing code and I'll adapt!",
        priority: 'medium',
        cooldown: 20 * 60 * 1000
    },
    {
        id: 'confidence-scores',
        trigger: 'user_correction',
        condition: (context) => context.userCorrected && !context.confidenceEnabled,
        message: "Enable confidence scores in Settings to see how certain I am about responses.",
        action: "⚙️ Settings → Show Confidence Scores",
        priority: 'high',
        cooldown: 15 * 60 * 1000
    },
    {
        id: 'context-card-suggestion',
        trigger: 'long_conversation',
        condition: (context) => context.messageCount > 10 && context.activeContexts === 0,
        message: "This is becoming a longer conversation. Want to add a context card to organize it?",
        action: "Click the + button at the top",
        priority: 'medium',
        cooldown: 30 * 60 * 1000
    },
    {
        id: 'voice-input-suggestion',
        trigger: 'long_user_message',
        condition: (context) => context.messageLength > 500,
        message: "Long message! You can use voice input (🎤) to talk instead of typing.",
        action: "Click the microphone button",
        priority: 'low',
        cooldown: 20 * 60 * 1000
    },
    {
        id: 'memory-system',
        trigger: 'repeated_info',
        condition: (context) => context.repeatedInfo && !context.hasMemoryNotes,
        message: "You can tell me to 'Remember that...' and I'll store information permanently.",
        action: "Say: 'Remember that [info]'",
        priority: 'medium',
        cooldown: 25 * 60 * 1000
    },
    {
        id: 'image-analysis',
        trigger: 'question_about_uploaded_image',
        condition: (context) => context.hasUploadedImage && context.askingQuestion,
        message: "I can analyze images in detail—ask me specific questions about what you uploaded.",
        action: "Try: 'What colors are in this?'",
        priority: 'medium',
        cooldown: 15 * 60 * 1000
    },
    {
        id: 'multi-chat',
        trigger: 'topic_shift',
        condition: (context) => context.topicChanged && context.totalChats < 3,
        message: "Switching topics? You can create separate chats to keep conversations organized.",
        action: "Click ✨ New Chat in the sidebar",
        priority: 'low',
        cooldown: 30 * 60 * 1000
    },
    {
        id: 'learning-feedback',
        trigger: 'multiple_responses',
        condition: (context) => context.responseCount > 5 && context.feedbackGiven === 0,
        message: "Use 👍👎 buttons to help me learn your preferences and improve over time.",
        action: "Found after each of my responses",
        priority: 'medium',
        cooldown: 20 * 60 * 1000
    },
    {
        id: 'nova-protocol',
        trigger: 'technical_deep_dive',
        condition: (context) => context.isTechnical && context.messageCount > 5 && !context.novaActive,
        message: "For deep technical work, activate Nova-Secure protocol for full creator context.",
        action: "Type: 'Nova-Secure'",
        priority: 'high',
        cooldown: 40 * 60 * 1000
    }
];

// Export state to window
window.currentChatId = currentChatId;
window.chats = chats;
window.isVoiceEnabled = isVoiceEnabled;
window.isAutoVoiceEnabled = isAutoVoiceEnabled;
window.isListening = isListening;
window.recognition = recognition;
window.currentUtterance = currentUtterance;
window.currentFiles = currentFiles;
window.userMemory = userMemory;
window.isSending = isSending;
window.lastUserActivity = lastUserActivity;
window.preferredImageGenerator = preferredImageGenerator;
window.learningEngine = learningEngine;
window.showConfidence = showConfidence;
window.metaCommentaryEnabled = metaCommentaryEnabled;
window.contextSuggestionsEnabled = contextSuggestionsEnabled;
window.featureRemindersEnabled = featureRemindersEnabled;
window.shownTips = shownTips;
window.tutorialSteps = tutorialSteps;
window.contextSuggestions = contextSuggestions;

// ==========================================
// ERROR STATE MANAGEMENT
// ==========================================
function enterErrorState() {
    isInErrorState = true;
    lastErrorTime = Date.now();
    console.log('🚨 Entered error state - cooldown active');
}

function canExitErrorState() {
    if (!isInErrorState) return true;
    const cooldownExpired = Date.now() - lastErrorTime > errorCooldownMs;
    if (cooldownExpired) {
        isInErrorState = false;
        console.log('✅ Exited error state - system ready');
    }
    return !isInErrorState;
}

window.canExitErrorState = canExitErrorState;

// ==========================================
// FEATURE TIPS
// ==========================================
function getRandomFeatureTip() {
    if (!featureRemindersEnabled) return null;
    
    const recentlyShown = shownTips.slice(-20);
    const availableTips = featureTips.filter(tip => !recentlyShown.includes(tip.id));
    
    if (availableTips.length === 0) {
        shownTips = [];
        localStorage.setItem(STORAGE_KEYS.SHOWN_TIPS, JSON.stringify(shownTips));
        return featureTips[Math.floor(Math.random() * featureTips.length)];
    }
    
    const tip = availableTips[Math.floor(Math.random() * availableTips.length)];
    
    shownTips.push(tip.id);
    localStorage.setItem(STORAGE_KEYS.SHOWN_TIPS, JSON.stringify(shownTips));
    
    return tip;
}

function shouldShowFeatureTip() {
    if (!featureRemindersEnabled) return false;
    return Math.random() < 0.2;
}

window.getRandomFeatureTip = getRandomFeatureTip;
window.shouldShowFeatureTip = shouldShowFeatureTip;

function loadFeatureReminders() {
    const enabled = localStorage.getItem(STORAGE_KEYS.FEATURE_REMINDERS) === 'true';
    const shown = localStorage.getItem(STORAGE_KEYS.SHOWN_TIPS);
    
    featureRemindersEnabled = enabled;
    shownTips = shown ? JSON.parse(shown) : [];
    
    if (document.getElementById('featureRemindersToggle')) {
        document.getElementById('featureRemindersToggle').checked = enabled;
    }
}

function loadContextSuggestions() {
    const enabled = localStorage.getItem(STORAGE_KEYS.CONTEXT_SUGGESTIONS_ENABLED) === 'true';
    contextSuggestionsEnabled = enabled;
    
    if (document.getElementById('contextSuggestionsToggle')) {
        document.getElementById('contextSuggestionsToggle').checked = enabled;
    }
}

// ==========================================
// INITIALIZATION
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    function initializeSplashScreen() {
        const splashSeen = sessionStorage.getItem(STORAGE_KEYS.SPLASH_SEEN);
        const tutorialCompleted = localStorage.getItem(STORAGE_KEYS.TUTORIAL);
        const splashScreen = document.getElementById('splash-screen');
        
        if (splashSeen) {
            splashScreen.style.display = 'none';
            if (!tutorialCompleted) {
                setTimeout(() => window.showTutorial(), 500);
            }
        } else {
            sessionStorage.setItem(STORAGE_KEYS.SPLASH_SEEN, 'true');
            setTimeout(() => {
                if (!tutorialCompleted) window.showTutorial();
            }, 2500);
        }
    }

    initializeSplashScreen();
    
    const userInputField = document.getElementById('userInput');
    if (userInputField) {
        userInputField.addEventListener('input', () => {
            lastUserActivity = Date.now();
            window.lastUserActivity = lastUserActivity;
        });
        
        userInputField.addEventListener('focus', () => {
            lastUserActivity = Date.now();
            window.lastUserActivity = lastUserActivity;
        });
    }

    const contextInput = document.getElementById('contextPickerInput');
    const contextMenu = document.getElementById('contextDropdownMenu');
    
    if (contextInput && contextMenu) {
        contextInput.addEventListener('focus', () => {
            contextMenu.classList.add('active');
        });
        
        contextInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                window.addCustomContext();
            }
        });
        
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.context-dropdown')) {
                contextMenu.classList.remove('active');
            }
        });
    }

    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
    
    loadSettings();
    loadChats();
    loadMemory();
    initUniversalMemory();
    updateHeaderDisplay();
    setupVoiceRecognition();
    
    // Initialize engines
    messageDeduper = new window.MessageDeduplicator();
    contextEngine = new window.ContextAwarenessEngine();
    learningEngine = new window.LearningEngine();
    suggestionEngine = new window.ContextSuggestionEngine();
    autonomousEngine = new window.AutonomousMessageEngine();
    
    window.messageDeduper = messageDeduper;
    window.contextEngine = contextEngine;
    window.learningEngine = learningEngine;
    window.suggestionEngine = suggestionEngine;
    window.autonomousEngine = autonomousEngine;
    
    console.log('🧠 Learning Engine initialized', learningEngine.getLearningStats());
    console.log('💡 Suggestion Engine initialized');
    
    contextEngine.renderContextCards();
    
    if (contextEngine.contexts.length > 0) {
        setTimeout(() => {
            contextEngine.showContinueBanner();
        }, 1000);
    }
    
    if (chats.length === 0) {
        createNewChat();
    } else {
        loadChat(chats[0].id);
    }
});

// ==========================================
// SMART WELCOME SYSTEM
// ==========================================
function getSmartWelcome() {
    const memory = getUniversalMemory();
    const lastInteraction = memory.conversationHistory.lastInteraction;
    const hour = new Date().getHours();
    
    let timeConcern = '';
    if (hour >= 22 || hour < 5) {
        timeConcern = ' You\'re up late—everything alright?';
    } else if (hour >= 5 && hour < 7) {
        timeConcern = ' Early start today. Coffee ready?';
    }
    
    if (!lastInteraction) {
        return getTimeBasedGreeting() + timeConcern + " What's first?";
    }
    
    const now = new Date();
    const lastVisit = new Date(lastInteraction);
    const hoursSince = (now - lastVisit) / (1000 * 60 * 60);
    
    if (hoursSince < 4) {
        return welcomeMessages[Math.floor(Math.random() * welcomeMessages.length)] + timeConcern;
    }
    
    const lastTopic = getLastConversationTopic();
    const greeting = getTimeBasedGreeting();
    
    if (lastTopic) {
        return `${greeting}${timeConcern} Last time we were ${lastTopic}. Want to continue, or switch gears?`;
    } else {
        return `${greeting}${timeConcern} What's on the agenda today?`;
    }
}

function getTimeBasedGreeting() {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return "Good morning, Gregory.";
    if (hour >= 12 && hour < 17) return "Good afternoon.";
    if (hour >= 17 && hour < 22) return "Evening, Gregory.";
    return "Burning the midnight oil?";
}

function getLastConversationTopic() {
    if (chats.length === 0) return null;
    const lastChat = chats[0];
    if (!lastChat.messages || lastChat.messages.length < 2) return null;
    
    const userMessages = lastChat.messages
        .filter(m => m.role === 'user')
        .filter(m => !m.content.toLowerCase().includes('nova-secure'))
        .filter(m => !m.content.toLowerCase().includes('nala niobi'));
    
    if (userMessages.length === 0) return null;
    
    const lastUserMsg = userMessages[userMessages.length - 1].content;
    let topic = lastUserMsg.substring(0, 50).trim();
    
    if (topic.toLowerCase().startsWith('can you')) topic = topic.substring(7);
    else if (topic.toLowerCase().startsWith('could you')) topic = topic.substring(9);
    else if (topic.toLowerCase().startsWith('please')) topic = topic.substring(6);
    
    if (lastUserMsg.length > 50) topic += '...';
    return `working on: "${topic}"`;
}

function trackConversationTopic(message) {
    const memory = getUniversalMemory();
    const keywords = ['debug', 'fix', 'build', 'create', 'design', 'deploy', 'test', 'analyze'];
    const lowerMsg = message.toLowerCase();
    
    keywords.forEach(keyword => {
        if (lowerMsg.includes(keyword)) {
            if (!memory.conversationHistory.topicsDiscussed) {
                memory.conversationHistory.topicsDiscussed = [];
            }
            const recentTopics = memory.conversationHistory.topicsDiscussed.slice(-10);
            if (!recentTopics.includes(keyword)) {
                memory.conversationHistory.topicsDiscussed.push(keyword);
            }
        }
    });
    localStorage.setItem(STORAGE_KEYS.UNIVERSAL_MEMORY, JSON.stringify(memory));
}

// ==========================================
// CHAT MANAGEMENT
// ==========================================
function createNewChat() {
    const newChat = {
        id: Date.now().toString(),
        title: 'New Chat',
        messages: [],
        pinned: false,
        archived: false,
        tag: null,
        createdAt: new Date().toISOString()
    };
    chats.unshift(newChat);
    window.chats = chats;
    incrementChatCount();
    saveChats();
    loadChat(newChat.id);
    const welcomeMsg = getSmartWelcome();
    addMessage('assistant', welcomeMsg);
}

function loadChat(chatId) {
    currentChatId = chatId;
    window.currentChatId = chatId;
    localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, chatId);
    const chat = chats.find(c => c.id === chatId);
    if (chat) window.renderMessages(chat.messages);
    window.renderChatsList();
    if (window.innerWidth <= 768) {
        const sidebar = document.getElementById('sidebar');
        if (sidebar.classList.contains('active')) window.toggleSidebar();
    }
}

function loadChats() {
    const savedChats = localStorage.getItem(STORAGE_KEYS.CHATS);
    chats = savedChats ? JSON.parse(savedChats) : [];
    chats = chats.map(chat => ({
        ...chat,
        pinned: chat.pinned || false,
        archived: chat.archived || false,
        tag: chat.tag || null
    }));
    window.chats = chats;
    window.renderChatsList();
}

function saveChats() {
    localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(chats));
}

function deleteChat(chatId) {
    if (!confirm('Delete this chat? This cannot be undone.')) return;
    chats = chats.filter(c => c.id !== chatId);
    window.chats = chats;
    saveChats();
    if (chatId === currentChatId) {
        if (chats.length > 0) loadChat(chats[0].id);
        else createNewChat();
    }
    window.renderChatsList();
}

window.createNewChat = createNewChat;
window.loadChat = loadChat;
window.saveChats = saveChats;
window.deleteChat = deleteChat;

// ==========================================
// MESSAGE HANDLING
// ==========================================
function addMessage(role, content, imageUrl = null, fileData = null) {
    const chat = chats.find(c => c.id === currentChatId);
    if (!chat) return;
    
    const message = { role, content };
    if (imageUrl) message.imageUrl = imageUrl;
    if (fileData) message.fileData = fileData;
    chat.messages.push(message);
    
    if (role === 'user' && chat.messages.filter(m => m.role === 'user').length === 1) {
        chat.title = content.substring(0, CONFIG.MAX_TITLE_LENGTH) + (content.length > CONFIG.MAX_TITLE_LENGTH ? '...' : '');
    }
    
    saveChats();
    const container = document.getElementById('chatContainer');
    window.renderMessages(chat.messages);
    
    if (role === 'assistant') {
        requestAnimationFrame(() => {
            const lastMessage = container.querySelector('.message:last-child');
            if (lastMessage) lastMessage.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    } else {
        container.scrollTop = container.scrollHeight;
    }

    window.renderChatsList();
    if (role === 'assistant' && isAutoVoiceEnabled) window.speak(content);
    
    if (role === 'assistant') {
        lastAssistantMessage = { content, timestamp: Date.now() };
        
        const isError = content.toLowerCase().includes('error') || 
                       content.toLowerCase().includes('failed') ||
                       content.toLowerCase().includes('encountered an issue') ||
                       content.startsWith('I encountered');
        
        if (showConfidence && learningEngine && !isError) {
            const confidence = learningEngine.calculateConfidence('general', false);
            addConfidenceIndicator(chat.messages.length - 1, confidence);
        }
        
        if (metaCommentaryEnabled && learningEngine && !isError && content.length > 100) {
            setTimeout(() => {
                const confidence = learningEngine.calculateConfidence('general', false);
                const commentary = learningEngine.getMetaCommentary(content, confidence);
                addMetaCommentary(chat.messages.length - 1, commentary);
            }, 100);
        }
    }
    
    if (contextEngine) {
        contextEngine.trackMessage(role, content);
        
        if (role === 'assistant') {
            setTimeout(() => {
                const insight = contextEngine.generateInsight();
                if (insight) {
                    const insightEl = document.createElement('div');
                    insightEl.className = 'context-insight';
                    insightEl.innerHTML = `
                        <div class="context-insight-header">
                            <span>💡</span>
                            <span>Context Insight</span>
                        </div>
                        <div class="context-insight-text">${insight.text}</div>
                        <div class="context-insight-actions">
                            ${insight.actions.map(action => `
                                <button class="context-insight-action" onclick="this.closest('.context-insight').remove()">
                                    ${action}
                                </button>
                            `).join('')}
                        </div>
                    `;
                    container.appendChild(insightEl);
                    container.scrollTop = container.scrollHeight;
                }
            }, 500);
        }
    }
}

function addMetaCommentary(messageIndex, commentary) {
    const container = document.getElementById('chatContainer');
    const messages = container.querySelectorAll('.message');
    const targetMessage = messages[messageIndex];
    
    if (!targetMessage) return;
    
    const wrapper = targetMessage.querySelector('.message-wrapper');
    if (!wrapper) return;
    
    const existing = wrapper.querySelector('.meta-commentary');
    if (existing) existing.remove();
    
    const metaDiv = document.createElement('div');
    metaDiv.className = 'meta-commentary';
    metaDiv.style.cssText = `
        margin-top: 8px;
        padding: 12px;
        background: rgba(59, 130, 246, 0.1);
        border-left: 3px solid #3b82f6;
        border-radius: 8px;
        font-size: 12px;
        color: var(--text-secondary);
    `;
    
    metaDiv.innerHTML = `
        <div style="font-weight: 600; color: #3b82f6; margin-bottom: 6px; font-size: 11px;">🧠 REASONING PROCESS</div>
        <div style="margin-bottom: 4px;"><strong>Approach:</strong> ${commentary.approach}</div>
        <div style="margin-bottom: 4px;"><strong>Confidence:</strong> ${commentary.confidence}</div>
        ${commentary.alternatives.length > 0 ? `<div style="margin-top: 6px; font-size: 11px; font-style: italic;">💡 I could also: ${commentary.alternatives[0]}</div>` : ''}
    `;
    
    wrapper.appendChild(metaDiv);
}

function addConfidenceIndicator(messageIndex, confidence) {
    const container = document.getElementById('chatContainer');
    const messages = container.querySelectorAll('.message');
    const targetMessage = messages[messageIndex];
    
    if (!targetMessage) return;
    
    const wrapper = targetMessage.querySelector('.message-wrapper');
    if (!wrapper) return;
    
    const existing = wrapper.querySelector('.confidence-indicator');
    if (existing) existing.remove();
    
    const barColor = confidence.score >= 80 ? '#10b981' : 
                     confidence.score >= 65 ? '#3b82f6' : 
                     confidence.score >= 50 ? '#f59e0b' : '#ef4444';
    
    const indicator = document.createElement('div');
    indicator.className = 'confidence-indicator';
    indicator.style.cssText = `
        margin-top: 8px;
        padding: 8px 12px;
        background: rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.1);
    `;
    
    indicator.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
            <span style="font-size: 11px; font-weight: 600; color: var(--text-tertiary);">CONFIDENCE</span>
            <span style="font-size: 11px; font-weight: 700; color: ${barColor};">${confidence.level} (${confidence.score}%)</span>
        </div>
        <div style="width: 100%; height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden;">
            <div style="width: ${confidence.score}%; height: 100%; background: ${barColor}; transition: width 0.3s;"></div>
        </div>
        <div style="font-size: 10px; color: var(--text-tertiary); margin-top: 4px;">${confidence.reason}</div>
    `;
    
    wrapper.appendChild(indicator);
}

window.addMessage = addMessage;

// ==========================================
// REGENERATE RESPONSE
// ==========================================
async function regenerateResponse(index) {
    const chat = chats.find(c => c.id === currentChatId);
    if (!chat || index === 0) return;
    
    chat.messages = chat.messages.slice(0, index);
    saveChats();
    window.renderMessages(chat.messages);
    
    const lastUserMessage = chat.messages[chat.messages.length - 1];
    if (!lastUserMessage || lastUserMessage.role !== 'user') return;
    
    const message = lastUserMessage.content;
    const fileData = lastUserMessage.fileData;
    
    const memoryResponse = checkMemoryCommands(message);
    if (memoryResponse && !fileData) {
        window.showThinking();
        setTimeout(() => {
            window.hideThinking();
            addMessage('assistant', memoryResponse);
        }, 500);
        return;
    }
    
    const localResponse = getLocalResponse(message);
    if (localResponse && !fileData) {
        window.showThinking();
        setTimeout(() => {
            window.hideThinking();
            addMessage('assistant', localResponse);
        }, 800);
        return;
    }

    if (shouldGenerateImage(message) && !fileData) {
        await handleImageGeneration(message);
        return;
    }
    
    window.showThinking();
    try {
        const memoryContext = getMemoryContext();
        const response = await fetchWithTimeout('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message + memoryContext + getTimeAwareContext(),
                history: chat.messages.slice(-CONFIG.MAX_CHAT_HISTORY).filter(m => m.content && m.content.trim() !== ''),
                fileData: fileData || null,
                needsSearch: shouldSearchWeb(message),
                novaActive: isNovaActive(),
                novaProtocol: isNovaActive() ? getNovaProtocol() : null,
                universalMemory: getUniversalMemory()
            })
        });
        
        if (!response.ok) throw new Error('API request failed');
        const data = await response.json();
        window.hideThinking();

        addMessage('assistant', data.response);

        isSending = false;
        window.isSending = false;
        const input = document.getElementById('userInput');
        input.disabled = false;
        const sendBtn = document.querySelector('.icon-btn.primary');
        if (sendBtn) sendBtn.disabled = false;
        console.log('🔓 UNLOCKED (success)');

        if (learningEngine && Math.random() < 0.15) {
            const trainingRequest = learningEngine.getProactiveTrainingRequest();
            if (trainingRequest) {
                setTimeout(() => {
                    addMessage('assistant', trainingRequest);
                }, 2000);
            }
        }
        
    } catch (error) {
        window.hideThinking();
        addMessage('assistant', 'I encountered an error while regenerating. Please try again.');
        console.error('Regenerate error:', error);
    }
}

window.regenerateResponse = regenerateResponse;

// ==========================================
// SEND MESSAGE (CORE FUNCTION)
// ==========================================
function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        if (isSending) {
            console.log('⏸️ Already sending (Enter blocked)');
            return false;
        }
        sendMessage();
        return false;
    }
}

window.handleKeyPress = handleKeyPress;

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
    
    if (message && messageDeduper.isDuplicate(message)) {
        console.log('🚫 BLOCKED: Duplicate message');
        return;
    }
    
    isSending = true;
    window.isSending = true;
    console.log('🔒 SEND LOCKED at', Date.now());
    input.disabled = true;
    const sendBtn = document.querySelector('.icon-btn.primary');
    if (sendBtn) sendBtn.disabled = true;
    
    try {
        if (detectNovaActivation(message)) {
            activateNovaProtocol();
            input.value = '';
            window.showThinking();
            setTimeout(() => {
                window.hideThinking();
                addMessage('assistant', `⭐ **Nova-Secure Protocol Activated**\n\nHello Gregory. Full creator context loaded.\n\nI now have access to:\n- Complete project history (Nova Secure → Crump AI v2.11.0)\n- N² Engine context (Nala & Niobi)\n- Your communication preferences and working style\n- All persistent notes and technical context\n\nOperating in full creator mode. How can I assist you today?`);
                isSending = false;
                window.isSending = false;
                input.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
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
                isSending = false;
                window.isSending = false;
                input.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
            }, 800);
            return;
        }

        incrementMessageCount();
        if (message) trackConversationTopic(message);
        
        if (lastAssistantMessage && learningEngine) {
            const correctionDetection = learningEngine.detectCorrectionPattern(message, lastAssistantMessage.content);
            if (correctionDetection.isCorrection) {
                const correction = learningEngine.recordCorrection(
                    lastAssistantMessage.content,
                    message,
                    'general'
                );
                console.log('🎓 Correction detected and learned!', correction);
            }
            
            learningEngine.detectPreferenceFromMessage(message);
            
            const codePatterns = learningEngine.recognizePattern(message, 'code');
            if (codePatterns.length > 0) {
                console.log('🔍 Code patterns detected:', codePatterns);
            }
            
            const prefPatterns = learningEngine.recognizePattern(message, 'preference');
            if (prefPatterns.length > 0) {
                console.log('🎯 Preference patterns detected:', prefPatterns);
            }
            
            if (message.includes('```') && message.length > 100) {
                const style = learningEngine.learnCodingStyle(message);
                console.log('🎨 Coding style updated:', style);
            }
        }
        
        const imageText = currentFiles.length > 0
            ? (message || `📎 ${currentFiles.length} image${currentFiles.length > 1 ? 's' : ''}`)
            : message;

        addMessage('user', imageText, null, currentFiles.length > 0 ? currentFiles[0] : null);
        input.value = '';
        window.autoResize(input);

        const hasFile = currentFiles.length > 0;
        const fileDataToSend = currentFiles.length > 0 ? currentFiles : null;
        window.removeFile();
        
        const memoryResponse = checkMemoryCommands(message);
        if (memoryResponse && !hasFile) {
            window.showThinking();
            setTimeout(() => {
                window.hideThinking();
                addMessage('assistant', memoryResponse);
                isSending = false;
                window.isSending = false;
                input.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
            }, 500);
            return;
        }
        
        if (!hasFile) {
            const localResponse = getLocalResponse(message);
            if (localResponse) {
                window.showThinking();
                setTimeout(() => {
                    window.hideThinking();
                    addMessage('assistant', localResponse);
                    isSending = false;
                    window.isSending = false;
                    input.disabled = false;
                    if (sendBtn) sendBtn.disabled = false;
                }, 800);
                return;
            }

            if (shouldGenerateImage(message)) {
                await handleImageGeneration(message);
                isSending = false;
                window.isSending = false;
                input.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
                return;
            }
        }
        
        window.showThinking();
        
        const safetyTimeout = setTimeout(() => {
            if (isSending) {
                console.error('⚠️ SAFETY TIMEOUT: Force unlocking after 30s');
                window.hideThinking();
                isSending = false;
                window.isSending = false;
                input.disabled = false;
                const sendBtn = document.querySelector('.icon-btn.primary');
                if (sendBtn) sendBtn.disabled = false;
                addMessage('assistant', '⏱️ **Request Timeout**\n\nThe request took too long (30+ seconds). This usually means:\n\n• Server is overloaded\n• Network connection issues\n• Message is too complex\n\nPlease try again with a shorter message or check your connection.');
                window.showNotification('⏱️ Request timed out - interface unlocked', 'error');
            }
        }, 30000);
        
        const chat = chats.find(c => c.id === currentChatId);
        
        const contextBackup = {
            messages: [...chat.messages],
            activeContext: contextEngine.activeContext,
            chatTitle: chat.title
        };
        
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
                universalMemory: getUniversalMemory()
            })
        });
        
        if (!response.ok) throw new Error('API request failed');
        const data = await response.json();
        window.hideThinking();

       addMessage('assistant', data.response);

        clearTimeout(safetyTimeout);

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
        
        isSending = false;
        window.isSending = false;
        input.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        console.log('🔓 UNLOCKED (success)');
        
    } catch (error) {
        window.hideThinking();
        
        if (typeof safetyTimeout !== 'undefined') {
            clearTimeout(safetyTimeout);
        }
        
        enterErrorState();
        console.error('❌ SEND ERROR:', error);
        console.error('Error stack:', error.stack);

        isSending = false;
        window.isSending = false;
        input.disabled = false;
        const sendBtn = document.querySelector('.icon-btn.primary');
        if (sendBtn) sendBtn.disabled = false;
        console.log('🔓 FORCE UNLOCKED (error caught)');

        if (contextBackup && chat.messages.length !== contextBackup.messages.length) {
            console.log('🔧 Restoring context from backup');
            chat.messages = contextBackup.messages;
            saveChats();
        }
        
        let errorMsg = '⚠️ **Message Failed**\n\n';
        
        if (error.message?.includes('fetch') || error.message?.includes('Failed to fetch')) {
            errorMsg += '**Connection Error:** Cannot reach server.\n\n';
            errorMsg += '• Check your internet connection\n';
            errorMsg += '• Verify server status\n';
            errorMsg += '• Try refreshing the page\n\n';
        } else if (error.message?.includes('timeout') || error.message?.includes('timed out')) {
            errorMsg += '**Timeout Error:** Request took too long.\n\n';
            errorMsg += '• Message might be too complex\n';
            errorMsg += '• Try a shorter message\n';
            errorMsg += '• Check your connection speed\n\n';
        } else if (error.message?.includes('token') || error.message?.includes('too long')) {
            errorMsg += '**Message Too Long:** Exceeded character limit.\n\n';
            errorMsg += '• Break into smaller messages\n';
            errorMsg += '• Remove unnecessary content\n\n';
        } else if (error.message?.includes('429') || error.message?.includes('rate limit')) {
            errorMsg += '**Rate Limited:** Too many requests.\n\n';
            errorMsg += '• Wait 60 seconds and try again\n\n';
        } else {
            errorMsg += `**Unknown Error:** ${error.message || 'Something went wrong'}\n\n`;
            errorMsg += 'Debug info:\n';
            errorMsg += `• Error type: ${error.name}\n`;
            errorMsg += `• Time: ${new Date().toLocaleTimeString()}\n\n`;
        }
        
        errorMsg += '🔄 **Your message is preserved.** Just hit send again when ready.';
        
        addMessage('assistant', errorMsg);
        window.showNotification('❌ Message failed - check details above', 'error');
    }
}

window.sendMessage = sendMessage;

// ==========================================
// LOCAL RESPONSES
// ==========================================
function getLocalResponse(message) {
    const lower = message.toLowerCase();
    if (lower.includes('who are you') || lower.includes('what are you')) {
        return "I'm Crump, your personal AI assistant powered by the N² Engine. I handle everything from technical work to creative projects with precision and intelligence. I was built by Gregory D. Crump Jr. to be helpful, direct, and professional.";
    }
    if (lower.includes('who am i') || lower.includes('who is gregory')) {
        return "You're the architect behind this system. The one who built Crump AI from scratch.";
    }
    if (lower.includes('what is crump') || lower.includes('what is the n')) {
        return "Crump AI is a premium, royal-branded personal AI assistant powered by the N² Engine, which enables me to handle technical, creative, and analytical tasks seamlessly.";
    }
    if (lower.includes('who built you') || lower.includes('who created you')) {
        return "I was built by Gregory D. Crump Jr., an artist and innovator who created me to be a powerful yet personal AI assistant.";
    }
    if (lower.includes('what can you do') || lower.includes('your capabilities')) {
        return "I can help you with:\n\n• Technical problems (debugging, code, algorithms)\n• Creative writing (stories, content, ideas)\n• Analysis and research\n• Voice conversations (speak to me!)\n• Image generation (just ask me to create an image)\n• Image analysis (upload any image and ask questions!)\n• Memory - I can remember important information about you\n• Multi-threaded conversations\n• Autonomous suggestions - I learn your patterns!\n• Self-improvement through training and corrections\n\n**Learning Commands:**\n• 'Remember that...' - Store information\n• 'Explain your reasoning' - See my thought process\n• 'Train me on X' - Interactive training\n• 'Show learning history' - View improvement timeline\n• 'Verify knowledge on X' - Test my understanding";
    }
    return null;
}

function shouldSearchWeb(message) {
    const lower = message.toLowerCase().trim();
    
    if (lower.includes('search for') || 
        lower.includes('look up') || 
        lower.includes('find information about') ||
        lower.startsWith('google ')) {
        return true;
    }
    
    if (message.split(' ').length < 4) {
        return false;
    }
    
    const realtimeKeywords = [
        'current weather', 'today\'s weather',
        'stock price', 'latest news',
        'current score', 'live score',
        'right now', 'as of today'
    ];
    if (realtimeKeywords.some(keyword => lower.includes(keyword))) {
        return true;
    }
    
    const timeIndicators = ['today', 'now', 'current', 'latest', 'recent', 'this week', 'this month'];
    const factualWords = ['what', 'who', 'when', 'where', 'how many', 'is there'];
    
    const hasTime = timeIndicators.some(t => lower.includes(t));
    const hasFactual = factualWords.some(f => lower.includes(f));
    
    return hasTime && hasFactual;
}

// ==========================================
// MEMORY SYSTEM
// ==========================================
function loadMemory() {
    const savedMemory = localStorage.getItem(STORAGE_KEYS.USER_MEMORY);
    if (savedMemory) {
        userMemory = JSON.parse(savedMemory);
        window.userMemory = userMemory;
    }
}

function saveMemory() {
    localStorage.setItem(STORAGE_KEYS.USER_MEMORY, JSON.stringify(userMemory));
}

window.saveMemory = saveMemory;

function checkMemoryCommands(message) {
    const lower = message.toLowerCase();
    
    if (lower.startsWith('remember that')) {
        const content = message.substring(message.indexOf('that') + 4).trim();
        if (content) {
            userMemory.notes.push({ content, timestamp: new Date().toISOString() });
            saveMemory();
            addCrossSessionContext(content);
            return `Got it. I'll remember: "${content}" (stored in both session and permanent memory)`;
        }
    }
    
    if (lower.startsWith('remember:')) {
        const content = message.substring(message.indexOf(':') + 1).trim();
        if (content) {
            userMemory.notes.push({ content, timestamp: new Date().toISOString() });
            saveMemory();
            addCrossSessionContext(content);
            return `Got it. I'll remember: "${content}" (stored in both session and permanent memory)`;
        }
    }
    
    if (lower.includes('what do you remember') || lower.includes('what do you know about me')) {
        if (userMemory.notes.length === 0 && Object.keys(userMemory.preferences).length === 0 && Object.keys(userMemory.contexts).length === 0) {
            return "I don't have any stored memories about you yet. You can tell me to remember things by saying 'Remember that...'";
        }
        let response = "Here's what I remember:\n\n";
        if (userMemory.notes.length > 0) {
            response += "📝 Notes:\n";
            userMemory.notes.forEach((note, i) => response += `${i + 1}. ${note.content}\n`);
        }
        if (Object.keys(userMemory.preferences).length > 0) {
            response += "\n⚙️ Preferences:\n";
            Object.entries(userMemory.preferences).forEach(([key, value]) => response += `• ${key}: ${value}\n`);
        }
        if (Object.keys(userMemory.contexts).length > 0) {
            response += "\n🎯 Context:\n";
            Object.entries(userMemory.contexts).forEach(([key, value]) => response += `• ${key}: ${value}\n`);
        }
        return response;
    }
    
    if (lower.startsWith('forget that') || lower.startsWith('forget:')) {
        const content = message.substring(message.indexOf('that') + 4).trim() || message.substring(message.indexOf(':') + 1).trim();
        const originalLength = userMemory.notes.length;
        userMemory.notes = userMemory.notes.filter(note => !note.content.toLowerCase().includes(content.toLowerCase()));
        if (userMemory.notes.length < originalLength) {
            saveMemory();
            return `I've forgotten that information.`;
        }
        return `I couldn't find that in my memory.`;
    }
    
    if (lower === 'clear memory' || lower === 'forget everything') {
        if (confirm('Clear all stored memories? This cannot be undone.')) {
            userMemory = { preferences: {}, contexts: {}, notes: [] };
            window.userMemory = userMemory;
            saveMemory();
            return "All memories cleared.";
        }
        return "Memory clear cancelled.";
    }
    
    if (lower === 'explain your reasoning' || lower === 'why did you say that' || lower === 'explain that' || lower === 'how did you decide') {
        if (!lastAssistantMessage || !learningEngine) {
            return "I don't have a recent response to explain. Ask me something first!";
        }
        
        const confidence = learningEngine.calculateConfidence('general', false);
        const commentary = learningEngine.getMetaCommentary(lastAssistantMessage.content, confidence);
        
        return `🧠 **META-COMMENTARY: My Reasoning Process**\n\n**Approach:**\n${commentary.approach}\n\n**Confidence:**\n${commentary.confidence}\n\n**Sources:**\n${commentary.sources.map((s, i) => `${i + 1}. ${s}`).join('\n')}\n\n${commentary.alternatives.length > 0 ? `**Alternative Approaches:**\n${commentary.alternatives.map((a, i) => `${i + 1}. ${a}`).join('\n')}` : ''}`;
    }
    
    if (lower.startsWith('train me on') || lower.startsWith('teach me about')) {
        const topic = lower.replace('train me on', '').replace('teach me about', '').trim();
        if (!topic) {
            return "What topic would you like me to train you on? Say 'train me on [topic]' or 'teach me about [topic]'.";
        }
        
        trainingSession = learningEngine.startTrainingSession(topic);
        return `🎓 **Training Session Started: ${topic}**\n\nI'll ask you questions to test your knowledge. Answer honestly, and I'll track your progress!\n\nReady for the first question?\n\n**Q1:** Can you explain what ${topic} is in your own words?`;
    }
    
    if (lower === 'end training' || lower === 'stop training') {
        if (!trainingSession || !trainingSession.active) {
            return "No active training session to end.";
        }
        
        const results = learningEngine.endTrainingSession(trainingSession);
        const accuracy = results.correctAnswers / results.questionsAsked;
        const grade = accuracy >= 0.9 ? 'A' : accuracy >= 0.8 ? 'B' : accuracy >= 0.7 ? 'C' : accuracy >= 0.6 ? 'D' : 'F';
        
        trainingSession = null;
        
        return `🎓 **Training Session Complete!**\n\n**Topic:** ${results.topic}\n**Duration:** ${results.duration} seconds\n**Questions:** ${results.questionsAsked}\n**Correct:** ${results.correctAnswers}\n**Accuracy:** ${Math.round(accuracy * 100)}%\n**Grade:** ${grade}\n\n${accuracy >= 0.7 ? '✅ Great job! This topic has been marked as learned.' : '📚 Keep practicing! You can retry this training anytime.'}`;
    }
    
    if (lower === 'show learning history' || lower === 'learning timeline' || lower === 'my learning history') {
        if (!learningEngine) {
            return "Learning engine not initialized.";
        }
        
        const history = learningEngine.getLearningHistory();
        if (history.length === 0) {
            return "No learning history yet. Start correcting me or doing training sessions to build your history!";
        }
        
        let response = '📚 **Learning History Timeline**\n\n';
        history.forEach(event => {
            const date = new Date(event.timestamp).toLocaleDateString();
            response += `${event.icon} **${date}** - ${event.description}\n`;
        });
        
        return response;
    }
    
    if (lower.startsWith('verify knowledge on') || lower.startsWith('test knowledge on')) {
        const topic = lower.replace('verify knowledge on', '').replace('test knowledge on', '').trim();
        if (!topic) {
            return "What topic would you like me to verify my knowledge on?";
        }
        
        const verification = learningEngine.verifyKnowledge(topic);
        
        let response = `🔍 **Knowledge Verification: ${topic}**\n\n`;
        
        if (verification.verified) {
            response += `✅ **Status: VERIFIED**\n\n`;
            response += `I have solid knowledge on this topic:\n`;
            response += `• Completed training with ${verification.trainingAccuracy}% accuracy\n`;
            response += `• No recent corrections needed\n\n`;
            response += `I'm confident in my understanding of ${topic}!`;
        } else if (verification.hasTraining && !verification.hasCorrections) {
            response += `✓ **Status: GOOD**\n\n`;
            response += `• Completed training with ${verification.trainingAccuracy}% accuracy\n`;
            response += `• Minor corrections: ${verification.correctionCount}\n\n`;
            response += `My knowledge is solid, with room for improvement.`;
        } else if (verification.hasCorrections) {
            response += `⚠️ **Status: NEEDS IMPROVEMENT**\n\n`;
            response += `• Corrections received: ${verification.correctionCount}\n`;
            if (verification.hasTraining) {
                response += `• Training completed: ${verification.trainingAccuracy}% accuracy\n`;
            } else {
                response += `• No formal training yet\n`;
            }
            response += `\nWould you like to train me on ${topic} to improve my knowledge?`;
        } else {
            response += `❓ **Status: UNKNOWN**\n\n`;
            response += `I don't have any training or corrections on this topic yet.\n\n`;
            response += `Say "train me on ${topic}" to help me learn!`;
        }
        
        return response;
    }
    
    return null;
}

function getMemoryContext() {
    if (userMemory.notes.length === 0 && Object.keys(userMemory.preferences).length === 0 && Object.keys(userMemory.contexts).length === 0) return '';
    let context = '\n\n[Context about user: ';
    if (userMemory.notes.length > 0) context += userMemory.notes.map(n => n.content).join('; ');
    if (Object.keys(userMemory.preferences).length > 0) {
        context += '. Preferences: ' + Object.entries(userMemory.preferences).map(([k,v]) => `${k}=${v}`).join(', ');
    }
    if (Object.keys(userMemory.contexts).length > 0) {
        context += '. ' + Object.entries(userMemory.contexts).map(([k,v]) => `${k}: ${v}`).join(', ');
    }
    context += ']';
    return context;
}

// ==========================================
// UNIVERSAL MEMORY
// ==========================================
function initUniversalMemory() {
    const existing = localStorage.getItem(STORAGE_KEYS.UNIVERSAL_MEMORY);
    if (existing) return JSON.parse(existing);
    const memory = {
        userProfile: { assistantName: 'Crump', name: null, communicationStyle: "adaptive", preferences: {}, interests: [], learnedContext: [] },
        conversationHistory: { totalMessages: 0, totalChats: 0, topicsDiscussed: [], commonRequests: [], lastInteraction: null, firstInteraction: new Date().toISOString() },
        crossSessionContext: []
    };
    localStorage.setItem(STORAGE_KEYS.UNIVERSAL_MEMORY, JSON.stringify(memory));
    return memory;
}

function getUniversalMemory() {
    const memory = localStorage.getItem(STORAGE_KEYS.UNIVERSAL_MEMORY);
    return memory ? JSON.parse(memory) : initUniversalMemory();
}

function addCrossSessionContext(context) {
    const memory = getUniversalMemory();
    memory.crossSessionContext.push({ timestamp: new Date().toISOString(), content: context });
    if (memory.crossSessionContext.length > CONFIG.MAX_CROSS_SESSION_NOTES) {
        memory.crossSessionContext = memory.crossSessionContext.slice(-CONFIG.MAX_CROSS_SESSION_NOTES);
    }
    localStorage.setItem(STORAGE_KEYS.UNIVERSAL_MEMORY, JSON.stringify(memory));
}

function incrementMessageCount() {
    const memory = getUniversalMemory();
    memory.conversationHistory.totalMessages++;
    memory.conversationHistory.lastInteraction = new Date().toISOString();
    localStorage.setItem(STORAGE_KEYS.UNIVERSAL_MEMORY, JSON.stringify(memory));
}

function incrementChatCount() {
    const memory = getUniversalMemory();
    memory.conversationHistory.totalChats++;
    localStorage.setItem(STORAGE_KEYS.UNIVERSAL_MEMORY, JSON.stringify(memory));
}

window.getUniversalMemory = getUniversalMemory;
window.initUniversalMemory = initUniversalMemory;

// ==========================================
// ASSISTANT NAME
// ==========================================
function getAssistantName() {
    return getUniversalMemory().userProfile.assistantName || 'Crump';
}

function setAssistantName(name) {
    const memory = getUniversalMemory();
    memory.userProfile.assistantName = name.trim();
    localStorage.setItem(STORAGE_KEYS.UNIVERSAL_MEMORY, JSON.stringify(memory));
    updateHeaderDisplay();
}

function resetAssistantName() {
    const memory = getUniversalMemory();
    memory.userProfile.assistantName = 'Crump';
    localStorage.setItem(STORAGE_KEYS.UNIVERSAL_MEMORY, JSON.stringify(memory));
    updateHeaderDisplay();
    const input = document.getElementById('assistant-name-input');
    if (input) input.value = 'Crump';
    const resetBtn = document.getElementById('reset-name-btn');
    if (resetBtn) resetBtn.style.display = 'none';
    window.showNotification('✓ Assistant name reset to Crump', 'success');
}

function saveAssistantName() {
    const input = document.getElementById('assistant-name-input');
    const name = input.value.trim();
    if (!name) { alert('Please enter a name'); return; }
    if (name.length > 20) { alert('Name must be 20 characters or less'); return; }
    setAssistantName(name);
    const button = event.target;
    const originalText = button.textContent;
    button.textContent = '✓ Saved';
    button.style.background = '#2d8659';
    const resetBtn = document.getElementById('reset-name-btn');
    if (resetBtn) resetBtn.style.display = name !== 'Crump' ? 'block' : 'none';
    setTimeout(() => {
        button.textContent = originalText;
        button.style.background = '#d4af37';
    }, 1500);
}

function updateHeaderDisplay() {
    const name = getAssistantName();
    const novaActive = isNovaActive();
    const icon = novaActive ? '⭐' : '👑';
    const iconStyle = novaActive ? 'font-size: 20px; filter: drop-shadow(0 0 8px #d4af37);' : 'font-size: 20px;';
    
    const headerLogoText = document.querySelector('.header .logo-text');
    if (headerLogoText) {
        const isMobile = window.innerWidth < 500;
        if (isMobile) {
            headerLogoText.innerHTML = `<span style="${iconStyle}">${icon}</span> ${name}`;
        } else {
            headerLogoText.innerHTML = `<span style="${iconStyle}">${icon}</span> ${name} <span style="font-size: 14px; color: #b8941f;">· N² Engine</span>`;
        }
    }
    
    const sidebarLogoText = document.querySelector('.sidebar .logo-text');
    if (sidebarLogoText) {
        sidebarLogoText.textContent = `${name} · N² Engine`;
    }
}

window.addEventListener('resize', updateHeaderDisplay);
window.getAssistantName = getAssistantName;
window.setAssistantName = setAssistantName;
window.resetAssistantName = resetAssistantName;
window.saveAssistantName = saveAssistantName;
window.updateHeaderDisplay = updateHeaderDisplay;

// ==========================================
// NOVA PROTOCOL
// ==========================================
function detectNovaActivation(message) {
    const t = message.trim().toLowerCase();
    return t === 'activate nova-secure' || t === 'nova-secure' || t === 'activate nala niobi protocol' || t === 'nala niobi protocol';
}

function detectNovaDeactivation(message) {
    const t = message.trim().toLowerCase();
    return t === 'deactivate nova-secure' || t === 'deactivate nala niobi protocol' || t === 'end protocol' || t === 'nova-secure off';
}

function initNovaProtocol() {
    const existing = localStorage.getItem(STORAGE_KEYS.NOVA_PROTOCOL);
    if (existing) return JSON.parse(existing);
    return {
        active: false, activations: [],
        gregoryContext: {
            identity: { name: "Gregory D. Crump Jr.", role: "Creator and Lead Developer", relationship: "Technical partner and collaborator" },
            projectHistory: { currentProject: "Crump AI v2.11.0 Royal Edition", previousProjects: ["Nova Secure (renamed to Crump AI)"], startDate: "October 14, 2025", deploymentUrl: "crumpai.vercel.app" },
            engineDetails: { name: "N² Engine", meaning: "Named after daughters Nala and Niobi", originalName: "Nova (stellar explosion/new star)", models: "Claude Sonnet 4.5 (technical) + GPT-4 (creative)" },
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
// IMAGE HANDLING
// ==========================================
function shouldGenerateImage(message) {
    const lower = message.toLowerCase();
    const imageKeywords = ['generate', 'create', 'make', 'draw', 'design', 'show me'];
    const imageNouns = ['image', 'picture', 'photo', 'illustration', 'artwork', 'drawing'];
    return imageKeywords.some(k => lower.includes(k)) && imageNouns.some(n => lower.includes(n));
}

async function generateImageWithSegmind(prompt) {
    const encodedPrompt = encodeURIComponent(prompt);
    const timestamp = Date.now();
    const imageUrl = `https://api.segmind.com/v1/sd1.5-txt2img?prompt=${encodedPrompt}&seed=${timestamp}&samples=1&scheduler=UniPC&num_inference_steps=25&guidance_scale=7.5&height=512&width=512`;
    return imageUrl;
}

function extractImagePrompt(message) {
    let prompt = message;
    const prefixes = ['generate an image of', 'create an image of', 'make an image of', 'draw an image of', 'show me an image of', 'generate a picture of', 'create a picture of', 'make a picture of', 'draw a picture of', 'show me a picture of', 'generate', 'create', 'make', 'draw', 'show me'];
    for (const prefix of prefixes) {
        if (prompt.toLowerCase().startsWith(prefix)) {
            prompt = prompt.substring(prefix.length).trim();
            break;
        }
    }
    return prompt;
}

async function handleImageGeneration(message, retryCount = 0) {
    const prompt = extractImagePrompt(message);
    window.showThinking();
    
    try {
        let imageUrl;
        let generatorName;
        
        if (preferredImageGenerator === 'segmind') {
            imageUrl = await generateImageWithSegmind(prompt);
            generatorName = 'Segmind';
        } else {
            const timestamp = Date.now();
            const encodedPrompt = encodeURIComponent(prompt);
            imageUrl = `https://image.pollinations.ai/prompt/${encodedPrompt}?width=1024&height=1024&seed=${timestamp}&nologo=true&enhance=true&model=flux`;
            generatorName = 'Pollinations';
        }
        
        const img = new Image();
        img.onload = () => {
            window.hideThinking();
            addMessage('assistant', `Here's your image based on: "${prompt}" (Generated with ${generatorName})`, imageUrl);
        };
        
        img.onerror = () => {
            console.log(`${generatorName} failed, trying alternate generator...`);
            
            let fallbackUrl;
            let fallbackName;
            
            if (preferredImageGenerator === 'segmind') {
                const timestamp = Date.now();
                const encodedPrompt = encodeURIComponent(prompt);
                fallbackUrl = `https://image.pollinations.ai/prompt/${encodedPrompt}?width=1024&height=1024&seed=${timestamp}&nologo=true&enhance=true&model=flux`;
                fallbackName = 'Pollinations';
            } else {
                fallbackUrl = generateImageWithSegmind(prompt);
                fallbackName = 'Segmind';
            }
            
            const fallbackImg = new Image();
            fallbackImg.onload = () => {
                window.hideThinking();
                addMessage('assistant', `Here's your image based on: "${prompt}" (Generated with ${fallbackName} - backup generator)`, fallbackUrl);
            };
            fallbackImg.onerror = () => {
                window.hideThinking();
                addMessage('assistant', `I encountered an error with both image generators. Please try again in a moment.`);
            };
            fallbackImg.src = fallbackUrl;
        };
        
        img.src = imageUrl;
        
    } catch (error) {
        window.hideThinking();
        addMessage('assistant', `Error generating image: ${error.message}`);
        console.error('Image generation error:', error);
    }
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
            window.updateVoiceButton();
        };
        recognition.onerror = (event) => {
            isListening = false;
            window.isListening = false;
            window.updateVoiceButton();
            if (event.error !== 'no-speech' && event.error !== 'aborted') {
                window.showNotification('Voice error: ' + event.error, 'error');
            }
        };
        recognition.onend = () => {
            isListening = false;
            window.isListening = false;
            window.updateVoiceButton();
        };
    }
}

// ==========================================
// SETTINGS LOADING
// ==========================================
function loadSettings() {
    const voiceOutput = localStorage.getItem(STORAGE_KEYS.VOICE_OUTPUT) === 'true';
    const autoVoice = localStorage.getItem(STORAGE_KEYS.AUTO_VOICE) === 'true';
    const autonomousMessages = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_MESSAGES) === 'true';
    const autonomousInterval = localStorage.getItem(STORAGE_KEYS.AUTONOMOUS_INTERVAL) || 'balanced';
    const imageGenerator = localStorage.getItem(STORAGE_KEYS.IMAGE_GENERATOR) || 'pollinations';
    const showConfidenceSetting = localStorage.getItem(STORAGE_KEYS.SHOW_CONFIDENCE) === 'true';
    const metaCommentarySetting = localStorage.getItem(STORAGE_KEYS.META_COMMENTARY) === 'true';
    const fontStyle = localStorage.getItem(STORAGE_KEYS.FONT_STYLE) || 'modern';
    const bgColor = localStorage.getItem(STORAGE_KEYS.BG_COLOR) || '#0a1628';
    
    document.getElementById('voiceToggle').checked = voiceOutput;
    document.getElementById('autoVoiceToggle').checked = autoVoice;
    document.getElementById('autonomousToggle').checked = autonomousMessages;
    document.getElementById('confidenceToggle').checked = showConfidenceSetting;
    document.getElementById('metaToggle').checked = metaCommentarySetting;
    
    showConfidence = showConfidenceSetting;
    window.showConfidence = showConfidence;
    metaCommentaryEnabled = metaCommentarySetting;
    window.metaCommentaryEnabled = metaCommentaryEnabled;
    
    autonomousEngine.setIntervalPreset(autonomousInterval);
    if (autonomousMessages) {
        document.getElementById('autonomous-interval-settings').style.display = 'block';
    }
    document.getElementById('interval-relaxed').classList.remove('active');
    document.getElementById('interval-balanced').classList.remove('active');
    document.getElementById('interval-active').classList.remove('active');
    document.getElementById('interval-very-active').classList.remove('active');
    document.getElementById(`interval-${autonomousInterval}`).classList.add('active');
    
    preferredImageGenerator = imageGenerator;
    window.preferredImageGenerator = imageGenerator;
    if (imageGenerator === 'segmind') {
        document.getElementById('genPollinations').classList.remove('active');
        document.getElementById('genSegmind').classList.add('active');
    }
    isVoiceEnabled = voiceOutput;
    window.isVoiceEnabled = voiceOutput;
    isAutoVoiceEnabled = autoVoice;
    window.isAutoVoiceEnabled = autoVoice;
    autonomousMessagesEnabled = autonomousMessages;
    window.autonomousMessagesEnabled = autonomousMessages;
    
    if (autonomousMessages) {
        autonomousEngine.start();
    }
    
    loadFeatureReminders();
    loadContextSuggestions();
    
    window.changeFont(fontStyle);
    window.changeBgColor(bgColor);
}

window.loadSettings = loadSettings;

// Add notification style
const notificationStyle = document.createElement('style');
notificationStyle.textContent = `@keyframes slideInNotification{from{transform:translateX(400px);opacity:0;}to{transform:translateX(0);opacity:1;}}@keyframes slideOutNotification{from{transform:translateX(0);opacity:1;}to{transform:translateX(400px);opacity:0;}}`;
document.head.appendChild(notificationStyle);

console.log('✅ Core module loaded');
