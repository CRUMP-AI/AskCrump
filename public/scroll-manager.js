// ==========================================
// CRUMP AI - SCROLL MANAGER v1.0
// Scrolls to TOP of new Crump messages
// ==========================================
(function() {
'use strict';
let chatContainer = null;
let scrollToEndBtn = null;
let isUserScrolling = false;
let scrollTimeout = null;

function initScrollToEnd() {
    chatContainer = document.getElementById('chatContainer');
    scrollToEndBtn = document.getElementById('scrollToEndBtn');
    
    if (!chatContainer || !scrollToEndBtn) {
        console.warn('⚠️ Scroll manager: Required elements not found');
        return;
    }
    
    chatContainer.addEventListener('scroll', handleScroll);
    scrollToEndBtn.addEventListener('click', scrollToBottom);
    
    console.log('✅ Scroll manager initialized');
}

function handleScroll() {
    if (!chatContainer || !scrollToEndBtn) return;
    
    const { scrollTop, scrollHeight, clientHeight } = chatContainer;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    
    // Show button if scrolled up more than 200px
    if (distanceFromBottom > 200) {
        scrollToEndBtn.classList.add('visible');
        isUserScrolling = true;
    } else {
        scrollToEndBtn.classList.remove('visible');
        isUserScrolling = false;
    }
    
    if (scrollTimeout) {
        clearTimeout(scrollTimeout);
    }
    
    scrollTimeout = setTimeout(() => {
        isUserScrolling = false;
    }, 3000);
}

function scrollToBottom(behavior = 'smooth') {
    if (!chatContainer) return;
    
    chatContainer.scrollTo({
        top: chatContainer.scrollHeight,
        behavior: behavior
    });
    
    if (scrollToEndBtn) {
        scrollToEndBtn.classList.remove('visible');
    }
    
    isUserScrolling = false;
}

// CRITICAL: Scroll to TOP of new Crump message
function scrollToMessageTop(messageElement) {
    if (!chatContainer || !messageElement) return;
    
    // Only auto-scroll if user isn't actively scrolling up
    if (isUserScrolling) {
        console.log('User scrolling - skipping auto-scroll');
        return;
    }
    
    setTimeout(() => {
        const containerTop = chatContainer.getBoundingClientRect().top;
        const messageTop = messageElement.getBoundingClientRect().top;
        const offset = messageTop - containerTop + chatContainer.scrollTop - 20;
        
        chatContainer.scrollTo({
            top: offset,
            behavior: 'smooth'
        });
    }, 100);
}

function autoScrollToBottom() {
    if (!chatContainer || isUserScrolling) return;
    scrollToBottom('smooth');
}

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
    autoScrollToBottom: autoScrollToBottom,
    isNearBottom: isNearBottom,
    setUserScrolling: (value) => { isUserScrolling = value; }
};

// Don't auto-init - let app.js call it after app is ready
console.log('✅ Scroll Manager v1.0 loaded');
})();

