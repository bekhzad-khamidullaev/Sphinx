"use strict";

document.addEventListener('DOMContentLoaded', function () {
    console.log("main.js DOM fully loaded and parsed");

    // --- Preloader ---
    const preloader = document.getElementById('preloader');
    if (preloader) {
        const hidePreloader = () => {
            preloader.style.opacity = '0';
            preloader.addEventListener('transitionend', () => {
                preloader.style.display = 'none';
            }, { once: true });
        };
        window.addEventListener('load', () => {
            setTimeout(hidePreloader, 50); // Small delay for smoother transition
        });
        setTimeout(hidePreloader, 3000); // Backup hide
    }

    // --- Dark Mode Toggle ---
    function applyTheme(theme) {
        if (theme === 'dark') {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }
        localStorage.setItem('theme', theme);
    }

    const darkModeToggle = document.getElementById('darkModeToggle');
    const darkModeToggleMobile = document.getElementById('darkModeToggleMobile');
    const currentTheme = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    applyTheme(currentTheme);

    const toggleFunction = () => {
        const newTheme = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
        applyTheme(newTheme);
    };

    darkModeToggle?.addEventListener('click', toggleFunction);
    darkModeToggleMobile?.addEventListener('click', toggleFunction);


    // --- Current Year ---
    const yearElement = document.getElementById('current-year');
    if (yearElement) {
        yearElement.textContent = new Date().getFullYear();
    }

    // --- Toastify Notifications ---
    // This can be expanded to handle Django messages automatically
    const messagesContainer = document.getElementById('messages-container');
    if (messagesContainer && typeof Toastify === 'function') {
        const messages = messagesContainer.querySelectorAll('div[role="alert"]'); // Assuming this structure from messages.html
        messages.forEach(messageElement => {
            const messageText = messageElement.querySelector('.flex-1 > div:last-child')?.textContent || 'Notification';
            let type = 'info'; // default
            if (messageElement.classList.contains('border-green-500')) type = 'success';
            else if (messageElement.classList.contains('border-red-500')) type = 'error';
            else if (messageElement.classList.contains('border-yellow-500')) type = 'warning';

            Toastify({
                text: messageText.trim(),
                duration: 5000,
                gravity: "top", // `top` or `bottom`
                position: "right", // `left`, `center` or `right`
                stopOnFocus: true, // Prevents dismissing of toast on hover
                className: `toastify-${type}`,
                style: {
                    background: type === 'success' ? "linear-gradient(to right, #00b09b, #96c93d)" :
                                type === 'error' ? "linear-gradient(to right, #ff5f6d, #ffc371)" :
                                type === 'warning' ? "linear-gradient(to right, #f39c12, #f1c40f)" :
                                "linear-gradient(to right, #007bff, #00c6ff)", // info/default
                },
            }).showToast();
            messageElement.remove(); // Remove original Django message element after showing toast
        });
    }
    
    // --- Global Error Handler for Uncaught JS Errors ---
    window.addEventListener('error', function(event) {
        console.error('Unhandled JS Error:', event.message, 'at', event.filename, ':', event.lineno);
        if (window.showNotification) { // Check if showNotification is defined globally
            window.showNotification('Произошла внутренняя ошибка скрипта. Подробности в консоли.', 'error');
        } else {
            // Fallback alert if showNotification is not available yet or at all
            // alert('Произошла внутренняя ошибка скрипта. Пожалуйста, проверьте консоль разработчика.');
        }
    });

    console.log("main.js initialization complete.");
});
