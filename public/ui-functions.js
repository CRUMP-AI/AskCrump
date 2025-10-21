// ==========================================
// CRUMP AI - UI FUNCTIONS MODULE
// v2.11.0 - Extracted for Vercel optimization
// ==========================================

// ==========================================
// TUTORIAL FUNCTIONS
// ==========================================
function showTutorial() {
    window.currentTutorialStep = 1;
    updateTutorialContent();
    document.getElementById('tutorial-overlay').classList.add('active');
}

function updateTutorialContent() {
    const step = window.tutorialSteps[window.currentTutorialStep - 1];
    const body = document.getElementById('tutorialBody');
    const stepIndicator = document.getElementById('tutorialStep');
    
    stepIndicator.textContent = `Step ${window.currentTutorialStep} of ${window.tutorialSteps.length}`;
    
    body.innerHTML = `
        <div class="tutorial-icon">${step.icon}</div>
        <h2>${step.title}</h2>
        <p>${step.text}</p>
    `;
}

function nextTutorialStep() {
    if (window.currentTutorialStep < window.tutorialSteps.length) {
        window.currentTutorialStep++;
        updateTutorialContent();
    } else {
        completeTutorial();
    }
}

function skipTutorial() {
    completeTutorial();
}

function completeTutorial() {
    localStorage.setItem(window.STORAGE_KEYS.TUTORIAL, 'true');
    document.getElementById('tutorial-overlay').classList.remove('active');
}

function replayTutorial() {
    localStorage.removeItem(window.STORAGE_KEYS.TUTORIAL);
    showTutorial();
}

// ==========================================
// RENDERING FUNCTIONS
// ==========================================
function renderChatsList(searchQuery = '') {
    const chatsList = document.getElementById('chatsList');
    let filteredChats = window.chats;
    if (searchQuery) {
        const query = searchQuery.toLowerCase();
        filteredChats = window.chats.filter(chat => 
            chat.title.toLowerCase().includes(query) ||
            chat.messages.some(m => m.content.toLowerCase().includes(query))
        );
    }
    
    const pinnedChats = filteredChats.filter(c => c.pinned && !c.archived);
    const regularChats = filteredChats.filter(c => !c.pinned && !c.archived);
    const archivedChats = filteredChats.filter(c => c.archived);
    
    let html = '';
    if (pinnedChats.length > 0) {
        html += '<div class="chat-section"><div class="chat-section-title">⭐ PINNED</div>';
        html += pinnedChats.map(chat => renderChatItem(chat)).join('');
        html += '</div>';
    }
    if (regularChats.length > 0) {
        html += '<div class="chat-section"><div class="chat-section-title">💬 CHATS</div>';
        html += regularChats.map(chat => renderChatItem(chat)).join('');
        html += '</div>';
    }
    if (archivedChats.length > 0) {
        html += '<div class="chat-section"><div class="chat-section-title">📦 ARCHIVED</div>';
        html += archivedChats.map(chat => renderChatItem(chat)).join('');
        html += '</div>';
    }
    if (filteredChats.length === 0) {
        html = '<div style="padding: 20px; text-align: center; color: var(--text-tertiary);">No chats found</div>';
    }
    chatsList.innerHTML = html;
}

function renderChatItem(chat) {
    const isActive = chat.id === window.currentChatId;
    const preview = chat.messages.length > 0 ? chat.messages[chat.messages.length - 1].content.substring(0, 50) : 'No messages yet';
    const pinIcon = chat.pinned ? '⭐' : '📌';
    const archiveIcon = chat.archived ? '📤' : '📦';
    const tagHtml = chat.tag ? `<span class="chat-tag">${chat.tag}</span>` : '';
    
    return `
        <div class="chat-item ${isActive ? 'active' : ''}" onclick="loadChat('${chat.id}')">
            <div class="chat-actions" onclick="event.stopPropagation()">
                <button class="chat-action-btn" onclick="togglePin('${chat.id}')" title="${chat.pinned ? 'Unpin' : 'Pin'}">${pinIcon}</button>
                <button class="chat-action-btn" onclick="toggleArchive('${chat.id}')" title="${chat.archived ? 'Unarchive' : 'Archive'}">${archiveIcon}</button>
                <button class="chat-action-btn" onclick="deleteChat('${chat.id}')" title="Delete">🗑️</button>
            </div>
            <div class="chat-header">${tagHtml}</div>
            <div class="chat-title">${chat.title}</div>
            <div class="chat-preview">${preview}${preview.length >= 50 ? '...' : ''}</div>
        </div>
    `;
}

