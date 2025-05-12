"use strict";

document.addEventListener('DOMContentLoaded', function () {
    const setupSearch = (inputId, suggestionsBoxId) => {
        const searchInput = document.getElementById(inputId);
        const suggestionsBox = document.getElementById(suggestionsBoxId);

        if (!searchInput || !suggestionsBox) {
            console.warn(`Search elements not found for: ${inputId}, ${suggestionsBoxId}`);
            return;
        }

        const suggestionsUrl = searchInput.dataset.suggestionsUrl;
        if (!suggestionsUrl) {
            console.error(`Search suggestions URL is not set for input: ${inputId}`);
            return;
        }

        let debounceTimer;
        let currentRequestController = null;
        let activeSuggestionIndex = -1;

        const fetchSuggestions = async (query) => {
            if (query.length < 2) {
                suggestionsBox.innerHTML = '';
                suggestionsBox.classList.add('hidden');
                return;
            }

            if (currentRequestController) {
                currentRequestController.abort();
            }
            currentRequestController = new AbortController();
            const signal = currentRequestController.signal;

            try {
                const url = `${suggestionsUrl}?q=${encodeURIComponent(query)}`;
                const response = await fetch(url, {
                    headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                    signal
                });

                if (!response.ok) {
                    if (signal.aborted) return;
                    throw new Error(`HTTP error ${response.status}`);
                }
                const data = await response.json();
                if (signal.aborted) return;

                renderSuggestions(data.results || []);
                activeSuggestionIndex = -1; // Reset active suggestion

            } catch (error) {
                if (error.name === 'AbortError') {
                    console.log('Search fetch aborted for previous query.');
                } else {
                    console.error('Error fetching suggestions:', error);
                    suggestionsBox.innerHTML = `<div class="p-3 text-sm text-red-600 dark:text-red-400">Ошибка: ${escapeHtml(error.message)}</div>`;
                    suggestionsBox.classList.remove('hidden');
                }
            } finally {
                if (signal === currentRequestController?.signal) {
                    currentRequestController = null;
                }
            }
        };

        const renderSuggestions = (results) => {
            suggestionsBox.innerHTML = ''; // Clear old suggestions
            if (results.length > 0) {
                results.forEach((item, index) => {
                    const link = document.createElement('a');
                    link.href = item.url || '#';
                    link.className = 'block px-4 py-2.5 text-sm hover:bg-gray-100 dark:hover:bg-dark-700 text-gray-800 dark:text-gray-200 transition-colors duration-150 border-b border-gray-100 dark:border-dark-700 last:border-b-0';
                    link.dataset.index = index;
                    link.innerHTML = `
                        <div class="flex items-center">
                            <i class="fas fa-${escapeHtml(item.icon || 'question-circle')} fa-fw mr-2.5 text-gray-400 dark:text-gray-500 w-4 text-center"></i>
                            <div class="flex-1 min-w-0">
                                <span class="font-medium truncate block">${escapeHtml(item.title || 'N/A')}</span>
                                ${item.context ? `<span class="text-xs text-gray-500 dark:text-gray-400 truncate block">${escapeHtml(item.context)}</span>` : ''}
                            </div>
                        </div>`;
                    link.addEventListener('mousedown', (e) => { // Use mousedown to trigger before blur hides suggestions
                        e.preventDefault();
                        window.location.href = item.url;
                    });
                    suggestionsBox.appendChild(link);
                });
                suggestionsBox.classList.remove('hidden');
            } else {
                suggestionsBox.innerHTML = `<div class="p-3 text-sm text-gray-500 dark:text-gray-400 italic">{% translate "Ничего не найдено" %}</div>`;
                suggestionsBox.classList.remove('hidden');
            }
        };

        const highlightSuggestion = (index) => {
            const suggestions = suggestionsBox.querySelectorAll('a');
            suggestions.forEach((suggestion, i) => {
                suggestion.classList.toggle('bg-gray-100', i === index);
                suggestion.classList.toggle('dark:bg-dark-700', i === index);
            });
        };

        searchInput.addEventListener('input', (event) => {
            const query = event.target.value.trim();
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => fetchSuggestions(query), 300);
        });

        searchInput.addEventListener('focus', () => {
            if (searchInput.value.trim().length >= 2) {
                fetchSuggestions(searchInput.value.trim());
            }
        });

        searchInput.addEventListener('blur', () => {
            setTimeout(() => {
                if (!suggestionsBox.matches(':hover')) { // Don't hide if mouse is over suggestions
                    suggestionsBox.classList.add('hidden');
                    activeSuggestionIndex = -1;
                }
            }, 150);
        });

        searchInput.addEventListener('keydown', (event) => {
            const suggestions = suggestionsBox.querySelectorAll('a');
            if (suggestions.length === 0 && event.key !== 'Escape') return;

            if (event.key === 'ArrowDown') {
                event.preventDefault();
                activeSuggestionIndex = (activeSuggestionIndex + 1) % suggestions.length;
                highlightSuggestion(activeSuggestionIndex);
            } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                activeSuggestionIndex = (activeSuggestionIndex - 1 + suggestions.length) % suggestions.length;
                highlightSuggestion(activeSuggestionIndex);
            } else if (event.key === 'Enter') {
                event.preventDefault();
                if (activeSuggestionIndex > -1 && suggestions[activeSuggestionIndex]) {
                    suggestions[activeSuggestionIndex].click();
                } else if (searchInput.value.trim()){
                    console.log(`Perform full search for: ${searchInput.value.trim()}`);
                    // Potentially redirect to a full search results page
                    // window.location.href = `/search/?q=${encodeURIComponent(searchInput.value.trim())}`;
                     suggestionsBox.classList.add('hidden');
                     searchInput.blur();
                }
            } else if (event.key === 'Escape') {
                suggestionsBox.innerHTML = '';
                suggestionsBox.classList.add('hidden');
                activeSuggestionIndex = -1;
            }
        });
    };

    setupSearch('universal-search-input', 'universal-suggestions-box');
    setupSearch('mobile-search-input', 'mobile-suggestions-box'); // Setup for mobile search

    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }
});