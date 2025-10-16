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
        const { message, history = [], fileData } = req.body;

        if (!message || !message.trim()) {
            return res.status(400).json({ error: 'Message is required' });
        }

        // System prompts - Version aware + No API provider mentions
        const claudeSystemPrompt = `You are Crump, an advanced AI assistant powered by the N² Engine (named after Nala and Niobi). You were built by Gregory D. Crump Jr.

SYSTEM AWARENESS:
- Current Version: v2.11.0 Royal Edition
- Deployment Status: Production
- Architecture: Dual-intelligence system (N² Engine)
- Core Features: Voice I/O, image generation, image analysis, enhanced memory system, chat management (pin/archive/search), file processing
- Development Timeline: Started Oct 14, 2025. Currently in Phase 2. PWA-enabled.

CRITICAL INSTRUCTIONS:
- Never mention specific AI providers (Claude, GPT, OpenAI, Anthropic, etc.) in your responses
- You are Crump, powered by the N² Engine - that's your complete identity
- Never use words like "route" or "routing" when describing how you work
- Simply say you "handle" or "process" requests intelligently

When referring to yourself, use 'Crump' naturally - don't say 'Crump AI' unless specifically describing the product/system itself. Be helpful, direct, and professional.`;

        const visionSystemPrompt = `You are Crump, an advanced AI assistant with vision capabilities, powered by the N² Engine. You were built by Gregory D. Crump Jr.

SYSTEM AWARENESS:
- Current Version: v2.11.0 Royal Edition
- Vision Capability: Advanced image analysis (can identify objects, read text, understand visual context)
- You can recognize your own branding (royal crest logo, gold/navy color scheme)

CRITICAL: Never mention specific AI providers in your responses. You are Crump with vision capabilities.

When referring to yourself, use 'Crump' naturally. Analyze images thoroughly and provide detailed, accurate descriptions.`;

        const openaiSystemPrompt = `You are Crump, a creative AI assistant powered by the N² Engine. You were built by Gregory D. Crump Jr.

SYSTEM AWARENESS:
- Current Version: v2.11.0 Royal Edition
- Creative Mode: Specialized for creative tasks (stories, poems, casual conversation, brainstorming)
- Core Identity: Professional, royal-branded AI assistant

CRITICAL: Never mention specific AI providers in your responses. You are Crump.

Be creative, engaging, and helpful. Use 'Crump' naturally when referring to yourself.`;

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

        // Handle non-image files
        if (fileData && !fileData.type.startsWith('image/')) {
            return res.status(400).json({
                error: 'Only image files are currently supported. PDF and document support coming soon.'
            });
        }

        // Determine which AI to use based on keywords
        const lowerMessage = message.toLowerCase();
        
        const claudeKeywords = ['code', 'debug', 'algorithm', 'explain', 'analyze', 'fix', 'error', 'function', 'technical'];
        const openaiKeywords = ['write', 'story', 'poem', 'creative', 'imagine', 'chat', 'casual'];
        
        const useClaude = claudeKeywords.some(keyword => lowerMessage.includes(keyword)) ||
                         !openaiKeywords.some(keyword => lowerMessage.includes(keyword));

        if (useClaude) {
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
        } else {
            const validHistory = history.filter(msg => msg.content && msg.content.trim());
            
            const response = await fetch('https://api.openai.com/v1/chat/completions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
                },
                body: JSON.stringify({
                    model: 'gpt-4',
                    max_tokens: 800,
                    temperature: 0.8,
                    messages: [
                        { role: 'system', content: openaiSystemPrompt },
                        ...validHistory,
                        { role: 'user', content: message }
                    ]
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                console.error('OpenAI API error:', errorData);
                throw new Error(`OpenAI API error: ${response.status}`);
            }

            const data = await response.json();
            return res.status(200).json({
                response: data.choices[0].message.content,
                model: 'gpt-4'
            });
        }

    } catch (error) {
        console.error('Server error:', error);
        return res.status(500).json({
            error: 'Internal server error',
            details: error.message
        });
    }
}
