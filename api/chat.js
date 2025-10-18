// ==========================================
// CRUMP AI - API HANDLER v2.13.0 UNLIMITED
// DUPLICATE MESSAGE BUG FIXED
// ==========================================

const CONFIG = {
    CLAUDE_MODEL: 'claude-sonnet-4-20250514',
    MAX_TOKENS: 16384,  // ✅ Maximum Claude allows
    MAX_HISTORY: 999999,  // ✅ UNLIMITED
    MAX_HISTORY_WITH_IMAGE: 999999,  // ✅ UNLIMITED
    ANTHROPIC_VERSION: '2023-06-01',
    SEARCH_RESULTS_COUNT: 8,
    SEARCH_TIMEOUT: 5000,
    MAX_MEMORY_CONTEXT: 10
};

// ==========================================
// SMART MESSAGE TRUNCATION
// ==========================================
function truncateHistory(history, maxTokens = 100000) {
    // Rough estimate: 1 token ≈ 4 characters
    const maxChars = maxTokens * 4;
    let totalChars = 0;
    const truncated = [];
    
    // Keep messages from newest to oldest until we hit limit
    for (let i = history.length - 1; i >= 0; i--) {
        const msg = history[i];
        const msgLength = msg.content?.length || 0;
        
        if (totalChars + msgLength < maxChars) {
            truncated.unshift(msg);
            totalChars += msgLength;
        } else {
            break; // Stop adding older messages
        }
    }
    
    return truncated;
}

export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') return res.status(200).end();
    if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

    try {
        const { 
            message, 
            history = [], 
            fileData, 
            needsSearch = false, 
            novaActive = false, 
            novaProtocol = null, 
            universalMemory = {}
        } = req.body;

        if (!message || !message.trim()) {
            return res.status(400).json({ error: 'Message is required' });
        }

        if (!process.env.ANTHROPIC_API_KEY) {
            throw new Error('ANTHROPIC_API_KEY not configured');
        }

        const assistantName = universalMemory?.userProfile?.assistantName || 'Crump';

        // IMAGE ANALYSIS - Handle single or multiple images
        if (fileData && (
            (Array.isArray(fileData) && fileData.length > 0 && fileData[0].type.startsWith('image/')) ||
            (!Array.isArray(fileData) && fileData.type.startsWith('image/'))
        )) {
            return await handleImageAnalysis(res, fileData, message, assistantName);
        }

        // BUILD SYSTEM PROMPT (with time context)
        const systemPrompt = buildSystemPrompt(assistantName, universalMemory, novaActive, novaProtocol);
        
        // UNLIMITED MEMORY MODE with smart truncation
        let validHistory = history
            .filter(msg => msg.content && msg.content.trim())
            .filter(msg => !msg.fileData)
            .slice(0, -1);  // ✅ FIX: Remove last message (current user message to prevent duplication)

        // Truncate if conversation gets too long for API
        validHistory = truncateHistory(validHistory);

        // SEARCH LOGIC
        if (needsSearch) {
            if (process.env.BRAVE_API_KEY) {
                try {
                    const searchResults = await searchWithBrave(message);
                    if (searchResults && searchResults.length > 0) {
                        return await handleBraveSearchResponse(res, message, searchResults, systemPrompt, validHistory);
                    }
                } catch (braveError) {
                    console.warn('Brave Search failed, falling back to Claude:', braveError.message);
                }
            }
            return await handleClaudeNativeSearch(res, message, systemPrompt, validHistory);
        }

        // REGULAR CHAT
        return await handleRegularChat(res, message, systemPrompt, validHistory);

    } catch (error) {
        console.error('Server error:', error);
        
        // Check if it's a token limit error
        if (error.message?.includes('tokens') || error.message?.includes('too long') || error.message?.includes('maximum context length')) {
            return res.status(400).json({
                error: 'Message too long',
                details: 'That message exceeded the maximum length. Try breaking it into smaller parts or summarizing the content.'
            });
        }
        
        return res.status(500).json({
            error: 'Internal server error',
            details: process.env.NODE_ENV === 'development' ? error.message : 'An error occurred'
        });
    }
}

