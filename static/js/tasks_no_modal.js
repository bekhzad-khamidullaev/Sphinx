"use strict";

document.addEventListener('DOMContentLoaded', () => {
    console.log("Initializing tasks.js (No Modal version)...");

    // --- Elements ---
    const taskListContainer = document.getElementById('task-list');
    const kanbanBoardContainer = document.getElementById('kanban-board');
    const toggleViewBtn = document.getElementById('toggleViewBtn');
    const toggleViewBtnMobile = document.getElementById('toggleViewBtnMobile');
    const columnToggleDropdown = document.getElementById('column-toggle-dropdown');
    const resetHiddenColumnsBtn = document.getElementById('resetHiddenColumnsBtn');
    const columnCheckboxes = document.querySelectorAll('.toggle-column-checkbox');
    const dropdownHoverButton = document.getElementById('dropdownHoverButton');

    // --- Get Base URL for AJAX calls ---
    const ajaxTaskBaseUrl = kanbanBoardContainer?.dataset.ajaxBaseUrl
                           || taskListContainer?.dataset.ajaxBaseUrl
                           || '/core/ajax/tasks/';
    if (!kanbanBoardContainer?.dataset.ajaxBaseUrl && !taskListContainer?.dataset.ajaxBaseUrl) {
        console.warn("Could not find data-ajax-base-url on containers. Using fallback:", ajaxTaskBaseUrl);
    } else {
        console.log("Using AJAX base URL:", ajaxTaskBaseUrl);
    }

    if (!taskListContainer || !kanbanBoardContainer) {
        console.error("Task list AND Kanban board containers must be present in the HTML. Exiting initialization.");
        return;
    }

    // --- WebSocket ---
    let taskUpdateSocket = null;
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const wsPath = window.djangoWsPath || '/ws/task_updates/';
        const wsUrl = `${protocol}${window.location.host}${wsPath}`;
        console.log(`Connecting to WebSocket: ${wsUrl}`);
        taskUpdateSocket = new WebSocket(wsUrl);
        taskUpdateSocket.onopen = () => { console.log('Task Update WebSocket connection established.'); window.wsRetryCount = 0; };
        taskUpdateSocket.onmessage = handleWebSocketMessage;
        taskUpdateSocket.onerror = (error) => { console.error('Task Update WebSocket error:', error); if (window.showNotification) showNotification('Ошибка соединения WebSocket', 'error'); };
        taskUpdateSocket.onclose = (event) => {
            console.log('Task Update WebSocket connection closed.', event.code, event.reason);
            if (!event.wasClean) {
                if (window.showNotification) showNotification('WebSocket отключен. Переподключение...', 'warning');
                const retryDelay = Math.min(30000, (Math.pow(1.5, window.wsRetryCount || 0) * 2000) + Math.random() * 1000);
                window.wsRetryCount = (window.wsRetryCount || 0) + 1;
                console.log(`Retrying WS connection in ${Math.round(retryDelay/1000)}s (Attempt ${window.wsRetryCount})`);
                setTimeout(connectWebSocket, retryDelay);
            } else {
                window.wsRetryCount = 0;
            }
        };
    }

    function handleWebSocketMessage(event) {
        try {
            const data = JSON.parse(event.data);
            console.log('WebSocket message received:', data);
            const currentUserId = window.currentUserId || null;
            const initiatorUserId = data.message?.updated_by_id;

            if (initiatorUserId && currentUserId && initiatorUserId === currentUserId) {
                 console.log(`Skipping self-initiated WebSocket update for task ${data.message?.task_id}, type: ${data.type}`);
                 return;
            }

            if (data.type === 'task_update' && data.message?.event === 'status_update') {
                const msg = data.message;
                if (window.showNotification) showNotification(`Статус задачи #${msg.task_id} обновлен на "${msg.status_display}" ${msg.updated_by || ''}`, 'info');
                updateTaskUI(msg.task_id, msg.status);
            } else if (data.type === 'list_update' && (data.message?.event === 'task_created' || data.message?.event === 'task_updated')) {
                 const eventType = data.message?.event === 'task_created' ? 'создана' : 'обновлена';
                 const byUser = data.message?.created_by || data.message?.updated_by || '';
                 if (window.showNotification) showNotification(`Задача #${data.message.task_id} ${eventType} ${byUser}. Обновление списка...`, data.message?.event === 'task_created' ? 'success' : 'info');
                 setTimeout(() => window.location.reload(), 1500); // Перезагрузка
            } else if (data.type === 'list_update' && data.message?.event === 'task_deleted') {
                removeTaskFromUI(data.message.task_id);
                if (window.showNotification) showNotification(`Задача #${data.message.task_id} удалена ${data.message.deleted_by || ''}`, 'info');
            } else if (data.type === 'error') {
                console.error('WebSocket error message from consumer:', data.message);
                if (window.showNotification) showNotification(`Ошибка обновления задачи: ${data.message}`, 'error');
                if (data.task_id && data.original_status) {
                    console.warn(`Attempting to revert UI for task ${data.task_id} to status ${data.original_status} due to server error.`);
                    updateTaskUI(data.task_id, data.original_status);
                }
            } else {
                console.warn("Received unknown WebSocket message structure:", data);
            }
        } catch (error) {
            console.error('Error processing WebSocket message:', error);
        }
    }
    // ---

    // --- View Switching ---
    function initializeViewSwitcher() {
        const urlParams = new URLSearchParams(window.location.search);
        const viewParam = urlParams.get('view');
        const savedView = localStorage.getItem('taskView');
        const initialView = viewParam || savedView || 'kanban';

        const updateButton = (btn, iconEl, textEl, view) => {
            if (!btn || !iconEl || !textEl) return;
            const isKanban = view === 'kanban';
            const kanbanText = btn.dataset.kanbanText || 'Вид: Канбан'; // Fallback
            const listText = btn.dataset.listText || 'Вид: Список'; // Fallback
            textEl.textContent = isKanban ? kanbanText : listText;
            iconEl.className = `fas ${isKanban ? 'fa-list' : 'fa-columns'} mr-2`;
            btn.setAttribute('aria-pressed', isKanban.toString());
        };

        const setView = (view) => {
            const isKanban = view === 'kanban';
            taskListContainer.classList.toggle('hidden', isKanban);
            kanbanBoardContainer.classList.toggle('hidden', !isKanban);
            columnToggleDropdown?.closest('.relative')?.classList.toggle('hidden', !isKanban);
            document.getElementById('pagination')?.classList.toggle('hidden', isKanban);
            localStorage.setItem('taskView', view);

            const viewIcon = document.getElementById('viewIcon');
            const viewText = document.getElementById('viewText');
            const viewIconMobile = document.getElementById('viewIconMobile');
            const viewTextMobile = document.getElementById('viewTextMobile');
            if (toggleViewBtn) updateButton(toggleViewBtn, viewIcon, viewText, view);
            if (toggleViewBtnMobile) updateButton(toggleViewBtnMobile, viewIconMobile, viewTextMobile, view);

            if (isKanban) {
                initializeKanban();
                restoreHiddenColumns();
                kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => updateKanbanColumnUI(col));
                adjustKanbanLayout();
            } else {
                initializeListSort();
                initializeListDeleteButtons();
                initializeListStatusChange();
            }
            console.log(`View switched to: ${view}`);
            if (window.history.pushState) {
                 const newUrl = new URL(window.location);
                 newUrl.searchParams.set('view', view);
                 newUrl.searchParams.delete('page');
                 window.history.pushState({path:newUrl.href}, '', newUrl.href);
            }
        };
        setView(initialView);
        [toggleViewBtn, toggleViewBtnMobile].forEach(btn => {
            if (btn) {
                btn.addEventListener('click', () => {
                    const currentStoredView = localStorage.getItem('taskView') || 'kanban';
                    const newView = currentStoredView === 'list' ? 'kanban' : 'list';
                    setView(newView);
                });
            }
        });
    }
    // ---

    // --- Kanban ---
    let sortableInstances = [];
    function initializeKanban() {
        if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden') || typeof Sortable === 'undefined') return; // Проверка Sortable
        sortableInstances.forEach(instance => instance.destroy());
        sortableInstances = [];
        console.log("Initializing Kanban board...");
        const columns = kanbanBoardContainer.querySelectorAll('.kanban-tasks');
        if (columns.length === 0) { console.log("No Kanban columns found."); return; }

        columns.forEach(column => {
            const instance = new Sortable(column, {
                group: 'kanban-tasks', animation: 150, ghostClass: 'kanban-ghost',
                chosenClass: 'kanban-chosen', dragClass: 'kanban-dragging',
                forceFallback: true, fallbackOnBody: true, swapThreshold: 0.65,
                onStart: (evt) => {
                    kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => col.classList.add('kanban-drag-active-zone'));
                    evt.item.classList.add('shadow-xl', 'scale-105', 'opacity-90');
                },
                onEnd: async (evt) => { /* ... (код onEnd как в предыдущем ответе) ... */
                    console.log("[Kanban onEnd]", evt);
                    kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => col.classList.remove('kanban-drag-active-zone'));
                    evt.item.classList.remove('shadow-xl', 'scale-105', 'opacity-90');
                    const taskElement = evt.item;
                    const targetTasksContainer = evt.to;
                    const sourceTasksContainer = evt.from;
                    const targetColumnElement = targetTasksContainer.closest('.kanban-column');
                    const sourceColumnElement = sourceTasksContainer.closest('.kanban-column');
                    const taskId = taskElement.dataset.taskId;
                    const newStatus = targetColumnElement?.dataset.status;
                    const oldStatus = sourceColumnElement?.dataset.status;
                    const newIndex = evt.newDraggableIndex;
                    updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement);
                    if (!taskId || !newStatus || !targetColumnElement) {
                        console.error("Kanban drop error: Missing data.");
                        if (sourceTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') { console.warn("Reverting drag due to missing data."); sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]); updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement); }
                        if (window.showNotification) showNotification('Ошибка перемещения: неверные данные.', 'error'); return;
                    }
                    if (oldStatus === newStatus && sourceTasksContainer === targetTasksContainer) { console.log(`Task ${taskId} dropped in the same column (${newStatus}).`); return; }
                    console.log(`Task ${taskId} moved from '${oldStatus || '?'}' to '${newStatus}'. Sending update...`);
                    const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`;
                    const loadingIndicator = document.getElementById('loading-indicator');
                    try {
                        if(loadingIndicator) loadingIndicator.classList.remove('hidden');
                        const response = await window.authenticatedFetch(url, { method: 'POST', body: { status: newStatus } });
                        if (response.ok) {
                            const responseData = await response.json();
                            if (responseData.success) { console.log(`Task ${taskId} status updated on server. New: ${responseData.new_status_key}`); taskElement.dataset.status = responseData.new_status_key; if (window.showNotification) showNotification(responseData.message || `Статус задачи #${taskId} обновлен.`, 'success'); }
                            else { console.warn("Server indicated failure:", responseData.message); if (window.showNotification) showNotification(responseData.message || 'Ошибка обновления на сервере.', 'error'); if (sourceTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') { sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]); updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement); } }
                        } else { console.error(`Server error: ${response.status}`); if (sourceTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') { sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]); updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement); } }
                    } catch (error) { console.error(`Fetch/JS error during status update for task ${taskId}:`, error); if (sourceTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') { sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]); updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement); }
                    } finally { if(loadingIndicator) loadingIndicator.classList.add('hidden'); }
                 } // End onEnd
            });
            sortableInstances.push(instance);
        });
        initializeKanbanDeleteButtons();
        console.log(`Kanban initialized for ${columns.length} columns.`);
    } // End initializeKanban

    function updateKanbanColumnUI(columnElement) {
        if (!columnElement) return;
        requestAnimationFrame(() => {
            const tasksContainer = columnElement.querySelector('.kanban-tasks');
            if (!tasksContainer) return;
            const countElement = columnElement.querySelector('.task-count');
            const noTasksMessage = tasksContainer.querySelector('.no-tasks-message');
            const taskElements = tasksContainer.querySelectorAll('.kanban-task');
            const taskCount = taskElements.length;
            if (countElement) { countElement.textContent = taskCount; }
            if (noTasksMessage) { noTasksMessage.classList.toggle('hidden', taskCount > 0); }
            else if (taskCount === 0) { console.warn(`No '.no-tasks-message' element in column ${columnElement.dataset.status}`); }
        });
    }

    const updateColumnVisibility = (status, isVisible) => {
        kanbanBoardContainer?.querySelectorAll(`.kanban-column-wrapper[data-status="${status}"]`)
            .forEach(wrapper => wrapper.classList.toggle('hidden', !isVisible));
    };

    function initializeColumnToggler() {
        if (!columnToggleDropdown || !resetHiddenColumnsBtn || !columnCheckboxes.length) return;
        const saveHiddenColumns = () => {
            const hiddenStatuses = Array.from(columnCheckboxes)
                                       .filter(cb => !cb.checked)
                                       .map(cb => cb.dataset.status);
            localStorage.setItem('hiddenKanbanColumns', JSON.stringify(hiddenStatuses));
            console.log('Saved hidden columns:', hiddenStatuses);
        };
        columnCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', function () {
                updateColumnVisibility(this.dataset.status, this.checked);
                saveHiddenColumns();
                adjustKanbanLayout();
            });
        });
        resetHiddenColumnsBtn.addEventListener('click', () => {
            columnCheckboxes.forEach(checkbox => {
                checkbox.checked = true;
                updateColumnVisibility(checkbox.dataset.status, true);
            });
            localStorage.removeItem('hiddenKanbanColumns');
            adjustKanbanLayout();
            if (window.showNotification) showNotification('Все колонки Kanban показаны.', 'info');
            // Скрываем dropdown меню (если используется Flowbite)
            const dropdownMenuId = dropdownHoverButton?.getAttribute('data-dropdown-toggle');
            if (dropdownMenuId && typeof Flowbite !== 'undefined') {
                 try {
                    const dropdownInstance = Flowbite.getInstance('Dropdown', dropdownMenuId);
                    if (dropdownInstance) dropdownInstance.hide();
                 } catch(e) { console.warn("Could not hide Flowbite dropdown:", e); }
            }
        });
    } // End initializeColumnToggler

    function restoreHiddenColumns() {
        if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        const hiddenStatuses = JSON.parse(localStorage.getItem('hiddenKanbanColumns') || '[]');
        console.log('Restoring hidden columns:', hiddenStatuses);
        // Сначала показываем все
        kanbanBoardContainer.querySelectorAll('.kanban-column-wrapper').forEach(wrapper => wrapper.classList.remove('hidden'));
        columnCheckboxes.forEach(cb => cb.checked = true);
        // Затем скрываем нужные
        hiddenStatuses.forEach(status => {
            const checkbox = document.querySelector(`.toggle-column-checkbox[data-status="${status}"]`);
            if (checkbox) {
                checkbox.checked = false;
                updateColumnVisibility(status, false);
            } else {
                console.warn(`Checkbox for status ${status} not found during restore.`);
            }
        });
        adjustKanbanLayout(); // Корректируем layout после восстановления
    } // End restoreHiddenColumns

    function adjustKanbanLayout() {
         if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        requestAnimationFrame(() => {
            const visibleCols = kanbanBoardContainer.querySelectorAll('.kanban-column-wrapper:not(.hidden)');
            const containerWidth = kanbanBoardContainer.offsetWidth;
            // Используем getComputedStyle для более точной оценки ширины (но может быть медленнее)
            const firstCol = visibleCols[0];
            const colWidthEstimate = firstCol ? parseFloat(getComputedStyle(firstCol).width) : 320; // 320px fallback
            const colGapEstimate = firstCol ? parseFloat(getComputedStyle(firstCol).marginRight) : 16; // 16px fallback (gap-4)

            const totalWidth = visibleCols.length * colWidthEstimate + (visibleCols.length - 1) * colGapEstimate;
            // Центрируем, если все колонки помещаются, иначе прижимаем к левому краю
            kanbanBoardContainer.classList.toggle('justify-center', totalWidth < containerWidth);
            kanbanBoardContainer.classList.toggle('justify-start', totalWidth >= containerWidth);
            // console.log(`Adjust Kanban Layout: Visible=${visibleCols.length}, TotalWidth=${totalWidth.toFixed(0)}, ContainerWidth=${containerWidth}`);
        });
    } // End adjustKanbanLayout
    // ---

    // --- List ---
    function initializeListSort() {
        if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
        const table = taskListContainer.querySelector('table'); if (!table) return;
        const headers = table.querySelectorAll('.sort-header');
        const tbody = table.querySelector('tbody'); if (!tbody || headers.length === 0) return;

        // --- Логика сортировки (пример) ---
        // Восстанавливаем состояние сортировки из localStorage
        const savedCol = localStorage.getItem('taskListSortColumn');
        const savedOrder = localStorage.getItem('taskListSortOrder') || 'asc'; // 'asc' или 'desc'

        const applySort = (columnName, order) => {
            const rows = Array.from(tbody.querySelectorAll('tr'));
            if (rows.length < 2) return; // Нечего сортировать

            // Определяем индекс колонки и тип данных
            let colIndex = -1;
            let dataType = 'string'; // По умолчанию строка
            headers.forEach((th, index) => {
                if (th.dataset.column === columnName) {
                    colIndex = index;
                    // Можно добавить data-type="number|date" к th для разных типов сортировки
                    dataType = th.dataset.type || 'string';
                }
                // Сбрасываем иконки сортировки у других колонок
                th.querySelector('.fa-sort').className = 'fas fa-sort ml-1 text-gray-400 dark:text-gray-500';
                th.setAttribute('aria-sort', 'none');
            });

            if (colIndex === -1) {
                console.warn(`Sort column '${columnName}' not found.`);
                return;
            }

            // Сортируем строки
            rows.sort((rowA, rowB) => {
                const cellA = rowA.cells[colIndex]?.textContent.trim() || '';
                const cellB = rowB.cells[colIndex]?.textContent.trim() || '';
                let comparison = 0;

                if (dataType === 'number') {
                    comparison = (parseFloat(cellA) || 0) - (parseFloat(cellB) || 0);
                } else if (dataType === 'date') {
                     // Нужен парсинг даты (например, из dd.mm.yyyy)
                     // const dateA = parseDate(cellA); const dateB = parseDate(cellB);
                     // comparison = dateA - dateB;
                     comparison = cellA.localeCompare(cellB); // Пока простая строковая
                } else { // string
                    comparison = cellA.localeCompare(cellB, undefined, {numeric: true, sensitivity: 'base'});
                }
                return order === 'asc' ? comparison : -comparison;
            });

            // Обновляем DOM
            rows.forEach(row => tbody.appendChild(row));

            // Обновляем иконку и aria-sort у активной колонки
            const activeHeader = headers[colIndex];
            activeHeader.setAttribute('aria-sort', order === 'asc' ? 'ascending' : 'descending');
            activeHeader.querySelector('.fa-sort').className = `fas ${order === 'asc' ? 'fa-sort-up' : 'fa-sort-down'} ml-1`;

            // Сохраняем состояние
            localStorage.setItem('taskListSortColumn', columnName);
            localStorage.setItem('taskListSortOrder', order);
            console.log(`List sorted by ${columnName} (${order})`);
        };

        // Назначаем обработчики на заголовки
        headers.forEach(header => {
            header.addEventListener('click', function () {
                const currentColumn = this.dataset.column;
                const currentSort = this.getAttribute('aria-sort');
                let newOrder;
                if (currentSort === 'ascending') {
                    newOrder = 'desc';
                } else { // none или descending
                    newOrder = 'asc';
                }
                applySort(currentColumn, newOrder);
            });
            // Устанавливаем начальную иконку для сохраненной колонки
             if (header.dataset.column === savedCol) {
                 header.setAttribute('aria-sort', savedOrder === 'asc' ? 'ascending' : 'descending');
                 header.querySelector('.fa-sort').className = `fas ${savedOrder === 'asc' ? 'fa-sort-up' : 'fa-sort-down'} ml-1`;
             }
        });

        // Применяем начальную сортировку, если она была сохранена
        if (savedCol) {
             console.log(`Applying initial sort: ${savedCol} (${savedOrder})`);
             // Задержка нужна, чтобы браузер успел отрисовать таблицу перед сортировкой
             setTimeout(() => applySort(savedCol, savedOrder), 100);
        }
        console.log("List sort initialized.");

    } // End initializeListSort

    function initializeListStatusChange() {
        if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
        const tbody = taskListContainer.querySelector('tbody'); if (!tbody) return;

        tbody.addEventListener('change', async function (event) {
            if (event.target.matches('.status-dropdown')) {
                const selectElement = event.target;
                const taskId = selectElement.dataset.taskId;
                const newStatus = selectElement.value;
                const previousStatus = selectElement.dataset.previousValue || '';

                if (!taskId || newStatus === previousStatus) {
                     if (newStatus !== previousStatus) selectElement.value = previousStatus;
                    return;
                }

                console.log(`List status change: Task ${taskId} to ${newStatus}`);
                const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`;
                const row = selectElement.closest('tr');
                selectElement.disabled = true;
                const loadingIndicator = document.getElementById('loading-indicator');

                try {
                    if(loadingIndicator) loadingIndicator.classList.remove('hidden');
                    const response = await window.authenticatedFetch(url, { method: 'POST', body: { status: newStatus } });
                    if (response.ok) {
                        const responseData = await response.json();
                        if (responseData.success) {
                            console.log(`List status update success for task ${taskId}`);
                            selectElement.dataset.previousValue = newStatus;
                            if (row) updateStatusBadge(row, responseData.new_status_key);
                            if (window.showNotification) showNotification(responseData.message || 'Статус обновлен.', 'success');
                        } else {
                            console.warn(`List status update failed on server for task ${taskId}:`, responseData.message);
                            selectElement.value = previousStatus;
                            if (window.showNotification) showNotification(responseData.message || 'Ошибка обновления статуса.', 'error');
                        }
                    } else {
                        console.error(`List status update server error for task ${taskId}: ${response.status}`);
                        selectElement.value = previousStatus;
                    }
                } catch (error) {
                    console.error(`List status update fetch/JS error for task ${taskId}:`, error);
                    selectElement.value = previousStatus;
                } finally {
                    selectElement.disabled = false;
                    if(loadingIndicator) loadingIndicator.classList.add('hidden');
                }
            }
        });
        tbody.querySelectorAll('.status-dropdown').forEach(select => { select.dataset.previousValue = select.value; });
        console.log("List status change initialized.");
    } // End initializeListStatusChange
    // ---

    // --- Delete ---
    function setupDeleteTaskHandler(containerSelector) {
        const container = document.querySelector(containerSelector); if (!container) return;
        container.addEventListener('click', async function (event) {
            // Используем closest для поиска кнопки, даже если клик был по иконке внутри
            const deleteButton = event.target.closest('button[data-action="delete-task"]');
            if (!deleteButton) return;

            const taskId = deleteButton.dataset.taskId;
            const taskName = deleteButton.dataset.taskName || `ID ${taskId}`;
            const deleteUrl = deleteButton.dataset.deleteUrl;

            if (!taskId || !deleteUrl) {
                console.error("Delete button missing task ID or delete URL.");
                if (window.showNotification) showNotification('Ошибка: Не удалось определить задачу для удаления.', 'error');
                return;
            }

            // Используем SweetAlert2 для подтверждения
            const result = await Swal.fire({
                title: `Удалить задачу "${escapeHtml(taskName)}"?`, // Экранируем имя
                text: "Это действие нельзя будет отменить!",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#d33', // Красный
                cancelButtonColor: '#3b82f6', // Синий (Tailwind blue-500)
                confirmButtonText: 'Да, удалить!',
                cancelButtonText: 'Отмена',
                customClass: { // Добавляем классы для темной темы, если нужно
                    popup: 'dark:bg-dark-800 dark:text-gray-200',
                    confirmButton: '...',
                    cancelButton: '...',
                }
            });

            if (result.isConfirmed) {
                console.log(`Attempting to delete task ${taskId} via ${deleteUrl}`);
                const loadingIndicator = document.getElementById('loading-indicator');
                try {
                    if(loadingIndicator) loadingIndicator.classList.remove('hidden');
                    // Используем POST для удаления, как требует Django CSRF по умолчанию
                    const response = await window.authenticatedFetch(deleteUrl, { method: 'POST' });

                    if (response.ok) {
                        const responseData = await response.json();
                        if (responseData.success !== false) {
                             console.log(`Task ${taskId} deleted successfully.`);
                             removeTaskFromUI(taskId);
                             if (window.showNotification) showNotification(responseData.message || `Задача "${escapeHtml(taskName)}" удалена.`, 'success');
                        } else {
                            console.warn(`Server indicated delete failure for task ${taskId}:`, responseData.message);
                             if (window.showNotification) showNotification(responseData.message || 'Не удалось удалить задачу на сервере.', 'error');
                        }
                    } else {
                        console.error(`Server error during delete for task ${taskId}: ${response.status}`);
                    }
                } catch (error) {
                    console.error(`Fetch/JS error during delete for task ${taskId}:`, error);
                } finally {
                     if(loadingIndicator) loadingIndicator.classList.add('hidden');
                }
            }
        });
    } // End setupDeleteTaskHandler

    function initializeListDeleteButtons() { setupDeleteTaskHandler('#task-list'); }
    function initializeKanbanDeleteButtons() { setupDeleteTaskHandler('#kanban-board'); }
    // ---

    // --- UI Update Functions ---
    function updateTaskUI(taskId, newStatus) {
        console.log(`Updating UI for task ${taskId} to status ${newStatus}`);
        const taskElementKanban = kanbanBoardContainer.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
        const taskElementRow = taskListContainer.querySelector(`#task-row-${taskId}`);

        // 1. Обновление Канбана
        if (!kanbanBoardContainer.classList.contains('hidden') && taskElementKanban) {
            const currentColumn = taskElementKanban.closest('.kanban-column');
            const targetColumn = kanbanBoardContainer.querySelector(`.kanban-column[data-status="${newStatus}"]`);
            const targetTasksContainer = targetColumn?.querySelector('.kanban-tasks');

            if (targetTasksContainer && currentColumn !== targetColumn) {
                console.log(`Moving task ${taskId} element to column ${newStatus}`);
                targetTasksContainer.appendChild(taskElementKanban); // Перемещаем элемент
                taskElementKanban.dataset.status = newStatus; // Обновляем data-атрибут
                updateKanbanColumnUI(currentColumn); updateKanbanColumnUI(targetColumn);
            } else if (!targetTasksContainer) {
                 console.warn(`Target column container for status ${newStatus} not found.`);
                 // Если колонки нет (скрыта?), оставляем задачу где была или удаляем?
                 // Пока оставляем, но обновляем data-атрибут
                 if(currentColumn) taskElementKanban.dataset.status = newStatus;
            } else { // Уже в правильной колонке
                 taskElementKanban.dataset.status = newStatus;
                 updateKanbanColumnUI(targetColumn);
            }
        }

        // 2. Обновление Списка
        if (!taskListContainer.classList.contains('hidden') && taskElementRow) {
            const statusSelect = taskElementRow.querySelector('.status-dropdown');
            if (statusSelect && statusSelect.value !== newStatus) {
                statusSelect.value = newStatus;
                selectElement.dataset.previousValue = newStatus; // Обновляем пред. значение
                console.log(`Updated list select for task ${taskId} to ${newStatus}`);
            }
            updateStatusBadge(taskElementRow, newStatus); // Обновляем бадж
        }
    } // End updateTaskUI

    function removeTaskFromUI(taskId) {
        console.log(`Removing task ${taskId} from UI`);
        const taskElementKanban = kanbanBoardContainer?.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
        const taskElementRow = taskListContainer?.querySelector(`#task-row-${taskId}`);
        let sourceColumn = null;

        if (taskElementKanban) {
             sourceColumn = taskElementKanban.closest('.kanban-column');
             taskElementKanban.remove();
             if (sourceColumn) updateKanbanColumnUI(sourceColumn);
        }
        if (taskElementRow) {
            taskElementRow.remove();
        }
         // Обновление счетчика пагинации (если возможно)
         const paginationInfo = document.querySelector('#pagination span:first-child'); // Пример селектора
         if (paginationInfo && paginationInfo.textContent.includes('Всего:')) {
             try {
                 let currentTotal = parseInt(paginationInfo.textContent.match(/Всего: (\d+)/)[1], 10);
                 if (!isNaN(currentTotal) && currentTotal > 0) {
                     paginationInfo.textContent = paginationInfo.textContent.replace(/Всего: \d+/, `Всего: ${currentTotal - 1}`);
                 }
             } catch (e) { console.warn("Could not update pagination total count after delete."); }
         }
    } // End removeTaskFromUI

    function updateStatusBadge(tableRow, newStatusKey) {
        if (!tableRow) return;
        const badge = tableRow.querySelector('.status-badge');
        // Используем status_choices из глобального window или data-атрибута таблицы
        const statusChoices = window.taskStatusChoices || [];
        const statusInfo = statusChoices.find(choice => choice[0] === newStatusKey);
        const statusDisplay = statusInfo ? statusInfo[1] : newStatusKey; // Название статуса

        if (badge) {
            badge.textContent = statusDisplay;
            // --- Обновление классов Tailwind для баджа ---
            const statusClasses = {
                'new': 'bg-gray-100 text-gray-800 dark:bg-dark-600 dark:text-gray-200',
                'in_progress': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/80 dark:text-yellow-200',
                'on_hold': 'bg-blue-100 text-blue-800 dark:bg-blue-900/80 dark:text-blue-200',
                'completed': 'bg-green-100 text-green-800 dark:bg-green-900/80 dark:text-green-200',
                'cancelled': 'bg-gray-100 text-gray-500 dark:bg-dark-700 dark:text-gray-400 line-through',
                'overdue': 'bg-red-100 text-red-800 dark:bg-red-900/80 dark:text-red-200'
            };
            const defaultClasses = 'bg-gray-100 text-gray-800 dark:bg-dark-600 dark:text-gray-200';
            // Сброс + установка новых классов
            badge.className = 'status-badge px-2 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full ' + (statusClasses[newStatusKey] || defaultClasses);
            // --- ---
            console.log(`Updated badge for task ${tableRow.id.split('-')[2]} to status ${newStatusKey}`);
        }
         // --- Обновление стиля строки для просроченных ---
         const deadlineCell = tableRow.cells[5]; // Предполагаем, что Срок - 6-я колонка (индекс 5)
         if (deadlineCell) {
             deadlineCell.classList.toggle('error', newStatusKey === 'overdue'); // Добавляем/удаляем класс error админки
             deadlineCell.classList.toggle('text-red-600', newStatusKey === 'overdue'); // Добавляем/удаляем класс Tailwind
             deadlineCell.classList.toggle('dark:text-red-400', newStatusKey === 'overdue');
         }
    } // End updateStatusBadge
    // ---

    // --- Helpers ---
    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return unsafe; // Return non-strings as is
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
            const later = () => { clearTimeout(timeout); func(...args); };
            clearTimeout(timeout); timeout = setTimeout(later, wait);
        };
    };
    // ---

    // --- Init ---
    // Передаем status_choices (массив кортежей) в JS
    window.taskStatusChoices = [];
    try {
        const statusChoicesElement = document.getElementById('status-choices-data'); // Нужен <script id="status-choices-data" type="application/json">...</script> в шаблоне
        if (statusChoicesElement) { window.taskStatusChoices = JSON.parse(statusChoicesElement.textContent || '[]'); }
        else {
            // Fallback: пытаемся получить из первого status-dropdown
            const firstDropdown = document.querySelector('.status-dropdown');
            if(firstDropdown) { window.taskStatusChoices = Array.from(firstDropdown.options).map(opt => [opt.value, opt.text]); }
            else { console.warn("Could not retrieve status choices for JS UI updates."); }
        }
    } catch(e) { console.error("Error parsing status choices data:", e); }

    initializeViewSwitcher();
    initializeColumnToggler();
    // initializeTaskForms(); // УДАЛЕНО
    connectWebSocket();
    window.addEventListener('resize', debounce(adjustKanbanLayout, 250));

    console.log("tasks.js (No Modal version) initialization complete.");

}); // End DOMContentLoaded