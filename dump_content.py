import sys
sys.stdout.reconfigure(encoding='utf-8')
import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
col = client.get_or_create_collection("langchain")
results = col.get(include=["metadatas", "documents"])

# Group chunks by source file
from collections import defaultdict
file_chunks = defaultdict(list)

for m, d in zip(results["metadatas"], results["documents"]):
    src = m.get("source", "unknown")
    page = m.get("page", "?")
    ocr = m.get("ocr", False)
    file_chunks[src].append({"page": page, "ocr": ocr, "content": d})

# Write to a readable file
with open("ingested_content.txt", "w", encoding="utf-8") as f:
    f.write(f"CHROMADB FULL CONTENT DUMP\n")
    f.write(f"Total chunks: {len(results['ids'])}\n")
    f.write(f"Total files: {len(file_chunks)}\n")
    f.write("=" * 80 + "\n\n")
    
    for src in sorted(file_chunks.keys()):
        chunks = file_chunks[src]
        f.write(f"\n{'#' * 80}\n")
        f.write(f"FILE: {src}\n")
        f.write(f"CHUNKS: {len(chunks)}\n")
        f.write(f"{'#' * 80}\n\n")
        
        for i, chunk in enumerate(chunks):
            f.write(f"--- Chunk {i+1} | Page: {chunk['page']} | OCR: {chunk['ocr']} ---\n")
            f.write(chunk["content"] if chunk["content"] else "(empty)")
            f.write("\n\n")

print(f"Done! Written to ingested_content.txt")
print(f"Total chunks: {len(results['ids'])}")
print(f"Total files: {len(file_chunks)}")