function renderMessages(messages) {
    const container = document.getElementById('chatContainer');
    container.innerHTML = messages.map((msg, index) => {
        const isUser = msg.role === 'user';
        const avatar = isUser ? 'G' : 'C';
        const avatarClass = isUser ? 'user' : 'assistant';
        
        let actionsHtml = '';
        if (!isUser) {
            actionsHtml = `
                <div class="message-actions">
                    <button class="message-action-btn" onclick="copyMessage(${index})">📋 Copy</button>
                    <button class="message-action-btn" onclick="regenerateResponse(${index})">🔄 Regenerate</button>
                    <button class="message-action-btn" onclick="provideFeedback(${index}, 'thumbsUp')">👍</button>
                    <button class="message-action-btn" onclick="provideFeedback(${index}, 'thumbsDown')">👎</button>
                    <button class="message-action-btn" onclick="provideCorrection(${index})">✏️ Correct</button>
                </div>
            `;
        }
        
        let content = `<div class="message-content">${msg.content}</div>`;
        if (msg.fileData && msg.fileData.type.startsWith('image/')) {
            content += `<div class="file-preview"><img src="${msg.fileData.data}" alt="Uploaded image"><div class="file-info">📎 ${msg.fileData.name}</div></div>`;
        }
        if (msg.imageUrl) {
            content += `<img src="${msg.imageUrl}" class="message-image" alt="Generated image">`;
        }
        
        return `
            <div class="message ${isUser ? 'user' : ''}">
                <div class="avatar ${avatarClass}">${avatar}</div>
                <div class="message-wrapper">${content}${actionsHtml}</div>
            </div>
        `;
    }).join('');
    container.scrollTop = container.scrollHeight;
}

function showThinking() {
    const container = document.getElementById('chatContainer');
    container.insertAdjacentHTML('beforeend', `
        <div class="thinking-indicator" id="thinkingIndicator">
            <div class="avatar assistant">C</div>
            <div class="message-content">Crump is thinking<div class="thinking-dots"><span></span><span></span><span></span></div></div>
        </div>
    `);
    container.scrollTop = container.scrollHeight;
}

function hideThinking() {
    const indicator = document.getElementById('thinkingIndicator');
    if (indicator) indicator.remove();
}

function showCopyNotification() {
    const notification = document.createElement('div');
    notification.className = 'copy-notification';
    notification.textContent = '✓ Copied to clipboard';
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), 2500);
}

// ==========================================
// CHAT MANAGEMENT FUNCTIONS
// ==========================================
function togglePin(chatId) {
    const chat = window.chats.find(c => c.id === chatId);
    if (chat) {
        chat.pinned = !chat.pinned;
        window.saveChats();
        renderChatsList();
    }
}

function toggleArchive(chatId) {
    const chat = window.chats.find(c => c.id === chatId);
    if (chat) {
        chat.archived = !chat.archived;
        window.saveChats();
        renderChatsList();
    }
}

function filterChats(query) {
    renderChatsList(query);
}

function clearCurrentChat() {
    if (!confirm('Clear all messages in this chat?')) return;
    const chat = window.chats.find(c => c.id === window.currentChatId);
    if (chat) {
        chat.messages = [];
        window.saveChats();
        renderMessages([]);
        renderChatsList();
    }
}

function deleteAllChats() {
    if (!confirm('Delete ALL chats? This cannot be undone.')) return;
    window.chats = [];
    window.saveChats();
    window.createNewChat();
}

function copyMessage(index) {
    const chat = window.chats.find(c => c.id === window.currentChatId);
    if (!chat || !chat.messages[index]) return;
    navigator.clipboard.writeText(chat.messages[index].content).then(() => {
        showCopyNotification();
    }).catch(err => console.error('Copy failed:', err));
}

// ==========================================
// CONTEXT PICKER FUNCTIONS
// ==========================================
function showContextPicker() {
    const menu = document.getElementById('contextDropdownMenu');
    const input = document.getElementById('contextPickerInput');
    
    menu.classList.add('active');
    input.focus();
}

