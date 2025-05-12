// static/js/chat.js
"use strict";

document.addEventListener('DOMContentLoaded', () => {
    console.log("Initializing chat.js...");

    // --- DOM Elements ---
    const chatMessagesContainer = document.getElementById('chat-messages');
    const messageForm = document.getElementById('chat-message-form');
    const messageInput = document.getElementById('chat-message-input');
    const messageSubmitBtn = document.getElementById('chat-message-submit');
    const fileInput = document.getElementById('chat-file-input');
    const fileInputLabel = document.querySelector('label[for="chat-file-input"]');
    const filePreviewArea = document.getElementById('file-preview');
    const filePreviewName = document.getElementById('file-preview-name');
    const removeFileBtn = document.getElementById('remove-file-btn');
    const replyPreviewArea = document.getElementById('reply-preview-area');
    const replyPreviewUser = document.getElementById('reply-preview-user');
    const replyPreviewText = document.getElementById('reply-preview-text');
    const cancelReplyBtn = document.getElementById('cancel-reply-btn');
    const replyMessageIdInput = document.getElementById('reply-message-id');
    const onlineUsersCount = document.getElementById('online-count');
    const onlineUsersList = document.getElementById('online-list');
    const noMessagesElement = document.getElementById('no-messages');
    const messageAnchor = document.getElementById('message-anchor'); // For scrolling

    // --- State Variables ---
    let chatSocket = null;
    let currentFile = null; // Stores the file object to be sent
    let isLoadingOlder = false; // Flag to prevent multiple load requests
    let hasMoreOlderMessages = true; // Assume more exist initially

    // --- Get Data from Template (Ensure these are set in room.html) ---
    const roomSlug = window.roomSlug;
    const currentUserId = window.currentUserId;
    const currentUsername = window.currentUsername;
    const getWsPath = window.djangoWsPath; // Function defined in room.html script block

    if (!chatMessagesContainer || !messageForm || !messageInput || !messageSubmitBtn || !fileInput || !roomSlug) {
        console.error("Essential chat elements or room slug not found. Chat cannot initialize.");
        return;
    }

    // --- Constants ---
    const MSG_TYPE_MESSAGE = 'chat_message';
    const MSG_TYPE_EDIT = 'edit_message';
    const MSG_TYPE_DELETE = 'delete_message';
    const MSG_TYPE_REACTION = 'reaction_update';
    const MSG_TYPE_FILE = 'file_message';
    const MSG_TYPE_READ_STATUS = 'read_status_update';
    const MSG_TYPE_REPLY = 'reply_message';
    const MSG_TYPE_ONLINE_USERS = 'online_users';
    const MSG_TYPE_ERROR = 'error_message';
    const MSG_TYPE_OLDER_MESSAGES = 'older_messages';
    const MSG_TYPE_LOAD_OLDER = 'load_older_messages';
    const MSG_TYPE_ACK = 'message_ack';

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

     // --- Debounce Helper ---
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

    function formatTimestamp(isoString) {
        if (!isoString) return '';
        try {
            const date = new Date(isoString);
            if (isNaN(date)) { // Check for invalid date
                console.error("Invalid date for timestamp:", isoString);
                return '--:--';
            }
            // Manual formatting for HH:MM with leading zeros
            const hours = date.getHours().toString().padStart(2, '0');
            const minutes = date.getMinutes().toString().padStart(2, '0');
            return `${hours}:${minutes}`;
        } catch (e) {
            console.error("Error formatting timestamp:", isoString, e);
            return '--:--'; // Return placeholder on error
        }
    }

    function scrollToBottom(force = false) {
        // Scrolls only if user is near the bottom or forced
        const threshold = 100; // Pixels from bottom
        const isScrolledUp = chatMessagesContainer.scrollHeight - chatMessagesContainer.scrollTop - chatMessagesContainer.clientHeight > threshold;
        const shouldScroll = force || !isScrolledUp;

        if (shouldScroll) {
            // Use smooth scrolling if available and not forced (instant scroll on forced)
             if ('scrollBehavior' in document.documentElement.style && !force) {
                 chatMessagesContainer.scrollTo({ top: chatMessagesContainer.scrollHeight, behavior: 'smooth' });
             } else {
                 chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
             }
            console.debug("Scrolled to bottom.");
        } else {
            console.debug("User scrolled up, not scrolling to bottom.");
             // Optionally show "new message" indicator here
             // e.g., newMessagesIndicator.classList.remove('hidden');
        }
    }

    // --- WebSocket Logic ---
    function connectWebSocket() {
        if (!getWsPath) {
            console.error("getWebsocketPath function not found.");
            if (window.showNotification) showNotification("WebSocket config error.", "error");
            return;
        }
        // Use the function passed from the template context
        const wsUrl = `${window.location.protocol === 'https:' ? 'wss://' : 'ws://'}${window.location.host}${getWsPath('chat', roomSlug)}`;
        console.log(`Connecting to Chat WebSocket: ${wsUrl}`);

        chatSocket = new WebSocket(wsUrl);

        chatSocket.onopen = (e) => {
            console.log('Chat WebSocket connection established.');
            window.wsRetryCount = 0; // Reset retries on successful open
            // Request older messages if needed or initial state
            // loadOlderMessages(); // Maybe call this initially?
            scrollToBottom(true); // Scroll down on connect
        };

        chatSocket.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                console.log('WebSocket message received:', data);
                handleWebSocketMessage(data);
            } catch (error) {
                console.error('Error processing WebSocket message:', error, "Data:", e.data);
            }
        };

        chatSocket.onerror = (e) => {
            console.error('Chat WebSocket error:', e);
            if (window.showNotification) showNotification('Chat WebSocket connection error', 'error');
        };

        chatSocket.onclose = (e) => {
            console.log('Chat WebSocket connection closed.', e.code, e.reason);
            chatSocket = null; // Ensure socket is nullified
            if (!e.wasClean && e.code !== 1000) {
                if (window.showNotification) showNotification('Chat disconnected. Reconnecting...', 'warning');
                const retryDelay = Math.min(30000, (Math.pow(window.wsRetryCount || 0) * 1000) + Math.random() * 1000);
                window.wsRetryCount = (window.wsRetryCount || 0) + 1;
                console.log(`Retrying Chat WS connection in ${retryDelay / 1000}s`);
                setTimeout(connectWebSocket, retryDelay);
            } else {
                window.wsRetryCount = 0; // Reset on clean closure
            }
        };
    }

    function sendWebSocketMessage(type, payload) {
        if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
            console.debug(`Sending WS message - Type: ${type}, Payload:`, payload);
            chatSocket.send(JSON.stringify({ type: type, payload: payload }));
        } else {
            console.error("Cannot send message: WebSocket is not connected.");
            if (window.showNotification) showNotification("Cannot send: not connected to chat.", "error");
            if (!chatSocket) {
                 console.log("Attempting to reconnect WebSocket...");
                 connectWebSocket();
            }
        }
    }

    // --- Message Handling ---
    function handleWebSocketMessage(data) {
        const type = data.type;
        const payload = data.payload;

        if (!payload) { console.warn("Received message without payload:", data); return; }

        switch (type) {
            case MSG_TYPE_MESSAGE:
            case MSG_TYPE_REPLY:
            case MSG_TYPE_FILE:
                addMessageToDOM(payload);
                scrollToBottom(); // Scroll down only if user is near bottom
                markAsReadIfNeeded(payload.id); // Mark received message as read potentially
                break;
            case MSG_TYPE_EDIT:
                updateMessageInDOM(payload);
                break;
            case MSG_TYPE_DELETE:
                deleteMessageInDOM(payload);
                break;
            case MSG_TYPE_REACTION:
                updateReactionsInDOM(payload.message_id, payload.reactions);
                break;
            case MSG_TYPE_ONLINE_USERS:
                updateOnlineList(payload.users);
                break;
            case MSG_TYPE_ERROR:
                console.error("Error from server:", payload.message);
                if (window.showNotification) showNotification(`Error: ${escapeHtml(payload.message)}`, "error");
                if (payload.client_id) handleMessageAckError(payload.client_id);
                break;
             case MSG_TYPE_OLDER_MESSAGES:
                 addOlderMessagesToDOM(payload.messages);
                 hasMoreOlderMessages = payload.has_more ?? true;
                 isLoadingOlder = false;
                 break;
             case MSG_TYPE_ACK:
                 handleMessageAck(payload.client_id, payload.server_id, payload.timestamp);
                 break;
            default:
                console.warn("Received unknown message type:", type);
        }
    }

    // --- DOM Manipulation & UI Updates ---
    function addMessageToDOM(msgData, prepend = false) {
        if (!msgData || !msgData.id) return;
        noMessagesElement?.remove();

        const messageElement = document.createElement('div');
        messageElement.id = `message-${msgData.id}`;
        messageElement.dataset.messageId = msgData.id;
        const isOwn = msgData.user?.id === currentUserId;
        messageElement.className = `message-item flex ${isOwn ? 'justify-end' : 'justify-start'} group animate-fade-in`;

        const avatarUrl = msgData.user?.avatar_url || '/static/img/user.svg';
        const username = escapeHtml(msgData.user?.username || 'System');
        const timestamp = formatTimestamp(msgData.timestamp);
        const editedTimestamp = msgData.edited_at ? formatTimestamp(msgData.edited_at) : null;
        const editedIndicator = editedTimestamp ? `<span class="text-xs opacity-70" title="Edited at ${editedTimestamp}">(edited)</span>` : ''; // Hardcoded English
        const deletedText = "Message deleted"; // Hardcoded English
        const fileText = "File"; // Hardcoded English
        const replyToText = "Reply to"; // Hardcoded English
        const originalDeletedText = "[original deleted]"; // Hardcoded English

        let contentHtml = '';
        if (msgData.is_deleted) {
            contentHtml = `<em class="text-xs italic opacity-70">${deletedText}</em>`;
        } else if (msgData.file) {
            const fileName = escapeHtml(msgData.file.name || 'file');
            const fileSize = msgData.file.size ? `(${(msgData.file.size / 1024).toFixed(1)} KB)` : '';
            contentHtml = `
                <div class="flex items-center space-x-2">
                     <i class="fas fa-file-alt fa-lg opacity-70"></i>
                     <div>
                         <a href="${escapeHtml(msgData.file.url || '#')}" target="_blank" rel="noopener noreferrer" class="hover:underline break-all font-medium">${fileName}</a>
                         <span class="text-xs opacity-70 ml-1">${fileSize}</span>
                         ${msgData.content ? `<p class="mt-1 text-xs opacity-90">${escapeHtml(msgData.content).replace(/\n/g, '<br>')}</p>` : ''}
                     </div>
                </div>`;
        } else {
            contentHtml = `<p class="whitespace-pre-wrap break-words">${escapeHtml(msgData.content).replace(/\n/g, '<br>')}</p>`;
        }

        let replyHtml = '';
        if (msgData.reply_to) {
             const replyUser = escapeHtml(msgData.reply_to.user?.username || 'System');
             const replyContent = msgData.reply_to.is_deleted ? originalDeletedText : (msgData.reply_to.has_file ? `<i class="fas fa-file-alt"></i> ${fileText}` : escapeHtml(msgData.reply_to.content || ''));
             replyHtml = `
                 <a href="#message-${msgData.reply_to.id}" class="block text-xs p-2 rounded-lg border ${isOwn ? 'bg-blue-100 border-blue-200 dark:bg-blue-900/50 dark:border-blue-700/50' : 'bg-gray-100 border-gray-200 dark:bg-dark-700 dark:border-dark-600'} opacity-80 hover:opacity-100 mb-1 max-w-xs cursor-pointer">
                     <p class="font-medium text-gray-700 dark:text-gray-300">${replyToText} ${replyUser}</p>
                     <p class="text-gray-500 dark:text-gray-400 italic truncate">${replyContent}</p>
                 </a>`;
        }

        messageElement.innerHTML = `
            <div class="flex items-end max-w-[85%] ${isOwn ? 'flex-row-reverse' : ''} space-x-2 rtl:space-x-reverse">
                ${!isOwn ? `<img src="${avatarUrl}" alt="${username}" class="w-6 h-6 rounded-full flex-shrink-0 mb-4 object-cover">` : ''}
                <div class="flex flex-col space-y-1 text-sm ${isOwn ? 'items-end' : 'items-start'}">
                    ${!isOwn ? `<span class="text-xs font-semibold text-gray-600 dark:text-gray-400">${username}</span>` : ''}
                    ${replyHtml}
                    <div class="relative px-3 py-2 rounded-xl min-w-[50px] ${isOwn ? 'rounded-br-none bg-blue-600 dark:bg-ios-blue text-white' : 'rounded-bl-none bg-white dark:bg-dark-700 text-gray-900 dark:text-gray-100 shadow-sm border border-gray-200 dark:border-dark-600'}">
                        ${contentHtml}
                        <span class="absolute bottom-1 ${isOwn ? 'right-2' : 'left-2'} text-xs ${isOwn ? 'text-blue-200' : 'text-gray-400 dark:text-gray-500'} opacity-0 group-hover:opacity-100 transition-opacity pt-1">
                            ${editedIndicator} ${timestamp}
                        </span>
                        <div class="reactions-area mt-1 flex flex-wrap gap-1 ${isOwn ? 'justify-end' : 'justify-start'}" id="reactions-${msgData.id}">
                            ${generateReactionsHtml(msgData.reactions || {})}
                        </div>
                         <div class="absolute top-0 ${isOwn ? 'left-[-3.5rem]' : 'right-[-3.5rem]'} z-10 hidden group-hover:flex space-x-1 bg-gray-100 dark:bg-dark-600 p-1 rounded-full shadow text-gray-600 dark:text-gray-300 text-xs">
                            <button type="button" data-action="add-reaction" title="React" class="p-1 rounded-full hover:bg-gray-200 dark:hover:bg-dark-500"><i class="far fa-smile"></i></button>
                            <button type="button" data-action="reply-message" title="Reply" class="p-1 rounded-full hover:bg-gray-200 dark:hover:bg-dark-500"><i class="fas fa-reply"></i></button>
                            ${isOwn && !msgData.is_deleted ? `
                            <button type="button" data-action="edit-message" title="Edit" class="p-1 rounded-full hover:bg-gray-200 dark:hover:bg-dark-500"><i class="fas fa-pen"></i></button>
                            <button type="button" data-action="delete-message" title="Delete" class="p-1 rounded-full hover:bg-gray-200 dark:hover:bg-dark-500 text-red-500"><i class="fas fa-trash"></i></button>
                            ` : ''}
                         </div>
                    </div>
                </div>
            </div>
        `;

        addMessageActionListeners(messageElement);

        if (prepend) {
            chatMessagesContainer.insertBefore(messageElement, chatMessagesContainer.firstChild);
        } else {
            chatMessagesContainer.appendChild(messageElement);
        }
    }

     function updateMessageInDOM(msgData) {
         const messageElement = document.getElementById(`message-${msgData.id}`);
         if (messageElement) {
             const contentP = messageElement.querySelector('p.whitespace-pre-wrap');
             const timeSpanContainer = messageElement.querySelector('.group-hover\\:opacity-100'); // Find container for time/edit
             if (contentP) {
                 contentP.innerHTML = escapeHtml(msgData.content).replace(/\n/g, '<br>');
             }
             if (timeSpanContainer) { // Rebuild the span content
                  const editedTimestamp = msgData.edited_at ? formatTimestamp(msgData.edited_at) : null;
                  const originalTimestamp = formatTimestamp(msgData.timestamp);
                  timeSpanContainer.innerHTML = `${editedTimestamp ? `<span title="Edited at ${editedTimestamp}">(edited)</span> ` : ''}${originalTimestamp}`;
             }
             messageElement.classList.add('bg-yellow-100/50', 'dark:bg-yellow-900/30');
             setTimeout(() => messageElement.classList.remove('bg-yellow-100/50', 'dark:bg-yellow-900/30'), 1500);
             console.info(`Updated message ${msgData.id} in DOM.`);
         }
     }

     function deleteMessageInDOM(msgData) {
          const messageElement = document.getElementById(`message-${msgData.id}`);
          if (messageElement) {
              const contentDiv = messageElement.querySelector('.relative.px-3');
              if (contentDiv) {
                  contentDiv.innerHTML = `<em class="text-xs italic opacity-70">Message deleted</em>`;
                  messageElement.querySelector('.reactions-area')?.remove();
                  messageElement.querySelector('.group-hover\\:flex')?.remove();
              }
              messageElement.classList.add('opacity-50');
              logger.info(`Marked message ${msgData.id} as deleted in DOM.`);
          }
     }

    function generateReactionsHtml(reactions) {
        let html = '';
        // Sort emojis maybe? Object.keys(reactions).sort().forEach(emoji => { ... });
        for (const [emoji, data] of Object.entries(reactions)) {
            const userList = data.users.join(', ');
            // Use currentUsername for comparison
            const isReacted = data.users.includes(currentUsername);
            html += `
                <button type="button" data-action="add-reaction" data-emoji="${escapeHtml(emoji)}"
                        title="${escapeHtml(userList)}"
                        class="${isReacted ? 'reacted-by-user' : ''}">
                    ${escapeHtml(emoji)} <span class="reaction-count">${data.count}</span>
                </button>
            `;
        }
        return html;
    }

    function updateReactionsInDOM(messageId, reactions) {
        const reactionsContainer = document.getElementById(`reactions-${messageId}`);
        if (reactionsContainer) {
            reactionsContainer.innerHTML = generateReactionsHtml(reactions || {});
        }
    }

    function updateOnlineList(users = []) {
        if (onlineUsersCount && onlineUsersList) {
            onlineUsersCount.textContent = users.length;
            // Use display_name if available from backend, otherwise username
            onlineUsersList.textContent = users.length > 0
                ? users.slice(0, 5).map(u => escapeHtml(u.display_name || u.username || '?')).join(', ') + (users.length > 5 ? '...' : '')
                : '(empty)';
        }
    }

    function addOlderMessagesToDOM(messages = []) {
        if (messages.length === 0) {
            hasMoreOlderMessages = false;
            logger.info("No older messages received.");
            // Optionally display a "no more messages" indicator at the top
            chatMessagesContainer.insertAdjacentHTML('afterbegin', '<p class="text-center text-xs text-gray-400 py-2">~ End of history ~</p>');
            return;
        }
        const firstMessageBeforeLoad = chatMessagesContainer.firstElementChild;
        messages.forEach(msg => addMessageToDOM(msg, true)); // Prepend
        if (firstMessageBeforeLoad) {
             firstMessageBeforeLoad.scrollIntoView({ behavior: 'auto', block: 'start' });
             logger.debug("Restored scroll position after loading older messages.");
        }
        isLoadingOlder = false;
    }

    // --- Event Listeners ---
    function attachEventListeners() {
        messageForm.addEventListener('submit', (e) => { e.preventDefault(); sendMessage(); });
        messageInput.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
        fileInput.addEventListener('change', handleFileSelect);
        removeFileBtn?.addEventListener('click', clearFileSelection);
        chatMessagesContainer.addEventListener('click', handleMessageActionDelegation); // Use delegation
        cancelReplyBtn?.addEventListener('click', clearReplyPreview);
        chatMessagesContainer.addEventListener('scroll', debounce(handleScroll, 150));
    }

    // --- Action Handlers ---
    function sendMessage() {
        const content = messageInput.value.trim();
        const replyToId = replyMessageIdInput?.value;
        // Ensure UUID library is loaded before calling
        const clientMsgId = typeof uuid !== 'undefined' ? `client_${uuid.v4()}` : `client_${Date.now()}`; // Fallback to timestamp

        // Strengthened Check
        if (content.length === 0 && !currentFile) {
             console.log("sendMessage aborted: Content is empty and no file selected.");
             messageInput.focus();
             return;
        }

        messageInput.disabled = true;
        messageSubmitBtn.disabled = true;
        messageSubmitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        if (currentFile) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const payload = {
                    filename: currentFile.name,
                    file_data: e.target.result.split(',')[1],
                    content: content, // Caption
                    client_id: clientMsgId,
                    reply_to_id: replyToId || null
                };
                console.log(">>> Preparing to send FILE message:", payload);
                sendWebSocketMessage('send_file', payload);
                clearFileSelection();
                 if(replyToId) clearReplyPreview();
            };
            reader.onerror = function(e) { console.error("File read error:", e); enableForm(); handleMessageAckError(clientMsgId); };
            reader.readAsDataURL(currentFile);
        } else {
            const messageType = replyToId ? MSG_TYPE_REPLY : MSG_TYPE_MESSAGE;
            const payload = {
                content: content, // Correct key
                client_id: clientMsgId,
                reply_to_id: replyToId || null
            };
            console.log(`>>> Preparing to send TEXT message (${messageType}):`, payload);
            sendWebSocketMessage(messageType, payload);
             if(replyToId) clearReplyPreview();
        }

        messageInput.value = '';
        // Re-enable form after a short delay, assuming message will likely send
        setTimeout(enableForm, 500);
    }

    function enableForm() {
         messageInput.disabled = false;
         messageSubmitBtn.disabled = false;
         messageSubmitBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
    }

    function handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) { clearFileSelection(); return; }
        if (file.size > 10 * 1024 * 1024) { // 10MB limit example
            if(window.showNotification) showNotification("File too large (max 10MB)", "error");
            clearFileSelection(); return;
        }
        currentFile = file;
        if (filePreviewArea && filePreviewName) {
            filePreviewName.textContent = file.name;
            filePreviewArea.classList.remove('hidden');
        }
        messageInput.placeholder = "Add caption (optional)..."; // Hardcoded English
    }

    function clearFileSelection() {
        currentFile = null;
        fileInput.value = '';
        if (filePreviewArea) filePreviewArea.classList.add('hidden');
        if (filePreviewName) filePreviewName.textContent = '';
        messageInput.placeholder = "Enter message..."; // Hardcoded English
    }

     // --- Event Delegation for Message Actions ---
     function handleMessageActionDelegation(event) {
        const button = event.target.closest('button[data-action]');
        if (!button) return;

        const action = button.dataset.action;
        const messageElement = button.closest('.message-item');
        const messageId = messageElement?.dataset.messageId;

        // Reactions are handled differently
        if (action === 'add-reaction') {
            const targetButton = event.target.closest('button[data-emoji]');
            const emoji = targetButton?.dataset.emoji || button.dataset.emoji;
            const reactionButtonContainer = messageElement.querySelector('.group-hover\\:flex');

            if (messageId && emoji) { // Clicked existing reaction bubble
                 sendWebSocketMessage('add_reaction', { message_id: messageId, emoji: emoji });
            } else if (messageId) { // Clicked the main react button (needs picker)
                 // TODO: Implement emoji picker here
                 const pickedEmoji = prompt("Pick emoji:"); // Simple placeholder
                 if(pickedEmoji) sendWebSocketMessage('add_reaction', { message_id: messageId, emoji: pickedEmoji });
            }
            return; // Stop further processing for reactions
        }

        // Other actions require messageId
        if (!messageId) return;
        console.log(`Action clicked: ${action}, Message ID: ${messageId}`);

        switch (action) {
            case 'reply-message': setupReply(messageId); break;
            case 'edit-message': startEdit(messageElement); break;
            case 'delete-message': confirmDelete(messageId); break;
        }
    }

    // Stubs for old listeners (now handled by delegation)
    function addReactionListeners(messageElement) { }
    function addMessageActionListeners(messageElement) { }


    function setupReply(messageId) {
         const messageElement = document.getElementById(`message-${messageId}`);
         if (!messageElement) return;
         const usernameElement = messageElement.querySelector('.flex-col > span.font-semibold');
         const replyUserText = usernameElement ? usernameElement.textContent : currentUsername;
         const contentP = messageElement.querySelector('p.whitespace-pre-wrap');
         const fileLink = messageElement.querySelector('.flex.items-center > div > a');
         let previewText = '';
         if (contentP) { previewText = contentP.textContent.substring(0, 50) + (contentP.textContent.length > 50 ? '...' : ''); }
         else if (fileLink) { previewText = `<i class="fas fa-file-alt mr-1"></i> ${escapeHtml(fileLink.textContent)}`; }
         else { previewText = messageElement.querySelector('em')?.textContent || ''; }

         if (replyPreviewArea && replyMessageIdInput && replyPreviewUser && replyPreviewText) {
             replyMessageIdInput.value = messageId;
             replyPreviewUser.textContent = replyUserText;
             replyPreviewText.innerHTML = previewText;
             replyPreviewArea.classList.remove('hidden');
             messageInput.focus();
         }
    }

    function clearReplyPreview() {
         if (replyPreviewArea && replyMessageIdInput) {
            replyMessageIdInput.value = '';
            replyPreviewArea.classList.add('hidden');
         }
    }

    function startEdit(messageElement) {
        console.warn("Edit functionality not fully implemented.");
        const messageId = messageElement.dataset.messageId;
        const contentP = messageElement.querySelector('p.whitespace-pre-wrap');
        if (!contentP) { if(window.showNotification) showNotification("Cannot edit file messages this way.", "warning"); return; }
        const currentContent = contentP.textContent;
        const newContent = prompt("Edit message:", currentContent); // Placeholder UI
        if (newContent !== null && newContent.trim() !== currentContent) {
             sendWebSocketMessage('edit_message', { message_id: messageId, content: newContent.trim() });
        }
    }

    function confirmDelete(messageId) {
         // Replace with SweetAlert if available
         if (confirm("Are you sure you want to delete this message? This cannot be undone.")) {
             sendWebSocketMessage('delete_message', { message_id: messageId });
         }
    }

    function handleScroll() {
         if (chatMessagesContainer.scrollTop < 200 && !isLoadingOlder && hasMoreOlderMessages) {
             isLoadingOlder = true;
             const firstMessage = chatMessagesContainer.querySelector('.message-item');
             const firstMessageId = firstMessage?.dataset.messageId;
             console.log("Loading older messages before:", firstMessageId || 'the beginning');
             sendWebSocketMessage(MSG_TYPE_LOAD_OLDER, { before_message_id: firstMessageId });
         }
    }

    function markAsReadIfNeeded(latestMessageId) {
         const threshold = 50;
         const isNearBottom = (chatMessagesContainer.scrollHeight - chatMessagesContainer.scrollTop - chatMessagesContainer.clientHeight < threshold);
         if (isNearBottom && latestMessageId) {
            console.debug("Near bottom, marking as read up to:", latestMessageId)
            sendWebSocketMessage('mark_read', { last_visible_message_id: latestMessageId });
         }
    }

    function handleMessageAck(clientId, serverId, timestamp) {
        console.log(`Message acknowledged: client_id=${clientId}, server_id=${serverId}`);
        // Optional: Update UI element with server ID, remove sending state
    }

    function handleMessageAckError(clientId) {
        console.error(`Message sending failed for client_id=${clientId}`);
        // Optional: Mark temporary UI element as failed
    }


    // --- Initialization ---
    console.log(`Chatting in room: ${roomSlug}`);
    connectWebSocket();
    attachEventListeners();
    scrollToBottom(true); // Scroll to bottom on initial load

}); // End DOMContentLoaded