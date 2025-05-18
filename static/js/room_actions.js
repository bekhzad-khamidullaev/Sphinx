// static/js/room_actions.js

document.addEventListener('DOMContentLoaded', () => {
    const i18n = window.chatConfig?.i18n || {}; // Получаем строки локализации

    // --- Helper function to get CSRF token ---
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    const csrfToken = getCookie('csrftoken');

    // --- Archive Room Functionality ---
    // Кнопка может быть не только в room_detail, но и в других местах,
    // поэтому используем делегирование событий или ищем все такие кнопки.
    // Для простоты, если кнопка только одна на странице room_detail.html:
    const archiveRoomButton = document.getElementById('archive-room-btn');

    if (archiveRoomButton) {
        archiveRoomButton.addEventListener('click', function() {
            const roomSlug = this.dataset.roomSlug;
            const roomName = this.dataset.roomName; // Используем для сообщения подтверждения
            const archiveUrl = this.dataset.url || `/rooms/${roomSlug}/archive/`; // Берем URL из data-атрибута или строим

            const confirmMessage = (i18n.confirmArchiveRoom || 'Вы уверены, что хотите заархивировать комнату "%s"?').replace('%s', roomName);

            if (confirm(confirmMessage)) {
                fetch(archiveUrl, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': csrfToken,
                        'X-Requested-With': 'XMLHttpRequest', // Важно для Django, чтобы отличить AJAX
                        'Accept': 'application/json',
                        'Content-Type': 'application/json' // Если отправляем JSON, иначе не нужно
                    },
                    // body: JSON.stringify({}), // Если сервер ожидает какой-то JSON payload
                })
                .then(response => {
                    if (!response.ok) {
                        // Попытаемся прочитать ошибку из JSON, если сервер ее так отдает
                        return response.json().then(errData => {
                            throw new Error(errData.error || `Server responded with ${response.status}`);
                        }).catch(() => { // Если тело ответа не JSON или пустое
                            throw new Error(`Server responded with ${response.status}`);
                        });
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        Toastify({
                            text: data.message || (i18n.roomArchivedSuccess || "Комната успешно архивирована."),
                            duration: 3000,
                            gravity: "top",
                            position: "right",
                            backgroundColor: "linear-gradient(to right, #00b09b, #96c93d)",
                        }).showToast();
                        // Перенаправление на список комнат или обновление UI
                        // Для простоты - перенаправление:
                        if (window.location.pathname.includes(`/rooms/${roomSlug}`)) {
                             // Если мы на странице самой комнаты, перенаправляем на список
                             window.location.href = "{% url 'room:rooms' %}"; // Нужно, чтобы Django обработал этот тег
                                                                            // или передавать URL списка комнат через data-атрибут/JS config
                        } else {
                            // Если мы на другой странице (например, список комнат),
                            // можно попытаться удалить элемент комнаты из DOM
                            const roomCard = document.getElementById(`room-card-${roomSlug}`); // Если карточки имеют такой ID
                            if (roomCard) {
                                roomCard.style.opacity = '0.5'; // Визуальный эффект
                                setTimeout(() => roomCard.remove(), 500);
                            } else {
                                // Если карточку не нашли, просто перезагружаем для обновления списка
                                window.location.reload();
                            }
                        }
                    } else {
                        Toastify({
                            text: data.error || (i18n.archiveRoomError || "Ошибка архивирования комнаты."),
                            duration: 3000,
                            gravity: "top",
                            position: "right",
                            backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                        }).showToast();
                    }
                })
                .catch(error => {
                    console.error('Error archiving room:', error);
                    Toastify({
                        text: i18n.serverError || "Произошла ошибка сервера.",
                        duration: 3000,
                        gravity: "top",
                        position: "right",
                        backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
                    }).showToast();
                });
            }
        });
    } else {
        // console.debug("Archive room button not found on this page.");
    }

    // Здесь можно добавить другую логику, связанную с действиями над комнатами,
    // например, "Покинуть комнату", "Пригласить пользователя" и т.д.,
    // если для них есть соответствующие кнопки и API эндпоинты.

});