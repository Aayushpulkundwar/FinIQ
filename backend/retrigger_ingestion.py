import argparse
from app.services.tasks import process_document_task

def run():
    parser = argparse.ArgumentParser(description="Trigger Celery process_document task.")
    parser.add_argument("--document-id", required=True, help="UUID of the document to ingest.")
    args = parser.parse_args()

    print(f"Sending celery task for document_id: {args.document_id}...")
    res = process_document_task.delay(args.document_id)
    print(f"Task sent successfully! Task ID: {res.id}")

if __name__ == "__main__":
    run()
