import os
import re
import hashlib
import pickle
from typing import List, Dict, Optional
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.docx import partition_docx
from unstructured.partition.text import partition_text
from unstructured.partition.md import partition_md
from unstructured.partition.html import partition_html
from unstructured.chunking.title import chunk_by_title

CACHE_DIR = os.getenv("PARSE_CACHE_DIR", "/tmp/documind_parse_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

MAX_HI_RES_BYTES = 15 * 1024 * 1024  # 15MB

PERIOD_PATTERNS = [
    (r'\bQ([1-4])\s*(?:FY|CY)?\s*(20\d{2})\b',
     lambda m: f"Q{m.group(1)}-{m.group(2)}"),
    (r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
     r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
     r'\s*(20\d{2})\b',
     lambda m: f"{m.group(1)[:3].upper()}-{m.group(2)}"),
    (r'\bFY\s*(20\d{2})\b',
     lambda m: f"FY-{m.group(1)}"),
    (r'\b(First|Second|Third|Fourth)\s+Quarter\s+(20\d{2})\b',
     lambda m: f"Q{['First','Second','Third','Fourth'].index(m.group(1))+1}-{m.group(2)}"),
]


class SmartPDFParser:
    def __init__(self, use_semantic_chunking: bool = True):
        self.use_semantic_chunking = use_semantic_chunking

        if use_semantic_chunking:
            try:
                from chonkie import SemanticChunker
                print("⏳ Loading semantic chunker...")
                self.semantic_chunker = SemanticChunker(
                    embedding_model="minishlab/potion-base-8M",
                    chunk_size=512,
                    similarity_threshold=0.5
                )
                print("✅ Semantic chunker ready")
            except Exception as e:
                print(f"⚠️  Semantic chunker failed to load ({e}) — using title chunking only")
                self.semantic_chunker = None
                self.use_semantic_chunking = False
        else:
            self.semantic_chunker = None

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _file_hash(self, file_path: str) -> str:
        """SHA-256 of first 64KB + file size — fast, content-based cache key."""
        h = hashlib.sha256()
        h.update(str(os.path.getsize(file_path)).encode())
        with open(file_path, "rb") as f:
            h.update(f.read(65536))
        return h.hexdigest()[:16]

    def _choose_strategy(self, file_path: str) -> str:
        """Use hi_res for files under 15MB, fall back to auto for large files."""
        if os.path.getsize(file_path) < MAX_HI_RES_BYTES:
            return "hi_res"
        print(f"   ⚠️ File > 15MB — using 'auto' strategy (tables may be imprecise)")
        return "auto"

    def _extract_period(self, section_header: str) -> Optional[str]:
        """Normalize period tokens from section headers."""
        for pattern, formatter in PERIOD_PATTERNS:
            m = re.search(pattern, section_header, re.IGNORECASE)
            if m:
                return formatter(m)
        return None

    def _build_element_sections(self, elements: list) -> Dict[int, str]:
        """
        Build parallel dict mapping element object id → section name.
        Uses id() for reliable object identity matching with orig_elements.
        """
        element_sections: Dict[int, str] = {}
        current_section = "General"
        for el in elements:
            if el.category == "Title":
                current_section = str(el).strip()
            element_sections[id(el)] = current_section
        return element_sections

    def _recover_section(self, chunk, elements: list,
                        element_sections: Dict[int, str]) -> str:
        """Recover section for a chunked element via orig_elements."""
        orig = getattr(chunk.metadata, "orig_elements", None)
        if orig:
            return element_sections.get(id(orig[0]), "General")
        return "General"

    def _recover_page_range(self, chunk) -> tuple:
        """Return (start_page, end_page) from orig_elements."""
        orig = getattr(chunk.metadata, "orig_elements", None)
        if orig:
            pages = [
                getattr(e.metadata, "page_number", None)
                for e in orig
                if getattr(e.metadata, "page_number", None)
            ]
            if pages:
                return min(pages), max(pages)
        fallback = getattr(chunk.metadata, "page_number", None) or 1
        return fallback, fallback

    # ── Main parse method ─────────────────────────────────────────────────────

    def parse_with_metadata(self, file_path: str) -> List[Dict]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at: {file_path}")

        # Issue 4 — cache check
        cache_key = self._file_hash(file_path)
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}_s{int(self.use_semantic_chunking)}.pkl")
        if os.path.exists(cache_path):
            print(f"   ⚡ Parse cache hit for {os.path.basename(file_path)}")
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass  # Corrupt cache — re-parse

        ext = os.path.splitext(file_path)[1].lower()
        elements = []

        try:
            print(f"📄 Parsing {os.path.basename(file_path)} with Unstructured...")

            # Issue 2 — explicit strategy with size guard
            if ext == ".pdf":
                strategy = self._choose_strategy(file_path)
                elements = partition_pdf(
                    filename=file_path,
                    strategy=strategy,
                    infer_table_structure=True,
                    extract_images_in_pdf=False,
                    include_page_breaks=True
                )
            elif ext == ".docx":
                elements = partition_docx(filename=file_path)
            elif ext == ".txt":
                elements = partition_text(filename=file_path)
            elif ext == ".md":
                elements = partition_md(filename=file_path)
            elif ext in (".html", ".htm"):
                elements = partition_html(filename=file_path)
            else:
                return []

            # Issue 1 — parallel dict for section tracking
            element_sections = self._build_element_sections(elements)

            # Issue 7 — lower combine threshold
            chunked_elements = chunk_by_title(
                elements,
                max_characters=2000,
                new_after_n_chars=1800,
                combine_text_under_n_chars=200,
                multipage_sections=True
            )

            base_chunks = []
            for i, element in enumerate(chunked_elements):
                # Issue 1 — recover section via orig_elements + parallel dict
                section = self._recover_section(element, elements, element_sections)

                # Issue 5 — page range
                start_page, end_page = self._recover_page_range(element)
                page_range = (f"{start_page}-{end_page}"
                              if start_page != end_page else str(start_page))

                # Issue 6 — period normalization
                period = self._extract_period(section)

                chunk = {
                    "text": str(element),
                    "metadata": {
                        "source": os.path.basename(file_path),
                        "page": start_page,
                        "page_end": end_page,
                        "page_range": page_range,
                        "chunk_id": i,
                        "type": element.category,
                        "section": section,
                        "period": period,
                    }
                }

                # Issue 3 — table typed chunks with HTML
                if element.category == "Table":
                    html_repr = getattr(element.metadata, "text_as_html", None)
                    if html_repr:
                        chunk["metadata"]["table_html"] = html_repr
                    chunk["metadata"]["is_authoritative"] = True

                base_chunks.append(chunk)

            # Patch B — semantic chunking, tables pass through untouched
            if self.use_semantic_chunking and self.semantic_chunker:
                final_chunks = []
                for i, chunk in enumerate(base_chunks):
                    # Type gate — never split tables
                    if chunk["metadata"]["type"] == "Table":
                        final_chunks.append(chunk)
                        continue

                    text = chunk["text"]
                    if len(text) > 600:
                        try:
                            sub_chunks = self.semantic_chunker.chunk(text)
                            for j, sc in enumerate(sub_chunks):
                                refined = dict(chunk)
                                refined["text"] = sc.text
                                refined["metadata"] = dict(chunk["metadata"])
                                refined["metadata"]["chunk_id"] = f"{i}_{j}"
                                final_chunks.append(refined)
                        except Exception as e:
                            print(f"   ⚠️ Semantic chunk failed for chunk {i}: {e}")
                            final_chunks.append(chunk)
                    else:
                        final_chunks.append(chunk)

                pre = len(base_chunks)
                post = len(final_chunks)
                if post != pre:
                    print(f"   🧠 Semantic chunking: {pre} → {post} chunks")
            else:
                final_chunks = base_chunks

            print(f"   - Parsed {len(final_chunks)} chunks (Smart Layout)")

            # Issue 4 — save to cache
            try:
                with open(cache_path, "wb") as f:
                    pickle.dump(final_chunks, f)
                print(f"   💾 Parse cached for future re-ingestion")
            except Exception as e:
                print(f"   ⚠️ Cache write failed: {e}")

            return final_chunks

        except Exception as e:
            print(f"❌ Error parsing {file_path}: {e}")
            return []
