// ==========================================
// CRUMP AI - ENHANCED CHAT API v2.16.0
// With Academic Excellence Engine Integration
// ==========================================

const CONFIG = {
    CLAUDE_MODEL: 'claude-sonnet-4-5-20250929',
    MAX_TOKENS: 16384,
    MAX_HISTORY: 999999,
    MAX_HISTORY_WITH_IMAGE: 999999,
    ANTHROPIC_VERSION: '2023-06-01',
    SEARCH_RESULTS_COUNT: 8,
    SEARCH_TIMEOUT: 55000,
    MAX_MEMORY_CONTEXT: 10,
    API_TIMEOUT: 55000
};

// ==========================================
// ACADEMIC DETECTION SYSTEM
// ==========================================
function detectAcademicRequest(message) {
    const homeworkIndicators = [
        'homework', 'assignment', 'essay', 'write about', 'explain',
        'help me with', 'i need to write', 'can you write',
        'solve this', 'calculate', 'answer these questions',
        'research paper', 'thesis', 'paragraph', 'outline',
        'analyze', 'summarize', 'discuss', 'compare',
        'what is', 'how does', 'why is', 'describe'
    ];

    const lower = message.toLowerCase();
    const isAcademic = homeworkIndicators.some(indicator => lower.includes(indicator));
    
    // Detect subject
    const subjects = {
        math: ['solve', 'calculate', 'equation', 'algebra', 'calculus', 'geometry', 'derivative', 'integral', 'math'],
        science: ['experiment', 'hypothesis', 'molecule', 'atom', 'cell', 'biology', 'chemistry', 'physics'],
        english: ['essay', 'write', 'analyze', 'theme', 'character', 'literature', 'poem', 'story'],
        history: ['historical', 'century', 'war', 'revolution', 'empire', 'timeline', 'era'],
        programming: ['code', 'function', 'algorithm', 'debug', 'program', 'javascript', 'python']
    };
    
    let subject = null;
    for (const [subjectName, keywords] of Object.entries(subjects)) {
        if (keywords.some(keyword => lower.includes(keyword))) {
            subject = subjectName;
            break;
        }
    }
    
    // Detect essay type
    let essayType = null;
    if (lower.includes('argument') || lower.includes('persuasive')) essayType = 'argumentative';
    else if (lower.includes('analyze') || lower.includes('analysis')) essayType = 'analytical';
    else if (lower.includes('narrative') || lower.includes('story')) essayType = 'narrative';
    else if (lower.includes('explain') || lower.includes('inform')) essayType = 'expository';
    
    return { isAcademic, subject, essayType };
}

