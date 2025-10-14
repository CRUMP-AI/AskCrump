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

    const { message, provider, conversationHistory = [] } = req.body;

    // Get API keys from environment variables (secure!)
    const CLAUDE_API_KEY = process.env.CLAUDE_API_KEY;
    const OPENAI_API_KEY = process.env.OPENAI_API_KEY;

    // Status check endpoint
    if (provider === 'status') {
        return res.status(200).json({
            claude: !!CLAUDE_API_KEY,
            openai: !!OPENAI_API_KEY
        });
    }

    // Route to appropriate AI
    try {
        let response;

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
                        ...conversationHistory.map(msg => ({
                            role: msg.role === 'assistant' ? 'assistant' : 'user',
                            content: msg.content
                        })),
                        { role: 'user', content: message }
                    ],
                    system: 'You are NOVA, created for Greg D. Crump Jr. Be concise, intelligent, and helpful.'
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
                    model: 'gpt-3.5-turbo',
                    messages: [
                        { role: 'system', content: 'You are NOVA, created for Greg D. Crump Jr. Be creative and engaging.' },
                        ...conversationHistory,
                        { role: 'user', content: message }
                    ],
                    temperature: 0.8,
                    max_tokens: 500
                })
            });

            if (!openaiResponse.ok) {
                const errorText = await openaiResponse.text();
                throw new Error(`OpenAI API error: ${openaiResponse.status} - ${errorText}`);
            }

            const data = await openaiResponse.json();
            response = data.choices[0].message.content;

        } else {
            throw new Error('Invalid provider');
        }

        return res.status(200).json({ response });

    } catch (error) {
        console.error('Backend error:', error);
        return res.status(500).json({ error: error.message });
    }
}