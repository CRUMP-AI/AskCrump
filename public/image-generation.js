/* ============================================
   CRUMP AI - ENHANCED IMAGE GENERATION
   Context-aware, Natural Language Detection
   ============================================ */

// Track conversation state
window.imageGenerationState = {
    lastResponseWasImage: false,
    lastImagePrompt: null,
    lastImageUrl: null,
    conversationContext: []
};

// ==========================================
// SMART IMAGE DETECTION (Enhanced)
// ==========================================
window.shouldGenerateImage = function(message) {
    if (!message || typeof message !== 'string') return false;
    
    const lowerMessage = message.toLowerCase().trim();
    
    // 1. FOLLOW-UP DETECTION (if last response was an image)
    if (window.imageGenerationState.lastResponseWasImage) {
        const followUpPhrases = [
            'try again', 'another one', 'different one', 'one more',
            'another', 'different', 'new one', 'remake', 'redo',
            'change it', 'modify it', 'adjust it', 'tweak it',
            'make it', 'do it', 'create it', 'show me',
            'more like', 'similar to', 'but with', 'except',
            'instead', 'rather', 'not that', 'better',
            'darker', 'lighter', 'bigger', 'smaller',
            'more colorful', 'less colorful', 'brighter', 'softer',
            'different style', 'different color', 'different size',
            'in a different', 'with a different', 'using a different'
        ];
        
        // Check if message is a follow-up request
        for (const phrase of followUpPhrases) {
            if (lowerMessage.includes(phrase)) {
                console.log('🔄 Follow-up image request detected');
                return true;
            }
        }
        
        // Short affirmative responses after image = wants another
        const shortAffirmatives = ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'yup'];
        if (shortAffirmatives.includes(lowerMessage) && lowerMessage.length < 10) {
            console.log('🔄 Affirmative follow-up detected');
            return true;
        }
    }
    
    // 2. EXPLICIT IMAGE KEYWORDS (Original)
    const explicitKeywords = [
        'generate', 'create', 'make', 'draw', 'design',
        'illustrate', 'render', 'produce', 'build', 'craft',
        'paint', 'sketch', 'compose', 'construct'
    ];
    
    const imageTypes = [
        'image', 'picture', 'photo', 'illustration', 'artwork',
        'graphic', 'visual', 'painting', 'drawing', 'render',
        'design', 'art', 'pic'
    ];
    
    // Check explicit patterns
    for (const keyword of explicitKeywords) {
        if (lowerMessage.includes(keyword)) {
            for (const type of imageTypes) {
                if (lowerMessage.includes(type)) {
                    console.log('🎨 Explicit image request detected');
                    return true;
                }
            }
        }
    }
    
    // 3. IMPLICIT IMAGE REQUESTS
    const implicitPatterns = [
        // Need/want patterns
        'i need a logo',
        'i need an icon',
        'i need a banner',
        'i need a header',
        'i need a background',
        'i want a logo',
        'i want an icon',
        'i want a banner',
        'need a logo for',
        'need an icon for',
        'need a banner for',
        'want a logo for',
        'want an icon for',
        
        // Show me patterns
        'show me a',
        'show me an',
        'show me what',
        'let me see a',
        'let me see an',
        
        // Can you patterns
        'can you make a',
        'can you make an',
        'can you create a',
        'can you create an',
        'can you draw a',
        'can you draw an',
        'can you design a',
        'can you design an',
        'could you make a',
        'could you create a',
        'could you draw a',
        'could you design a',
        
        // Would you patterns
        'would you make',
        'would you create',
        'would you draw',
        'would you design',
        
        // Visualization patterns
        'visualize a',
        'visualize an',
        'imagine a',
        'imagine an',
        'picture a',
        'picture an',
        
        // Logo/Brand specific
        'logo for',
        'icon for',
        'banner for',
        'header for',
        'thumbnail for',
        'cover for',
        'background for',
        'wallpaper for',
        'poster for',
        'flyer for',
        'card for',
        'badge for',
        
        // Art style indicators
        'in the style of',
        'watercolor of',
        'oil painting of',
        'sketch of',
        'cartoon of',
        'anime of',
        'realistic photo of',
        'abstract art of',
        'vector art of',
        'pixel art of',
        '3d render of',
        'photorealistic'
    ];
    
    for (const pattern of implicitPatterns) {
        if (lowerMessage.includes(pattern)) {
            console.log('🎨 Implicit image request detected:', pattern);
            return true;
        }
    }
    
    // 4. QUESTION PATTERNS ABOUT IMAGES
    const questionPatterns = [
        'what would',
        'how would',
        'what does',
        'how does',
        'what if'
    ];
    
    const visualVerbs = ['look like', 'appear', 'seem'];
    
    for (const qPattern of questionPatterns) {
        if (lowerMessage.includes(qPattern)) {
            for (const vVerb of visualVerbs) {
                if (lowerMessage.includes(vVerb)) {
                    console.log('🎨 Visual question detected');
                    return true;
                }
            }
        }
    }
    
    // 5. SINGLE WORD + "OF" PATTERN
    // "painting of a sunset", "drawing of a cat", etc.
    const singleWordImageTypes = [
        'painting', 'drawing', 'sketch', 'illustration',
        'photo', 'picture', 'image', 'render', 'graphic',
        'artwork', 'design', 'logo', 'icon', 'banner'
    ];
    
    for (const type of singleWordImageTypes) {
        const pattern = new RegExp(`\\b${type}\\s+of\\b`, 'i');
        if (pattern.test(message)) {
            console.log('🎨 Single-word pattern detected:', type);
            return true;
        }
    }
    
    // 6. CONTEXT-BASED: Check recent messages
    // If user mentioned images in last 2 messages, be more lenient
    const recentContext = window.imageGenerationState.conversationContext.slice(-2);
    const mentionedImagesRecently = recentContext.some(msg => 
        msg.includes('image') || msg.includes('picture') || msg.includes('visual')
    );
    
    if (mentionedImagesRecently) {
        // More lenient detection
        const contextualKeywords = [
            'that', 'this', 'it', 'one', 'another', 'different',
            'better', 'worse', 'similar', 'like that', 'like this'
        ];
        
        for (const keyword of contextualKeywords) {
            if (lowerMessage === keyword || lowerMessage.includes(keyword + ' ')) {
                console.log('🎨 Contextual image request detected');
                return true;
            }
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
// ENHANCED IMAGE GENERATION
// ==========================================
window.handleImageGeneration = async function(userMessage) {
    try {
        console.log('🎨 Generating image for:', userMessage);
        
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

        // Add user message
        const userMsg = {
            role: 'user',
            content: userMessage,
            timestamp: Date.now()
        };
        currentChat.messages.push(userMsg);
        currentChat.updatedAt = Date.now();
        
        if (typeof window.crumpDebug?.getCurrentChat === 'function') {
            const chats = JSON.parse(localStorage.getItem('crump_chats') || '[]');
            const chatIndex = chats.findIndex(c => c.id === currentChat.id);
            if (chatIndex !== -1) {
                chats[chatIndex] = currentChat;
                localStorage.setItem('crump_chats', JSON.stringify(chats));
            }
        }

        // Render user message
        if (typeof renderMessage === 'function') {
            renderMessage(userMsg);
        }

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
            content: `Here's your image:\n\n![Generated Image](${imageUrl})\n\nPrompt: "${prompt}"\n\nWould you like me to create a different version or modify this?`,
            timestamp: Date.now(),
            imageUrl: imageUrl
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

        // Re-render chat to show image
        const container = document.getElementById('chatContainer');
        container.innerHTML = '';
        currentChat.messages.forEach(msg => {
            if (!msg.generating && typeof renderMessage === 'function') {
                renderMessage(msg);
            }
        });
        
        if (typeof scrollToBottom === 'function') {
            scrollToBottom();
        }

        console.log('✅ Image generated successfully');

    } catch (error) {
        console.error('❌ Image generation error:', error);
        
        // Reset state on error
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
    
    // Remove common command words
    let prompt = message
        .replace(/^(generate|create|make|draw|design|illustrate|render|produce|show me|give me|i need|i want|can you|could you|would you|please)\s+(an?|the|some)?\s*/i, '')
        .replace(/\s*(image|picture|photo|illustration|artwork|graphic|visual|painting|drawing|render|design|art|pic)\s*(of|for|with|about)?\s*/i, ' ')
        .trim();
    
    // If prompt is too short or empty, use full message
    if (prompt.length < 3) {
        prompt = message;
    }
    
    // Clean up
    prompt = prompt
        .replace(/^(of|for|with|about)\s+/i, '')
        .replace(/\s+/g, ' ')
        .trim();
    
    console.log('📝 Extracted prompt:', prompt);
    return prompt;
}

// ==========================================
// CONTEXT-AWARE PROMPT ENHANCEMENT
// ==========================================
function enhancePromptWithContext(newMessage, previousPrompt) {
    const lowerMessage = newMessage.toLowerCase();
    
    // If asking for modifications
    const modificationKeywords = [
        'darker', 'lighter', 'bigger', 'smaller', 'brighter',
        'more colorful', 'less colorful', 'different color',
        'different style', 'another style', 'in the style of',
        'more', 'less', 'with', 'without', 'but', 'except'
    ];
    
    for (const keyword of modificationKeywords) {
        if (lowerMessage.includes(keyword)) {
            // Combine previous prompt with modification
            return `${previousPrompt}, ${newMessage}`;
        }
    }
    
    // If asking for "try again" or "another", use similar prompt
    const retryKeywords = ['try again', 'another', 'different', 'one more', 'new'];
    for (const keyword of retryKeywords) {
        if (lowerMessage.includes(keyword)) {
            return previousPrompt; // Use same prompt
        }
    }
    
    // Otherwise, extract new prompt
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
        
        // Preload image to verify it works
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
// RESET STATE (call when starting new chat)
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

console.log('✅ Enhanced image generation loaded');
