# room/utils.py
import redis.asyncio as redis
import logging
import re
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import base64

logger = logging.getLogger(__name__)
redis_pool = None

async def get_redis_connection():
    """
    Возвращает асинхронное соединение с Redis из пула.
    Пул создается при первом вызове.
    """
    global redis_pool
    if redis_pool:
        try:
            # Простая проверка работоспособности пула перед возвратом соединения
            conn_test = redis.Redis(connection_pool=redis_pool)
            await conn_test.ping()
            # logger.debug("Reusing existing Redis connection pool.")
            return conn_test # Возвращаем новое соединение из существующего пула
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, Exception) as e:
            logger.warning(f"Existing Redis pool connection failed: {e}. Recreating pool.")
            await close_redis_pool() # Закрываем старый пул
            redis_pool = None # Сбрасываем, чтобы пересоздать

    redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/1')
    # decode_responses=True - Redis будет возвращать строки, а не байты
    # Это важно для работы с ID пользователей и другими строковыми данными.
    logger.info(f"Creating new Redis connection pool for URL: {redis_url} (decode_responses=True)")
    try:
        redis_pool = redis.ConnectionPool.from_url(
            redis_url,
            max_connections=getattr(settings, 'REDIS_MAX_CONNECTIONS', 20), # Из настроек или дефолт
            decode_responses=True # <--- ВАЖНО
        )
        # Возвращаем новое соединение, созданное из только что созданного пула
        return redis.Redis(connection_pool=redis_pool)
    except Exception as e:
        logger.exception(f"FATAL: Could not create Redis connection pool for {redis_url}: {e}")
        return None

async def close_redis_pool():
    """ Закрывает существующий пул соединений Redis. """
    global redis_pool
    if redis_pool:
        logger.info("Closing Redis connection pool.")
        # У ConnectionPool в redis-py нет awaitable close(), используется dispose()
        # Для redis.asyncio.ConnectionPool используется disconnect()
        await redis_pool.disconnect()
        redis_pool = None


def get_room_online_users_redis_key(room_slug: str) -> str:
    """ Генерирует ключ для Redis set, хранящего ID онлайн пользователей в комнате. """
    # Очистка слага для безопасности ключа Redis
    safe_slug = re.sub(r'[^a-zA-Z0-9_-]', '', room_slug)
    return f"chat:room:{safe_slug}:online_users"


class FileUploadValidator:
    def __init__(self, file_data_base64: str, filename: str):
        self.file_data_base64 = file_data_base64
        self.filename = filename
        self.max_size = getattr(settings, 'MAX_FILE_UPLOAD_SIZE_BYTES', 5 * 1024 * 1024)
        self.allowed_types = getattr(settings, 'ALLOWED_FILE_TYPES', []) # Список MIME типов

    def validate(self):
        if not self.file_data_base64 or not self.filename:
            raise ValidationError(_("Отсутствуют данные файла или имя файла."))

        try:
            decoded_file = base64.b64decode(self.file_data_base64)
        except (TypeError, ValueError):
            raise ValidationError(_("Некорректные данные файла (ошибка декодирования Base64)."))

        if len(decoded_file) > self.max_size:
            raise ValidationError(
                _("Файл слишком большой. Максимальный размер: %(size)s MB.") %
                {'size': self.max_size // (1024 * 1024)}
            )

        # Проверка типа файла (если ALLOWED_FILE_TYPES заданы)
        # Для этого нужна библиотека python-magic или анализ расширения файла,
        # что менее надежно. Здесь простой пример по расширению, для продакшена лучше python-magic.
        if self.allowed_types:
            import mimetypes
            mimetype, _ = mimetypes.guess_type(self.filename)
            if not mimetype or mimetype.lower() not in [t.lower() for t in self.allowed_types]:
                # Более сложная проверка с `magic`
                # import magic
                # detected_mimetype = magic.from_buffer(decoded_file, mime=True)
                # if detected_mimetype.lower() not in [t.lower() for t in self.allowed_types]:
                raise ValidationError(
                    _("Недопустимый тип файла: %(filename)s. Разрешенные типы: %(types)s") %
                    {'filename': self.filename, 'types': ", ".join(self.allowed_types)}
                )
        return decoded_file