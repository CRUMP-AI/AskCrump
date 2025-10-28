// ==========================================
// CRUMP AI - DETECTION ENGINES v1.0
// Image generation, search, API routing
// ==========================================
// Message Deduplication
class MessageDeduplicator {
    constructor() {
        this.recentHashes = new Set();
        this.maxSize = 100;
    }
    
    // Better hash function - FNV-1a algorithm (fewer collisions)
    hash(str) {
        let hash = 2166136261; // FNV offset basis
        for (let i = 0; i < str.length; i++) {
            hash ^= str.charCodeAt(i);
            hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
        }
        // Return positive integer
        return hash >>> 0;
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
