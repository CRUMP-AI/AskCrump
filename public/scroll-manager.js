(function initializeScrollManager() {
    'use strict';

    let chatContainer = null;
    let scrollToEndButton = null;
    let initialized = false;

    function initialize() {
        chatContainer = document.getElementById('chatContainer');
        scrollToEndButton = document.getElementById('scrollToEndBtn');
        if (!chatContainer || !scrollToEndButton || initialized) return;

        chatContainer.addEventListener('scroll', handleScroll, { passive: true });
        scrollToEndButton.addEventListener('click', jumpToNewest);
        initialized = true;
        handleScroll();
    }

    function handleScroll() {
        const distance = distanceFromBottom();
        const showControl = distance > 200;
        scrollToEndButton?.classList.toggle('visible', showControl);
        scrollToEndButton?.setAttribute('aria-hidden', showControl ? 'false' : 'true');
    }

    function distanceFromBottom() {
        if (!chatContainer) return 0;
        return chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight;
    }

    function jumpToNewest(event) {
        if (!chatContainer) return;
        event?.preventDefault?.();
        chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: 'smooth' });
        scrollToEndButton?.classList.remove('visible');
        scrollToEndButton?.setAttribute('aria-hidden', 'true');
    }

    window.crumpScrollManager = {
        init: initialize,
        // Compatibility no-ops: renders, streams, presence, images, and restored
        // history never receive authority to move the conversation viewport.
        scrollToBottom: () => undefined,
        scrollToMessageTop: () => undefined,
        autoScrollToBottom: () => undefined,
        isNearBottom: () => distanceFromBottom() < 100,
        setUserScrolling: () => handleScroll(),
    };
}());
