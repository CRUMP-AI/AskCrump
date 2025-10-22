// ==========================================
// CRUMP AI - IMPROVED RENDERING v2.12.0
// Add to or replace functions in ui-functions.js
// ==========================================

// ==========================================
// ENHANCED MESSAGE RENDERING
// ==========================================
function renderMessages(messages) {
    const container = document.getElementById('chatContainer');
    const userInitial = localStorage.getItem(window.STORAGE_KEYS.USER_INITIAL) || 'U';
    
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
        let content = msg.content;
        
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
        if (msg.fileData && msg.fileData.type.startsWith('image/')) {
            contentHtml += `
                <div class="file-preview">
                    <img src="${msg.fileData.data}" alt="Uploaded image">
                    <div class="file-info">📎 ${msg.fileData.name}</div>
                </div>
            `;
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
        Prism.highlightAll();
    }
    
    // Render math expressions
    if (typeof renderMathInElement !== 'undefined') {
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
    text = text.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    
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

// Export functions
window.renderMessages = renderMessages;
window.processCodeBlocks = processCodeBlocks;
window.processMarkdown = processMarkdown;

console.log('✅ Improved rendering loaded');
