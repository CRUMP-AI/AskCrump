// ==========================================
// CRUMP AI - AUTONOMOUS MESSAGING v1.0
// Contextual, natural, proactive assistance
// ==========================================
class AutonomousMessaging {
constructor() {
this.enabled = false;
this.frequency = 'balanced';
this.lastMessageTime = Date.now();
this.lastTopics = [];
this.checkInterval = null;
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
        return { type: 'greeting', topics: [] };
    }

    const recentMessages = chat.messages.slice(-5);
    const lastUserMessage = recentMessages.filter(m => m.role === 'user').pop();
    
    // Extract topics from recent conversation
    const topics = this.extractTopics(recentMessages);
    
    // Determine context type
    const context = {
        type: 'followup',
        topics: topics,
        lastUserMessage: lastUserMessage?.content || '',
        messageCount: chat.messages.length,
        workMode: localStorage.getItem('crump_work_mode') === 'true'
    };

    return context;
}

extractTopics(messages) {
    const topics = new Set();
    const keywords = ['work', 'project', 'code', 'bug', 'error', 'help', 
                     'learn', 'understand', 'create', 'build', 'design',
                     'meeting', 'deadline', 'task', 'plan'];

    messages.forEach(msg => {
        const content = msg.content.toLowerCase();
        keywords.forEach(keyword => {
            if (content.includes(keyword)) {
                topics.add(keyword);
            }
        });
    });

    return Array.from(topics);
}

async generateContextualMessage(context) {
    // Generate natural, contextual messages based on conversation
    const messages = [
        // Context-aware followups
        context.topics.includes('work') || context.topics.includes('project') 
            ? "Hey! How's that project coming along? Need any help brainstorming or problem-solving?"
            : null,
        
        context.topics.includes('code') || context.topics.includes('bug')
            ? "Just checking in - did you get that code working? I'm here if you need a fresh pair of eyes!"
            : null,
        
        context.topics.includes('learn')
            ? "How's the learning going? Want to dive deeper into anything or clarify any concepts?"
            : null,

        // Time-based natural messages
        this.isWorkHours() && context.workMode
            ? "Taking a quick break? Let me know if you need help with anything work-related."
            : null,

        // Generic natural followups
        context.messageCount > 5
            ? "Anything else on your mind? I'm here to help however I can."
            : null,

        "What's next on your agenda? I'm ready to assist with whatever you're working on.",
        
        "Just wanted to check in - is there anything I can help you with right now?",
        
        this.shouldCheckNews()
            ? "Would you like a quick update on today's top news stories?"
            : null
    ];

    // Filter out nulls and pick a random relevant message
    const validMessages = messages.filter(m => m !== null);
    
    if (validMessages.length === 0) return null;

    // Prefer context-aware messages over generic ones
    return validMessages[0] || validMessages[Math.floor(Math.random() * validMessages.length)];
}

isWorkHours() {
    // Get user-configured work hours (default 9-5)
    const workStart = parseInt(localStorage.getItem('crump_work_start') || '9');
    const workEnd = parseInt(localStorage.getItem('crump_work_end') || '17');
    
    const hour = new Date().getHours();
    return hour >= workStart && hour < workEnd;
}

shouldCheckNews() {
    const lastNewsCheck = localStorage.getItem('crump_last_news_check');
    if (!lastNewsCheck) return true;
    
    const timeSinceNews = Date.now() - parseInt(lastNewsCheck);
    return timeSinceNews > 3600000; // 1 hour
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
console.log('✅ Autonomous Messaging v1.0 loaded');
