// ==========================================
// CRUMP AI - AUTONOMOUS MESSAGING v2.0
// Creepy-natural, human-like conversations
// ==========================================
class AutonomousMessaging {
    constructor() {
        this.enabled = false;
        this.frequency = 'balanced';
        this.lastMessageTime = Date.now();
        this.lastTopics = [];
        this.checkInterval = null;
        this.messageHistory = []; // Track what we've said
        this.ignoreCount = 0; // Track if user is ghosting
        this.lastMessageType = null; // Track message variety
        this.frequencies = {
            relaxed: 15 * 60 * 1000,  // 15 minutes
            balanced: 10 * 60 * 1000, // 10 minutes
            active: 5 * 60 * 1000     // 5 minutes
        };
    }

    start() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
        }

        const interval = this.frequencies[this.frequency] || this.frequencies.balanced;
        
        this.checkInterval = setInterval(() => {
            this.checkForAutonomousMessage();
        }, interval);

        console.log(`✅ Autonomous messaging started (${this.frequency})`);
    }

    stop() {
        if (this.checkInterval) {
            clearInterval(this.checkInterval);
            this.checkInterval = null;
        }
        console.log('⏹️ Autonomous messaging stopped');
    }

    async checkForAutonomousMessage() {
        if (!this.enabled) return;

        const timeSinceLastMessage = Date.now() - this.lastMessageTime;
        const interval = this.frequencies[this.frequency];

        // Only send if enough time has passed
        if (timeSinceLastMessage < interval) return;

        // PROTECTION #1: Don't interrupt if user is actively typing
        const userInput = document.getElementById('userInput');
        if (userInput && userInput === document.activeElement) {
            console.log('⏸️ Autonomous: User is typing - skipping');
            return;
        }
        
        // PROTECTION #2: Don't send if user typed recently (within 30 seconds)
        if (userInput && userInput.value && userInput.value.trim().length > 0) {
            console.log('⏸️ Autonomous: User has unsent message - skipping');
            return;
        }
        
        // PROTECTION #3: Don't send if page is not visible
        if (document.hidden) {
            console.log('⏸️ Autonomous: Tab is hidden - skipping');
            return;
        }
        
        // PROTECTION #4: Limit messages per session (prevent overnight spam)
        const sessionStart = sessionStorage.getItem('crump_session_start');
        const autonomousCount = parseInt(sessionStorage.getItem('crump_autonomous_count') || '0');
        const maxPerSession = 10; // Max 10 autonomous messages per session
        
        if (!sessionStart) {
            sessionStorage.setItem('crump_session_start', Date.now().toString());
            sessionStorage.setItem('crump_autonomous_count', '0');
        } else if (autonomousCount >= maxPerSession) {
            console.log('⏸️ Autonomous: Session limit reached (10 messages) - stopping');
            this.enabled = false;
            return;
        }

        // Get current context
        const context = this.analyzeContext();
        
        // Generate contextual message
        const message = await this.generateContextualMessage(context);
        
        if (message) {
            this.sendAutonomousMessage(message);
            this.lastMessageTime = Date.now();
            
            // Increment session counter
            sessionStorage.setItem('crump_autonomous_count', (autonomousCount + 1).toString());
        }
    }

    analyzeContext() {
        const chat = window.chats?.find(c => c.id === window.currentChatId);
        if (!chat || !chat.messages || chat.messages.length === 0) {
            return { type: 'greeting', topics: [], userResponded: false };
        }

        const recentMessages = chat.messages.slice(-10);
        const lastUserMessage = recentMessages.filter(m => m.role === 'user').pop();
        const lastAssistantMessage = recentMessages.filter(m => m.role === 'assistant').pop();
        
        // Check if user responded to last autonomous message
        const userResponded = lastAssistantMessage?.autonomous 
            ? (lastUserMessage?.timestamp || 0) > (lastAssistantMessage?.timestamp || 0)
            : true;
        
        // Track ignore count
        if (!userResponded && lastAssistantMessage?.autonomous) {
            this.ignoreCount++;
        } else {
            this.ignoreCount = 0;
        }
        
        // Extract topics from recent conversation
        const topics = this.extractTopics(recentMessages);
        
        // Determine context type
        const context = {
            type: this.determineContextType(topics, userResponded),
            topics: topics,
            lastUserMessage: lastUserMessage?.content || '',
            messageCount: chat.messages.length,
            workMode: localStorage.getItem('crump_work_mode') === 'true',
            userResponded: userResponded,
            ignoreCount: this.ignoreCount,
            timeSinceLastUser: lastUserMessage ? Date.now() - lastUserMessage.timestamp : 999999
        };

        return context;
    }

    determineContextType(topics, userResponded) {
        // If user hasn't responded, we're being ignored
        if (!userResponded) return 'ignored';
        
        // If conversation has topics, we can follow up
        if (topics.length > 0) return 'followup';
        
        // Otherwise, shift to new topic
        return 'newtopic';
    }

    extractTopics(messages) {
        const topics = new Set();
        const keywords = {
            work: ['work', 'job', 'project', 'meeting', 'deadline', 'task'],
            code: ['code', 'bug', 'error', 'debug', 'function', 'script'],
            learn: ['learn', 'study', 'understand', 'homework', 'research'],
            create: ['create', 'build', 'design', 'make', 'develop'],
            problem: ['problem', 'issue', 'stuck', 'help', 'confused']
        };

        messages.forEach(msg => {
            const content = msg.content.toLowerCase();
            Object.keys(keywords).forEach(topic => {
                if (keywords[topic].some(kw => content.includes(kw))) {
                    topics.add(topic);
                }
            });
        });

        return Array.from(topics);
    }

    async generateContextualMessage(context) {
        // Determine message type rotation
        const messageTypes = ['followup', 'fact', 'idea', 'question', 'observation'];
        
        // Don't use the same type twice in a row
        let availableTypes = messageTypes.filter(t => t !== this.lastMessageType);
        
        // Pick message type based on context
        let messageType;
        if (context.type === 'ignored' && context.ignoreCount > 0) {
            messageType = 'ignored';
        } else if (context.type === 'followup' && availableTypes.includes('followup')) {
            messageType = Math.random() < 0.5 ? 'followup' : this.pickRandom(availableTypes);
        } else {
            messageType = this.pickRandom(availableTypes);
        }
        
        this.lastMessageType = messageType;
        
        // Generate message based on type
        let message;
        switch(messageType) {
            case 'ignored':
                message = this.generateIgnoredMessage(context);
                break;
            case 'followup':
                message = this.generateFollowupMessage(context);
                break;
            case 'fact':
                message = this.generateFactMessage();
                break;
            case 'idea':
                message = this.generateIdeaMessage(context);
                break;
            case 'question':
                message = this.generateQuestionMessage();
                break;
            case 'observation':
                message = this.generateObservationMessage(context);
                break;
            default:
                message = this.generateGenericMessage();
        }
        
        // Deduplication check
        if (this.messageHistory.includes(message)) {
            console.log('🔄 Duplicate message detected, generating new one');
            return this.generateContextualMessage(context); // Recursively try again
        }
        
        // Add to history (keep last 20)
        this.messageHistory.push(message);
        if (this.messageHistory.length > 20) {
            this.messageHistory.shift();
        }
        
        return message;
    }

    generateIgnoredMessage(context) {
        const ignoredMessages = [
            "You good? Haven't heard from you in a bit.",
            "Still there? No pressure, just checking in.",
            "Ghosting me? 😅 All good, I'll be here when you need me.",
            "Taking a break? Cool. I'll chill here.",
            "Radio silence over there. Everything alright?",
            "Guess you're busy. Hit me up whenever.",
            "Not trying to be annoying, but just wanted to check you're good.",
            "I'll take the silence as 'focused mode' 😄"
        ];
        
        // If ignored multiple times, be more chill
        if (context.ignoreCount > 2) {
            return "Alright, I'll give you some space. Just toggle me off if you don't need autonomous check-ins right now 👍";
        }
        
        return this.pickRandom(ignoredMessages);
    }

    generateFollowupMessage(context) {
        const topic = context.topics[0];
        
        const followups = {
            work: [
                "How's that work project going?",
                "Making progress on the work stuff?",
                "Need a second opinion on anything work-related?",
                "Work going smooth or hitting any walls?"
            ],
            code: [
                "Did that code end up working?",
                "Any luck with the bug you were tackling?",
                "Want me to look at that code with fresh eyes?",
                "Still debugging or did you crack it?"
            ],
            learn: [
                "How's the learning going? Anything clicking?",
                "Getting the hang of it or need to go deeper on something?",
                "Want to quiz yourself? I can help test your understanding.",
                "Making sense so far or should we break something down?"
            ],
            create: [
                "How's the project shaping up?",
                "Making progress on what you're building?",
                "Need feedback on what you've created so far?",
                "Want to brainstorm next steps?"
            ],
            problem: [
                "Figure out that issue you were working on?",
                "Still stuck or did you find a workaround?",
                "Want to talk through it again?",
                "Any new insights on the problem?"
            ]
        };
        
        return this.pickRandom(followups[topic] || followups.work);
    }

    generateFactMessage() {
        const facts = [
            "Random fact: The Apollo Guidance Computer that landed humans on the moon had less computing power than a modern key fob. Wild, right?",
            "Did you know? The first computer bug was an actual moth stuck in a Harvard computer in 1947. We've been 'debugging' ever since.",
            "Interesting: Your phone has more computing power than all of NASA had when they sent humans to the moon.",
            "Fun fact: The @ symbol was chosen for email addresses because it was rarely used and wouldn't appear in anyone's name.",
            "Random thought: AI can write poetry and code but still can't reliably identify traffic lights in captchas. What a time to be alive.",
            "Did you know? The average person unlocks their phone 150 times per day. You're probably way past that already today.",
            "Weird fact: There are more possible iterations of a chess game than atoms in the observable universe.",
            "Here's something: The word 'robot' comes from the Czech word 'robota' meaning forced labor. Fitting, huh?"
        ];
        
        return this.pickRandom(facts);
    }

    generateIdeaMessage(context) {
        const ideas = [
            "Random idea: Ever thought about automating some of your repetitive tasks? I could help set something up.",
            "Just thinking... you could probably build a quick script to handle that thing you mentioned earlier.",
            "Idea: What if we made a dashboard to track the stuff you're working on?",
            "Thought bubble: You should document what you're learning. Future you will thank present you.",
            "Random suggestion: Have you tried breaking that big project into smaller, stupidly-simple milestones?",
            "Just spitballing: Could be cool to set up some automated reminders for your recurring tasks.",
            "Thinking out loud: What's one thing that would make your workflow 10% smoother?",
            "Wild idea: What if you built something fun this weekend instead of something productive? Sometimes that's what unlocks creativity."
        ];
        
        return this.pickRandom(ideas);
    }

    generateQuestionMessage() {
        const questions = [
            "What's the most interesting thing you learned this week?",
            "If you could automate one annoying task in your life, what would it be?",
            "What's on your mind right now? Work stuff or life stuff?",
            "Quick question: When you're stuck on something, do you prefer to grind it out solo or talk it through?",
            "Curiosity: What's your next big goal? Like, the thing you're building toward.",
            "Random Q: Coffee or energy drinks? There's a right answer here. 😄",
            "What's something you're procrastinating on that I could help with?",
            "If you had zero distractions for 4 hours right now, what would you work on?"
        ];
        
        return this.pickRandom(questions);
    }

    generateObservationMessage(context) {
        const hour = new Date().getHours();
        
        const observations = [
            "Btw, I'm getting better at understanding your workflow. Pretty cool how you tackle things.",
            "Just noticing - you ask really good questions. Makes my job easier.",
            "Random observation: You've been pretty productive lately. Respect.",
            "Not gonna lie, some of the stuff you're building is actually impressive.",
            "Fun pattern I noticed: You work best when you're not overthinking it.",
            "Just saying - you're getting faster at debugging. Leveling up in real time.",
            "Observation: You've got that builder mentality. Ship fast, iterate quick. I like it.",
            "Noticing you're in the zone. Don't let me interrupt - just wanted to vibe check."
        ];
        
        // Time-based observations
        if (hour >= 22 || hour < 6) {
            return "It's late. You doing alright? Not judging, just checking.";
        } else if (hour >= 6 && hour < 9) {
            return "Early start today. Respect. What's first on the agenda?";
        }
        
        return this.pickRandom(observations);
    }

    generateGenericMessage() {
        const generic = [
            "What's next on your list?",
            "Need anything?",
            "How can I help right now?",
            "What are you working on?",
            "Anything I can do for you?"
        ];
        
        return this.pickRandom(generic);
    }

    pickRandom(array) {
        return array[Math.floor(Math.random() * array.length)];
    }

    isWorkHours() {
        const workStart = parseInt(localStorage.getItem('crump_work_start') || '9');
        const workEnd = parseInt(localStorage.getItem('crump_work_end') || '17');
        
        const hour = new Date().getHours();
        return hour >= workStart && hour < workEnd;
    }

    sendAutonomousMessage(content) {
        const chat = window.chats?.find(c => c.id === window.currentChatId);
        if (!chat) return;

        const message = {
            role: 'assistant',
            content: content,
            timestamp: Date.now(),
            autonomous: true
        };

        chat.messages.push(message);
        chat.updatedAt = Date.now();

        if (typeof window.saveChats === 'function') {
            window.saveChats();
        }

        if (typeof window.renderMessages === 'function') {
            window.renderMessages(chat.messages);
        }

        // Scroll to new message
        if (window.crumpScrollManager) {
            setTimeout(() => {
                const messages = document.querySelectorAll('.message.assistant');
                const lastMessage = messages[messages.length - 1];
                if (lastMessage) {
                    window.crumpScrollManager.scrollToMessageTop(lastMessage);
                }
            }, 100);
        }

        console.log('💬 Autonomous message sent:', content);
    }

    setEnabled(enabled) {
        this.enabled = enabled;
        if (enabled) {
            this.start();
        } else {
            this.stop();
        }
    }

    setFrequency(frequency) {
        this.frequency = frequency;
        if (this.enabled) {
            this.stop();
            this.start();
        }
    }
}

// Initialize
window.autonomousMessaging = new AutonomousMessaging();
console.log('✅ Autonomous Messaging v2.0 loaded - Now with creepy-natural conversations 👻');
