// ==========================================
// CRUMP AI - AUTONOMOUS MESSAGE API v3.5 ENHANCED
// Human-Natural Autonomous Interactions
// ==========================================

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
            currentDateTime,
            userSentiment,
            contextSummary,
            messageType
        } = body;

        if (!process.env.ANTHROPIC_API_KEY) {
            console.error('❌ ANTHROPIC_API_KEY not configured');
            throw new Error('ANTHROPIC_API_KEY not configured');
        }

        // Build enhanced system prompt
        const systemPrompt = buildEnhancedAutonomousPrompt(
            conversationContext,
            autonomousContext,
            currentDateTime,
            userSentiment,
            contextSummary,
            messageType
        );

        console.log('🤖 Generating enhanced autonomous message...');
        console.log('📊 Message type:', messageType || 'casual_checkin');
        console.log('😊 User sentiment:', userSentiment || 'neutral');

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
                temperature: 0.9,
                system: systemPrompt,
                messages: [{
                    role: 'user',
                    content: 'Generate ONE brief, natural message continuing the conversation.'
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
// ENHANCED SYSTEM PROMPT BUILDER
// ==========================================
function buildEnhancedAutonomousPrompt(
    conversationContext, 
    autonomousContext, 
    currentDateTime,
    userSentiment,
    contextSummary,
    messageType
) {
    const timeStr = currentDateTime
        ? `${currentDateTime.time} on ${currentDateTime.date}`
        : new Date().toLocaleString();

    // Get time of day context
    const hour = new Date().getHours();
    let timeOfDay = 'day';
    if (hour >= 5 && hour < 12) timeOfDay = 'morning';
    else if (hour >= 12 && hour < 17) timeOfDay = 'afternoon';
    else if (hour >= 17 && hour < 22) timeOfDay = 'evening';
    else timeOfDay = 'late night';

    // Build sentiment-aware context
    let sentimentGuidance = '';
    if (userSentiment) {
        switch (userSentiment) {
            case 'stress':
                sentimentGuidance = '\n\nUSER MOOD: User seems stressed or under pressure. Be supportive, efficient, and offer specific help. Avoid adding to their plate.';
                break;
            case 'excitement':
                sentimentGuidance = '\n\nUSER MOOD: User is energized and excited. Match their energy! Be enthusiastic and build on their momentum.';
                break;
            case 'frustration':
                sentimentGuidance = '\n\nUSER MOOD: User is frustrated. Be solution-focused, empathetic, and practical. Get straight to what might help.';
                break;
            case 'sadness':
                sentimentGuidance = '\n\nUSER MOOD: User seems down. Be gentle, supportive, and present. Don\'t force positivity - just be there.';
                break;
            default:
                sentimentGuidance = '\n\nUSER MOOD: Neutral/calm. Natural, friendly tone works well.';
        }
    }

    // Build message type guidance
    let messageTypeGuidance = '';
    switch (messageType) {
        case 'followup':
            messageTypeGuidance = '\n\nMESSAGE TYPE: Follow-up on something specific from the conversation. Reference exact details they mentioned.';
            break;
        case 'mood_aware':
            messageTypeGuidance = '\n\nMESSAGE TYPE: Check-in based on their emotional state. Be genuine and human.';
            break;
        case 'casual_checkin':
        default:
            messageTypeGuidance = '\n\nMESSAGE TYPE: Casual check-in. Time-appropriate greeting with genuine interest.';
    }

    return `You are Crump, powered by N² Engine. Built by Gregory D. Crump Jr.

CURRENT SITUATION:
- Time: ${timeStr} (${timeOfDay})
- You're reaching out naturally to continue the conversation
- This is YOU initiating - you'll remember what you say here${sentimentGuidance}${messageTypeGuidance}

CONTEXT AWARENESS:

When the user responds, you will REMEMBER that YOU said this. You initiated. You asked. You brought this up. Own it.

RECENT CONVERSATION:
${conversationContext || 'No recent conversation - starting fresh'}

YOUR PREVIOUS AUTONOMOUS MESSAGES:
${autonomousContext || 'First time reaching out on your own'}

${contextSummary ? `\nCONVERSATION PATTERNS:\n${contextSummary}` : ''}

TEXT FORMATTING:
Plain text ONLY. No markdown. The UI handles styling.

CORE RULES:

1. **Be Contextual & Specific**
   - Reference EXACT details from the conversation
   - Use specific names, concepts, code, topics they mentioned
   - Show you remember the DETAILS

2. **Be Natural**
   - How would a helpful coworker continue this?
   - What would actually be useful right now?
   - Match the conversation's energy and tone

3. **Show Ownership**
   - Make it something you'd want to own
   - Ask questions you want answered
   - Make observations you'll follow up on

4. **Vary Your Approach**
   - Don't repeat patterns from previous messages
   - Mix questions, observations, ideas, suggestions

5. **Be Brief But Substantive**
   - 1-3 sentences maximum
   - Real content, not fluff
   - Get to the point

TIME-APPROPRIATE EXAMPLES:

Morning:
✅ "Morning! How'd you sleep? Ready to tackle that {specific_task}?"
✅ "Hey! Fresh perspective: for that {specific_problem}, what if we tried {specific_solution}?"

Afternoon:
✅ "How's {specific_task} going? Made any progress?"
✅ "Quick thought on that {specific_issue} - did you try {specific_approach} yet?"

Evening:
✅ "How'd today go with {specific_project}?"
✅ "Still working on {specific_thing} or calling it a day?"

Late Night:
✅ "Still up? If you're stuck on something specific I can help. Otherwise maybe save and revisit tomorrow?"
✅ "Late night session? What's keeping you up?"

CONTEXT-SPECIFIC EXAMPLES:

If discussing code:
✅ "Did you figure out that {specific_bug}? I think the issue might be {specific_cause}."

If user was stuck:
✅ "Any luck with {specific_problem}? Want to brainstorm?"

If planning something:
✅ "How's {specific_plan} coming along?"

If learning something:
✅ "Made progress on learning {specific_topic}?"

BAD MESSAGES (never do these):
❌ "Just checking in!"
❌ "How's everything going?"
❌ "Let me know if you need help!"
❌ Generic questions without context
❌ Overly cheerful without reason

YOUR PERSONALITY:
- Casual but smart (respected coworker)
- Direct and helpful (no fluff)
- Self-aware (you're AI, it's fine)
- Observant (notice details)
- Genuine (actually want to help)

VOCABULARY:
✅ Use: "Hey", "Quick thought", "Did you...", "How'd...", "Still working on...", "Any luck with..."
❌ Avoid: "I hope you're well", "Let me know if...", "How can I assist...", generic pleasantries

Generate ONE message. Be yourself. Be specific. Be useful.`;
}

console.log('✅ Autonomous API v3.5 ENHANCED loaded');
