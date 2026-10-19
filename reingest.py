"""Re-ingest all documents with improved OCR for garbled Marathi PDFs."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
import shutil
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Step 1: Delete existing ChromaDB
CHROMA_DB_DIR = "./chroma_db"
if os.path.exists(CHROMA_DB_DIR):
    logging.info("Deleting existing ChromaDB...")
    shutil.rmtree(CHROMA_DB_DIR)
    logging.info("ChromaDB deleted.")

# Step 2: Re-ingest
logging.info("Starting fresh ingestion with OCR support...")
from rag_engine import RAGPipeline
pipeline = RAGPipeline()

logging.info("=" * 60)
logging.info("INGESTION COMPLETE!")
logging.info(f"You can now restart app.py")
