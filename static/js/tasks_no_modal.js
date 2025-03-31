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
    // Modal elements are removed

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
        taskUpdateSocket.onopen = () => console.log('Task Update WebSocket connection established.');
        taskUpdateSocket.onmessage = handleWebSocketMessage;
        taskUpdateSocket.onerror = (error) => { console.error('Task Update WebSocket error:', error); if (window.showNotification) showNotification('Ошибка соединения WebSocket', 'error'); };
        taskUpdateSocket.onclose = (event) => {
            console.log('Task Update WebSocket connection closed.', event.code, event.reason);
            if (!event.wasClean) {
                if (window.showNotification) showNotification('WebSocket отключен. Переподключение...', 'warning');
                const retryDelay = Math.min(30000, (Math.pow(2, window.wsRetryCount || 0) * 1000) + Math.random() * 1000);
                window.wsRetryCount = (window.wsRetryCount || 0) + 1;
                console.log(`Retrying WS connection in ${retryDelay/1000}s`);
                setTimeout(connectWebSocket, retryDelay);
            } else {
                window.wsRetryCount = 0;
            }
        };
    }

    function handleWebSocketMessage(event) {
        // ... (Логика обработки сообщений WS остается прежней) ...
        // Важно: Теперь функции addNewTaskToUI и updateExistingTaskUI должны получать
        // HTML и для списка, и для канбана, и правильно их вставлять/заменять.
        // Или, проще, после получения события о создании/обновлении - перезагружать страницу
        // или делать AJAX-запрос для обновления части страницы (но это сложнее).
        // Пока оставим как есть, но возможно потребуется доработка этой части.
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
            } else if (data.type === 'list_update' && data.message?.event === 'task_created') {
                 // Простейший вариант - перезагрузка для отображения новой задачи
                 if (window.showNotification) showNotification(`Добавлена новая задача ${data.message.created_by || ''}. Обновление списка...`, 'success');
                 setTimeout(() => window.location.reload(), 1500); // Перезагрузка с задержкой
                // addNewTaskToUI(data.message.task_html_list || null, data.message.task_html_kanban || null, data.message.status);
            } else if (data.type === 'list_update' && data.message?.event === 'task_deleted') {
                removeTaskFromUI(data.message.task_id);
                if (window.showNotification) showNotification(`Задача #${data.message.task_id} удалена ${data.message.deleted_by || ''}`, 'info');
            } else if (data.type === 'list_update' && data.message?.event === 'task_updated') {
                // Простейший вариант - перезагрузка
                 if (window.showNotification) showNotification(`Задача #${data.message.task_id} обновлена ${data.message.updated_by || ''}. Обновление списка...`, 'info');
                 setTimeout(() => window.location.reload(), 1500);
                // updateExistingTaskUI(data.message.task_id, data.message.task_html_list || null, data.message.task_html_kanban || null, data.message.status);
            } else if (data.type === 'error') {
                console.error('WebSocket error message from consumer:', data.message);
                if (window.showNotification) showNotification(`Ошибка обновления задачи: ${data.message}`, 'error');
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

    // --- View Switching ---
    function initializeViewSwitcher() {
        // ... (Код остается без изменений) ...
         const urlParams = new URLSearchParams(window.location.search);
        const viewParam = urlParams.get('view');
        const savedView = localStorage.getItem('taskView');
        const initialView = viewParam || savedView || 'kanban';

        const updateButton = (btn, iconEl, textEl, view) => { /* ... */ };
        const setView = (view) => { /* ... */ };

        setView(initialView);
        [toggleViewBtn, toggleViewBtnMobile].forEach(btn => { /* ... */ });
    }

    // --- Kanban ---
    let sortableInstances = [];
    function initializeKanban() {
         // ... (Код SortableJS и onEnd остается без изменений) ...
        if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        sortableInstances.forEach(instance => instance.destroy());
        sortableInstances = [];
        console.log("Initializing Kanban board...");
        const columns = kanbanBoardContainer.querySelectorAll('.kanban-tasks');
        if (columns.length === 0) return;

        columns.forEach(column => { /* ... new Sortable(...) ... */ });

        initializeKanbanDeleteButtons(); // Обработчики удаления для Канбана
        console.log(`Kanban initialized for ${columns.length} columns.`);
    }

    function updateKanbanColumnUI(columnElement) {
        // ... (Код остается без изменений) ...
         if (!columnElement) return;
        requestAnimationFrame(() => { /* ... */ });
    }

    const updateColumnVisibility = (status, isVisible) => {
        // ... (Код остается без изменений) ...
        kanbanBoardContainer?.querySelectorAll(`.kanban-column-wrapper[data-status="${status}"]`)
            .forEach(wrapper => wrapper.classList.toggle('hidden', !isVisible));
    };

    function initializeColumnToggler() {
        // ... (Код остается без изменений) ...
         if (!columnToggleDropdown || !resetHiddenColumnsBtn || !columnCheckboxes.length) return;
        const saveHiddenColumns = () => { /* ... */ };
        columnCheckboxes.forEach(checkbox => { /* ... */ });
        resetHiddenColumnsBtn.addEventListener('click', () => { /* ... */ });
    }

    function restoreHiddenColumns() {
        // ... (Код остается без изменений) ...
        if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        const hiddenStatuses = JSON.parse(localStorage.getItem('hiddenKanbanColumns') || '[]');
        console.log('Restoring hidden columns:', hiddenStatuses);
        kanbanBoardContainer.querySelectorAll('.kanban-column-wrapper').forEach(wrapper => wrapper.classList.remove('hidden'));
        columnCheckboxes.forEach(cb => cb.checked = true);
        hiddenStatuses.forEach(status => { /* ... */ });
        adjustKanbanLayout();
    }

    function adjustKanbanLayout() {
        // ... (Код остается без изменений) ...
         if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        requestAnimationFrame(() => { /* ... */ });
    }

    // --- List ---
    function initializeListSort() {
        // ... (Код остается без изменений) ...
        if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
        const table = taskListContainer.querySelector('table'); if (!table) return;
        const headers = table.querySelectorAll('.sort-header');
        const tbody = table.querySelector('tbody'); if (!tbody || headers.length === 0) return;
    }

    function initializeListStatusChange() {
        // ... (Код остается без изменений) ...
        if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
        const tbody = taskListContainer.querySelector('tbody'); if (!tbody) return;
        tbody.addEventListener('change', async function (event) { /* ... */ });
        tbody.querySelectorAll('.status-dropdown').forEach(select => { /* ... */ });
    }

    // --- Delete ---
    function setupDeleteTaskHandler(containerSelector) {
         // ... (Код остается БЕЗ изменений, т.к. он уже использует SweetAlert) ...
        const container = document.querySelector(containerSelector); if (!container) return;
        container.addEventListener('click', async function (event) { /* ... */ });
    }
    function initializeListDeleteButtons() { setupDeleteTaskHandler('#task-list'); }
    function initializeKanbanDeleteButtons() { setupDeleteTaskHandler('#kanban-board'); }

    // --- ФУНКЦИИ ДЛЯ МОДАЛОК УДАЛЕНЫ ---
    // function initializeTaskForms() { ... }
    // async function loadFormIntoModal(url) { ... }
    // async function handleFormSubmit(event) { ... }
    // function displayFormErrors(form, errors) { ... }
    // ---------------------------------------

    // --- UI Update Functions ---
    // Оставляем, т.к. они нужны для обновления после WebSocket и AJAX (смена статуса, удаление)
    function updateTaskUI(taskId, newStatus) {
        // ... (Код остается без изменений) ...
        console.log(`Updating UI for task ${taskId} to status ${newStatus}`);
        const taskElementKanban = kanbanBoardContainer.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
        const taskElementRow = taskListContainer.querySelector(`#task-row-${taskId}`);
        // ... (обновление Канбана) ...
        // ... (обновление Списка) ...
    }

    function removeTaskFromUI(taskId) {
        // ... (Код остается без изменений) ...
        console.log(`Removing task ${taskId} from UI`);
        const taskElementKanban = kanbanBoardContainer.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
        const taskElementRow = taskListContainer.querySelector(`#task-row-${taskId}`);
        let sourceColumn = null;
        if (taskElementKanban) { /* ... */ }
        if (taskElementRow) { taskElementRow.remove(); }
    }

    // Функции addNewTaskToUI и updateExistingTaskUI теперь не нужны,
    // так как при создании/обновлении будет полная перезагрузка страницы или редирект.
    // function addNewTaskToUI(taskHtmlList, taskHtmlKanban, status) { ... }
    // function updateExistingTaskUI(taskId, taskHtmlList, taskHtmlKanban, status) { ... }

    function updateStatusBadge(tableRow, newStatusKey) {
        // ... (Код остается без изменений) ...
        if (!tableRow) return;
        const badge = tableRow.querySelector('.status-badge');
        const statusMap = window.taskStatusMapping || {};
        const statusInfo = statusMap[newStatusKey];
        // ... (логика обновления баджа) ...
    }

    // --- Helpers ---
    function escapeHtml(unsafe) { /* ... */ }
    function debounce(func, wait) { /* ... */ };

    // --- Init ---
    // Передаем status_mapping в JS (оставляем)
    window.taskStatusMapping = {};
     try { /* ... */ } catch(e) { /* ... */ }

    // Инициализируем только нужные функции
    initializeViewSwitcher(); // Переключение видов
    initializeColumnToggler(); // Скрытие колонок Канбана
    // initializeTaskForms(); // УДАЛЕНО
    connectWebSocket(); // WebSocket
    window.addEventListener('resize', debounce(adjustKanbanLayout, 250));

    console.log("tasks.js (No Modal version) initialization complete.");

}); // End DOMContentLoaded