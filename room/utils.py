# filename: room/utils.py
import redis.asyncio as redis
from django.conf import settings

async def get_redis_connection():
    """ Creates an async Redis connection using settings. """
    try:
        # Assumes REDIS_URL is defined in settings like 'redis://localhost:6379/0'
        if hasattr(settings, 'REDIS_URL'):
            return await redis.from_url(settings.REDIS_URL)
        else:
            # Fallback to default localhost if not configured
            print("Warning: REDIS_URL not found in settings. Falling back to default localhost:6379.")
            return await redis.Redis(host='localhost', port=6379, db=0)
    except Exception as e:
        print(f"Error connecting to Redis: {e}")
        return None