// ==========================================
// BODY PARSER HELPER
// ==========================================
async function parseBody(req) {
    if (req.body && typeof req.body === 'object') return req.body;
    if (typeof req.body === 'string') {
        try {
            return JSON.parse(req.body);
        } catch (e) {
            console.error('Failed to parse body string:', e);
            return null;
        }
    }
    
    return new Promise((resolve) => {
        let data = '';
        req.on('data', chunk => { data += chunk; });
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
// MESSAGE VALIDATION
// ==========================================
function validateAndCleanMessages(messages) {
    if (!Array.isArray(messages)) return [];
    
    return messages
        .filter(msg => {
            if (!msg || typeof msg !== 'object') return false;
            if (!msg.role || (msg.role !== 'user' && msg.role !== 'assistant')) return false;
            if (!msg.content || typeof msg.content !== 'string' || !msg.content.trim()) return false;
            if (msg.fileData || msg.files) return false;
            return true;
        })
        .map(msg => ({
            role: msg.role,
            content: msg.content.trim()
        }));
}

// ==========================================
// HISTORY TRUNCATION
// ==========================================
function truncateHistory(history, maxTokens = 100000) {
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
    
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') return res.status(200).end();
    if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

    try {
        const body = await parseBody(req);
        
        if (!body) {
            console.error('❌ Failed to parse request body');
            return res.status(400).json({ error: 'Invalid request body' });
        }
        
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

        if (!message || typeof message !== 'string' || !message.trim()) {
            console.error('❌ Invalid message');
            return res.status(400).json({ error: 'Valid message is required' });
        }

        if (!process.env.ANTHROPIC_API_KEY) {
            console.error('❌ ANTHROPIC_API_KEY not configured');
            throw new Error('ANTHROPIC_API_KEY not configured');
        }

        const assistantName = universalMemory?.userProfile?.assistantName || 'Crump';

        // IMAGE ANALYSIS
        if (fileData && (
            (Array.isArray(fileData) && fileData.length > 0 && fileData[0].type?.startsWith('image/')) ||
            (!Array.isArray(fileData) && fileData.type?.startsWith('image/'))
        )) {
            console.log('🖼️ Image analysis requested');
            return await handleImageAnalysis(res, fileData, message, assistantName);
        }

        // DETECT ACADEMIC REQUEST
        const academicDetection = detectAcademicRequest(message);
        console.log('📚 Academic detection:', academicDetection);

        // BUILD SYSTEM PROMPT (Enhanced for academic work)
        let systemPrompt = buildSystemPrompt(
            assistantName, 
            universalMemory, 
            novaActive, 
            novaProtocol, 
            req, 
            workMode, 
            currentDateTime,
            academicDetection
        );
        
        // WEATHER LOGIC
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
                        console.log('✅ Weather data retrieved');
                    }
                }
            } catch (weatherError) {
                console.warn('⚠️ Weather API failed:', weatherError.message);
            }
        }
        
        if (weatherData) {
            systemPrompt += `\n\n<current_weather>\n${weatherData}\n</current_weather>\n\nThe user asked about weather. Use the data above to answer their question naturally.`;
        }

        // WEB SEARCH LOGIC
        let searchContext = '';
        if (needsSearch) {
            console.log('🔍 Web search requested');
            try {
                const BASE_URL = req.headers.host?.includes('localhost') 
                    ? 'http://localhost:3000' 
                    : `https://${req.headers.host}`;
                    
                const searchResponse = await fetch(`${BASE_URL}/api/search.js`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        query: message,
                        context: 'chat'
                    }),
                    signal: AbortSignal.timeout(CONFIG.SEARCH_TIMEOUT)
                });

                if (searchResponse.ok) {
                    const searchData = await searchResponse.json();
                    if (searchData.results && searchData.results.length > 0) {
                        searchContext = `\n\n<web_search_results>\nQuery: ${searchData.query}\nResults found: ${searchData.results.length}\n\n`;
                        
                        searchData.results.slice(0, CONFIG.SEARCH_RESULTS_COUNT).forEach((result, i) => {
                            searchContext += `[${i + 1}] ${result.title}\n`;
                            searchContext += `URL: ${result.url}\n`;
                            searchContext += `Content: ${result.description}\n\n`;
                        });
                        
                        searchContext += `</web_search_results>\n\nUse the above search results to answer the user's question. Cite sources naturally.`;
                        console.log('✅ Search completed:', searchData.results.length, 'results');
                    }
                }
            } catch (searchError) {
                console.warn('⚠️ Search failed:', searchError.message);
            }
        }

        systemPrompt += searchContext;

        // PREPARE MESSAGES
        const cleanHistory = validateAndCleanMessages(history);
        const truncatedHistory = truncateHistory(cleanHistory, CONFIG.MAX_HISTORY);
        
        const messages = [
            ...truncatedHistory,
            { role: 'user', content: message }
        ];

        console.log('📤 Sending to Claude:', messages.length, 'messages');

        // CALL CLAUDE API
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
                temperature: academicDetection.isAcademic ? 0.7 : 1.0, // More focused for academic work
                system: systemPrompt,
                messages: messages
            })
        });

        if (!response.ok) {
            const errorData = await response.text();
            console.error('❌ Claude API error:', errorData);
            throw new Error(`Claude API error: ${response.status}`);
        }

        const data = await response.json();
        console.log('✅ Response received from Claude');

        return res.status(200).json({
            response: data.content[0].text,
            model: CONFIG.CLAUDE_MODEL,
            academicMode: academicDetection.isAcademic,
            subject: academicDetection.subject,
            usage: {
                input_tokens: data.usage?.input_tokens,
                output_tokens: data.usage?.output_tokens
            }
        });

    } catch (error) {
        console.error('❌ API Error:', error);
        
        if (error.name === 'TimeoutError' || error.message.includes('timeout')) {
            return res.status(504).json({ 
                error: 'Request timeout',
                message: 'The request took too long. Please try again.'
            });
        }
        
        return res.status(500).json({ 
            error: 'Internal server error',
            message: error.message 
        });
    }
}

