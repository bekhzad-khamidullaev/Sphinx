// static/js/app_utils.js

// Utility function to close the modal
function closeModal() {
    const modal = document.getElementById("modal");
    if (modal) {
        modal.classList.add("hidden");
        const modalContent = document.getElementById("modal-content");
        if (modalContent) {
            modalContent.innerHTML = ''; // Clear modal content
        }
    }
}

// Utility function to open the modal
function openModal() {
    const modal = document.getElementById("modal");
    if (modal) {
        modal.classList.remove("hidden");
    }
}

// DOMContentLoaded ensures all HTML is loaded before running JS
document.addEventListener('DOMContentLoaded', function () {

    // --- Sidebar Toggle ---
    const sideBar = document.getElementById('sideBar');
    const sideBarOpenBtn = document.getElementById('sideBarOpenBtn');
    const sideBarCloseBtn = document.getElementById('sideBarCloseBtn');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');

    // Only add event listeners if elements exist
    if (sideBarOpenBtn && sideBarCloseBtn && sidebarBackdrop) {
        sideBarOpenBtn.addEventListener('click', () => {
            sideBar.classList.remove('-translate-x-full');
            sidebarBackdrop.classList.remove('hidden');
        });

        sideBarCloseBtn.addEventListener('click', () => {
            sideBar.classList.add('-translate-x-full');
            sidebarBackdrop.classList.add('hidden');
        });

        sidebarBackdrop.addEventListener('click', () => {
            closeSidebar(); // Reuse closeSidebar function
        });

        function closeSidebar() {
            sideBar.classList.add('-translate-x-full');
            sidebarBackdrop.classList.add('hidden');
        }
    }

    // --- HTMX Modal Handling ---
    // Use event delegation to handle dynamically added content.
    document.body.addEventListener('htmx:afterSwap', function (event) {
        if (event.detail.target.id === "modal-content") {
            openModal(); // Open the modal *after* content is swapped in
        }
    });

     // --- WebSocket for General Task Notifications (if needed) ---
     const socket = new WebSocket('ws://' + window.location.host + '/ws/tasks/'); // For general task updates
     socket.onmessage = function (e) {
         const data = JSON.parse(e.data);
         if (data.message) {
            // Assuming data.message contains a simple string. Adapt as needed.
            showNotification(data.message);  // Show a notification (you'll need to define this function)
         }
     };
     // --- Helper function for displaying notifications ---
    function showNotification(message) {
        const notification = document.createElement('div');
        notification.classList.add('notification');  // Add a class for styling
        notification.textContent = message;
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 5000); // Remove after 5 seconds

        // Optionally play a sound (make sure you have notification.mp3)
        // const sound = new Audio('/static/sounds/notification.mp3');
        // sound.play();
    }

    // --- Task List and Kanban Board Logic ---
    const taskList = document.getElementById('task-list');
    const kanbanBoard = document.getElementById('kanban-board');
    const toggleViewBtn = document.getElementById('toggleViewBtn');

    // --- View Toggle (List/Kanban) ---
    let savedView = localStorage.getItem('taskView') || 'list'; // Default to list view

    const setView = (view) => {
        if (view === 'list') {
            taskList.classList.remove('hidden');
            kanbanBoard.classList.add('hidden');
        } else {
            taskList.classList.add('hidden');
            kanbanBoard.classList.remove('hidden');
        }
        localStorage.setItem('taskView', view);
        if (toggleViewBtn) { // Make sure toggleViewBtn exists
            toggleViewBtn.setAttribute('aria-pressed', view === 'kanban' ? 'true' : 'false');
        }
    };

    setView(savedView); // Initial view setup

    if (toggleViewBtn) {
        toggleViewBtn.addEventListener('click', function () {
            setView(savedView === 'list' ? 'kanban' : 'list'); // Toggle the view
            savedView = localStorage.getItem('taskView'); // update the savedView
        });
    }

    // --- Table Sorting ---
    const sortHeaders = document.querySelectorAll('.sort-header');
    if(sortHeaders.length > 0){
        sortHeaders.forEach(header => {
            header.addEventListener('click', function () {
                const tableBody = document.querySelector('#task-list tbody');
                if (!tableBody) return; // IMPORTANT: Check if tbody exists

                const rows = Array.from(tableBody.querySelectorAll('tr'));
                const columnIndex = this.cellIndex;
                const order = this.dataset.order = -(this.dataset.order || -1); // Toggle order

                rows.sort((rowA, rowB) => {
                    const cellA = rowA.cells[columnIndex].textContent.trim();
                    const cellB = rowB.cells[columnIndex].textContent.trim();
                    return order * cellA.localeCompare(cellB, undefined, { numeric: true, sensitivity: 'base' });
                });

                rows.forEach(row => tableBody.appendChild(row));

                // Update aria-sort attributes
                document.querySelectorAll('.sort-header').forEach(th => {
                    th.setAttribute('aria-sort', th === this ? (order === 1 ? 'ascending' : 'descending') : 'none');
                });
            });
        });
    }


    // --- WebSocket for Status Updates ---
    const updates_socket = new WebSocket('ws://' + window.location.host + '/ws/task_updates/');

    updates_socket.onopen = function () {
        console.log('WebSocket connection established (task_updates).');
    };

    // Find status dropdowns *only within the task list*.  This is crucial.
    const statusDropdowns = taskList ? taskList.querySelectorAll('.status-dropdown') : [];
    statusDropdowns.forEach(select => {
        select.addEventListener('change', function () {
            const taskId = this.closest('tr').id.replace('task-', '');
            const newStatus = this.value;

            if (!newStatus) {
                alert("Please select a status."); // Use a simple alert, or a better notification method.
                return;
            }

            updates_socket.send(JSON.stringify({
                type: 'status_update',
                task_id: taskId,
                status: newStatus
            }));
        });
    });

    updates_socket.onmessage = function (event) {
        const data = JSON.parse(event.data);
        if (data.type === 'status_update' && data.success) {
            const taskRow = document.getElementById('task-' + data.task_id);
            if (taskRow) {
                const dropdown = taskRow.querySelector('.status-dropdown');
                if (dropdown) {
                    dropdown.value = data.new_status;
                }
            }

            // If kanban board is visible, reload (for now - can be optimized)
            if (kanbanBoard && !kanbanBoard.classList.contains('hidden')) {
                window.location.reload(); // Simplest way to update.  Could be optimized.
            }
        }
    };

    updates_socket.onerror = function (error) {
        console.error('WebSocket error: ', error);
    };
    updates_socket.onclose = function () {
        console.log('WebSocket connection closed (task_updates).');
    };


    // --- Kanban Board Drag & Drop ---
    if (kanbanBoard) { // Only run if kanban board exists
        let draggedTask = null;

        const kanbanTasks = document.querySelectorAll('.kanban-task');
        kanbanTasks.forEach(task => {
            task.draggable = true; // Make tasks draggable

            task.addEventListener('dragstart', function (e) {
                draggedTask = this;
                setTimeout(() => this.classList.add('opacity-50'), 0); // Visual feedback
                e.dataTransfer.effectAllowed = 'move'; // Specify drag effect
            });

            task.addEventListener('dragend', function () {
                this.classList.remove('opacity-50');
                draggedTask = null;
            });
        });

        const kanbanColumns = document.querySelectorAll('.kanban-column');
        kanbanColumns.forEach(column => {
            column.addEventListener('dragover', function (e) {
                e.preventDefault(); // Necessary to allow dropping
                if (draggedTask && !this.querySelector('.kanban-tasks').contains(draggedTask)) {
                    e.dataTransfer.dropEffect = 'move'; // Allow drop
                    this.classList.add('bg-gray-100'); // Visual feedback: highlight column
                }
            });

            column.addEventListener('dragleave', function () {
                this.classList.remove('bg-gray-100'); // Remove highlight
            });

            column.addEventListener('drop', function (e) {
                e.preventDefault();
                this.classList.remove('bg-gray-100'); // Remove highlight
                if (draggedTask) {
                    const taskId = draggedTask.getAttribute('data-task-id');
                    const newStatus = this.getAttribute('data-status');
                    this.querySelector('.kanban-tasks').appendChild(draggedTask); // Move the task

                    // Send status update via WebSocket
                    updates_socket.send(JSON.stringify({
                        type: 'status_update',
                        task_id: taskId,
                        status: newStatus
                    }));
                }
            });
        });
    }
});