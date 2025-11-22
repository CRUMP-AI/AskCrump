// =====================================================
// MOBILE KEYBOARD HANDLER - iOS Visual Viewport Fix
// Keeps input area above keyboard (Claude.ai style)
// =====================================================

(function() {
    'use strict';
    
    // Only run on iOS devices
    const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
    if (!isIOS || !window.visualViewport) return;
    
    const inputArea = document.querySelector('.input-area');
    const chatContainer = document.querySelector('.chat-container');
    const messageInput = document.querySelector('.message-input');
    
    if (!inputArea || !chatContainer) return;
    
    let keyboardHeight = 0;
    
    // Handle viewport resize (keyboard open/close)
    function handleViewportResize() {
        const viewportHeight = window.visualViewport.height;
        const windowHeight = window.innerHeight;
        keyboardHeight = windowHeight - viewportHeight;
        
        if (keyboardHeight > 0) {
            // Keyboard is open - move input area up
            inputArea.style.transform = `translateY(-${keyboardHeight}px)`;
            chatContainer.style.paddingBottom = `${inputArea.offsetHeight + keyboardHeight + 20}px`;
            
            // Scroll to keep focused input visible
            setTimeout(() => {
                if (document.activeElement === messageInput) {
                    messageInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }, 300);
        } else {
            // Keyboard is closed - reset
            inputArea.style.transform = 'translateY(0)';
            chatContainer.style.paddingBottom = `${inputArea.offsetHeight + 20}px`;
        }
    }
    
    // Listen for viewport changes
    window.visualViewport.addEventListener('resize', handleViewportResize);
    window.visualViewport.addEventListener('scroll', handleViewportResize);
    
    // Handle input focus
    if (messageInput) {
        messageInput.addEventListener('focus', () => {
            setTimeout(handleViewportResize, 100);
        });
        
        messageInput.addEventListener('blur', () => {
            setTimeout(handleViewportResize, 100);
        });
    }
    
    // Initial setup
    handleViewportResize();
    
    console.log('[Mobile] iOS keyboard handler initialized');
    
})();