function closeContextPicker() {
    const menu = document.getElementById('contextDropdownMenu');
    const input = document.getElementById('contextPickerInput');
    
    menu.classList.remove('active');
    input.value = '';
}

function addCustomContext() {
    const input = document.getElementById('contextPickerInput');
    const label = input.value.trim();
    
    if (!label) {
        return;
    }
    
    window.contextEngine.addContext(label);
    closeContextPicker();
    showNotification(`✓ Context "${label}" added`, 'success');
}

function addContextFromSuggestion(label) {
    window.contextEngine.addContext(label);
    closeContextPicker();
    showNotification(`✓ Context "${label}" added`, 'success');
}

// ==========================================
// SETTINGS FUNCTIONS
// ==========================================
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('active');
    document.getElementById('sidebar-overlay').classList.toggle('active');
}

function closeSidebar() {
    document.getElementById('sidebar').classList.remove('active');
    document.getElementById('sidebar-overlay').classList.remove('active');
}

function toggleSettings() {
    document.getElementById('settingsPanel').classList.toggle('active');
    const nameInput = document.getElementById('assistant-name-input');
    const resetBtn = document.getElementById('reset-name-btn');
    const currentName = window.getAssistantName();
    if (nameInput) nameInput.value = currentName;
    if (resetBtn) resetBtn.style.display = currentName !== 'Crump' ? 'block' : 'none';
}

function toggleVoiceOutput() {
    window.isVoiceEnabled = document.getElementById('voiceToggle').checked;
    localStorage.setItem(window.STORAGE_KEYS.VOICE_OUTPUT, window.isVoiceEnabled);
}

function toggleAutoVoice() {
    window.isAutoVoiceEnabled = document.getElementById('autoVoiceToggle').checked;
    localStorage.setItem(window.STORAGE_KEYS.AUTO_VOICE, window.isAutoVoiceEnabled);
}

function toggleAutonomousMessages() {
    const enabled = document.getElementById('autonomousToggle').checked;
    const intervalSettings = document.getElementById('autonomous-interval-settings');
    
    if (enabled) {
        startAutonomousMessages();
        intervalSettings.style.display = 'block';
    } else {
        stopAutonomousMessages();
        intervalSettings.style.display = 'none';
    }
}

function startAutonomousMessages() {
    window.autonomousMessagesEnabled = true;
    window.autonomousEngine.start();
    localStorage.setItem(window.STORAGE_KEYS.AUTONOMOUS_MESSAGES, 'true');
    showNotification('✓ Autonomous messages enabled', 'success');
}

function stopAutonomousMessages() {
    window.autonomousMessagesEnabled = false;
    window.autonomousEngine.stop();
    localStorage.setItem(window.STORAGE_KEYS.AUTONOMOUS_MESSAGES, 'false');
    showNotification('Autonomous messages disabled', 'info');
}

function setImageGenerator(generator) {
    window.preferredImageGenerator = generator;
    localStorage.setItem(window.STORAGE_KEYS.IMAGE_GENERATOR, generator);
    
    document.getElementById('genPollinations').classList.remove('active');
    document.getElementById('genSegmind').classList.remove('active');
    
    if (generator === 'pollinations') {
        document.getElementById('genPollinations').classList.add('active');
        showNotification('✓ Using Pollinations AI for images', 'success');
    } else {
        document.getElementById('genSegmind').classList.add('active');
        showNotification('✓ Using Segmind for images', 'success');
    }
}

function setAutonomousInterval(interval) {
    window.autonomousEngine.setIntervalPreset(interval);
    localStorage.setItem(window.STORAGE_KEYS.AUTONOMOUS_INTERVAL, interval);
    
    document.getElementById('interval-relaxed').classList.remove('active');
    document.getElementById('interval-balanced').classList.remove('active');
    document.getElementById('interval-active').classList.remove('active');
    document.getElementById('interval-very-active').classList.remove('active');
    
    document.getElementById(`interval-${interval}`).classList.add('active');
    
    const labels = {
        'relaxed': '🐌 Relaxed (15min)',
        'balanced': '⚡ Balanced (5min)',
        'active': '🔥 Active (2min)',
        'very-active': '💬 Very Active (1min)'
    };
    
    showNotification(`✓ Autonomous messages: ${labels[interval]}`, 'success');
}

