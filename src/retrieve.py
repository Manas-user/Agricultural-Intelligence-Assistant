# src/retrieve.py

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
import os

# Match this with the path used in ingest.py
BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_DIR = os.path.join(BASE_PATH, "chromadb_index")

embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
db = Chroma(persist_directory=DB_DIR, embedding_function=embedding_model)
retriever = db.as_retriever(search_kwargs={"k": 5})

