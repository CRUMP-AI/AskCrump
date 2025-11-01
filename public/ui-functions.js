// ==========================================
// CRUMP AI - UI FUNCTIONS v2.12.1
// Message rendering with markdown and code blocks
// ==========================================

// ==========================================
// ENHANCED MESSAGE RENDERING
// ==========================================
function renderMessages(messages) {
    const container = document.getElementById('chatContainer');
    if (!container) {
        console.error('❌ chatContainer not found');
        return;
    }
    
    const userInitial = localStorage.getItem(window.STORAGE_KEYS?.USER_INITIAL) || 'U';
    
    container.innerHTML = messages.map((msg, index) => {
        const isUser = msg.role === 'user';
        const avatar = isUser ? userInitial : 'C';
        const avatarClass = isUser ? 'user' : 'assistant';
        
        let actionsHtml = '';
        if (!isUser) {
            actionsHtml = `
                <div class="message-actions">
                    <button class="message-action-btn" onclick="copyMessage(${index})" title="Copy message">
                        📋 Copy
                    </button>
                    <button class="message-action-btn" onclick="regenerateResponse(${index})" title="Regenerate response">
                        🔄 Regenerate
                    </button>
                    <button class="message-action-btn" onclick="provideFeedback(${index}, 'thumbsUp')" title="Good response">
                        👍
                    </button>
                    <button class="message-action-btn" onclick="provideFeedback(${index}, 'thumbsDown')" title="Bad response">
                        👎
                    </button>
                    <button class="message-action-btn" onclick="provideCorrection(${index})" title="Correct this">
                        ✏️ Correct
                    </button>
                </div>
            `;
        }
        
        // Parse markdown and code blocks
        let content = msg.content || '';
        
        if (!isUser) {
            // Process code blocks FIRST (before markdown)
            content = processCodeBlocks(content);
            
            // Then process markdown
            content = processMarkdown(content);
        } else {
            // For user messages, just escape HTML
            content = escapeHtml(content);
        }
        
        let contentHtml = `<div class="message-content">${content}</div>`;
        
        // Handle file attachments
        if (msg.fileData) {
            if (Array.isArray(msg.fileData)) {
                msg.fileData.forEach(file => {
                    if (file.type.startsWith('image/')) {
                        contentHtml += `
                            <div class="file-preview">
                                <img src="${file.data}" alt="Uploaded image">
                                <div class="file-info">📎 ${file.name}</div>
                            </div>
                        `;
                    }
                });
            } else if (msg.fileData.type.startsWith('image/')) {
                contentHtml += `
                    <div class="file-preview">
                        <img src="${msg.fileData.data}" alt="Uploaded image">
                        <div class="file-info">📎 ${msg.fileData.name || 'Uploaded image'}</div>
                    </div>
                `;
            }
        }
        
        // Handle generated images
        if (msg.imageUrl) {
            contentHtml += `
                <div class="generated-image-wrapper">
                    <img src="${msg.imageUrl}" class="message-image" alt="Generated image" 
                         onerror="this.parentElement.innerHTML='<div class=\\'image-error\\'>❌ Image failed to load</div>'">
                    <div class="image-actions">
                        <button class="image-action-btn" onclick="downloadImage('${msg.imageUrl}')" title="Download image">
                            💾 Download
                        </button>
                        <button class="image-action-btn" onclick="openImageInNewTab('${msg.imageUrl}')" title="Open in new tab">
                            🔗 Open
                        </button>
                    </div>
                </div>
            `;
        }
        
        return `
            <div class="message ${isUser ? 'user' : ''}">
                <div class="avatar ${avatarClass}">${avatar}</div>
                <div class="message-wrapper">
                    ${contentHtml}
                    ${actionsHtml}
                </div>
            </div>
        `;
    }).join('');
    
    // Highlight all code blocks after rendering
    if (typeof Prism !== 'undefined') {
        try {
            Prism.highlightAll();
        } catch (e) {
            console.warn('Prism highlighting failed:', e);
        }
    }
    
    // Render math expressions
    if (typeof renderMathInElement !== 'undefined') {
        try {
            renderMathInElement(container, {
                delimiters: [
                    {left: '$$', right: '$$', display: true},
                    {left: '$', right: '$', display: false},
                    {left: '\\[', right: '\\]', display: true},
                    {left: '\\(', right: '\\)', display: false}
                ],
                throwOnError: false,
                strict: false
            });
        } catch (e) {
            console.warn('Math rendering failed:', e);
        }
    }
    
    container.scrollTop = container.scrollHeight;
}

// ==========================================
// CODE BLOCK PROCESSING
// ==========================================
function processCodeBlocks(text) {
    // Match code blocks with optional language specifier
    return text.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const language = lang || 'plaintext';
        const escapedCode = code
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        return `
            <div class="code-block-wrapper">
                <div class="code-block-header">
                    <span class="code-language">${language}</span>
                    <button class="code-copy-btn" onclick="copyCodeBlock(this)">
                        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                        Copy
                    </button>
                </div>
                <pre><code class="language-${language}">${escapedCode}</code></pre>
            </div>
        `;
    });
}

// ==========================================
// MARKDOWN PROCESSING
// ==========================================
function processMarkdown(text) {
    // Bold (but not in code blocks - already processed)
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // Italic
    text = text.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
    
    // Inline code (but preserve HTML entities)
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Links
    text = text.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    
    // Headers
    text = text.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
    text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    
    // Lists (basic support)
    text = text.replace(/^\* (.+)$/gm, '<li>$1</li>');
    text = text.replace(/^- (.+)$/gm, '<li>$1</li>');
    
    // Wrap consecutive <li> in <ul>
    text = text.replace(/(<li>.*?<\/li>\n?)+/g, '<ul>$&</ul>');
    
    // Line breaks (double newline = paragraph break)
    text = text.replace(/\n\n/g, '<br><br>');
    
    // Single line breaks
    text = text.replace(/\n/g, '<br>');
    
    return text;
}

