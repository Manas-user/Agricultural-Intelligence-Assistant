import sys
sys.stdout.reconfigure(encoding='utf-8')
import fitz  # PyMuPDF - more reliable page counting

file_path = r"./data/krishi/जुन्या भात खाचरांची बांध दुरुस्ती.pdf"

# Get actual page count
doc = fitz.open(file_path)
total_pages = len(doc)
print(f"Actual pages in PDF: {total_pages}")
print("=" * 60)

for i, page in enumerate(doc):
    text = page.get_text().strip()
    print(f"Page {i}: {len(text)} chars | Has images: {len(page.get_images()) > 0}")
    if text:
        print(f"  Preview: {text[:150]}...")
    else:
        print(f"  (NO TEXT - likely scanned image)")
doc.close()

# Now check what PyPDF got
print("\n" + "=" * 60)
print("What PyPDFLoader extracted:")
from langchain_community.document_loaders import PyPDFLoader
loader = PyPDFLoader(file_path)
docs = loader.load()
print(f"Pages extracted by PyPDF: {len(docs)}")
total_text = sum(len(d.page_content.strip()) for d in docs)
print(f"Total text chars: {total_text}")

# Now check ChromaDB
import chromadb
client = chromadb.PersistentClient(path="./chroma_db")
col = client.get_or_create_collection("langchain")
results = col.get(include=["metadatas", "documents"])

chunks = [(m, d) for m, d in zip(results["metadatas"], results["documents"]) 
          if "बांध दुरुस्ती" in m.get("source", "")]

print(f"\nChunks in ChromaDB: {len(chunks)}")
total_chunk_chars = sum(len(d) for _, d in chunks)
print(f"Total chars in ChromaDB: {total_chunk_chars}")
