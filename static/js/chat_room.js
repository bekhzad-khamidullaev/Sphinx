// filename: static/js/chat_room.js

document.addEventListener('DOMContentLoaded', () => {
    const roomName = JSON.parse(document.getElementById('json-roomname').textContent);
    const userName = JSON.parse(document.getElementById('json-username').textContent);
    const userId = JSON.parse(document.getElementById('json-userid').textContent);

    const chatLog = document.querySelector('#chat-messages');
    const messageInput = document.querySelector('#chat-message-input');
    const messageSubmit = document.querySelector('#chat-message-submit');
    const fileInput = document.getElementById('file-input');
    const onlineUsersList = document.getElementById('online-users-list');
    const noOnlineUsersLi = document.getElementById('no-online-users');
    const messageTemplate = document.getElementById('message-template');
    const replyPreviewArea = document.getElementById('reply-preview-area');
    const replyPreviewUser = document.getElementById('reply-preview-user');
    const replyPreviewContent = document.getElementById('reply-preview-content');
    const cancelReplyButton = document.getElementById('cancel-reply-button');
    const searchButton = document.getElementById('search-button');
    const searchArea = document.getElementById('search-area');
    const searchInput = document.getElementById('search-input');
    const searchResults = document.getElementById('search-results');
    const archiveButton = document.getElementById('archive-button');


    let currentReplyToId = null; // Store the ID of the message being replied to
    let webSocket;

    function connectWebSocket() {
        const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        webSocket = new WebSocket(
            wsScheme + '://' + window.location.host + '/ws/' + roomName + '/'
        );

        webSocket.onopen = function(e) {
            console.log('WebSocket connection established');
            // Request initial state if needed, e.g., unread counts
            // Mark messages as potentially read on connect/focus
            markMessagesAsRead();
        };

        webSocket.onclose = function(e) {
            console.error('WebSocket closed unexpectedly. Attempting to reconnect...', e);
            // Implement backoff strategy for reconnection
            setTimeout(connectWebSocket, 5000); // Try reconnecting every 5 seconds
        };

        webSocket.onerror = function(e) {
            console.error('WebSocket error:', e);
            // Maybe close and attempt reconnect
             webSocket.close();
        };

        webSocket.onmessage = function(e) {
            const data = JSON.parse(e.data);
            console.log("Message received: ", data); // Debugging

            switch (data.type) {
                case 'chat_message':
                case 'reply_message':
                case 'file_message':
                    appendMessage(data.payload);
                    // If message is not from current user, potentially show notification/update unread count
                    if (data.payload.user.username !== userName) {
                        // Increment unread count for this room in the sidebar (logic needed)
                    }
                    break;
                case 'edit_message':
                    updateMessageContent(data.payload);
                    break;
                case 'delete_message':
                    markMessageAsDeleted(data.payload);
                    break;
                case 'reaction_update':
                    updateReactions(data.payload.message_id, data.payload.reactions);
                    break;
                case 'online_users':
                    updateOnlineUsers(data.payload.users);
                    break;
                 case 'error_message':
                     alert(`Error: ${data.payload.message}`); // Simple alert for errors
                     break;
                // Handle other message types (read_status_update, user_join, user_leave etc.) if implemented
                default:
                    console.warn('Unknown message type received:', data.type);
            }
        };
    }

    function sendMessage(type, payload) {
        if (webSocket.readyState === WebSocket.OPEN) {
            webSocket.send(JSON.stringify({ type: type, ...payload }));
        } else {
            console.error("WebSocket is not open. Message not sent.");
            // Optionally queue message or show error
        }
    }

    function formatTimestamp(isoString) {
        const date = new Date(isoString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function appendMessage(msgData) {
        const messageElement = createMessageElement(msgData);
        chatLog.appendChild(messageElement);
        scrollToBottom();
    }

    function createMessageElement(msgData) {
        const templateClone = messageTemplate.content.cloneNode(true);
        const messageDiv = templateClone.querySelector('.message-container');
        const bubble = templateClone.querySelector('.message-bubble');
        const content = templateClone.querySelector('.message-content');
        const timestamp = templateClone.querySelector('.timestamp');
        const editedIndicator = templateClone.querySelector('.edited-indicator');
        const replyBlock = templateClone.querySelector('.reply-block');
        const fileBlock = templateClone.querySelector('.file-block');
        const reactionsBlock = templateClone.querySelector('.reactions-block');
        const actions = templateClone.querySelector('.message-actions');

        messageDiv.id = `message-${msgData.id}`;
        messageDiv.dataset.messageId = msgData.id;
        messageDiv.dataset.username = msgData.user.username;

        // Set alignment
        if (msgData.user.username === userName) {
            messageDiv.classList.add('justify-end');
            bubble.classList.add('bg-blue-500', 'text-white');
        } else {
            messageDiv.classList.add('justify-start');
            bubble.classList.add('bg-white', 'shadow-md');
        }

        // Set content
        if (msgData.is_deleted) {
            content.textContent = 'Message deleted';
            content.classList.add('italic', 'text-gray-500');
            actions.remove(); // No actions on deleted messages
        } else {
            content.textContent = msgData.content;
            timestamp.textContent = formatTimestamp(msgData.timestamp);
            if (msgData.edited_at) {
                editedIndicator.classList.remove('hidden');
            }

            // Handle reply
            if (msgData.reply_to) {
                replyBlock.classList.remove('hidden');
                templateClone.querySelector('.reply-user').textContent = msgData.reply_to.user.username;
                templateClone.querySelector('.reply-content').textContent = msgData.reply_to.content;
                // Add click handler to scroll to original message if needed
                replyBlock.onclick = () => {
                     const originalMsg = document.getElementById(`message-${msgData.reply_to.id}`);
                     if (originalMsg) originalMsg.scrollIntoView({ behavior: 'smooth' });
                };
            }

            // Handle file
            if (msgData.file) {
                fileBlock.classList.remove('hidden');
                const fileLink = templateClone.querySelector('.file-link');
                fileLink.href = msgData.file.url;
                templateClone.querySelector('.file-name').textContent = msgData.file.name;
                // Add specific previews for images/videos here
                 if (/\.(jpg|jpeg|png|gif)$/i.test(msgData.file.name)) {
                    const img = document.createElement('img');
                    img.src = msgData.file.url;
                    img.className = 'max-w-xs max-h-48 mt-1 rounded';
                    fileBlock.appendChild(img);
                 }
            }

            // Add reactions
            updateReactionsElement(reactionsBlock, msgData.id, msgData.reactions);

            // Add action handlers (only if message is not deleted)
            setupMessageActions(actions, msgData);

             // Hide actions for other users' messages (edit/delete)
             if (msgData.user.username !== userName) {
                 actions.querySelector('.action-edit')?.remove();
                 actions.querySelector('.action-delete')?.remove();
             }
        }


        // Add hover effect to show actions
         messageDiv.addEventListener('mouseenter', () => actions.style.opacity = '1');
         messageDiv.addEventListener('mouseleave', () => actions.style.opacity = '0');


        return templateClone;
    }

     function setupMessageActions(actionsContainer, msgData) {
        const messageId = msgData.id;

        actionsContainer.querySelector('.action-reply')?.addEventListener('click', () => {
            startReply(messageId, msgData.user.username, msgData.content);
        });

        actionsContainer.querySelector('.action-edit')?.addEventListener('click', () => {
            editMessage(messageId, msgData.content);
        });

        actionsContainer.querySelector('.action-delete')?.addEventListener('click', () => {
            if (confirm('Are you sure you want to delete this message?')) {
                 sendMessage('delete_message', { message_id: messageId });
            }
        });

        actionsContainer.querySelector('.action-react')?.addEventListener('click', (e) => {
             // Implement emoji picker pop-up here
             // For now, just send a default reaction
             const emoji = prompt("Enter emoji to react with:", "👍");
             if (emoji) {
                 sendMessage('add_reaction', { message_id: messageId, emoji: emoji });
             }
        });
    }

    function updateMessageContent(msgData) {
        const messageDiv = document.getElementById(`message-${msgData.id}`);
        if (messageDiv) {
            const content = messageDiv.querySelector('.message-content');
            const editedIndicator = messageDiv.querySelector('.edited-indicator');
            if (content) content.textContent = msgData.content;
            if (editedIndicator) editedIndicator.classList.remove('hidden');
        }
    }

    function markMessageAsDeleted(msgData) {
        const messageDiv = document.getElementById(`message-${msgData.id}`);
        if (messageDiv) {
            const content = messageDiv.querySelector('.message-content');
            const bubble = messageDiv.querySelector('.message-bubble');
            const actions = messageDiv.querySelector('.message-actions');
            const reactions = messageDiv.querySelector('.reactions-block');
            const fileBlock = messageDiv.querySelector('.file-block');
            const replyBlock = messageDiv.querySelector('.reply-block');

            if (content) {
                content.textContent = 'Message deleted';
// filename: static/js/chat_room.js
// (Continuing from previous response)

content.className = 'message-content text-sm italic text-gray-500'; // Apply styling
}
bubble?.classList.add('opacity-70'); // Fade it slightly
actions?.remove(); // Remove actions
reactions?.remove(); // Remove reactions block
fileBlock?.remove(); // Remove file block
replyBlock?.remove(); // Remove reply block
}
}

function updateReactions(messageId, reactionsSummary) {
const messageDiv = document.getElementById(`message-${messageId}`);
if (messageDiv) {
const reactionsBlock = messageDiv.querySelector('.reactions-block');
if (reactionsBlock) {
    updateReactionsElement(reactionsBlock, messageId, reactionsSummary);
}
}
}

function updateReactionsElement(reactionsBlock, messageId, reactionsSummary) {
reactionsBlock.innerHTML = ''; // Clear existing reactions
if (!reactionsSummary || Object.keys(reactionsSummary).length === 0) {
reactionsBlock.classList.add('hidden');
return;
}

reactionsBlock.classList.remove('hidden');

for (const [emoji, data] of Object.entries(reactionsSummary)) {
const reactionButton = document.createElement('button');
reactionButton.className = 'px-1.5 py-0.5 border rounded-full text-xs bg-gray-200 hover:bg-gray-300';
// Check if current user reacted with this emoji
if (data.users.includes(userName)) {
    reactionButton.classList.add('border-blue-500', 'bg-blue-100'); // Highlight user's reaction
}
reactionButton.textContent = `${emoji} ${data.count}`;
reactionButton.title = `Reacted by: ${data.users.join(', ')}`; // Show users on hover

reactionButton.onclick = () => {
    // Clicking existing reaction toggles it (sends add_reaction again)
    sendMessage('add_reaction', { message_id: messageId, emoji: emoji });
};
reactionsBlock.appendChild(reactionButton);
}
}


function editMessage(messageId, currentContent) {
// Simple prompt-based edit for now. Could be replaced with inline editing UI.
const newContent = prompt("Edit your message:", currentContent);
if (newContent !== null && newContent.trim() !== '' && newContent !== currentContent) {
sendMessage('edit_message', {
    message_id: messageId,
    content: newContent.trim()
});
}
}

function startReply(messageId, replyUsername, replyContent) {
currentReplyToId = messageId;
replyPreviewUser.textContent = replyUsername;
replyPreviewContent.textContent = replyContent.substring(0, 50) + (replyContent.length > 50 ? '...' : ''); // Show preview
replyPreviewArea.classList.remove('hidden');
messageInput.focus();
}

function cancelReply() {
currentReplyToId = null;
replyPreviewArea.classList.add('hidden');
replyPreviewUser.textContent = '';
replyPreviewContent.textContent = '';
}

function handleFormSubmit() {
const messageContent = messageInput.value.trim();

if (!messageContent && !currentReplyToId) { // Allow empty message only if it's a file upload (handled separately)
 // Check if a file is being uploaded implicitly? No, file upload is separate action.
 // If no content and no reply, do nothing.
return;
}

if (currentReplyToId) {
// Send reply message
sendMessage('reply_message', {
    message: messageContent,
    reply_to_id: currentReplyToId
});
cancelReply(); // Clear reply state after sending
} else {
// Send normal chat message
sendMessage('chat_message', {
    message: messageContent
});
}

messageInput.value = ''; // Clear input field
messageInput.focus();
}

function handleFileInputChange(event) {
const file = event.target.files[0];
if (!file) return;

// Optional: Add checks for file size, type etc.
const maxSize = 50 * 1024 * 1024; // 50MB limit example
if (file.size > maxSize) {
 alert(`File is too large. Maximum size is ${maxSize / 1024 / 1024} MB.`);
 fileInput.value = ''; // Reset file input
 return;
}


const reader = new FileReader();
reader.onload = function(e) {
const fileData = e.target.result.split(',')[1]; // Get base64 part
const caption = prompt("Enter an optional caption for the file:", ""); // Ask for caption

sendMessage('send_file', {
    filename: file.name,
    file_data: fileData,
    content: caption || "" // Send caption or empty string
});
};
reader.onerror = function(e) {
console.error("File reading error:", e);
alert("Could not read file.");
};
reader.readAsDataURL(file); // Read file as Base64

fileInput.value = ''; // Reset file input after initiating upload
}


function updateOnlineUsers(users) {
if (!onlineUsersList || !noOnlineUsersLi) return;

onlineUsersList.innerHTML = ''; // Clear current list
if (users && users.length > 0) {
noOnlineUsersLi.classList.add('hidden');
users.forEach(username => {
    const li = document.createElement('li');
     // Add a green dot indicator
     const indicator = document.createElement('span');
     indicator.className = 'inline-block w-2 h-2 bg-green-500 rounded-full mr-2';
     li.appendChild(indicator);
     li.appendChild(document.createTextNode(username));
     // Highlight current user?
     if (username === userName) {
        li.classList.add('font-semibold');
     }
    onlineUsersList.appendChild(li);
});
} else {
onlineUsersList.appendChild(noOnlineUsersLi); // Show the "no users online" message
noOnlineUsersLi.classList.remove('hidden');
noOnlineUsersLi.textContent = "No users online";
}
}

function scrollToBottom() {
// Only scroll if user is near the bottom already
const threshold = 100; // Pixels from bottom
if (chatLog.scrollHeight - chatLog.scrollTop - chatLog.clientHeight < threshold) {
 chatLog.scrollTop = chatLog.scrollHeight;
}
}

function markMessagesAsRead() {
// Find the ID of the last visible message
const messages = chatLog.querySelectorAll('.message-container');
let lastVisibleMessageId = null;
if (messages.length > 0) {
// This could be more sophisticated (check visibility % in viewport)
lastVisibleMessageId = messages[messages.length - 1].dataset.messageId;
}

// Send the update via WebSocket
if (lastVisibleMessageId) {
sendMessage('mark_read', { last_visible_message_id: lastVisibleMessageId });
} else {
 // Or send a generic "mark all" if no messages are visible/present
 sendMessage('mark_read', {});
}
// Also, clear any visual unread indicators for this room in the sidebar
const unreadIndicator = document.getElementById(`unread-${roomName}`);
if (unreadIndicator) {
unreadIndicator.classList.add('hidden');
unreadIndicator.textContent = '';
}
}

// --- Search Functionality ---
let searchDebounceTimer;
searchButton?.addEventListener('click', () => {
searchArea.classList.toggle('hidden');
if (!searchArea.classList.contains('hidden')) {
searchInput.focus();
} else {
searchResults.innerHTML = ''; // Clear results when hiding
searchInput.value = '';
}
});

searchInput?.addEventListener('input', () => {
clearTimeout(searchDebounceTimer);
const query = searchInput.value.trim();
searchResults.innerHTML = query ? 'Searching...' : ''; // Indicate searching

if (query.length < 2) {
searchResults.innerHTML = ''; // Clear if query is too short
return;
}

searchDebounceTimer = setTimeout(() => {
// Use Fetch API for search (or could use WebSocket if UserSearchConsumer is set up)
fetch(`/chat/${roomName}/search/?q=${encodeURIComponent(query)}`, {
    method: 'GET',
    headers: {
        'X-Requested-With': 'XMLHttpRequest', // Identify as AJAX
        'Accept': 'application/json',
    }
})
.then(response => {
     if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
     return response.json();
})
.then(data => {
    searchResults.innerHTML = ''; // Clear previous results/searching message
    if (data.success && data.messages.length > 0) {
        data.messages.forEach(msg => {
            const div = document.createElement('div');
            div.className = 'p-2 border-b hover:bg-gray-100 cursor-pointer text-sm';
            div.innerHTML = `<strong>${msg.user}:</strong> ${msg.content.substring(0, 100)}... <span class="text-gray-500 text-xs">${formatTimestamp(msg.timestamp)}</span>`;
            div.onclick = () => {
                // Scroll to the message in the main chat log
                const targetMsg = document.getElementById(`message-${msg.id}`);
                if (targetMsg) {
                    targetMsg.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    targetMsg.classList.add('highlight-message'); // Add temporary highlight
                    setTimeout(() => targetMsg.classList.remove('highlight-message'), 2000);
                    searchArea.classList.add('hidden'); // Hide search after clicking
                } else {
                    alert('Original message not found (might be older).');
                }
            };
            searchResults.appendChild(div);
        });
    } else if (data.success) {
        searchResults.innerHTML = '<div class="p-2 text-gray-500">No results found.</div>';
    } else {
        searchResults.innerHTML = `<div class="p-2 text-red-500">Error: ${data.error || 'Search failed'}</div>`;
    }
})
.catch(error => {
    console.error('Search fetch error:', error);
    searchResults.innerHTML = '<div class="p-2 text-red-500">Search request failed.</div>';
});
}, 500); // Debounce time: 500ms
});

// --- Archive Functionality ---
archiveButton?.addEventListener('click', () => {
const roomSlug = archiveButton.dataset.roomSlug;
if (confirm(`Are you sure you want to archive the room "${roomName}"? This will hide it for all participants.`)) {
 fetch(`/chat/${roomSlug}/archive/`, {
     method: 'POST',
     headers: {
         'X-CSRFToken': csrfToken, // Defined in the template
         'X-Requested-With': 'XMLHttpRequest',
         'Accept': 'application/json',
     }
 })
 .then(response => response.json())
 .then(data => {
     if (data.success) {
         alert('Room archived successfully.');
         // Redirect to the main rooms list or update UI
         window.location.href = '/chat/'; // Redirect to rooms list
     } else {
         alert(`Failed to archive room: ${data.error || 'Unknown error'}`);
     }
 })
 .catch(error => {
     console.error('Archive fetch error:', error);
     alert('An error occurred while trying to archive the room.');
 });
}
});


// --- Event Listeners ---
messageSubmit.addEventListener('click', handleFormSubmit);
messageInput.addEventListener('keydown', (e) => {
if (e.key === 'Enter' && !e.shiftKey) { // Send on Enter, allow newline with Shift+Enter
e.preventDefault();
handleFormSubmit();
}
});

fileInput.addEventListener('change', handleFileInputChange);

cancelReplyButton.addEventListener('click', cancelReply);

// Mark as read when window gains focus or user interacts
window.addEventListener('focus', markMessagesAsRead);
chatLog.addEventListener('scroll', () => {
// Potentially trigger markMessagesAsRead on scroll events too,
// maybe debounced or when scrolling stops near the bottom.
// For now, focus is the primary trigger.
});


// --- Initial Setup ---
scrollToBottom(); // Scroll down on initial load
connectWebSocket(); // Start WebSocket connection

// Initial mark as read after a short delay to ensure WebSocket might be ready
setTimeout(markMessagesAsRead, 1500);

}); // End DOMContentLoaded

// Add CSS for highlighting searched message if needed:
/*
.highlight-message {
animation: highlight 2s ease-out;
}

@keyframes highlight {
0% { background-color: yellow; }
100% { background-color: transparent; }
}
*/