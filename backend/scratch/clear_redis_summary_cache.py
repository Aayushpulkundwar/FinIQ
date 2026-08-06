import asyncio
from app.core.cache import cache

async def clear_cache():
    await cache.invalidate_pattern("financial_summary:*")
    await cache.invalidate_pattern("detailed_financials:*")
    print("Flushed financial summary and detailed financials cache keys in Redis.")

if __name__ == "__main__":
    asyncio.run(clear_cache())
