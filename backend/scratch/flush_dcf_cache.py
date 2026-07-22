import sys
import os
sys.path.append(os.getcwd())

import asyncio
from app.core.cache import cache

async def run():
    print("Flushing DCF inputs cache...")
    res = await cache.invalidate_pattern("dcf_inputs:*")
    print(f"Invalidated pattern result: {res}")

if __name__ == "__main__":
    asyncio.run(run())