function toggleConfidenceDisplay() {
    window.showConfidence = document.getElementById('confidenceToggle').checked;
    localStorage.setItem(window.STORAGE_KEYS.SHOW_CONFIDENCE, window.showConfidence);
    
    if (window.showConfidence) {
        showNotification('✓ Confidence indicators enabled', 'success');
    } else {
        showNotification('Confidence indicators disabled', 'info');
        document.querySelectorAll('.confidence-indicator').forEach(el => el.remove());
    }
}

function toggleMetaCommentary() {
    window.metaCommentaryEnabled = document.getElementById('metaToggle').checked;
    localStorage.setItem(window.STORAGE_KEYS.META_COMMENTARY, window.metaCommentaryEnabled);
    
    if (window.metaCommentaryEnabled) {
        showNotification('✓ Auto meta-commentary enabled', 'success');
    } else {
        showNotification('Auto meta-commentary disabled', 'info');
        document.querySelectorAll('.meta-commentary').forEach(el => el.remove());
    }
}

function toggleContextSuggestions() {
    window.contextSuggestionsEnabled = document.getElementById('contextSuggestionsToggle').checked;
    localStorage.setItem(window.STORAGE_KEYS.CONTEXT_SUGGESTIONS_ENABLED, window.contextSuggestionsEnabled);
    
    if (window.contextSuggestionsEnabled) {
        showNotification('✓ Context-aware suggestions enabled', 'success');
    } else {
        showNotification('Context suggestions disabled', 'info');
    }
}

function toggleFeatureReminders() {
    window.featureRemindersEnabled = document.getElementById('featureRemindersToggle').checked;
    localStorage.setItem(window.STORAGE_KEYS.FEATURE_REMINDERS, window.featureRemindersEnabled);
    
    if (window.featureRemindersEnabled) {
        showNotification('✓ Feature reminders enabled', 'success');
    } else {
        showNotification('Feature reminders disabled', 'info');
    }
}

function changeFont(style) {
    document.body.className = style === 'modern' ? '' : `${style}-font`;
    localStorage.setItem(window.STORAGE_KEYS.FONT_STYLE, style);
    document.querySelectorAll('.font-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.textContent.toLowerCase() === style) btn.classList.add('active');
    });
}

function changeBgColor(color) {
    document.documentElement.style.setProperty('--bg-primary', color);
    document.getElementById('bgColorPicker').value = color;
    localStorage.setItem(window.STORAGE_KEYS.BG_COLOR, color);
}

function resetBgColor() {
    changeBgColor('#0a1628');
}

function resetAllPreferences() {
    if (!confirm('Reset ALL preferences? Chats will NOT be deleted.')) return;
    localStorage.removeItem(window.STORAGE_KEYS.UNIVERSAL_MEMORY);
    localStorage.removeItem(window.STORAGE_KEYS.NOVA_PROTOCOL);
    localStorage.removeItem(window.STORAGE_KEYS.SUGGESTIONS);
    window.userMemory = { preferences: {}, contexts: {}, notes: [] };
    window.saveMemory();
    localStorage.removeItem(window.STORAGE_KEYS.VOICE_OUTPUT);
    localStorage.removeItem(window.STORAGE_KEYS.AUTO_VOICE);
    localStorage.removeItem(window.STORAGE_KEYS.FONT_STYLE);
    localStorage.removeItem(window.STORAGE_KEYS.BG_COLOR);
    window.initUniversalMemory();
    window.loadSettings();
    window.updateHeaderDisplay();
    alert('All preferences reset. Assistant name is now "Crump".');
    toggleSettings();
}

// ==========================================
// LEARNING FUNCTIONS
// ==========================================
function provideFeedback(messageIndex, feedbackType) {
    if (!window.learningEngine) return;
    
    const chat = window.chats.find(c => c.id === window.currentChatId);
    if (!chat || !chat.messages[messageIndex]) return;
    
    const messageId = `${window.currentChatId}-${messageIndex}`;
    window.learningEngine.recordFeedback(messageId, feedbackType);
    
    const emoji = feedbackType === 'thumbsUp' ? '👍' : '👎';
    const message = feedbackType === 'thumbsUp' 
        ? 'Thanks! I\'m learning from positive feedback.'
        : 'Noted. I\'ll work on improving.';
    
    showNotification(`${emoji} ${message}`, 'success');
    
    const stats = window.learningEngine.getLearningStats();
    console.log('📊 Learning Stats:', stats);
}

