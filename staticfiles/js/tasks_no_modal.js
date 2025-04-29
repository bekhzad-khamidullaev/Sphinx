"use strict";

document.addEventListener('DOMContentLoaded', () => {
    console.log("Initializing tasks_no_modal.js...");

    // --- Global Elements & Config ---
    const taskListContainer = document.getElementById('task-list');
    const kanbanBoardContainer = document.getElementById('kanban-board');
    const taskDetailContainer = document.getElementById('task-detail-container'); // For detail page detection

    // Base URL for AJAX calls (Task List/Kanban specific)
    // Prefer Kanban URL if both exist, otherwise list, then fallback
    const ajaxTaskBaseUrl = kanbanBoardContainer?.dataset.ajaxBaseUrl
        || taskListContainer?.dataset.ajaxBaseUrl
        || '/core/ajax/tasks/'; // Adjust fallback if necessary

    // --- Global Helper Functions ---
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

    // --- Task List/Kanban Specific Logic ---
    if (taskListContainer && kanbanBoardContainer) {
        console.log("Task List/Kanban page detected. Initializing list/kanban features...");

        const toggleViewBtn = document.getElementById('toggleViewBtn');
        const toggleViewBtnMobile = document.getElementById('toggleViewBtnMobile');
        const columnToggleDropdown = document.getElementById('column-toggle-dropdown');
        const resetHiddenColumnsBtn = document.getElementById('resetHiddenColumnsBtn');
        const columnCheckboxes = document.querySelectorAll('.toggle-column-checkbox');

        // --- Task List/Kanban WebSocket ---
        let taskUpdateSocket = null;
        function connectTaskListWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            const wsPath = window.djangoWsPath || '/ws/task_updates/'; // General task updates endpoint
            const wsUrl = `${protocol}${window.location.host}${wsPath}`;
            console.log(`Connecting to Task List WebSocket: ${wsUrl}`);

            taskUpdateSocket = new WebSocket(wsUrl);
            taskUpdateSocket.onopen = () => {
                console.log('Task List WebSocket connection established.');
                window.wsRetryCount = 0; // Reset retry count on success
            };
            taskUpdateSocket.onmessage = handleTaskListWebSocketMessage;
            taskUpdateSocket.onerror = (error) => {
                console.error('Task List WebSocket error:', error);
                if (window.showNotification) showNotification('Ошибка соединения WebSocket', 'error');
            };
            taskUpdateSocket.onclose = (event) => {
                console.log('Task List WebSocket connection closed.', event.code, event.reason);
                // Exponential backoff retry only on abnormal closure
                if (!event.wasClean && event.code !== 1000) {
                    if (window.showNotification) showNotification('WebSocket отключен. Переподключение...', 'warning');
                    const retryDelay = Math.min(30000, (Math.pow(2, window.wsRetryCount || 0) * 1000) + Math.random() * 1000);
                    window.wsRetryCount = (window.wsRetryCount || 0) + 1;
                    console.log(`Retrying WS connection in ${retryDelay / 1000}s`);
                    setTimeout(connectTaskListWebSocket, retryDelay);
                } else {
                    window.wsRetryCount = 0; // Reset on clean close
                }
            };
        }

        function handleTaskListWebSocketMessage(event) {
            try {
                const data = JSON.parse(event.data);
                console.log('Task List WS message received:', data);
                const currentUserId = window.currentUserId || null;
                // Determine initiator ID from various possible keys
                const initiatorUserId = data.message?.updated_by_id || data.message?.created_by_id || data.message?.deleted_by_id;

                if (initiatorUserId && currentUserId && initiatorUserId === currentUserId) {
                    console.log(`Skipping self-initiated Task List WS update for task ${data.message?.task_id}`);
                    return;
                }

                // Process different event types for List/Kanban
                if (data.type === 'task_update' && data.message?.event === 'status_update') {
                    const msg = data.message;
                    if (window.showNotification) showNotification(`Статус задачи #${msg.task_id} обновлен на "${msg.status_display}" ${msg.updated_by || ''}`, 'info');
                    updateTaskUI(msg.task_id, msg.status);
                } else if (data.type === 'list_update' && data.message?.event === 'task_created') {
                    // Simple reload to show new task and ensure correct sorting/filtering
                    if (window.showNotification) showNotification(`Добавлена новая задача ${data.message.created_by || ''}. Обновление...`, 'success');
                    setTimeout(() => window.location.reload(), 1500);
                    // Alternate: Dynamic addition (more complex)
                    // addNewTaskToUI(data.message.task_html_list || null, data.message.task_html_kanban || null, data.message.status);
                } else if (data.type === 'list_update' && data.message?.event === 'task_deleted') {
                    removeTaskFromUI(data.message.task_id);
                    if (window.showNotification) showNotification(`Задача #${data.message.task_id} удалена ${data.message.deleted_by || ''}`, 'info');
                } else if (data.type === 'list_update' && data.message?.event === 'task_updated') {
                    // Simple reload to reflect full changes
                    if (window.showNotification) showNotification(`Задача #${data.message.task_id} обновлена ${data.message.updated_by || ''}. Обновление...`, 'info');
                    setTimeout(() => window.location.reload(), 1500);
                    // Alternate: Dynamic update (more complex)
                    // updateExistingTaskUI(data.message.task_id, data.message.task_html_list || null, data.message.task_html_kanban || null, data.message.status);
                } else if (data.type === 'error') {
                    console.error('WS error from list consumer:', data.message);
                    if (window.showNotification) showNotification(`Ошибка обновления: ${escapeHtml(data.message)}`, 'error');
                    if (data.task_id && data.original_status) {
                        updateTaskUI(data.task_id, data.original_status); // Revert UI
                    }
                } else { console.warn("Unknown Task List WS message:", data); }
            } catch (error) { console.error('Error processing Task List WS message:', error, "Data:", event.data); }
        }

        // --- View Switching Logic ---
        function initializeViewSwitcher() {
            const urlParams = new URLSearchParams(window.location.search);
            const viewParam = urlParams.get('view');
            const savedView = localStorage.getItem('taskView');
            const initialView = viewParam || savedView || 'kanban'; // Default to Kanban

            // Texts for buttons (consider using Django trans tags if rendering this JS in template)
            const kanbanText = toggleViewBtn?.dataset.kanbanText || "View: Kanban";
            const listText = toggleViewBtn?.dataset.listText || "View: List";
            const kanbanTextMobile = toggleViewBtnMobile?.dataset.kanbanText || "Kanban";
            const listTextMobile = toggleViewBtnMobile?.dataset.listText || "List";

            const updateButton = (btn, iconEl, textEl, view) => {
                if (!btn || !iconEl || !textEl) return;
                const isKanban = view === 'kanban';
                // Icon shows what you WILL switch TO
                iconEl.className = `fas ${isKanban ? 'fa-list' : 'fa-columns'} mr-2`;
                // Text shows the CURRENT view
                textEl.textContent = isKanban ? (btn === toggleViewBtnMobile ? kanbanTextMobile : kanbanText) : (btn === toggleViewBtnMobile ? listTextMobile : listText);
                // aria-pressed reflects the state (true if LIST is active)
                btn.setAttribute('aria-pressed', (!isKanban).toString());
            };

            const setView = (view) => {
                const isKanban = view === 'kanban';
                console.log(`Setting view to: ${view}`);
                kanbanBoardContainer.classList.toggle('hidden', !isKanban);
                taskListContainer.classList.toggle('hidden', isKanban);
                document.getElementById('pagination')?.classList.toggle('hidden', isKanban);
                columnToggleDropdown?.closest('.relative')?.classList.toggle('hidden', !isKanban); // Show column toggle only for Kanban

                // Update button states
                updateButton(toggleViewBtn, document.getElementById('viewIcon'), document.getElementById('viewText'), view);
                updateButton(toggleViewBtnMobile, document.getElementById('viewIconMobile'), document.getElementById('viewTextMobile'), view);

                localStorage.setItem('taskView', view); // Save preference

                // Initialize view-specific features
                if (isKanban) {
                    initializeKanban();
                    restoreHiddenColumns();
                    adjustKanbanLayout();
                } else {
                    initializeListSort();
                    initializeListStatusChange();
                    initializeListDeleteButtons();
                }

                // Update URL without reloading (optional)
                if (window.history.pushState) {
                    const newUrl = new URL(window.location);
                    newUrl.searchParams.set('view', view);
                    window.history.pushState({ path: newUrl.href }, '', newUrl.href);
                }
            };

            setView(initialView); // Set initial view on load

            // Add event listeners to buttons
            [toggleViewBtn, toggleViewBtnMobile].forEach(btn => {
                if (btn) {
                    btn.addEventListener('click', () => {
                        const currentView = localStorage.getItem('taskView') || 'kanban';
                        setView(currentView === 'kanban' ? 'list' : 'kanban');
                    });
                }
            });
        }

        // --- Kanban Specific Functions ---
        let sortableInstances = [];
        function initializeKanban() {
            if (!window.Sortable || kanbanBoardContainer.classList.contains('hidden')) return;
            sortableInstances.forEach(instance => instance.destroy()); // Clear previous instances
            sortableInstances = [];
            console.log("Initializing Kanban board...");
            const columns = kanbanBoardContainer.querySelectorAll('.kanban-tasks');
            if (columns.length === 0) return;

            columns.forEach(column => {
                const instance = new Sortable(column, {
                    group: 'kanban-tasks', animation: 150, ghostClass: 'kanban-ghost',
                    dragClass: 'kanban-dragging', forceFallback: true, fallbackOnBody: true, swapThreshold: 0.65,
                    onStart: (evt) => {
                        kanbanBoardContainer.querySelectorAll('.kanban-column').forEach(col => col.classList.add('kanban-drag-active-zone'));
                        evt.item.classList.add('shadow-xl', 'scale-105', 'opacity-90');
                    },
                    onEnd: async (evt) => {
                        // Remove visual effects
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

                        // Update column counts/messages optimistically
                        updateKanbanColumnUI(sourceColumnElement);
                        updateKanbanColumnUI(targetColumnElement);

                        if (!taskId || !newStatus || !targetColumnElement || oldStatus === newStatus) {
                            if (oldStatus !== newStatus) { // Revert only if status was intended to change but failed
                                console.error("Kanban drop error: Missing data or same status.");
                                sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]);
                                updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement);
                            }
                            return;
                        }

                        console.log(`Task ${taskId} moved from '${oldStatus}' to '${newStatus}'. Sending update...`);
                        const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`;

                        try {
                            // Assuming authenticatedFetch handles CSRF and JSON automatically
                            const response = await window.authenticatedFetch(url, { method: 'POST', body: { status: newStatus } });

                            if (response.ok) {
                                const responseData = await response.json();
                                if (responseData.success) {
                                    taskElement.dataset.status = responseData.new_status_key; // Update data attr
                                    if (window.showNotification) showNotification(responseData.message || `Статус #${taskId} обновлен.`, 'success');
                                    // Also update the list view if it exists (for consistency)
                                    updateTaskUIInList(taskId, responseData.new_status_key);
                                } else {
                                    throw new Error(responseData.message || 'Server indicated failure.');
                                }
                            } else {
                                // authenticatedFetch should show error notification
                                throw new Error(`Server error ${response.status}`);
                            }
                        } catch (error) {
                            console.error(`Failed status update for task ${taskId}:`, error);
                            // Notification shown by authenticatedFetch or here
                            if (window.showNotification && !error.handled) showNotification(`Ошибка обновления #${taskId}: ${error.message}`, 'error');
                            // Revert Kanban UI
                            sourceTasksContainer.insertBefore(taskElement, sourceTasksContainer.children[evt.oldDraggableIndex]);
                            updateKanbanColumnUI(sourceColumnElement); updateKanbanColumnUI(targetColumnElement);
                        }
                    }
                });
                sortableInstances.push(instance);
            });
            initializeKanbanDeleteButtons(); // Ensure delete buttons work on initial load/re-init
            console.log(`Kanban initialized for ${columns.length} columns.`);
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
            // No need to call adjustKanbanLayout here if it does nothing
        };

        function initializeColumnToggler() {
            if (!columnToggleDropdown || !resetHiddenColumnsBtn || !columnCheckboxes.length) return;
            const saveHiddenColumns = () => {
                const hidden = Array.from(columnCheckboxes)
                    .filter(cb => !cb.checked)
                    .map(cb => cb.dataset.status);
                localStorage.setItem('hiddenKanbanColumns', JSON.stringify(hidden));
            };
            columnCheckboxes.forEach(checkbox => {
                checkbox.addEventListener('change', function () {
                    updateColumnVisibility(this.dataset.status, this.checked);
                    saveHiddenColumns();
                    // adjustKanbanLayout(); // Call if needed
                });
            });
            resetHiddenColumnsBtn.addEventListener('click', () => {
                columnCheckboxes.forEach(cb => {
                    cb.checked = true;
                    updateColumnVisibility(cb.dataset.status, true);
                });
                saveHiddenColumns(); // Save empty array
                // adjustKanbanLayout(); // Call if needed
            });
        }

        function restoreHiddenColumns() {
            if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
            const hiddenStatuses = JSON.parse(localStorage.getItem('hiddenKanbanColumns') || '[]');
            console.log('Restoring hidden columns:', hiddenStatuses);
            // Ensure all are visible first
            kanbanBoardContainer.querySelectorAll('.kanban-column-wrapper').forEach(wrapper => wrapper.classList.remove('hidden'));
            columnCheckboxes.forEach(cb => cb.checked = true);
            // Hide the stored ones
            hiddenStatuses.forEach(status => {
                updateColumnVisibility(status, false);
                const checkbox = kanbanBoardContainer.querySelector(`.toggle-column-checkbox[data-status="${status}"]`);
                if (checkbox) checkbox.checked = false;
            });
            // adjustKanbanLayout(); // Call if needed
        }

        function adjustKanbanLayout() {
            // Placeholder for potential future logic (e.g., dynamic width)
            console.log("Adjusting Kanban layout (placeholder)...");
        }

        // --- List Specific Functions ---
        function initializeListSort() {
            if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
            const table = taskListContainer.querySelector('table'); if (!table) return;
            const headers = table.querySelectorAll('.sort-header');
            const tbody = table.querySelector('tbody'); if (!tbody || headers.length === 0) return;

            // Add sort indicators based on current URL param
            const urlParams = new URLSearchParams(window.location.search);
            const currentSort = urlParams.get('sort');
            headers.forEach(header => {
                const column = header.dataset.column;
                const icon = header.querySelector('.fa-sort');
                if (!icon) return;
                header.classList.remove('sorted-asc', 'sorted-desc'); // Reset
                icon.className = 'fas fa-sort ml-1 text-gray-400 dark:text-gray-500 opacity-50'; // Reset icon
                if (currentSort === column) {
                    icon.className = 'fas fa-sort-up ml-1';
                    header.classList.add('sorted-asc');
                    header.setAttribute('aria-sort', 'ascending');
                } else if (currentSort === `-${column}`) {
                    icon.className = 'fas fa-sort-down ml-1';
                    header.classList.add('sorted-desc');
                    header.setAttribute('aria-sort', 'descending');
                } else {
                    header.setAttribute('aria-sort', 'none');
                }
            });


            headers.forEach(header => {
                header.addEventListener('click', () => {
                    const column = header.dataset.column;
                    if (!column) return;
                    const currentUrl = new URL(window.location);
                    const currentSortParam = currentUrl.searchParams.get('sort');
                    let newSort = column;
                    if (currentSortParam === column) newSort = `-${column}`;
                    else if (currentSortParam === `-${column}`) newSort = column; // Cycle or remove: currentUrl.searchParams.delete('sort');
                    currentUrl.searchParams.set('sort', newSort);
                    currentUrl.searchParams.set('view', 'list'); // Ensure list view remains
                    window.location.href = currentUrl.toString(); // Reload page
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

                    if (!taskId || newStatus === previousStatus) return;

                    console.log(`List status change: Task ${taskId} to ${newStatus}`);
                    const url = `${ajaxTaskBaseUrl}${taskId}/update-status/`;
                    selectElement.disabled = true;

                    try {
                        const response = await window.authenticatedFetch(url, { method: 'POST', body: { status: newStatus } });
                        if (response.ok) {
                            const responseData = await response.json();
                            if (responseData.success) {
                                selectElement.dataset.previousValue = newStatus;
                                updateStatusBadge(selectElement.closest('tr'), responseData.new_status_key);
                                if (window.showNotification) showNotification(responseData.message || 'Статус обновлен.', 'success');
                                // Update Kanban if visible
                                updateTaskUIInKanban(taskId, responseData.new_status_key);
                            } else { throw new Error(responseData.message || 'Update failed'); }
                        } else { throw new Error(`Server error ${response.status}`); }
                    } catch (error) {
                        console.error(`List status update failed for task ${taskId}:`, error);
                        if (window.showNotification && !error.handled) showNotification(`Ошибка обновления #${taskId}: ${error.message}`, 'error');
                        selectElement.value = previousStatus; // Revert dropdown
                    } finally {
                        selectElement.disabled = false;
                    }
                }
            });

            // Store initial value on load
            tbody.querySelectorAll('.status-dropdown').forEach(select => {
                select.dataset.previousValue = select.value;
            });
        }

        // --- Delete Handling ---
        function setupDeleteTaskHandler(containerSelector) {
            const container = document.querySelector(containerSelector); if (!container) return;
            container.addEventListener('click', async function (event) {
                const deleteButton = event.target.closest('button[data-action="delete-task"]');
                if (!deleteButton) return;

                const taskId = deleteButton.dataset.taskId;
                const taskName = deleteButton.dataset.taskName || `ID ${taskId}`;
                const deleteUrl = deleteButton.dataset.deleteUrl;

                if (!taskId || !deleteUrl) { /* ... error handling ... */ return; }

                // Use SweetAlert2 or fallback confirm
                let confirmed = false;
                if (typeof Swal !== 'undefined') {
                    const result = await Swal.fire({ /* ... SweetAlert options ... */ });
                    confirmed = result.isConfirmed;
                } else {
                    confirmed = confirm(`Вы уверены, что хотите удалить задачу "${taskName}"?`);
                }

                if (confirmed) {
                    console.log(`Attempting to delete task ${taskId} via ${deleteUrl}`);
                    try {
                        // Use POST for deletion as recommended by DRF/Django best practices often
                        const response = await window.authenticatedFetch(deleteUrl, { method: 'POST' }); // Or 'DELETE' if backend expects it

                        if (response.ok) {
                            const responseData = await response.json().catch(() => ({})); // Handle empty response possibility
                            if (responseData.success !== false) {
                                console.log(`Task ${taskId} deleted successfully.`);
                                removeTaskFromUI(taskId);
                                if (window.showNotification) showNotification(responseData.message || `Задача "${taskName}" удалена.`, 'success');
                            } else { throw new Error(responseData.message || 'Server indicated delete failure.'); }
                        } else { throw new Error(`Server error: ${response.status}`); }
                    } catch (error) {
                        console.error(`Failed to delete task ${taskId}:`, error);
                        if (window.showNotification && !error.handled) showNotification(`Ошибка удаления "${taskName}": ${error.message}`, 'error');
                    }
                }
            });
        }
        function initializeListDeleteButtons() { setupDeleteTaskHandler('#task-list'); }
        function initializeKanbanDeleteButtons() { setupDeleteTaskHandler('#kanban-board'); }

        // --- UI Update Functions ---
        function updateTaskUI(taskId, newStatus) {
            console.log(`Updating UI for task ${taskId} to status ${newStatus}`);
            updateTaskUIInKanban(taskId, newStatus);
            updateTaskUIInList(taskId, newStatus);
        }

        function updateTaskUIInKanban(taskId, newStatus) {
            if (!kanbanBoardContainer || kanbanBoardContainer.classList.contains('hidden')) return;
            const taskElementKanban = kanbanBoardContainer.querySelector(`.kanban-task[data-task-id="${taskId}"]`);
            if (!taskElementKanban) return;

            const currentStatus = taskElementKanban.dataset.status;
            if (currentStatus !== newStatus) {
                const targetColumn = kanbanBoardContainer.querySelector(`.kanban-tasks[data-status="${newStatus}"]`);
                const sourceColumnEl = taskElementKanban.closest('.kanban-column'); // Get column element
                const targetColumnEl = targetColumn?.closest('.kanban-column');

                if (targetColumn) {
                    console.log(`Moving Kanban task ${taskId} to column ${newStatus}`);
                    targetColumn.appendChild(taskElementKanban);
                    taskElementKanban.dataset.status = newStatus;
                    updateKanbanColumnUI(sourceColumnEl);
                    updateKanbanColumnUI(targetColumnEl);
                } else {
                    console.warn(`Target Kanban column for status ${newStatus} not found.`);
                }
            }
        }

        function updateTaskUIInList(taskId, newStatus) {
            if (!taskListContainer || taskListContainer.classList.contains('hidden')) return;
            const taskElementRow = taskListContainer.querySelector(`#task-row-${taskId}`);
            if (taskElementRow) {
                const dropdown = taskElementRow.querySelector('.status-dropdown');
                if (dropdown) {
                    dropdown.value = newStatus;
                    dropdown.dataset.previousValue = newStatus; // Update stored value
                }
                updateStatusBadge(taskElementRow, newStatus);
            }
        }

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
                // Check if tbody is empty after removal
                const tbody = taskListContainer?.querySelector('tbody');
                if (tbody && !tbody.querySelector('tr')) {
                    // Optionally add the "No tasks found" row back
                    const colCount = taskListContainer.querySelector('thead th')?.colSpan || 8; // Get colspan or default
                    tbody.innerHTML = `<tr><td colspan="${colCount}" class="px-6 py-12 text-center ...">... No tasks message ...</td></tr>`;
                }
            }
        }

        function updateStatusBadge(tableRow, newStatusKey) {
            if (!tableRow) return;
            const badge = tableRow.querySelector('.status-badge');
            if (!badge) return;
            const statusMap = window.taskStatusMapping || {};
            const statusDisplay = statusMap[newStatusKey]?.display || newStatusKey; // Use display name from map

            // Reset classes and apply new ones based on status
            badge.textContent = statusDisplay;
            const baseClasses = "status-badge px-2 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full";
            let newClasses = baseClasses;

            // Apply status-specific classes (ensure these match template)
            switch (newStatusKey) {
                case 'new': newClasses += ' bg-gray-100 text-gray-800 dark:bg-dark-600 dark:text-gray-200'; break;
                case 'in_progress': newClasses += ' bg-yellow-100 text-yellow-800 dark:bg-yellow-900/60 dark:text-yellow-200'; break;
                case 'on_hold': newClasses += ' bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-200'; break;
                case 'completed': newClasses += ' bg-green-100 text-green-800 dark:bg-green-900/60 dark:text-green-200'; break;
                case 'canceled': newClasses += ' bg-gray-100 text-gray-500 dark:bg-dark-700 dark:text-gray-400 line-through'; break;
                case 'overdue': newClasses += ' bg-red-100 text-red-800 dark:bg-red-900/60 dark:text-red-200'; break;
                default: newClasses += ' bg-gray-100 text-gray-800 dark:bg-dark-600 dark:text-gray-200'; break;
            }
            badge.className = newClasses;
        }

        // --- Fetch and Store Status Mapping ---
        window.taskStatusMapping = {};
        try {
            const statusMappingElement = document.getElementById('status-mapping-data');
            if (statusMappingElement) {
                window.taskStatusMapping = JSON.parse(statusMappingElement.textContent);
                console.log("Loaded status mapping:", window.taskStatusMapping);
            } else {
                console.error("Status mapping data script tag (#status-mapping-data) not found.");
            }
        } catch (e) { console.error("Error parsing status mapping data:", e); }


        // --- Initializations for Task List/Kanban ---
        if (ajaxTaskBaseUrl !== '/core/ajax/tasks/') { // Basic check if base URL seems valid
            initializeViewSwitcher(); // Runs first, calls view-specific inits
            initializeColumnToggler();
            connectTaskListWebSocket(); // Start general task WebSocket
            window.addEventListener('resize', debounce(adjustKanbanLayout, 250));
            console.log("Task List/Kanban features initialized.");
        } else {
            console.error("Cannot initialize Task List/Kanban features due to missing AJAX base URL.");
        }

    } // --- END Task List/Kanban Specific Logic ---


    // --- TASK DETAIL PAGE SPECIFIC LOGIC ---
    if (taskDetailContainer) {
        console.log("Task Detail page detected. Initializing comment features...");

        // --- Read Data from HTML ---
        let taskDetailData = {};
        try {
            const dataElement = document.getElementById('task-detail-data');
            if (!dataElement) throw new Error("Task detail data script tag (#task-detail-data) not found.");
            taskDetailData = JSON.parse(dataElement.textContent);
            if (!taskDetailData.taskId) throw new Error("Task ID missing from task detail data.");
            if (!taskDetailData.translations) throw new Error("Translations missing from task detail data.");
            console.log("Task Detail Data:", taskDetailData);
        } catch (e) {
            console.error("Error reading or parsing task detail data:", e);
            return; // Stop detail page JS initialization if data is broken
        }

        // --- Comment Elements ---
        const commentList = document.getElementById('comment-list');
        const noCommentsMessage = document.getElementById('no-comments-message');
        const commentForm = document.getElementById('comment-form');
        const commentTextArea = commentForm?.querySelector('textarea[name="text"]');
        const commentSubmitButton = commentForm?.querySelector('button[type="submit"]');
        const commentTextErrors = document.getElementById('comment-text-errors');
        const commentNonFieldErrors = document.getElementById('comment-non-field-errors');
        const commentCountSpan = document.getElementById('comment-count');

        // Check essential comment elements
        if (!commentList || !commentForm || !commentTextArea || !commentSubmitButton) {
            console.warn('Comment elements (list, form, textarea, button) not all found. Comment features disabled.');
        } else {

            // --- Comment Helper Functions ---
            function formatRelativeTime(isoDateString) {
                const T = taskDetailData.translations;
                try {
                    const date = new Date(isoDateString);
                    const now = new Date();
                    if (isNaN(date)) { console.error("Invalid date from:", isoDateString); return isoDateString; }
                    const seconds = Math.round((now - date) / 1000);
                    const minutes = Math.round(seconds / 60);
                    const hours = Math.round(minutes / 60);
                    const days = Math.round(hours / 24);
                    const currentLocale = document.documentElement.lang || 'ru-RU';

                    if (seconds < 5) return T.justNow || "just now";
                    if (seconds < 60) return `${seconds} ${T.secondsAgo || "sec. ago"}`;
                    if (minutes < 60) return `${minutes} ${T.minutesAgo || "min. ago"}`;
                    if (hours < 24) return `${hours} ${T.hoursAgo || "hr ago"}`;
                    if (days === 1) return T.yesterday || "yesterday";
                    if (days < 7) return `${days} ${T.daysAgo || "days ago"}`;
                    return date.toLocaleDateString(currentLocale, { day: '2-digit', month: '2-digit', year: 'numeric' });
                } catch (e) { console.error("Error formatting date:", isoDateString, e); return isoDateString; }
            }

            function addCommentToDOM(comment) {
                const T = taskDetailData.translations;
                if (!comment?.author || typeof comment.text !== 'string' || !comment.id || !comment.created_at_iso) { console.error("Invalid comment data received:", comment); return; }
                if (noCommentsMessage) noCommentsMessage.classList.add('hidden');
                const commentElement = document.createElement('div');
                commentElement.className = 'flex space-x-3 comment-item animate-fade-in';
                commentElement.id = `comment-${comment.id}`;
                const avatarUrl = comment.author.avatar_url || taskDetailData.defaultAvatarUrl || '/static/img/user.svg';
                const authorName = escapeHtml(comment.author.name || T.unknownUser || 'Unknown');
                const commentTextHtml = escapeHtml(comment.text).replace(/\n/g, '<br>');
                const timeAgo = formatRelativeTime(comment.created_at_iso);
                const fullTime = new Date(comment.created_at_iso).toLocaleString();
                // Reconstruct innerHTML based on task_detail.html structure
                commentElement.innerHTML = `
                    <img class="w-8 h-8 rounded-full object-cover flex-shrink-0 mt-1" src="${avatarUrl}" alt="${authorName}">
                    <div class="flex-1 bg-gray-50 dark:bg-dark-700 p-3 rounded-lg border border-gray-100 dark:border-dark-600">
                        <div class="flex justify-between items-center mb-1">
                            <span class="text-sm font-semibold text-gray-800 dark:text-gray-200">${authorName}</span>
                            <span class="text-xs text-gray-400 dark:text-gray-500" title="${fullTime}">${timeAgo}</span>
                        </div>
                        <p class="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">${commentTextHtml}</p>
                    </div>`;
                commentList.appendChild(commentElement);
                commentList.scrollTop = commentList.scrollHeight;
                if (commentCountSpan) {
                    try {
                        let count = parseInt(commentCountSpan.textContent.match(/\d+/)?.[0] || '0', 10);
                        commentCountSpan.textContent = `(${(count || 0) + 1})`;
                    } catch (e) { console.warn("Could not update comment count.", e); }
                }
            }

            // --- Comment WebSocket Connection ---
            let commentSocket = null;
            function connectCommentWebSocket() {
                const taskId = taskDetailData.taskId;
                const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
                const wsUrl = `${protocol}${window.location.host}/ws/tasks/${taskId}/comments/`;
                console.log(`Connecting to Task Comments WebSocket: ${wsUrl}`);
                try {
                    commentSocket = new WebSocket(wsUrl);
                    commentSocket.onopen = () => console.log('Task Comments WS connected.');
                    commentSocket.onerror = (error) => console.error('Task Comments WS error:', error);
                    commentSocket.onclose = (event) => { console.log('Task Comments WS closed.', event.code); /* Optional: Reconnect */ };
                    commentSocket.onmessage = handleCommentWebSocketMessage;
                } catch (e) { console.error("Failed to create Comment WebSocket:", e); }
            }

            function handleCommentWebSocketMessage(event) {
                const T = taskDetailData.translations;
                try {
                    const data = JSON.parse(event.data);
                    console.log('Comment WS message received:', data);
                    if (data.type === 'new_comment' && data.comment) {
                        // Compare username from WS data with username from template context
                        if (!data.comment.author || data.comment.author.name !== taskDetailData.currentUsername) {
                            addCommentToDOM(data.comment);
                            if (window.showNotification) {
                                const author = escapeHtml(data.comment.author.name || T.unknownUser);
                                showNotification(`${T.newCommentNotification} ${author}`, 'info');
                            }
                        } else { console.log("Skipping own comment received via WS."); }
                    } else if (data.type === 'error') {
                        console.error("Error message via Comment WS:", data.message);
                        if (window.showNotification) showNotification(`${T.websocketError} ${escapeHtml(data.message)}`, 'error');
                    }
                } catch (e) { console.error('Error processing comment WS message:', e, 'Data:', event.data); }
            }

            // --- Comment AJAX Form Submission ---
            commentForm.addEventListener('submit', async function (e) {
                e.preventDefault();
                const T = taskDetailData.translations;
                const commentText = commentTextArea.value.trim();
                if (!commentText) {
                    if (commentTextErrors) commentTextErrors.textContent = T.commentCannotBeEmpty;
                    commentTextArea.classList.add('border-red-500', 'dark:border-red-500');
                    commentTextArea.focus(); return;
                }
                if (commentTextErrors) commentTextErrors.textContent = '';
                if (commentNonFieldErrors) commentNonFieldErrors.textContent = '';
                commentTextArea.classList.remove('border-red-500', 'dark:border-red-500');

                commentTextArea.disabled = true;
                commentSubmitButton.disabled = true;
                const originalButtonHtml = commentSubmitButton.innerHTML;
                commentSubmitButton.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i> ${T.sending}`;

                try {
                    const formData = new FormData(commentForm);
                    const csrfToken = commentForm.querySelector('[name=csrfmiddlewaretoken]')?.value;
                    if (!csrfToken) throw new Error("CSRF token not found!");

                    // Use authenticatedFetch if available, otherwise standard fetch
                    const fetchFunc = window.authenticatedFetch || fetch;
                    const response = await fetchFunc(commentForm.action, {
                        method: 'POST',
                        body: formData,
                        headers: { // authenticatedFetch might add CSRF automatically
                            'X-CSRFToken': csrfToken,
                            'X-Requested-With': 'XMLHttpRequest',
                            'Accept': 'application/json'
                        }
                    });

                    let responseData;
                    try { responseData = await response.json(); }
                    catch (e) { throw new Error(`Server error (${response.status}). Invalid JSON response.`); }

                    if (response.ok && responseData.success && responseData.comment) {
                        addCommentToDOM(responseData.comment);
                        commentTextArea.value = '';
                        if (window.showNotification) showNotification(T.commentAdded, 'success');
                    } else {
                        let errorMsg = responseData.error || T.submitError;
                        if (responseData.errors) {
                            const fieldErrors = Object.entries(responseData.errors)
                                .map(([field, errors]) => `${field}: ${errors.join(', ')}`)
                                .join('; ');
                            errorMsg += ` Details: ${fieldErrors}`;
                            if (responseData.errors.text && commentTextErrors) {
                                commentTextErrors.textContent = responseData.errors.text.join(' ');
                                commentTextArea.classList.add('border-red-500', 'dark:border-red-500');
                            }
                            if (responseData.errors.__all__ && commentNonFieldErrors) {
                                commentNonFieldErrors.textContent = responseData.errors.__all__.join(' ');
                            }
                        }
                        throw new Error(errorMsg); // Throw error to be caught below
                    }
                } catch (error) {
                    console.error('Error submitting comment:', error);
                    const displayError = error instanceof Error ? error.message : T.networkError;
                    if (commentNonFieldErrors && !commentNonFieldErrors.textContent && !commentTextErrors?.textContent) {
                        commentNonFieldErrors.textContent = displayError;
                    }
                    if (window.showNotification && !error.handled) showNotification(displayError, 'error'); // Avoid double notification if authenticatedFetch handled it
                } finally {
                    commentTextArea.disabled = false;
                    commentSubmitButton.disabled = false;
                    commentSubmitButton.innerHTML = originalButtonHtml;
                }
            });

            // --- Initial Connection (Comments) ---
            connectCommentWebSocket();

        } // End if(commentElementsFound)

    } // --- END TASK DETAIL PAGE SPECIFIC LOGIC ---

    console.log("tasks_no_modal.js initialization complete.");

}); // End DOMContentLoaded