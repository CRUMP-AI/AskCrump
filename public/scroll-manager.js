(function initializeScrollManager() {
    'use strict';

    let chatContainer = null;
    let scrollToEndButton = null;
    let userIsReviewingHistory = false;
    let reviewTimeout = null;

    function initialize() {
        chatContainer = document.getElementById('chatContainer');
        scrollToEndButton = document.getElementById('scrollToEndBtn');
        if (!chatContainer || !scrollToEndButton) return;

        chatContainer.addEventListener('scroll', handleScroll, { passive: true });
        scrollToEndButton.addEventListener('click', scrollToBottom);
    }

    function handleScroll() {
        const distance = distanceFromBottom();
        const showControl = distance > 200;
        scrollToEndButton?.classList.toggle('visible', showControl);
        userIsReviewingHistory = showControl;

        clearTimeout(reviewTimeout);
        reviewTimeout = setTimeout(() => {
            userIsReviewingHistory = distanceFromBottom() > 200;
        }, 3000);
    }

    function distanceFromBottom() {
        if (!chatContainer) return 0;
        return chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight;
    }

    function scrollToBottom(behaviorOrEvent) {
        if (!chatContainer) return;
        const behavior = typeof behaviorOrEvent === 'string' ? behaviorOrEvent : 'smooth';
        chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior });
        scrollToEndButton?.classList.remove('visible');
        userIsReviewingHistory = false;
    }

    function scrollToMessageTop(messageElement) {
        if (!chatContainer || !messageElement || userIsReviewingHistory) return;

        setTimeout(() => {
            const containerTop = chatContainer.getBoundingClientRect().top;
            const messageTop = messageElement.getBoundingClientRect().top;
            const top = messageTop - containerTop + chatContainer.scrollTop - 20;
            chatContainer.scrollTo({ top, behavior: 'smooth' });
        }, 100);
    }

    function autoScrollToBottom() {
        if (!userIsReviewingHistory) scrollToBottom('smooth');
    }

    window.crumpScrollManager = {
        init: initialize,
        scrollToBottom,
        scrollToMessageTop,
        autoScrollToBottom,
        isNearBottom: () => distanceFromBottom() < 100,
        setUserScrolling: value => { userIsReviewingHistory = Boolean(value); }
    };
}());
