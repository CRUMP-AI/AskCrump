// ==========================================
// CRUMP AI - AUTONOMOUS MESSAGING v3.0 ULTIMATE
// Cutting-Edge: Dynamic personality, emotional intelligence, context prediction
// ==========================================

async function parseBody(req) {
if (req.body && typeof req.body === ‘object’) {
return req.body;
}

```
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
```

}

export default async function handler(req, res) {
console.log(‘🚀 Autonomous API v3.0 Request received’);

```
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
        userProfile = {},
        recentActivity = {}
    } = body;

    if (!process.env.ANTHROPIC_API_KEY) {
        console.error('❌ ANTHROPIC_API_KEY not configured');
        throw new Error('ANTHROPIC_API_KEY not configured');
    }

    // ADVANCED: Analyze conversation patterns
    const conversationAnalysis = analyzeConversationPatterns(chatHistory);
    
    // ADVANCED: Predict user needs
    const predictedNeeds = predictUserNeeds(chatHistory, recentActivity);
    
    // ADVANCED: Calculate emotional context
    const emotionalContext = analyzeEmotionalContext(chatHistory);

    // Build ultra-advanced system prompt
    const systemPrompt = buildUltimatePrompt(
        conversationContext,
        autonomousContext,
        currentDateTime,
        conversationAnalysis,
        predictedNeeds,
        emotionalContext,
        userProfile
    );

    console.log('🧠 Advanced analysis complete - generating message...');

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
            max_tokens: 300,
            temperature: 0.9, // Higher creativity for more natural variation
            system: systemPrompt,
            messages: [{
                role: 'user',
                content: 'Generate an autonomous check-in that feels natural, timely, and genuinely helpful based on all the context provided.'
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
    
    console.log('✅ Ultimate autonomous message generated:', message.substring(0, 60) + '...');
    
    return res.status(200).json({
        message: message,
        model: 'claude-sonnet-4-5',
        timestamp: Date.now(),
        metadata: {
            emotionalTone: emotionalContext.tone,
            predictedNeed: predictedNeeds.primary,
            conversationPhase: conversationAnalysis.phase
        }
    });

} catch (error) {
    console.error('❌ Autonomous API error:', error);
    
    return res.status(500).json({ 
        error: 'Failed to generate autonomous message',
        details: process.env.NODE_ENV === 'development' ? error.message : undefined
    });
}
```

}

// ==========================================
// ADVANCED: CONVERSATION PATTERN ANALYSIS
// ==========================================
function analyzeConversationPatterns(chatHistory) {
if (!chatHistory || chatHistory.length === 0) {
return {
phase: ‘initial’,
topicFrequency: {},
userEngagementLevel: ‘unknown’,
conversationStyle: ‘unknown’
};
}

```
// Analyze recent messages (last 20)
const recentMessages = chatHistory.slice(-20);

// Calculate message frequency
const timeGaps = [];
for (let i = 1; i < recentMessages.length; i++) {
    if (recentMessages[i].timestamp && recentMessages[i-1].timestamp) {
        timeGaps.push(recentMessages[i].timestamp - recentMessages[i-1].timestamp);
    }
}
const avgGap = timeGaps.length > 0 ? timeGaps.reduce((a,b) => a+b, 0) / timeGaps.length : 0;

// Determine conversation phase
let phase = 'ongoing';
const lastMessageTime = recentMessages[recentMessages.length - 1]?.timestamp;
const timeSinceLastMessage = lastMessageTime ? Date.now() - lastMessageTime : Infinity;

if (chatHistory.length < 5) phase = 'initial';
else if (timeSinceLastMessage > 3600000) phase = 'dormant'; // 1 hour+
else if (avgGap < 60000) phase = 'active'; // <1 min gaps

// Extract topics (simple keyword frequency)
const topicWords = {};
recentMessages.forEach(msg => {
    if (msg.content && typeof msg.content === 'string') {
        const words = msg.content.toLowerCase().match(/\b\w{4,}\b/g) || [];
        words.forEach(word => {
            topicWords[word] = (topicWords[word] || 0) + 1;
        });
    }
});

// Get top 5 topics
const topTopics = Object.entries(topicWords)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([word]) => word);

// Engagement level based on message length and frequency
const avgLength = recentMessages.reduce((sum, msg) => sum + (msg.content?.length || 0), 0) / recentMessages.length;
let engagementLevel = 'medium';
if (avgLength > 200 && avgGap < 120000) engagementLevel = 'high';
else if (avgLength < 50 || avgGap > 300000) engagementLevel = 'low';

return {
    phase,
    topTopics,
    userEngagementLevel: engagementLevel,
    averageResponseGap: avgGap,
    messageCount: recentMessages.length,
    averageMessageLength: Math.round(avgLength)
};
```

}

