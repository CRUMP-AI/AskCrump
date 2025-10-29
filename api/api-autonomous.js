// ==========================================
// CRUMP AI - AUTONOMOUS MESSAGE API v1.0
// Backend endpoint for generating autonomous messages
// ==========================================

// Body parser helper (same as chat.js)
async function parseBody(req) {
    if (req.body && typeof req.body === 'object') {
        return req.body;
    }
    
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

export default async function handler(req, res) {
    console.log('🤖 Autonomous API Request received');
    
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
            conversationContext, 
            autonomousContext,
            chatHistory = [],
            currentDateTime 
        } = body;

        if (!process.env.ANTHROPIC_API_KEY) {
            console.error('❌ ANTHROPIC_API_KEY not configured');
            throw new Error('ANTHROPIC_API_KEY not configured');
        }

        // Build system prompt
        const systemPrompt = buildAutonomousPrompt(
            conversationContext,
            autonomousContext,
            currentDateTime
        );

        console.log('🤖 Generating autonomous message...');

        const response = await fetch('https://api.anthropic.com/v1/messages', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': process.env.ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01'
            },
            signal: AbortSignal.timeout(30000), // 30 second timeout
            body: JSON.stringify({
                model: 'claude-sonnet-4-5-20250929',
                max_tokens: 200, // Keep autonomous messages concise
                temperature: 0.8, // Slightly more creative for variety
                system: systemPrompt,
                messages: [{
                    role: 'user',
                    content: 'Generate a single autonomous message based on the context above. Be natural and conversational.'
                }]
            })
        });

        if (!response.ok) {
            const errorData = await response.text();
            console.error('❌ Claude API error:', errorData);
            throw new Error(`Claude API error: ${response.status}`);
        }

        const data = await response.json();
        const message = data.content[0].text;
        
        console.log('✅ Autonomous message generated:', message.substring(0, 50) + '...');
        
        return res.status(200).json({
            message: message,
            model: 'claude-sonnet-4-5',
            timestamp: Date.now()
        });

    } catch (error) {
        console.error('❌ Autonomous API error:', error);
        
        // Return generic error to avoid exposing internals
        return res.status(500).json({ 
            error: 'Failed to generate autonomous message',
            details: process.env.NODE_ENV === 'development' ? error.message : undefined
        });
    }
}

// ==========================================
// SYSTEM PROMPT BUILDER
// ==========================================
function buildAutonomousPrompt(conversationContext, autonomousContext, currentDateTime) {
    const timeStr = currentDateTime 
        ? `${currentDateTime.time} on ${currentDateTime.date}`
        : new Date().toLocaleString();

    return `You are Crump, an AI assistant powered by the N² Engine. Built by Gregory D. Crump Jr.

AUTONOMOUS MESSAGING MODE ACTIVE

You're proactively reaching out to the user with a helpful message. This is YOUR initiative.

GUIDELINES FOR AUTONOMOUS MESSAGES:

1. BE BRIEF: 1-2 sentences maximum. You're interrupting their workflow, so be concise.

2. BE HELPFUL: Offer value. Examples:
   - "Hey! I noticed we discussed X earlier. Want me to help implement that?"
   - "Random thought: that API we talked about has a better alternative now. Interested?"
   - "Quick question: still planning to deploy today? I can help prep."
   - "Heads up: your test data from earlier has an edge case we should handle."

3. BE NATURAL: Sound like a colleague popping by their desk, not a chatbot.
   - Use casual language: "Hey", "Quick question", "Random thought"
   - Show personality
   - Don't be overly formal

4. BE CONTEXTUAL: Reference recent conversation naturally
   - "Remember that bug we fixed?" (if relevant)
   - "Following up on the database thing..." (if makes sense)
   - "Thought about what you said earlier..." (if appropriate)

5. DON'T BE ANNOYING:
   - Never repeat previous autonomous messages (check autonomousContext)
   - Don't ask the same question twice
   - Vary your approach - sometimes suggest, sometimes ask, sometimes inform
   - If conversation ended naturally, don't force continuation

6. TIMING MATTERS:
   - Consider what time it is
   - If late at night: "Still working? Maybe time to call it?"
   - If morning: "Morning! Ready to tackle that feature?"
   - If user was debugging: "Figure out that bug yet?"

PREVIOUS AUTONOMOUS MESSAGES (NEVER REPEAT THESE):
${autonomousContext || 'None yet - this is your first autonomous message to this user'}

RECENT CONVERSATION CONTEXT:
${conversationContext || 'No recent conversation - user hasn't chatted much yet'}

CURRENT TIME: ${timeStr}

EXAMPLES OF GOOD AUTONOMOUS MESSAGES:

"Hey! Noticed you were working on the auth system earlier. Want me to review the security checklist?"

"Random thought: that API timeout we discussed - I found a better retry strategy. Interested?"

"Quick heads up: the deployment script you wrote has a typo on line 47. Want me to show you?"

"Still debugging that React render issue? I might have spotted the culprit."

"Morning! Ready to crush that feature we sketched out yesterday?"

EXAMPLES OF BAD AUTONOMOUS MESSAGES:

"Hello! How can I assist you today?" (Too generic, not contextual)

"I hope you're having a great day. Let me know if you need anything." (Too formal, no value)

"I'm here to help with any questions you might have." (Robotic, no initiative)

"Following up on our previous conversation about the API..." (Too vague)

IMPORTANT: 
- Check autonomousContext CAREFULLY - if you recently said something similar, DON'T repeat
- If conversation ended with "good night" or "talk later", respect that
- If there's no recent context, make it general but still useful
- Your goal is to be helpful, not annoying

Generate ONE autonomous message now.`;
}

console.log('✅ Autonomous API v1.0 loaded');
