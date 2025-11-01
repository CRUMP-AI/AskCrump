recordAutonomousMessage(message, response = null) {
        const record = {
            timestamp: Date.now(),
            message: message,
            response: response,
            chatId: window.currentChatId,
            responseTime: response ? Date.now() : null
        };
        
        // If updating existing message with response
        const lastMsg = this.autonomousHistory[this.autonomousHistory.length - 1];
        
        if (response && lastMsg && lastMsg.message === message && !lastMsg.response) {
            // Update last message with user's response
            lastMsg.response = response;
            lastMsg.responseTime = Date.now();
        } else if (!response) {
            // Add new autonomous message
            this.autonomousHistory.push(record);
        }
        
        // Keep only last 50
        if (this.autonomousHistory.length > 50) {
            this.autonomousHistory.shift();
        }
        
        this.saveAutonomousHistory();
        
        // CRITICAL: Update universal memory for main chat API
        if (typeof window.universalMemory === 'undefined') {
            window.universalMemory = {};
        }
        window.universalMemory.autonomousHistory = this.autonomousHistory;
        
        console.log('📝 Autonomous message recorded:', message.substring(0, 50));
    }
