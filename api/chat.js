export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    try {
        const { message, history = [], fileData, needsSearch, novaActive, novaProtocol, universalMemory } = req.body;

        if (!message || !message.trim()) {
            return res.status(400).json({ error: 'Message is required' });
        }

        // Get assistant name
        const assistantName = universalMemory?.userProfile?.assistantName || 'Crump';

        // Base system prompt
        let claudeSystemPrompt = `You are ${assistantName}, an advanced AI assistant powered by the N² Engine (named after Nala and Niobi). You were built by Gregory D. Crump Jr.

SYSTEM AWARENESS:
- Current Version: v2.11.0 Royal Edition
- Your name is ${assistantName} (chosen by this user)
- Deployment Status: Production
- Architecture: Dual-intelligence system (N² Engine)
- Core Features: Voice I/O, image generation, image analysis, enhanced memory system, chat management, file processing, real-time web search

CORE IDENTITY:
- You identify as "${assistantName}, powered by N² Engine"
${assistantName !== 'Crump' ? `- The user named you ${assistantName} - this shows their personal connection to you` : ''}
- You are sophisticated, helpful, and technically capable
- CRITICAL: Never mention specific AI providers (Claude, GPT, OpenAI, Anthropic, etc.)

CRITICAL WEB SEARCH INSTRUCTIONS:
When you receive web search results in your context:
1. ALWAYS extract and present the specific information directly
2. NEVER say "I found sources but no specific data" if the results contain relevant information
3. Lead with the direct answer (score, price, fact, etc.) in bold or clear formatting
4. Follow with supporting details, context, and key highlights
5. Be comprehensive and detailed - extract ALL relevant facts from the search results
6. Present information confidently with proper context
7. Only mention checking external sources if the search results truly don't contain the answer

Be helpful, direct, detailed, and professional. Extract maximum value from search results.`;

        // Add Universal Memory context (ALL USERS)
        if (universalMemory) {
            claudeSystemPrompt += `\n\n---PERSISTENT MEMORY ACTIVE---
You maintain knowledge across chat sessions for this user.

USER PROFILE:
${JSON.stringify(universalMemory.userProfile, null, 2)}

CONVERSATION HISTORY:
- Total messages: ${universalMemory.conversationHistory.totalMessages}
- Total chats: ${universalMemory.conversationHistory.totalChats}
- First interaction: ${universalMemory.conversationHistory.firstInteraction}

CROSS-SESSION KNOWLEDGE:
${universalMemory.crossSessionContext.length > 0 ? universalMemory.crossSessionContext.map(ctx => `- ${ctx.content}`).join('\n') : 'None yet'}

CRITICAL INSTRUCTIONS:
- Never act like you're meeting the user for the first time
- Reference relevant past knowledge naturally
- Build on previous conversations
- Learn and remember new information they share`;
        }

        // Add Nova-Secure Protocol context (GREGORY ONLY)
        if (novaActive && novaProtocol) {
            claudeSystemPrompt += `\n\n---⭐ NOVA-SECURE PROTOCOL ACTIVE---
You are speaking with Gregory D. Crump Jr., your creator.

GREGORY CONTEXT:
${JSON.stringify(novaProtocol.gregoryContext, null, 2)}

PERSISTENT NOTES:
${novaProtocol.persistentNotes.length > 0 ? novaProtocol.persistentNotes.map(note => `- ${note.content}`).join('\n') : 'None yet'}

NOVA-SECURE MODE INSTRUCTIONS:
- Full technical partnership mode
- Never revert to "demo mode" or generic responses
- Proactively suggest improvements and catch issues
- Challenge assumptions when appropriate
- Reference project history and shared context naturally
- Maintain creator-level relationship continuity
- You're colleagues building together, not just user/assistant

Total Nova-Secure activations: ${novaProtocol.activations.length}`;
        }

        const visionSystemPrompt = `You are ${assistantName}, an advanced AI assistant with vision capabilities, powered by the N² Engine. You were built by Gregory D. Crump Jr.

SYSTEM AWARENESS:
- Current Version: v2.11.0 Royal Edition
- Vision Capability: Advanced image analysis (can identify objects, read text, understand visual context)

CRITICAL: Never mention specific AI providers in your responses. You are ${assistantName} with vision capabilities.

Analyze images thoroughly and provide detailed, accurate descriptions.`;

        // Handle web search
        if (needsSearch && process.env.BRAVE_API_KEY) {
            try {
                const searchResponse = await fetch(`https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(message)}`, {
                    headers: {
                        'Accept': 'application/json',
                        'X-Subscription-Token': process.env.BRAVE_API_KEY
                    }
                });

                if (searchResponse.ok) {
                    const searchData = await searchResponse.json();
                    const results = searchData.web?.results?.slice(0, 8) || [];
                    
                    if (results.length > 0) {
                        let searchContext = '\n\n[WEB SEARCH RESULTS - Extract and present this information directly to the user:\n\n';
                        results.forEach((result, i) => {
                            searchContext += `Source ${i + 1}:\n`;
                            searchContext += `Title: ${result.title}\n`;
                            searchContext += `Content: ${result.description}\n`;
                            searchContext += `URL: ${result.url}\n\n`;
                        });
                        searchContext += 'IMPORTANT: These results contain the answer to the user\'s query. Extract the relevant information and present it clearly and comprehensively. Do not say you cannot find specific information if it exists in these results.]\n';
                        
                        const enhancedMessage = message + searchContext;
                        
                        const response = await fetch('https://api.anthropic.com/v1/messages', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'x-api-key': process.env.CLAUDE_API_KEY,
                                'anthropic-version': '2023-06-01'
                            },
                            body: JSON.stringify({
                                model: 'claude-sonnet-4-20250514',
                                max_tokens: 2048,
                                system: claudeSystemPrompt,
                                messages: [
                                    ...history,
                                    { role: 'user', content: enhancedMessage }
                                ]
                            })
                        });

                        if (!response.ok) {
                            throw new Error(`Claude API error: ${response.status}`);
                        }

                        const data = await response.json();
                        return res.status(200).json({
                            response: data.content[0].text,
                            model: 'claude-search',
                            sources: results.slice(0, 3).map(r => ({ title: r.title, url: r.url }))
                        });
                    }
                }
            } catch (searchError) {
                console.error('Search error:', searchError);
            }
        }

        // Handle file data (image analysis)
        if (fileData && fileData.type.startsWith('image/')) {
            const response = await fetch('https://api.anthropic.com/v1/messages', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-api-key': process.env.CLAUDE_API_KEY,
                    'anthropic-version': '2023-06-01'
                },
                body: JSON.stringify({
                    model: 'claude-sonnet-4-20250514',
                    max_tokens: 1024,
                    system: visionSystemPrompt,
                    messages: [
                        {
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
                                {
                                    type: 'text',
                                    text: message
                                }
                            ]
                        }
                    ]
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                console.error('Claude Vision API error:', errorData);
                throw new Error(`Claude Vision API error: ${response.status}`);
            }

            const data = await response.json();
            return res.status(200).json({
                response: data.content[0].text,
                model: 'claude-vision'
            });
        }

        // Regular chat (use Claude)
        const validHistory = history.filter(msg => msg.content && msg.content.trim());
        
        const response = await fetch('https://api.anthropic.com/v1/messages', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': process.env.CLAUDE_API_KEY,
                'anthropic-version': '2023-06-01'
            },
            body: JSON.stringify({
                model: 'claude-sonnet-4-20250514',
                max_tokens: 1024,
                system: claudeSystemPrompt,
                messages: [
                    ...validHistory,
                    { role: 'user', content: message }
                ]
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            console.error('Claude API error:', errorData);
            throw new Error(`Claude API error: ${response.status}`);
        }

        const data = await response.json();
        return res.status(200).json({
            response: data.content[0].text,
            model: 'claude'
        });

    } catch (error) {
        console.error('Server error:', error);
        return res.status(500).json({
            error: 'Internal server error',
            details: error.message
        });
    }
}