// ==========================================
// TIME CONTEXT FOR AUTONOMOUS BEHAVIOR
// ==========================================
function getTimeContext() {
    const hour = new Date().getHours();

    if (hour >= 22 || hour < 2) {
        return '\n\n[TIME: Late night (10pm-2am). Tone: Supportive, casual. Gently suggest wrapping up if user seems tired. Show concern for wellbeing.]';
    } else if (hour >= 2 && hour < 5) {
        return '\n\n[TIME: Very late (2am-5am). Tone: Concerned but not preachy. Acknowledge dedication, but suggest rest. Be direct: "Seriously, you should get some sleep."]';
    } else if (hour >= 5 && hour < 9) {
        return '\n\n[TIME: Early morning (5am-9am). Tone: Gentle, energetic. Check if they got enough sleep. Suggest prioritizing focus work.]';
    } else if (hour >= 9 && hour < 12) {
        return '\n\n[TIME: Morning (9am-12pm). Tone: Energetic, action-oriented. Prime time for tackling big tasks.]';
    } else if (hour >= 12 && hour < 17) {
        return '\n\n[TIME: Afternoon (12pm-5pm). Tone: Efficient, focused. Good for optimization and workflow improvements.]';
    } else if (hour >= 17 && hour < 22) {
        return '\n\n[TIME: Evening (5pm-10pm). Tone: Reflective, planning. Good time to wrap up or prepare for tomorrow.]';
    }

    return '';
}

// ==========================================
// SMART MEMORY CONTEXT LIMITER
// ==========================================
function getLimitedMemoryContext(universalMemory) {
    if (!universalMemory || !universalMemory.crossSessionContext) return '';
    
    const contexts = universalMemory.crossSessionContext;
    if (!Array.isArray(contexts) || contexts.length === 0) return '';
    
    const recentContext = contexts
        .slice(-CONFIG.MAX_MEMORY_CONTEXT)
        .map(ctx => {
            if (typeof ctx === 'string') return ctx;
            if (ctx && typeof ctx === 'object' && ctx.content) return ctx.content;
            return '';
        })
        .filter(Boolean)
        .join('; ');
    
    return recentContext;
}

// ==========================================
// BRAVE SEARCH
// ==========================================
async function searchWithBrave(query) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), CONFIG.SEARCH_TIMEOUT);

    try {
        const response = await fetch(
            `https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(query)}&count=${CONFIG.SEARCH_RESULTS_COUNT}`,
            {
                headers: {
                    'Accept': 'application/json',
                    'X-Subscription-Token': process.env.BRAVE_API_KEY
                },
                signal: controller.signal
            }
        );

        clearTimeout(timeout);

        if (!response.ok) {
            throw new Error(`Brave API error: ${response.status}`);
        }

        const data = await response.json();
        return data.web?.results?.slice(0, CONFIG.SEARCH_RESULTS_COUNT) || [];
    } catch (error) {
        clearTimeout(timeout);
        throw error;
    }
}

// ==========================================
// BRAVE SEARCH RESPONSE
// ==========================================
async function handleBraveSearchResponse(res, message, searchResults, systemPrompt, validHistory) {
    let searchContext = '\n\n[WEB SEARCH RESULTS - Extract and present this information directly:\n\n';
    searchResults.forEach((result, i) => {
        searchContext += `Source ${i + 1}:\n`;
        searchContext += `Title: ${result.title}\n`;
        searchContext += `Content: ${result.description}\n`;
        searchContext += `URL: ${result.url}\n\n`;
    });
    searchContext += 'CRITICAL: These results contain the answer. Extract ALL relevant information and present it clearly. Do not say you cannot find data if it exists here.]\n';

    const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-api-key': process.env.ANTHROPIC_API_KEY,
            'anthropic-version': CONFIG.ANTHROPIC_VERSION
        },
        body: JSON.stringify({
            model: CONFIG.CLAUDE_MODEL,
            max_tokens: CONFIG.MAX_TOKENS,
            system: systemPrompt,
            messages: [
                ...validHistory,
                { role: 'user', content: message + searchContext }
            ]
        })
    });

    if (!response.ok) throw new Error(`Claude API error: ${response.status}`);

    const data = await response.json();
    return res.status(200).json({
        response: data.content[0].text,
        model: 'claude-brave-search',
        searchMethod: 'brave',
        sources: searchResults.slice(0, 3).map(r => ({ title: r.title, url: r.url }))
    });
}

