// ==========================================
// CRUMP AI - DETECTION ENGINES v1.0
// Image generation, search, API routing
// ==========================================
// Message Deduplication
class MessageDeduplicator {
constructor() {
this.recentMessages = new Set();
this.timeout = 5000; // 5 seconds
}
isDuplicate(content) {
    const hash = this.hashMessage(content);
    
    if (this.recentMessages.has(hash)) {
        return true;
    }

    this.recentMessages.add(hash);
    
    setTimeout(() => {
        this.recentMessages.delete(hash);
    }, this.timeout);

    return false;
}

hashMessage(content) {
    let hash = 0;
    for (let i = 0; i < content.length; i++) {
        const char = content.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return hash;
}
}
// Search Detection Engine
class SearchDetectionEngine {
constructor() {
this.searchTriggers = [
'search for',
'search the web',
'look up',
'find information',
'what is happening',
'latest news',
'current events',
'who won',
'what happened',
'breaking news'
];
}
needsSearch(message) {
    const lower = message.toLowerCase();
    return this.searchTriggers.some(trigger => lower.includes(trigger));
}

extractSearchQuery(message) {
    const lower = message.toLowerCase();
    
    for (const trigger of this.searchTriggers) {
        if (lower.includes(trigger)) {
            const index = lower.indexOf(trigger);
            return message.substring(index + trigger.length).trim();
        }
    }
    
    return message;
}
}
// Image Generation Detection
class ImageDetectionEngine {
constructor() {
this.imageTriggers = [
'generate an image',
'create an image',
'draw',
'make a picture',
'generate a picture',
'create artwork',
'visualize'
];
}
needsImage(message) {
    const lower = message.toLowerCase();
    return this.imageTriggers.some(trigger => lower.includes(trigger));
}

extractImagePrompt(message) {
    const lower = message.toLowerCase();
    
    for (const trigger of this.imageTriggers) {
        if (lower.includes(trigger)) {
            const index = lower.indexOf(trigger);
            return message.substring(index + trigger.length).trim();
        }
    }
    
    return message;
}
}
// Export to global
window.MessageDeduplicator = MessageDeduplicator;
window.SearchDetectionEngine = SearchDetectionEngine;
window.ImageDetectionEngine = ImageDetectionEngine;
console.log('✅ Detection Engines v1.0 loaded');
