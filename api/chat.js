// NOVA Backend API - Serverless Function
// This runs on Vercel and keeps your API keys secure

export default async function handler(req, res) {
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    // Handle preflight
    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    const { message, history = [] } = req.body;

    if (!message) {
        return res.status(400).json({ error: 'Message is required' });
    }

    // Get API keys from environment variables (secure!)
    const CLAUDE_API_KEY = process.env.CLAUDE_API_KEY;
    const OPENAI_API_KEY = process.env.OPENAI_API_KEY;

    // Intelligent routing based on message content
    function determineProvider(msg) {
        const lowerMsg = msg.toLowerCase();
        
        // Claude for technical/reasoning
        const claudeKeywords = ['code', 'debug', 'algorithm', 'explain', 'analyze', 'architecture', 'build', 'function', 'error', 'fix'];
        
        // OpenAI for creative/casual
        const openaiKeywords = ['write', 'story', 'poem', 'creative', 'imagine', 'casual', 'chat', 'joke', 'fun'];
        
        // Check Claude keywords
        if (claudeKeywords.some(keyword => lowerMsg.includes(keyword))) {
            return 'claude';
        }
        
        // Check OpenAI keywords
        if (openaiKeywords.some(keyword => lowerMsg.includes(keyword))) {
            return 'openai';
        }
        
        // Default to Claude for general queries
        return 'claude';
    }

    const provider = determineProvider(message);

    // Route to appropriate AI
    try {
        let response;
        let aiUsed = provider.toUpperCase();

        if (provider === 'claude') {
            if (!CLAUDE_API_KEY) {
                throw new Error('Claude API key not configured');
            }

            const claudeResponse = await fetch('https://api.anthropic.com/v1/messages', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-api-key': CLAUDE_API_KEY,
                    'anthropic-version': '2023-06-01'
                },
                body: JSON.stringify({
                    model: 'claude-sonnet-4-20250514',
                    max_tokens: 1024,
                    messages: [
                        ...history.slice(-10).map(msg => ({
                            role: msg.role === 'assistant' ? 'assistant' : 'user',
                            content: msg.content
                        })),
                        { role: 'user', content: message }
                    ],
                    system: 'You are NOVA, an intelligent AI assistant created for Gregory (Greg D. Crump Jr.). Be direct, concise, and helpful. Focus on providing clear, actionable answers without unnecessary explanations.'
                })
            });

            if (!claudeResponse.ok) {
                const errorText = await claudeResponse.text();
                throw new Error(`Claude API error: ${claudeResponse.status} - ${errorText}`);
            }

            const data = await claudeResponse.json();
            response = data.content[0].text;

        } else if (provider === 'openai') {
            if (!OPENAI_API_KEY) {
                throw new Error('OpenAI API key not configured');
            }

            const openaiResponse = await fetch('https://api.openai.com/v1/chat/completions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${OPENAI_API_KEY}`
                },
                body: JSON.stringify({
                    model: 'gpt-4',
                    messages: [
                        { role: 'system', content: 'You are NOVA, an intelligent AI assistant created for Gregory (Greg D. Crump Jr.). Be creative, engaging, and helpful.' },
                        ...history.slice(-10),
                        { role: 'user', content: message }
                    ],
                    temperature: 0.8,
                    max_tokens: 800
                })
            });

            if (!openaiResponse.ok) {
                const errorText = await openaiResponse.text();
                throw new Error(`OpenAI API error: ${openaiResponse.status} - ${errorText}`);
            }

            const data = await openaiResponse.json();
            response = data.choices[0].message.content;
        }

        return res.status(200).json({ 
            response, 
            aiUsed 
        });

    } catch (error) {
        console.error('Backend error:', error);
        return res.status(500).json({ 
            error: error.message,
            details: 'Check Vercel function logs for more info'
        });
    }
}
