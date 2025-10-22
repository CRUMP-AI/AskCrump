// ==========================================
// CRUMP AI - ROBUST IMAGE GENERATION v2.12.0
// With validation, fallback, and retry logic
// ==========================================

// ==========================================
// MAIN IMAGE GENERATION HANDLER
// ==========================================
async function handleImageGeneration(message, retryCount = 0) {
    const prompt = extractImagePrompt(message);
    
    // Check usage limits FIRST
    if (window.profileManager) {
        const imageCheck = window.profileManager.canGenerateImage();
        
        if (!imageCheck.allowed) {
            window.hideThinking();
            addMessage('assistant', imageCheck.message);
            if (imageCheck.action === 'upgrade') {
                setTimeout(() => window.showUpgradePrompt(), 1000);
            }
            return;
        }
        
        if (imageCheck.warning) {
            window.showNotification(imageCheck.warning, 'info');
        }
    }
    
    window.showThinking();
    console.log(`🎨 Generating image: "${prompt}" (attempt ${retryCount + 1})`);
    
    try {
        // Try primary: Pollinations
        const imageUrl = await generateWithPollinations(prompt);
        
        // CRITICAL: Validate image before displaying
        console.log('🔍 Validating image...');
        const isValid = await validateImageUrl(imageUrl, 15000);
        
        if (isValid) {
            window.hideThinking();
            addMessage('assistant', `Here's your image: **"${prompt}"**`, imageUrl);
            console.log('✅ Image generated successfully');
            
            // Increment usage counter
            if (window.profileManager) {
                window.profileManager.incrementImageUsage();
            }
            
            return;
        }
        
        throw new Error('Image validation failed - image did not load properly');
        
    } catch (primaryError) {
        console.warn('⚠️ Pollinations failed:', primaryError.message);
        
        // Try fallback: Different Pollinations model
        try {
            console.log('🔄 Trying fallback model...');
            const fallbackUrl = await generateWithPollinationsFallback(prompt);
            const isValid = await validateImageUrl(fallbackUrl, 15000);
            
            if (isValid) {
                window.hideThinking();
                addMessage('assistant', `Here's your image: **"${prompt}"**\n\n*(Generated with fallback model)*`, fallbackUrl);
                console.log('✅ Fallback image generated');
                
                if (window.profileManager) {
                    window.profileManager.incrementImageUsage();
                }
                
                return;
            }
        } catch (fallbackError) {
            console.error('❌ Fallback also failed:', fallbackError.message);
        }
        
        // Final retry with exponential backoff
        if (retryCount < 2) {
            console.log(`🔄 Retry ${retryCount + 1}/2 after delay...`);
            const delay = (retryCount + 1) * 2000; // 2s, 4s
            await new Promise(resolve => setTimeout(resolve, delay));
            return handleImageGeneration(message, retryCount + 1);
        }
        
        // All attempts failed
        window.hideThinking();
        
        const errorMsg = `❌ **Image Generation Failed**

I couldn't generate your image after multiple attempts.

**Possible reasons:**
• Image generation service temporarily unavailable
• Prompt might violate content policy
• Network connectivity issues
• Server overload

**What you can try:**
1. **Simplify your prompt** - Try a shorter, clearer description
2. **Wait a minute** - Service might be temporarily down
3. **Try a different prompt** - Some phrases may be restricted

**Your prompt:** "${prompt}"

Would you like me to help you rephrase it?`;
        
        addMessage('assistant', errorMsg);
        console.error('❌ All image generation attempts failed');
    }
}

// ==========================================
// PRIMARY: POLLINATIONS (FLUX MODEL)
// ==========================================
async function generateWithPollinations(prompt) {
    const timestamp = Date.now();
    const encodedPrompt = encodeURIComponent(prompt);
    
    // Pollinations URL with best settings
    const imageUrl = `https://image.pollinations.ai/prompt/${encodedPrompt}?width=1024&height=1024&seed=${timestamp}&nologo=true&enhance=true&model=flux&safe=true`;
    
    console.log('🎨 Pollinations (Flux):', imageUrl.substring(0, 100) + '...');
    
    // Pre-warm the image (trigger generation on their server)
    try {
        await fetch(imageUrl, { 
            method: 'HEAD', 
            mode: 'no-cors',
            cache: 'no-cache'
        }).catch(() => {
            // Ignore CORS errors on HEAD request
        });
    } catch (e) {
        // Ignore
    }
    
    // Give Pollinations time to generate (they generate on-demand)
    await new Promise(resolve => setTimeout(resolve, 3000));
    
    return imageUrl;
}

