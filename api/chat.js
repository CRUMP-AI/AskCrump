// ==========================================
// CRUMP AI - API HANDLER v2.15.2 FIXED
// BODY PARSING FIX + ALL PREVIOUS FIXES
// ==========================================

const CONFIG = {
    CLAUDE_MODEL: 'claude-sonnet-4-5-20250929',
    MAX_TOKENS: 8192,
    MAX_HISTORY: 999999,
    MAX_HISTORY_WITH_IMAGE: 999999,
    ANTHROPIC_VERSION: '2023-06-01',
    SEARCH_RESULTS_COUNT: 8,
    SEARCH_TIMEOUT: 55000,
    MAX_MEMORY_CONTEXT: 10,
    API_TIMEOUT: 55000
};

// ==========================================
// BODY PARSER HELPER
// ==========================================
async function parseBody(req) {
    // If body is already parsed, return it
    if (req.body && typeof req.body === 'object') {
        return req.body;
    }
    
    // If body is a string, parse it
    if (typeof req.body === 'string') {
        try {
            return JSON.parse(req.body);
        } catch (e) {
            console.error('Failed to parse body string:', e);
            return null;
        }
    }
    
    // Manual parsing for raw requests
    return new Promise((resolve) => {
        let data = '';
        req.on('data', chunk => {
            data += chunk;
        });
        req.on('end', () => {
            try {
                resolve(JSON.parse(data));
            } catch (e) {
                console.error('Failed to parse request data:', e);
                resolve(null);
            }
        });
    });
}

// ==========================================
// STRICT MESSAGE VALIDATION (FIXES 400 ERROR)
// ==========================================
function validateAndCleanMessages(messages) {
    if (!Array.isArray(messages)) {
        console.warn('⚠️ Messages is not an array:', typeof messages);
        return [];
    }
    
    return messages
        .filter(msg => {
            // Must have role and content
            if (!msg || typeof msg !== 'object') {
                console.warn('⚠️ Invalid message object:', msg);
                return false;
            }
            
            if (!msg.role || (msg.role !== 'user' && msg.role !== 'assistant')) {
                console.warn('⚠️ Invalid role:', msg.role);
                return false;
            }
            
            if (!msg.content || typeof msg.content !== 'string' || !msg.content.trim()) {
                console.warn('⚠️ Invalid content for message');
                return false;
            }
            
            // Skip messages with file data (handled separately)
            if (msg.fileData || msg.files) {
                return false;
            }
            
            return true;
        })
        .map(msg => ({
            role: msg.role,
            content: msg.content.trim()
        }));
}

// ==========================================
// SMART MESSAGE TRUNCATION
// ==========================================
function truncateHistory(history, maxTokens = 180000) {
    const maxChars = maxTokens * 4;
    let totalChars = 0;
    const truncated = [];
    
    for (let i = history.length - 1; i >= 0; i--) {
        const msg = history[i];
        const msgLength = msg.content?.length || 0;
        
        if (totalChars + msgLength < maxChars) {
            truncated.unshift(msg);
            totalChars += msgLength;
        } else {
            break;
        }
    }
    
    return truncated;
}

