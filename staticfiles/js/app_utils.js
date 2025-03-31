// static/js/app_utils.js
"use strict";

// === Глобальные Утилиты (Определяются СРАЗУ, ВНЕ DOMContentLoaded) ===

// --- Получение CSRF токена ---
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// --- Показ Уведомлений ---
function showNotification(message, type = 'info') {
    console.log(`Notification (${type}): ${message}`);
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        container.className = 'fixed bottom-5 right-5 z-[100] space-y-2';
        document.body.appendChild(container);
    }

    const notification = document.createElement('div');
    notification.className = 'p-4 rounded-lg shadow-lg text-sm transition-opacity duration-300 ease-out max-w-sm';
    notification.setAttribute('role', 'alert');

    switch (type) {
        case 'success': notification.classList.add('bg-green-100', 'border', 'border-green-400', 'text-green-700', 'dark:bg-green-800/90', 'dark:text-green-200', 'dark:border-green-600'); break;
        case 'error': notification.classList.add('bg-red-100', 'border', 'border-red-400', 'text-red-700', 'dark:bg-red-800/90', 'dark:text-red-200', 'dark:border-red-600'); break;
        case 'warning': notification.classList.add('bg-yellow-100', 'border', 'border-yellow-400', 'text-yellow-700', 'dark:bg-yellow-800/90', 'dark:text-yellow-200', 'dark:border-yellow-600'); break;
        default: notification.classList.add('bg-blue-100', 'border', 'border-blue-400', 'text-blue-700', 'dark:bg-blue-800/90', 'dark:text-blue-200', 'dark:border-blue-600'); break;
    }

    notification.textContent = message;
    container.appendChild(notification);

    requestAnimationFrame(() => { notification.style.opacity = '0'; requestAnimationFrame(() => { notification.style.opacity = '1'; }); });
    setTimeout(() => { notification.style.opacity = '0'; notification.addEventListener('transitionend', () => notification.remove()); }, 5000);
}
window.showNotification = showNotification;

// --- Аутентифицированный Fetch ---
// Default indicatorSelector is '#loading-indicator'
async function authenticatedFetch(url, options = {}, indicatorSelector = '#loading-indicator') {
    const indicator = indicatorSelector ? document.querySelector(indicatorSelector) : null;
    if (indicator) indicator.classList.remove('hidden');

    const csrftoken = getCookie('csrftoken');
    const method = options.method?.toUpperCase() || 'GET';

    const defaultHeaders = { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest', };
    if (csrftoken && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) { defaultHeaders['X-CSRFToken'] = csrftoken; }

    let body = options.body;
    if (body && typeof body === 'object' && !(body instanceof FormData)) {
        try {
            body = JSON.stringify(body);
            if (!options.headers || !options.headers['Content-Type']) { defaultHeaders['Content-Type'] = 'application/json'; }
        } catch (e) {
            console.error("Failed to stringify body for authenticatedFetch:", e);
            if (indicator) indicator.classList.add('hidden');
            if (window.showNotification) window.showNotification('Ошибка подготовки данных запроса.', 'error');
            throw new Error("Invalid body data provided to authenticatedFetch");
        }
    }

    options.headers = { ...defaultHeaders, ...options.headers };
    options.body = body;

    console.log(`authenticatedFetch: ${method} ${url}`);

    try {
        const response = await fetch(url, options);
        console.log(`authenticatedFetch Response: ${response.status} ${response.statusText}`);

        if (!response.ok) {
            let errorData = { message: `Ошибка сервера: ${response.status}` };
            try {
                const contentType = response.headers.get("content-type");
                if (contentType?.includes("application/json")) { errorData = await response.json(); }
                else {
                    const textError = await response.text();
                    const errorMatch = textError.match(/<title>(.*?)<\/title>/i) || textError.match(/<p class="error.*?">(.*?)<\/p>/i);
                    errorData.message = errorMatch ? errorMatch[1].trim() : (textError.substring(0, 200) || errorData.message);
                }
            } catch (e) { console.warn("Could not parse error response body."); errorData.message = response.statusText || errorData.message; }

            console.error("AuthenticatedFetch Error:", response.status, errorData);
            if (window.showNotification) { window.showNotification(errorData.message || 'Произошла ошибка при выполнении запроса.', 'error'); }

            const error = new Error(errorData.message || `HTTP error! status: ${response.status}`);
            error.response = response; error.data = errorData;
            throw error;
        }
        return response;
    } catch (error) {
        console.error('authenticatedFetch failed:', error.message || error);
        if (!(error instanceof Error && error.response)) {
             if (window.showNotification) window.showNotification('Ошибка сети или выполнения запроса.', 'error');
        }
        throw error;
    } finally {
        // Hide the indicator regardless of success or failure
        if (indicator) {
             console.log("Hiding indicator:", indicatorSelector); // Add log for debugging
             indicator.classList.add('hidden');
        } else {
             console.log("Indicator not found or not specified:", indicatorSelector); // Add log
        }
    }
}
window.authenticatedFetch = authenticatedFetch;

// === Код, выполняемый после загрузки DOM ===
document.addEventListener('DOMContentLoaded', function () {
    console.log("Initializing app_utils DOM listeners...");
    // --- Sidebar Toggle --- (Unchanged)
    const sideBar = document.getElementById('sideBar');
    const sideBarOpenBtn = document.getElementById('sideBarOpenBtn');
    const sideBarCloseBtn = document.getElementById('sideBarCloseBtn');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');
    if (sideBarOpenBtn && sideBarCloseBtn && sidebarBackdrop && sideBar) { /* ... sidebar logic ... */ }
    else { console.warn("Sidebar elements not found. Skipping sidebar toggle initialization."); }

    console.log("app_utils DOM listeners initialized.");
});