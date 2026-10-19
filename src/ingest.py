# RAG System for Financial Reports using Gemini API (VS Code Version)

# ========== Step 1: Data Ingestion ========== #

# File: src/ingest.py (using FAISS instead of Chroma)

import os
import zipfile
import tempfile
from langchain_community.document_loaders import PyMuPDFLoader, UnstructuredXMLLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import pickle

# ========== Set project base path ==========
BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASE_DIRS = [
    os.path.join(BASE_PATH, "Annual_Reports"),
    os.path.join(BASE_PATH, "Quarterly_Reports"),
    os.path.join(BASE_PATH, "Announcements")
]

print("📂 Looking for report folders:")
for d in BASE_DIRS:
    print("   ➤", d)

# ========== Initialize embedding model and text splitter ==========
EMBEDDING_MODEL = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
TEXT_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)

all_docs = []

# ========== Loop through all base folders ==========
for base_dir in BASE_DIRS:
    if not os.path.isdir(base_dir):
        print(f"❌ Skipping missing directory: {base_dir}")
        continue

    print(f"\n📁 Scanning directory: {base_dir}")
    for company in os.listdir(base_dir):
        company_dir = os.path.join(base_dir, company)
        if not os.path.isdir(company_dir):
            print(f"⚠️ Not a directory: {company_dir}")
            continue

        print(f"🏢 Company: {company}")
        print(f"📄 Files in {company_dir}: {os.listdir(company_dir)}")

        for file in os.listdir(company_dir):
            file_path = os.path.join(company_dir, file)
            extension = file.lower().split(".")[-1]

            print(f"🔍 Processing file: {file_path} (ext: {extension})")

            # ========== PDF Files ==========
            if extension == "pdf":
                try:
                    loader = PyMuPDFLoader(file_path)
                    pages = loader.load()
                    print(f"✅ Loaded {len(pages)} page(s) from PDF")
                except Exception as e:
                    print(f"❌ Error loading PDF {file_path}: {e}")
                    continue

            # ========== XML Files ==========
            elif extension == "xml":
                try:
                    loader = UnstructuredXMLLoader(file_path)
                    pages = loader.load()
                    print(f"✅ Loaded {len(pages)} page(s) from XML")
                except Exception as e:
                    print(f"❌ Error loading XML {file_path}: {e}")
                    continue

            # ========== ZIP Files ==========
            elif extension == "zip":
                pages = []
                try:
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        with tempfile.TemporaryDirectory() as temp_dir:
                            zip_ref.extractall(temp_dir)
                            extracted_files = os.listdir(temp_dir)
                            print(f"📦 Extracted ZIP contains: {extracted_files}")
                            for extracted_file in extracted_files:
                                extracted_path = os.path.join(temp_dir, extracted_file)
                                ext = extracted_file.lower().split(".")[-1]
                                try:
                                    if ext == "pdf":
                                        loader = PyMuPDFLoader(extracted_path)
                                    elif ext == "xml":
                                        loader = UnstructuredXMLLoader(extracted_path)
                                    else:
                                        print(f"⚠️ Skipping unsupported file in ZIP: {extracted_file}")
                                        continue
                                    file_pages = loader.load()
                                    print(f"✅ Loaded {len(file_pages)} page(s) from {extracted_file}")
                                    for doc in file_pages:
                                        doc.metadata.update({
                                            "company": company,
                                            "type": os.path.basename(base_dir),
                                            "source": extracted_file
                                        })
                                    pages.extend(file_pages)
                                except Exception as inner_e:
                                    print(f"❌ Error loading file from ZIP: {extracted_file} - {inner_e}")
                                    continue
                except Exception as zip_e:
                    print(f"❌ Error reading ZIP {file_path}: {zip_e}")
                    continue

            else:
                print(f"⚠️ Unsupported format: {file_path}")
                continue

            # ========== Add metadata and accumulate ==========
            for doc in pages:
                doc.metadata.update({
                    "company": company,
                    "type": os.path.basename(base_dir),
                    "source": file
                })
            all_docs.extend(pages)
            print(f"📚 Total documents collected so far: {len(all_docs)}")

# ========== Split and Save ==========
chunks = TEXT_SPLITTER.split_documents(all_docs)
print(f"\n📊 Total chunks created: {len(chunks)}")

if chunks:
    DB_DIR = os.path.join(BASE_PATH, "chromadb_index")  # ✅ New directory for Chroma
    db = Chroma.from_documents(documents=chunks, embedding=EMBEDDING_MODEL, persist_directory=DB_DIR)
    db.persist()  # ✅ Save to disk
    print("✅ Ingestion complete. ChromaDB index saved at 'chromadb_index'")
else:
    print("⚠️ No documents were chunked. Please check your source files.")