function provideCorrection(messageIndex) {
    const chat = window.chats.find(c => c.id === window.currentChatId);
    if (!chat || !chat.messages[messageIndex]) return;
    
    const originalMessage = chat.messages[messageIndex].content;
    
    const correction = prompt(
        '✏️ How should I have responded?\n\n' +
        'Original response (first 100 chars):\n' +
        originalMessage.substring(0, 100) + '...\n\n' +
        'Your correction:'
    );
    
    if (correction && correction.trim()) {
        window.learningEngine.recordCorrection(
            originalMessage,
            correction.trim(),
            'user_correction'
        );
        
        showNotification('✓ Correction learned! I\'ll remember this.', 'success');
        
        const stats = window.learningEngine.getLearningStats();
        console.log('🎓 New correction recorded. Total corrections:', stats.totalCorrections);
    }
}

function viewLearningStats() {
    if (!window.learningEngine) return;
    
    const stats = window.learningEngine.getLearningStats();
    
    const statsMessage = `
📊 CRUMP LEARNING STATS

Total Interactions: ${stats.totalInteractions}
Corrections Received: ${stats.totalCorrections}
Positive Feedback: ${stats.positiveRate}%
Improvement Rate: ${stats.improvementRate}%

Recent Corrections: ${stats.recentCorrections.length}
Preferences Learned: ${Object.keys(stats.preferences).length}

Current Preferences:
- Response Length: ${stats.preferences.responseLength}
- Code Style: ${stats.preferences.codeStyle}
- Tone: ${stats.preferences.tone}
    `.trim();
    
    alert(statsMessage);
    console.log('📊 Full Learning Stats:', stats);
}

function clearLearningData() {
    if (!confirm('⚠️ Clear all learning data? This will erase:\n\n- All corrections\n- Learned preferences\n- Performance metrics\n\nThis cannot be undone.')) {
        return;
    }
    
    localStorage.removeItem(window.STORAGE_KEYS.CORRECTIONS);
    localStorage.removeItem(window.STORAGE_KEYS.USER_PREFERENCES);
    localStorage.removeItem(window.STORAGE_KEYS.PERFORMANCE_METRICS);
    
    if (window.learningEngine) {
        window.learningEngine = new window.LearningEngine();
    }
    
    showNotification('✓ Learning data cleared', 'success');
}

// ==========================================
// VOICE FUNCTIONS
// ==========================================
function toggleVoiceInput() {
    if (!window.recognition) {
        alert('Voice recognition not supported in your browser.');
        return;
    }
    if (window.isListening) {
        window.recognition.stop();
        window.isListening = false;
    } else {
        window.recognition.start();
        window.isListening = true;
    }
    updateVoiceButton();
}

function updateVoiceButton() {
    const btn = document.getElementById('voiceBtn');
    btn.textContent = window.isListening ? '⏹️' : '🎤';
    btn.style.background = window.isListening ? 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))' : 'transparent';
    btn.style.color = window.isListening ? 'var(--bg-primary)' : 'var(--text-secondary)';
}

function speak(text) {
    if (!window.isVoiceEnabled) return;
    if (window.currentUtterance) speechSynthesis.cancel();
    window.currentUtterance = new SpeechSynthesisUtterance(text);
    window.currentUtterance.rate = 1.1;
    window.currentUtterance.pitch = 1.0;
    speechSynthesis.speak(window.currentUtterance);
}

// ==========================================
// FILE HANDLING FUNCTIONS
// ==========================================
function attachFile() {
    document.getElementById('fileInput').click();
}

function handleFileSelect(event) {
    const files = Array.from(event.target.files);
    if (!files.length) return;
    
    if (files.length > 5) {
        alert('Maximum 5 images at once');
        files.length = 5;
    }
    
    for (const file of files) {
        if (!file.type.startsWith('image/')) {
            alert('Only images are supported');
            return;
        }
        if (file.size > window.CONFIG.FILE_SIZE_LIMIT_MB * 1024 * 1024) {
            alert(`Files must be under ${window.CONFIG.FILE_SIZE_LIMIT_MB}MB`);
            return;
        }
    }
    
    window.currentFiles = [];
    let processed = 0;
    
    files.forEach((file, index) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            window.currentFiles.push({
                name: file.name,
                size: file.size,
                type: file.type,
                data: e.target.result
            });
            processed++;
            
            if (processed === files.length) {
                updateFilePreview();
            }
        };
        reader.readAsDataURL(file);
    });
}

