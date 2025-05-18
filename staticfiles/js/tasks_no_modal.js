// tasks/static/js/tasks_no_modal.js
"use strict";

document.addEventListener('DOMContentLoaded', () => {
    // --- Polyfills and Helpers ---
    if (window.NodeList && !NodeList.prototype.forEach) {
        NodeList.prototype.forEach = Array.prototype.forEach;
    }
    if (window.HTMLCollection && !HTMLCollection.prototype.forEach) {
        HTMLCollection.prototype.forEach = Array.prototype.forEach;
    }
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

    window.authenticatedFetch = async (url, options = {}) => {
        const defaultHeaders = {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrfToken,
        };
        if (options.method && ['POST', 'PUT', 'PATCH'].includes(options.method.toUpperCase())) {
            if (!(options.body instanceof FormData)) {
                 defaultHeaders['Content-Type'] = 'application/json';
            }
        }
        options.headers = { ...defaultHeaders, ...options.headers };
        if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData) && options.headers['Content-Type'] === 'application/json') {
            options.body = JSON.stringify(options.body);
        }
        try {
            const response = await fetch(url, options);
            return response;
        } catch (error) {
            console.error(`AuthenticatedFetch error for ${url}:`, error);
            error.handled = false; // Позволяем другим обработчикам поймать, если нужно
            throw error; // Перебрасываем ошибку
        }
    };

    // --- Shared Variables & Functions ---
    const taskListContainer = document.getElementById('task-list');
    const kanbanBoardContainer = document.getElementById('kanban-board');
    const taskDetailContainer = document.getElementById('task-detail-container'); // <--- ЕДИНСТВЕННОЕ ОБЪЯВЛЕНИЕ

    const configElement = document.getElementById('task-list-config');
    let taskListConfig = { updateStatusUrlTemplate: "", deleteTaskUrlTemplate: "" }; // Добавил deleteTaskUrlTemplate
    if (configElement) {
        try {
            taskListConfig = JSON.parse(configElement.textContent);
            if (!taskListConfig.updateStatusUrlTemplate) {
                console.warn("Warning: updateStatusUrlTemplate is missing from task-list-config JSON.");
            }
            if (!taskListConfig.deleteTaskUrlTemplate) { // Проверка для URL удаления
                console.warn("Warning: deleteTaskUrlTemplate is missing from task-list-config JSON.");
            }
        } catch (e) {
            console.error("CRITICAL: Could not parse task-list-config JSON:", e);
        }
    } else {
        // Эта ошибка выводится только если мы на странице списка задач
        if (taskListContainer || kanbanBoardContainer) {
            console.error("CRITICAL: task-list-config script tag not found on task list/kanban page! Actions will fail.");
        }
    }
    
    window.taskStatusMapping = {};
    try {
        const statusMappingElement = document.getElementById('status-mapping-data');
        if (statusMappingElement) {
            window.taskStatusMapping = JSON.parse(statusMappingElement.textContent);
        } else {
           // console.warn("Status mapping data script tag (#status-mapping-data) not found."); // Менее критично
        }
    } catch (e) { console.error("Error parsing status mapping data:", e); }

    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return String(unsafe); // Преобразуем в строку, если не строка
        return unsafe
            .replace(/&/g, "&")
            .replace(/</g, "<")
            .replace(/>/g, ">")
            .replace(/"/g, """)
            .replace(/'/g, "'"); // Заменил на ' для HTML атрибутов
    }

    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    // --- Task List / Kanban Board Logic ---
    if (taskListContainer || kanbanBoardContainer) { // Изменил условие, чтобы код выполнялся если есть хотя бы один из контейнеров
        console.log("Task list or Kanban container found. Initializing list/kanban logic...");
        const toggleViewBtn = document.getElementById('toggleViewBtn');
        const toggleViewBtnMobile = document.getElementById('toggleViewBtnMobile');
        // columnToggleDropdown теперь column-toggle-dropdown-wrapper
        const columnToggleDropdownWrapper = document.getElementById('column-toggle-dropdown-wrapper'); 
        const resetHiddenColumnsBtn = document.getElementById('resetHiddenColumnsBtn');
        const columnCheckboxes = document.querySelectorAll('.toggle-column-checkbox');
        window.wsRetryCount = 0;

        let taskUpdateSocket = null; // Объявляем здесь, чтобы была доступна в функциях ниже

        function connectTaskListWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            // Используем глобальную функцию, если она определена в шаблоне
            const wsPath = typeof window.djangoWsPath === 'function' ? window.djangoWsPath('tasks_list_updates') : '/ws/tasks_list_updates/'; // Пример имени для WS задач
            const wsUrl = `${protocol}${window.location.host}${wsPath.startsWith('/') ? wsPath : '/' + wsPath}`;
            
            if (!("WebSocket" in window)) { 
                if (window.showNotification) window.showNotification('WebSocket не поддерживается вашим браузером.', 'error'); 
                return; 
            }
            try {
                taskUpdateSocket = new WebSocket(wsUrl);
                taskUpdateSocket.onopen = () => { 
                    window.wsRetryCount = 0; 
                    console.log('Task List WebSocket connected.'); 
                    if (window.showNotification) window.showNotification('Обновления задач активны.', 'info', 2000);
                };
                taskUpdateSocket.onmessage = handleTaskListWebSocketMessage; // Определена ниже
                taskUpdateSocket.onerror = (error) => { 
                    console.error('Task List WebSocket error:', error); 
                    if (window.showNotification) window.showNotification('Ошибка WebSocket соединения с задачами.', 'error');
                };
                taskUpdateSocket.onclose = (event) => {
                    console.log(`Task List WebSocket closed. Code: ${event.code}, Clean: ${event.wasClean}, Reason: ${event.reason}`);
                    if (!event.wasClean && event.code !== 1000 && event.code !== 1001) { // 1000 - Normal, 1001 - Going Away
                        if (window.showNotification) window.showNotification('Соединение для обновления задач потеряно. Попытка переподключения...', 'warning');
                        const retryDelay = Math.min(30000, (Math.pow(2, window.wsRetryCount) * 1000) + Math.floor(Math.random() * 1000));
                        window.wsRetryCount++; 
                        console.log(`Retrying Task List WS connection in ${retryDelay / 1000}s (attempt ${window.wsRetryCount})`);
                        setTimeout(connectTaskListWebSocket, retryDelay);
                    } else { 
                        window.wsRetryCount = 0; // Сброс счетчика при чистом закрытии
                    }
                };
            } catch (e) { 
                if (window.showNotification) window.showNotification('Не удалось установить WebSocket соединение с задачами.', 'error'); 
                console.error("Task List WebSocket connection failed:", e); 
            }
        }

        function handleTaskListWebSocketMessage(event) {
            // ... (логика обработки сообщений WebSocket для списка задач, как была) ...
            // Пример:
             try {
                const data = JSON.parse(event.data);
                console.log("Task List WS Rcvd:", data);
                if ((data.type === 'list_update' || data.type === 'task_update') && data.message) {
                    const message = data.message;
                    if (!message.action || !message.id) {
                        console.warn("WS task update missing action or id:", message);
                        return;
                    }
                    switch(message.action) {
                        case 'create':
                        case 'update':
                            if (window.showNotification) window.showNotification(`Задача #${escapeHtml(message.task_number || message.id)} ${message.action === 'create' ? 'создана' : 'обновлена'}. Обновление страницы...`, 'info', 3000);
                            // Для простоты - перезагрузка. В идеале - обновить конкретный элемент.
                            debounce(() => { window.location.reload(); }, 1500)(); 
                            break;
                        case 'delete':
                            removeTaskFromUI(message.id); // Убедитесь, что эта функция определена
                            if (window.showNotification) window.showNotification(`Задача #${escapeHtml(message.task_number || message.id)} удалена.`, 'info');
                            break;
                    }
                } else if (data.type === 'status_update_confirmation' && data.task_id) { // Если сервер подтверждает смену статуса
                    updateTaskUI(data.task_id, data.new_status_key, data.new_status_display); // Убедитесь, что эта функция определена
                } else if (data.type === 'error_message' || (data.message && data.type && data.type.endsWith('_error'))) {
                    if (window.showNotification) window.showNotification(`Ошибка WebSocket: ${escapeHtml(data.message)}`, 'error');
                }
            } catch (error) { console.error('Error processing Task List WS Message:', error, "Raw data:", event.data); }
        }
        
        // ... (initializeViewSwitcher, initializeKanban, updateKanbanColumnUI, initializeColumnToggler, restoreHiddenColumns)
        // ... (initializeListSort, initializeListStatusChange, setupDeleteTaskHandler, initializeListDeleteButtons, initializeKanbanDeleteButtons)
        // ... (updateTaskUI, updateTaskUIInKanban, updateTaskUIInList, updateStatusDropdownAppearance, removeTaskFromUI)
        // Эти функции должны быть здесь, как в вашем исходном файле.
        // Для краткости я их не дублирую, но они должны быть в этом блоке `if (taskListContainer || kanbanBoardContainer)`
        // или объявлены глобально, если используются и на других страницах.

        // Вызовы инициализации для страницы списка задач/канбана
        if (toggleViewBtn || toggleViewBtnMobile) initializeViewSwitcher();
        if (columnToggleDropdownWrapper) initializeColumnToggler(); // Используем wrapper
        // connectTaskListWebSocket(); // Вызов для подключения к WebSocket
    }


    // --- Task Detail Page Specific Logic ---
    // const taskDetailContainer = document.getElementById('task-detail-container'); // <--- УДАЛЕНО ПОВТОРНОЕ ОБЪЯВЛЕНИЕ
    if (taskDetailContainer) { // Используем переменную, объявленную в начале
        console.log("Task detail container found. Initializing detail page logic...");
        let taskDetailData = {};
        try {
            const dataEl = document.getElementById('task-detail-data');
            if (!dataEl) throw new Error("Script tag #task-detail-data not found!");
            taskDetailData = JSON.parse(dataEl.textContent);
            if (!taskDetailData.taskId) throw new Error("taskId missing in taskDetailData");
            taskDetailData.translations = taskDetailData.translations || {};
            taskDetailData.defaultAvatarUrl = taskDetailData.defaultAvatarUrl || '/static/img/user.svg';
        } catch (e) {
            console.error("Task Detail data initialization error:", e);
            return; 
        }

        const commentForm = document.getElementById('comment-form');
        const commentTextArea = document.getElementById('id_text'); 
        const commentSubmitBtn = commentForm?.querySelector('button[type="submit"]');
        const commentTextErrors = document.getElementById('comment-text-errors');
        const commentNonFieldErrors = document.getElementById('comment-non-field-errors');
        const commentList = document.getElementById('comment-list'); // Для addCommentToDOM

        if (!commentForm) console.error("Comment form (#comment-form) not found on detail page!");
        if (!commentTextArea) console.error("Comment textarea (#id_text) not found on detail page!");
        if (!commentSubmitBtn) console.error("Comment submit button not found on detail page!");

        if (commentForm && commentTextArea && commentSubmitBtn) {
            console.log("Comment form and essential elements for detail page found.");
            
            function addCommentToDOM(comment) {
                console.log("Adding comment to DOM:", comment);
                const noMessagesPlaceholder = document.getElementById('no-comments-message');
                if (commentList && comment && comment.author) { // Добавил проверку comment.author
                    if (noMessagesPlaceholder) noMessagesPlaceholder.style.display = 'none';
                    
                    const div = document.createElement('div');
                    div.className = 'flex space-x-3 comment-item';
                    div.id = `comment-${comment.id}`;
                    
                    const authorName = escapeHtml(comment.author.display_name || comment.author.username || (taskDetailData.translations.unknownUser || "Автор"));
                    const authorAvatar = escapeHtml(comment.author.avatar_url || taskDetailData.defaultAvatarUrl);
                    // Форматирование времени
                    let timeDisplay = taskDetailData.translations.justNow || 'только что';
                    let timeTitle = new Date(comment.created_at_iso).toLocaleString();
                    try {
                        // Тут можно добавить вашу функцию formatRelativeTime, если она есть
                        // timeDisplay = formatRelativeTime(comment.created_at_iso); 
                    } catch(e) { console.warn("formatRelativeTime not available or failed")}


                    div.innerHTML = `
                        <img class="w-8 h-8 rounded-full object-cover flex-shrink-0 mt-1" src="${authorAvatar}" alt="${authorName}">
                        <div class="flex-1 bg-gray-50 p-3 rounded-lg border border-gray-100">
                            <div class="flex justify-between items-center mb-1">
                                <span class="text-sm font-semibold text-gray-800">${authorName}</span>
                                <span class="text-xs text-gray-400" title="${timeTitle}">${timeDisplay}</span>
                            </div>
                            <p class="text-sm text-gray-700 whitespace-pre-wrap">${escapeHtml(comment.text)}</p>
                        </div>
                    `;
                    commentList.appendChild(div);
                    commentList.scrollTop = commentList.scrollHeight;

                    const commentCountSpan = document.getElementById('comment-count');
                    if (commentCountSpan) {
                        const currentCountMatch = commentCountSpan.textContent.match(/\d+/);
                        const currentCount = currentCountMatch ? parseInt(currentCountMatch[0], 10) : 0;
                        commentCountSpan.textContent = `(${currentCount + 1})`;
                    }
                } else {
                    console.error("Could not add comment to DOM. Missing commentList, comment, or comment.author.", {commentList, comment});
                }
            }

            commentForm.addEventListener('submit', async function (event) {
                event.preventDefault();
                console.log("Comment form submitted on detail page.");

                const T = taskDetailData.translations;
                const commentText = commentTextArea.value.trim();
                console.log("Comment text to send from detail page:", `"${commentText}"`);

                if (commentTextErrors) commentTextErrors.innerHTML = '';
                if (commentNonFieldErrors) commentNonFieldErrors.innerHTML = '';
                commentTextArea.classList.remove('border-red-500');

                if (!commentText) {
                    console.log("Client-side validation on detail page: Comment text is empty.");
                    if (commentTextErrors) {
                        commentTextErrors.innerHTML = `<p>${T.commentCannotBeEmpty || "Комментарий не может быть пустым."}</p>`;
                    }
                    commentTextArea.classList.add('border-red-500');
                    commentTextArea.focus();
                    return;
                }

                commentTextArea.disabled = true;
                commentSubmitBtn.disabled = true;
                const originalBtnHtml = commentSubmitBtn.innerHTML;
                commentSubmitBtn.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i> ${T.sending || "Отправка..."}`;

                try {
                    const formData = new FormData(commentForm);
                    const actionUrl = commentForm.action || window.location.pathname; // Используем action формы
                    console.log("Sending comment data via fetch to:", actionUrl);
                    
                    const response = await window.authenticatedFetch(actionUrl, {
                        method: 'POST',
                        body: formData,
                        headers: { 'Accept': 'application/json' }
                    });

                    console.log("Response status from detail page:", response.status);
                    let responseData;
                    const contentType = response.headers.get("content-type");

                    if (contentType && contentType.includes("application/json")) {
                        responseData = await response.json();
                        console.log("Response JSON data from detail page:", responseData);
                    } else {
                        const responseText = await response.text();
                        console.log("Non-JSON response text from detail page:", responseText);
                        if (response.ok && (response.redirected || response.status === 200 || response.status === 201 || response.status === 302)) {
                            commentTextArea.value = '';
                            if (window.showNotification) window.showNotification(T.commentAdded || "Комментарий добавлен.", 'success');
                            // Если сервер сделал редирект (например, после успешного POST без AJAX),
                            // то браузер автоматически перейдет. Если же это был "успешный" HTML-ответ,
                            // но мы ожидали JSON, то здесь можно вызвать window.location.href = response.url;
                            // или просто перезагрузить, если URL не изменился, но контент должен.
                            if (response.redirected) {
                                window.location.href = response.url;
                            } else {
                                // Возможно, стоит просто перезагрузить, чтобы увидеть новый комментарий
                                // window.location.reload(); 
                                // или если WebSocket обновит, то ничего не делать
                            }
                            return;
                        }
                        throw new Error(`Server responded with status ${response.status} and non-JSON content on detail page.`);
                    }

                    if (response.ok && responseData.success && responseData.comment) {
                        // Проверяем, что comment.author существует перед добавлением
                        if (responseData.comment.author && !document.getElementById(`comment-${responseData.comment.id}`)) {
                            addCommentToDOM(responseData.comment);
                        } else if (!responseData.comment.author) {
                            console.warn("Received comment data without author, cannot add to DOM:", responseData.comment);
                        }
                        commentTextArea.value = '';
                        if (window.showNotification) window.showNotification(responseData.message || T.commentAdded || "Комментарий добавлен.", 'success');
                    } else {
                        let errMessage = responseData.error || (responseData.errors ? "Validation errors" : (T.submitError || "Ошибка отправки."));
                        if (responseData.errors) {
                            if (responseData.errors.text && commentTextErrors) {
                                commentTextErrors.innerHTML = responseData.errors.text.map(e => `<p>${escapeHtml(e.message || e)}</p>`).join('');
                                commentTextArea.classList.add('border-red-500');
                            }
                            if (responseData.errors.__all__ && commentNonFieldErrors) {
                                commentNonFieldErrors.innerHTML = responseData.errors.__all__.map(e => `<p>${escapeHtml(e.message || e)}</p>`).join('');
                            }
                        }
                        throw new Error(errMessage);
                    }
                } catch (error) {
                    console.error('Comment submit error on detail page:', error);
                    const displayErr = error instanceof Error ? error.message : (T.networkError || "Сетевая ошибка.");
                    if (commentNonFieldErrors && !commentNonFieldErrors.textContent && !commentTextErrors?.textContent) {
                        commentNonFieldErrors.innerHTML = `<p>${escapeHtml(displayErr)}</p>`;
                    }
                    if (window.showNotification && !error.handled) window.showNotification(displayErr, 'error');
                } finally {
                    commentTextArea.disabled = false;
                    commentSubmitBtn.disabled = false;
                    commentSubmitBtn.innerHTML = originalBtnHtml;
                }
            });

            // Если есть WebSocket для комментариев на странице деталей, его нужно подключить
            // connectCommentWebSocket(); // Убедитесь, что эта функция определена
        }
    }
});