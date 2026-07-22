import json
import hashlib
from typing import Any, Optional
from loguru import logger
from redis.asyncio import Redis
import redis

from app.core.config import settings


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    from uuid import UUID
    from datetime import datetime, date
    from decimal import Decimal
    from enum import Enum
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Type {type(obj)} not serializable")



class RedisCache:
    """
    Distributed Redis Caching interface for storing company profiles, financial statements,
    embeddings, and general AI/RAG summaries.
    """
    def __init__(self):
        self.host = settings.REDIS_HOST
        self.port = settings.REDIS_PORT
        self.password = settings.REDIS_PASSWORD
        self.client: Optional[Redis] = None
        self.sync_client: Optional[redis.Redis] = None
        self.enabled = False

        if self.host:
            try:
                self.client = Redis(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                    decode_responses=True,
                    socket_timeout=1.0,
                )
                self.sync_client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                    decode_responses=True,
                    socket_timeout=1.0,
                )
                self.enabled = True
                logger.info(f"RedisCache initialized connecting to {self.host}:{self.port}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis caching layer: {e}")
                self.enabled = False

    def _recreate_client(self):
        try:
            self.client = Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                decode_responses=True,
                socket_timeout=1.0,
            )
            logger.info("RedisCache async client re-created due to closed event loop.")
        except Exception as e:
            logger.error(f"Failed to recreate RedisCache async client: {e}")

    async def get(self, key: str) -> Optional[Any]:
        """Fetch value from cache. Deserializes JSON if applicable."""
        if not self.enabled or not self.client:
            return None
        try:
            val = await self.client.get(key)
            if val is not None:
                logger.bind(key=key).debug("Cache HIT")
                return json.loads(val)
        except Exception as e:
            if "Event loop is closed" in str(e):
                self._recreate_client()
                try:
                    val = await self.client.get(key)
                    if val is not None:
                        logger.bind(key=key).debug("Cache HIT after client recreation")
                        return json.loads(val)
                except Exception as re:
                    logger.error(f"Redis get retry failed: {re}")
            else:
                logger.error(f"Redis get failed: {e}")
        return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Store serialized value in cache with a TTL in seconds."""
        if not self.enabled or not self.client:
            return False
        try:
            serialized = json.dumps(value, default=json_serial)
            await self.client.set(key, serialized, ex=ttl)
            logger.bind(key=key, ttl=ttl).debug("Cache SET")
            return True
        except Exception as e:
            if "Event loop is closed" in str(e):
                self._recreate_client()
                try:
                    serialized = json.dumps(value, default=json_serial)
                    await self.client.set(key, serialized, ex=ttl)
                    logger.bind(key=key, ttl=ttl).debug("Cache SET after client recreation")
                    return True
                except Exception as re:
                    logger.error(f"Redis set retry failed: {re}")
            else:
                logger.error(f"Redis set failed: {e}")
        return False

    async def delete(self, key: str) -> bool:
        """Remove explicit key from cache."""
        if not self.enabled or not self.client:
            return False
        try:
            await self.client.delete(key)
            logger.bind(key=key).debug("Cache INVALIDATED")
            return True
        except Exception as e:
            if "Event loop is closed" in str(e):
                self._recreate_client()
                try:
                    await self.client.delete(key)
                    logger.bind(key=key).debug("Cache INVALIDATED after client recreation")
                    return True
                except Exception as re:
                    logger.error(f"Redis delete retry failed: {re}")
            else:
                logger.error(f"Redis delete failed: {e}")
        return False

    async def invalidate_pattern(self, pattern: str) -> bool:
        """Invalidate all keys matching pattern (e.g. 'company:*')."""
        if not self.enabled or not self.client:
            return False
        try:
            keys = await self.client.keys(pattern)
            if keys:
                await self.client.delete(*keys)
                logger.bind(pattern=pattern, count=len(keys)).debug("Cache pattern INVALIDATED")
            return True
        except Exception as e:
            if "Event loop is closed" in str(e):
                self._recreate_client()
                try:
                    keys = await self.client.keys(pattern)
                    if keys:
                        await self.client.delete(*keys)
                        logger.bind(pattern=pattern, count=len(keys)).debug("Cache pattern INVALIDATED after client recreation")
                    return True
                except Exception as re:
                    logger.error(f"Redis invalidate_pattern retry failed: {re}")
            else:
                logger.error(f"Redis invalidate_pattern failed: {e}")
        return False

    def get_sync(self, key: str) -> Optional[Any]:
        """Synchronously fetch value from cache."""
        if not self.enabled or not self.sync_client:
            return None
        try:
            val = self.sync_client.get(key)
            if val is not None:
                return json.loads(val)
        except Exception as e:
            logger.error(f"Redis get_sync failed: {e}")
        return None

    def set_sync(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Synchronously store serialized value in cache with a TTL."""
        if not self.enabled or not self.sync_client:
            return False
        try:
            serialized = json.dumps(value, default=json_serial)
            self.sync_client.set(key, serialized, ex=ttl)
            return True
        except Exception as e:
            logger.error(f"Redis set_sync failed: {e}")
        return False

    @staticmethod
    def hash_key(text: str) -> str:
        """Compute standard MD5 hash for dynamic parameter values."""
        return hashlib.md5(text.encode("utf-8")).hexdigest()


# Global Singleton instance
cache = RedisCache()

