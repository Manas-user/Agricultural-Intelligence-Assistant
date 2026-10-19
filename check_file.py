import sys
sys.stdout.reconfigure(encoding='utf-8')
import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
col = client.get_or_create_collection("langchain")
results = col.get(include=["metadatas", "documents"])

chunks = []
for m, d in zip(results["metadatas"], results["documents"]):
    src = m.get("source", "")
    if "\u092e\u091c\u0917\u0940" in src:  # मजगी
        chunks.append((m, d))

print(f"File: मजगी.pdf")
print(f"Total chunks: {len(chunks)}")
print("=" * 60)

for i, (meta, doc) in enumerate(chunks):
    page = meta.get("page", "?")
    ocr = meta.get("ocr", False)
    print(f"\n--- Chunk {i+1} | Page: {page} | OCR: {ocr} ---")
    print(doc if doc else "(empty)")
    print()
