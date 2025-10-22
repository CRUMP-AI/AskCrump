// ==========================================
// CRUMP AI - CORE FIXES v2.12.0
// CRITICAL PATCHES FOR app.js (core module)
// ==========================================

/*
 * APPLY THESE CHANGES TO YOUR EXISTING app.js FILE
 * 
 * This file contains all the critical fixes:
 * 1. Chat restoration on refresh
 * 2. Profile manager integration
 * 3. Improved timeout handling
 * 4. Better error messages
 */

// ==========================================
// FIX #1: ADD TIMEOUT CONFIGURATION
// ==========================================
// ADD THIS AT THE TOP WITH OTHER CONFIG (around line 9-16)

const TIMEOUT_CONFIG = {
    API_REQUEST: 65000,        // 65s (5s buffer over backend)
    WARNING_TIME: 30000,       // Show warning after 30s
    PROGRESS_INTERVAL: 5000    // Update progress every 5s
};

window.TIMEOUT_CONFIG = TIMEOUT_CONFIG;


// ==========================================
// FIX #2: INITIALIZE PROFILE MANAGER
// ==========================================
// IN DOMContentLoaded (around line 598-612), ADD THIS AFTER setupVoiceRecognition():

    // Initialize Profile Manager
    profileManager = new window.UserProfileManager();
    window.profileManager = profileManager;
    console.log('👤 Profile Manager initialized:', profileManager.getTierInfo());
    
    // Update UI with tier info
    updateTierDisplay();


// ==========================================
// FIX #3: FIX CHAT RESTORATION ON REFRESH
// ==========================================
// REPLACE THIS CODE (lines 624-628):

/*
OLD CODE:
    if (chats.length === 0) {
        createNewChat();
    } else {
        loadChat(chats[0].id);
    }
*/

// NEW CODE:
    if (chats.length === 0) {
        createNewChat();
    } else {
        // ✅ FIX: Load last active chat, not first
        const lastChatId = localStorage.getItem(STORAGE_KEYS.CURRENT_CHAT);
        
        if (lastChatId && chats.find(c => c.id === lastChatId)) {
            // Load the chat user was on
            loadChat(lastChatId);
            console.log('✅ Restored last active chat:', lastChatId);
        } else {
            // Fallback to most recent chat (first in array)
            loadChat(chats[0].id);
            console.log('ℹ️ Loading most recent chat');
        }
    }


// ==========================================
// FIX #4: UPDATE loadChat TO SAVE CURRENT CHAT
// ==========================================
// MODIFY THE loadChat FUNCTION (around line 740), ADD THIS LINE:

function loadChat(chatId) {
    const chat = chats.find(c => c.id === chatId);
    if (!chat) return;
    
    currentChatId = chatId;
    window.currentChatId = chatId;
    
    // ✅ ADD THIS LINE TO SAVE CURRENT CHAT FOR RESTORATION
    localStorage.setItem(STORAGE_KEYS.CURRENT_CHAT, chatId);
    
    window.renderMessages(chat.messages);
    window.renderChatsList();
    updateHeaderDisplay();
    
    if (contextEngine) {
        contextEngine.loadChatContext(chatId);
    }
}


// ==========================================
// FIX #5: IMPROVED TIMEOUT HANDLING
// ==========================================
// REPLACE THE sendMessage FUNCTION (lines 1061-1370) WITH THIS IMPROVED VERSION:

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

    // ============================================
    // CHECK TIER LIMITS
    // ============================================
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

    // ============================================
    // UNIFIED UNLOCK FUNCTION
    // ============================================
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
                addMessage('assistant', `⭐ **Nova-Secure Protocol Activated**\n\nHello Gregory. Full creator context loaded.\n\nI now have access to:\n- Complete project history (Nova Secure → Crump AI v2.11.0)\n- N² Engine context (Nala & Niobi)\n- Your communication preferences and working style\n- All persistent notes and technical context\n\nOperating in full creator mode. How can I assist you today?`);
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

        incrementMessageCount();
        if (message) trackConversationTopic(message);
        
        // Learning engine processing
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
            ? (message || `📎 ${currentFiles.length} file${currentFiles.length > 1 ? 's' : ''}`)
            : message;

        addMessage('user', imageText, null, currentFiles.length > 0 ? currentFiles[0] : null);
        input.value = '';
        window.autoResize(input);

        const hasFile = currentFiles.length > 0;
        const fileDataToSend = currentFiles.length > 0 ? currentFiles : null;
        window.removeFile();
        
        // Check memory commands
        const memoryResponse = checkMemoryCommands(message);
        if (memoryResponse && !hasFile) {
            window.showThinking();
            setTimeout(() => {
                window.hideThinking();
                addMessage('assistant', memoryResponse);
                unlockUI();
            }, 500);
            return;
        }
        
        // Check local responses
        if (!hasFile) {
            const localResponse = getLocalResponse(message);
            if (localResponse) {
                window.showThinking();
                setTimeout(() => {
                    window.hideThinking();
                    addMessage('assistant', localResponse);
                    unlockUI();
                }, 800);
                return;
            }

            // Check for image generation
            if (shouldGenerateImage(message)) {
                await handleImageGeneration(message);
                unlockUI();
                return;
            }
        }
        
        // Show thinking with progressive timeout
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


// ==========================================
// FIX #6: ADD PROGRESSIVE TIMEOUT INDICATOR
// ==========================================
// ADD THIS NEW FUNCTION AFTER sendMessage:

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


// ==========================================
// FIX #7: BETTER ERROR HANDLING
// ==========================================
// ADD THIS NEW FUNCTION AFTER clearProgressiveTimeout:

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


// ==========================================
// FIX #8: ADD TIER DISPLAY FUNCTION
// ==========================================
// ADD THIS NEW FUNCTION AT THE END OF THE FILE:

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
window.showProgressiveTimeout = showProgressiveTimeout;
window.clearProgressiveTimeout = clearProgressiveTimeout;
window.handleSendError = handleSendError;

console.log('✅ Core fixes applied');