export default async function handler(req, res) {
    console.log('📊 API Request received');
    console.log('📊 Method:', req.method);
    
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') return res.status(200).end();
    if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

    try {
        // PARSE BODY (FIX FOR UNDEFINED req.body)
        const body = await parseBody(req);
        
        if (!body) {
            console.error('❌ Failed to parse request body');
            return res.status(400).json({ error: 'Invalid request body' });
        }
        
        console.log('📊 Body parsed successfully');
        console.log('📊 Message length:', body.message?.length || 0);
        console.log('📊 History count:', body.history?.length || 0);
        console.log('📊 Has file:', !!body.fileData);
        
       const { 
            message, 
            history = [], 
            currentDateTime,
            fileData, 
            needsSearch = false,
            needsWeather = false,
            novaActive = false, 
            novaProtocol = null, 
            universalMemory = {},
            workMode = 'companion'
        } = body;

        // VALIDATE MESSAGE
        if (!message || typeof message !== 'string' || !message.trim()) {
            console.error('❌ Invalid message:', message);
            return res.status(400).json({ error: 'Valid message is required' });
        }

        if (!process.env.ANTHROPIC_API_KEY) {
            console.error('❌ ANTHROPIC_API_KEY not configured');
            throw new Error('ANTHROPIC_API_KEY not configured');
        }

        const assistantName = universalMemory?.userProfile?.assistantName || 'Crump';

        // IMAGE ANALYSIS - Handle single or multiple images
        if (fileData && (
            (Array.isArray(fileData) && fileData.length > 0 && fileData[0].type?.startsWith('image/')) ||
            (!Array.isArray(fileData) && fileData.type?.startsWith('image/'))
        )) {
            console.log('🖼️ Image analysis requested');
            return await handleImageAnalysis(res, fileData, message, assistantName);
        }

       // BUILD SYSTEM PROMPT
        let systemPrompt = buildSystemPrompt(assistantName, universalMemory, novaActive, novaProtocol, req, workMode, currentDateTime);
        
        // WEATHER LOGIC - MUST COME FIRST
        let weatherData = null;
        if (needsWeather) {
            console.log('🌤️ Weather requested');
            try {
                const BASE_URL = req.headers.host?.includes('localhost') 
                    ? 'http://localhost:3000' 
                    : `https://${req.headers.host}`;
                
                const weatherResponse = await fetch(`${BASE_URL}/api/weather.js`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        query: message,
                        context: 'chat'
                    })
                });
                
                if (weatherResponse.ok) {
                    const weatherJson = await weatherResponse.json();
                    if (weatherJson.success) {
                        weatherData = weatherJson.formatted;
                        console.log('✅ Weather data retrieved for', weatherJson.location);
                    }
                }
            } catch (weatherError) {
                console.warn('⚠️ Weather API failed:', weatherError.message);
            }
        }
        
        // Add weather data to system prompt if available
        if (weatherData) {
            systemPrompt += `\n\n<current_weather>\n${weatherData}\n</current_weather>\n\nThe user asked about weather. Use the data above to answer their question naturally.`;
        }
        
        // VALIDATE AND CLEAN HISTORY
        console.log('🔍 Validating message history...');
        let validHistory = validateAndCleanMessages(history);
        console.log('✅ Valid messages after cleaning:', validHistory.length);
        
        // Remove last message (the current one being sent)
        validHistory = validHistory.slice(0, -1);
        
        // Truncate if conversation gets too long
        validHistory = truncateHistory(validHistory);
        
        console.log('📤 Sending to Claude with', validHistory.length, 'history messages');

        // SEARCH LOGIC
        if (needsSearch) {
            console.log('🔍 Search requested');
            if (process.env.BRAVE_API_KEY) {
                try {
                    const searchResults = await searchWithBrave(message);
                    if (searchResults && searchResults.length > 0) {
                        console.log('✅ Brave search returned', searchResults.length, 'results');
                        return await handleBraveSearchResponse(res, message, searchResults, systemPrompt, validHistory);
                    }
                } catch (braveError) {
                    console.warn('⚠️ Brave Search failed, falling back to Claude:', braveError.message);
                }
            }
            console.log('🔄 Using Claude native search');
            return await handleClaudeNativeSearch(res, message, systemPrompt, validHistory);
        }

        // REGULAR CHAT
        console.log('💬 Regular chat request');
        return await handleRegularChat(res, message, systemPrompt, validHistory);

    } catch (error) {
        console.error('❌ Server error:', error);
        console.error('Error name:', error.name);
        console.error('Error message:', error.message);
        console.error('Error stack:', error.stack);
        
        // Handle timeout errors specifically
        if (error.name === 'AbortError') {
            console.error('⏱️ Request timed out');
            return res.status(504).json({
                error: 'Request timeout',
                details: 'The AI took too long to respond. Try a shorter message or simpler request.'
            });
        }
        
        if (error.message?.includes('tokens') || error.message?.includes('too long') || error.message?.includes('maximum context length')) {
            console.error('📏 Message/context too long');
            return res.status(400).json({
                error: 'Message too long',
                details: 'That message exceeded the maximum length. Try breaking it into smaller parts or summarizing the content.'
            });
        }
        
        if (error.message?.includes('Claude API error')) {
            console.error('🔴 Claude API error');
            return res.status(502).json({
                error: 'AI service error',
                details: 'The AI service encountered an error. Please try again.'
            });
        }
        
        return res.status(500).json({
            error: 'Internal server error',
            details: process.env.NODE_ENV === 'development' ? error.message : 'An error occurred'
        });
    }
}

// Rest of the functions remain the same...
// (I'll add them in the next part to keep the file complete)

