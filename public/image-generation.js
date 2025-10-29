/* ============================================
   CRUMP AI - SMART IMAGE GENERATION v3.0
   Fixed: "another" sensitivity + better blacklist
   ============================================ */

window.imageGenerationState = {
    lastResponseWasImage: false,
    lastImagePrompt: null,
    lastImageUrl: null,
    conversationContext: []
};

// ==========================================
// SMART IMAGE DETECTION (FIXED)
// ==========================================
window.shouldGenerateImage = function(message) {
    if (!message || typeof message !== 'string') return false;
    
    const lowerMessage = message.toLowerCase().trim();
    
    // 1. FOLLOW-UP DETECTION (if last response was an image)
    if (window.imageGenerationState.lastResponseWasImage) {
        const followUpPhrases = [
            'try again', 'another image', 'another picture', 'different image', 
            'different picture', 'one more image', 'new image', 'remake', 'redo', 
            'change it', 'modify it', 'adjust it', 'tweak it', 'make it', 
            'more like', 'but with', 'similar but'
        ];
        
        for (const phrase of followUpPhrases) {
            if (lowerMessage.includes(phrase)) {
                console.log('🔄 Follow-up image request detected');
                return true;
            }
        }
        
        // Short affirmatives after image = wants another
        const shortAffirmatives = ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay'];
        if (shortAffirmatives.includes(lowerMessage) && lowerMessage.length < 10) {
            console.log('🔄 Affirmative follow-up detected');
            return true;
        }
    }
    
    // 2. CONTEXT BLACKLIST - EXPANDED (never trigger on these contexts)
    const blacklistContexts = [
        // Technical/debugging
        'bug', 'error', 'issue', 'problem', 'fix', 'debug', 'test', 'testing',
        
        // Analysis/discussion
        'example', 'instance', 'case', 'scenario', 'situation', 
        'think', 'maybe', 'perhaps', 'might', 'could be', 'probably',
        
        // File upload indicators
        'can you see', 'do you see', 'look at', 'view', 'analyze', 
        'check', 'inspect', 'uploaded', 'attached', 'sent you',
        
        // Questions/explanations
        'why', 'how', 'what does', 'explain', 'describe',
        
        // UI/code references
        'word', 'causing', 'certain', 'moment', 'startup', 'splash',
        'logo for you', 'i want to', 'come up with',
        
        // Conversation meta (specific contexts where "another" means something else)
        'another bug', 'another problem', 'another issue', 'another question',
        'another error', 'another test'
    ];
    
    for (const context of blacklistContexts) {
        if (lowerMessage.includes(context)) {
            console.log('🚫 Blacklisted context detected:', context, '- blocking image gen');
            return false;
        }
    }
    
    // 3. EXPLICIT MULTI-WORD PATTERNS (must have BOTH action AND image type)
    const actionWords = ['generate', 'create', 'make', 'draw', 'design', 'produce', 'show me'];
    const imageWords = ['image', 'picture', 'photo', 'illustration', 'logo', 'icon', 'banner', 'graphic', 'artwork', 'visual'];
    
    let hasAction = false;
    let hasImageWord = false;
    
    for (const action of actionWords) {
        if (lowerMessage.includes(action)) {
            hasAction = true;
            break;
        }
    }
    
    for (const imageWord of imageWords) {
        if (lowerMessage.includes(imageWord)) {
            hasImageWord = true;
            break;
        }
    }
    
    // CRITICAL: Must have BOTH to trigger
    if (hasAction && hasImageWord) {
        console.log('🎨 Explicit image request detected');
        return true;
    }
    
    // 4. SPECIFIC SAFE PATTERNS (high confidence only)
    const safePatterns = [
        /^(generate|create|make|draw)\s+(me\s+)?(a|an)\s+\w+\s+(image|picture|logo|icon)/i,
        /^show me (a|an)\s+\w+\s+(image|picture)/i,
        /i (need|want)\s+(a|an)\s+(logo|icon|banner|image|picture)/i
    ];
    
    for (const pattern of safePatterns) {
        if (pattern.test(message)) {
            console.log('🎨 Safe pattern matched');
            return true;
        }
    }
    
    // 5. SINGLE WORD + "OF" PATTERN (but ONLY for obvious image types)
    const singleWordImageTypes = [
        'painting', 'drawing', 'sketch', 'illustration',
        'photo', 'picture', 'image', 'render', 'graphic',
        'artwork', 'design', 'logo', 'icon', 'banner'
    ];
    
    for (const type of singleWordImageTypes) {
        const pattern = new RegExp(`^${type}\\s+of\\b`, 'i');
        if (pattern.test(message)) {
            console.log('🎨 Single-word pattern detected:', type);
            return true;
        }
    }
    
    // Add to conversation context
    window.imageGenerationState.conversationContext.push(lowerMessage);
    if (window.imageGenerationState.conversationContext.length > 5) {
        window.imageGenerationState.conversationContext.shift();
    }
    
    return false;
};

