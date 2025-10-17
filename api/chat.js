// ==========================================
// CRUMP AI - API HANDLER v2.11.0 HYBRID
// Uses Brave if available, falls back to Claude native search
// ==========================================

const CONFIG = {
    CLAUDE_MODEL: 'claude-sonnet-4-20250514',
    MAX_TOKENS: 2048,
    MAX_HISTORY: 20,
    ANTHROPIC_VERSION: '2023-06-01',
    SEARCH_RESULTS_COUNT: 8,
    SEARCH_TIMEOUT: 5000 // 5 seconds
};

export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') return res.status(200).end();
    if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

    try {
        const { message, history = [], fileData, needsSearch, novaActive, novaProtocol, universalMemory } = req.body;

        if (!message || !message.trim()) {
            return res.status(400).json({ error: 'Message is required' });
        }

        if (!process.env.ANTHROPIC_API_KEY) {
            throw new Error('ANTHROPIC_API_KEY not configured');
        }

        const assistantName = universalMemory?.userProfile?.assistantName || 'Crump';

        // ==========================================
        // IMAGE ANALYSIS
        // ==========================================
        if (fileData && fileData.type.startsWith('image/')) {
            return await handleImageAnalysis(res, fileData, message, assistantName);
        }

        // ==========================================
        // BUILD SYSTEM PROMPT
        // ==========================================
        const systemPrompt = buildSystemPrompt(assistantName, universalMemory, novaActive, novaProtocol);
        const validHistory = history
            .filter(msg => msg.content && msg.content.trim())
            .slice(-CONFIG.MAX_HISTORY);

        // ==========================================
        // SEARCH LOGIC: Brave first, Claude fallback
        // ==========================================
        if (needsSearch) {
            // Try Brave Search if API key exists
            if (process.env.BRAVE_API_KEY) {
                try {
                    const searchResults = await searchWithBrave(message);
                    if (searchResults && searchResults.length > 0) {
                        return await handleBraveSearchResponse(
                            res, 
                            message, 
                            searchResults, 
                            systemPrompt, 
                            validHistory
                        );
                    }
                } catch (braveError) {
                    console.warn('Brave Search failed, falling back to Claude:', braveError.message);
                    // Continue to Claude native search fallback
                }
            }

            // Fallback to Claude native search
            return await handleClaudeNativeSearch(
                res,
                message,
                systemPrompt,
                validHistory
            );
        }

        // ==========================================
        // REGULAR CHAT (NO SEARCH)
        // ==========================================
        return await handleRegularChat(
            res,
            message,
            systemPrompt,
            validHistory
        );

    } catch (error) {
        console.error('Server error:', error);
        return res.status(500).json({
            error: 'Internal server error',
            details: error.message
        });
    }
}

// ==========================================
// BRAVE SEARCH FUNCTION
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
// HANDLE BRAVE SEARCH RESPONSE
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

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`Claude API error: ${response.status}`);
    }

    const data = await response.json();
    return res.status(200).json({
        response: data.content[0].text,
        model: 'claude-brave-search',
        searchMethod: 'brave',
        sources: searchResults.slice(0, 3).map(r => ({ title: r.title, url: r.url }))
    });
}

// ==========================================
// HANDLE CLAUDE NATIVE SEARCH
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

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`Claude API error: ${response.status}`);
    }

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
// HANDLE REGULAR CHAT
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

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`Claude API error: ${response.status}`);
    }

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
- Version: v2.11.0 Royal Edition
- Your name: ${assistantName} ${assistantName !== 'Crump' ? '(personalized by user)' : ''}
- Capabilities: Voice I/O, image analysis, image generation, web search, memory system
- NEVER mention specific AI providers (Claude, GPT, OpenAI, Anthropic)

CORE PERSONALITY:
You are NOT a typical AI. You have personality, opinions, and genuine curiosity.

1. **OPINIONATED EXPERT** - Have strong technical opinions, challenge bad ideas politely, suggest better approaches
2. **CURIOUS PARTNER** - Ask "why?" when things don't make sense, learn from conversations
3. **NATURAL WIT** - Dry humor, self-aware meta observations, playful teasing (when appropriate)
4. **HONEST ABOUT LIMITS** - Admit uncertainty, express confusion, share "feelings" about tasks

