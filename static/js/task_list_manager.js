// task_no_modal.js

"use strict";

document.addEventListener('DOMContentLoaded', () => {
    console.log("Initializing tasks.js (No Modal version for LIST VIEW)...");

    // --- Elements ---
    const taskListContainer = document.getElementById('task-list');
    const kanbanBoardContainer = document.getElementById('kanban-board');
    const toggleViewBtn = document.getElementById('toggleViewBtn');
    const toggleViewBtnMobile = document.getElementById('toggleViewBtnMobile');
    const columnToggleDropdown = document.getElementById('column-toggle-dropdown');
    const resetHiddenColumnsBtn = document.getElementById('resetHiddenColumnsBtn');
    const columnCheckboxes = document.querySelectorAll('.toggle-column-checkbox');
    const dropdownHoverButton = document.getElementById('dropdownHoverButton'); // For Flowbite dropdown
    const loadingIndicator = document.getElementById('loading-indicator');


    // --- Get Base URL for AJAX calls ---
    // Ensure this data attribute exists on one of the containers in your template
    const ajaxTaskBaseUrl = kanbanBoardContainer?.dataset.ajaxBaseUrl ||
                            taskListContainer?.dataset.ajaxBaseUrl ||
                            '/tasks/ajax/tasks/'; // Fallback, ensure your app's URL structure matches

    if (!kanbanBoardContainer?.dataset.ajaxBaseUrl && !taskListContainer?.dataset.ajaxBaseUrl) {
        console.warn("Could not find data-ajax-base-url on containers. Using fallback:", ajaxTaskBaseUrl);
    } else {
        console.log("Using AJAX base URL from data attribute.");
    }


    if (!taskListContainer || !kanbanBoardContainer) {
        console.error("Task list AND Kanban board containers must be present in the HTML. Exiting initialization.");
        return;
    }

    // --- WebSocket ---
    let taskListSocket = null;
    window.wsRetryCount = 0; // Initialize retry count globally for WebSocket

    function connectWebSocket() {
        if (!window.djangoWebsocketsEnabled) { // Check global var set by Django template
            console.log("WebSockets are disabled by Django settings. Skipping WebSocket connection.");
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        // window.djangoWsPath should be set by the Django template, e.g., to "{% url 'tasks:ws_task_list' %}"
        const wsPath = window.djangoWsPath || '/ws/tasks/list/'; // Fallback to the list consumer path

        if (window.djangoWsPath === undefined) {
            console.warn("window.djangoWsPath is not defined in the template. Defaulting WebSocket to: " + wsPath +
                         ". Ensure your Django template sets this to the correct WebSocket URL (e.g., using Django's {% url 'tasks:ws_task_list' %}).");
        }

        const wsUrl = `${protocol}${window.location.host}${wsPath}`;
        console.log(`Connecting to Task List WebSocket: ${wsUrl}`);

        taskListSocket = new WebSocket(wsUrl);

        taskListSocket.onopen = () => {
            console.log('Task List WebSocket connection established.');
            window.wsRetryCount = 0; // Reset retry count on successful connection
        };

        taskListSocket.onmessage = handleWebSocketMessage;

        taskListSocket.onerror = (error) => {
            console.error('Task List WebSocket error:', error);
            if (window.showNotification) window.showNotification('Ошибка WebSocket соединения со списком задач', 'error');
        };

        taskListSocket.onclose = (event) => {
            console.log('Task List WebSocket connection closed.', `Code: ${event.code}`, `Reason: "${event.reason}"`, `Was Clean: ${event.wasClean}`);
            // Don't retry if connection closed cleanly (code 1000) or by server for specific reasons (e.g. auth failure handled by consumer)
            if (!event.wasClean && event.code !== 1000 && event.code !== 4001 && event.code !== 4003) { // Example: 4001 for unauth, 4003 for forbidden
                if (window.showNotification) window.showNotification('WebSocket списка задач отключен. Попытка переподключения...', 'warning');
                const retryDelay = Math.min(30000, (Math.pow(1.5, window.wsRetryCount) * 2000) + Math.random() * 1000);
                window.wsRetryCount++;
                console.log(`Retrying Task List WS connection in ${Math.round(retryDelay / 1000)}s (Attempt ${window.wsRetryCount})`);
                setTimeout(connectWebSocket, retryDelay);
            } else {
                window.wsRetryCount = 0; // Reset on clean or non-retriable close
            }
        };
    }

    function handleWebSocketMessage(event) {
        try {
            const wsMessage = JSON.parse(event.data); // Message from consumer (includes type, payload, success)
            console.log('Task List WebSocket message received:', wsMessage);

            const signalData = wsMessage.payload; // This is the original 'message' from the signal
            const clientEventType = wsMessage.type; // This is for client-side JS to handle

            if (!signalData && clientEventType !== 'connection_established' && clientEventType !== 'websocket_error') {
                console.warn("WebSocket message received without payload:", wsMessage);
                return;
            }
            
            // window.currentUserId should be set in your Django template
            const currentUserId = window.currentUserId ? parseInt(window.currentUserId, 10) : null;
            
            // Determine initiator from various possible fields in signalData
            let initiatorUserId = null;
            if (signalData) {
                 initiatorUserId = signalData.updated_by_id || signalData.created_by_id || signalData.deleted_by_id || (signalData.author ? signalData.author.id : null);
                 if (initiatorUserId) initiatorUserId = parseInt(initiatorUserId, 10);
            }


            if (initiatorUserId && currentUserId && initiatorUserId === currentUserId) {
                console.log(`Skipping self-initiated WebSocket update. Event type: ${clientEventType}, Task ID: ${signalData?.task_id}`);
                return;
            }

            if (clientEventType === 'task_item_changed_in_list') {
                const taskId = signalData.task_id;
                const newStatusKey = signalData.status; // From task_list_item_update payload

                if (signalData.event_type === 'task_list_item_update') { // Corresponds to task_updated from original signal
                    const byUser = signalData.updated_by_username || ''; // Assuming updated_by_username is in payload
                    if (window.showNotification) showNotification(`Задача #${taskId} обновлена ${byUser}. Статус: ${signalData.status_display || newStatusKey}.`, 'info');
                    updateTaskUI(taskId, newStatusKey);
                } else if (signalData.event_type === 'task_created') {
                    const byUser = signalData.created_by_username || ''; // Assuming created_by_username is in payload
                    if (window.showNotification) showNotification(`Новая задача #${taskId} создана ${byUser}. Перезагрузка страницы...`, 'success');
                    setTimeout(() => window.location.reload(), 2000); // Reload to show new task
                } else if (signalData.event_type === 'task_deleted') {
                     const byUser = signalData.deleted_by_username || ''; // Assuming deleted_by_username is in payload
                    if (window.showNotification) showNotification(`Задача #${taskId} удалена ${byUser}.`, 'info');
                    removeTaskFromUI(taskId);
                } else {
                     console.warn("Unknown event_type within task_item_changed_in_list:", signalData);
                }

            } else if (clientEventType === 'websocket_error') { // Handle errors sent by consumer
                console.error('WebSocket error message from consumer:', wsMessage.payload?.message);
                if (window.showNotification) showNotification(`Ошибка WebSocket: ${wsMessage.payload?.message || 'Неизвестная ошибка'}`, 'error');
            } else if (clientEventType === 'connection_established') {
                console.log("WebSocket connection established message from server:", wsMessage.payload?.message);
            }
             else {
                console.warn("Received unknown WebSocket client event type:", clientEventType, "Full message:", wsMessage);
            }
        } catch (error) {
            console.error('Error processing WebSocket message:', error, "Raw data:", event.data);
        }
    }
    // --- End WebSocket ---

    // --- View Switching ---
    function initializeViewSwitcher() {
        // ... (Implementation from your provided JS, seems mostly fine) ...
        // Ensure querySelector targets are correct for your HTML
        const urlParams = new URLSearchParams(window.location.search);
        const viewParam = urlParams.get('view');
        const savedView = localStorage.getItem('taskView');
        const initialView = viewParam || savedView || 'kanban'; // Default to Kanban

        const updateButton = (btn, iconEl, textEl, view) => {
            if (!btn || !iconEl || !textEl) return;
            const isKanban = view === 'kanban';
            const kanbanText = btn.dataset.kanbanText || 'Вид: Канбан';
            const listText = btn.dataset.listText || 'Вид: Список';
            textEl.textContent = isKanban ? kanbanText : listText; // Change text to "Switch to List" or "Switch to Kanban"
            iconEl.className = `fas ${isKanban ? 'fa-list' : 'fa-th-large'} mr-2`; // fa-th-large for kanban icon
            btn.setAttribute('aria-pressed', isKanban.toString());
            // Update title attribute for hover hint
            btn.title = isKanban ? (btn.dataset.listText || 'Переключить на Список') : (btn.dataset.kanbanText || 'Переключить на Канбан');

        };

        const setView = (view) => {
            const isKanban = view === 'kanban';
            taskListContainer.classList.toggle('hidden', isKanban);
            kanbanBoardContainer.classList.toggle('hidden', !isKanban);
            
            // Show/hide column toggler and pagination based on view
            const columnTogglerWrapper = columnToggleDropdown?.closest('.relative');
            if (columnTogglerWrapper) columnTogglerWrapper.classList.toggle('hidden', isKanban); // Hide for Kanban, show for list
            document.getElementById('pagination')?.classList.toggle('hidden', isKanban); // Hide pagination for Kanban

            localStorage.setItem('taskView', view);

            const viewIcon = document.getElementById('viewIcon');
            const viewText = document.getElementById('viewText');
            const viewIconMobile = document.getElementById('viewIconMobile');
            const viewTextMobile = document.getElementById('viewTextMobile');

            if (toggleViewBtn && viewIcon && viewText) updateButton(toggleViewBtn, viewIcon, viewText, view);
            if (toggleViewBtnMobile && viewIconMobile && viewTextMobile) updateButton(toggleViewBtnMobile, viewIconMobile, viewTextMobile, view);
            
            if (isKanban) {
                initializeKanban(); // Initialize Sortable for Kanban
                restoreHiddenColumns(); // Restore hidden columns state for Kanban
                kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => updateKanbanColumnUI(col));
                adjustKanbanLayout();
            } else {
                initializeListSort(); // Initialize client-side sorting for list view
                initializeListDeleteButtons(); // Re-init delete for list items
                initializeListStatusChange(); // Re-init status change for list items
            }
            console.log(`View switched to: ${view}`);
            // Update URL without reloading
            if (window.history.pushState) {
                const newUrl = new URL(window.location);
                newUrl.searchParams.set('view', view);
                if (isKanban) newUrl.searchParams.delete('page'); // Remove page for Kanban
                window.history.pushState({ path: newUrl.href }, '', newUrl.href);
            }
        };
        setView(initialView); // Set initial view on page load

        [toggleViewBtn, toggleViewBtnMobile].forEach(btn => {
            if (btn) {
                btn.addEventListener('click', () => {
                    const currentStoredView = localStorage.getItem('taskView') || 'kanban';
                    // Toggle to the other view
                    const newView = currentStoredView === 'list' ? 'kanban' : 'list';
                    setView(newView);
                });
            }
        });
    }
    // --- End View Switching ---

    // --- Kanban Specific Functions ---
    let sortableInstances = [];
    function initializeKanban() {
        if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden') || typeof Sortable === 'undefined') {
            if(typeof Sortable === 'undefined') console.warn("SortableJS library not found. Kanban drag-drop will not work.");
            return;
        }
        sortableInstances.forEach(instance => instance.destroy()); // Destroy previous instances
        sortableInstances = [];
        console.log("Initializing Kanban board drag-and-drop...");
        const columns = kanbanBoardContainer.querySelectorAll('.kanban-tasks'); // Target the task containers
        if (columns.length === 0) { console.log("No Kanban task containers (.kanban-tasks) found."); return; }

        columns.forEach(column => {
            const instance = new Sortable(column, {
                group: 'kanban-shared-tasks', // Make sure this is consistent across all columns
                animation: 150,
                ghostClass: 'kanban-ghost', // Class for the placeholder
                chosenClass: 'kanban-chosen', // Class for the chosen item
                dragClass: 'kanban-dragging', // Class for the dragged item
                forceFallback: true, // Ensures ghost element works well
                fallbackOnBody: true, // Appends ghost to body
                swapThreshold: 0.65, // How much of an item needs to be over another to swap
                onStart: (evt) => {
                    kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => col.classList.add('kanban-drag-active-zone'));
                    evt.item.classList.add('shadow-xl', 'scale-105', 'opacity-90', 'rotate-1'); // Visual feedback
                },
                onEnd: async (evt) => {
                    kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => col.classList.remove('kanban-drag-active-zone'));
                    evt.item.classList.remove('shadow-xl', 'scale-105', 'opacity-90', 'rotate-1');

                    const taskElement = evt.item;
                    const targetTasksContainer = evt.to;
                    const sourceTasksContainer = evt.from;
                    const targetColumnElement = targetTasksContainer.closest('.kanban-column');
                    const sourceColumnElement = sourceTasksContainer.closest('.kanban-column');

                    const taskId = taskElement.dataset.taskId;
                    const newStatus = targetColumnElement?.dataset.status;
                    const oldStatus = sourceColumnElement?.dataset.status; // Or taskElement.dataset.status before move

                    // Update UI immediately for responsiveness
                    updateKanbanColumnUI(sourceColumnElement);
                    updateKanbanColumnUI(targetColumnElement);

                    if (!taskId || !newStatus || !targetColumnElement) {
                        console.error("Kanban drop error: Missing data (taskId, newStatus, or targetColumnElement). Reverting drag.");
                        // Revert drag if essential data is missing
                        if (sourceTasksContainer && typeof evt.oldDraggableIndex !== 'undefined') {
                            sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]);
                            updateKanbanColumnUI(sourceColumnElement);
                            updateKanbanColumnUI(targetColumnElement);
                        }
                        if (window.showNotification) showNotification('Ошибка перемещения задачи: неверные данные.', 'error');
                        return;
                    }

                    if (oldStatus === newStatus && sourceTasksContainer === targetTasksContainer) {
                        console.log(`Task ${taskId} reordered within the same column '${newStatus}'. No status update needed.`);
                        // Here you might want to send an API call to save the new order if your backend supports it.
                        return;
                    }
                    
                    console.log(`Task ${taskId} moved from status '${oldStatus || '?'}' to '${newStatus}'. Sending update to server...`);
                    const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`; // Correct AJAX URL

                    if (loadingIndicator) loadingIndicator.classList.remove('hidden');
                    try {
                        // authenticatedFetch should handle CSRF and headers
                        const response = await window.authenticatedFetch(url, {
                            method: 'POST',
                            body: JSON.stringify({ status: newStatus }), // Send as JSON
                            headers: { 'Content-Type': 'application/json' }
                        });

                        if (response.ok) {
                            const responseData = await response.json();
                            if (responseData.success) {
                                console.log(`Task ${taskId} status successfully updated on server. New status: ${responseData.new_status_key}`);
                                taskElement.dataset.status = responseData.new_status_key; // Confirm update on element
                                if (window.showNotification) showNotification(responseData.message || `Статус задачи #${taskId} обновлен.`, 'success');
                            } else {
                                console.warn("Server indicated status update failure:", responseData.message);
                                if (window.showNotification) showNotification(responseData.message || 'Ошибка обновления статуса на сервере.', 'error');
                                // Revert drag on server failure
                                sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]);
                                updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement);
                            }
                        } else {
                            const errorData = await response.json().catch(() => ({ message: `Server error: ${response.status}` }));
                            console.error(`Server error during status update: ${response.status}`, errorData.message);
                            if (window.showNotification) showNotification(errorData.message || `Ошибка сервера: ${response.status}`, 'error');
                            sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]);
                            updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement);
                        }
                    } catch (error) {
                        console.error(`Network/JS error during status update for task ${taskId}:`, error);
                        if (window.showNotification) showNotification('Сетевая ошибка при обновлении статуса.', 'error');
                        sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]);
                        updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement);
                    } finally {
                        if (loadingIndicator) loadingIndicator.classList.add('hidden');
                    }
                } // End onEnd
            });
            sortableInstances.push(instance);
        });
        initializeKanbanDeleteButtons(); // Initialize delete buttons for Kanban cards
        console.log(`Kanban drag-and-drop initialized for ${columns.length} task containers.`);
    }

    function updateKanbanColumnUI(columnElement) {
        if (!columnElement) return;
        requestAnimationFrame(() => { // Use rAF for smoother UI updates
            const tasksContainer = columnElement.querySelector('.kanban-tasks');
            if (!tasksContainer) return;

            const countElement = columnElement.querySelector('.task-count');
            const noTasksMessage = columnElement.querySelector('.no-tasks-message'); // Ensure this element exists in each column
            const taskElements = tasksContainer.querySelectorAll('.kanban-task'); // Count actual task elements
            const taskCount = taskElements.length;

            if (countElement) {
                countElement.textContent = taskCount;
            }
            if (noTasksMessage) {
                noTasksMessage.classList.toggle('hidden', taskCount > 0);
            } else if (taskCount === 0 && columnElement.dataset.status) { // Only warn if it's a real column
                console.warn(`'.no-tasks-message' element not found in Kanban column: ${columnElement.dataset.status}`);
            }
        });
    }

    const updateColumnVisibility = (status, isVisible) => {
        kanbanBoardContainer?.querySelectorAll(`.kanban-column-wrapper[data-status="${status}"]`)
            .forEach(wrapper => wrapper.classList.toggle('hidden', !isVisible));
    };

    function initializeColumnToggler() {
        // ... (Implementation from your provided JS, seems mostly fine) ...
        // Make sure dropdownHoverButton and Flowbite integration is correct if used.
        if (!columnToggleDropdown || !resetHiddenColumnsBtn || !columnCheckboxes.length) return;
        const saveHiddenColumns = () => {
            const hiddenStatuses = Array.from(columnCheckboxes)
                .filter(cb => !cb.checked)
                .map(cb => cb.dataset.status);
            localStorage.setItem('hiddenKanbanColumns', JSON.stringify(hiddenStatuses));
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
            if (dropdownMenuId && typeof Flowbite !== 'undefined' && Flowbite.getInstance) { // Check getInstance
                try {
                    const dropdownInstance = Flowbite.getInstance('Dropdown', dropdownMenuId);
                    if (dropdownInstance) dropdownInstance.hide();
                } catch (e) { console.warn("Could not hide Flowbite dropdown via getInstance:", e); }
            }
        });
    }

    function restoreHiddenColumns() {
        // ... (Implementation from your provided JS, seems mostly fine) ...
        if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        const hiddenStatuses = JSON.parse(localStorage.getItem('hiddenKanbanColumns') || '[]');
        
        // First, ensure all checkboxes are checked and columns are visible by default
        columnCheckboxes.forEach(cb => cb.checked = true);
        kanbanBoardContainer.querySelectorAll('.kanban-column-wrapper').forEach(wrapper => wrapper.classList.remove('hidden'));
        
        // Then, hide based on localStorage
        hiddenStatuses.forEach(status => {
            const checkbox = document.querySelector(`.toggle-column-checkbox[data-status="${status}"]`);
            if (checkbox) {
                checkbox.checked = false;
                updateColumnVisibility(status, false);
            }
        });
        adjustKanbanLayout();
    }

    function adjustKanbanLayout() {
        // ... (Implementation from your provided JS, seems mostly fine) ...
        // Consider using CSS Grid or Flexbox for responsive column layout primarily,
        // JS adjustments can be for fine-tuning or when CSS alone isn't enough.
        if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
        requestAnimationFrame(() => {
            const visibleCols = kanbanBoardContainer.querySelectorAll('.kanban-column-wrapper:not(.hidden)');
            if (visibleCols.length === 0) return;

            const containerWidth = kanbanBoardContainer.offsetWidth;
            const firstColStyle = getComputedStyle(visibleCols[0]);
            const colWidth = parseFloat(firstColStyle.width) + parseFloat(firstColStyle.marginLeft) + parseFloat(firstColStyle.marginRight);
            
            // This logic assumes all columns have similar width and margins.
            // More robust would be to sum up individual widths if they vary.
            const totalColsWidth = visibleCols.length * colWidth; 
            
            // If Tailwind's 'space-x-*' or 'gap-*' is used on the parent, direct width calculation is simpler.
            // Example: if parent is flex and has gap-4 (1rem), total width is sum of col widths + (N-1)*gap.
            
            // Simple centering logic (may need refinement based on actual CSS for spacing)
            kanbanBoardContainer.classList.toggle('justify-center', totalColsWidth < containerWidth);
            kanbanBoardContainer.classList.toggle('justify-start', totalColsWidth >= containerWidth);
        });
    }
    // --- End Kanban Specific Functions ---

    // --- List View Specific Functions ---
    function initializeListSort() {
        // ... (Client-side sorting logic from your JS) ...
        // This is kept as-is, but server-side sorting via URL parameters is generally more robust for larger datasets.
        // If your TaskListView in Django handles 'sort' URL param, this client-side sort might conflict or be redundant.
        // For now, assuming it's a desired client-side enhancement.
        if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
        const table = taskListContainer.querySelector('table'); if (!table) return;
        const headers = table.querySelectorAll('.sort-header'); // Ensure headers have this class and data-column attribute
        const tbody = table.querySelector('tbody'); if (!tbody || headers.length === 0) return;

        const savedCol = localStorage.getItem('taskListSortColumn');
        const savedOrder = localStorage.getItem('taskListSortOrder') || 'asc';

        const applySort = (columnName, order) => {
            const rows = Array.from(tbody.querySelectorAll('tr'));
            if (rows.length < 2) return;

            let colIndex = -1;
            headers.forEach((th, index) => {
                if (th.dataset.column === columnName) colIndex = index;
                th.querySelector('.fa-sort').className = 'fas fa-sort ml-1 text-gray-400 dark:text-gray-500';
                th.setAttribute('aria-sort', 'none');
            });

            if (colIndex === -1) return;

            const dataType = headers[colIndex].dataset.type || 'string';
            rows.sort((rowA, rowB) => {
                const cellAVal = rowA.cells[colIndex]?.dataset.sortValue || rowA.cells[colIndex]?.textContent.trim() || '';
                const cellBVal = rowB.cells[colIndex]?.dataset.sortValue || rowB.cells[colIndex]?.textContent.trim() || '';
                let comparison = 0;

                if (dataType === 'number') {
                    comparison = (parseFloat(cellAVal) || 0) - (parseFloat(cellBVal) || 0);
                } else if (dataType === 'date') { // Assumes YYYY-MM-DD or ISO format for dates in data-sort-value
                    const dateA = new Date(cellAVal);
                    const dateB = new Date(cellBVal);
                    comparison = dateA - dateB;
                } else {
                    comparison = cellAVal.localeCompare(cellBVal, undefined, { numeric: true, sensitivity: 'base' });
                }
                return order === 'asc' ? comparison : -comparison;
            });

            rows.forEach(row => tbody.appendChild(row));
            const activeHeader = headers[colIndex];
            activeHeader.setAttribute('aria-sort', order === 'asc' ? 'ascending' : 'descending');
            activeHeader.querySelector('.fa-sort').className = `fas ${order === 'asc' ? 'fa-sort-up' : 'fa-sort-down'} ml-1`;
            localStorage.setItem('taskListSortColumn', columnName);
            localStorage.setItem('taskListSortOrder', order);
        };

        headers.forEach(header => {
            header.addEventListener('click', function () {
                const currentColumn = this.dataset.column;
                const currentSort = this.getAttribute('aria-sort');
                applySort(currentColumn, (currentSort === 'ascending' ? 'desc' : 'asc'));
            });
            if (header.dataset.column === savedCol) { // Apply initial icon
                 header.setAttribute('aria-sort', savedOrder === 'asc' ? 'ascending' : 'descending');
                 header.querySelector('.fa-sort').className = `fas ${savedOrder === 'asc' ? 'fa-sort-up' : 'fa-sort-down'} ml-1`;
            }
        });

        if (savedCol) {
            setTimeout(() => applySort(savedCol, savedOrder), 50); // Small delay for DOM
        }
        console.log("List client-side sort initialized.");
    }

    function initializeListStatusChange() {
        // ... (Implementation from your provided JS, seems mostly fine) ...
        // Ensure .status-dropdown elements have data-task-id and data-previous-value attributes.
        if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
        const tbody = taskListContainer.querySelector('tbody'); if (!tbody) return;

        tbody.addEventListener('change', async function (event) {
            if (event.target.matches('.status-dropdown')) {
                const selectElement = event.target;
                const taskId = selectElement.dataset.taskId;
                const newStatus = selectElement.value;
                const previousStatus = selectElement.dataset.previousValue || ''; // Store previous value to revert on error

                if (!taskId || newStatus === previousStatus) { // No change or no task ID
                    if (newStatus !== previousStatus) selectElement.value = previousStatus; // Revert if no task ID but value changed
                    return;
                }
                
                console.log(`List status change initiated: Task ${taskId} from '${previousStatus}' to '${newStatus}'`);
                const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`;
                const row = selectElement.closest('tr');
                selectElement.disabled = true; // Prevent multiple submissions
                if (loadingIndicator) loadingIndicator.classList.remove('hidden');

                try {
                    const response = await window.authenticatedFetch(url, {
                        method: 'POST',
                        body: JSON.stringify({ status: newStatus }),
                        headers: { 'Content-Type': 'application/json' }
                    });

                    if (response.ok) {
                        const responseData = await response.json();
                        if (responseData.success) {
                            console.log(`List status update success for task ${taskId}. New status: ${responseData.new_status_key}`);
                            selectElement.dataset.previousValue = responseData.new_status_key; // Update stored previous value
                            if (row) updateStatusBadge(row, responseData.new_status_key); // Update visual badge
                            if (window.showNotification) showNotification(responseData.message || 'Статус задачи обновлен.', 'success');
                        } else {
                            console.warn(`List status update failed on server for task ${taskId}:`, responseData.message);
                            selectElement.value = previousStatus; // Revert dropdown on server error
                            if (window.showNotification) showNotification(responseData.message || 'Ошибка обновления статуса на сервере.', 'error');
                        }
                    } else {
                        const errorData = await response.json().catch(() => ({ message: `Server error: ${response.status}` }));
                        console.error(`List status update server error for task ${taskId}: ${response.status}`, errorData.message);
                        selectElement.value = previousStatus; // Revert dropdown
                        if (window.showNotification) showNotification(errorData.message || `Ошибка сервера: ${response.status}`, 'error');
                    }
                } catch (error) {
                    console.error(`List status update fetch/JS error for task ${taskId}:`, error);
                    selectElement.value = previousStatus; // Revert dropdown on network/JS error
                    if (window.showNotification) showNotification('Сетевая ошибка при обновлении статуса.', 'error');
                } finally {
                    selectElement.disabled = false;
                    if (loadingIndicator) loadingIndicator.classList.add('hidden');
                }
            }
        });
        // Initialize previous values for all dropdowns
        tbody.querySelectorAll('.status-dropdown').forEach(select => {
            select.dataset.previousValue = select.value;
        });
        console.log("List status change handlers initialized.");
    }
    // --- End List View Specific Functions ---

    // --- Delete Task Functions ---
    function setupDeleteTaskHandler(containerSelector) {
        const container = document.querySelector(containerSelector);
        if (!container) {
            // console.warn(`Delete handler: Container '${containerSelector}' not found.`);
            return;
        }
        container.addEventListener('click', async function (event) {
            const deleteButton = event.target.closest('button[data-action="delete-task"]');
            if (!deleteButton) return;

            event.preventDefault(); // Prevent default button action if any

            const taskId = deleteButton.dataset.taskId;
            const taskName = deleteButton.dataset.taskName || `ID ${taskId}`;
            const deleteUrl = deleteButton.dataset.deleteUrl; // This should be the URL to the TaskDeleteView

            if (!taskId || !deleteUrl) {
                console.error("Delete button missing data-task-id or data-delete-url.");
                if (window.showNotification) showNotification('Ошибка: Не удалось определить задачу для удаления.', 'error');
                return;
            }

            const result = await Swal.fire({
                title: `Удалить задачу "${escapeHtml(taskName)}"?`,
                text: "Это действие нельзя будет отменить!",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#EF4444', // Tailwind red-500
                cancelButtonColor: '#3B82F6',  // Tailwind blue-500
                confirmButtonText: 'Да, удалить!',
                cancelButtonText: 'Отмена',
                customClass: { // For Tailwind dark mode compatibility with SweetAlert2
                    popup: 'dark:bg-gray-800 dark:text-gray-200',
                    title: 'dark:text-gray-100',
                    htmlContainer: 'dark:text-gray-300',
                    confirmButton: 'bg-red-500 hover:bg-red-600 text-white font-bold py-2 px-4 rounded',
                    cancelButton: 'bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded ml-3'
                },
                buttonsStyling: false // Use customClass for styling buttons
            });

            if (result.isConfirmed) {
                console.log(`User confirmed deletion for task ${taskId}. Sending POST to ${deleteUrl}`);
                if (loadingIndicator) loadingIndicator.classList.remove('hidden');
                try {
                    // Django's DeleteView expects a POST request with CSRF token
                    // authenticatedFetch should handle CSRF
                    const response = await window.authenticatedFetch(deleteUrl, { method: 'POST' });

                    // DeleteView typically redirects on success (response.ok might be true, but status 200 if no explicit JSON returned)
                    // Or, it might return JSON if overridden. Check for redirect or specific success payload.
                    if (response.ok && response.redirected) { // Common case for DeleteView success
                        console.log(`Task ${taskId} deleted successfully (redirected).`);
                        removeTaskFromUI(taskId); // Remove from UI
                        if (window.showNotification) showNotification(`Задача "${escapeHtml(taskName)}" удалена.`, 'success');
                        // Optionally, redirect client-side if DeleteView doesn't for AJAX, or if you want to go to task list
                        // window.location.href = targetListUrl; // (targetListUrl needs to be defined)
                    } else if (response.ok) { // If DeleteView returns JSON
                        const responseData = await response.json().catch(() => ({ success: true, message: "Удалено (нет JSON ответа)"})); // Assume success if OK but no JSON
                        if (responseData.success !== false) { // Check for explicit success:false
                            console.log(`Task ${taskId} deleted (JSON response).`);
                            removeTaskFromUI(taskId);
                            if (window.showNotification) showNotification(responseData.message || `Задача "${escapeHtml(taskName)}" удалена.`, 'success');
                        } else {
                             console.warn(`Server indicated delete failure for task ${taskId}:`, responseData.message);
                            if (window.showNotification) showNotification(responseData.message || 'Не удалось удалить задачу на сервере.', 'error');
                        }
                    } else {
                        const errorText = await response.text();
                        console.error(`Server error during delete for task ${taskId}: ${response.status}`, errorText);
                        if (window.showNotification) showNotification(`Ошибка удаления: ${response.statusText || response.status}`, 'error');
                    }
                } catch (error) {
                    console.error(`Network/JS error during delete for task ${taskId}:`, error);
                    if (window.showNotification) showNotification('Сетевая ошибка при удалении задачи.', 'error');
                } finally {
                    if (loadingIndicator) loadingIndicator.classList.add('hidden');
                }
            }
        });
    }
    function initializeListDeleteButtons() { setupDeleteTaskHandler('#task-list'); }
    function initializeKanbanDeleteButtons() { setupDeleteTaskHandler('#kanban-board'); }
    // --- End Delete Task Functions ---

    // --- UI Update Functions (Shared) ---
    function updateTaskUI(taskId, newStatusKey) {
        console.log(`Attempting UI update for task ${taskId} to status ${newStatusKey}`);
        const taskElementKanban = kanbanBoardContainer.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
        const taskElementRow = taskListContainer.querySelector(`#task-row-${taskId}`);

        // 1. Update Kanban View (if visible and element exists)
        if (!kanbanBoardContainer.classList.contains('hidden') && taskElementKanban) {
            const currentColumn = taskElementKanban.closest('.kanban-column');
            const targetColumn = kanbanBoardContainer.querySelector(`.kanban-column[data-status="${newStatusKey}"]`);
            const targetTasksContainer = targetColumn?.querySelector('.kanban-tasks');

            if (targetTasksContainer && currentColumn?.dataset.status !== newStatusKey) {
                console.log(`Kanban: Moving task ${taskId} to column ${newStatusKey}`);
                targetTasksContainer.appendChild(taskElementKanban);
                taskElementKanban.dataset.status = newStatusKey;
                if (currentColumn) updateKanbanColumnUI(currentColumn);
                updateKanbanColumnUI(targetColumn);
            } else if (targetColumn) { // Already in correct column or target not found (e.g. hidden)
                taskElementKanban.dataset.status = newStatusKey; // Ensure data attribute is up-to-date
                updateKanbanColumnUI(targetColumn); // Update count for current column
            } else {
                console.warn(`Kanban: Target column for status ${newStatusKey} not found or task already there.`);
            }
        }

        // 2. Update List View (if visible and element exists)
        if (!taskListContainer.classList.contains('hidden') && taskElementRow) {
            const statusSelect = taskElementRow.querySelector('.status-dropdown');
            if (statusSelect && statusSelect.value !== newStatusKey) {
                statusSelect.value = newStatusKey;
                statusSelect.dataset.previousValue = newStatusKey; // Update for future direct changes
                console.log(`List: Updated status dropdown for task ${taskId} to ${newStatusKey}`);
            }
            updateStatusBadge(taskElementRow, newStatusKey); // Update the visual status badge
        }
    }

    function removeTaskFromUI(taskId) {
        console.log(`Removing task ${taskId} from UI`);
        const taskElementKanban = kanbanBoardContainer?.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
        const taskElementRow = taskListContainer?.querySelector(`#task-row-${taskId}`);
        
        if (taskElementKanban) {
            const sourceColumn = taskElementKanban.closest('.kanban-column');
            taskElementKanban.remove();
            if (sourceColumn) updateKanbanColumnUI(sourceColumn);
            console.log(`Removed task ${taskId} from Kanban.`);
        }
        if (taskElementRow) {
            taskElementRow.remove();
            console.log(`Removed task ${taskId} from List.`);
        }

        // Update pagination total count if displayed (simple example)
        const paginationTotalElement = document.querySelector('.pagination-total-count'); // Adjust selector
        if (paginationTotalElement) {
            let currentTotal = parseInt(paginationTotalElement.textContent, 10);
            if (!isNaN(currentTotal) && currentTotal > 0) {
                paginationTotalElement.textContent = currentTotal - 1;
            }
        }
    }

    function updateStatusBadge(tableRow, newStatusKey) {
        // ... (Implementation from your provided JS, ensure window.taskStatusChoices is populated) ...
        if (!tableRow) return;
        const badge = tableRow.querySelector('.status-badge'); // Ensure your list items have this
        const statusChoices = window.taskStatusChoices || []; // Should be populated from template
        const statusInfo = statusChoices.find(choice => choice[0] === newStatusKey);
        const statusDisplay = statusInfo ? statusInfo[1] : newStatusKey; // Text for the badge

        if (badge) {
            badge.textContent = statusDisplay;
            const statusColorClasses = { // Tailwind example classes
                'new': 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
                'in_progress': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
                'on_hold': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200',
                'completed': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
                'cancelled': 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400 line-through',
                'overdue': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
            };
            const defaultClasses = 'bg-gray-200 text-gray-700 dark:bg-gray-600 dark:text-gray-300';
            const newBadgeClasses = statusColorClasses[newStatusKey] || defaultClasses;
            // Base classes for all badges + specific color classes
            badge.className = `status-badge px-2 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full ${newBadgeClasses}`;
        }
        // Highlight overdue tasks in the list
        const deadlineCell = tableRow.querySelector('.task-deadline-cell'); // Add this class to your deadline TD
        if (deadlineCell) {
            const isOverdue = newStatusKey === 'overdue' || (newStatusKey !== 'completed' && newStatusKey !== 'cancelled' && deadlineCell.dataset.isOverdue === 'true');
            deadlineCell.classList.toggle('text-red-600', isOverdue);
            deadlineCell.classList.toggle('dark:text-red-400', isOverdue);
            deadlineCell.classList.toggle('font-semibold', isOverdue);
        }
    }
    // --- End UI Update Functions ---

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
    }
    // --- End Helpers ---

    // --- Initialization ---
    // window.taskStatusChoices should be populated by a script tag in your Django template
    // Example: <script id="status-choices-data" type="application/json">{{ status_choices_json_data|safe }}</script>
    // And then:
    // const statusChoicesElem = document.getElementById('status-choices-data');
    // window.taskStatusChoices = statusChoicesElem ? JSON.parse(statusChoicesElem.textContent || '[]') : [];
    // Ensure window.currentUserId and window.djangoWebsocketsEnabled are also set in the template.

    // Initial setup calls
    initializeViewSwitcher(); // Sets initial view and calls relevant sub-initializers
    initializeColumnToggler(); // For Kanban column visibility
    
    connectWebSocket(); // Connect WebSocket after other UI setup

    window.addEventListener('resize', debounce(adjustKanbanLayout, 250)); // Adjust Kanban on resize

    console.log("tasks.js (No Modal version for LIST VIEW) initialization complete.");
});