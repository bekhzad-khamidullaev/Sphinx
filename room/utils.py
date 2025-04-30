# room/utils.py
import redis.asyncio as redis
import logging
from django.conf import settings

logger = logging.getLogger(__name__)
redis_pool = None # Global pool instance

async def get_redis_connection():
    """ Creates or reuses an async Redis connection pool. """
    global redis_pool
    if redis_pool:
        try:
            # Test connection validity before returning (optional but good)
            conn = redis.Redis(connection_pool=redis_pool)
            await conn.ping()
            # logger.debug("Reusing existing Redis connection pool.")
            return conn # Return a connection instance from the pool
        except Exception as e:
            logger.warning(f"Existing Redis pool connection failed ping: {e}. Recreating pool.")
            redis_pool = None # Force recreation

    redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0') # Default URL
    logger.info(f"Creating new Redis connection pool for URL: {redis_url}")
    try:
        # Create pool with appropriate settings
        redis_pool = redis.BlockingConnectionPool.from_url(
            redis_url,
            max_connections=getattr(settings, 'REDIS_MAX_CONNECTIONS', 20), # Make configurable
            timeout=5 # Connection timeout
        )
        # Return a connection instance
        return redis.Redis(connection_pool=redis_pool)
    except Exception as e:
        logger.exception(f"FATAL: Could not create Redis connection pool for {redis_url}: {e}")
        return None

# Note: When using pooling, you typically don't explicitly close connections obtained
# from redis.Redis(connection_pool=pool), as closing returns it to the pool.
# The consumer code's explicit .close() might need adjustment if using pooling strictly.
# However, redis-py handles this reasonably well.