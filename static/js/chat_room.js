document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Элементы ---
    const chatMessagesContainer = document.getElementById('chat-messages-container');
    const chatMessagesList = document.getElementById('chat-messages-list');
    const messageForm = document.getElementById('chat-message-form');
    const messageInput = document.getElementById('chat-message-input');
    const messageSubmitBtn = document.getElementById('chat-message-submit-btn');
    const onlineCountEl = document.getElementById('online-count');
    const onlineListEl = document.getElementById('online-list');
    const typingIndicatorPanel = document.getElementById('typing-indicator-panel');
    const loadOlderBtn = document.getElementById('load-older-messages-btn');
    const olderMessagesLoaderDiv = document.getElementById('older-messages-loader');
    const noMessagesPlaceholder = document.getElementById('no-messages-placeholder');
    const messageAnchor = document.getElementById('message-anchor'); // Для автопрокрутки

    // Элементы для ответа на сообщение
    const replyPreviewArea = document.getElementById('reply-preview-area');
    const replyPreviewUser = document.getElementById('reply-preview-user');
    const replyPreviewText = document.getElementById('reply-preview-text');
    const cancelReplyBtn = document.getElementById('cancel-reply-btn');
    const replyMessageIdHidden = document.getElementById('reply-message-id-hidden');

    // Элементы для прикрепления файла
    const fileInputTrigger = document.getElementById('chat-file-input-trigger'); // label
    const fileInput = document.getElementById('chat-file-input');
    const filePreviewArea = document.getElementById('file-preview-area');
    const filePreviewName = document.getElementById('file-preview-name');
    const filePreviewSize = document.getElementById('file-preview-size');
    const removeFileBtn = document.getElementById('remove-file-btn');

    // Мобильный сайдбар
    const openSidebarBtn = document.getElementById('open-sidebar-btn');
    const closeSidebarBtn = document.getElementById('close-sidebar-btn');
    const mobileSidebar = document.getElementById('mobile-sidebar');
    const mobileSidebarOverlay = document.getElementById('mobile-sidebar-overlay');


    // --- Состояние чата ---
    let chatSocket = null;
    let currentUser = { id: window.chatConfig.currentUserId, username: window.chatConfig.currentUsername };
    let oldestMessageId = null; // Для подгрузки старых сообщений
    let isLoadingOlderMessages = false;
    let hasMoreOlderMessages = window.chatConfig.initialMessagesCount >= window.chatConfig.messagesPageSize;
    let typingTimeout = null;
    let currentAttachedFile = null; // { file: File, base64: string }

    // --- Инициализация ---
    function init() {
        if (!messageInput || !chatMessagesList) {
            console.error('Chat UI elements not found. Chat cannot initialize.');
            return;
        }
        connectWebSocket();
        setupEventListeners();
        scrollToBottom(true); // true для мгновенной прокрутки
        updateLoadOlderButtonVisibility();
        autoResizeTextarea(messageInput);
        updateSubmitButtonState();
    }

    // --- WebSocket Логика ---
    function connectWebSocket() {
        const wsPath = window.djangoWsPath('chat', window.chatConfig.roomSlug);
        chatSocket = new WebSocket(wsPath);

        chatSocket.onopen = (e) => {
            console.log('Chat WebSocket connected.');
            // Можно запросить начальные данные, если они не передаются через Django context
            // Например, список онлайн пользователей, если он не был получен при первом рендере.
        };

        chatSocket.onmessage = (e) => {
            const data = JSON.parse(e.data);
            console.log('Data received:', data);
            handleWebSocketMessage(data);
        };

        chatSocket.onerror = (e) => {
            console.error('Chat WebSocket error:', e);
            // Показать пользователю сообщение об ошибке соединения
            displayGlobalError("Ошибка соединения с чатом. Попробуйте обновить страницу.");
        };

        chatSocket.onclose = (e) => {
            console.warn('Chat WebSocket closed. Code:', e.code, 'Reason:', e.reason);
            // Попытка переподключения через некоторое время или уведомление пользователя
            if (e.code !== 1000 && e.code !== 1005) { // Не закрыто чисто
                displayGlobalError("Соединение с чатом потеряно. Попытка переподключения через 5 секунд...");
                setTimeout(connectWebSocket, 5000);
            }
        };
    }

    function sendWebSocketMessage(type, payload = {}, client_id = null) {
        if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
            const message = { type: type, payload: payload };
            if (client_id) { // Для сообщений, ожидающих ACK
                message.payload.client_id = client_id;
            }
            chatSocket.send(JSON.stringify(message));
        } else {
            console.error('WebSocket is not connected.');
            displayGlobalError("Не удается отправить сообщение. Нет соединения с сервером.");
        }
    }

    function handleWebSocketMessage(data) {
        const type = data.type;
        const payload = data.payload || {}; // Убедимся, что payload есть

        switch (type) {
            case 'new_message': // MSG_TYPE_SERVER_NEW_MESSAGE
            case 'update_message': // MSG_TYPE_SERVER_UPDATE_MESSAGE
                handleNewOrUpdateMessage(payload, type === 'new_message');
                break;
            case 'reaction_update': // MSG_TYPE_SERVER_REACTION_UPDATE
                updateMessageReactions(payload.message_id, payload.reactions);
                break;
            case 'online_users_update': // MSG_TYPE_SERVER_ONLINE_USERS
                updateOnlineUsersList(payload.users);
                break;
            case 'older_messages_list': // MSG_TYPE_SERVER_OLDER_MESSAGES
                handleOlderMessages(payload.messages, payload.has_more, payload.client_id);
                break;
            case 'message_ack': // MSG_TYPE_SERVER_MESSAGE_ACK
                handleMessageAck(data.client_id, payload.server_id, payload.timestamp);
                break;
            case 'error_notification': // MSG_TYPE_SERVER_ERROR
                handleServerError(payload.message, data.client_id || payload.client_id);
                break;
            case 'typing_update': // MSG_TYPE_SERVER_TYPING_UPDATE
                handleTypingUpdate(payload.user, payload.is_typing);
                break;
            default:
                console.warn('Unknown WebSocket message type:', type);
        }
    }

    // --- Обработчики сообщений от сервера ---
    function handleNewOrUpdateMessage(messageData, isNew) {
        if (noMessagesPlaceholder) noMessagesPlaceholder.classList.add('hidden');

        const existingMessageEl = document.getElementById(`message-${messageData.id}`);
        if (existingMessageEl) { // Обновление существующего
            // Заменяем содержимое существующего элемента новым, отрендеренным
            // Это проще, чем обновлять отдельные части, но можно и так
            const tempDiv = document.createElement('div');
            // Предполагается, что у вас есть функция renderMessageToHTML
            tempDiv.innerHTML = renderMessageToHTML(messageData, currentUser.id);
            existingMessageEl.replaceWith(tempDiv.firstElementChild);
        } else if (isNew) { // Добавление нового
            const messageHTML = renderMessageToHTML(messageData, currentUser.id);
            chatMessagesList.insertAdjacentHTML('beforeend', messageHTML);
        }

        if (isNew || messageData.user.id === currentUser.id) {
             // Прокрутка вниз для новых сообщений или если это наше обновленное сообщение
            scrollToBottom();
        }
        // Обновляем oldestMessageId если это первое сообщение или старее текущего самого старого
        if (chatMessagesList.children.length > 0 && (!oldestMessageId || new Date(messageData.timestamp) < new Date(chatMessagesList.firstElementChild.dataset.timestamp || '9999-12-31'))) {
             const firstMessageEl = chatMessagesList.querySelector('.chat-message');
             if (firstMessageEl) oldestMessageId = firstMessageEl.dataset.messageId;
        }
    }

    function updateMessageReactions(messageId, reactionsSummary) {
        const messageEl = document.getElementById(`message-${messageId}`);
        if (!messageEl) return;

        const reactionsContainer = messageEl.querySelector('.reactions-container');
        if (!reactionsContainer) return;

        reactionsContainer.innerHTML = ''; // Очищаем старые реакции
        for (const emoji in reactionsSummary) {
            const reactionData = reactionsSummary[emoji];
            const reactionButton = document.createElement('button');
            reactionButton.className = `px-2 py-1 text-xs rounded-full border transition-colors
                                       ${reactionData.reacted_by_current_user
                                           ? 'bg-indigo-100 dark:bg-indigo-700/50 border-indigo-300 dark:border-indigo-600 text-indigo-700 dark:text-indigo-300'
                                           : 'bg-gray-100 dark:bg-dark-600 border-gray-300 dark:border-dark-500 text-gray-600 dark:text-gray-300 hover:border-indigo-400 dark:hover:border-indigo-500'
                                       }`;
            reactionButton.textContent = `${emoji} ${reactionData.count}`;
            reactionButton.title = reactionData.users.join(', ');
            reactionButton.dataset.emoji = emoji;
            reactionButton.dataset.messageId = messageId; // Для обработчика клика
            reactionButton.onclick = handleReactionClick; // Обработчик клика на реакцию
            reactionsContainer.appendChild(reactionButton);
        }
    }

    function updateOnlineUsersList(users) {
        if (onlineCountEl) onlineCountEl.textContent = users.length;
        if (onlineListEl) {
            if (users.length === 0) {
                onlineListEl.textContent = window.chatConfig.i18n.noOneOnline || 'Никого нет в сети';
                return;
            }
            // Показать несколько имен, остальных скрыть под "и еще N"
            const maxToShow = 3;
            let names = users.slice(0, maxToShow).map(u => u.display_name || u.username).join(', ');
            if (users.length > maxToShow) {
                names += ` ${window.chatConfig.i18n.andMore || 'и еще'} ${users.length - maxToShow}`;
            }
            onlineListEl.textContent = names;
            onlineListEl.title = users.map(u => u.display_name || u.username).join(', '); // Полный список в title
        }
    }

    function handleOlderMessages(messages, hasMore, clientId) {
        isLoadingOlderMessages = false;
        if (loadOlderBtn) loadOlderBtn.disabled = false;
        if (loadOlderBtn) loadOlderBtn.querySelector('i').classList.remove('fa-spin');

        if (messages.length > 0) {
            const currentScrollHeight = chatMessagesContainer.scrollHeight;
            messages.forEach(msgData => {
                const messageHTML = renderMessageToHTML(msgData, currentUser.id);
                chatMessagesList.insertAdjacentHTML('afterbegin', messageHTML);
            });
            // Сохраняем позицию скролла относительно старых сообщений
            chatMessagesContainer.scrollTop += (chatMessagesContainer.scrollHeight - currentScrollHeight);

            const firstMessageEl = chatMessagesList.querySelector('.chat-message');
            if (firstMessageEl) oldestMessageId = firstMessageEl.dataset.messageId;

        } else {
            // Если сообщений не пришло, но hasMore=true, возможно это конец истории для текущего фильтра
            // Если hasMore=false, то это точно конец истории
        }
        hasMoreOlderMessages = hasMore;
        updateLoadOlderButtonVisibility();
    }

    function handleMessageAck(clientId, serverId, timestamp) {
        console.log(`ACK received: client_id=${clientId}, server_id=${serverId}`);
        // Найти сообщение с client_id и обновить его ID на serverId,
        // или пометить как "доставлено".
        const tempMessage = document.querySelector(`.chat-message[data-client-id="${clientId}"]`);
        if (tempMessage) {
            tempMessage.id = `message-${serverId}`;
            tempMessage.dataset.messageId = serverId;
            tempMessage.classList.remove('opacity-70'); // Убрать индикатор "отправляется"
            // Обновить data-timestamp, если нужно
            const timeEl = tempMessage.querySelector('time');
            if (timeEl) timeEl.setAttribute('datetime', timestamp);
        }
    }

    function handleServerError(errorMessage, clientId) {
        // Показать ошибку пользователю. Если есть client_id, можно привязать к конкретному сообщению.
        console.error('Server error for client:', clientId, 'Message:', errorMessage);
        // Простой alert или более красивое уведомление
        displayGlobalError(`${window.chatConfig.i18n.serverError || "Ошибка сервера"}: ${errorMessage}`);

        if (clientId) { // Если ошибка связана с конкретным сообщением, удалить временное
            const tempMessage = document.querySelector(`.chat-message[data-client-id="${clientId}"]`);
            if (tempMessage) tempMessage.remove();
        }
    }

    let typingUsers = {}; // { userId: {username: 'name', timeoutId: id} }
    function handleTypingUpdate(userData, isTyping) {
        if (userData.id === currentUser.id) return; // Не показывать собственный статус печати

        if (isTyping) {
            if (typingUsers[userData.id] && typingUsers[userData.id].timeoutId) {
                clearTimeout(typingUsers[userData.id].timeoutId);
            }
            typingUsers[userData.id] = {
                username: userData.display_name || userData.username,
                timeoutId: setTimeout(() => {
                    delete typingUsers[userData.id];
                    renderTypingIndicator();
                }, 3000) // Если нет нового события typing в течение 3 сек, убираем
            };
        } else {
            if (typingUsers[userData.id]) {
                clearTimeout(typingUsers[userData.id].timeoutId);
                delete typingUsers[userData.id];
            }
        }
        renderTypingIndicator();
    }

    function renderTypingIndicator() {
        if (!typingIndicatorPanel) return;
        const usersTyping = Object.values(typingUsers).map(u => u.username);
        if (usersTyping.length === 0) {
            typingIndicatorPanel.innerHTML = '';
        } else if (usersTyping.length === 1) {
            typingIndicatorPanel.innerHTML = `<span class="italic">${usersTyping[0]} ${window.chatConfig.i18n.isTyping || 'печатает...'}</span>`;
        } else if (usersTyping.length <= 3) {
            typingIndicatorPanel.innerHTML = `<span class="italic">${usersTyping.join(', ')} ${window.chatConfig.i18n.areTyping || 'печатают...'}</span>`;
        } else {
            typingIndicatorPanel.innerHTML = `<span class="italic">${usersTyping.slice(0,2).join(', ')} ${window.chatConfig.i18n.andOthersAreTyping || 'и другие печатают...'}</span>`;
        }
    }


    // --- Отправка сообщений на сервер ---
    function sendMessage() {
        const content = messageInput.value.trim();
        const replyToId = replyMessageIdHidden.value;
        const tempClientId = `client-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

        if (!content && !currentAttachedFile) {
            return; // Не отправлять пустое сообщение без файла
        }

        // Оптимистичное добавление сообщения в UI
        const optimisticMessageData = {
            id: tempClientId, // Временный ID
            client_id: tempClientId,
            user: currentUser, // Используем данные текущего пользователя
            room_slug: window.chatConfig.roomSlug,
            content: content,
            file: currentAttachedFile ? { name: currentAttachedFile.file.name, size: currentAttachedFile.file.size, url: '#' } : null,
            timestamp: new Date().toISOString(),
            edited_at: null,
            is_deleted: false,
            reply_to: null, // TODO: Сделать предпросмотр ответа для оптимистичного сообщения
            reactions: {}
        };
        if (replyToId) { // Добавить инфо об ответе, если есть
            const replyPreviewUserText = replyPreviewUser.textContent;
            const replyPreviewContentText = replyPreviewText.textContent;
            optimisticMessageData.reply_to = {
                id: replyToId, // Важно для связи на сервере
                user: { username: replyPreviewUserText },
                content_preview: replyPreviewContentText,
                has_file: false, // Упрощенно для оптимистичного
                is_deleted: false
            };
        }

        const messageHTML = renderMessageToHTML(optimisticMessageData, currentUser.id);
        chatMessagesList.insertAdjacentHTML('beforeend', messageHTML);
        // Добавляем data-client-id для последующего обновления через ACK
        const addedEl = chatMessagesList.lastElementChild;
        if(addedEl) {
            addedEl.dataset.clientId = tempClientId;
            addedEl.classList.add('opacity-70'); // Индикатор отправки
        }
        if (noMessagesPlaceholder) noMessagesPlaceholder.classList.add('hidden');
        scrollToBottom();


        if (currentAttachedFile) {
            sendWebSocketMessage('send_file', { // MSG_TYPE_CLIENT_SEND_FILE
                file_data: currentAttachedFile.base64,
                filename: currentAttachedFile.file.name,
                content: content, // Текст к файлу
                reply_to_id: replyToId || null,
            }, tempClientId);
            clearAttachment();
        } else {
            sendWebSocketMessage('send_message', { // MSG_TYPE_CLIENT_SEND_MESSAGE
                content: content,
                reply_to_id: replyToId || null,
            }, tempClientId);
        }

        // Очистка поля ввода и состояния ответа
        messageInput.value = '';
        messageInput.style.height = 'auto'; // Сброс высоты textarea
        messageInput.focus();
        clearReply();
        sendTypingStatus(false); // Сообщить, что перестали печатать
        updateSubmitButtonState();
    }

    function sendEditMessage(messageId, newContent) {
        const tempClientId = `client-edit-${Date.now()}`;
        sendWebSocketMessage('edit_message', { // MSG_TYPE_CLIENT_EDIT_MESSAGE
            message_id: messageId,
            content: newContent,
        }, tempClientId);
        // Оптимистичное обновление можно сделать, но сложнее из-за модального окна
    }

    function sendDeleteMessage(messageId) {
        const tempClientId = `client-delete-${Date.now()}`;
        sendWebSocketMessage('delete_message', { // MSG_TYPE_CLIENT_DELETE_MESSAGE
            message_id: messageId,
        }, tempClientId);
        // Оптимистичное обновление: найти сообщение и пометить как удаленное
        // const msgEl = document.getElementById(`message-${messageId}`);
        // if (msgEl) { msgEl.querySelector('.message-text-content').textContent = window.chatConfig.i18n.messageDeleted; ... }
    }

    function sendReaction(messageId, emoji, add = true) {
        sendWebSocketMessage(add ? 'add_reaction' : 'remove_reaction', { // MSG_TYPE_CLIENT_ADD_REACTION / REMOVE_REACTION
            message_id: messageId,
            emoji: emoji,
        });
        // Оптимистичное обновление UI для реакции (добавить/убрать класс, изменить счетчик)
    }

    function sendTypingStatus(isTyping) {
        sendWebSocketMessage('typing_status', { is_typing: isTyping }); // MSG_TYPE_CLIENT_TYPING
    }

    function loadOlderMessages() {
        if (isLoadingOlderMessages || !hasMoreOlderMessages) return;

        isLoadingOlderMessages = true;
        if (loadOlderBtn) {
            loadOlderBtn.disabled = true;
            const icon = loadOlderBtn.querySelector('i');
            if(icon) icon.classList.add('fa-spin');
            loadOlderBtn.childNodes[loadOlderBtn.childNodes.length -1].textContent = ` ${window.chatConfig.i18n.loadingOlder || 'Загрузка...'}`;
        }

        const tempClientId = `client-load-${Date.now()}`; // Если нужен ACK для этого
        sendWebSocketMessage('load_older_messages', { // MSG_TYPE_CLIENT_LOAD_OLDER
            before_message_id: oldestMessageId,
            limit: window.chatConfig.messagesPageSize
        }, tempClientId);
    }

    // --- UI Вспомогательные функции ---
    function renderMessageToHTML(msgData, currentUserId) {
        // Эта функция должна генерировать HTML для одного сообщения,
        // аналогично вашему Django шаблону room/partials/message_item.html
        // Это самая сложная часть для рендеринга на клиенте.
        // Для простоты, можно сделать AJAX запрос к Django view,
        // который вернет отрендеренный HTML для сообщения. Но это медленнее.
        // Прямой рендеринг в JS - быстрее, но требует дублирования логики шаблона.

        const isOwn = String(msgData.user.id) === String(currentUserId);
        let avatarHTML = '';
        if (msgData.user.avatar_url) {
            avatarHTML = `<img src="${msgData.user.avatar_url}" alt="${msgData.user.username}" class="w-8 h-8 rounded-full object-cover">`;
        } else {
            avatarHTML = `<span class="w-8 h-8 rounded-full bg-gray-300 dark:bg-dark-600 flex items-center justify-center text-sm font-semibold text-gray-600 dark:text-gray-300">${msgData.user.username.slice(0,1).toUpperCase()}</span>`;
        }

        let replyHTML = '';
        if (msgData.reply_to) {
            replyHTML = `
                <a href="#message-${msgData.reply_to.id}" class="block mb-1.5 p-2 -mx-1.5 rounded-lg text-xs ${isOwn ? 'bg-indigo-500/80 hover:bg-indigo-500/100 dark:bg-indigo-700/50 dark:hover:bg-indigo-700/80' : 'bg-gray-100 hover:bg-gray-200 dark:bg-dark-600 dark:hover:bg-dark-500'} opacity-90 hover:opacity-100 transition">
                    <p class="font-medium ${isOwn ? 'text-indigo-100' : 'text-gray-700 dark:text-gray-200'}">
                        ${window.chatConfig.i18n.replyTo || 'Ответ на:'} ${msgData.reply_to.user.username}
                    </p>
                    <p class="italic truncate ${isOwn ? 'text-indigo-200' : 'text-gray-500 dark:text-gray-400'}">
                        ${escapeHTML(msgData.reply_to.content_preview) || (msgData.reply_to.has_file ? window.chatConfig.i18n.file || '[Файл]' : '')}
                    </p>
                </a>`;
        }

        let fileHTML = '';
        if (msgData.file && msgData.file.url && msgData.file.url !== '#') {
            const fileSizeFormatted = msgData.file.size ? `(${(msgData.file.size / 1024).toFixed(1)} KB)` : '';
            fileHTML = `
                <div class="mb-1">
                    <a href="${msgData.file.url}" target="_blank" class="inline-flex items-center p-2 rounded-lg ${isOwn ? 'bg-indigo-500/80 hover:bg-indigo-500/100 text-indigo-50 dark:bg-indigo-700/50 dark:hover:bg-indigo-700/80' : 'bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-dark-600 dark:hover:bg-dark-500 dark:text-gray-200'}">
                        <i class="fas fa-file-alt mr-2"></i>
                        <span>${escapeHTML(msgData.file.name)}</span>
                        <span class="text-xs ml-2 opacity-70">${fileSizeFormatted}</span>
                    </a>
                </div>`;
        }

        let contentHTML = '';
        if (msgData.is_deleted) {
            contentHTML = `<p class="italic text-sm ${isOwn ? 'text-indigo-200' : 'text-gray-500 dark:text-gray-400'}">${window.chatConfig.i18n.messageDeleted || "Сообщение удалено"}</p>`;
        } else {
            contentHTML = `<p class="text-sm whitespace-pre-wrap message-text-content">${escapeHTML(msgData.content)}</p>`;
        }

        // Классы для кнопок действий
        const actionButtonClasses = isOwn
            ? 'child:text-indigo-200 child:hover:text-white child-dark:text-indigo-300 child-dark:hover:text-indigo-100'
            : 'child:text-gray-400 child:hover:text-gray-600 child-dark:text-gray-500 child-dark:hover:text-gray-300';

        let editDeleteActions = '';
        if (String(msgData.user.id) === String(currentUser.id) && !msgData.is_deleted) {
            editDeleteActions = `
                <button class="action-edit" title="${window.chatConfig.i18n.edit || 'Редактировать'}"><i class="fas fa-pen fa-xs"></i></button>
                <button class="action-delete" title="${window.chatConfig.i18n.delete || 'Удалить'}"><i class="fas fa-trash-alt fa-xs"></i></button>
            `;
        }

        const messageTimestamp = new Date(msgData.timestamp);
        const formattedTime = `${messageTimestamp.getHours().toString().padStart(2,'0')}:${messageTimestamp.getMinutes().toString().padStart(2,'0')}`;
        const editedAtTitle = msgData.edited_at ? new Date(msgData.edited_at).toLocaleString() : '';
        const editedAtHTML = msgData.edited_at ? `<span class="italic ml-1" title="${editedAtTitle}">(${window.chatConfig.i18n.edited || 'ред.'})</span>` : '';

        return `
            <div class="chat-message group flex items-end mb-3 ${isOwn ? 'justify-end' : ''}" id="message-${msgData.id}" data-message-id="${msgData.id}" data-user-id="${msgData.user.id}" data-timestamp="${msgData.timestamp}">
                ${!isOwn ? `<div class="flex-shrink-0 mr-2">${avatarHTML}</div>` : ''}
                <div class="message-content max-w-xs lg:max-w-md break-words">
                    <div class="px-3.5 py-2.5 rounded-2xl shadow ${isOwn ? 'bg-indigo-600 text-white dark:bg-indigo-600 rounded-br-none' : 'bg-white text-gray-700 dark:bg-dark-700 dark:text-gray-100 border border-gray-200 dark:border-dark-600 rounded-bl-none'}">
                        ${!isOwn ? `<p class="text-xs font-semibold mb-0.5 ${isOwn ? 'text-indigo-200 dark:text-indigo-300' : 'text-indigo-600 dark:text-indigo-400'}">${escapeHTML(msgData.user.username)}</p>`: ''}
                        ${replyHTML}
                        ${fileHTML}
                        ${contentHTML}
                        <div class="message-meta text-xs mt-1.5 flex justify-between items-center ${isOwn ? 'text-indigo-200 dark:text-indigo-300 opacity-80' : 'text-gray-400 dark:text-gray-500'}">
                            <span>
                                <time datetime="${msgData.timestamp}">${formattedTime}</time>
                                ${editedAtHTML}
                            </span>
                            <div class="message-actions ml-2 opacity-0 group-hover:opacity-100 transition-opacity flex items-center space-x-1.5 ${actionButtonClasses}">
                                <button class="action-reply" title="${window.chatConfig.i18n.reply || 'Ответить'}"><i class="fas fa-reply fa-xs"></i></button>
                                <button class="action-react" title="${window.chatConfig.i18n.react || 'Реагировать'}"><i class="far fa-smile fa-xs"></i></button>
                                ${editDeleteActions}
                            </div>
                        </div>
                    </div>
                    <div class="reactions-container mt-1 flex flex-wrap gap-1 ${isOwn ? 'justify-end pr-1' : 'pl-1'}" data-message-id="${msgData.id}">
                        ${renderReactionsToHTML(msgData.id, msgData.reactions)}
                    </div>
                </div>
                ${isOwn ? `<div class="flex-shrink-0 ml-2">${avatarHTML}</div>` : ''}
            </div>
        `;
    }
    function renderReactionsToHTML(messageId, reactionsSummary) {
        let html = '';
        if (!reactionsSummary) return html;
        for (const emoji in reactionsSummary) {
            const reactionData = reactionsSummary[emoji];
            html += `
                <button class="reaction-btn px-2 py-1 text-xs rounded-full border transition-colors
                               ${reactionData.reacted_by_current_user
                                   ? 'bg-indigo-100 dark:bg-indigo-700/50 border-indigo-300 dark:border-indigo-600 text-indigo-700 dark:text-indigo-300'
                                   : 'bg-gray-100 dark:bg-dark-600 border-gray-300 dark:border-dark-500 text-gray-600 dark:text-gray-300 hover:border-indigo-400 dark:hover:border-indigo-500'
                               }"
                        title="${escapeHTML(reactionData.users.join(', '))}"
                        data-emoji="${escapeHTML(emoji)}"
                        data-message-id="${messageId}">
                    ${escapeHTML(emoji)} ${reactionData.count}
                </button>
            `;
        }
        return html;
    }


    function scrollToBottom(instant = false) {
        if (chatMessagesContainer) {
            // Прокручиваем только если пользователь уже внизу или близко к низу,
            // чтобы не мешать ему читать старые сообщения.
            // Допуск в пикселях, чтобы считать "внизу"
            const SCROLL_THRESHOLD = 100;
            const isScrolledToBottom = chatMessagesContainer.scrollHeight - chatMessagesContainer.clientHeight <= chatMessagesContainer.scrollTop + SCROLL_THRESHOLD;

            if (isScrolledToBottom || instant) {
                // messageAnchor.scrollIntoView({ behavior: instant ? 'instant' : 'smooth', block: 'end' });
                // Или просто
                 chatMessagesContainer.scrollTo({
                    top: chatMessagesContainer.scrollHeight,
                    behavior: instant ? 'instant' : 'smooth'
                });
            }
        }
    }

    function updateLoadOlderButtonVisibility() {
        if (olderMessagesLoaderDiv && loadOlderBtn) {
            if (hasMoreOlderMessages) {
                olderMessagesLoaderDiv.classList.remove('hidden');
                loadOlderBtn.disabled = isLoadingOlderMessages;
                loadOlderBtn.childNodes[loadOlderBtn.childNodes.length -1].textContent = ` ${isLoadingOlderMessages ? (window.chatConfig.i18n.loadingOlder || 'Загрузка...') : (window.chatConfig.i18n.loadOlderButton || 'Загрузить еще...')}`;
                if(isLoadingOlderMessages) loadOlderBtn.querySelector('i').classList.add('fa-spin'); else loadOlderBtn.querySelector('i').classList.remove('fa-spin');

            } else {
                olderMessagesLoaderDiv.classList.add('hidden');
            }
        }
    }

    function autoResizeTextarea(textarea) {
        textarea.style.height = 'auto'; // Сначала сбросить высоту
        // Установить высоту на основе scrollHeight, но не более максимальной
        let newHeight = Math.min(textarea.scrollHeight, parseInt(textarea.style.maxHeight) || 120);
        textarea.style.height = newHeight + 'px';
    }

    function setupReply(messageId, username, textContent) {
        replyMessageIdHidden.value = messageId;
        replyPreviewUser.textContent = username;
        replyPreviewText.textContent = textContent.substring(0, 50) + (textContent.length > 50 ? '...' : '');
        replyPreviewArea.classList.remove('hidden');
        messageInput.focus();
    }
    function clearReply() {
        replyMessageIdHidden.value = '';
        replyPreviewArea.classList.add('hidden');
    }

    function attachFile(file) {
        if (!file) return;
        // Проверка размера и типа файла (базовая на клиенте, основная на сервере)
        if (file.size > (window.chatConfig.maxFileSizeMb || 5) * 1024 * 1024) {
            displayGlobalError(`Файл слишком большой (макс. ${window.chatConfig.maxFileSizeMb || 5} MB)`);
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            currentAttachedFile = {
                file: file,
                base64: e.target.result.split(',')[1] // Убираем "data:mime/type;base64,"
            };
            filePreviewName.textContent = file.name;
            filePreviewSize.textContent = `(${(file.size / 1024).toFixed(1)} KB)`;
            filePreviewArea.classList.remove('hidden');
            updateSubmitButtonState();
        };
        reader.onerror = (e) => {
            console.error("FileReader error:", e);
            displayGlobalError("Не удалось прочитать файл.");
            clearAttachment();
        };
        reader.readAsDataURL(file);
    }
    function clearAttachment() {
        currentAttachedFile = null;
        fileInput.value = ''; // Сброс input type=file
        filePreviewArea.classList.add('hidden');
        updateSubmitButtonState();
    }

    function updateSubmitButtonState() {
        const hasText = messageInput.value.trim().length > 0;
        const hasAttachment = !!currentAttachedFile;
        messageSubmitBtn.disabled = !hasText && !hasAttachment;
    }

    function displayGlobalError(message) {
        // TODO: Реализовать более красивое отображение глобальных ошибок (например, toast-уведомление)
        alert(message);
    }

    function escapeHTML(str) {
        if (str === null || str === undefined) return '';
        return String(str).replace(/[&<>"']/g, function (match) {
            return {
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            }[match];
        });
    }

    // --- Обработчики событий DOM ---
    function setupEventListeners() {
        messageForm.addEventListener('submit', (e) => {
            e.preventDefault();
            sendMessage();
        });

        messageInput.addEventListener('input', () => {
            autoResizeTextarea(messageInput);
            updateSubmitButtonState();
            // Логика "печатает..."
            if (typingTimeout) clearTimeout(typingTimeout);
            sendTypingStatus(true);
            typingTimeout = setTimeout(() => {
                sendTypingStatus(false);
            }, 2000); // Если не печатает 2 секунды, статус "не печатает"
        });
        messageInput.addEventListener('keypress', (e) => {
            // Отправка по Enter, если не зажат Shift
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        if (chatMessagesContainer) {
            chatMessagesContainer.addEventListener('scroll', () => {
                if (chatMessagesContainer.scrollTop === 0 && hasMoreOlderMessages && !isLoadingOlderMessages) {
                    loadOlderMessages();
                }
            });
        }
        if (loadOlderBtn) {
            loadOlderBtn.addEventListener('click', loadOlderMessages);
        }

        // Обработчики для действий с сообщениями (делегирование событий)
        chatMessagesList.addEventListener('click', (e) => {
            const target = e.target;
            const messageAction = target.closest('button[class*="action-"]');
            if (messageAction) {
                const messageEl = target.closest('.chat-message');
                const messageId = messageEl.dataset.messageId;

                if (messageAction.classList.contains('action-reply')) {
                    const userEl = messageEl.querySelector('.text-xs.font-semibold'); // Имя пользователя
                    const contentEl = messageEl.querySelector('.message-text-content'); // Текст сообщения
                    setupReply(messageId, userEl ? userEl.textContent.trim() : 'User', contentEl ? contentEl.textContent.trim() : '[Файл]');
                } else if (messageAction.classList.contains('action-edit')) {
                    const contentEl = messageEl.querySelector('.message-text-content');
                    const currentContent = contentEl ? contentEl.textContent : '';
                    // TODO: Показать модальное окно для редактирования
                    const newContent = prompt(window.chatConfig.i18n.editMessagePrompt || "Введите новый текст сообщения:", currentContent);
                    if (newContent !== null && newContent.trim() !== currentContent.trim()) {
                        sendEditMessage(messageId, newContent.trim());
                    }
                } else if (messageAction.classList.contains('action-delete')) {
                    // TODO: Показать подтверждение удаления
                    if (confirm(window.chatConfig.i18n.confirmDeleteMessage || "Вы уверены, что хотите удалить это сообщение?")) {
                        sendDeleteMessage(messageId);
                    }
                } else if (messageAction.classList.contains('action-react')) {
                    // TODO: Показать пикер эмодзи
                    const emoji = prompt(window.chatConfig.i18n.reactPrompt || "Введите эмодзи для реакции:", "👍");
                    if (emoji && emoji.trim()) {
                        sendReaction(messageId, emoji.trim(), true);
                    }
                }
            }
            // Клик по самой реакции (для удаления/добавления своей)
            const reactionBtn = target.closest('button.reaction-btn');
            if (reactionBtn) {
                handleReactionClick(e);
            }
        });

        // Реакции
        function handleReactionClick(event) {
            const button = event.currentTarget; // или event.target.closest('button.reaction-btn');
            const messageId = button.dataset.messageId;
            const emoji = button.dataset.emoji;
            const alreadyReacted = button.classList.contains('bg-indigo-100') || button.classList.contains('dark:bg-indigo-700/50'); // Проверка по стилю

            sendReaction(messageId, emoji, !alreadyReacted); // Toggle reaction
        }


        if (cancelReplyBtn) {
            cancelReplyBtn.addEventListener('click', clearReply);
        }

        // Файлы
        if (fileInputTrigger) {
            fileInputTrigger.addEventListener('click', () => fileInput.click()); // Клик по label триггерит input
        }
        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files[0]) {
                    attachFile(e.target.files[0]);
                }
            });
        }
        if (removeFileBtn) {
            removeFileBtn.addEventListener('click', clearAttachment);
        }

        // Мобильный сайдбар
        if (openSidebarBtn) {
            openSidebarBtn.addEventListener('click', () => mobileSidebar.classList.remove('hidden'));
        }
        if (closeSidebarBtn) {
            closeSidebarBtn.addEventListener('click', () => mobileSidebar.classList.add('hidden'));
        }
        if (mobileSidebarOverlay) {
            mobileSidebarOverlay.addEventListener('click', () => mobileSidebar.classList.add('hidden'));
        }
    }

    // --- Запуск ---
    init();

}); // Конец DOMContentLoaded