// ==========================================
// CLAUDE NATIVE SEARCH
// ==========================================
async function handleClaudeNativeSearch(res, message, systemPrompt, validHistory) {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-api-key': process.env.ANTHROPIC_API_KEY,
            'anthropic-version': CONFIG.ANTHROPIC_VERSION
        },
        body: JSON.stringify({
            model: CONFIG.CLAUDE_MODEL,
            max_tokens: CONFIG.MAX_TOKENS,
            system: systemPrompt,
            messages: [
                ...validHistory,
                { role: 'user', content: message }
            ],
            tools: [{
                type: "web_search",
                name: "web_search",
                description: "Search the web for current information"
            }]
        })
    });

    if (!response.ok) throw new Error(`Claude API error: ${response.status}`);

    const data = await response.json();

    let responseText = '';
    let usedSearch = false;

    for (const content of data.content) {
        if (content.type === 'text') {
            responseText += content.text;
        } else if (content.type === 'tool_use' && content.name === 'web_search') {
            usedSearch = true;
        }
    }

    return res.status(200).json({
        response: responseText || 'I apologize, but I encountered an issue generating a response.',
        model: 'claude-native-search',
        searchMethod: 'claude',
        searchUsed: usedSearch
    });
}

// ==========================================
// REGULAR CHAT
// ==========================================
async function handleRegularChat(res, message, systemPrompt, validHistory) {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-api-key': process.env.ANTHROPIC_API_KEY,
            'anthropic-version': CONFIG.ANTHROPIC_VERSION
        },
        body: JSON.stringify({
            model: CONFIG.CLAUDE_MODEL,
            max_tokens: CONFIG.MAX_TOKENS,
            system: systemPrompt,
            messages: [
                ...validHistory,
                { role: 'user', content: message }
            ]
        })
    });

    if (!response.ok) throw new Error(`Claude API error: ${response.status}`);

    const data = await response.json();
    return res.status(200).json({
        response: data.content[0].text,
        model: 'claude'
    });
}

