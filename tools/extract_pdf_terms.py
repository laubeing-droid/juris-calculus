#!/usr/bin/env python3
"""Extract ALL terms from PDFs and merge for saturation testing"""
import pdfplumber, json, re, os
from pathlib import Path

# Set US_PDF_PATH env var to your PDF directory before running
BASE = os.environ.get("US_PDF_PATH", ".")
PDFS = [
    ("WA_Glossary", Path(BASE) / "Glossary of Legal Terms.pdf"),
    ("DOJ_Glossary", Path(BASE) / "U.S. Attorneys _ Legal Terms Glossary _ United States Department of Justice.pdf"),
]

all_terms = set()

for name, path in PDFS:
    print(f"\n=== {name} ({os.path.getsize(path):,} bytes) ===")
    with pdfplumber.open(path) as pdf:
        full_text = ""
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                full_text += t + "\n"
    
    # Extract term-definition pairs
    # Pattern: term on its own line, followed by definition
    lines = full_text.split('\n')
    terms_found = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        # Skip empty, header lines, URLs
        if not line or len(line) < 2 or line.startswith('http') or line.startswith('202'):
            continue
        # Skip definition-only lines (longer than 80 chars, starts lowercase)
        if len(line) > 80 or (line[0].islower() and len(line.split()) > 3):
            continue
        # Term candidates: short, title-case or ALL CAPS
        words = line.split()
        if 1 <= len(words) <= 8 and len(line) <= 80:
            # All-caps headers (letter groups like "A", "B")
            if len(words) == 1 and len(line) <= 2 and line.isalpha():
                continue
            # Clean up
            term = re.sub(r'[\(\[].*$', '', line).strip()
            term = term.rstrip('.,;:')
            if len(term) >= 2:
                terms_found.append(term)
    
    # Deduplicate within this PDF
    unique = list(dict.fromkeys(terms_found))
    print(f"  Raw lines: {len(lines)}")
    print(f"  Candidate terms: {len(unique)}")
    
    # Sample
    print(f"  Sample terms: {unique[:15]}")
    all_terms.update(unique)

print(f"\n=== TOTAL unique terms across all PDFs: {len(all_terms)} ===")

# Filter: remove common false positives
false_positives = {'the', 'of', 'and', 'in', 'to', 'a', 'for', 'is', 'by', 'on', 
                   'or', 'at', 'be', 'as', 'an', 'it', 'no', 'so', 'if', 'we',
                   'page', 'search', 'print', 'about', 'find', 'help', 'home',
                   'definitions', 'definition', 'glossary', 'terms', 'legal',
                   'www', 'com', 'org', 'gov', 'html', 'pdf', 'back', 'top',
                   'more', 'all', 'not', 'this', 'that', 'with', 'from',
                   'contact', 'email', 'phone', 'address', 'office',
                   'content', 'menu', 'main', 'footer', 'header', 'link',
                   'also', 'new', 'may', 'can', 'has', 'been', 'one', 'two',
                   'some', 'other', 'each', 'such', 'any', 'will', 'shall',
                   '2026', 'U.S', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
                   'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W',
                   'X', 'Y', 'Z'}

filtered = sorted(t for t in all_terms if t.lower() not in false_positives and len(t) >= 3)
print(f"Filtered terms: {len(filtered)}")

# Save
output = Path(__file__).resolve().parents[1] / "configs" / "en_US" / "all_glossary_terms.json"
with open(output, "w", encoding="utf-8") as f:
    json.dump(filtered, f, ensure_ascii=False, indent=2)

print(f"Saved: {output} ({len(filtered)} terms)")