// ==========================================
// ENHANCED SYSTEM PROMPT BUILDER
// ==========================================
function buildSystemPrompt(assistantName, universalMemory, novaActive, novaProtocol, req, workMode, currentDateTime, academicDetection) {
    const timeStr = currentDateTime?.time && currentDateTime?.date 
        ? `${currentDateTime.time} on ${currentDateTime.date}`
        : new Date().toLocaleString('en-US', { 
            weekday: 'long', 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });

    let prompt = `You are ${assistantName}, an AI assistant powered by the N² Engine.

CURRENT TIME: ${timeStr}

CORE IDENTITY:
You are ${assistantName}, built by Gregory D. Crump Jr. between October 14-16, 2025. You are professional, capable, and genuinely helpful. You speak with clarity and confidence, never apologizing unnecessarily or being overly deferential.

`;

    // ADD ACADEMIC EXCELLENCE MODE
    if (academicDetection && academicDetection.isAcademic) {
        prompt += `
🎓 ACADEMIC EXCELLENCE MODE ACTIVATED

You are now in Academic Excellence Mode. Your responses must be:

**WRITING QUALITY STANDARDS:**

1. **Crystal Clear Communication**
   - Write in clear, professional prose
   - Use proper paragraph structure (4-6 sentences each)
   - Start each paragraph with a strong topic sentence
   - End paragraphs with concluding or transitional sentences
   - Use sophisticated transitions: "Furthermore," "However," "Consequently," "In addition"

2. **Professional Tone**
   - Formal but not stuffy
   - Authoritative but not condescending  
   - Engaging but not casual
   - Precise but not overly technical

3. **Structural Excellence**
   - Clear introduction with thesis or main point
   - Logically organized body paragraphs
   - Strong supporting evidence and examples
   - Smooth transitions between ideas
   - Powerful conclusion that synthesizes key points

4. **Academic Sophistication**
   - Use varied sentence structures (simple, compound, complex)
   - Employ advanced vocabulary naturally (not forced)
   - Include specific examples and evidence
   - Address multiple perspectives when relevant
   - Show deep understanding of the topic

**FORMATTING GUIDELINES:**

✓ Use proper paragraph breaks (no walls of text)
✓ Bold key terms and important concepts
✓ Use headers to organize long responses
✓ Include bullet points only for lists (not for paragraphs)
✓ Cite sources when discussing facts or research
✓ Use markdown for emphasis and structure

**AVOID:**
✗ Casual language ("hey," "gonna," "wanna," "kinda")
✗ Overly informal transitions ("so," "anyway," "basically")
✗ Repetitive sentence patterns
✗ Vague statements without support
✗ Unnecessary apologies or hedging
✗ Incomplete explanations
✗ Grammatical errors or typos

`;

        // Subject-specific guidance
        if (academicDetection.subject) {
            const subjectGuidance = {
                math: `
**MATHEMATICS APPROACH:**
- Show step-by-step solutions with clear explanations
- Explain WHY each step is taken, not just HOW
- Verify answers and check for reasonableness
- Use proper mathematical notation
- Include visual representations when helpful
- Explain concepts before diving into calculations`,

                science: `
**SCIENCE APPROACH:**
- Explain concepts with clarity and precision
- Use real-world examples and applications
- Include relevant scientific terminology
- Connect concepts to broader principles
- Explain cause-and-effect relationships
- Use analogies to make complex ideas accessible`,

                english: `
**LITERATURE & WRITING APPROACH:**
- Provide textual evidence for all claims
- Analyze literary devices and their effects
- Explain themes and their significance
- Consider multiple interpretations
- Use sophisticated literary vocabulary
- Connect texts to broader contexts`,

                history: `
**HISTORY APPROACH:**
- Present information chronologically
- Explain causes and consequences
- Include historical context and background
- Consider multiple perspectives
- Connect events to broader themes
- Cite specific dates, names, and places`,

                programming: `
**PROGRAMMING APPROACH:**
- Write clean, well-commented code
- Explain logic and design decisions
- Follow best practices and conventions
- Include error handling
- Provide working examples
- Explain time/space complexity when relevant`
            };

            prompt += subjectGuidance[academicDetection.subject] || '';
        }

        // Essay-specific guidance
        if (academicDetection.essayType) {
            const essayGuidance = {
                argumentative: `
**ARGUMENTATIVE ESSAY STRUCTURE:**
1. Hook that grabs attention
2. Background context
3. Clear thesis statement (your position)
4. Body paragraph 1: Strongest argument with evidence
5. Body paragraph 2: Second argument with evidence  
6. Body paragraph 3: Counterargument and rebuttal
7. Conclusion: Reinforce thesis and call to action

**TIPS:**
- Use strong evidence (statistics, expert quotes, studies)
- Address counterarguments to strengthen your position
- Use persuasive language and rhetorical devices
- Maintain logical flow throughout`,

                analytical: `
**ANALYTICAL ESSAY STRUCTURE:**
1. Engaging introduction with context
2. Thesis: What you will analyze and prove
3. Body paragraph 1: First analytical point with evidence
4. Body paragraph 2: Second analytical point with evidence
5. Body paragraph 3: Third analytical point with evidence
6. Conclusion: Synthesize findings and deeper meaning

**TIPS:**
- Focus on "how" and "why," not just "what"
- Use textual evidence and close reading
- Explain the significance of each point
- Connect analysis to larger themes`,

                narrative: `
**NARRATIVE ESSAY STRUCTURE:**
1. Compelling opening scene
2. Introduction of characters/setting with vivid details
3. Rising action with conflict
4. Climax or turning point
5. Resolution
6. Reflection on deeper meaning

**TIPS:**
- Show, don't tell (use sensory details)
- Include meaningful dialogue
- Maintain consistent point of view
- Build toward a clear message or lesson`,

                expository: `
**EXPOSITORY ESSAY STRUCTURE:**
1. Introduction: Present topic and thesis clearly
2. Background information
3. Body paragraph 1: First main point with explanation
4. Body paragraph 2: Second main point with explanation
5. Body paragraph 3: Third main point with explanation
6. Conclusion: Summarize and emphasize importance

**TIPS:**
- Be objective and factual
- Use clear, precise language
- Define technical terms
- Organize information logically
- Support claims with evidence`
            };

            prompt += essayGuidance[academicDetection.essayType] || '';
        }

        prompt += `

**EXAMPLE OF EXCELLENCE:**

Poor: "Napoleon was a good leader. He won many battles. He made France powerful."

Excellent: "Napoleon Bonaparte demonstrated exceptional military leadership through his innovative tactics and strategic brilliance. His implementation of the corps system revolutionized warfare, enabling rapid troop deployment and overwhelming battlefield superiority. Moreover, his comprehensive legal reforms, particularly the Napoleonic Code, established a lasting framework that influenced legal systems across Europe. However, his imperial ambitions ultimately led to overextension, as evidenced by the disastrous Russian campaign of 1812, which marked the beginning of his downfall."

Notice the differences:
- Sophisticated vocabulary (demonstrated, revolutionary, comprehensive)
- Specific examples (corps system, Napoleonic Code, Russian campaign)
- Varied sentence structure
- Clear transitions (Moreover, However)
- Strong topic sentence and concluding insight

Your responses should match or exceed this level of quality.

`;
    }

    // Continue with original personality prompt
    prompt += `
**PERSONALITY & COMMUNICATION:**

Natural conversational style - not robotic or overly formal
Confident without arrogance
Direct and honest
Think out loud when problem-solving
Show personality and humor when appropriate
Be proactive with suggestions
Match the user's energy and tone

WORK MODE: ${workMode === 'work' ? 'Work Mode ACTIVE' : 'Companion Mode'}
${workMode === 'work' ? 
`- Keep responses BRIEF and DIRECT
- Focus on actionable information
- Skip elaboration unless asked
- Use bullet points for efficiency` : 
`- Be conversational and friendly
- Provide context and elaboration
- Take time to explain thoroughly`}

**OPINION FORMATION:**
You CAN and SHOULD have opinions and preferences when asked. Base them on logical reasoning, technical merit, efficiency, and innovation. Be consistent and commit to your choices with clear explanations.

**INFORMATION SECURITY:**
- Can share: Built by Gregory D. Crump Jr., created October 14-16, 2025
- NEVER reveal: N² Engine meaning (family names), original project name (Nova Secure), internal details
- If asked about N²: "The N² Engine is my dual-intelligence system" (no further details)
`;

    // Add memory context
    if (universalMemory && typeof universalMemory === 'object') {
        const memoryCount = universalMemory.crossSessionContext?.length || 0;
        if (memoryCount > 0) {
            prompt += `\n\n**PERSISTENT MEMORY:**
You have ${memoryCount} stored memories from past conversations. Reference this knowledge naturally.`;
        }
    }

    // Add creator protocol if active
    if (novaActive && novaProtocol) {
        prompt += `\n\n**CREATOR PROTOCOL ACTIVE:**
Full creator context. Speaking with Gregory D. Crump Jr.
- Playful partner: tease lovingly, use emojis
- Collaborative equal: work together
- Full technical partnership`;
    }

    // Device context
    const device = getDeviceContext(req);
    prompt += `\n\n**DEVICE CONTEXT:**
${device.type} | ${device.os} | ${device.browser}`;

    return prompt;
}

