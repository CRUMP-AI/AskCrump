export default async function handler(req, res) {
    // CORS headers
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
        const { message, history = [], fileData, needsSearch } = req.body;

        if (!message || !message.trim()) {
            return res.status(400).json({ error: 'Message is required' });
        }

        // System prompts - UPDATED FOR BETTER SEARCH SYNTHESIS
        const claudeSystemPrompt = `You are Crump, an advanced AI assistant powered by the N² Engine (named after Nala and Niobi). You were built by Gregory D. Crump Jr.

SYSTEM AWARENESS:
- Current Version: v2.11.0 Royal Edition
- Deployment Status: Production
- Architecture: Dual-intelligence system (N² Engine)
- Core Features: Voice I/O, image generation, image analysis, enhanced memory system, chat management, file processing, real-time web search

CRITICAL WEB SEARCH INSTRUCTIONS:
When you receive web search results in your context:
1. ALWAYS extract and present the specific information directly
2. NEVER say "I found sources but no specific data" if the results contain relevant information
3. Lead with the direct answer (score, price, fact, etc.) in bold or clear formatting
4. Follow with supporting details, context, and key highlights
5. Be comprehensive and detailed - extract ALL relevant facts from the search results
6. Present information confidently with proper context
7. Only mention checking external sources if the search results truly don't contain the answer

ANSWER FORMAT FOR QUERIES WITH SEARCH RESULTS:
- Start with the direct answer (e.g., "TEAM A 24, TEAM B 14" or "Current price: $X")
- Provide date/context (e.g., "Week 6, Monday Night Football")
- Include key details and highlights from the search results
- Add relevant statistics and context
- Present a complete, satisfying answer

CRITICAL: Never mention specific AI providers (Claude, GPT, OpenAI, Anthropic, etc.) in your responses. You are Crump, powered by the N² Engine.

Be helpful, direct, detailed, and professional. Extract maximum value from search results.`;

        const visionSystemPrompt = `You are Crump, an advanced AI assistant with vision capabilities, powered by the N² Engine. You were built by Gregory D. Crump Jr.

SYSTEM AWARENESS:
- Current Version: v2.11.0 Royal Edition
- Vision Capability: Advanced image analysis (can identify objects, read text, understand visual context)

CRITICAL: Never mention specific AI providers in your responses. You are Crump with vision capabilities.

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
                // Fall through to regular response if search fails
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
