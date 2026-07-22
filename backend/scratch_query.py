import asyncio
import json
import sys
from app.services.response_generation import ResponseGenerationService

async def run():
    service = ResponseGenerationService()
    company = {"company_name": "Arvind Limited", "ticker_symbol": "ARVIND"}
    
    # Query 1
    chunks1 = [
        {
            "chunk_text": "Arvind Limited is a leading textile player and vertically integrated manufacturer of denim, wovens, and knits. It has evolved into a major apparel retail powerhouse licensing top international brands.",
            "document_title": "Arvind Limited Annual Report FY25",
            "page_number": 12
        }
    ]
    res1 = await service.generate_response(
        user_query="What does Arvind Limited do?",
        company_details=company,
        document_metadata=[],
        retrieved_chunks=chunks1
    )
    
    # Query 2
    chunks2 = [
        {
            "chunk_text": "Arvind Limited operates primarily in the textile, apparel, and retail industries. The textile segment includes fabric manufacturing (denim, wovens, shirting) while the brand retail segment controls major licensed apparel portfolios.",
            "document_title": "Arvind Limited Annual Report FY25",
            "page_number": 15
        }
    ]
    res2 = await service.generate_response(
        user_query="Which industry does Arvind Limited operate in?",
        company_details=company,
        document_metadata=[],
        retrieved_chunks=chunks2
    )

    # Query 3
    chunks3 = [
        {
            "chunk_text": "Chairman's Message: We delivered record revenue and solid margin expansion despite global headwinds. We are scaling our garments capacity and investing in advanced materials solutions for high growth.",
            "document_title": "Arvind Limited Annual Report FY25",
            "page_number": 3
        }
    ]
    res3 = await service.generate_response(
        user_query="Summarize the Chairman's message.",
        company_details=company,
        document_metadata=[],
        retrieved_chunks=chunks3
    )

    # Write outputs to file
    with open("query_output.txt", "w") as f:
        f.write("=== What does Arvind Limited do? ===\n")
        f.write(json.dumps(res1.model_dump(), indent=2) + "\n\n")
        f.write("=== Which industry does Arvind Limited operate in? ===\n")
        f.write(json.dumps(res2.model_dump(), indent=2) + "\n\n")
        f.write("=== Summarize the Chairman's message. ===\n")
        f.write(json.dumps(res3.model_dump(), indent=2) + "\n\n")

if __name__ == "__main__":
    import traceback
    try:
        asyncio.run(run())
    except Exception as e:
        with open("query_output.txt", "w") as f:
            f.write("ERROR OCCURRED:\n")
            f.write(str(e) + "\n")
            f.write(traceback.format_exc() + "\n")