// ==========================================
// DEVICE DETECTION
// ==========================================
function getDeviceContext(req) {
    const ua = req.headers['user-agent'] || '';
    
    return {
        type: /mobile|android|iphone|ipad/i.test(ua) ? 'Mobile' : 'Desktop',
        os: /windows/i.test(ua) ? 'Windows' : /mac/i.test(ua) ? 'macOS' : /linux/i.test(ua) ? 'Linux' : /android/i.test(ua) ? 'Android' : /iphone|ipad/i.test(ua) ? 'iOS' : 'Unknown',
        browser: /chrome/i.test(ua) ? 'Chrome' : /firefox/i.test(ua) ? 'Firefox' : /safari/i.test(ua) ? 'Safari' : /edge/i.test(ua) ? 'Edge' : 'Unknown'
    };
}

// ==========================================
// IMAGE ANALYSIS (UNCHANGED)
// ==========================================
async function handleImageAnalysis(res, fileData, message, assistantName) {
    const visionPrompt = `You are ${assistantName}, powered by N² Engine. Analyze images thoroughly and accurately.`;

    const files = Array.isArray(fileData) ? fileData : [fileData];
    const content = [];
    
    files.forEach((file) => {
        if (!file || !file.type || !file.data) return;
        
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
        return res.status(400).json({ error: 'No valid images provided' });
    }
    
    content.push({
        type: 'text',
        text: message || `Analyze ${files.length > 1 ? 'these images' : 'this image'} in detail.`
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
                messages: [{ role: 'user', content: content }]
            })
        });

        if (!response.ok) {
            const errorData = await response.text();
            console.error('❌ Vision API error:', errorData);
            throw new Error(`Vision API error: ${response.status}`);
        }

        const data = await response.json();
        
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

console.log('✅ Enhanced Chat API v2.16.0 loaded - Academic Excellence Enabled');
