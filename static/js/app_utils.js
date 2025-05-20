"use strict";

// --- CSRF Token ---
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
const csrfToken = getCookie('csrftoken');

// --- Toastify Notifications ---
function showAppNotification(message, type = 'info', duration = 4000) {
    if (typeof Toastify !== 'function') {
        console.warn("Toastify not loaded. Showing alert instead:", message);
        alert(message);
        return;
    }

    let backgroundColor;
    switch (type) {
        case 'success': backgroundColor = "linear-gradient(to right, #00b09b, #96c93d)"; break;
        case 'error':   backgroundColor = "linear-gradient(to right, #ff5f6d, #ffc371)"; break;
        case 'warning': backgroundColor = "linear-gradient(to right, #f39c12, #f1c40f)"; break;
        default:        backgroundColor = "linear-gradient(to right, #007bff, #00c6ff)"; break; // info
    }

    Toastify({
        text: message,
        duration: duration,
        gravity: "top",
        position: "right",
        stopOnFocus: true,
        className: `toastify-${type}`,
        style: { background: backgroundColor }
    }).showToast();
}
window.showAppNotification = showAppNotification; // Make global for other scripts

// --- Authenticated Fetch ---
async function authenticatedFetch(url, options = {}, indicatorSelector = '#loading-indicator') {
    const indicator = indicatorSelector ? document.querySelector(indicatorSelector) : null;
    if (indicator) indicator.classList.remove('hidden');

    const method = options.method?.toUpperCase() || 'GET';
    const defaultHeaders = {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
    };

    if (csrfToken && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
        defaultHeaders['X-CSRFToken'] = csrfToken;
    }

    let body = options.body;
    // If body is an object and not FormData, stringify it and set Content-Type
    if (body && typeof body === 'object' && !(body instanceof FormData)) {
        try {
            body = JSON.stringify(body);
            if (!options.headers || !options.headers['Content-Type']) {
                defaultHeaders['Content-Type'] = 'application/json';
            }
        } catch (e) {
            console.error("Failed to stringify body for authenticatedFetch:", e);
            if (indicator) indicator.classList.add('hidden');
            if (window.showAppNotification) window.showAppNotification('Ошибка подготовки данных запроса.', 'error');
            throw new Error("Invalid body data provided");
        }
    }

    options.headers = { ...defaultHeaders, ...options.headers };
    options.body = body; // body might be stringified JSON or FormData

    try {
        const response = await fetch(url, options);

        if (!response.ok) {
            let errorData = { message: `Server error: ${response.status}` };
            try {
                const contentType = response.headers.get("content-type");
                if (contentType?.includes("application/json")) {
                    errorData = await response.json();
                } else {
                    const textError = await response.text();
                    errorData.message = textError.substring(0, 200) || errorData.message;
                }
            } catch (e) { console.warn("Could not parse error response body."); }

            console.error("AuthenticatedFetch Error:", response.status, errorData);
            // Set a flag on the error object so downstream handlers know if notification was shown
            errorData.notificationShown = true;
            if (window.showAppNotification) {
                 window.showAppNotification(errorData.message || 'Request failed.', 'error');
            }

            const error = new Error(errorData.message || `HTTP error! status: ${response.status}`);
            error.response = response;
            error.data = errorData;
            throw error;
        }
        return response;
    } catch (error) {
        console.error('authenticatedFetch failed:', error);
        if (!error.notificationShown && window.showAppNotification) {
             window.showAppNotification('Network error or request failed.', 'error');
        }
        throw error; // Re-throw for specific handling
    } finally {
        if (indicator) indicator.classList.add('hidden');
    }
}
window.authenticatedFetch = authenticatedFetch; // Make global