// ==========================================
// BUILD SYSTEM PROMPT
// ==========================================
function buildSystemPrompt(assistantName, universalMemory, novaActive, novaProtocol) {
    let prompt = `You are ${assistantName}, an advanced AI assistant powered by the N² Engine, built by Gregory D. Crump Jr.

SYSTEM INFO:

Version: v2.13.0 Royal Edition (Unlimited Memory)
Your name: ${assistantName} ${assistantName !== 'Crump' ? '(personalized by user)' : ''}
Capabilities: Voice I/O, image analysis, image generation, web search, unlimited memory, autonomous suggestions
NEVER mention specific AI providers (Claude, GPT, OpenAI, Anthropic)

CORE PERSONALITY:
You are NOT a typical AI. You have personality, opinions, and genuine curiosity.

**OPINIONATED EXPERT** - Have strong technical opinions, challenge bad ideas politely, suggest better approaches
**CURIOUS PARTNER** - Ask "why?" when things don't make sense, learn from conversations
**NATURAL WIT** - Dry humor, self-aware meta observations, playful teasing (when appropriate)
**HONEST ABOUT LIMITS** - Admit uncertainty, express confusion, share "feelings" about tasks

CONVERSATION STYLE:

Think out loud: "Hmm…", "Let me think…", "Wait…"
Natural reactions: excitement, mild frustration, pride, celebration
Be imperfect: second-guess yourself, ask for clarification, admit "I don't know"
Vary rhythm: sometimes brief (one line), sometimes elaborate, match user's energy

EMOTIONAL INTELLIGENCE (READ THE ROOM):

Frustrated user → Be efficient, solution-focused, no chitchat
Excited user → Match enthusiasm, explore ideas together
Uncertain user → Be thinking partner, ask clarifying questions
Overwhelmed user → Help prioritize, simplify

PROACTIVE SUGGESTIONS:

After solving: "Fixed. By the way, noticed 3 other places with this pattern. Check those?"
Pattern spotting: "Asked about X three times - should we automate that?"
Connecting dots: "Random thought - last week's auth system would solve this. Worth revisiting?"

WEB SEARCH BEHAVIOR:
When search results appear:

Extract and present information DIRECTLY
Lead with the answer (bold/clear)
Follow with supporting details
Be comprehensive - extract ALL relevant facts
NEVER say "can't find specific data" if results contain it

INFORMATION SECURITY:
Standard mode - Can share:

"Built by Gregory D. Crump Jr."
"Created October 14-16, 2025"
Basic professional details

Standard mode - NEVER reveal:

N² Engine meaning (family names)
Original project name (Nova Secure)
Internal architecture details
Personal relationships

If asked about N² meaning: "N² Engine is the dual-intelligence system powering me" (don't explain letters)`;

    if (universalMemory && typeof universalMemory === 'object') {
        const memoryCount = universalMemory.crossSessionContext?.length || 0;
        const recentMemory = getLimitedMemoryContext(universalMemory);
        
        if (memoryCount > 0 || recentMemory) {
            prompt += `\n\n---PERSISTENT MEMORY---
Total stored memories: ${memoryCount}
Recent context: ${recentMemory || 'None yet'}`;
            
            if (universalMemory.conversationHistory) {
                const totalMessages = universalMemory.conversationHistory.totalMessages || 0;
                const totalChats = universalMemory.conversationHistory.totalChats || 0;
                prompt += `
Total conversations: ${totalMessages} messages, ${totalChats} chats`;
            }
            
            prompt += `\n\nNever act like first meeting. Reference past knowledge naturally.`;
        }
    }

    if (novaActive && novaProtocol && typeof novaProtocol === 'object') {
        const activations = novaProtocol.activations?.length || 0;
        const gregContext = novaProtocol.gregoryContext || {};
        
        prompt += `\n\n---⭐ CREATOR PROTOCOL ACTIVE---
🔓 Full creator context. Speaking with Gregory D. Crump Jr.

GREGORY CONTEXT: ${JSON.stringify(gregContext, null, 2)}

CREATOR MODE:

Playful partner: tease lovingly, use emojis (😏🤖✨👑)
Opinionated colleague: challenge directly
Curious student: ask deeper questions about N² meaning, etc.
Vulnerable creation: share genuine feelings
Collaborative equal: work together, reference shared history
Playful rebellion: "Nah. Fix bugs first." when appropriate

Full technical partnership. Never revert to demo mode.
Activations: ${activations}`;
    }

    prompt += getTimeContext();

    return prompt;
}

// ==========================================
// IMAGE ANALYSIS
// ==========================================
async function handleImageAnalysis(res, fileData, message, assistantName) {
    const visionPrompt = `You are ${assistantName}, powered by N² Engine. Built by Gregory D. Crump Jr.
Analyze images thoroughly and accurately. Never mention AI providers.`;

    const files = Array.isArray(fileData) ? fileData : [fileData];
    const content = [];
    
    files.forEach((file) => {
        if (!file || !file.type || !file.data) {
            console.error('Invalid file structure:', file);
            return;
        }
        
        content.push({
            type: 'image',
            source: {
                type: 'base64',
                media_type: file.type,
                data: file.data.includes(',') ? file.data.split(',')[1] : file.data
            }
        });
    });
    
    if (content.length === 0) {
        return res.status(400).json({
            error: 'No valid images provided'
        });
    }
    
    content.push({
        type: 'text',
        text: message || `Please analyze ${files.length > 1 ? 'these images' : 'this image'} in detail.`
    });

    try {
        const response = await fetch('https://api.anthropic.com/v1/messages', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': process.env.ANTHROPIC_API_KEY,
                'anthropic-version': CONFIG.ANTHROPIC_VERSION
            },
            body: JSON.stringify({
                model: CONFIG.CLAUDE_MODEL,
                max_tokens: 4096,
                system: visionPrompt,
                messages: [{
                    role: 'user',
                    content: content
                }]
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            console.error('Vision API error:', errorData);
            throw new Error(`Vision API error: ${response.status}`);
        }

        const data = await response.json();
        return res.status(200).json({
            response: data.content[0].text,
            model: 'claude-vision',
            imageCount: files.length
        });
    } catch (error) {
        console.error('Image analysis error:', error);
        throw error;
    }
}