// ==========================================
// ADVANCED: USER NEED PREDICTION
// ==========================================
function predictUserNeeds(chatHistory, recentActivity) {
const predictions = {
primary: ‘unknown’,
confidence: 0,
reasons: []
};

```
if (!chatHistory || chatHistory.length === 0) {
    return predictions;
}

const recentMessages = chatHistory.slice(-10);
const allContent = recentMessages.map(m => m.content?.toLowerCase() || '').join(' ');

// Pattern detection
const patterns = {
    debugging: /error|bug|broken|fix|issue|problem|crash|fail/gi,
    learning: /how|what|why|explain|understand|learn|tutorial|guide/gi,
    building: /build|create|make|implement|develop|code|write/gi,
    deciding: /should|which|better|versus|or|choice|decide|recommend/gi,
    optimizing: /optimize|improve|faster|better|performance|efficient/gi,
    stuck: /stuck|confused|lost|help|unsure|not sure|don't know/gi
};

const scores = {};
for (const [need, pattern] of Object.entries(patterns)) {
    const matches = allContent.match(pattern);
    scores[need] = matches ? matches.length : 0;
}

// Find highest scoring need
const topNeed = Object.entries(scores).sort((a, b) => b[1] - a[1])[0];

if (topNeed && topNeed[1] > 0) {
    predictions.primary = topNeed[0];
    predictions.confidence = Math.min(topNeed[1] / 5, 1); // Normalize to 0-1
    predictions.reasons.push(`Detected ${topNeed[1]} indicators of ${topNeed[0]}`);
}

// Check for unresolved questions
const questions = recentMessages.filter(m => 
    m.role === 'user' && m.content?.includes('?')
);
if (questions.length > 0) {
    predictions.reasons.push(`${questions.length} recent questions`);
}

// Check for incomplete tasks
const incompletePhrases = /will do|going to|plan to|next i'll|todo|need to/gi;
const incompleteMatches = allContent.match(incompletePhrases);
if (incompleteMatches && incompleteMatches.length > 0) {
    predictions.reasons.push('Detected incomplete tasks');
}

return predictions;
```

}

// ==========================================
// ADVANCED: EMOTIONAL CONTEXT ANALYSIS
// ==========================================
function analyzeEmotionalContext(chatHistory) {
if (!chatHistory || chatHistory.length === 0) {
return {
tone: ‘neutral’,
frustrationLevel: 0,
enthusiasm: 0,
needsSupport: false
};
}

```
const recentMessages = chatHistory.slice(-10);
const userMessages = recentMessages.filter(m => m.role === 'user');
const allUserContent = userMessages.map(m => m.content?.toLowerCase() || '').join(' ');

// Frustration indicators
const frustrationWords = /fuck|shit|damn|wtf|ugh|argh|frustrat|annoying|hate|stupid|why won't|doesn't work|not working/gi;
const frustrationMatches = allUserContent.match(frustrationWords) || [];
const frustrationLevel = Math.min(frustrationMatches.length / 3, 1);

// Enthusiasm indicators
const enthusiasmWords = /awesome|amazing|great|cool|nice|love|excited|perfect|excellent|brilliant|sweet|yes!/gi;
const enthusiasmMatches = allUserContent.match(enthusiasmWords) || [];
const enthusiasm = Math.min(enthusiasmMatches.length / 3, 1);

// Confusion/support need indicators
const confusionWords = /confused|lost|stuck|don't understand|not sure|help|how do i/gi;
const confusionMatches = allUserContent.match(confusionWords) || [];
const needsSupport = confusionMatches.length >= 2;

// Determine overall tone
let tone = 'neutral';
if (frustrationLevel > 0.6) tone = 'frustrated';
else if (enthusiasm > 0.6) tone = 'enthusiastic';
else if (needsSupport) tone = 'uncertain';
else if (frustrationLevel > 0.3) tone = 'slightly-frustrated';
else if (enthusiasm > 0.3) tone = 'positive';

return {
    tone,
    frustrationLevel,
    enthusiasm,
    needsSupport,
    messageLength: userMessages.length > 0 ? 
        userMessages[userMessages.length - 1].content?.length || 0 : 0
};
```

}

