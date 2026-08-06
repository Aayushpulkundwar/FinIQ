import asyncio
from app.core.cache import cache

async def main():
    print("Flushing Redis cache keys matching 'ai_response:*' and 'news:*'...")
    await cache.invalidate_pattern("ai_response:*")
    await cache.invalidate_pattern("news:*")
    print("Redis cache flush completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