// ==========================================
// FALLBACK: POLLINATIONS (TURBO MODEL)
// ==========================================
async function generateWithPollinationsFallback(prompt) {
    const timestamp = Date.now() + 1; // Different seed
    const encodedPrompt = encodeURIComponent(prompt);
    
    // Use faster "turbo" model as fallback
    const imageUrl = `https://image.pollinations.ai/prompt/${encodedPrompt}?width=1024&height=1024&seed=${timestamp}&nologo=true&model=flux-realism&safe=true`;
    
    console.log('🎨 Pollinations (Turbo):', imageUrl.substring(0, 100) + '...');
    
    try {
        await fetch(imageUrl, { 
            method: 'HEAD', 
            mode: 'no-cors',
            cache: 'no-cache'
        }).catch(() => {});
    } catch (e) {
        // Ignore
    }
    
    await new Promise(resolve => setTimeout(resolve, 2500));
    
    return imageUrl;
}

// ==========================================
// IMAGE URL VALIDATION
// ==========================================
async function validateImageUrl(url, timeout = 15000) {
    return new Promise((resolve) => {
        const img = new Image();
        
        const timeoutId = setTimeout(() => {
            console.warn('⏱️ Image validation timeout');
            img.src = ''; // Stop loading
            resolve(false);
        }, timeout);
        
        img.onload = () => {
            clearTimeout(timeoutId);
            
            // Check if it's a valid image (not an error page)
            if (img.naturalWidth > 0 && img.naturalHeight > 0) {
                // Check minimum size (error images are often tiny)
                if (img.naturalWidth >= 256 && img.naturalHeight >= 256) {
                    console.log(`✅ Image validated: ${img.naturalWidth}x${img.naturalHeight}`);
                    resolve(true);
                } else {
                    console.warn(`⚠️ Image too small: ${img.naturalWidth}x${img.naturalHeight}`);
                    resolve(false);
                }
            } else {
                console.warn('⚠️ Image loaded but dimensions are 0');
                resolve(false);
            }
        };
        
        img.onerror = (error) => {
            clearTimeout(timeoutId);
            console.error('❌ Image load error:', error);
            resolve(false);
        };
        
        // Start loading
        img.src = url;
    });
}

// ==========================================
// PROMPT EXTRACTION
// ==========================================
function extractImagePrompt(message) {
    let prompt = message.trim();
    
    // Remove common prefixes
    const prefixes = [
        'generate an image of ',
        'generate image of ',
        'generate a picture of ',
        'generate picture of ',
        'create an image of ',
        'create image of ',
        'create a picture of ',
        'create picture of ',
        'make an image of ',
        'make image of ',
        'make a picture of ',
        'make picture of ',
        'draw an image of ',
        'draw image of ',
        'draw a picture of ',
        'draw picture of ',
        'show me an image of ',
        'show me image of ',
        'show me a picture of ',
        'show me picture of ',
        'show me ',
        'generate ',
        'create ',
        'make ',
        'draw '
    ];
    
    const lowerPrompt = prompt.toLowerCase();
    
    for (const prefix of prefixes) {
        if (lowerPrompt.startsWith(prefix)) {
            prompt = prompt.substring(prefix.length).trim();
            break;
        }
    }
    
    // Remove "an image of" / "a picture of" from middle
    prompt = prompt.replace(/\b(an? )?(image|picture|photo|drawing) of /gi, '');
    
    return prompt;
}

// ==========================================
// IMAGE DETECTION
// ==========================================
function shouldGenerateImage(message) {
    const lower = message.toLowerCase();
    
    // Must have an action word
    const actionWords = ['generate', 'create', 'make', 'draw', 'design', 'show me', 'give me'];
    const hasAction = actionWords.some(word => lower.includes(word));
    
    // Must have an image noun
    const imageNouns = ['image', 'picture', 'photo', 'illustration', 'artwork', 'drawing', 'art'];
    const hasImageNoun = imageNouns.some(noun => lower.includes(noun));
    
    return hasAction && hasImageNoun;
}

// ==========================================
// EXPORT TO WINDOW
// ==========================================
window.handleImageGeneration = handleImageGeneration;
window.shouldGenerateImage = shouldGenerateImage;
window.extractImagePrompt = extractImagePrompt;
window.validateImageUrl = validateImageUrl;

console.log('✅ Robust image generation loaded');
