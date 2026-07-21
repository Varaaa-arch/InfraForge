import redis
from loguru import logger

from app.config import settings 

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True,
    socket_timeout=2,  # Set a timeout for socket operations
)

def check_redis_connection() -> bool: 
    try:
        redis_client.ping()
        logger.info("Redis Connections successful.")
        return True
    except redis.ConnectionError as e:
        logger.warning(f"Redis connection failed: {e}")
        return False 
    
    