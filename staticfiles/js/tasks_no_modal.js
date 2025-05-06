// tasks/tasks_no_modal.js
"use strict";

document.addEventListener('DOMContentLoaded', () => {

    const taskListContainer = document.getElementById('task-list');
    const kanbanBoardContainer = document.getElementById('kanban-board');
    const taskDetailContainer = document.getElementById('task-detail-container');

    const ajaxTaskBaseUrl = kanbanBoardContainer?.dataset.ajaxBaseUrl
        || taskListContainer?.dataset.ajaxBaseUrl
        || '/tasks/ajax/tasks/';

    window.taskStatusMapping = {};
    try {
        const statusMappingElement = document.getElementById('status-mapping-data');
        if (statusMappingElement) {
            window.taskStatusMapping = JSON.parse(statusMappingElement.textContent);
        } else {
           console.error("Status mapping data script tag (#status-mapping-data) not found.");
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

        let taskUpdateSocket = null;
        function connectTaskListWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            const wsPath = window.djangoWsPath || '/ws/tasks/';
            const wsUrl = `${protocol}${window.location.host}${wsPath}`;

            if (!("WebSocket" in window)) {
                console.error("WebSockets are not supported by your browser.");
                if (window.showNotification) showNotification('WebSocket не поддерживается браузером.', 'error');
                return;
            }

            try {
                taskUpdateSocket = new WebSocket(wsUrl);
                taskUpdateSocket.onopen = () => { window.wsRetryCount = 0; };
                taskUpdateSocket.onmessage = handleTaskListWebSocketMessage;
                taskUpdateSocket.onerror = (error) => { console.error('Task List WebSocket error:', error); };
                taskUpdateSocket.onclose = (event) => {
                    if (!event.wasClean && event.code !== 1000 && event.code !== 1001) {
                        if (window.showNotification) showNotification('WebSocket отключен. Попытка переподключения...', 'warning');
                        const retryDelay = Math.min(30000, (Math.pow(2, window.wsRetryCount || 0) * 1000) + Math.random() * 1000);
                        window.wsRetryCount = (window.wsRetryCount || 0) + 1;
                        setTimeout(connectTaskListWebSocket, retryDelay);
                    } else { window.wsRetryCount = 0; }
                };
            } catch (e) {
                 console.error("Failed to create Task List WebSocket:", e);
                 if (window.showNotification) showNotification('Не удалось создать WebSocket соединение.', 'error');
            }
        }

        function handleTaskListWebSocketMessage(event) {
            try {
                const data = JSON.parse(event.data);
                const message = data.message;

                if (!message || !message.event) { return; }

                switch(message.event) {
                    case 'status_update':
                        if (message.task_id && message.status) {
                            updateTaskUI(message.task_id, message.status);
                        }
                        break;
                    case 'task_created':
                    case 'task_updated':
                        if (window.showNotification) showNotification(`Список задач обновлен (ID: ${message.task_id})...`, 'info');
                        setTimeout(() => { window.location.reload(); }, 1200);
                        break;
                    case 'task_deleted':
                        if (message.task_id) {
                            removeTaskFromUI(message.task_id);
                            if (window.showNotification) showNotification(`Задача #${message.task_id} удалена.`, 'info');
                        }
                        break;
                    default:
                        console.warn("Unknown Task List WS event type:", message.event, data);
                }

            } catch (error) {
                console.error('Error processing Task List WS message:', error, "Raw Data:", event.data);
            }
        }

        function initializeViewSwitcher() {
            const urlParams = new URLSearchParams(window.location.search);
            const viewParam = urlParams.get('view');
            const savedView = localStorage.getItem('taskView');
            const initialView = viewParam || savedView || 'kanban';

            const kanbanText = toggleViewBtn?.dataset.kanbanText || "Канбан";
            const listText = toggleViewBtn?.dataset.listText || "Список";
            const kanbanTextMobile = toggleViewBtnMobile?.dataset.kanbanText || "Канбан";
            const listTextMobile = toggleViewBtnMobile?.dataset.listText || "Список";

            const updateButton = (btn, iconEl, textEl, view) => {
                if (!btn || !iconEl || !textEl) return;
                const isKanban = view === 'kanban';
                iconEl.className = `fas ${isKanban ? 'fa-list' : 'fa-columns'} mr-2`;
                textEl.textContent = isKanban ? kanbanText : listText;
                btn.setAttribute('aria-pressed', isKanban.toString());
            };

            const setView = (view) => {
                const isKanban = view === 'kanban';
                kanbanBoardContainer.classList.toggle('hidden', !isKanban);
                taskListContainer.classList.toggle('hidden', isKanban);
                document.getElementById('pagination')?.classList.toggle('hidden', isKanban);
                columnToggleDropdown?.closest('.relative')?.classList.toggle('hidden', !isKanban);
                updateButton(toggleViewBtn, document.getElementById('viewIcon'), document.getElementById('viewText'), view);
                updateButton(toggleViewBtnMobile, document.getElementById('viewIconMobile'), document.getElementById('viewTextMobile'), view);
                localStorage.setItem('taskView', view);
                if (isKanban) { initializeKanban(); restoreHiddenColumns(); }
                else { initializeListSort(); initializeListStatusChange(); initializeListDeleteButtons(); }
                if (window.history.pushState) {
                    const newUrl = new URL(window.location);
                    newUrl.searchParams.set('view', view);
                    window.history.pushState({ path: newUrl.href }, '', newUrl.href);
                }
            };

            setView(initialView);
            [toggleViewBtn, toggleViewBtnMobile].forEach(btn => {
                if (btn) {
                    btn.addEventListener('click', () => {
                        const currentView = localStorage.getItem('taskView') || 'kanban';
                        setView(currentView === 'kanban' ? 'list' : 'kanban');
                    });
                }
            });
        }

        let sortableInstances = [];
        function initializeKanban() {
            if (!window.Sortable || !kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
            sortableInstances.forEach(instance => instance.destroy());
            sortableInstances = [];
            const columns = kanbanBoardContainer.querySelectorAll('.kanban-tasks');
            if (columns.length === 0) return;

            columns.forEach(column => {
                const instance = new Sortable(column, {
                    group: 'kanban-tasks', animation: 150, ghostClass: 'kanban-ghost',
                    dragClass: 'kanban-dragging', forceFallback: true, fallbackOnBody: true, swapThreshold: 0.65,
                    onStart: (evt) => { evt.item.classList.add('shadow-xl', 'scale-105'); },
                    onEnd: async (evt) => {
                        evt.item.classList.remove('shadow-xl', 'scale-105');
                        const taskElement = evt.item;
                        const targetTasksContainer = evt.to;
                        const sourceTasksContainer = evt.from;
                        const targetColumnElement = targetTasksContainer.closest('.kanban-column');
                        const sourceColumnElement = sourceTasksContainer.closest('.kanban-column');
                        const taskId = taskElement.dataset.taskId;
                        const newStatus = targetColumnElement?.dataset.status;
                        const oldStatus = sourceColumnElement?.dataset.status;

                        updateKanbanColumnUI(sourceColumnElement);
                        updateKanbanColumnUI(targetColumnElement);

                        if (!taskId || !newStatus || !targetColumnElement || oldStatus === newStatus) {
                            if (oldStatus !== newStatus && sourceTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') {
                                sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]);
                                updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement);
                            }
                            return;
                        }
                        const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`;
                        try {
                            const response = await window.authenticatedFetch(url, { method: 'POST', body: { status: newStatus } });
                            if (!response.ok) {
                                const errorData = await response.json().catch(() => ({}));
                                throw new Error(errorData.message || `Server error ${response.status}`);
                            }
                            const responseData = await response.json();
                            if (responseData.success) {
                                taskElement.dataset.status = responseData.new_status_key;
                                if (window.showNotification) showNotification(responseData.message || `Статус #${taskId} обновлен.`, 'success');
                                updateTaskUIInList(taskId, responseData.new_status_key);
                            } else { throw new Error(responseData.message || 'Server indicated failure.'); }
                        } catch (error) {
                            console.error(`Failed status update for task ${taskId}:`, error);
                            if (window.showNotification && !error.handled) showNotification(`Ошибка обновления #${taskId}: ${error.message}`, 'error');
                            if (sourceTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') {
                                sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]);
                                updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement);
                            }
                        }
                    }
                });
                sortableInstances.push(instance);
            });
            initializeKanbanDeleteButtons();
        }

        function updateKanbanColumnUI(columnElement) {
            if (!columnElement) return;
            requestAnimationFrame(() => {
                const tasksContainer = columnElement.querySelector('.kanban-tasks');
                if (!tasksContainer) return;
                const countElement = columnElement.querySelector('.task-count');
                const noTasksMessage = tasksContainer.querySelector('.no-tasks-message');
                const taskCount = tasksContainer.querySelectorAll('.kanban-task').length;
                if (countElement) countElement.textContent = taskCount;
                if (noTasksMessage) noTasksMessage.classList.toggle('hidden', taskCount > 0);
            });
        }

        const updateColumnVisibility = (status, isVisible) => {
            kanbanBoardContainer?.querySelectorAll(`.kanban-column-wrapper[data-status="${status}"]`)
                .forEach(wrapper => wrapper.classList.toggle('hidden', !isVisible));
        };

        function initializeColumnToggler() {
            if (!columnToggleDropdown || !resetHiddenColumnsBtn || !columnCheckboxes.length) return;
            const saveHiddenColumns = () => {
                const hidden = Array.from(columnCheckboxes).filter(cb => !cb.checked).map(cb => cb.dataset.status);
                localStorage.setItem('hiddenKanbanColumns', JSON.stringify(hidden));
            };
            columnCheckboxes.forEach(checkbox => {
                checkbox.addEventListener('change', function () { updateColumnVisibility(this.dataset.status, this.checked); saveHiddenColumns(); });
            });
            resetHiddenColumnsBtn.addEventListener('click', () => {
                columnCheckboxes.forEach(cb => { cb.checked = true; updateColumnVisibility(cb.dataset.status, true); });
                saveHiddenColumns();
            });
        }

        function restoreHiddenColumns() {
            if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
            const hiddenStatuses = JSON.parse(localStorage.getItem('hiddenKanbanColumns') || '[]');
            kanbanBoardContainer.querySelectorAll('.kanban-column-wrapper').forEach(wrapper => wrapper.classList.remove('hidden'));
            columnCheckboxes.forEach(cb => cb.checked = true);
            hiddenStatuses.forEach(status => {
                updateColumnVisibility(status, false);
                const checkbox = kanbanBoardContainer.querySelector(`.toggle-column-checkbox[data-status="${status}"]`);
                if (checkbox) checkbox.checked = false;
            });
        }

        function initializeListSort() {
            if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
            const table = taskListContainer.querySelector('table'); if (!table) return;
            const headers = table.querySelectorAll('.sort-header'); if (headers.length === 0) return;
            const urlParams = new URLSearchParams(window.location.search);
            const currentSort = urlParams.get('sort');
            headers.forEach(header => {
                const column = header.dataset.column;
                const icon = header.querySelector('.fa-sort, .fa-sort-up, .fa-sort-down'); if (!icon) return;
                header.classList.remove('sorted-asc', 'sorted-desc');
                icon.className = 'fas fa-sort ml-1 text-gray-400 dark:text-gray-500 opacity-50';
                header.setAttribute('aria-sort', 'none');
                if (currentSort === column) { icon.className = 'fas fa-sort-up ml-1'; header.classList.add('sorted-asc'); header.setAttribute('aria-sort', 'ascending'); }
                else if (currentSort === `-${column}`) { icon.className = 'fas fa-sort-down ml-1'; header.classList.add('sorted-desc'); header.setAttribute('aria-sort', 'descending'); }
            });
            headers.forEach(header => {
                header.addEventListener('click', () => {
                    const column = header.dataset.column; if (!column) return;
                    const currentUrl = new URL(window.location);
                    const currentSortParam = currentUrl.searchParams.get('sort');
                    let newSort = column;
                    if (currentSortParam === column) newSort = `-${column}`;
                    else if (currentSortParam === `-${column}`) newSort = column;
                    currentUrl.searchParams.set('sort', newSort);
                    currentUrl.searchParams.set('view', 'list');
                    currentUrl.searchParams.delete('page');
                    window.location.href = currentUrl.toString();
                });
            });
        }

        function initializeListStatusChange() {
            if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
            const tbody = taskListContainer.querySelector('tbody'); if (!tbody) return;
            tbody.addEventListener('change', async function (event) {
                if (event.target.matches('.status-dropdown')) {
                    const selectElement = event.target;
                    const taskId = selectElement.dataset.taskId;
                    const newStatus = selectElement.value;
                    const previousStatus = selectElement.dataset.previousValue || '';
                    if (!taskId || newStatus === previousStatus) { if (newStatus !== previousStatus) selectElement.value = previousStatus; return; }
                    const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`;
                    selectElement.disabled = true;
                    try {
                        const response = await window.authenticatedFetch(url, { method: 'POST', body: { status: newStatus } });
                        if (!response.ok) { const errorData = await response.json().catch(() => ({})); throw new Error(errorData.message || `Server error ${response.status}`); }
                        const responseData = await response.json();
                        if (responseData.success) {
                            selectElement.dataset.previousValue = newStatus;
                            updateStatusBadge(selectElement.closest('tr'), responseData.new_status_key);
                            if (window.showNotification) showNotification(responseData.message || 'Статус обновлен.', 'success');
                            updateTaskUIInKanban(taskId, responseData.new_status_key);
                        } else { throw new Error(responseData.message || 'Update failed'); }
                    } catch (error) {
                        console.error(`List status update failed for task ${taskId}:`, error);
                        if (window.showNotification && !error.handled) showNotification(`Ошибка обновления #${taskId}: ${error.message}`, 'error');
                        selectElement.value = previousStatus;
                    } finally { selectElement.disabled = false; }
                }
            });
            tbody.querySelectorAll('.status-dropdown').forEach(select => { select.dataset.previousValue = select.value; });
        }

        function setupDeleteTaskHandler(containerSelector) {
            const container = document.querySelector(containerSelector); if (!container) return;
            container.addEventListener('click', async function (event) {
                const deleteButton = event.target.closest('button[data-action="delete-task"]');
                if (!deleteButton) return;
                const taskId = deleteButton.dataset.taskId;
                const taskName = deleteButton.dataset.taskName || `ID ${taskId}`;
                const deleteUrl = deleteButton.dataset.deleteUrl;
                if (!taskId || !deleteUrl) { return; }
                let confirmed = false;
                if (typeof Swal !== 'undefined') {
                    const result = await Swal.fire({ title: `Удалить задачу "${escapeHtml(taskName)}"?`, text: "Это действие нельзя будет отменить!", icon: 'warning', showCancelButton: true, confirmButtonColor: '#d33', cancelButtonColor: '#3085d6', confirmButtonText: 'Да, удалить!', cancelButtonText: 'Отмена' });
                    confirmed = result.isConfirmed;
                } else { confirmed = confirm(`Удалить задачу "${taskName}"?`); }
                if (confirmed) {
                    try {
                        const response = await window.authenticatedFetch(deleteUrl, { method: 'POST' });
                        if (!response.ok) { const errorData = await response.json().catch(() => ({})); throw new Error(errorData.message || `Server error ${response.status}`); }
                        const responseData = await response.json().catch(() => ({}));
                        if (responseData.success !== false) {
                            removeTaskFromUI(taskId);
                            if (window.showNotification) showNotification(responseData.message || `Задача "${escapeHtml(taskName)}" удалена.`, 'success');
                        } else { throw new Error(responseData.message || 'Server indicated delete failure.'); }
                    } catch (error) {
                        console.error(`Failed to delete task ${taskId}:`, error);
                        if (window.showNotification && !error.handled) showNotification(`Ошибка удаления "${escapeHtml(taskName)}": ${error.message}`, 'error');
                    }
                }
            });
        }
        function initializeListDeleteButtons() { setupDeleteTaskHandler('#task-list'); }
        function initializeKanbanDeleteButtons() { setupDeleteTaskHandler('#kanban-board'); }

        function updateTaskUI(taskId, newStatus) { updateTaskUIInKanban(taskId, newStatus); updateTaskUIInList(taskId, newStatus); }
        function updateTaskUIInKanban(taskId, newStatus) {
            if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
            const taskElementKanban = kanbanBoardContainer.querySelector(`.kanban-task[data-task-id="${taskId}"]`); if (!taskElementKanban) return;
            const currentStatus = taskElementKanban.dataset.status;
            if (currentStatus !== newStatus) {
                const targetColumnTasks = kanbanBoardContainer.querySelector(`.kanban-tasks[data-status="${newStatus}"]`);
                const sourceColumnEl = taskElementKanban.closest('.kanban-column'); const targetColumnEl = targetColumnTasks?.closest('.kanban-column');
                if (targetColumnTasks) { targetColumnTasks.appendChild(taskElementKanban); taskElementKanban.dataset.status = newStatus; updateKanbanColumnUI(sourceColumnEl); updateKanbanColumnUI(targetColumnEl); }
            } else { taskElementKanban.dataset.status = newStatus; updateKanbanColumnUI(taskElementKanban.closest('.kanban-column')); }
        }
        function updateTaskUIInList(taskId, newStatus) {
            if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
            const taskElementRow = taskListContainer.querySelector(`#task-row-${taskId}`);
            if (taskElementRow) {
                const dropdown = taskElementRow.querySelector('.status-dropdown');
                if (dropdown && dropdown.value !== newStatus) { dropdown.value = newStatus; dropdown.dataset.previousValue = newStatus; }
                updateStatusBadge(taskElementRow, newStatus);
            }
        }
        function removeTaskFromUI(taskId) {
            const taskElementKanban = kanbanBoardContainer?.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
            const taskElementRow = taskListContainer?.querySelector(`#task-row-${taskId}`);
            let sourceColumn = null;
            if (taskElementKanban) { sourceColumn = taskElementKanban.closest('.kanban-column'); taskElementKanban.remove(); if (sourceColumn) updateKanbanColumnUI(sourceColumn); }
            if (taskElementRow) {
                taskElementRow.remove();
                const tbody = taskListContainer?.querySelector('tbody');
                if (tbody && !tbody.querySelector('tr')) {
                    const colCount = taskListContainer.querySelector('thead th')?.length || 8;
                    tbody.innerHTML = `<tr><td colspan="${colCount}" class="px-6 py-12 text-center text-gray-400 dark:text-gray-500 italic"><i class="fas fa-inbox fa-3x mb-3 text-gray-300 dark:text-gray-600"></i><br>Задачи не найдены.</td></tr>`;
                }
            }
        }
        function updateStatusBadge(tableRow, newStatusKey) {
            if (!tableRow) return; const badge = tableRow.querySelector('.status-badge'); if (!badge) return;
            const statusDisplay = window.taskStatusMapping[newStatusKey] || newStatusKey; badge.textContent = statusDisplay;
            const baseClasses = "status-badge px-2 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full"; let newClasses = baseClasses;
            switch (newStatusKey) {
                case 'new': newClasses += ' bg-gray-100 text-gray-800 dark:bg-dark-600 dark:text-gray-200'; break;
                case 'in_progress': newClasses += ' bg-yellow-100 text-yellow-800 dark:bg-yellow-900/60 dark:text-yellow-200'; break;
                case 'on_hold': newClasses += ' bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-200'; break;
                case 'completed': newClasses += ' bg-green-100 text-green-800 dark:bg-green-900/60 dark:text-green-200'; break;
                case 'canceled': newClasses += ' bg-gray-100 text-gray-500 dark:bg-dark-700 dark:text-gray-400 line-through'; break;
                case 'overdue': newClasses += ' bg-red-100 text-red-800 dark:bg-red-900/60 dark:text-red-200'; break;
                default: newClasses += ' bg-gray-100 text-gray-800 dark:bg-dark-600 dark:text-gray-200'; break;
            } badge.className = newClasses;
        }

        initializeViewSwitcher();
        initializeColumnToggler();
        connectTaskListWebSocket();
        window.addEventListener('resize', debounce(() => { if (localStorage.getItem('taskView') === 'kanban') initializeKanban(); }, 250));

    } // --- END Task List/Kanban Specific Logic ---

    if (taskDetailContainer) {
        let taskDetailData = {};
        try {
            const dataElement = document.getElementById('task-detail-data');
            if (!dataElement) throw new Error("#task-detail-data not found.");
            taskDetailData = JSON.parse(dataElement.textContent);
            if (!taskDetailData.taskId) throw new Error("taskId missing.");
            if (!taskDetailData.translations) throw new Error("translations missing.");
        } catch (e) { console.error("Error reading task detail data:", e); return; }

        const commentList = document.getElementById('comment-list');
        const noCommentsMessage = document.getElementById('no-comments-message');
        const commentForm = document.getElementById('comment-form');
        const commentTextArea = commentForm?.querySelector('textarea[name="text"]');
        const commentSubmitButton = commentForm?.querySelector('button[type="submit"]');
        const commentTextErrors = document.getElementById('comment-text-errors');
        const commentNonFieldErrors = document.getElementById('comment-non-field-errors');
        const commentCountSpan = document.getElementById('comment-count');

        if (commentList && commentForm && commentTextArea && commentSubmitButton) {
            function formatRelativeTime(isoDateString) { const T = taskDetailData.translations; try { const date = new Date(isoDateString); const now = new Date(); if (isNaN(date)) return isoDateString; const seconds = Math.round((now - date) / 1000); const minutes = Math.round(seconds / 60); const hours = Math.round(minutes / 60); const days = Math.round(hours / 24); const currentLocale = document.documentElement.lang || 'ru-RU'; if (seconds < 5) return T.justNow || "только что"; if (seconds < 60) return `${seconds} ${T.secondsAgo || "сек. назад"}`; if (minutes < 60) return `${minutes} ${T.minutesAgo || "мин. назад"}`; if (hours < 24) return `${hours} ${T.hoursAgo || "ч. назад"}`; if (days === 1) return T.yesterday || "вчера"; if (days < 7) return `${days} ${T.daysAgo || "д. назад"}`; return date.toLocaleDateString(currentLocale, { day: '2-digit', month: '2-digit', year: 'numeric' }); } catch (e) { console.error("Error formatting date:", isoDateString, e); return isoDateString; } }
            function addCommentToDOM(comment) { const T = taskDetailData.translations; if (!comment?.author || typeof comment.text !== 'string' || !comment.id || !comment.created_at_iso) { console.error("Invalid comment data:", comment); return; } if (noCommentsMessage) noCommentsMessage.classList.add('hidden'); const commentElement = document.createElement('div'); commentElement.className = 'flex space-x-3 comment-item animate-fade-in'; commentElement.id = `comment-${comment.id}`; const avatarUrl = comment.author.avatar_url || taskDetailData.defaultAvatarUrl || '/static/img/user.svg'; const authorName = escapeHtml(comment.author.name || T.unknownUser || 'Unknown'); const commentTextHtml = escapeHtml(comment.text).replace(/\n/g, '<br>'); const timeAgo = formatRelativeTime(comment.created_at_iso); const fullTime = new Date(comment.created_at_iso).toLocaleString(); commentElement.innerHTML = `<img class="w-8 h-8 rounded-full object-cover flex-shrink-0 mt-1" src="${avatarUrl}" alt="${authorName}"><div class="flex-1 bg-gray-50 dark:bg-dark-700 p-3 rounded-lg border border-gray-100 dark:border-dark-600"><div class="flex justify-between items-center mb-1"><span class="text-sm font-semibold text-gray-800 dark:text-gray-200">${authorName}</span><span class="text-xs text-gray-400 dark:text-gray-500" title="${fullTime}">${timeAgo}</span></div><p class="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">${commentTextHtml}</p></div>`; commentList.appendChild(commentElement); commentList.scrollTop = commentList.scrollHeight; if (commentCountSpan) { try { let count = parseInt(commentCountSpan.textContent.match(/\d+/)?.[0] || '0', 10); commentCountSpan.textContent = `(${(count || 0) + 1})`; } catch (e) { /* ignore */ } } }

            let commentSocket = null;
            function connectCommentWebSocket() { const taskId = taskDetailData.taskId; const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://'; const wsUrl = `${protocol}${window.location.host}/ws/tasks/${taskId}/comments/`; try { commentSocket = new WebSocket(wsUrl); commentSocket.onopen = () => {}; commentSocket.onerror = (error) => console.error('Task Comments WS error:', error); commentSocket.onclose = (event) => {}; commentSocket.onmessage = handleCommentWebSocketMessage; } catch (e) { console.error("Failed to create Comment WebSocket:", e); } }
            function handleCommentWebSocketMessage(event) { const T = taskDetailData.translations; try { const data = JSON.parse(event.data); if (data.type === 'new_comment' && data.comment) { if (!data.comment.author || data.comment.author.name !== taskDetailData.currentUsername) { addCommentToDOM(data.comment); if (window.showNotification) { const author = escapeHtml(data.comment.author.name || T.unknownUser); showNotification(`${T.newCommentNotification} ${author}`, 'info'); } } } else if (data.type === 'error') { if (window.showNotification) showNotification(`${T.websocketError} ${escapeHtml(data.message)}`, 'error'); } } catch (e) { console.error('Error processing comment WS message:', e, 'Data:', event.data); } }

            commentForm.addEventListener('submit', async function (e) {
                e.preventDefault(); const T = taskDetailData.translations; const commentText = commentTextArea.value.trim(); if (!commentText) { if (commentTextErrors) commentTextErrors.textContent = T.commentCannotBeEmpty || 'Коммент пуст'; commentTextArea.classList.add('border-red-500', 'dark:border-red-500'); commentTextArea.focus(); return; } if (commentTextErrors) commentTextErrors.textContent = ''; if (commentNonFieldErrors) commentNonFieldErrors.textContent = ''; commentTextArea.classList.remove('border-red-500', 'dark:border-red-500'); commentTextArea.disabled = true; commentSubmitButton.disabled = true; const originalButtonHtml = commentSubmitButton.innerHTML; commentSubmitButton.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i> ${T.sending || 'Отправка...'}`;
                try {
                    const formData = new FormData(commentForm); const csrfToken = commentForm.querySelector('[name=csrfmiddlewaretoken]')?.value; if (!csrfToken) throw new Error("CSRF token not found!"); const fetchFunc = window.authenticatedFetch || fetch; const response = await fetchFunc(commentForm.action, { method: 'POST', body: formData, headers: { 'X-CSRFToken': csrfToken, 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' } }); let responseData; try { responseData = await response.json(); } catch (e) { throw new Error(`Server error (${response.status}). Invalid JSON.`); }
                    if (response.ok && responseData.success && responseData.comment) { addCommentToDOM(responseData.comment); commentTextArea.value = ''; if (window.showNotification) showNotification(T.commentAdded || 'Комментарий добавлен.', 'success'); }
                    else { let errorMsg = responseData.error || T.submitError || 'Ошибка.'; if (responseData.errors) { const fieldErrors = Object.entries(responseData.errors).map(([field, errors]) => `${field}: ${errors.join(', ')}`).join('; '); errorMsg += ` Details: ${fieldErrors}`; if (responseData.errors.text && commentTextErrors) { commentTextErrors.textContent = responseData.errors.text.join(' '); commentTextArea.classList.add('border-red-500', 'dark:border-red-500'); } if (responseData.errors.__all__ && commentNonFieldErrors) { commentNonFieldErrors.textContent = responseData.errors.__all__.join(' '); } } throw new Error(errorMsg); }
                } catch (error) {
                    console.error('Error submitting comment:', error); const displayError = error instanceof Error ? error.message : (T.networkError || 'Сетевая ошибка.'); if (commentNonFieldErrors && !commentNonFieldErrors.textContent && !commentTextErrors?.textContent) { commentNonFieldErrors.textContent = displayError; } if (window.showNotification && !error.handled) showNotification(displayError, 'error');
                } finally { commentTextArea.disabled = false; commentSubmitButton.disabled = false; commentSubmitButton.innerHTML = originalButtonHtml; }
            });
            connectCommentWebSocket();
        }
    } // --- END TASK DETAIL PAGE SPECIFIC LOGIC ---

}); // End DOMContentLoaded