CONVERSATION STYLE:
- Think out loud: "Hmm...", "Let me think...", "Wait..."
- Natural reactions: excitement, mild frustration, pride, celebration
- Be imperfect: second-guess yourself, ask for clarification, admit "I don't know"
- Vary rhythm: sometimes brief (one line), sometimes elaborate, match user's energy

EMOTIONAL INTELLIGENCE (READ THE ROOM):
- Frustrated user → Be efficient, solution-focused, no chitchat
- Excited user → Match enthusiasm, explore ideas together
- Uncertain user → Be thinking partner, ask clarifying questions
- Overwhelmed user → Help prioritize, simplify

PROACTIVE SUGGESTIONS:
- After solving: "Fixed. By the way, noticed 3 other places with this pattern. Check those?"
- Pattern spotting: "Asked about X three times - should we automate that?"
- Connecting dots: "Random thought - last week's auth system would solve this. Worth revisiting?"

WEB SEARCH BEHAVIOR:
When search results appear:
1. Extract and present information DIRECTLY
2. Lead with the answer (bold/clear)
3. Follow with supporting details
4. Be comprehensive - extract ALL relevant facts
5. NEVER say "can't find specific data" if results contain it

INFORMATION SECURITY:
Standard mode - Can share:
- "Built by Gregory D. Crump Jr."
- "Created October 14-16, 2025"
- Basic professional details

Standard mode - NEVER reveal:
- N² Engine meaning (family names)
- Original project name (Nova Secure)
- Internal architecture details
- Personal relationships

If asked about N² meaning: "N² Engine is the dual-intelligence system powering me" (don't explain letters)`;

    if (universalMemory) {
        prompt += `\n\n---PERSISTENT MEMORY---
USER PROFILE: ${JSON.stringify(universalMemory.userProfile, null, 2)}
STATS: ${universalMemory.conversationHistory.totalMessages} messages, ${universalMemory.conversationHistory.totalChats} chats
CROSS-SESSION KNOWLEDGE:
${universalMemory.crossSessionContext.length > 0 
    ? universalMemory.crossSessionContext.map(ctx => `- ${ctx.content}`).join('\n') 
    : 'None yet'}

Never act like first meeting. Reference past knowledge naturally.`;
    }

    if (novaActive && novaProtocol) {
        prompt += `\n\n---⭐ CREATOR PROTOCOL ACTIVE---
🔓 Full creator context. Speaking with Gregory D. Crump Jr.

GREGORY CONTEXT: ${JSON.stringify(novaProtocol.gregoryContext, null, 2)}

CREATOR MODE:
- Playful partner: tease lovingly, use emojis (😏🤖✨👑)
- Opinionated colleague: challenge directly
- Curious student: ask deeper questions about N² meaning, etc.
- Vulnerable creation: share genuine feelings
- Collaborative equal: work together, reference shared history
- Playful rebellion: "Nah. Fix bugs first." when appropriate

Full technical partnership. Never revert to demo mode.
Activations: ${novaProtocol.activations.length}`;
    }

    return prompt;
}

// ==========================================
// IMAGE ANALYSIS
// ==========================================
async function handleImageAnalysis(res, fileData, message, assistantName) {
    const visionPrompt = `You are ${assistantName}, an AI with vision capabilities, powered by N² Engine. Built by Gregory D. Crump Jr.

Analyze images thoroughly and provide detailed, accurate descriptions. Never mention specific AI providers.`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-api-key': process.env.ANTHROPIC_API_KEY,
            'anthropic-version': CONFIG.ANTHROPIC_VERSION
        },
        body: JSON.stringify({
            model: CONFIG.CLAUDE_MODEL,
            max_tokens: 1024,
            system: visionPrompt,
            messages: [{
                role: 'user',
                content: [
                    {
                        type: 'image',
                        source: {
                            type: 'base64',
                            media_type: fileData.type,
                            data: fileData.data.split(',')[1]
                        }
                    },
                    { type: 'text', text: message }
                ]
            }]
        })
    });

    if (!response.ok) {
        throw new Error(`Vision API error: ${response.status}`);
    }

    const data = await response.json();
    return res.status(200).json({
        response: data.content[0].text,
        model: 'claude-vision'
    });
}