// ==========================================
// UTILITY FUNCTIONS
// ==========================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==========================================
// MESSAGE ACTIONS
// ==========================================

// Copy message to clipboard
window.copyMessage = function(index) {
    const chat = window.chats.find(c => c.id === window.currentChatId);
    if (!chat || !chat.messages[index]) return;
    
    const message = chat.messages[index];
    const text = message.content;
    
    navigator.clipboard.writeText(text).then(() => {
        window.showNotification('✅ Message copied to clipboard', 'success');
    }).catch(err => {
        console.error('Copy failed:', err);
        window.showNotification('❌ Failed to copy message', 'error');
    });
};

// Regenerate response
window.regenerateResponse = function(index) {
    const chat = window.chats.find(c => c.id === window.currentChatId);
    if (!chat || !chat.messages[index]) return;
    
    // Find the user message before this assistant message
    let userMessageIndex = index - 1;
    while (userMessageIndex >= 0 && chat.messages[userMessageIndex].role !== 'user') {
        userMessageIndex--;
    }
    
    if (userMessageIndex >= 0) {
        const userMessage = chat.messages[userMessageIndex].content;
        
        // Remove old assistant response
        chat.messages.splice(index, 1);
        window.saveChats();
        window.renderMessages(chat.messages);
        
        // Resend the user message
        document.getElementById('userInput').value = userMessage;
        window.sendMessage();
    }
};

// Provide feedback
window.provideFeedback = function(index, type) {
    if (window.learningEngine) {
        window.learningEngine.recordFeedback(index, type);
    }
};

// Provide correction
window.provideCorrection = function(index) {
    const chat = window.chats.find(c => c.id === window.currentChatId);
    if (!chat || !chat.messages[index]) return;
    
    const message = chat.messages[index];
    const correction = prompt('What should the correct response be?', message.content);
    
    if (correction && correction.trim()) {
        if (window.learningEngine) {
            window.learningEngine.recordCorrection(message.content, correction);
        }
    }
};

// Code block copy function
window.copyCodeBlock = function(button) {
    const codeBlock = button.closest('.code-block-wrapper').querySelector('code');
    const text = codeBlock.textContent;
    
    navigator.clipboard.writeText(text).then(() => {
        const originalHtml = button.innerHTML;
        button.innerHTML = `
            <svg width="16" height="16" fill="none" stroke="#10b981" stroke-width="2" viewBox="0 0 24 24">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            Copied!
        `;
        button.style.color = '#10b981';
        
        setTimeout(() => {
            button.innerHTML = originalHtml;
            button.style.color = '';
        }, 2000);
    }).catch(err => {
        console.error('Copy failed:', err);
        window.showNotification('❌ Copy failed', 'error');
    });
};

// Image actions
window.downloadImage = function(url) {
    const link = document.createElement('a');
    link.href = url;
    link.download = `crump-generated-${Date.now()}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.showNotification('✅ Image download started', 'success');
};

window.openImageInNewTab = function(url) {
    window.open(url, '_blank');
};

// ==========================================
// REPLACE the showThinking() function in ui-functions.js
// Around line 331-356
// ==========================================

function showThinking() {
    const container = document.getElementById('chatContainer');
    if (!container) return;
    
    const existing = document.getElementById('thinkingIndicator');
    if (existing) return; // Already showing
    
    const thinking = document.createElement('div');
    thinking.id = 'thinkingIndicator';
    thinking.className = 'thinking-indicator';
    thinking.style.display = 'flex';
    thinking.innerHTML = `
        <div class="thinking-avatar">
            <img src="/assets/logo-c.png" alt="Assistant">
        </div>
        <div class="thinking-content">
            <div class="thinking-text"><span class="assistant-name">Crump</span> is typing</div>
            <div class="thinking-dots-wrapper">
                <span class="thinking-dot"></span>
                <span class="thinking-dot"></span>
                <span class="thinking-dot"></span>
            </div>
        </div>
    `;
    
    container.appendChild(thinking);
    container.scrollTop = container.scrollHeight;
}

function hideThinking() {
    const thinking = document.getElementById('thinkingIndicator');
    if (thinking) {
        thinking.remove();
    }
}

// ==========================================
// NOTIFICATION SYSTEM
// ==========================================
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 24px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        z-index: 10001;
        animation: slideInNotification 0.3s ease;
        font-size: 14px;
        font-weight: 500;
        max-width: 400px;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutNotification 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ==========================================
// EXPORT TO WINDOW
// ==========================================
window.renderMessages = renderMessages;
window.processCodeBlocks = processCodeBlocks;
window.processMarkdown = processMarkdown;
window.showThinking = showThinking;
window.hideThinking = hideThinking;
window.showNotification = showNotification;

// COMPATIBILITY: Single message wrapper for image-generation.js and self-debug-v3.js
window.renderMessage = function(message) {
    const chat = window.chats?.find(c => c.id === window.currentChatId);
    if (chat && chat.messages) {
        renderMessages(chat.messages);
    } else {
        console.warn('⚠️ renderMessage: No active chat found');
    }
};

console.log('✅ UI Functions v2.12.1 loaded');
