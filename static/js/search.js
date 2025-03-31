// static/js/search.js
"use strict";

document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('universal-search-input');
    const suggestionsBox = document.getElementById('universal-suggestions-box');
    const mobileSearchInput = document.getElementById('mobile-search-input');

    if (!searchInput || !suggestionsBox) {
        console.warn("Universal search elements not found.");
    }
    if (!mobileSearchInput) {
        console.warn("Mobile search input not found.");
    }

    const suggestionsUrl = searchInput?.dataset.suggestionsUrl;
    if (!suggestionsUrl) {
        console.error("Search suggestions URL is not set!");
        return;
    }

    let debounceTimer;
    let currentRequestController = null;

    const fetchSuggestions = async (query, targetInput, targetBox) => {
        if (!targetBox) return;
        if (query.length < 2) { targetBox.innerHTML = ''; targetBox.classList.add('hidden'); return; }
        if (currentRequestController) currentRequestController.abort();
        currentRequestController = new AbortController();
        const signal = currentRequestController.signal;

        try {
            const url = `${suggestionsUrl}?q=${encodeURIComponent(query)}`;
            const response = await fetch(url, { headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, signal });
            if (!response.ok) { if (signal.aborted) return; throw new Error(`HTTP error ${response.status}`); }
            const data = await response.json(); if (signal.aborted) return;
            targetBox.innerHTML = ''; // Clear old
            if (data.results && data.results.length > 0) {
                data.results.forEach(item => {
                    const link = document.createElement('a');
                    link.href = item.url;
                    link.className = 'block px-4 py-2 text-sm hover:bg-gray-100 dark:hover:bg-dark-700 text-gray-800 dark:text-gray-200 transition-colors duration-150';
                    link.innerHTML = `<i class="fas fa-${item.icon || 'question-circle'} fa-fw mr-2 text-${item.color || 'gray'}-500 dark:text-ios-${item.color || 'gray'}"></i><span>${escapeHtml(item.title || 'N/A')}</span>${item.context ? `<span class="text-xs text-gray-500 dark:text-gray-400 ml-2">(${escapeHtml(item.context)})</span>` : ''}`;
                    link.addEventListener('mousedown', (e) => { e.preventDefault(); window.location.href = item.url; }); // Use mousedown for click before blur
                    targetBox.appendChild(link);
                });
            } else { targetBox.innerHTML = '<div class="p-2 text-sm text-gray-500 dark:text-gray-400">Ничего не найдено</div>'; }
            targetBox.classList.remove('hidden');
        } catch (error) {
            if (error.name === 'AbortError') console.log('Search fetch aborted');
            else { console.error('Error fetching suggestions:', error); targetBox.innerHTML = `<div class="p-2 text-sm text-red-600 dark:text-red-400">Ошибка: ${error.message}</div>`; targetBox.classList.remove('hidden'); }
        } finally { if (signal === currentRequestController?.signal) currentRequestController = null; }
    };

    // --- Helpers ---
    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return unsafe;
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    [searchInput, mobileSearchInput].forEach(input => {
        if (!input) return;
        const targetBox = suggestionsBox; // Assuming same suggestion box for mobile for now
        input.addEventListener('input', (event) => {
            const query = event.target.value.trim(); clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => fetchSuggestions(query, input, targetBox), 300);
        });
        input.addEventListener('focus', () => { if (input.value.trim().length >= 2) fetchSuggestions(input.value.trim(), input, targetBox); });
        input.addEventListener('blur', () => { setTimeout(() => { if (targetBox) targetBox.classList.add('hidden'); }, 150); });
        input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault(); const query = input.value.trim();
                if (query) { console.log(`Perform full search for: ${query}`); /* Add full search redirect if needed */ if (targetBox) targetBox.classList.add('hidden'); input.blur(); }
            } else if (event.key === 'Escape') { if (targetBox) { targetBox.innerHTML = ''; targetBox.classList.add('hidden'); } }
        });
    });
});