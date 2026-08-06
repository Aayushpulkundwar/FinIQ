import asyncio
import os
from loguru import logger
from app.core.config import settings
from app.services.response_generation import ResponseGenerationService

async def test_generation(label: str, query: str):
    logger.info(f"\n=== TESTING: {label} ===")
    logger.info(f"OPENROUTER_API_KEY: '{settings.OPENROUTER_API_KEY[:10]}...'")
    logger.info(f"OLLAMA_GENERATION_ENABLED: {settings.OLLAMA_GENERATION_ENABLED}")
    logger.info(f"OLLAMA_MODEL: {settings.OLLAMA_MODEL}")

    service = ResponseGenerationService()
    
    mock_company = {
        "company_name": "Arvind Limited",
        "ticker_symbol": "ARVIND",
        "sector": "Textiles",
        "industry": "Apparel"
    }
    
    mock_chunks = [
        {
            "document_title": "Arvind Annual Report 2024",
            "page_number": 12,
            "chunk_text": "Arvind Limited reported revenue growth of 12% in FY24 driven by strong demand in denim and woven fabrics. Operating margins expanded by 150 bps."
        },
        {
            "document_title": "Arvind Annual Report 2024",
            "page_number": 15,
            "chunk_text": "Net profit for Arvind Limited reached 350 Crores in FY24, supported by cost optimization and higher export volumes."
        }
    ]

    response = await service.generate_response(
        user_query=query,
        company_details=mock_company,
        document_metadata=[{"title": "Arvind Annual Report 2024"}],
        retrieved_chunks=mock_chunks,
    )

    logger.info(f"RESPONSE PROVIDER: {response.provider}")
    logger.info(f"RESPONSE GENERATION MODE: {response.generation_mode}")
    logger.info(f"RESPONSE IS DEGRADED: {response.is_degraded}")
    logger.info(f"EXECUTIVE SUMMARY: {response.executive_summary[:200]}")
    logger.info(f"KEY INSIGHTS: {response.key_insights}")
    return response

async def main():
    # 1. Primary path with valid OpenRouter key
    res_primary = await test_generation("1. PRIMARY PATH (Valid OpenRouter Key)", "What was Arvind Limited's revenue growth in FY24?")

    # 2. Deliberately break OpenRouter key
    original_key = settings.OPENROUTER_API_KEY
    settings.OPENROUTER_API_KEY = "sk-or-v1-invalid-broken-key-for-fallback-testing"
    
    res_fallback = await test_generation("2. FALLBACK PATH (Broken OpenRouter Key)", "What was Arvind Limited's net profit in FY24?")

    # 3. Restore valid OpenRouter key
    settings.OPENROUTER_API_KEY = original_key
    res_restored = await test_generation("3. RESTORED PRIMARY PATH (Valid OpenRouter Key)", "What was Arvind Limited's operating margin expansion in FY24?")

    print("\n================ VERIFICATION SUMMARY ================")
    print(f"1. Primary Path Provider:  {res_primary.provider}")
    print(f"2. Fallback Path Provider: {res_fallback.provider}")
    print(f"3. Restored Path Provider: {res_restored.provider}")
    print("=======================================================")

if __name__ == "__main__":
    asyncio.run(main())
