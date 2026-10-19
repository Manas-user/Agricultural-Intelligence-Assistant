from flask import Flask, request, jsonify
import logging
import os
from scraper_service import start_scheduler, run_scrapers_sync
from rag_engine import RAGPipeline
import threading
from langdetect import detect

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


def check_and_provoke_scrapers():
    data_dirs = ["./data/agriwelfare", "./data/krishi"]

    is_empty = True

    for d in data_dirs:
        if os.path.exists(d):
            for root, dirs, files in os.walk(d):
                if files:
                    is_empty = False
                    break

        if not is_empty:
            break

    if is_empty:
        logging.info(
            "Data folders are empty! Provoking scrapers immediately..."
        )
        run_scrapers_sync()
    else:
        logging.info(
            "Data folders have files. Proceeding without scraping."
        )


# ============================================================
# 1. CHECK DATA FOLDERS
# ============================================================

check_and_provoke_scrapers()


# ============================================================
# 2. INITIALIZE RAG PIPELINE
# ============================================================

# This will automatically check if ChromaDB exists
# and initialize the RAG system.

rag = RAGPipeline()


# ============================================================
# 3. QUERY ENDPOINT
# ============================================================

@app.route('/query', methods=['POST'])
def query_endpoint():

    data = request.get_json()

    if not data or 'query' not in data:
        return jsonify({
            "error": "Please provide a 'query' field in the JSON body."
        }), 400

    query_text = data['query'].strip()

    if not query_text:
        return jsonify({
            "error": "Query cannot be empty."
        }), 400

    logging.info(f"Received query: {query_text}")


    # --------------------------------------------------------
    # Get language selected from frontend
    # --------------------------------------------------------

    requested_language = data.get("language", "en-IN")

    language_map = {
        "en-IN": "English",
        "hi-IN": "Hindi",
        "mr-IN": "Marathi",

        # Also support simple language values
        "English": "English",
        "Hindi": "Hindi",
        "Marathi": "Marathi",

        "en": "English",
        "hi": "Hindi",
        "mr": "Marathi"
    }

    answer_language = language_map.get(
        requested_language,
        "English"
    )


    try:

        # ----------------------------------------------------
        # Detect the language of the user's query
        # ----------------------------------------------------

        try:
            detected_lang = detect(query_text)
        except Exception:
            detected_lang = "unknown"


        logging.info(
            f"Requested answer language: {answer_language}"
        )

        logging.info(
            f"Detected query language: {detected_lang}"
        )


        # ----------------------------------------------------
        # Send query to RAG engine
        # ----------------------------------------------------

        result = rag.query(
            query_text,
            answer_language=answer_language
        )


        # ----------------------------------------------------
        # Return response
        # ----------------------------------------------------

        return jsonify({
            "answer": result.get("answer"),
            "sources": result.get("sources", []),
            "detected_language": detected_lang,
            "answer_language": result.get(
                "answer_language",
                answer_language
            )
        }), 200


    except Exception as e:

        logging.error(
            f"Error processing query: {e}",
            exc_info=True
        )

        return jsonify({
            "error": "An internal error occurred while processing the query."
        }), 500


# ============================================================
# 4. MANUAL INGESTION ENDPOINT
# ============================================================

@app.route('/ingest', methods=['POST'])
def ingest_endpoint():
    """
    Endpoint to trigger document ingestion manually.
    Ingestion runs in a separate thread so that
    the API does not get blocked.
    """

    try:

        threading.Thread(
            target=rag.ingest_documents,
            daemon=True
        ).start()

        return jsonify({
            "status": "Ingestion started in the background."
        }), 202

    except Exception as e:

        logging.error(
            f"Error starting ingestion: {e}",
            exc_info=True
        )

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================
# 5. INITIALIZE APPLICATION
# ============================================================

def init_app():

    # Start APScheduler for web scrapers
    logging.info("Initializing system...")

    start_scheduler()


# ============================================================
# 6. RUN FLASK APPLICATION
# ============================================================

if __name__ == '__main__':

    # Initialize scheduler before starting Flask
    init_app()

    # debug=False is recommended when using APScheduler
    # because Flask's reloader can create duplicate jobs.

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False
    )