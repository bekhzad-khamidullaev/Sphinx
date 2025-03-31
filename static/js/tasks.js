// static/js/tasks.js
"use strict";

document.addEventListener('DOMContentLoaded', () => {
    console.log("Initializing tasks.js...");

    // --- Elements ---
    const taskListContainer = document.getElementById('task-list');
    const kanbanBoardContainer = document.getElementById('kanban-board');
    const toggleViewBtn = document.getElementById('toggleViewBtn');
    const toggleViewBtnMobile = document.getElementById('toggleViewBtnMobile');
    const columnToggleDropdown = document.getElementById('column-toggle-dropdown');
    const resetHiddenColumnsBtn = document.getElementById('resetHiddenColumnsBtn');
    const columnCheckboxes = document.querySelectorAll('.toggle-column-checkbox');
    const modalContentElement = document.getElementById('modal-content');
    const createTaskBtnDesktop = document.querySelector('#list_actions button[data-action="create-task"]');
    const createTaskBtnMobile = document.querySelector('#list_actions_mobile button[data-action="create-task"]');
    const dropdownHoverButton = document.getElementById('dropdownHoverButton');

    // --- Get Base URL for AJAX calls ---
    const ajaxTaskBaseUrl = kanbanBoardContainer?.dataset.ajaxBaseUrl
                           || taskListContainer?.dataset.ajaxBaseUrl
                           || '/core/ajax/tasks/'; // Fallback
    if (!ajaxTaskBaseUrl || !ajaxTaskBaseUrl.endsWith('/core/ajax/tasks/')) {
        console.warn("Could not reliably determine AJAX base URL with language prefix from data-ajax-base-url. Using fallback:", ajaxTaskBaseUrl);
    } else {
        console.log("Using AJAX base URL:", ajaxTaskBaseUrl);
    }

    if (!taskListContainer && !kanbanBoardContainer) {
        console.log("Task list or Kanban board container not found. Exiting tasks.js initialization.");
        return;
    }

    // --- WebSocket ---
    let taskUpdateSocket = null;
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const wsUrl = `${protocol}${window.location.host}/ws/task_updates/`;
        console.log(`Connecting to WebSocket: ${wsUrl}`);
        taskUpdateSocket = new WebSocket(wsUrl);
        taskUpdateSocket.onopen = () => console.log('Task Update WebSocket connection established.');
        taskUpdateSocket.onmessage = handleWebSocketMessage;
        taskUpdateSocket.onerror = (error) => { console.error('Task Update WebSocket error:', error); if (window.showNotification) showNotification('Ошибка соединения WebSocket', 'error'); };
        taskUpdateSocket.onclose = (event) => { console.log('Task Update WebSocket connection closed.', event.code, event.reason); if (!event.wasClean && window.showNotification) showNotification('WebSocket отключен. Переподключение...', 'warning'); setTimeout(connectWebSocket, 5000 + Math.random() * 2000); };
    }

    function handleWebSocketMessage(event) {
        try {
            const data = JSON.parse(event.data);
            console.log('WebSocket message received:', data);
            const currentUserId = window.currentUserId || null;

            if (data.user_id && currentUserId && data.user_id === currentUserId && (data.type === 'status_update' || data.type === 'task_updated')) {
                 console.log(`Skipping self-initiated WebSocket update for task ${data.task_id}, type: ${data.type}`);
                 return;
            }

            if (data.type === 'status_update' && data.task_id && data.new_status) {
                if (window.showNotification) showNotification(`Статус задачи #${data.task_id} обновлен ${data.user_info || ''} на "${data.new_status_display || data.new_status}"`, 'info');
                updateTaskUI(data.task_id, data.new_status);
            } else if (data.type === 'task_created' && data.task_html) {
                addNewTaskToUI(data.task_html, data.status);
                if (window.showNotification) showNotification(`Добавлена новая задача ${data.user_info || ''}`, 'success');
            } else if (data.type === 'task_deleted' && data.task_id) {
                removeTaskFromUI(data.task_id);
                if (window.showNotification) showNotification(`Задача #${data.task_id} удалена ${data.user_info || ''}`, 'info');
            } else if (data.type === 'task_updated' && data.task_id && data.task_html) {
                updateExistingTaskUI(data.task_id, data.task_html, data.status);
                if (window.showNotification) showNotification(`Задача #${data.task_id} обновлена ${data.user_info || ''}`, 'info');
            } else if (data.type === 'error') {
                console.error('WebSocket error message:', data.message);
                if (window.showNotification) showNotification(`Ошибка WebSocket: ${data.message}`, 'error');
            } else {
                console.warn("Received unknown WebSocket message type:", data.type, data);
            }
        } catch (error) {
            console.error('Error processing WebSocket message:', error);
        }
    }

    // --- View Switching ---
    function initializeViewSwitcher() {
        const currentView = localStorage.getItem('taskView') || 'list';
        const updateButton = (btn, iconEl, textEl, view) => {
            if (!btn || !iconEl || !textEl) return;
            const isKanban = view === 'kanban';
            iconEl.className = `fas ${isKanban ? 'fa-list' : 'fa-columns'} mr-2`;
            textEl.textContent = isKanban ? ' Вид: Список' : ' Вид: Канбан';
            btn.setAttribute('aria-pressed', isKanban ? 'true' : 'false');
        };
        const setView = (view) => {
            if (!taskListContainer && !kanbanBoardContainer) return;
            const isKanban = view === 'kanban';
            if (taskListContainer) taskListContainer.classList.toggle('hidden', isKanban);
            if (kanbanBoardContainer) kanbanBoardContainer.classList.toggle('hidden', !isKanban);
            if (columnToggleDropdown) columnToggleDropdown.closest('.relative')?.classList.toggle('hidden', !isKanban);
            const pagination = document.getElementById('pagination');
            if (pagination) pagination.classList.toggle('hidden', isKanban);
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
                updateTaskCounts();
                adjustKanbanLayout();
            } else {
                initializeListSort();
                initializeListDeleteButtons();
                initializeListStatusChange();
            }
            console.log(`View switched to: ${view}`);
        };
        setView(currentView);
        [toggleViewBtn, toggleViewBtnMobile].forEach(btn => {
            if (btn) {
                btn.addEventListener('click', () => {
                    const currentStoredView = localStorage.getItem('taskView') || 'list';
                    const newView = currentStoredView === 'list' ? 'kanban' : 'list';
                    setView(newView);
                });
            }
        });
    }

    // --- Kanban ---
    let sortableInstances = [];
    function initializeKanban() {
         if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        sortableInstances.forEach(instance => instance.destroy());
        sortableInstances = [];
        console.log("Initializing Kanban board...");
        const columns = kanbanBoardContainer.querySelectorAll('.kanban-tasks');
        if (columns.length === 0) {
            console.log("No Kanban columns found to initialize.");
            return;
        }

        columns.forEach(column => {
            const instance = new Sortable(column, {
                group: 'kanban-tasks',
                animation: 150,
                ghostClass: 'kanban-ghost',
                chosenClass: 'kanban-chosen',
                dragClass: 'kanban-dragging',
                forceFallback: true,
                fallbackOnBody: true,
                swapThreshold: 0.65,

                onStart: (evt) => {
                    kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => col.classList.add('kanban-drag-active-zone'));
                    evt.item.classList.add('shadow-lg', 'scale-105');
                },
                onEnd: async (evt) => {
                    // ---!!! ЛОГ ДЛЯ ПРОВЕРКИ ВЫЗОВА ОБРАБОТЧИКА !!!---
                    console.log("--- Kanban onEnd Handler START ---", evt);
                    // ---!!! КОНЕЦ ЛОГА !!!---

                    // Убираем визуальные эффекты перетаскивания
                    kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => col.classList.remove('kanban-drag-active-zone'));
                    evt.item.classList.remove('shadow-lg', 'scale-105'); // evt.item - перетаскиваемый элемент

                    // Получаем необходимые данные из события и DOM
                    const taskElement = evt.item;
                    const targetColumnElement = evt.to.closest('.kanban-column'); // Колонка, КУДА перетащили
                    const taskId = taskElement.dataset.taskId; // ID задачи из data-атрибута
                    const newStatus = targetColumnElement?.dataset.status; // Новый статус из data-атрибута колонки назначения
                    const oldColumnElement = evt.from.closest('.kanban-column'); // Колонка, ОТКУДА перетащили
                    const oldStatus = oldColumnElement?.dataset.status; // Старый статус
                    const newIndex = evt.newDraggableIndex; // Новый порядковый номер в колонке назначения (0-based)

                    // --- Валидация данных ---
                    if (!taskId || !newStatus || !targetColumnElement) {
                        console.error("Kanban drop error: Missing taskId, newStatus, or target column data attribute.");
                        // Попытка визуально вернуть элемент обратно, если возможно
                        if (evt.from && typeof evt.oldDraggableIndex !== 'undefined') {
                             console.warn("Attempting to revert drag due to missing data.");
                             evt.from.insertBefore(taskElement, evt.from.children[evt.oldDraggableIndex]);
                        }
                        if (window.showNotification) showNotification('Ошибка перемещения: неверные данные задачи или колонки.', 'error');
                        updateTaskCounts(); // Обновить счетчики после возможного отката
                        return; // Прерываем выполнение обработчика
                    }

                    // --- Проверка, изменилась ли колонка ---
                    // Если перетащили внутри той же колонки, статус не меняется.
                    // Можно добавить логику для обновления только порядка, если это необходимо.
                    if (oldStatus === newStatus && evt.from === evt.to) {
                        console.log(`Task ${taskId} dropped in the same column (${newStatus}). Order might have changed to index ${newIndex}, but status update not needed.`);
                        // Опционально: Если нужно сохранять порядок даже внутри колонки:
                        // const orderUrl = `${ajaxTaskBaseUrl}${taskId}/update-order/`; // Пример URL
                        // try {
                        //    await window.authenticatedFetch(orderUrl, { method: 'POST', body: { order: newIndex } });
                        //    console.log(`Task ${taskId} order updated to ${newIndex}`);
                        // } catch (orderError) {
                        //    console.error(`Error updating task ${taskId} order:`, orderError);
                        //    // Возможно, нужно откатить визуальное изменение порядка
                        // }
                        return; // Прерываем выполнение, т.к. статус не менялся
                    }

                    // --- Подготовка к AJAX запросу ---
                    console.log(`Task ${taskId} moved from status '${oldStatus || 'unknown'}' to '${newStatus}'. New index: ${newIndex}. Sending update...`);
                    updateTaskCounts(); // Обновляем счетчики на UI оптимистично

                    const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`; // Формируем URL с ID задачи

                    // --- Выполнение AJAX запроса ---
                    try {
                        console.log("Attempting authenticatedFetch..."); // LOG 1
                        // Вызываем authenticatedFetch БЕЗ указания specific indicator,
                        // чтобы использовался глобальный #loading-indicator
                        const response = await window.authenticatedFetch(url, {
                            method: 'POST',
                            body: {
                                status: newStatus,  // Отправляем новый статус
                                order: newIndex     // Отправляем новый порядок
                            },
                        });
                        console.log("authenticatedFetch completed. Response ok:", response.ok); // LOG 2

                        if (response.ok) {
                            // --- Успешный ответ от сервера (статус 2xx) ---
                            console.log("Processing successful response..."); // LOG 3
                            let responseData = null;
                            try {
                                responseData = await response.json(); // Пытаемся разобрать JSON
                                console.log("Response data parsed:", responseData); // LOG 4b
                            } catch (jsonError) {
                                // Сервер вернул 200 OK, но тело не является валидным JSON
                                console.error("Error parsing JSON response even though status was OK:", jsonError, response); // LOG 4a (modified)
                                // Можно показать предупреждение или обработать как частичный успех
                                if (window.showNotification) showNotification(`Статус задачи #${taskId} обновлен, но ответ сервера некорректен.`, 'warning');
                                // Продолжаем выполнение, т.к. статус на сервере, вероятно, обновился
                            }

                            // Проверяем данные ответа (если JSON был разобран)
                            if (responseData && responseData.success) {
                                // Сервер подтвердил успешное обновление
                                console.log(`Status/order for task ${taskId} updated successfully on server. Response:`, responseData); // LOG 5
                                // Обновляем data-атрибут на карточке для консистентности
                                if (responseData.new_status_key && taskElement.dataset.status !== responseData.new_status_key) {
                                    taskElement.dataset.status = responseData.new_status_key;
                                    console.log(`Updated task element data-status to ${responseData.new_status_key}`); // LOG 6
                                }
                                // Показываем уведомление об успехе
                                if (window.showNotification) showNotification(responseData.message || `Статус задачи #${taskId} обновлен.`, 'success'); // LOG 7
                                console.log("Success path finished."); // LOG 8
                            } else {
                                // Сервер вернул 200 OK, но в JSON указано { success: false } или JSON не был разобран
                                console.warn("Response OK, but operation indicated failure or data missing/invalid:", responseData);
                                if (window.showNotification) showNotification(responseData?.message || 'Операция на сервере не удалась.', 'warning');
                                // --- Откат визуального изменения ---
                                if (evt.from && typeof evt.oldDraggableIndex !== 'undefined') {
                                    console.warn(`Attempting to revert drag for task ${taskId} due to unsuccessful operation confirmation.`);
                                    evt.from.insertBefore(taskElement, evt.from.children[evt.oldDraggableIndex]);
                                    updateTaskCounts(); // Обновляем счетчики после отката
                                }
                            }

                        } else {
                            // --- Ошибка от сервера (статус не 2xx) ---
                            // authenticatedFetch уже должен был показать уведомление с текстом ошибки
                            console.error(`Server responded !ok: ${response.status}`); // LOG 9
                            // --- Откат визуального изменения ---
                            if (evt.from && typeof evt.oldDraggableIndex !== 'undefined') {
                                console.warn(`Attempting to revert drag for task ${taskId} due to server error (${response.status}).`);
                                evt.from.insertBefore(taskElement, evt.from.children[evt.oldDraggableIndex]);
                                updateTaskCounts(); // Обновляем счетчики после отката
                            }
                        }
                    } catch (error) {
                        // --- Ошибка сети или JS ошибка в процессе fetch/обработки ---
                        // authenticatedFetch уже должен был показать уведомление "Ошибка сети..."
                        console.error(`Caught error during status/order update process for task ${taskId}:`, error); // LOG 10
                        // --- Откат визуального изменения ---
                        if (evt.from && typeof evt.oldDraggableIndex !== 'undefined') {
                             console.warn(`Attempting to revert drag for task ${taskId} due to fetch/JS error.`);
                             evt.from.insertBefore(taskElement, evt.from.children[evt.oldDraggableIndex]);
                             updateTaskCounts(); // Обновляем счетчики после отката
                        }
                    } 
                    // app_utils.js -> authenticatedFetch -> finally
                    finally {
                        const finalIndicatorCheck = document.querySelector(indicatorSelector); // <<< ПРОВЕРЯЕМ ЕЩЕ РАЗ
                        console.log(`Finally check: Found indicator [${indicatorSelector}]?`, finalIndicatorCheck); // <<< НОВЫЙ ЛОГ
                    
                        if (finalIndicatorCheck) { // <<< ИСПОЛЬЗУЕМ ПЕРЕПРОВЕРЕННЫЙ ЭЛЕМЕНТ
                             console.log("Hiding indicator:", indicatorSelector);
                             finalIndicatorCheck.classList.add('hidden');
                        } else {
                             console.log("Indicator not found in finally:", indicatorSelector); // <<< ИЗМЕНЕННЫЙ ЛОГ
                        }
                    }
                } // --- Конец обработчика onEnd ---
            }); // End new Sortable
            sortableInstances.push(instance);
        }); // End columns.forEach

        initializeKanbanDeleteButtons();
        console.log(`Kanban initialized for ${columns.length} columns.`);

    } // End initializeKanban

    function updateTaskCounts() {
         if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        requestAnimationFrame(() => {
            kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(column => {
                const countElement = column.querySelector('.task-count');
                if (countElement) {
                    const taskCount = column.querySelectorAll('.kanban-tasks .kanban-task').length;
                    countElement.textContent = taskCount;
                }
            });
        });
    }

    // Helper function to show/hide a Kanban column wrapper based on status
    const updateColumnVisibility = (status, isVisible) => {
        kanbanBoardContainer?.querySelectorAll(`.kanban-column-wrapper[data-status="${status}"]`)
            .forEach(wrapper => wrapper.classList.toggle('hidden', !isVisible));
    };

    function initializeColumnToggler() {
        if (!columnToggleDropdown || !resetHiddenColumnsBtn || !columnCheckboxes.length) return;

        const saveHiddenColumns = () => {
            const hiddenStatuses = [];
            columnCheckboxes.forEach(cb => {
                if (!cb.checked) {
                    hiddenStatuses.push(cb.dataset.status);
                }
            });
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

            const dropdownMenuId = dropdownHoverButton?.getAttribute('data-dropdown-toggle');
            if (dropdownMenuId && typeof Flowbite !== 'undefined') {
                 const dropdownInstance = Flowbite.getInstance('Dropdown', dropdownMenuId);
                 if (dropdownInstance) dropdownInstance.hide();
            }
        });
    }

    function restoreHiddenColumns() {
        if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        const hiddenStatuses = JSON.parse(localStorage.getItem('hiddenKanbanColumns') || '[]');
        console.log('Restoring hidden columns:', hiddenStatuses);
        kanbanBoardContainer.querySelectorAll('.kanban-column-wrapper').forEach(wrapper => wrapper.classList.remove('hidden'));
        columnCheckboxes.forEach(cb => cb.checked = true);
        hiddenStatuses.forEach(status => {
            const checkbox = document.querySelector(`.toggle-column-checkbox[data-status="${status}"]`);
            if (checkbox) {
                checkbox.checked = false;
                updateColumnVisibility(status, false);
            } else {
                console.warn(`Checkbox for status ${status} not found during restore.`);
            }
        });
        adjustKanbanLayout();
    }

    function adjustKanbanLayout() {
         if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        requestAnimationFrame(() => {
            const visibleCols = kanbanBoardContainer.querySelectorAll('.kanban-column-wrapper:not(.hidden)');
            const containerWidth = kanbanBoardContainer.offsetWidth;
            const colWidthEstimate = 320;
            const colGapEstimate = 16;
            const totalWidth = visibleCols.length * (colWidthEstimate + colGapEstimate) - colGapEstimate;
            kanbanBoardContainer.classList.toggle('justify-center', totalWidth <= containerWidth);
            kanbanBoardContainer.classList.toggle('justify-start', totalWidth > containerWidth);
        });
    }

    // --- List --- (Functions unchanged)
    function initializeListSort() {
        if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
        const table = taskListContainer.querySelector('table'); if (!table) return;
        const headers = table.querySelectorAll('.sort-header');
        const tbody = table.querySelector('tbody'); if (!tbody || headers.length === 0) return;
        const savedCol = localStorage.getItem('taskListSortColumn');
        const savedOrd = parseInt(localStorage.getItem('taskListSortOrder') || '1', 10);
        headers.forEach(header => { /* ... set initial icons ... */ });
        headers.forEach(header => { header.addEventListener('click', function () { /* ... sort logic ... */ }); });
        if (savedCol) { /* ... apply initial sort ... */ }
    }
    function initializeListStatusChange() {
        if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
        const tbody = taskListContainer.querySelector('tbody'); if (!tbody) return;
        tbody.addEventListener('change', async function (event) { /* ... status change logic using ajaxTaskBaseUrl ... */ });
        tbody.querySelectorAll('.status-dropdown').forEach(select => { select.dataset.previousValue = select.value; });
    }

    // --- Delete --- (Functions unchanged)
    function setupDeleteTaskHandler(containerSelector) {
        const container = document.querySelector(containerSelector); if (!container) return;
        container.addEventListener('click', async function (event) { /* ... delete logic using data-delete-url ... */ });
    }
    function initializeListDeleteButtons() { setupDeleteTaskHandler('#task-list'); }
    function initializeKanbanDeleteButtons() { setupDeleteTaskHandler('#kanban-board'); }

    // --- Create/Edit Forms (Modal Handling) --- (Functions unchanged)
    function initializeTaskForms() { /* ... */ }
    async function loadFormIntoModal(url) { /* ... */ }
    async function handleFormSubmit(event) { /* ... */ }

    // --- UI Update Functions --- (Functions unchanged)
    function updateTaskUI(taskId, newStatus) { /* ... */ }
    function removeTaskFromUI(taskId) { /* ... */ }
    function addNewTaskToUI(taskHtml, status) { /* ... */ }
    function updateExistingTaskUI(taskId, taskHtml, status) { /* ... */ }
    function updateStatusBadge(tableRow, newStatus) { /* ... */ }

    // --- Helpers --- (Functions unchanged)
    function escapeHtml(unsafe) { /* ... */ }
    function debounce(func, wait) { /* ... */ };

    // --- Init ---
    initializeViewSwitcher();
    initializeColumnToggler();
    initializeTaskForms();
    connectWebSocket();
    window.addEventListener('resize', debounce(adjustKanbanLayout, 250));

    console.log("tasks.js initialization complete.");

}); // End DOMContentLoaded