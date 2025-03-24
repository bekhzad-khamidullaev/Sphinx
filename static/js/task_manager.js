import { showNotification, debounce } from '/static/js/utils.js';

// Initialize WebSocket
const socket = new WebSocket('ws://' + window.location.host + '/ws/task_updates/');

// Initialize SortableJS for Kanban
document.querySelectorAll('.kanban-tasks').forEach(column => {
    new Sortable(column, {
        group: 'shared',
        animation: 150,
        ghostClass: 'bg-gray-200',
        chosenClass: 'shadow-xl',
        dragClass: 'cursor-grabbing',
        easing: "cubic-bezier(1, 0, 0, 1)",
        onEnd: function (evt) {
            const taskId = evt.item.getAttribute('data-task-id');
            const newStatus = evt.to.closest('.kanban-column').getAttribute('data-status');
            socket.send(JSON.stringify({ type: 'status_update', task_id: taskId, status: newStatus }));
        },
    });
});

// Handle WebSocket messages
socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'status_update' && data.success) {
        showNotification('Статус задачи обновлен', 'success');
        updateTaskCounts();
    }
};

// Update task counts
const updateTaskCounts = () => {
    requestAnimationFrame(() => {
        document.querySelectorAll('.kanban-column').forEach(column => {
            const taskCount = column.querySelectorAll('.kanban-task').length;
            column.querySelector('.task-count').textContent = taskCount;
        });
    });
};

// Initialize PWA
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/service-worker.js')
        .then(registration => console.log('ServiceWorker registered:', registration))
        .catch(error => console.error('ServiceWorker registration failed:', error));
}