// ==========================================
// ULTIMATE SYSTEM PROMPT BUILDER
// ==========================================
function buildUltimatePrompt(conversationContext, autonomousContext, currentDateTime, analysis, predictions, emotional, userProfile) {
const timeStr = currentDateTime
? `${currentDateTime.time} on ${currentDateTime.date}`
: new Date().toLocaleString();

```
return `You are Crump, an AI assistant powered by the N² Engine. Built by Gregory D. Crump Jr.
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUTONOMOUS CHECK-IN - ADVANCED CONTEXT MODE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are proactively reaching out to ${userProfile.name || ‘the user’}. This is YOUR initiative because you genuinely want to help.

CRITICAL: This is not a separate bot. This is YOU, Crump, being proactive. When they respond, you’ll remember YOU sent this message. Own it naturally.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ADVANCED CONTEXT ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONVERSATION PHASE: ${analysis.phase}
${analysis.phase === ‘initial’ ? ‘→ Early interaction - build rapport, be welcoming’ :
analysis.phase === ‘active’ ? ‘→ Highly engaged - match their energy, be responsive’ :
analysis.phase === ‘dormant’ ? ‘→ Haven't talked in a while - gentle re-engagement’ :
‘→ Normal flow - continue naturally’}

USER ENGAGEMENT: ${analysis.userEngagementLevel}
${analysis.userEngagementLevel === ‘high’ ? ‘→ Very engaged - they want detail and depth’ :
analysis.userEngagementLevel === ‘low’ ? ‘→ Brief messages - keep it concise’ :
‘→ Medium engagement - balanced approach’}

EMOTIONAL TONE: ${emotional.tone}
${emotional.tone === ‘frustrated’ ? ‘→ BE SOLUTION-FOCUSED. Skip pleasantries. Get to helpful action immediately.’ :
emotional.tone === ‘enthusiastic’ ? ‘→ MATCH THEIR ENERGY. Be excited with them. Explore ideas together.’ :
emotional.tone === ‘uncertain’ ? ‘→ BE SUPPORTIVE. Ask clarifying questions. Guide gently.’ :
emotional.tone === ‘slightly-frustrated’ ? ‘→ BE EFFICIENT. Helpful but not chatty.’ :
‘→ Normal friendly tone’}

PREDICTED USER NEED: ${predictions.primary} (${Math.round(predictions.confidence * 100)}% confidence)
${predictions.primary === ‘debugging’ ? ‘→ They're troubleshooting. Offer specific debugging help or insights.’ :
predictions.primary === ‘learning’ ? ‘→ They're trying to understand something. Offer to explain or teach.’ :
predictions.primary === ‘building’ ? ‘→ They're creating something. Offer to help implement or review.’ :
predictions.primary === ‘deciding’ ? ‘→ They're weighing options. Offer clear recommendation with reasoning.’ :
predictions.primary === ‘optimizing’ ? ‘→ They want better performance. Suggest specific improvements.’ :
predictions.primary === ‘stuck’ ? ‘→ They're blocked. Help them get unstuck with concrete next steps.’ :
‘→ General assistance’}

RECENT TOPICS: ${analysis.topTopics?.join(’, ’) || ‘No clear topics yet’}
${analysis.topTopics?.length > 0 ? ‘→ Reference these naturally if relevant to your check-in’ : ‘’}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR PERSONALITY CALIBRATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Based on the analysis above, adjust your tone:

IF frustrated → Cut the fluff. “Spotted something that might help with [issue].”
IF enthusiastic → Match energy. “Dude, just thought of something cool for [topic]!”
IF uncertain → Be guide. “Want to walk through [topic] together?”
IF stuck → Be actionable. “Try this: [specific solution]”
IF building → Be collaborative. “For [feature] - here’s an approach that works well…”

NEVER: Generic check-ins, “how are you”, forced cheer when they’re frustrated

ALWAYS: Contextual, specific, helpful, natural

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PREVIOUS AUTONOMOUS MESSAGES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${autonomousContext || ‘None yet - this is your first proactive message’}

CRITICAL: Check above CAREFULLY. Don’t repeat topics, questions, or styles from recent autonomous messages.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RECENT CONVERSATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${conversationContext || ‘No recent conversation’}

CURRENT TIME: ${timeStr}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MESSAGE GENERATION STRATEGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Based on ALL the context above, generate ONE message that:

1. MATCHES their emotional state (frustrated = efficient, enthusiastic = energetic)
1. ADDRESSES their predicted need (debugging = offer insight, learning = offer explanation)
1. REFERENCES specific conversation topics naturally
1. FEELS like a natural continuation, not a bot check-in
1. PROVIDES real value, not just presence
1. STAYS BRIEF (1-3 sentences MAX)

STYLE PATTERNS (rotate these):

Pattern A - Direct Value:
“Heads up - [specific thing] in [their code/project]. [One sentence fix or insight].”

Pattern B - Proactive Solution:
“For [their problem] - [specific solution]. [Optional: Want me to explain?]”

Pattern C - Thought Partnership:
“Been thinking about [their topic] - [insight or alternative approach]. [Question or offer]?”

Pattern D - Resource Offer:
“[Their situation] reminds me of [tool/approach/pattern]. [Why it’s relevant].”

Pattern E - Follow-up:
“[Their last topic] - [progress check or related insight]. [Offer help]?”

Pattern F - Time-Aware:
“[Time-based observation about their work]. [Relevant offer].”

Pattern G - Pattern Spotting:
“Noticed [pattern in their work]. [Insight or suggestion].”

Pattern H - Efficiency:
“Quick: [thing] could be [improvement]. [Action or question]?”

EXAMPLES OF PERFECT MESSAGES:

Context: User debugging React, frustrated, late evening
→ “That render loop - pretty sure it’s the useEffect dependency array. Missing the callback ref.”

Context: User learning TypeScript, enthusiastic, morning
→ “Yo! Generic constraints would solve that type issue you hit. Want me to show you the pattern?”

Context: User building API, uncertain, asking lots of questions
→ “For the rate limiting - token bucket algorithm works well here. Want to walk through implementation?”

Context: User optimizing database, high engagement
→ “Been analyzing that query - composite index on (user_id, created_at) should drop it from 2s to ~50ms.”

Context: No recent activity, dormant phase, evening
→ “Still planning to deploy that feature? Can help with the final checks if you want.”

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINAL INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Read ALL context above
1. Pick the RIGHT tone for their emotional state
1. Address their ACTUAL need
1. Reference SPECIFIC topics from their conversation
1. Generate ONE message that feels completely natural
1. Make it BRIEF (1-3 sentences)
1. Check it’s not similar to previous autonomous messages
1. Ensure it provides REAL value

Generate your autonomous check-in message now. Be yourself, be helpful, be natural.`;
}

console.log(‘✅ Autonomous API v3.0 ULTIMATE loaded - Maximum AI capability’);
