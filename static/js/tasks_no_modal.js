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
            error.handled = false;
            throw error;
        }
    };

    // --- Shared Variables & Functions ---
    const taskListContainer = document.getElementById('task-list');
    const kanbanBoardContainer = document.getElementById('kanban-board');
    const taskDetailContainer = document.getElementById('task-detail-container');

    // Get the full URL template for status updates
    const configElement = document.getElementById('task-list-config');
    let taskListConfig = { updateStatusUrlTemplate: "" }; // Default empty
    if (configElement) {
        try {
            taskListConfig = JSON.parse(configElement.textContent);
            if (!taskListConfig.updateStatusUrlTemplate) {
                console.error("CRITICAL: updateStatusUrlTemplate is missing from task-list-config JSON.");
            }
        } catch (e) {
            console.error("CRITICAL: Could not parse task-list-config JSON:", e);
        }
    } else {
        console.error("CRITICAL: task-list-config script tag not found! Status updates will fail.");
    }
    // ajaxTaskBaseUrl might still be needed for other actions like delete, if they don't use a full template
    const ajaxTaskBaseUrlForDelete = kanbanBoardContainer?.dataset.ajaxBaseUrl || taskListContainer?.dataset.ajaxBaseUrl || '';


    window.taskStatusMapping = {};
    try {
        const statusMappingElement = document.getElementById('status-mapping-data');
        if (statusMappingElement) {
            window.taskStatusMapping = JSON.parse(statusMappingElement.textContent);
        } else {
           console.warn("Status mapping data script tag (#status-mapping-data) not found.");
        }
    } catch (e) { console.error("Error parsing status mapping data:", e); }

    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
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

    if (taskListContainer && kanbanBoardContainer) {
        const toggleViewBtn = document.getElementById('toggleViewBtn');
        const toggleViewBtnMobile = document.getElementById('toggleViewBtnMobile');
        const columnToggleDropdown = document.getElementById('column-toggle-dropdown');
        const resetHiddenColumnsBtn = document.getElementById('resetHiddenColumnsBtn');
        const columnCheckboxes = document.querySelectorAll('.toggle-column-checkbox');
        window.wsRetryCount = 0;

        class KanbanBoard {
            constructor(container, options = {}) {
                this.container = container;
                this.updateUrlTemplate = options.updateUrlTemplate || '';
                this.columnCheckboxes = options.columnCheckboxes || [];
                this.resetButton = options.resetButton;
                this.sortableInstances = [];
            }

            init() {
                this.initDragDrop();
                this.setupColumnToggler();
                this.restoreHiddenColumns();
            }

            initDragDrop() {
                if (!window.Sortable || !this.container || this.container.classList.contains('hidden')) return;
                this.sortableInstances.forEach(i => i.destroy());
                this.sortableInstances = [];
                const columns = this.container.querySelectorAll('.kanban-tasks');
                if (!columns.length) return;
                columns.forEach(column => {
                    const instance = new Sortable(column, {
                        group: 'kanban-tasks',
                        animation: 150,
                        ghostClass: 'kanban-ghost',
                        dragClass: 'kanban-dragging',
                        forceFallback: true,
                        fallbackOnBody: true,
                        swapThreshold: 0.65,
                        onStart: evt => evt.item.classList.add('shadow-xl', 'scale-105', 'z-50'),
                        onEnd: async evt => {
                            evt.item.classList.remove('shadow-xl', 'scale-105', 'z-50');
                            const taskElement = evt.item;
                            const targetColumn = evt.to.closest('.kanban-column');
                            const sourceColumn = evt.from.closest('.kanban-column');
                            const taskId = taskElement.dataset.taskId;
                            const newStatus = targetColumn?.dataset.status;
                            const oldStatus = taskElement.dataset.status;
                            this.updateColumnUI(sourceColumn);
                            this.updateColumnUI(targetColumn);
                            if (!taskId || !newStatus || oldStatus === newStatus) {
                                if (oldStatus !== newStatus && evt.from && typeof evt.oldDraggableIndex !== 'undefined') {
                                    evt.from.insertBefore(taskElement, evt.from.children[evt.oldDraggableIndex]);
                                    this.updateColumnUI(sourceColumn);
                                    this.updateColumnUI(targetColumn);
                                }
                                return;
                            }
                            if (!this.updateUrlTemplate) { console.error('Update URL template not configured.'); return; }
                            const url = this.updateUrlTemplate.replace('0', taskId);
                            try {
                                const response = await window.authenticatedFetch(url, { method: 'POST', body: JSON.stringify({ status: newStatus }) });
                                if (!response.ok) {
                                    const errorData = await response.json().catch(() => ({ message: `Server error ${response.status}` }));
                                    throw new Error(errorData.message);
                                }
                                const data = await response.json();
                                if (data.success) {
                                    taskElement.dataset.status = data.new_status_key;
                                    if (window.showNotification) window.showNotification(data.message || `Статус #${escapeHtml(taskId)} обновлен.`, 'success');
                                    updateTaskUIInList(taskId, data.new_status_key, data.new_status_display);
                                } else { throw new Error(data.message || 'Server indicated failure.'); }
                            } catch (error) {
                                console.error(`Kanban AJAX Error for task ${taskId}:`, error);
                                if (window.showNotification && !error.handled) window.showNotification(`Ошибка Kanban #${escapeHtml(taskId)}: ${error.message}`, 'error');
                                if (evt.from && typeof evt.oldDraggableIndex !== 'undefined') {
                                    evt.from.insertBefore(taskElement, evt.from.children[evt.oldDraggableIndex]);
                                    taskElement.dataset.status = oldStatus;
                                    this.updateColumnUI(sourceColumn);
                                    this.updateColumnUI(targetColumn);
                                }
                            }
                        }
                    });
                    this.sortableInstances.push(instance);
                });
                this.initializeDeleteButtons();
            }

            initializeDeleteButtons() {
                setupDeleteTaskHandler('#kanban-board');
            }

            updateColumnUI(column) {
                if (!column) return;
                requestAnimationFrame(() => {
                    const tasksContainer = column.querySelector('.kanban-tasks');
                    if (!tasksContainer) return;
                    const countEl = column.querySelector('.task-count');
                    const noTasksMsg = tasksContainer.querySelector('.no-tasks-message');
                    const count = tasksContainer.querySelectorAll('.kanban-task').length;
                    if (countEl) countEl.textContent = count;
                    if (noTasksMsg) noTasksMsg.classList.toggle('hidden', count > 0);
                });
            }

            updateColumnVisibility(status, isVisible) {
                this.container?.querySelectorAll(`.kanban-column-wrapper[data-status="${status}"]`).forEach(w => w.classList.toggle('hidden', !isVisible));
            }

            setupColumnToggler() {
                if (!columnToggleDropdown || !this.resetButton || !this.columnCheckboxes.length) return;
                const saveHidden = () => localStorage.setItem('hiddenKanbanColumns', JSON.stringify(Array.from(this.columnCheckboxes).filter(cb => !cb.checked).map(cb => cb.dataset.status)));
                this.columnCheckboxes.forEach(cb => cb.addEventListener('change', () => { this.updateColumnVisibility(cb.dataset.status, cb.checked); saveHidden(); }));
                this.resetButton.addEventListener('click', () => {
                    this.columnCheckboxes.forEach(cb => { cb.checked = true; this.updateColumnVisibility(cb.dataset.status, true); });
                    saveHidden();
                });
            }

            restoreHiddenColumns() {
                if (!this.container || this.container.classList.contains('hidden')) return;
                const hidden = JSON.parse(localStorage.getItem('hiddenKanbanColumns') || '[]');
                this.container.querySelectorAll('.kanban-column-wrapper').forEach(w => w.classList.remove('hidden'));
                this.columnCheckboxes.forEach(cb => cb.checked = true);
                hidden.forEach(status => {
                    this.updateColumnVisibility(status, false);
                    const cb = this.container.querySelector(`.toggle-column-checkbox[data-status="${status}"]`);
                    if (cb) cb.checked = false;
                });
            }

            updateTask(taskId, newStatusKey) {
                if (!this.container || this.container.classList.contains('hidden')) return;
                const taskEl = this.container.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
                if (!taskEl) return;
                if (taskEl.dataset.status !== newStatusKey) {
                    const targetColTasks = this.container.querySelector(`.kanban-column[data-status="${newStatusKey}"] .kanban-tasks`);
                    const sourceColEl = taskEl.closest('.kanban-column');
                    if (targetColTasks) {
                        targetColTasks.appendChild(taskEl);
                        taskEl.dataset.status = newStatusKey;
                        this.updateColumnUI(sourceColEl);
                        this.updateColumnUI(targetColTasks.closest('.kanban-column'));
                    }
                } else {
                    taskEl.dataset.status = newStatusKey;
                }
            }
        }

        const kanbanBoard = new KanbanBoard(kanbanBoardContainer, {
            updateUrlTemplate: taskListConfig.updateStatusUrlTemplate,
            columnCheckboxes: columnCheckboxes,
            resetButton: resetHiddenColumnsBtn
        });

        let taskUpdateSocket = null;
        function connectTaskListWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            const wsPath = window.djangoWsPath || '/ws/tasks/';
            const wsUrl = `${protocol}${window.location.host}${wsPath.startsWith('/') ? wsPath : '/' + wsPath}`;
            if (!("WebSocket" in window)) { if (window.showNotification) window.showNotification('WebSocket не поддерживается.', 'error'); return; }
            try {
                taskUpdateSocket = new WebSocket(wsUrl);
                taskUpdateSocket.onopen = () => { window.wsRetryCount = 0; console.log('Task List WS connected.'); };
                taskUpdateSocket.onmessage = handleTaskListWebSocketMessage;
                taskUpdateSocket.onerror = (error) => { console.error('Task List WS error:', error); };
                taskUpdateSocket.onclose = (event) => {
                    if (!event.wasClean && event.code !== 1000 && event.code !== 1001) {
                        if (window.showNotification) window.showNotification('WS отключен. Переподключение...', 'warning');
                        const retryDelay = Math.min(30000, (Math.pow(2, window.wsRetryCount) * 1000) + Math.floor(Math.random() * 1000));
                        window.wsRetryCount++; setTimeout(connectTaskListWebSocket, retryDelay);
                    } else { window.wsRetryCount = 0; }
                };
            } catch (e) { if (window.showNotification) window.showNotification('Ошибка WS соединения.', 'error'); console.error("WS connect fail:", e); }
        }

        function handleTaskListWebSocketMessage(event) {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'list_update' || data.type === 'task_update') {
                    const message = data.message;
                    if (!message || !message.action || !message.id) return;
                    switch(message.action) {
                        case 'create': case 'update':
                            if (window.showNotification) window.showNotification(`Задача #${message.task_number || message.id} ${message.action === 'create' ? 'создана' : 'обновлена'}. Обновление...`, 'info');
                            debounce(() => { window.location.reload(); }, 1500)();
                            break;
                        case 'delete':
                            removeTaskFromUI(message.id);
                            if (window.showNotification) window.showNotification(`Задача #${message.task_number || message.id} удалена.`, 'info');
                            break;
                    }
                } else if (data.type === 'status_update_confirmation' && data.success) {
                    updateTaskUI(data.task_id, data.new_status);
                } else if (data.type === 'error_message' || (data.type && data.type.endsWith('_error'))) {
                    if (window.showNotification) window.showNotification(`Ошибка WS: ${escapeHtml(data.message)}`, 'error');
                }
            } catch (error) { console.error('WS Message Error:', error, "Raw:", event.data); }
        }

        function initializeViewSwitcher() {
            const urlParams = new URLSearchParams(window.location.search);
            const viewParam = urlParams.get('view');
            const savedView = localStorage.getItem('taskView');
            const initialView = viewParam || savedView || 'kanban';
            const kanbanText = toggleViewBtn?.dataset.kanbanText || "Канбан";
            const listText = toggleViewBtn?.dataset.listText || "Список";
            const updateButton = (btn, iconEl, textEl, currentView) => {
                if (!btn || !iconEl || !textEl) return;
                const isCurrentlyKanban = currentView === 'kanban';
                iconEl.className = `fas ${isCurrentlyKanban ? 'fa-list' : 'fa-columns'} mr-2`;
                textEl.textContent = isCurrentlyKanban ? listText : kanbanText;
                btn.setAttribute('aria-pressed', isCurrentlyKanban.toString());
            };
            const setView = (view) => {
                const isKanban = view === 'kanban';
                kanbanBoardContainer.classList.toggle('hidden', !isKanban);
                taskListContainer.classList.toggle('hidden', isKanban);
                document.getElementById('pagination')?.classList.toggle('hidden', isKanban || !document.getElementById('pagination'));
                columnToggleDropdown?.closest('.relative')?.classList.toggle('hidden', !isKanban);
                updateButton(toggleViewBtn, document.getElementById('viewIcon'), document.getElementById('viewText'), view);
                updateButton(toggleViewBtnMobile, document.getElementById('viewIconMobile'), document.getElementById('viewTextMobile'), view);
                localStorage.setItem('taskView', view);
                if (isKanban) { kanbanBoard.init(); }
                else { initializeListSort(); initializeListStatusChange(); initializeListDeleteButtons(); }
                if (window.history.pushState) { const newUrl = new URL(window.location.href); newUrl.searchParams.set('view', view); window.history.pushState({ path: newUrl.href }, '', newUrl.href); }
            };
            setView(initialView);
            [toggleViewBtn, toggleViewBtnMobile].forEach(btn => {
                if (btn) btn.addEventListener('click', () => setView((localStorage.getItem('taskView') || 'kanban') === 'kanban' ? 'list' : 'kanban'));
            });
        }

        // Deprecated functions retained for backward compatibility

        function initializeListSort() {
            if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
            const table = taskListContainer.querySelector('table'); if (!table) return;
            const headers = table.querySelectorAll('th.sort-header'); if (headers.length === 0) return;
            const urlParams = new URLSearchParams(window.location.search); const currentSort = urlParams.get('sort');
            headers.forEach(header => {
                const link = header.querySelector('a'); if (!link) return;
                const hrefSort = new URL(link.href).searchParams.get('sort'); const icon = header.querySelector('.fa-sort, .fa-sort-up, .fa-sort-down'); if (!icon) return;
                header.classList.remove('sorted-asc', 'sorted-desc'); icon.className = 'fas fa-sort fa-fw ml-1.5 text-gray-400 opacity-40 group-hover:opacity-80'; header.setAttribute('aria-sort', 'none');
                if (currentSort === hrefSort) {
                    if (hrefSort.startsWith('-')) { icon.className = 'fas fa-sort-down fa-fw ml-1.5 text-gray-600'; header.classList.add('sorted-desc'); header.setAttribute('aria-sort', 'descending'); }
                    else { icon.className = 'fas fa-sort-up fa-fw ml-1.5 text-gray-600'; header.classList.add('sorted-asc'); header.setAttribute('aria-sort', 'ascending'); }
                }
            });
        }

        function initializeListStatusChange() {
            if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
            const tbody = taskListContainer.querySelector('tbody'); if (!tbody) return;
            tbody.addEventListener('change', async function (event) {
                if (event.target.matches('.status-dropdown')) {
                    const selectElement = event.target, taskId = selectElement.dataset.taskId, newStatus = selectElement.value;
                    const previousStatus = selectElement.dataset.previousValue || selectElement.options[0].value; // Fallback to first option if no previous
                    if (!taskId || newStatus === previousStatus) { if (newStatus !== previousStatus) selectElement.value = previousStatus; return; }
                    if (!taskListConfig.updateStatusUrlTemplate) { console.error("Update URL template not configured for List status update."); return; }
                    const url = taskListConfig.updateStatusUrlTemplate.replace('0', taskId); // USE TEMPLATE
                    console.log("List attempting to update URL:", url, " NewStatus:", newStatus);

                    selectElement.disabled = true;
                    try {
                        const response = await window.authenticatedFetch(url, { method: 'POST', body: JSON.stringify({ status: newStatus }) });
                        if (!response.ok) { const errorData = await response.json().catch(() => ({ message: `Server error ${response.status}` })); throw new Error(errorData.message); }
                        const responseData = await response.json();
                        if (responseData.success) {
                            selectElement.dataset.previousValue = newStatus;
                            updateStatusDropdownAppearance(selectElement, responseData.new_status_key);
                            if (window.showNotification) window.showNotification(responseData.message || 'Статус обновлен.', 'success');
                            kanbanBoard.updateTask(taskId, responseData.new_status_key);
                        } else { throw new Error(responseData.message || 'Update failed.'); }
                    } catch (error) {
                        console.error(`List AJAX Error for task ${taskId}:`, error);
                        if (window.showNotification && !error.handled) window.showNotification(`Ошибка List #${escapeHtml(taskId)}: ${error.message}`, 'error');
                        selectElement.value = previousStatus; updateStatusDropdownAppearance(selectElement, previousStatus);
                    } finally { selectElement.disabled = false; }
                }
            });
            tbody.querySelectorAll('.status-dropdown').forEach(select => { select.dataset.previousValue = select.value; });
        }

        function setupDeleteTaskHandler(containerSelector) {
            const container = document.querySelector(containerSelector); if (!container) return;
            container.addEventListener('click', async function (event) {
                const deleteButton = event.target.closest('button[data-action="delete-task"]'); if (!deleteButton) return;
                const taskId = deleteButton.dataset.taskId, taskName = deleteButton.dataset.taskName || `ID ${taskId}`;
                let deleteUrl = deleteButton.dataset.deleteUrl; // This should be the {% url 'tasks:ajax_delete_task' task_id=task.pk %}
                if (!taskId || !deleteUrl) return;
                // If deleteUrl is a template like the status one, it should be handled by replacing placeholder
                // If it's already the final URL from template, it's fine.
                // Assuming data-delete-url provides the final, correct URL from the Django template.

                let confirmed = (typeof Swal === 'undefined') ? confirm(`Удалить задачу "${escapeHtml(taskName)}"?`) : (await Swal.fire({ title: `Удалить "${escapeHtml(taskName)}"?`, text: "Это действие необратимо!", icon: 'warning', showCancelButton: true, confirmButtonColor: '#d33', cancelButtonColor: '#6e7881', confirmButtonText: 'Да, удалить!', cancelButtonText: 'Отмена' })).isConfirmed;
                if (confirmed) {
                    try {
                        const response = await window.authenticatedFetch(deleteUrl, { method: 'POST' }); // Or 'DELETE' if API supports
                        if (!response.ok) { const errorData = await response.json().catch(() => ({ message: `Server error ${response.status}` })); throw new Error(errorData.message); }
                        let responseData = { success: true, message: `Задача "${escapeHtml(taskName)}" удалена.` };
                        if (response.status !== 204) responseData = await response.json().catch(() => responseData);
                        if (responseData.success !== false) { removeTaskFromUI(taskId); if (window.showNotification) window.showNotification(responseData.message, 'success'); }
                        else { throw new Error(responseData.message || 'Server error on delete.'); }
                    } catch (error) { console.error(`Delete AJAX Error for task ${taskId}:`, error); if (window.showNotification && !error.handled) window.showNotification(`Ошибка удаления "${escapeHtml(taskName)}": ${error.message}`, 'error'); }
                }
            });
        }
        function initializeListDeleteButtons() { setupDeleteTaskHandler('#task-list'); }

        function updateTaskUI(taskId, newStatusKey, newStatusDisplay) { kanbanBoard.updateTask(taskId, newStatusKey); updateTaskUIInList(taskId, newStatusKey, newStatusDisplay); }
        function updateTaskUIInList(taskId, newStatusKey, newStatusDisplayProvided) {
            if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
            const rowEl = taskListContainer.querySelector(`#task-row-${taskId}`); if (!rowEl) return;
            const dropdown = rowEl.querySelector('.status-dropdown');
            if (dropdown) { if (dropdown.value !== newStatusKey) dropdown.value = newStatusKey; dropdown.dataset.previousValue = newStatusKey; updateStatusDropdownAppearance(dropdown, newStatusKey); }
        }
        function updateStatusDropdownAppearance(selectElement, newStatusKey) {
            if (!selectElement) return;
            const baseClasses = "status-dropdown appearance-none px-2 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full focus:outline-none focus:ring-1 focus:ring-blue-400 transition-all border border-transparent hover:border-gray-300 focus:border-blue-400 cursor-pointer";
            let statusClasses = ""; const s = newStatusKey; /* short alias */
            if (s === 'new') statusClasses = ' bg-gray-100 text-gray-800';
            else if (s === 'in_progress') statusClasses = ' bg-yellow-100 text-yellow-800';
            else if (s === 'on_hold') statusClasses = ' bg-blue-100 text-blue-800';
            else if (s === 'completed') statusClasses = ' bg-green-100 text-green-800';
            else if (s === 'cancelled' || s === 'canceled') statusClasses = ' bg-gray-100 text-gray-500 line-through';
            else if (s === 'overdue') statusClasses = ' bg-red-100 text-red-800';
            else statusClasses = ' bg-gray-100 text-gray-800';
            selectElement.className = baseClasses + statusClasses;
        }
        function removeTaskFromUI(taskId) {
            const taskKanban = kanbanBoardContainer?.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
            if (taskKanban) { const col = taskKanban.closest('.kanban-column'); taskKanban.remove(); if (col) kanbanBoard.updateColumnUI(col); }
            const taskRow = taskListContainer?.querySelector(`#task-row-${taskId}`);
            if (taskRow) {
                taskRow.remove(); const tbody = taskListContainer?.querySelector('tbody');
                if (tbody && !tbody.querySelector('tr')) { const colCount = taskListContainer.querySelector('thead th')?.length || 8; tbody.innerHTML = `<tr><td colspan="${colCount}" class="px-6 py-12 text-center text-gray-400 italic"><i class="fas fa-inbox fa-3x mb-3"></i><br>Задачи не найдены.</td></tr>`; }
            }
        }
        initializeViewSwitcher(); connectTaskListWebSocket();
        window.addEventListener('resize', debounce(() => { if (localStorage.getItem('taskView') === 'kanban' && kanbanBoardContainer && !kanbanBoardContainer.classList.contains('hidden')) kanbanBoard.init(); }, 250));
    }

    // --- Task Detail Page Specific Logic ---
    if (taskDetailContainer) {
        let taskDetailData = {};
        try {
            const dataEl = document.getElementById('task-detail-data'); if (!dataEl) throw new Error("No #task-detail-data");
            taskDetailData = JSON.parse(dataEl.textContent); if (!taskDetailData.taskId) throw new Error("taskId missing");
            taskDetailData.translations = taskDetailData.translations || { justNow: "только что", secondsAgo: "сек. назад", minutesAgo: "мин. назад", hoursAgo: "ч. назад", yesterday: "вчера", daysAgo: "д. назад", unknownUser: "Неизвестный", newCommentNotification: "Новый комментарий от", websocketError: "Ошибка WebSocket:", commentCannotBeEmpty: "Комментарий не может быть пустым.", sending: "Отправка...", commentAdded: "Комментарий добавлен.", submitError: "Ошибка отправки.", networkError: "Сетевая ошибка." };
            taskDetailData.defaultAvatarUrl = taskDetailData.defaultAvatarUrl || '/static/img/user.svg';
            taskDetailData.currentUsername = taskDetailData.currentUsername || null;
        } catch (e) { console.error("Task Detail data error:", e); return; }

        const commentList = document.getElementById('comment-list'), noCommentsMsg = document.getElementById('no-comments-message');
        const commentForm = document.getElementById('comment-form'), commentTextArea = commentForm?.querySelector('textarea[name="text"]');
        const commentSubmitBtn = commentForm?.querySelector('button[type="submit"]'), commentTextErrors = document.getElementById('comment-text-errors');
        const commentNonFieldErrors = document.getElementById('comment-non-field-errors'), commentCountSpan = document.getElementById('comment-count');

        if (commentList && commentForm && commentTextArea && commentSubmitBtn) {
            function formatRelativeTime(isoDateStr) { /* ... (same as before) ... */ return isoDateStr; } // Placeholder
            function addCommentToDOM(comment) { /* ... (same as before, ensure T is taskDetailData.translations) ... */ } // Placeholder

            let commentSocket = null;
            function connectCommentWebSocket() { /* ... (same as before) ... */ }
            function handleCommentWebSocketMessage(event) { /* ... (same as before, ensure T and check for existingComment.id) ... */ }

            commentForm.addEventListener('submit', async function (e) {
                e.preventDefault(); const T = taskDetailData.translations; const commentText = commentTextArea.value.trim();
                if (commentTextErrors) commentTextErrors.textContent = ''; if (commentNonFieldErrors) commentNonFieldErrors.textContent = '';
                commentTextArea.classList.remove('border-red-500', '');
                if (!commentText) { if (commentTextErrors) commentTextErrors.textContent = T.commentCannotBeEmpty; commentTextArea.classList.add('border-red-500', ''); commentTextArea.focus(); return; }
                commentTextArea.disabled = true; commentSubmitBtn.disabled = true; const originalBtnHtml = commentSubmitBtn.innerHTML; commentSubmitBtn.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i> ${T.sending}`;
                try {
                    const formData = new FormData(commentForm);
                    const response = await window.authenticatedFetch(commentForm.action, { method: 'POST', body: formData, headers: {'Accept': 'application/json'} });
                    let responseData; const contentType = response.headers.get("content-type");
                    if (contentType && contentType.includes("application/json")) responseData = await response.json();
                    else { if (response.ok && response.redirected) { addCommentToDOM({id: `temp-${Date.now()}`, text: commentText, created_at_iso: new Date().toISOString(), author: {name: taskDetailData.currentUsername || T.unknownUser, avatar_url: taskDetailData.currentUserAvatar || taskDetailData.defaultAvatarUrl}}); commentTextArea.value = ''; if (window.showNotification) window.showNotification(T.commentAdded, 'success'); return; } throw new Error(`Server responded with ${response.status}. Expected JSON.`); }
                    if (response.ok && responseData.success && responseData.comment) { if (!document.getElementById(`comment-${responseData.comment.id}`)) addCommentToDOM(responseData.comment); commentTextArea.value = ''; if (window.showNotification) window.showNotification(T.commentAdded, 'success'); }
                    else { let err = responseData.error || T.submitError; if (responseData.errors) { err += ` Details: ${Object.entries(responseData.errors).map(([f, e]) => `${f}: ${e.join(', ')}`).join('; ')}`; if (responseData.errors.text && commentTextErrors) { commentTextErrors.textContent = responseData.errors.text.join(' '); commentTextArea.classList.add('border-red-500',''); } if (responseData.errors.__all__ && commentNonFieldErrors) commentNonFieldErrors.textContent = responseData.errors.__all__.join(' '); } throw new Error(err); }
                } catch (error) { console.error('Comment submit error:', error); const displayErr = error instanceof Error ? error.message : T.networkError; if (commentNonFieldErrors && !commentNonFieldErrors.textContent && !commentTextErrors?.textContent) commentNonFieldErrors.textContent = displayErr; if (window.showNotification && !error.handled) window.showNotification(displayErr, 'error');
                } finally { commentTextArea.disabled = false; commentSubmitBtn.disabled = false; commentSubmitBtn.innerHTML = originalBtnHtml; }
            });
            connectCommentWebSocket();
        }
    }
});