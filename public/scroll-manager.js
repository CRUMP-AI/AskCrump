// ========================================
// SCROLL TO END BUTTON FUNCTIONALITY
// For Crump AI v2.11.0
// ========================================

(function() {
    'use strict';
    
    let chatContainer = null;
    let scrollToEndBtn = null;
    let isUserScrolling = false;
    let scrollTimeout = null;
    
    // Initialize scroll functionality
    function initScrollToEnd() {
        chatContainer = document.getElementById('chatContainer');
        scrollToEndBtn = document.getElementById('scrollToEndBtn');
        
        if (!chatContainer || !scrollToEndBtn) {
            console.warn('Scroll to end: Required elements not found');
            return;
        }
        
        // Add scroll event listener to chat container
        chatContainer.addEventListener('scroll', handleScroll);
        
        // Add click event to scroll button
        scrollToEndBtn.addEventListener('click', scrollToBottom);
        
        console.log('✅ Scroll to end initialized');
    }
    
    // Handle scroll events
    function handleScroll() {
        if (!chatContainer || !scrollToEndBtn) return;
        
        const { scrollTop, scrollHeight, clientHeight } = chatContainer;
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
        
        // Show button if user scrolled up more than 200px from bottom
        if (distanceFromBottom > 200) {
            scrollToEndBtn.classList.add('visible');
            isUserScrolling = true;
        } else {
            scrollToEndBtn.classList.remove('visible');
            isUserScrolling = false;
        }
        
        // Clear any existing timeout
        if (scrollTimeout) {
            clearTimeout(scrollTimeout);
        }
        
        // Set timeout to reset user scrolling flag
        scrollTimeout = setTimeout(() => {
            isUserScrolling = false;
        }, 1000);
    }
    
    // Smooth scroll to bottom
    function scrollToBottom(behavior = 'smooth') {
        if (!chatContainer) return;
        
        chatContainer.scrollTo({
            top: chatContainer.scrollHeight,
            behavior: behavior
        });
        
        // Hide button immediately
        if (scrollToEndBtn) {
            scrollToEndBtn.classList.remove('visible');
        }
        
        isUserScrolling = false;
    }
    
    // Scroll to top of a specific message element
    function scrollToMessageTop(messageElement, behavior = 'smooth') {
        if (!chatContainer || !messageElement) return;
        
        const containerTop = chatContainer.getBoundingClientRect().top;
        const messageTop = messageElement.getBoundingClientRect().top;
        const offset = messageTop - containerTop + chatContainer.scrollTop - 20; // 20px padding
        
        chatContainer.scrollTo({
            top: offset,
            behavior: behavior
        });
    }
    
    // Auto-scroll to new Crump message (top of message)
    function scrollToNewCrumpMessage(messageElement) {
        if (!chatContainer || !messageElement) return;
        
        // If user is actively scrolling up, don't auto-scroll
        if (isUserScrolling) {
            console.log('User is scrolling, skipping auto-scroll');
            return;
        }
        
        // Small delay to ensure message is rendered
        setTimeout(() => {
            scrollToMessageTop(messageElement, 'smooth');
        }, 100);
    }
    
    // Auto-scroll to bottom for new messages (use when appropriate)
    function autoScrollToBottom() {
        if (!chatContainer) return;
        
        // Only auto-scroll if user isn't scrolling up
        if (!isUserScrolling) {
            scrollToBottom('smooth');
        }
    }
    
    // Check if user is near bottom (within 100px)
    function isNearBottom() {
        if (!chatContainer) return false;
        
        const { scrollTop, scrollHeight, clientHeight } = chatContainer;
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
        
        return distanceFromBottom < 100;
    }
    
    // Public API
    window.crumpScrollManager = {
        init: initScrollToEnd,
        scrollToBottom: scrollToBottom,
        scrollToMessageTop: scrollToMessageTop,
        scrollToNewCrumpMessage: scrollToNewCrumpMessage,
        autoScrollToBottom: autoScrollToBottom,
        isNearBottom: isNearBottom,
        setUserScrolling: (value) => { isUserScrolling = value; }
    };
    
    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initScrollToEnd);
    } else {
        initScrollToEnd();
    }
    
})();

// ========================================
// INTEGRATION GUIDE FOR YOUR APP.JS
// ========================================
/*

// When adding a new Crump message, use this:
function addCrumpMessage(messageText) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant-message';
    messageDiv.textContent = messageText;
    
    chatContainer.appendChild(messageDiv);
    
    // SCROLL TO TOP OF NEW MESSAGE
    if (window.crumpScrollManager) {
        window.crumpScrollManager.scrollToNewCrumpMessage(messageDiv);
    }
}

// For user messages, scroll to bottom:
function addUserMessage(messageText) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user-message';
    messageDiv.textContent = messageText;
    
    chatContainer.appendChild(messageDiv);
    
    // SCROLL TO BOTTOM FOR USER MESSAGES
    if (window.crumpScrollManager) {
        window.crumpScrollManager.autoScrollToBottom();
    }
}

// During streaming responses, check if user is scrolling:
function streamingUpdate() {
    if (window.crumpScrollManager && window.crumpScrollManager.isNearBottom()) {
        // Continue auto-scrolling during streaming
        window.crumpScrollManager.autoScrollToBottom();
    }
}

*/
