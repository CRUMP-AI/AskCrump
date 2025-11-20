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
    
    const userInitial =
        (window.currentProfile && window.currentProfile.profile && window.currentProfile.profile.initial) ||
        localStorage.getItem(window.STORAGE_KEYS?.USER_INITIAL) ||
        localStorage.getItem('crump_user_initial') ||
        'U';

    container.innerHTML = messages.map((msg, index) => {
        const isUser = msg.role === 'user';

        // Build avatar HTML
        let avatarHtml;
        if (isUser) {
            // Your messages → letter avatar (G, etc.)
            avatarHtml = `
            <div class="avatar user">
                ${userInitial}
            </div>
        `;
        } else {
            // Crump's messages → Ask Crump logo
            avatarHtml = `
            <div class="avatar assistant">
                <img src="/assets/logo-c.png"
                     alt="Assistant"
                     style="width: 100%; height: 100%; object-fit: contain;">
            </div>
        `;
        }

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
            // For user messages, just escape HTML to prevent injection
            content = escapeHtml(content);
        }

        let contentHtml = `<div class="message-content">${content}</div>`;

        // Handle attached files (non-images)
        if (msg.files && Array.isArray(msg.files)) {
            msg.files.forEach(file => {
                if (!file.type || !file.type.startsWith('image/')) {
                    contentHtml += `
                <div class="message-attachment">
                    <div class="file-icon">📎</div>
                    <div class="file-info">
                        <div class="file-name">${file.name || 'Attachment'}</div>
                        <div class="file-meta">${file.type || 'File'}</div>
                    </div>
                    ${file.url ? `<button class="file-open-btn" onclick="window.open('${file.url}', '_blank')">Open</button>` : ''}
                </div>
            `;
                }
            });
        }

        // Handle attached images
        if (msg.files && Array.isArray(msg.files)) {
            msg.files.forEach(file => {
                if (file.type && file.type.startsWith('image/')) {
                    contentHtml += `
                <div class="message-image-wrapper">
                    <img src="${file.url}" class="message-image" alt="${file.name || 'Uploaded image'}" 
                         onerror="this.parentElement.innerHTML='<div class=\\'image-error\\'>❌ Image failed to load</div>'">
                    <div class="image-actions">
                        <button class="image-action-btn" onclick="downloadImage('${file.url}')" title="Download image">
                            💾 Download
                        </button>
                        <button class="image-action-btn" onclick="openImageInNewTab('${file.url}')" title="Open in new tab">
                            🔗 Open
                        </button>
                    </div>
                </div>
            `;
                }
            });
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
        ${avatarHtml}
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

    // Render math if KaTeX is available
    if (window.katex) {
        try {
            renderMathInElement(container, {
                delimiters: [
                    { left: '$$', right: '$$', display: true },
                    { left: '$', right: '$', display: false },
                    { left: '\\[', right: '\\]', display: true },
                    { left: '\\(', right: '\\)', display: false }
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
// MARKDOWN & CODE PROCESSING HELPERS
// ==========================================

function processCodeBlocks(content) {
    if (!content || typeof content !== 'string') return content;

    // Handle ```lang\ncode``` blocks
    const codeBlockRegex = /```([a-zA-Z0-9]*)\n([\s\S]*?)```/g;
    content = content.replace(codeBlockRegex, (match, lang, code) => {
        const language = lang || 'javascript';
        const escapedCode = escapeHtml(code.trim());
        return `
        <pre class="code-block">
            <code class="language-${language}">${escapedCode}</code>
        </pre>
        `;
    });

    // Handle inline `code`
    const inlineCodeRegex = /`([^`]+)`/g;
    content = content.replace(inlineCodeRegex, (match, code) => {
        return `<code class="inline-code">${escapeHtml(code)}</code>`;
    });

    return content;
}

function processMarkdown(content) {
    if (!content || typeof content !== 'string') return content;

    let html = content;

    // Headings: #, ##, ###
    html = html.replace(/^### (.*)$/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*)$/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*)$/gim, '<h1>$1</h1>');

    // Bold **text**
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');

    // Italic *text*
    html = html.replace(/\*(.*?)\*/gim, '<em>$1</em>');

    // Links [text](url)
    html = html.replace(
        /\[(.*?)\]\((.*?)\)/gim,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    );

    // Lists
    html = html.replace(/^\s*[-*] (.*)$/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/gim, '<ul>$1</ul>');

    // Line breaks
    html = html.replace(/\n/g, '<br>');

    return html;
}

function escapeHtml(unsafe) {
    if (!unsafe || typeof unsafe !== 'string') return unsafe;
    return unsafe
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

