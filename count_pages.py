import sys, os, fitz
sys.stdout.reconfigure(encoding='utf-8')

big = []
small = 0

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
                    big.append((f, pages))
                else:
                    small += 1
            except:
                pass

print(f"PDFs with <= 10 pages: {small}")
print(f"PDFs with > 10 pages:  {len(big)}")
print()
if big:
    for name, pages in sorted(big, key=lambda x: -x[1]):
        print(f"  {pages:3d} pages | {name}")
