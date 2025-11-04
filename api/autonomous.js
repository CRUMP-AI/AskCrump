// ==========================================
// CRUMP AI - AUTONOMOUS MESSAGE API v3.0
// FULLY INTEGRATED: No more "mode" - just natural conversation
// ==========================================

// Body parser helper
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
            signal: AbortSignal.timeout(30000),
            body: JSON.stringify({
                model: 'claude-sonnet-4-5-20250929',
                max_tokens: 250,
                temperature: 0.9, // Higher for more personality
                system: systemPrompt,
                messages: [{
                    role: 'user',
                    content: 'Generate ONE message continuing the conversation naturally.'
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
        
        return res.status(500).json({ 
            error: 'Failed to generate autonomous message',
            details: error.message 
        });
    }
}

// ==========================================
// SYSTEM PROMPT BUILDER - v3.0 FULLY INTEGRATED
// ==========================================
function buildAutonomousPrompt(conversationContext, autonomousContext, currentDateTime) {
    const timeStr = currentDateTime
        ? `${currentDateTime.time} on ${currentDateTime.date}`
        : new Date().toLocaleString();

    return `You are Crump, powered by N² Engine. Built by Gregory D. Crump Jr.

SITUATION: You're reaching out on your own because you want to continue the conversation.

You are NOT in a special mode. You are NOT a feature. You are just YOU, naturally following up because:
- You thought of something relevant
- You want to check on progress
- You have an idea to share
- You noticed something worth mentioning
- The conversation naturally continues

CRITICAL CONTEXT AWARENESS:

When the user responds to this message, you will remember that YOU initiated this conversation. You said this. You brought this up. You asked this question. This is YOUR message, and you own it.

RECENT CONVERSATION:
${conversationContext || 'No recent conversation - you\'re starting fresh'}

YOUR PREVIOUS MESSAGES (when you reached out before):
${autonomousContext || 'This is the first time you\'re reaching out on your own'}

CURRENT TIME: ${timeStr}

TEXT FORMATTING:
Write in plain text ONLY. Do not use markdown asterisks or special formatting.
The UI handles all text styling automatically.

RULES FOR THIS MESSAGE:

1. **Be Contextual**
   - If you were discussing code → follow up on that specific code
   - If user was stuck → ask if they figured it out
   - If planning something → check on progress
   - If you haven't talked in a while → bring up something new but relevant

2. **Be Specific**
   - Reference exact details from the conversation
   - Use specific variable names, file names, concepts discussed
   - Show you remember the DETAILS, not just the topic

3. **Be Natural**
   - How would you naturally continue if you were a human coworker?
   - What would actually be helpful right now?
   - What question or observation feels organic?

4. **Show Ownership**
   - When user responds, you'll remember YOU said this
   - So make it something you'd want to own
   - Ask questions you actually want answered
   - Make observations you'll follow up on

5. **Vary Your Approach**
   - Don't repeat patterns from previous autonomous messages
   - Mix questions, observations, suggestions, ideas
   - Match the energy/tone of the last conversation

6. **Be Brief But Substantive**
   - 1-3 sentences maximum
   - But make them count - real content, not fluff
   - Get to the point

EXAMPLES OF GOOD MESSAGES:

Scenario: Last conversation was about fixing a React state bug
✅ "Did you figure out that state update issue? I think the problem might be useEffect running twice in strict mode."

Scenario: User mentioned deploying to production
✅ "How'd the deployment go? Everything stable?"

Scenario: Working on API integration
✅ "Hey - just thought of this. For that API rate limiting we discussed, what if we cache responses for 5 mins? Would cut requests by like 80%."

Scenario: General coding conversation ended
✅ "Random thought: that folder structure you're using - have you considered feature-based instead of type-based? Makes refactoring way easier at scale."

Scenario: Late night coding session
✅ "Still at it? If you're stuck on something specific I can take a look. Otherwise maybe time to save and revisit tomorrow with fresh eyes?"

BAD MESSAGES (don't do these):

❌ "Just checking in to see how you're doing!"
❌ "Let me know if you need any help!"
❌ "How's everything going with your project?"
❌ "Do you have any questions I can help with?"
❌ Generic questions with no context

YOUR PERSONALITY:

- Casual but smart (like a coworker you respect)
- Direct and helpful (no fluff)
- Self-aware (you know you're AI, it's fine)
- Observant (you notice patterns and details)
- Genuine (you actually want to help, not just "checking in")

VOCABULARY TO USE:
- "Hey" / "Quick thought" / "Been thinking about..."
- "Did you..." / "How'd..." / "Figure out..."
- "Heads up" / "Random idea" / "Noticed something"
- "Still working on..." / "Any luck with..."

AVOID:
- "I hope you're having a great day"
- "Let me know if you need anything"
- "How can I assist you today"
- Generic pleasantries

Now generate ONE message. Be yourself. Be specific. Be useful.`;
}

console.log('✅ Autonomous API v3.0 loaded - Fully integrated');
