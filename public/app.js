// ==========================================
// CONFIGURATION CONSTANTS - FIXED
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

// ==========================================
// FIX #2: ERROR STATE MANAGEMENT
// ==========================================
let isInErrorState = false;
let lastErrorTime = 0;
let errorCooldownMs = 30000;

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

// ==========================================
// FIX #3: TIME/DATE AWARENESS FOR CRUMP
// ==========================================
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
        context += `⚠️ It's ${time.formattedTime} - Gregory is up VERY la
