import sys, os, fitz
sys.stdout.reconfigure(encoding='utf-8')

deleted = 0
for d in ['./data/agriwelfare', './data/krishi']:
    if not os.path.exists(d):
        continue
    for root, _, files in os.walk(d):
        for f in files:
            if not f.lower().endswith('.pdf'):
                continue
            path = os.path.join(root, f)
            try:
                doc = fitz.open(path)
                pages = len(doc)
                doc.close()
                if pages > 10:
                    os.remove(path)
                    deleted += 1
                    print(f"Deleted ({pages:4d} pages): {f}")
            except Exception as e:
                print(f"Error with {f}: {e}")

print(f"\nTotal deleted: {deleted}")