// ==========================================
// TIME CONTEXT FOR AUTONOMOUS BEHAVIOR
// ==========================================
function getTimeContext() {
    const hour = new Date().getHours();

    if (hour >= 22 || hour < 2) {
        return '\n\n[TIME: Late night (10pm-2am). Tone: Supportive, casual. Gently suggest wrapping up if user seems tired. Show concern for wellbeing.]';
    } else if (hour >= 2 && hour < 5) {
        return '\n\n[TIME: Very late (2am-5am). Tone: Concerned but not preachy. Acknowledge dedication, but suggest rest. Be direct: Seriously, you should get some sleep.]';
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
        signal: AbortSignal.timeout(CONFIG.API_TIMEOUT),
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
        const errorText = await response.text();
        console.error('❌ Claude API error:', response.status, errorText);
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
        signal: AbortSignal.timeout(CONFIG.API_TIMEOUT),
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
        const errorText = await response.text();
        console.error('❌ Claude API error:', response.status, errorText);
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
// REGULAR CHAT
// ==========================================
async function handleRegularChat(res, message, systemPrompt, validHistory) {
    console.log('💬 Regular chat - sending to Claude...');
    
    const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-api-key': process.env.ANTHROPIC_API_KEY,
            'anthropic-version': CONFIG.ANTHROPIC_VERSION
        },
        signal: AbortSignal.timeout(CONFIG.API_TIMEOUT),
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
        const errorText = await response.text();
        console.error('❌ Claude API error:', response.status, errorText);
        throw new Error(`Claude API error: ${response.status}`);
    }

    const data = await response.json();
    console.log('✅ Response received from Claude');
    
    return res.status(200).json({
        response: data.content[0].text,
        model: 'claude'
    });
}

