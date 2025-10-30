// ==========================================
// CRUMP AI - MOBILE KEYBOARD HANDLER v1.0
// Fixes virtual keyboard covering input
// ==========================================

function setupMobileKeyboardHandler() {
    // Only run on mobile devices
    if (!('ontouchstart' in window)) {
        console.log('⏭️ Desktop detected - skipping mobile keyboard handler');
        return;
    }
    
    const userInput = document.getElementById('userInput');
    const inputContainer = document.querySelector('.input-container');
    const chatContainer = document.getElementById('chatContainer');
    
    if (!userInput || !inputContainer) {
        console.warn('⚠️ Required elements not found for keyboard handler');
        return;
    }
    
    console.log('📱 Mobile keyboard handler initializing...');
    
    // ==========================================
    // KEYBOARD OPEN/CLOSE DETECTION
    // ==========================================
    
    let lastHeight = window.innerHeight;
    let keyboardHeight = 0;
    
    // When keyboard opens, viewport height shrinks
    window.addEventListener('resize', () => {
        const currentHeight = window.innerHeight;
        const heightDiff = lastHeight - currentHeight;
        
        // Keyboard opened (viewport shrunk by >150px)
        if (heightDiff > 150) {
            keyboardHeight = heightDiff;
            handleKeyboardOpen(keyboardHeight);
        } 
        // Keyboard closed (viewport grew back)
        else if (heightDiff < -150) {
            handleKeyboardClose();
        }
        
        lastHeight = currentHeight;
    });
    
    // ==========================================
    // FOCUS HANDLING
    // ==========================================
    
    userInput.addEventListener('focus', () => {
        // Wait for keyboard animation to complete
        setTimeout(() => {
            scrollInputIntoView();
        }, 300);
    });
    
    // ==========================================
    // INPUT TRACKING
    // ==========================================
    
    // As user types, keep input visible
    userInput.addEventListener('input', () => {
        if (document.activeElement === userInput) {
            requestAnimationFrame(() => {
                scrollInputIntoView();
            });
        }
    });
    
    // ==========================================
    // SCROLL MANAGEMENT
    // ==========================================
    
    function scrollInputIntoView() {
        userInput.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'nearest',
            inline: 'nearest'
        });
    }
    
    function handleKeyboardOpen(height) {
        console.log('⌨️ Keyboard opened, height:', height + 'px');
        
        // Add padding to bottom of chat container so messages aren't hidden
        if (chatContainer) {
            chatContainer.style.paddingBottom = `${height + 20}px`;
        }
        
        // Ensure input container stays visible
        if (inputContainer) {
            inputContainer.style.position = 'fixed';
            inputContainer.style.bottom = '0';
            inputContainer.style.zIndex = '1000';
        }
        
        // Scroll to keep current view in place
        setTimeout(scrollInputIntoView, 100);
    }
    
    function handleKeyboardClose() {
        console.log('⌨️ Keyboard closed');
        
        // Remove padding
        if (chatContainer) {
            chatContainer.style.paddingBottom = '';
        }
        
        // Reset input container
        if (inputContainer) {
            inputContainer.style.position = '';
            inputContainer.style.bottom = '';
        }
    }
    
    // ==========================================
    // iOS SPECIFIC FIXES
    // ==========================================
    
    const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
    
    if (isIOS) {
        console.log('🍎 iOS detected - applying specific fixes');
        
        // Fix iOS Safari bounce scroll interference
        let startY = 0;
        
        inputContainer.addEventListener('touchstart', (e) => {
            startY = e.touches[0].pageY;
        }, { passive: true });
        
        inputContainer.addEventListener('touchmove', (e) => {
            const y = e.touches[0].pageY;
            const scrollTop = inputContainer.scrollTop;
            
            // Prevent bounce when scrolling at boundaries
            if (scrollTop <= 0 && y > startY) {
                e.preventDefault();
            }
            
            if (scrollTop >= inputContainer.scrollHeight - inputContainer.clientHeight && y < startY) {
                e.preventDefault();
            }
        }, { passive: false });
        
        // Fix iOS viewport height issues
        // iOS Safari changes innerHeight when keyboard opens, but we need the true viewport
        const setVH = () => {
            const vh = window.innerHeight * 0.01;
            document.documentElement.style.setProperty('--vh', `${vh}px`);
        };
        
        setVH();
        window.addEventListener('resize', setVH);
        
        // Update CSS to use the custom property
        if (chatContainer) {
            chatContainer.style.height = 'calc(var(--vh, 1vh) * 100 - 140px)';
        }
    }
    
    // ==========================================
    // ANDROID SPECIFIC FIXES
    // ==========================================
    
    const isAndroid = /Android/.test(navigator.userAgent);
    
    if (isAndroid) {
        console.log('🤖 Android detected - applying specific fixes');
        
        // Android Chrome has different keyboard behavior
        // Ensure input stays visible when keyboard opens
        userInput.addEventListener('focus', () => {
            setTimeout(() => {
                window.scrollTo(0, document.body.scrollHeight);
            }, 400);
        });
    }
    
    // ==========================================
    // BLUR HANDLING
    // ==========================================
    
    userInput.addEventListener('blur', () => {
        // Small delay before closing to allow for button clicks
        setTimeout(() => {
            handleKeyboardClose();
        }, 100);
    });
    
    console.log('✅ Mobile keyboard handler initialized');
}

// Export for use in app.js
window.setupMobileKeyboardHandler = setupMobileKeyboardHandler;

console.log('✅ Mobile keyboard handler v1.0 loaded');