function updateFilePreview() {
    const preview = document.getElementById('filePreview');
    const previewImage = document.getElementById('filePreviewImage');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    
    if (window.currentFiles.length === 0) {
        preview.classList.remove('active');
        return;
    }
    
    previewImage.src = window.currentFiles[0].data;
    
    if (window.currentFiles.length === 1) {
        fileName.textContent = window.currentFiles[0].name;
        fileSize.textContent = formatFileSize(window.currentFiles[0].size);
    } else {
        fileName.textContent = `${window.currentFiles.length} images selected`;
        const totalSize = window.currentFiles.reduce((sum, f) => sum + f.size, 0);
        fileSize.textContent = formatFileSize(totalSize);
    }
    
    preview.classList.add('active');
}

function removeFile() {
    window.currentFiles = [];
    document.getElementById('filePreview').classList.remove('active');
    document.getElementById('fileInput').value = '';
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}

// ==========================================
// EXPORT/IMPORT FUNCTIONS
// ==========================================
function exportAllData() {
    try {
        const exportData = {
            version: "2.11.0",
            exportDate: new Date().toISOString(),
            chats: window.chats,
            currentChatId: window.currentChatId,
            memory: window.userMemory,
            universalMemory: window.getUniversalMemory(),
            novaProtocol: window.getNovaProtocol(),
            suggestions: localStorage.getItem(window.STORAGE_KEYS.SUGGESTIONS),
            settings: {
                voiceOutput: localStorage.getItem(window.STORAGE_KEYS.VOICE_OUTPUT),
                autoVoice: localStorage.getItem(window.STORAGE_KEYS.AUTO_VOICE),
                fontStyle: localStorage.getItem(window.STORAGE_KEYS.FONT_STYLE),
                bgColor: localStorage.getItem(window.STORAGE_KEYS.BG_COLOR)
            },
            tutorialCompleted: localStorage.getItem(window.STORAGE_KEYS.TUTORIAL)
        };
        const dataStr = JSON.stringify(exportData, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        const timestamp = new Date().toISOString().split('T')[0];
        link.download = `${window.getAssistantName().toLowerCase()}-backup-${timestamp}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        showNotification('✓ Data exported successfully!', 'success');
    } catch (error) {
        console.error('Export error:', error);
        showNotification('❌ Error exporting data', 'error');
    }
}

function handleImport(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const importData = JSON.parse(e.target.result);
            if (!importData.version || !importData.exportDate) throw new Error('Invalid backup');
            if (importData.chats && !Array.isArray(importData.chats)) throw new Error('Invalid chats');
            if (importData.chats) {
                for (const chat of importData.chats) {
                    if (!chat.id || !chat.messages || !Array.isArray(chat.messages)) throw new Error('Invalid chat structure');
                }
            }
            if (!confirm('⚠️ Replace all data with imported backup?')) {
                event.target.value = '';
                return;
            }
            if (importData.chats) localStorage.setItem(window.STORAGE_KEYS.CHATS, JSON.stringify(importData.chats));
            if (importData.currentChatId) localStorage.setItem(window.STORAGE_KEYS.CURRENT_CHAT, importData.currentChatId);
            if (importData.memory) localStorage.setItem(window.STORAGE_KEYS.USER_MEMORY, JSON.stringify(importData.memory));
            if (importData.universalMemory) localStorage.setItem(window.STORAGE_KEYS.UNIVERSAL_MEMORY, JSON.stringify(importData.universalMemory));
            if (importData.novaProtocol) localStorage.setItem(window.STORAGE_KEYS.NOVA_PROTOCOL, JSON.stringify(importData.novaProtocol));
            if (importData.suggestions) localStorage.setItem(window.STORAGE_KEYS.SUGGESTIONS, importData.suggestions);
            if (importData.settings) {
                if (importData.settings.voiceOutput) localStorage.setItem(window.STORAGE_KEYS.VOICE_OUTPUT, importData.settings.voiceOutput);
                if (importData.settings.autoVoice) localStorage.setItem(window.STORAGE_KEYS.AUTO_VOICE, importData.settings.autoVoice);
                if (importData.settings.fontStyle) localStorage.setItem(window.STORAGE_KEYS.FONT_STYLE, importData.settings.fontStyle);
                if (importData.settings.bgColor) localStorage.setItem(window.STORAGE_KEYS.BG_COLOR, importData.settings.bgColor);
            }
            if (importData.tutorialCompleted) localStorage.setItem(window.STORAGE_KEYS.TUTORIAL, importData.tutorialCompleted);
            showNotification('✓ Data imported! Reloading...', 'success');
            setTimeout(() => window.location.reload(), 1500);
        } catch (error) {
            console.error('Import error:', error);
            showNotification('❌ Error importing data', 'error');
            event.target.value = '';
        }
    };
    reader.readAsText(file);
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `position:fixed;top:20px;right:20px;background:${type==='success'?'#10b981':type==='error'?'#ef4444':'#3b82f6'};color:white;padding:16px 24px;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.3);z-index:10000;font-size:14px;font-weight:600;max-width:400px;animation:slideInNotification 0.3s ease-out;`;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => {
        notification.style.animation = 'slideOutNotification 0.3s ease-out';
        setTimeout(() => { if (notification.parentNode) document.body.removeChild(notification); }, 300);
    }, 3000);
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

function updateCharCount() {
    const input = document.getElementById('userInput');
    const counter = document.getElementById('charCount');
    const count = input.value.length;
    
    if (count > 0) {
        counter.style.display = 'block';
        counter.textContent = `${count.toLocaleString()} / 50,000`;
        
        if (count > 40000) {
            counter.style.color = '#ff4444';
        } else if (count > 30000) {
            counter.style.color = '#f59e0b';
        } else {
            counter.style.color = 'var(--text-tertiary)';
        }
    } else {
        counter.style.display = 'none';
    }
}

function sendBrowserNotification(title, body) {
    if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
        new Notification(title, {
            body: body,
            icon: '/assets/icon-192.png',
            badge: '/assets/icon-192.png'
        });
    }
}

// Export functions to window
window.showTutorial = showTutorial;
window.nextTutorialStep = nextTutorialStep;
window.skipTutorial = skipTutorial;
window.replayTutorial = replayTutorial;
window.renderChatsList = renderChatsList;
window.renderMessages = renderMessages;
window.showThinking = showThinking;
window.hideThinking = hideThinking;
window.togglePin = togglePin;
window.toggleArchive = toggleArchive;
window.filterChats = filterChats;
window.clearCurrentChat = clearCurrentChat;
window.deleteAllChats = deleteAllChats;
window.copyMessage = copyMessage;
window.showContextPicker = showContextPicker;
window.closeContextPicker = closeContextPicker;
window.addCustomContext = addCustomContext;
window.addContextFromSuggestion = addContextFromSuggestion;
window.toggleSidebar = toggleSidebar;
window.closeSidebar = closeSidebar;
window.toggleSettings = toggleSettings;
window.toggleVoiceOutput = toggleVoiceOutput;
window.toggleAutoVoice = toggleAutoVoice;
window.toggleAutonomousMessages = toggleAutonomousMessages;
window.setImageGenerator = setImageGenerator;
window.setAutonomousInterval = setAutonomousInterval;
window.toggleConfidenceDisplay = toggleConfidenceDisplay;
window.toggleMetaCommentary = toggleMetaCommentary;
window.toggleContextSuggestions = toggleContextSuggestions;
window.toggleFeatureReminders = toggleFeatureReminders;
window.changeFont = changeFont;
window.changeBgColor = changeBgColor;
window.resetBgColor = resetBgColor;
window.resetAllPreferences = resetAllPreferences;
window.provideFeedback = provideFeedback;
window.provideCorrection = provideCorrection;
window.viewLearningStats = viewLearningStats;
window.clearLearningData = clearLearningData;
window.toggleVoiceInput = toggleVoiceInput;
window.speak = speak;
window.attachFile = attachFile;
window.handleFileSelect = handleFileSelect;
window.removeFile = removeFile;
window.exportAllData = exportAllData;
window.handleImport = handleImport;
window.showNotification = showNotification;
window.autoResize = autoResize;
window.updateCharCount = updateCharCount;

console.log('✅ UI Functions module loaded');