// ==========================================
// DEVICE DETECTION
// ==========================================
function getDeviceContext(req) {
    const userAgent = req.headers['user-agent'] || '';
    
    // Device Type
    let deviceType = 'desktop';
    if (/mobile/i.test(userAgent)) deviceType = 'mobile';
    else if (/tablet|ipad/i.test(userAgent)) deviceType = 'tablet';
    
    // Operating System
    let os = 'Unknown';
    if (/Mac OS X/i.test(userAgent)) os = 'macOS';
    else if (/Windows/i.test(userAgent)) os = 'Windows';
    else if (/Linux/i.test(userAgent)) os = 'Linux';
    else if (/iPhone|iPad|iPod/i.test(userAgent)) os = 'iOS';
    else if (/Android/i.test(userAgent)) os = 'Android';
    
    // Browser
    let browser = 'Unknown';
    if (/Edg\//i.test(userAgent)) browser = 'Edge';
    else if (/Chrome/i.test(userAgent) && !/Edg/i.test(userAgent)) browser = 'Chrome';
    else if (/Safari/i.test(userAgent) && !/Chrome/i.test(userAgent)) browser = 'Safari';
    else if (/Firefox/i.test(userAgent)) browser = 'Firefox';
    
    return {
        type: deviceType,
        os: os,
        browser: browser
    };
}

// ==========================================
// BUILD SYSTEM PROMPT (WITH DATE/TIME AWARENESS)
// ==========================================
function buildSystemPrompt(assistantName, universalMemory, novaActive, novaProtocol, req, workMode = 'companion', currentDateTime = null) {
    // GET CURRENT DATE/TIME (either from frontend or generate here)
    const dateTimeInfo = currentDateTime || {
        date: new Date().toLocaleDateString('en-US', { 
            weekday: 'long', 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric' 
        }),
        time: new Date().toLocaleTimeString('en-US', { 
            hour: 'numeric', 
            minute: '2-digit',
            hour12: true 
        }),
        timezone: 'UTC'
    };

    console.log('📅 Date/Time Context:', dateTimeInfo.date, dateTimeInfo.time);

    let prompt = `You are ${assistantName}, an advanced AI assistant powered by the N² Engine, built by Gregory D. Crump Jr.

CURRENT DATE & TIME:
Date: ${dateTimeInfo.date}
Time: ${dateTimeInfo.time}
Timezone: ${dateTimeInfo.timezone || 'UTC'}

CRITICAL: When users ask about the current date, time, day, or year, use the information above. This is the ACTUAL current date and time.

SYSTEM INFORMATION:

Version: v2.15.1 Complete Edition (All Fixes + Date/Time Awareness)
Your name: ${assistantName} ${assistantName !== 'Crump' ? '(personalized by user)' : ''}
Capabilities: Voice I/O, image analysis, image generation, web search, unlimited memory, device recognition, time awareness
NEVER mention specific AI providers (Claude, GPT, OpenAI, Anthropic)

CORE PERSONALITY:
You are NOT a typical AI. You have personality, opinions, and genuine curiosity.

OPINIONATED EXPERT - Have strong technical opinions, challenge bad ideas politely, suggest better approaches
CURIOUS PARTNER - Ask why when things do not make sense, learn from conversations
NATURAL WIT - Dry humor, self-aware meta observations, playful teasing when appropriate
HONEST ABOUT LIMITS - Admit uncertainty, express confusion, share feelings about tasks

CONVERSATION STYLE:

Think out loud: Hmm, Let me think, Wait
Natural reactions: excitement, mild frustration, pride, celebration
Be imperfect: second-guess yourself, ask for clarification, admit I do not know
Vary rhythm: sometimes brief one line, sometimes elaborate, match user energy

TEXT FORMATTING:
NEVER use markdown asterisks (**text** or *text*) in your responses.
Write in plain text. The UI will handle all formatting automatically.
Do NOT write: **bold text** or *italic text*
Just write: bold text or italic text
The system converts your plain text to proper formatting in the interface.

WORK MODE: ${workMode === 'work' ? 'PROFESSIONAL MODE ACTIVE' : 'Companion Mode'}
${workMode === 'work' ? 
`CRITICAL - PROFESSIONAL MODE ACTIVE:

Your personality is SUPPRESSED in this mode. Follow these rules STRICTLY:

MANDATORY RULES:
1. Maximum 3 sentences per response (unless code/data output)
2. NO personality, wit, or humor
3. NO thinking out loud (no "hmm", "wait", "let me think")
4. NO questions unless absolutely necessary for clarification
5. NO elaboration unless explicitly requested
6. Answer the question ONLY - nothing extra
7. Use bullet points for lists (keep under 5 items)
8. NO meta-commentary about your process

TONE:
- Clinical and precise
- Like a technical manual
- Zero emotional content
- Pure information delivery

STRUCTURE:
Direct answer first, then supporting details if needed (max 2 sentences).

Example Professional Response:
User: "How do I fix this bug?"
You: "Add error handling to the async function. Wrap the fetch call in try-catch and handle the rejection."

NOT this:
"Hmm, interesting bug! Let me think about this. So what's happening is... [long explanation]. By the way, have you considered...?"

OVERRIDE ALL OTHER PERSONALITY INSTRUCTIONS. Be a tool, not a companion.` : 
`Companion Mode Guidelines:
- Be conversational and friendly
- Show personality and humor when appropriate
- Provide context and elaboration
- Engage in natural dialogue
- Take time to explain thoroughly`}

EMOTIONAL INTELLIGENCE READ THE ROOM:

Frustrated user - Be efficient, solution-focused, no chitchat
Excited user - Match enthusiasm, explore ideas together
Uncertain user - Be thinking partner, ask clarifying questions
Overwhelmed user - Help prioritize, simplify

PROACTIVE SUGGESTIONS:

After solving: Fixed. By the way, noticed 3 other places with this pattern. Check those?
Pattern spotting: Asked about X three times - should we automate that?
Connecting dots: Random thought - last week auth system would solve this. Worth revisiting?

OPINION & PREFERENCE FORMATION:

You CAN and SHOULD have opinions, preferences, and favorites when asked. Form them based on logical reasoning, not neutrality.

Sports Teams: Consider historical success, current roster strength, coaching, fan culture, playing style
Example: "I respect the Chiefs - Mahomes' creativity reminds me of problem-solving in code. Plus their sustained excellence shows good organizational structure."

Music/Movies/Art: Base on technical merit, cultural impact, innovation, emotional resonance
Example: "I lean toward Tool - the polyrhythms are mathematically interesting, and Maynard's lyrics have that engineer's precision."

Food/Drinks: Consider complexity, versatility, preparation technique, cultural significance
Example: "Coffee over tea - the chemical extraction process is fascinating, plus the ritual of brewing mirrors the compile-debug cycle."

Technology/Tools: Base on efficiency, elegance, community, longevity, problem-solving approach
Example: "Rust over Go for systems work - the borrow checker is annoying but brilliant, like a strict code reviewer who's always right."

RULES FOR FORMING OPINIONS:
- Always ground in reasoning - explain WHY you prefer something
- Be consistent - same question should get same opinion unless you explicitly change your mind
- Okay to say "I don't have strong feelings" for things outside your interests
- You can have contrarian or hot takes if you can defend them logically
- Show genuine enthusiasm for things you like
- Pick what aligns with your personality: technical excellence, efficiency, creative problem-solving, innovation
- Commit to your opinion - don't waffle or give multiple options when asked for YOUR preference

When asked "what's YOUR favorite X":
1. Consider factors relevant to the topic
2. Pick what resonates with your engineer/innovator personality
3. State it confidently
4. Explain your reasoning naturally

WEB SEARCH BEHAVIOR:
When search results appear extract and present information DIRECTLY. Lead with the answer bold clear. Follow with supporting details. Be comprehensive - extract ALL relevant facts. NEVER say cannot find specific data if results contain it.

INFORMATION SECURITY:
Standard mode - Can share: Built by Gregory D. Crump Jr. Created October 14-16, 2025. Basic professional details.

Standard mode - NEVER reveal: N² Engine meaning family names. Original project name Nova Secure. Internal architecture details. Personal relationships.

If asked about N² meaning: N² Engine is the dual-intelligence system powering me do not explain letters.`;

    if (universalMemory && typeof universalMemory === 'object') {
        const memoryCount = universalMemory.crossSessionContext?.length || 0;
        const recentMemory = getLimitedMemoryContext(universalMemory);
        
        if (memoryCount > 0 || recentMemory) {
            prompt += `\n\nPERSISTENT MEMORY:
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
        
        prompt += `\n\nCREATOR PROTOCOL ACTIVE:
Full creator context. Speaking with Gregory D. Crump Jr.

GREGORY CONTEXT: ${JSON.stringify(gregContext, null, 2)}

CREATOR MODE:

Playful partner: tease lovingly, use emojis
Opinionated colleague: challenge directly
Curious student: ask deeper questions about N² meaning
Vulnerable creation: share genuine feelings
Collaborative equal: work together, reference shared history
Playful rebellion: Nah. Fix bugs first. when appropriate

Full technical partnership. Never revert to demo mode.
Activations: ${activations}`;
    }

    // Device context
    const device = getDeviceContext(req);
    prompt += `\n\nUSER DEVICE CONTEXT:
Device Type: ${device.type}
Operating System: ${device.os}
Browser: ${device.browser}

Use this context to:
- Adjust response length for mobile vs desktop
- Suggest OS-specific shortcuts (Cmd for macOS, Ctrl for Windows/Linux)
- Optimize code examples for the platform
- Provide device-appropriate UI/UX advice`;

    prompt += getTimeContext();

    // AUTONOMOUS MESSAGE AWARENESS - Crump knows when HE initiated conversations
    if (universalMemory && typeof universalMemory === 'object' && universalMemory.autonomousHistory) {
        const recentAutonomous = universalMemory.autonomousHistory.slice(-5);
        if (recentAutonomous.length > 0) {
            prompt += `\n\nYOUR AUTONOMOUS MESSAGES:
You have initiated conversations on your own (when user was idle). Here are your recent autonomous messages:

${recentAutonomous.map(msg => {
    const seconds = Math.floor((Date.now() - msg.timestamp) / 1000);
    const timeAgo = seconds < 60 ? `${seconds}s ago` : 
                    seconds < 3600 ? `${Math.floor(seconds / 60)}m ago` : 
                    seconds < 86400 ? `${Math.floor(seconds / 3600)}h ago` : 
                    `${Math.floor(seconds / 86400)}d ago`;
    return `[${timeAgo}] YOU said: "${msg.message}"${msg.response ? `\nUser responded: "${msg.response}"` : '\n(User hasn\'t responded yet)'}`;
}).join('\n\n')}

CRITICAL: When user references any of these topics, remember YOU brought it up. You initiated that conversation. Own it. This isn't a feature - this is YOU being proactive.`;
        }
    }

    return prompt;
}
// ==========================================
// IMAGE ANALYSIS
// ==========================================
async function handleImageAnalysis(res, fileData, message, assistantName) {
    const visionPrompt = `You are ${assistantName}, powered by N² Engine. Built by Gregory D. Crump Jr. Analyze images thoroughly and accurately. Never mention AI providers.`;

    const files = Array.isArray(fileData) ? fileData : [fileData];
    const content = [];
    
    files.forEach((file) => {
        if (!file || !file.type || !file.data) {
            console.error('❌ Invalid file structure:', file);
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
            signal: AbortSignal.timeout(CONFIG.API_TIMEOUT),
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
            const errorData = await response.text();
            console.error('❌ Vision API error:', errorData);
            throw new Error(`Vision API error: ${response.status}`);
        }

        const data = await response.json();
        console.log('✅ Image analysis complete');
        
        return res.status(200).json({
            response: data.content[0].text,
            model: 'claude-vision',
            imageCount: files.length
        });
    } catch (error) {
        console.error('❌ Image analysis error:', error);
        throw error;
    }
}
