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
    const modalContentElement = document.getElementById('modal-content'); // Убедитесь, что модалка есть
    const createTaskBtnDesktop = document.querySelector('#list_actions button[data-action="create-task"]');
    const createTaskBtnMobile = document.querySelector('#list_actions_mobile button[data-action="create-task"]');
    const dropdownHoverButton = document.getElementById('dropdownHoverButton'); // Для управления меню колонок

    // --- Get Base URL for AJAX calls ---
    // Получаем URL из любого доступного контейнера
    const ajaxTaskBaseUrl = kanbanBoardContainer?.dataset.ajaxBaseUrl
                           || taskListContainer?.dataset.ajaxBaseUrl
                           || '/core/ajax/tasks/'; // Безопасный fallback (без языка)
    // Проверка и логгирование
    if (!kanbanBoardContainer?.dataset.ajaxBaseUrl && !taskListContainer?.dataset.ajaxBaseUrl) {
        console.warn("Could not find data-ajax-base-url on containers. Using fallback:", ajaxTaskBaseUrl);
    } else {
        console.log("Using AJAX base URL:", ajaxTaskBaseUrl);
    }

    if (!taskListContainer || !kanbanBoardContainer) { // Теперь оба должны существовать
        console.error("Task list AND Kanban board containers must be present in the HTML. Exiting tasks.js initialization.");
        return;
    }

    // --- WebSocket ---
    // ... (Код WebSocket без изменений) ...
    let taskUpdateSocket = null;
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const wsPath = window.djangoWsPath || '/ws/task_updates/'; // Используем переменную из base.html или fallback
        const wsUrl = `${protocol}${window.location.host}${wsPath}`;
        console.log(`Connecting to WebSocket: ${wsUrl}`);
        taskUpdateSocket = new WebSocket(wsUrl);
        taskUpdateSocket.onopen = () => console.log('Task Update WebSocket connection established.');
        taskUpdateSocket.onmessage = handleWebSocketMessage;
        taskUpdateSocket.onerror = (error) => { console.error('Task Update WebSocket error:', error); if (window.showNotification) showNotification('Ошибка соединения WebSocket', 'error'); };
        taskUpdateSocket.onclose = (event) => {
            console.log('Task Update WebSocket connection closed.', event.code, event.reason);
            if (!event.wasClean) {
                if (window.showNotification) showNotification('WebSocket отключен. Переподключение...', 'warning');
                // Exponential backoff retry
                const retryDelay = Math.min(30000, (Math.pow(2, window.wsRetryCount || 0) * 1000) + Math.random() * 1000);
                window.wsRetryCount = (window.wsRetryCount || 0) + 1;
                console.log(`Retrying WS connection in ${retryDelay/1000}s`);
                setTimeout(connectWebSocket, retryDelay);
            } else {
                window.wsRetryCount = 0; // Reset retry count on clean close
            }
        };
    }

    function handleWebSocketMessage(event) {
        try {
            const data = JSON.parse(event.data);
            console.log('WebSocket message received:', data);
            const currentUserId = window.currentUserId || null; // Получаем ID текущего юзера

            // Игнорируем обновления, инициированные этим же пользователем, если есть user_id
            const initiatorUserId = data.message?.updated_by_id; // Пример, как может приходить ID
            if (initiatorUserId && currentUserId && initiatorUserId === currentUserId) {
                 console.log(`Skipping self-initiated WebSocket update for task ${data.message?.task_id}, type: ${data.type}`);
                 return;
            }

            // Обработка разных типов сообщений
            if (data.type === 'task_update' && data.message?.event === 'status_update') {
                const msg = data.message;
                if (window.showNotification) showNotification(`Статус задачи #${msg.task_id} обновлен на "${msg.status_display}" ${msg.updated_by || ''}`, 'info');
                updateTaskUI(msg.task_id, msg.status); // Обновляем UI
            } else if (data.type === 'list_update' && data.message?.event === 'task_created') {
                // Это сообщение для списков, нужно добавить задачу
                addNewTaskToUI(data.message.task_html_list || null, data.message.task_html_kanban || null, data.message.status);
                if (window.showNotification) showNotification(`Добавлена новая задача ${data.message.created_by || ''}`, 'success');
            } else if (data.type === 'list_update' && data.message?.event === 'task_deleted') {
                removeTaskFromUI(data.message.task_id);
                if (window.showNotification) showNotification(`Задача #${data.message.task_id} удалена ${data.message.deleted_by || ''}`, 'info');
            } else if (data.type === 'list_update' && data.message?.event === 'task_updated') {
                updateExistingTaskUI(data.message.task_id, data.message.task_html_list || null, data.message.task_html_kanban || null, data.message.status);
                if (window.showNotification) showNotification(`Задача #${data.message.task_id} обновлена ${data.message.updated_by || ''}`, 'info');
            } else if (data.type === 'error') { // Обработка ошибок от консьюмера
                console.error('WebSocket error message from consumer:', data.message);
                if (window.showNotification) showNotification(`Ошибка обновления задачи: ${data.message}`, 'error');
                // Возможно, нужно откатить оптимистичное обновление UI здесь
                if (data.task_id && data.original_status) {
                    console.warn(`Attempting to revert UI for task ${data.task_id} to status ${data.original_status} due to server error.`);
                    updateTaskUI(data.task_id, data.original_status);
                }
            }
             else {
                console.warn("Received unknown WebSocket message structure:", data);
            }
        } catch (error) {
            console.error('Error processing WebSocket message:', error);
        }
    }
    // ---

    // --- View Switching ---
    function initializeViewSwitcher() {
        // Определяем начальный вид из localStorage или параметра URL, или дефолт
        const urlParams = new URLSearchParams(window.location.search);
        const viewParam = urlParams.get('view'); // ?view=list или ?view=kanban
        const savedView = localStorage.getItem('taskView');
        const initialView = viewParam || savedView || 'kanban'; // Приоритет: URL > localStorage > default

        const updateButton = (btn, iconEl, textEl, view) => {
            if (!btn || !iconEl || !textEl) return;
            const isKanban = view === 'kanban';
            iconEl.className = `fas ${isKanban ? 'fa-list' : 'fa-columns'} mr-2`; // Иконка показывает, НА ЧТО переключит кнопка
            textEl.textContent = isKanban ? ' {% trans "Вид: Канбан" %}' : ' {% trans "Вид: Список" %}'; // Текст показывает ТЕКУЩИЙ вид
            btn.setAttribute('aria-pressed', isKanban.toString()); // aria-pressed для текущего состояния
        };

        const setView = (view) => {
            const isKanban = view === 'kanban';

            // Переключаем видимость контейнеров
            taskListContainer.classList.toggle('hidden', isKanban);
            kanbanBoardContainer.classList.toggle('hidden', !isKanban);

            // Переключаем видимость кнопки управления колонками и пагинации
            columnToggleDropdown?.closest('.relative')?.classList.toggle('hidden', !isKanban);
            document.getElementById('pagination')?.classList.toggle('hidden', isKanban);

            // Сохраняем выбор пользователя
            localStorage.setItem('taskView', view);

            // Обновляем вид кнопок
            const viewIcon = document.getElementById('viewIcon');
            const viewText = document.getElementById('viewText');
            const viewIconMobile = document.getElementById('viewIconMobile');
            const viewTextMobile = document.getElementById('viewTextMobile');
            if (toggleViewBtn) updateButton(toggleViewBtn, viewIcon, viewText, view);
            if (toggleViewBtnMobile) updateButton(toggleViewBtnMobile, viewIconMobile, viewTextMobile, view);

            // Инициализируем специфичные для вида функции
            if (isKanban) {
                initializeKanban(); // Инициализация SortableJS
                restoreHiddenColumns(); // Восстановление скрытых колонок
                updateKanbanColumnUI(); // Обновление счетчиков И сообщения "Нет задач"
                adjustKanbanLayout(); // Центрирование/растягивание
            } else {
                initializeListSort(); // Инициализация сортировки таблицы
                initializeListDeleteButtons(); // Обработчики удаления для списка
                initializeListStatusChange(); // Выпадающие списки статусов
            }
            console.log(`View switched to: ${view}`);
            // Обновляем URL без перезагрузки страницы (опционально)
            if (window.history.pushState) {
                 const newUrl = new URL(window.location);
                 newUrl.searchParams.set('view', view);
                 window.history.pushState({path:newUrl.href}, '', newUrl.href);
            }
        };

        // Устанавливаем начальный вид при загрузке
        setView(initialView);

        // Назначаем обработчики на кнопки переключения
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
        if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        // Уничтожаем старые экземпляры SortableJS перед новой инициализацией
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
                ghostClass: 'kanban-ghost', // Класс для "тени" перетаскиваемого элемента
                chosenClass: 'kanban-chosen', // Класс для выбранного элемента
                dragClass: 'kanban-dragging', // Класс для перетаскиваемого элемента
                forceFallback: true, // Используется для лучшей совместимости и стилизации
                fallbackOnBody: true, // "Тень" элемента добавляется в body
                swapThreshold: 0.65, // Порог для смены местами

                onStart: (evt) => {
                    // Визуальные эффекты при начале перетаскивания
                    kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => col.classList.add('kanban-drag-active-zone')); // Подсветка зон
                    evt.item.classList.add('shadow-xl', 'scale-105', 'opacity-90'); // Эффект для перетаскиваемого элемента
                },
                onEnd: async (evt) => {
                    console.log("--- Kanban onEnd Handler START ---", evt);

                    // Убираем визуальные эффекты
                    kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => col.classList.remove('kanban-drag-active-zone'));
                    evt.item.classList.remove('shadow-xl', 'scale-105', 'opacity-90');

                    const taskElement = evt.item;
                    const targetColumnTasksContainer = evt.to; // Контейнер .kanban-tasks КУДА перетащили
                    const sourceColumnTasksContainer = evt.from; // Контейнер .kanban-tasks ОТКУДА перетащили
                    const targetColumnElement = targetColumnTasksContainer.closest('.kanban-column');
                    const sourceColumnElement = sourceColumnTasksContainer.closest('.kanban-column');

                    const taskId = taskElement.dataset.taskId;
                    const newStatus = targetColumnElement?.dataset.status;
                    const oldStatus = sourceColumnElement?.dataset.status;
                    const newIndex = evt.newDraggableIndex;

                    // --- Обновляем UI колонок (счетчики и "Нет задач") СРАЗУ ---
                    updateKanbanColumnUI(sourceColumnElement); // Обновляем колонку-источник
                    updateKanbanColumnUI(targetColumnElement); // Обновляем колонку-назначение

                    // --- Валидация ---
                    if (!taskId || !newStatus || !targetColumnElement) {
                        console.error("Kanban drop error: Missing taskId, newStatus, or target column data attribute.");
                        if (sourceColumnTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') {
                            console.warn("Attempting to revert drag due to missing data.");
                            // Вставляем обратно в ИСХОДНУЮ колонку на старую позицию
                            sourceColumnTasksContainer.insertBefore(taskElement, sourceColumnTasksContainer.children[evt.oldDraggableIndex]);
                            // Снова обновляем UI колонок после отката
                            updateKanbanColumnUI(sourceColumnElement);
                            updateKanbanColumnUI(targetColumnElement);
                        }
                        if (window.showNotification) showNotification('Ошибка перемещения: неверные данные.', 'error');
                        return;
                    }

                    // --- Если статус не изменился, выходим (можно добавить логику порядка) ---
                    if (oldStatus === newStatus && sourceColumnTasksContainer === targetColumnTasksContainer) {
                        console.log(`Task ${taskId} dropped in the same column (${newStatus}). Status update not needed.`);
                        // Здесь можно добавить AJAX для сохранения порядка, если нужно
                        return;
                    }

                    // --- Отправка AJAX запроса ---
                    console.log(`Task ${taskId} moved from status '${oldStatus || 'unknown'}' to '${newStatus}'. Sending update...`);
                    const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`;

                    try {
                        // Показываем индикатор загрузки (если есть)
                        const loadingIndicator = document.getElementById('loading-indicator');
                        if(loadingIndicator) loadingIndicator.classList.remove('hidden');

                        const response = await window.authenticatedFetch(url, {
                            method: 'POST',
                            body: { status: newStatus } // Отправляем только новый статус
                        });

                        if (response.ok) {
                            const responseData = await response.json();
                            if (responseData.success) {
                                console.log(`Status for task ${taskId} updated successfully on server. New status: ${responseData.new_status_key}`);
                                taskElement.dataset.status = responseData.new_status_key; // Обновляем data-атрибут
                                if (window.showNotification) showNotification(responseData.message || `Статус задачи #${taskId} обновлен.`, 'success');
                            } else {
                                // Сервер ответил OK, но указал на ошибку (например, валидации)
                                console.warn("Server indicated failure:", responseData.message);
                                if (window.showNotification) showNotification(responseData.message || 'Ошибка обновления на сервере.', 'error');
                                // Откат
                                if (sourceColumnTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') {
                                    sourceColumnTasksContainer.insertBefore(taskElement, sourceColumnTasksContainer.children[evt.oldDraggableIndex]);
                                    updateKanbanColumnUI(sourceColumnElement);
                                    updateKanbanColumnUI(targetColumnElement);
                                }
                            }
                        } else {
                            // Ошибка сервера (не 2xx) - authenticatedFetch должен был показать уведомление
                            console.error(`Server error: ${response.status}`);
                            // Откат
                            if (sourceColumnTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') {
                                sourceColumnTasksContainer.insertBefore(taskElement, sourceColumnTasksContainer.children[evt.oldDraggableIndex]);
                                updateKanbanColumnUI(sourceColumnElement);
                                updateKanbanColumnUI(targetColumnElement);
                            }
                        }
                    } catch (error) {
                        // Ошибка сети или JS - authenticatedFetch должен был показать уведомление
                        console.error(`Fetch/JS error during status update for task ${taskId}:`, error);
                        // Откат
                        if (sourceColumnTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') {
                             sourceColumnTasksContainer.insertBefore(taskElement, sourceColumnTasksContainer.children[evt.oldDraggableIndex]);
                             updateKanbanColumnUI(sourceColumnElement);
                             updateKanbanColumnUI(targetColumnElement);
                        }
                    } finally {
                         if(loadingIndicator) loadingIndicator.classList.add('hidden');
                    }
                } // --- Конец onEnd ---
            }); // End new Sortable
            sortableInstances.push(instance);
        }); // End columns.forEach

        initializeKanbanDeleteButtons(); // Навешиваем обработчики удаления на кнопки в Канбане
        console.log(`Kanban initialized for ${columns.length} columns.`);

    } // End initializeKanban

    // ИЗМЕНЕНО: Функция обновляет и счетчик, и сообщение "Нет задач"
    function updateKanbanColumnUI(columnElement) {
        if (!columnElement) return; // Проверка, что элемент колонки передан

        requestAnimationFrame(() => { // Используем requestAnimationFrame для плавности
            const tasksContainer = columnElement.querySelector('.kanban-tasks');
            if (!tasksContainer) return;

            const countElement = columnElement.querySelector('.task-count');
            const noTasksMessage = tasksContainer.querySelector('.no-tasks-message'); // Ищем сообщение
            const taskElements = tasksContainer.querySelectorAll('.kanban-task');
            const taskCount = taskElements.length;

            // Обновляем счетчик
            if (countElement) {
                countElement.textContent = taskCount;
            }

            // Показываем/скрываем сообщение "Нет задач"
            if (noTasksMessage) {
                noTasksMessage.classList.toggle('hidden', taskCount > 0);
                // console.log(`Column ${columnElement.dataset.status}: Task count = ${taskCount}, NoTasks Hidden = ${taskCount > 0}`); // Отладка
            } else if (taskCount === 0) {
                 // Если сообщение не найдено, но задач нет, можно его создать динамически (опционально)
                 console.warn(`No '.no-tasks-message' element found in column ${columnElement.dataset.status}, but it's empty.`);
            }
        });
    }


    // Helper function to show/hide a Kanban column wrapper based on status
    const updateColumnVisibility = (status, isVisible) => {
        kanbanBoardContainer?.querySelectorAll(`.kanban-column-wrapper[data-status="${status}"]`)
            .forEach(wrapper => wrapper.classList.toggle('hidden', !isVisible));
    };

    function initializeColumnToggler() {
        // ... (код без изменений) ...
         if (!columnToggleDropdown || !resetHiddenColumnsBtn || !columnCheckboxes.length) return;
        const saveHiddenColumns = () => { /* ... */ };
        columnCheckboxes.forEach(checkbox => { checkbox.addEventListener('change', function () { updateColumnVisibility(this.dataset.status, this.checked); saveHiddenColumns(); adjustKanbanLayout(); }); });
        resetHiddenColumnsBtn.addEventListener('click', () => { /* ... */ });
    }

    function restoreHiddenColumns() {
        // ... (код без изменений) ...
        if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        const hiddenStatuses = JSON.parse(localStorage.getItem('hiddenKanbanColumns') || '[]');
        console.log('Restoring hidden columns:', hiddenStatuses);
        kanbanBoardContainer.querySelectorAll('.kanban-column-wrapper').forEach(wrapper => wrapper.classList.remove('hidden'));
        columnCheckboxes.forEach(cb => cb.checked = true);
        hiddenStatuses.forEach(status => { /* ... */ });
        adjustKanbanLayout();
    }

    function adjustKanbanLayout() {
        // ... (код без изменений) ...
         if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        requestAnimationFrame(() => { /* ... */ });
    }

    // --- List ---
    function initializeListSort() {
        // ... (логика сортировки таблицы без изменений) ...
        if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
        const table = taskListContainer.querySelector('table'); if (!table) return;
        const headers = table.querySelectorAll('.sort-header');
        const tbody = table.querySelector('tbody'); if (!tbody || headers.length === 0) return;
        // ... (остальная логика)
    }

    function initializeListStatusChange() {
        if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
        const tbody = taskListContainer.querySelector('tbody'); if (!tbody) return;

        tbody.addEventListener('change', async function (event) {
            if (event.target.matches('.status-dropdown')) {
                const selectElement = event.target;
                const taskId = selectElement.dataset.taskId;
                const newStatus = selectElement.value;
                const previousStatus = selectElement.dataset.previousValue || ''; // Получаем старое значение

                if (!taskId || newStatus === previousStatus) {
                    // Статус не изменился или нет ID
                     if (newStatus !== previousStatus) selectElement.value = previousStatus; // Возвращаем старое значение визуально
                    return;
                }

                console.log(`List status change: Task ${taskId} to ${newStatus}`);
                const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`;

                // Оптимистичное обновление UI (можно добавить/убрать)
                const row = selectElement.closest('tr');
                const badge = row?.querySelector('.status-badge');
                if(badge) {
                    // Обновляем текст и классы баджа (логика классов должна быть синхронизирована с шаблоном)
                    // badge.textContent = selectElement.options[selectElement.selectedIndex].text;
                    // Обновить классы... (сложно без helper-функции)
                }
                 selectElement.disabled = true; // Блокируем на время запроса

                try {
                    const response = await window.authenticatedFetch(url, {
                        method: 'POST',
                        body: { status: newStatus }
                    });

                    if (response.ok) {
                        const responseData = await response.json();
                        if (responseData.success) {
                            console.log(`List status update success for task ${taskId}`);
                            selectElement.dataset.previousValue = newStatus; // Обновляем предыдущее значение
                            // Обновляем бадж на основе ответа сервера
                            if(badge) updateStatusBadge(row, responseData.new_status_key);
                            if (window.showNotification) showNotification(responseData.message || 'Статус обновлен.', 'success');
                        } else {
                            console.warn(`List status update failed on server for task ${taskId}:`, responseData.message);
                            selectElement.value = previousStatus; // Возвращаем старое значение
                            if (window.showNotification) showNotification(responseData.message || 'Ошибка обновления статуса.', 'error');
                        }
                    } else {
                        console.error(`List status update server error for task ${taskId}: ${response.status}`);
                        selectElement.value = previousStatus; // Возвращаем старое значение
                        // Уведомление показано через authenticatedFetch
                    }
                } catch (error) {
                    console.error(`List status update fetch/JS error for task ${taskId}:`, error);
                    selectElement.value = previousStatus; // Возвращаем старое значение
                     // Уведомление показано через authenticatedFetch
                } finally {
                    selectElement.disabled = false; // Разблокируем в любом случае
                }
            }
        });

        // Сохраняем начальное значение для каждого select
        tbody.querySelectorAll('.status-dropdown').forEach(select => {
            select.dataset.previousValue = select.value;
        });
    }

    // --- Delete ---
    function setupDeleteTaskHandler(containerSelector) {
        const container = document.querySelector(containerSelector); if (!container) return;
        container.addEventListener('click', async function (event) {
            const deleteButton = event.target.closest('button[data-action="delete-task"]');
            if (!deleteButton) return;

            const taskId = deleteButton.dataset.taskId;
            const taskName = deleteButton.dataset.taskName || `ID ${taskId}`;
            const deleteUrl = deleteButton.dataset.deleteUrl; // Получаем URL из data-атрибута

            if (!taskId || !deleteUrl) {
                console.error("Delete button missing task ID or delete URL.");
                if (window.showNotification) showNotification('Ошибка: Не удалось определить задачу для удаления.', 'error');
                return;
            }

            // Используем SweetAlert2 для подтверждения (или window.confirm)
            const result = await Swal.fire({
                title: `Удалить задачу "${taskName}"?`,
                text: "Это действие нельзя будет отменить!",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#d33',
                cancelButtonColor: '#3085d6',
                confirmButtonText: 'Да, удалить!',
                cancelButtonText: 'Отмена'
            });

            if (result.isConfirmed) {
                console.log(`Attempting to delete task ${taskId} via ${deleteUrl}`);
                try {
                    const response = await window.authenticatedFetch(deleteUrl, { method: 'POST' }); // Используем DELETE или POST в зависимости от бэкенда

                    if (response.ok) {
                        const responseData = await response.json();
                        if (responseData.success !== false) { // Считаем успехом, если нет явного false
                             console.log(`Task ${taskId} deleted successfully.`);
                             removeTaskFromUI(taskId); // Удаляем из UI
                             if (window.showNotification) showNotification(responseData.message || `Задача "${taskName}" удалена.`, 'success');
                        } else {
                            console.warn(`Server indicated delete failure for task ${taskId}:`, responseData.message);
                             if (window.showNotification) showNotification(responseData.message || 'Не удалось удалить задачу на сервере.', 'error');
                        }
                    } else {
                        console.error(`Server error during delete for task ${taskId}: ${response.status}`);
                        // Уведомление показано authenticatedFetch
                    }
                } catch (error) {
                    console.error(`Fetch/JS error during delete for task ${taskId}:`, error);
                    // Уведомление показано authenticatedFetch
                }
            }
        });
    }
    function initializeListDeleteButtons() { setupDeleteTaskHandler('#task-list'); }
    function initializeKanbanDeleteButtons() { setupDeleteTaskHandler('#kanban-board'); }

    // --- Create/Edit Forms (Modal Handling) ---
    function initializeTaskForms() {
        // Обработчик для кнопок "Создать"
        [createTaskBtnDesktop, createTaskBtnMobile].forEach(btn => {
            if (btn) {
                btn.addEventListener('click', (e) => {
                    const url = e.currentTarget.dataset.createUrl;
                    if (url) loadFormIntoModal(url);
                });
            }
        });

        // Обработчик для кнопок "Редактировать" (делегирование событий)
        document.body.addEventListener('click', (e) => {
             const editButton = e.target.closest('button[data-action="edit-task"]');
             if (editButton) {
                 const url = editButton.dataset.editUrl;
                 if (url) loadFormIntoModal(url);
             }
        });

         // Обработчик отправки формы внутри модального окна
         const modalElement = document.getElementById('task-form-modal'); // Убедитесь, что ID модалки правильный
         if (modalElement) {
             modalElement.addEventListener('submit', handleFormSubmit);
         } else {
              console.warn("Modal element #task-form-modal not found for form submission handler.");
         }
    }

    async function loadFormIntoModal(url) {
        console.log(`Loading form from: ${url}`);
        const modalTitleElement = document.getElementById('task-modal-title');
        const modalBodyElement = document.getElementById('modal-content');
        const modalElement = document.getElementById('modal'); // Основной контейнер

        if (!modalTitleElement || !modalBodyElement || !modalElement) {
             console.error("Modal title, body, or main container element not found.");
             if(window.showNotification) showNotification('Ошибка интерфейса: не найдены элементы модального окна.', 'error');
             return;
        }

        const modalLoading = document.getElementById('modal-loading-indicator');
        if(modalLoading) modalLoading.classList.remove('hidden');
        modalBodyElement.innerHTML = '';
        modalTitleElement.textContent = 'Загрузка...';

        try {
            const response = await window.authenticatedFetch(url, { method: 'GET' });
            if (response.ok) {
                const html = await response.text();
                modalBodyElement.innerHTML = html;

                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = html;
                const formTitle = tempDiv.querySelector('h2')?.textContent
                               || tempDiv.querySelector('h3')?.textContent
                               || tempDiv.querySelector('.page-title')?.textContent
                               || 'Форма';
                modalTitleElement.textContent = formTitle;

                 if (typeof $ !== 'undefined' && $.fn.select2) {
                      $(modalBodyElement).find('.select2-single').select2({ theme: 'bootstrap-5', width: '100%', dropdownParent: $(modalElement) });
                      $(modalBodyElement).find('.select2-multiple').select2({ theme: 'bootstrap-5', width: '100%', dropdownParent: $(modalElement) });
                 }
                window.dispatchEvent(new CustomEvent('modal-open'));

            } else {
                console.error(`Failed to load form from ${url}: ${response.status}`);
                modalBodyElement.innerHTML = `<p class="text-red-500">Не удалось загрузить форму.</p>`;
                modalTitleElement.textContent = 'Ошибка';
                window.dispatchEvent(new CustomEvent('modal-open'));
            }
        } catch (error) {
            console.error(`Error loading form from ${url}:`, error);
            modalBodyElement.innerHTML = `<p class="text-red-500">Ошибка сети при загрузке формы.</p>`;
            modalTitleElement.textContent = 'Ошибка';
            window.dispatchEvent(new CustomEvent('modal-open'));
        } finally {
             if(modalLoading) modalLoading.classList.add('hidden');
        }
    }

    async function handleFormSubmit(event) {
        event.preventDefault(); // Предотвращаем стандартную отправку
        const form = event.target;
        const url = form.action;
        const method = form.method.toUpperCase();
        const submitButton = form.querySelector('button[type="submit"]');
        const buttonOriginalText = submitButton ? submitButton.innerHTML : '';
        if(submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Сохранение...';
        }

        // Очищаем предыдущие ошибки формы
        form.querySelectorAll('.form-errors').forEach(el => el.remove());
        form.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));

        try {
            // Используем FormData для правильной отправки файлов
            const formData = new FormData(form);
            const response = await window.authenticatedFetch(url, {
                method: method,
                body: formData // Отправляем FormData, не JSON!
                // Headers не нужны для FormData, браузер установит Content-Type multipart/form-data
            });

            const responseData = await response.json(); // Ожидаем JSON в ответе

            if (response.ok && responseData.success) {
                console.log("Form submitted successfully:", responseData.message);
                if (window.showNotification) showNotification(responseData.message || ('Данные сохранены.'), 'success');
                // Закрываем модальное окно
                const modalInstance = bootstrap.Modal.getInstance(document.getElementById('task-form-modal'));
                 if (modalInstance) modalInstance.hide();
                 // Перезагружаем страницу или обновляем список/канбан через WebSocket/AJAX
                 // window.location.reload(); // Простейший вариант
                 // TODO: Implement dynamic update without reload using WebSocket data or AJAX fetch
            } else {
                // Отображаем ошибки валидации или общую ошибку
                if (responseData.errors) {
                     console.warn("Form validation errors:", responseData.errors);
                     displayFormErrors(form, responseData.errors);
                     if (window.showNotification) showNotification(('Пожалуйста, исправьте ошибки в форме.'), 'warning');
                } else {
                    console.error("Form submission failed:", responseData.message || `Server error ${response.status}`);
                    if (window.showNotification) showNotification(responseData.message || ('Ошибка сохранения данных.'), 'error');
                     // Отобразить общую ошибку над формой
                     const generalErrorDiv = document.createElement('div');
                     generalErrorDiv.className = 'alert alert-danger form-errors'; // Используйте свои классы
                     generalErrorDiv.textContent = responseData.message || ('Произошла неизвестная ошибка.');
                     form.prepend(generalErrorDiv);
                }
            }
        } catch (error) {
            console.error("Error submitting form:", error);
            if (window.showNotification) showNotification(('Ошибка сети при отправке формы.'), 'error');
             // Отобразить общую ошибку над формой
             const generalErrorDiv = document.createElement('div');
             generalErrorDiv.className = 'alert alert-danger form-errors';
             generalErrorDiv.textContent = ('Ошибка сети.');
             form.prepend(generalErrorDiv);
        } finally {
             if(submitButton) {
                 submitButton.disabled = false;
                 submitButton.innerHTML = buttonOriginalText;
             }
        }
    }

    function displayFormErrors(form, errors) {
        // Отображение ошибок рядом с полями и общих ошибок
        for (const fieldName in errors) {
             const errorList = errors[fieldName]; // Список ошибок для поля
             const fieldElement = form.querySelector(`[name="${fieldName}"]`);
             const errorContainer = document.createElement('div');
             errorContainer.className = 'invalid-feedback form-errors'; // Класс для стилизации ошибок
             errorContainer.innerHTML = errorList.map(err => `<span>${escapeHtml(err.message || err)}</span>`).join('<br>');

             if (fieldElement) {
                 fieldElement.classList.add('is-invalid'); // Подсветка поля
                 // Вставляем ошибку после поля или в специальный контейнер
                 fieldElement.parentNode.insertBefore(errorContainer, fieldElement.nextSibling);
             } else if (fieldName === '__all__') {
                  // Общие ошибки формы
                  const generalErrorDiv = document.createElement('div');
                  generalErrorDiv.className = 'alert alert-danger form-errors'; // Общий блок ошибок
                  generalErrorDiv.innerHTML = errorList.map(err => `<span>${escapeHtml(err.message || err)}</span>`).join('<br>');
                  form.prepend(generalErrorDiv); // Вставляем в начало формы
             }
        }
    }

    // --- UI Update Functions ---
    function updateTaskUI(taskId, newStatus) {
        console.log(`Updating UI for task ${taskId} to status ${newStatus}`);
        const taskElementKanban = kanbanBoardContainer.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
        const taskElementRow = taskListContainer.querySelector(`#task-row-${taskId}`);

        // 1. Обновление Канбана (если видимый)
        if (!kanbanBoardContainer.classList.contains('hidden') && taskElementKanban) {
            const currentColumn = taskElementKanban.closest('.kanban-column');
            const targetColumn = kanbanBoardContainer.querySelector(`.kanban-column[data-status="${newStatus}"]`);
            const targetTasksContainer = targetColumn?.querySelector('.kanban-tasks');

            if (targetTasksContainer && currentColumn !== targetColumn) {
                console.log(`Moving task ${taskId} element to column ${newStatus}`);
                targetTasksContainer.appendChild(taskElementKanban); // Перемещаем элемент
                taskElementKanban.dataset.status = newStatus; // Обновляем data-атрибут
                // Обновляем UI обеих колонок
                updateKanbanColumnUI(currentColumn);
                updateKanbanColumnUI(targetColumn);
            } else if (!targetTasksContainer) {
                 console.warn(`Target column container for status ${newStatus} not found.`);
            } else {
                 console.log(`Task ${taskId} already in correct column ${newStatus}.`);
                 taskElementKanban.dataset.status = newStatus; // Обновляем data-атрибут на всякий случай
                 updateKanbanColumnUI(targetColumn); // Обновляем UI текущей колонки
            }
        }

        // 2. Обновление Списка (если видимый)
        if (!taskListContainer.classList.contains('hidden') && taskElementRow) {
            const statusSelect = taskElementRow.querySelector('.status-dropdown');
            const statusBadge = taskElementRow.querySelector('.status-badge');
            if (statusSelect && statusSelect.value !== newStatus) {
                statusSelect.value = newStatus;
                statusSelect.dataset.previousValue = newStatus; // Обновляем сохраненное значение
                console.log(`Updated list select for task ${taskId} to ${newStatus}`);
            }
            if (statusBadge) {
                updateStatusBadge(taskElementRow, newStatus); // Обновляем бадж
            }
             // Обновляем класс для просроченных задач в строке (если нужно)
            // const deadlineCell = taskElementRow.querySelector('td:nth-child(6)'); // Пример селектора
            // if(deadlineCell) {
            //      deadlineCell.classList.toggle('text-red-600', newStatus === 'overdue');
            // }
        }
    }

    function removeTaskFromUI(taskId) {
        console.log(`Removing task ${taskId} from UI`);
        const taskElementKanban = kanbanBoardContainer.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
        const taskElementRow = taskListContainer.querySelector(`#task-row-${taskId}`);
        let sourceColumn = null;

        if (taskElementKanban) {
             sourceColumn = taskElementKanban.closest('.kanban-column');
             taskElementKanban.remove();
             if (sourceColumn) updateKanbanColumnUI(sourceColumn); // Обновляем UI колонки-источника
        }
        if (taskElementRow) {
            taskElementRow.remove();
        }
        // TODO: Обновить пагинацию, если удалили из списка? (сложно без перезагрузки)
    }

    function addNewTaskToUI(taskHtmlList, taskHtmlKanban, status) {
         // Добавляет новую задачу в начало списка и канбан колонку
         console.log(`Adding new task to UI in status ${status}`);

         // Добавление в список (если видимый)
         if (!taskListContainer.classList.contains('hidden') && taskHtmlList) {
             const tbody = taskListContainer.querySelector('tbody');
             const noTasksRow = tbody?.querySelector('tr td[colspan]'); // Строка "Задачи не найдены"
             if (noTasksRow) noTasksRow.closest('tr').remove(); // Удаляем сообщение, если было
             tbody?.insertAdjacentHTML('afterbegin', taskHtmlList); // Вставляем в начало
             // Заново инициализируем обработчики для новой строки (если нужно)
             const newRow = tbody?.querySelector('tr:first-child');
             if (newRow) {
                 initializeListStatusChangeForRow(newRow);
                 initializeListDeleteButtonForRow(newRow);
             }
         }

         // Добавление в канбан (если видимый)
         if (!kanbanBoardContainer.classList.contains('hidden') && taskHtmlKanban) {
              const targetColumn = kanbanBoardContainer.querySelector(`.kanban-column[data-status="${status}"]`);
              const tasksContainer = targetColumn?.querySelector('.kanban-tasks');
              if (tasksContainer) {
                   tasksContainer.insertAdjacentHTML('afterbegin', taskHtmlKanban); // Вставляем в начало
                   updateKanbanColumnUI(targetColumn); // Обновляем UI колонки
                   // Заново инициализируем обработчики для новой карточки
                   const newCard = tasksContainer.querySelector('.kanban-task:first-child');
                   if(newCard) initializeKanbanDeleteButtonForCard(newCard);
              } else {
                   console.warn(`Kanban column for status ${status} not found when adding new task.`);
              }
         }
          // TODO: Обновить пагинацию/счетчики
    }

    function updateExistingTaskUI(taskId, taskHtmlList, taskHtmlKanban, status) {
        // Заменяет существующую карточку/строку новым HTML
        console.log(`Updating existing task ${taskId} in UI`);
        removeTaskFromUI(taskId); // Сначала удаляем старую версию
        addNewTaskToUI(taskHtmlList, taskHtmlKanban, status); // Затем добавляем новую
    }

    function updateStatusBadge(tableRow, newStatusKey) {
        if (!tableRow) return;
        const badge = tableRow.querySelector('.status-badge');
        const statusMap = window.taskStatusMapping || {}; // Предполагаем, что status_mapping доступен глобально или передан
        const statusInfo = statusMap[newStatusKey];

        if (badge && statusInfo) {
            badge.textContent = statusInfo.display;
            // Удаляем старые классы цвета и добавляем новые
             badge.className = 'status-badge px-2 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full'; // Сброс классов
             badge.classList.add(...(statusInfo.classes || ['bg-gray-100', 'text-gray-800'])); // Добавляем новые или дефолтные
            console.log(`Updated badge for task ${tableRow.id.split('-')[2]} to status ${newStatusKey}`);
        } else if (badge) {
             badge.textContent = newStatusKey; // Fallback
             badge.className = 'status-badge px-2 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-800'; // Default style
        }
    }

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
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };

    // --- Init ---
    // Передаем status_mapping в JS для использования в updateStatusBadge
    window.taskStatusMapping = {}; // Создаем объект для маппинга
     try {
        const statusMappingElement = document.getElementById('status-mapping-data'); // Ищем скрытый элемент
        if(statusMappingElement) {
            window.taskStatusMapping = JSON.parse(statusMappingElement.textContent);
        } else {
            // Fallback: пытаемся получить из первого status-dropdown (менее надежно)
            const firstDropdown = document.querySelector('.status-dropdown');
            if(firstDropdown) {
                Array.from(firstDropdown.options).forEach(opt => {
                    window.taskStatusMapping[opt.value] = { display: opt.text, classes: [] }; // Классы нужно будет определить
                });
            } else {
                 console.warn("Could not retrieve status mapping for JS UI updates.");
            }
        }
    } catch(e) {
        console.error("Error parsing status mapping data:", e);
    }


    initializeViewSwitcher(); // Запускает инициализацию нужного вида (Kanban или List)
    initializeColumnToggler(); // Инициализация скрытия колонок (для Канбана)
    initializeTaskForms(); // Инициализация модальных окон для форм
    connectWebSocket(); // Подключение WebSocket
    window.addEventListener('resize', debounce(adjustKanbanLayout, 250)); // Адаптация Канбана при ресайзе

    console.log("tasks.js initialization complete.");

}); // End DOMContentLoaded