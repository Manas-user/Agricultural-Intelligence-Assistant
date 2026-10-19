import sys
sys.stdout.reconfigure(encoding='utf-8')
import chromadb
import os

client = chromadb.PersistentClient(path="./chroma_db")
col = client.get_or_create_collection("langchain")
results = col.get(include=["metadatas"])

sources = set()
for m in results["metadatas"]:
    sources.add(m.get("source", "unknown"))

total_chunks = len(results["ids"])
print(f"Total chunks in ChromaDB: {total_chunks}")
print(f"Unique documents ingested: {len(sources)}")
print("=" * 60)

# Also list all files in data folders
data_files = set()
for data_dir in ["./data/agriwelfare", "./data/krishi"]:
    if os.path.exists(data_dir):
        for root, _, files in os.walk(data_dir):
            for f in files:
                data_files.add(os.path.join(root, f))

print(f"\nTotal files in data folders: {len(data_files)}")
print("=" * 60)

# Show ingested documents
print("\n[OK] INGESTED documents:")
for s in sorted(sources):
    print(f"  {s}")

# Find missing files
missing = data_files - sources
if missing:
    print(f"\n[MISSING] NOT INGESTED ({len(missing)} files):")
    for m in sorted(missing):
        print(f"  {m}")
else:
    print("\n[OK] All files were ingested!")