// ==========================================
// IMAGE GENERATION HANDLER
// ==========================================
window.handleImageGeneration = async function(userMessage) {
    try {
        console.log('🎨 Generating image for:', userMessage);
        
        // Check usage limits
        if (window.currentProfile) {
            const canGenerate = window.currentProfile.canGenerateImage();
            if (!canGenerate.allowed) {
                if (window.showToast) {
                    window.showToast(canGenerate.message || 'Image generation limit reached', 'error');
                }
                if (typeof showUpgradePrompt === 'function') {
                    setTimeout(() => showUpgradePrompt(), 1000);
                }
                return;
            }
        }
        
        const currentChat = window.crumpDebug?.getCurrentChat?.();
        if (!currentChat) {
            console.error('❌ No current chat found');
            return;
        }

        // Extract or reuse prompt
        let prompt = extractImagePrompt(userMessage);
        
        // If it's a follow-up, combine with previous prompt
        if (window.imageGenerationState.lastResponseWasImage && 
            window.imageGenerationState.lastImagePrompt) {
            prompt = enhancePromptWithContext(userMessage, window.imageGenerationState.lastImagePrompt);
        }

       // NOTE: User message already added and rendered by app.js - don't duplicate!

        // Show generating indicator
        const assistantMsg = {
            role: 'assistant',
            content: 'Generating image...',
            timestamp: Date.now(),
            generating: true
        };
        currentChat.messages.push(assistantMsg);
        
        if (typeof renderMessage === 'function') {
            renderMessage(assistantMsg);
        }

        // Generate image
        const imageUrl = await generateImageWithPollinations(prompt);
        
        if (!imageUrl) {
            throw new Error('Failed to generate image');
        }

        // Update state
        window.imageGenerationState.lastResponseWasImage = true;
        window.imageGenerationState.lastImagePrompt = prompt;
        window.imageGenerationState.lastImageUrl = imageUrl;

        // Remove generating message and add final message
        currentChat.messages.pop();
        
       const finalMsg = {
    role: 'assistant',
    content: '', // Empty - image will render from imageUrl property
    timestamp: Date.now(),
    imageUrl: imageUrl,
    imagePrompt: prompt
};
        
        currentChat.messages.push(finalMsg);
        currentChat.updatedAt = Date.now();
        
        if (typeof window.crumpDebug?.getCurrentChat === 'function') {
            const chats = JSON.parse(localStorage.getItem('crump_chats') || '[]');
            const chatIndex = chats.findIndex(c => c.id === currentChat.id);
            if (chatIndex !== -1) {
                chats[chatIndex] = currentChat;
                localStorage.setItem('crump_chats', JSON.stringify(chats));
            }
        }

       // Re-render chat to show image using app.js renderMessages
        if (typeof renderMessages === 'function') {
            renderMessages(currentChat.messages);
        }
        
        // Scroll to bottom
        if (window.crumpScrollManager) {
            window.crumpScrollManager.scrollToBottom('smooth');
        }

        console.log('✅ Image generated successfully');

    } catch (error) {
        console.error('❌ Image generation error:', error);
        
        window.imageGenerationState.lastResponseWasImage = false;
        
        if (typeof showToast === 'function') {
            showToast('Failed to generate image', 'error');
        }
    }
};

