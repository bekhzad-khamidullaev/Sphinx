"use strict";

// Функция для управления прелоадером
function handlePreloader() {
    const preloader = document.getElementById('preloader');
    if (!preloader) return;

    console.log('Preloader initialization');

    // Функция для скрытия прелоадера
    const hidePreloader = () => {
        console.log('Hiding preloader');
        preloader.style.opacity = '0';
        
        // Обработчик, который сработает один раз после завершения анимации
        const onTransitionEnd = () => {
            console.log('Preloader transition ended');
            preloader.style.display = 'none';
            preloader.removeEventListener('transitionend', onTransitionEnd);
        };
        
        preloader.addEventListener('transitionend', onTransitionEnd);
    };

    // Скрываем прелоадер при полной загрузке страницы
    window.addEventListener('load', () => {
        console.log('Window loaded event');
        setTimeout(hidePreloader, 300); // Небольшая задержка для плавности
    });

    // Запасной вариант: скрыть через 5 секунд в любом случае
    const backupTimeout = setTimeout(() => {
        console.warn('Using backup preloader hide');
        hidePreloader();
    }, 5000);

    // Очистка таймера при успешной загрузке
    window.addEventListener('load', () => {
        clearTimeout(backupTimeout);
    });
}

// Инициализация темной темы
function setupDarkModeToggle() {
    const toggleBtn = document.getElementById('darkModeToggle');
    if (!toggleBtn) return;

    toggleBtn.addEventListener('click', () => {
        document.documentElement.classList.toggle('dark');
        localStorage.setItem('darkMode', document.documentElement.classList.contains('dark'));
    });

    // Восстановление темы при загрузке
    if (localStorage.getItem('darkMode') === 'true') {
        document.documentElement.classList.add('dark');
    }
}

// Установка текущего года в футере
function setCurrentYear() {
    const yearElement = document.getElementById('year');
    if (yearElement) {
        yearElement.textContent = new Date().getFullYear();
    }
}

document.addEventListener('DOMContentLoaded', function () {
    console.log("DOM fully loaded and parsed");
    
    try {
        setupDarkModeToggle();
        setCurrentYear();
        handlePreloader();
        
        // Инициализация Flowbite, если подключен
        if (typeof initFlowbite === 'function') { 
            initFlowbite(); 
        }
    } catch (error) {
        console.error("Initialization error:", error);
        // Гарантированно скрываем прелоадер при ошибке
        const preloader = document.getElementById('preloader');
        if (preloader) preloader.style.display = 'none';
    }
});

// Добавляем функцию в глобальную область видимости
window.showNotification = function(message, type = 'info') {
    console.log(`Notification (${type}): ${message}`);
    // ... существующая реализация showNotification ...
};