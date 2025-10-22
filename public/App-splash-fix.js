// ==========================================
// CRUMP AI - APP.JS SPLASH SCREEN FIX
// Add this fix to app.js line 540-550
// ==========================================

// FIND THIS FUNCTION (around line 540):
/*
function initializeSplashScreen() {
    const splashScreen = document.getElementById('splashScreen');
    splashScreen.style.display = 'flex';  // ❌ CRASHES if null
    
    setTimeout(() => {
        splashScreen.classList.add('fade-out');
        setTimeout(() => {
            splashScreen.style.display = 'none';
        }, 500);
    }, 2000);
}
*/

// REPLACE WITH THIS SAFE VERSION:
function initializeSplashScreen() {
    const splashScreen = document.getElementById('splashScreen');
    
    // CRITICAL FIX: Check if element exists before accessing
    if (!splashScreen) {
        console.warn('⚠️ Splash screen element not found in HTML');
        return;
    }
    
    splashScreen.style.display = 'flex';
    
    setTimeout(() => {
        splashScreen.classList.add('fade-out');
        setTimeout(() => {
            splashScreen.style.display = 'none';
        }, 500);
    }, 2000);
}

// ==========================================
// ALTERNATIVE: Make splash screen optional
// ==========================================

// If you want to make the splash screen completely optional:
function initializeSplashScreen() {
    const splashScreen = document.getElementById('splashScreen');
    
    if (!splashScreen) {
        console.log('ℹ️ No splash screen - skipping initialization');
        // Just proceed without splash screen
        return;
    }
    
    // Only run splash animation if element exists
    try {
        splashScreen.style.display = 'flex';
        
        setTimeout(() => {
            splashScreen.classList.add('fade-out');
            setTimeout(() => {
                splashScreen.style.display = 'none';
            }, 500);
        }, 2000);
    } catch (error) {
        console.error('❌ Splash screen error:', error);
        // Hide it immediately if there's an error
        splashScreen.style.display = 'none';
    }
}

// ==========================================
// ALSO CHECK THESE OTHER DOM ELEMENTS
// ==========================================

// Add null checks to other critical DOM accesses in app.js:

// Example for DOMContentLoaded event:
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Crump AI initializing...');
    
    // Check critical elements exist
    const requiredElements = [
        'chatContainer',
        'userInput',
        'sendButton',
        'newChatBtn'
    ];
    
    const missing = [];
    for (const id of requiredElements) {
        if (!document.getElementById(id)) {
            missing.push(id);
        }
    }
    
    if (missing.length > 0) {
        console.error('❌ CRITICAL: Missing required HTML elements:', missing);
        alert('Error: Page HTML is incomplete. Please refresh or contact support.');
        return;
    }
    
    // Now proceed with initialization...
    // Rest of your DOMContentLoaded code
});

console.log('✅ Splash screen fix applied');