// ==========================================
// SMART PROMPT EXTRACTION
// ==========================================
function extractImagePrompt(message) {
    const lowerMessage = message.toLowerCase();
    
    let prompt = message
        .replace(/^(generate|create|make|draw|design|illustrate|render|produce|build|craft|paint|sketch)\s+(me\s+)?(an?|the|some)?\s*/i, '')
        .replace(/^(show me|give me|let me see|i need|i want)\s+(an?|the|some)?\s*/i, '')
        .replace(/^(can you|could you|would you|will you|please)\s+(make|create|generate|draw|design)\s+(me\s+)?(an?|the|some)?\s*/i, '')
        .trim();
    
    prompt = prompt
        .replace(/^\s*(image|picture|photo|illustration|artwork|graphic|visual|painting|drawing|render|design|art|pic|logo|icon|banner)\s+(of|for|with|about|showing)?\s*/i, '')
        .trim();
    
    if (prompt.length < 3) {
        const patterns = [
            /(?:of|for|with|about|showing)\s+(.+)/i,
            /(?:a|an|the)\s+(.+)/i,
            /\s+(.+)$/i
        ];
        
        for (const pattern of patterns) {
            const match = message.match(pattern);
            if (match && match[1] && match[1].length > 2) {
                prompt = match[1].trim();
                break;
            }
        }
    }
    
    if (prompt.length < 3) {
        prompt = message;
    }
    
    prompt = prompt
        .replace(/^(of|for|with|about|showing)\s+/i, '')
        .replace(/\s+/g, ' ')
        .replace(/^(a|an|the)\s+/i, '')
        .trim();
    
    console.log('📝 Extracted prompt:', prompt);
    return prompt;
}

// ==========================================
// CONTEXT-AWARE PROMPT ENHANCEMENT
// ==========================================
function enhancePromptWithContext(newMessage, previousPrompt) {
    const lowerMessage = newMessage.toLowerCase();
    
    const modificationKeywords = [
        'darker', 'lighter', 'bigger', 'smaller', 'brighter',
        'more colorful', 'less colorful', 'different color',
        'different style', 'another style', 'in the style of',
        'more', 'less', 'with', 'without', 'but', 'except'
    ];
    
    for (const keyword of modificationKeywords) {
        if (lowerMessage.includes(keyword)) {
            return `${previousPrompt}, ${newMessage}`;
        }
    }
    
    const retryKeywords = ['try again', 'different', 'new'];
    for (const keyword of retryKeywords) {
        if (lowerMessage.includes(keyword)) {
            return previousPrompt;
        }
    }
    
    return extractImagePrompt(newMessage);
}

// ==========================================
// POLLINATIONS IMAGE GENERATION
// ==========================================
async function generateImageWithPollinations(prompt) {
    try {
        const encodedPrompt = encodeURIComponent(prompt);
        const imageUrl = `https://image.pollinations.ai/prompt/${encodedPrompt}?width=1024&height=1024&nologo=true`;
        
        console.log('🌸 Pollinations URL:', imageUrl);
        
        await new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(imageUrl);
            img.onerror = () => reject(new Error('Image failed to load'));
            img.src = imageUrl;
        });
        
        return imageUrl;
    } catch (error) {
        console.error('❌ Pollinations error:', error);
        throw error;
    }
}

// ==========================================
// RESET STATE
// ==========================================
window.resetImageGenerationState = function() {
    window.imageGenerationState = {
        lastResponseWasImage: false,
        lastImagePrompt: null,
        lastImageUrl: null,
        conversationContext: []
    };
    console.log('🔄 Image generation state reset');
};

console.log('✅ Smart image generation v3.0 loaded - Fixed sensitivity');
