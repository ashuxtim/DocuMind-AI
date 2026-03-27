import os
import re
import hashlib
import pickle
from typing import List, Dict, Optional

from chonkie import SemanticChunker

from unstructured.partition.docx import partition_docx
from unstructured.partition.text import partition_text
from unstructured.partition.md import partition_md
from unstructured.partition.html import partition_html
from unstructured.chunking.title import chunk_by_title

# NOTE: partition_pdf is intentionally not imported here.
# LlamaParse handles all PDFs. unstructured_inference + torch still load at
# startup because unstructured's non-PDF partitioners pull them in transitively.
# Removing that weight requires migrating docx/txt/md/html to lighter libs —
# tracked as follow-up technical debt.

CACHE_DIR = os.getenv("PARSE_CACHE_DIR", "/tmp/documind_parse_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

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


# ── LlamaParse PDF utilities ───────────────────────────────────────────────────

def _extract_section_from_markdown(text: str) -> str:
    """
    Extract the deepest section header from a markdown page/chunk.
    Most specific header wins: h2 overrides h1, h3 inherits h2/h1 context.
    Falls back to "General" if no headers found.

    Stack approach: h1 sets context, h2 refines it, h3 inherits h2 (not
    promoted to section name itself). This keeps section stable for the
    audit pipeline — h3 granularity would fragment it too much.
    """
    h1 = h2 = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("### "):
            # h3 inherits current h2 or h1 — does not replace them
            continue
        elif line.startswith("## "):
            h2 = line.lstrip("# ").strip()
        elif line.startswith("# "):
            h1 = line.lstrip("# ").strip()
            h2 = None  # reset h2 on new h1
    return h2 or h1 or "General"


def _is_markdown_table(text: str) -> bool:
    """
    Detect a genuine markdown table — requires:
    - At least 2 lines matching |...|
    - At least one separator row (|---|)
    Guards against single pipe chars in prose triggering false positives.
    """
    pipe_lines = [l for l in text.splitlines() if re.match(r'^\|.+\|', l.strip())]
    has_separator = any(re.match(r'^\|[\s\-|:]+\|', l.strip()) for l in pipe_lines)
    return len(pipe_lines) >= 2 and has_separator


def _parse_pdf_with_llamaparse(file_path: str) -> List[Dict]:
    """
    Parse a PDF with LlamaParse. Returns one raw chunk per page with text
    and page metadata. Semantic chunking pass runs after this in the main flow.

    Uses llama_parse (pip: llama-parse>=0.5.0) — stable, not yet migrated to
    llama-cloud>=1.0. Migration tracked as follow-up before May 2026 deprecation.

    load_data() is synchronous — correct inside asyncio.to_thread() in ingest.py.
    page_label is a string in LlamaParse metadata — cast to int explicitly.
    """
    from llama_parse import LlamaParse

    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    if not api_key:
        raise RuntimeError(
            "LLAMA_CLOUD_API_KEY is required for PDF parsing. "
            "Set it in backend/.env and run: make secrets"
        )

    parser = LlamaParse(
        api_key=api_key,
        result_type="markdown",   # Returns one Document per page
        verbose=False,
        language="en",
    )

    print(f"   ☁️  LlamaParse: uploading {os.path.basename(file_path)}...")
    documents = parser.load_data(file_path)
    print(f"   ☁️  LlamaParse: received {len(documents)} page(s)")

    page_chunks = []
    for doc in documents:
        # page_label is a string in LlamaParse metadata e.g. '1', '2'
        raw_page = doc.metadata.get("page_label", "1")
        try:
            page_num = int(raw_page)
        except (ValueError, TypeError):
            page_num = 1

        text = doc.text.strip()
        if not text:
            continue

        section = _extract_section_from_markdown(text)
        is_table = _is_markdown_table(text)

        chunk: Dict = {
            "text": text,
            "metadata": {
                "source": os.path.basename(file_path),
                "page": page_num,
                "page_end": page_num,
                "page_range": str(page_num),
                "chunk_id": page_num - 1,
                "type": "Table" if is_table else "NarrativeText",
                "section": section,
                "period": None,   # filled below
            }
        }

        chunk["metadata"]["period"] = _extract_period_from_text(section)

        if is_table:
            # No HTML repr from LlamaParse — markdown is the authoritative form
            chunk["metadata"]["is_authoritative"] = True
            chunk["metadata"]["table_markdown"] = text

        page_chunks.append(chunk)

    return page_chunks


def _extract_period_from_text(text: str) -> Optional[str]:
    """Shared period extractor — same patterns as _extract_period but takes raw text."""
    for pattern, formatter in PERIOD_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return formatter(m)
    return None


class SmartPDFParser:
    def __init__(self, use_semantic_chunking: bool = True):
        self.use_semantic_chunking = use_semantic_chunking

        if use_semantic_chunking:
            try:
                print("⏳ Loading semantic chunker (bge-small, local)...")
                # Chonkie + bge-small: local, zero network calls during ingest.
                # NVIDIA API handles retrieval embeddings and reranking — that's
                # where quality matters. Chunking only needs sentence boundary
                # detection, bge-small (33M params, ~200MB RAM) is sufficient.
                # Model is cached on model-cache PVC — no re-download on restart.
                self.semantic_chunker = SemanticChunker(
                    embedding_model="BAAI/bge-small-en-v1.5",
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

    # ── Utilities (non-PDF path) ──────────────────────────────────────────────

    def _file_hash(self, file_path: str) -> str:
        """SHA-256 of first 64KB + file size — fast, content-based cache key."""
        h = hashlib.sha256()
        h.update(str(os.path.getsize(file_path)).encode())
        with open(file_path, "rb") as f:
            h.update(f.read(65536))
        return h.hexdigest()[:16]

    def _extract_period(self, section_header: str) -> Optional[str]:
        """Normalize period tokens from section headers."""
        return _extract_period_from_text(section_header)

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

    # ── Semantic chunking pass (shared by all formats) ────────────────────────

    def _apply_semantic_chunking(self, base_chunks: List[Dict]) -> List[Dict]:
        """
        Semantic chunking pass — tables always pass through untouched.
        chunk() returns Chonkie chunk objects — access text via sc.text.
        """
        if not (self.use_semantic_chunking and self.semantic_chunker):
            return base_chunks

        final_chunks = []
        for i, chunk in enumerate(base_chunks):
            if chunk["metadata"]["type"] == "Table":
                final_chunks.append(chunk)
                continue

            text = chunk["text"]
            if len(text) > 600:
                try:
                    sub_chunks = self.semantic_chunker.chunk(text)
                    if len(sub_chunks) > 1:
                        for j, sc in enumerate(sub_chunks):
                            refined = dict(chunk)
                            refined["text"] = sc.text
                            refined["metadata"] = dict(chunk["metadata"])
                            refined["metadata"]["chunk_id"] = f"{i}_{j}"
                            final_chunks.append(refined)
                        continue
                except Exception as e:
                    print(f"   ⚠️ Semantic chunk failed for chunk {i}: {e}")
            final_chunks.append(chunk)

        pre = len(base_chunks)
        post = len(final_chunks)
        if post != pre:
            print(f"   🧠 Semantic chunking: {pre} → {post} chunks")

        return final_chunks

    # ── Alias window (Stage 0 for ingest.py alias pre-pass) ──────────────────

    def get_alias_window(self, file_path: str) -> str:
        """
        Returns the raw LlamaParse markdown for a PDF — the full text before
        semantic chunking — as a single string for alias registry extraction.

        Why this exists here:
          - parse_with_metadata() runs LlamaParse then caches the CHUNKED output.
          - ingest.py needs the PRE-CHUNK markdown to find alias definitions that
            straddle chunk boundaries (e.g. a parenthetical on the next line).
          - This method writes a separate _raw.pkl cache so LlamaParse is only
            ever called once per file regardless of call order.

        Non-PDF files (docx, txt, md, html) join chunk text as a fallback —
        alias patterns in those formats are typically within single elements.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            # Check raw cache first — avoids burning LlamaParse credits twice
            cache_key = self._file_hash(file_path)
            raw_cache_path = os.path.join(
                CACHE_DIR, f"{cache_key}_raw.pkl"
            )
            if os.path.exists(raw_cache_path):
                try:
                    with open(raw_cache_path, "rb") as f:
                        return pickle.load(f)
                except Exception:
                    pass  # Corrupt cache — re-fetch

            # Call LlamaParse for raw page markdown
            raw_pages = _parse_pdf_with_llamaparse(file_path)
            # Join all page texts preserving page boundaries for regex patterns
            raw_text = "\n\n---PAGE---\n\n".join(
                p["text"] for p in raw_pages if p.get("text")
            )

            # Cache both the joined string (alias window) AND the raw page
            # list (_pages.pkl) so parse_with_metadata() can reuse the pages
            # without calling LlamaParse again on the same file.
            try:
                with open(raw_cache_path, "wb") as f:
                    pickle.dump(raw_text, f)
                pages_cache_path = os.path.join(
                    CACHE_DIR, f"{cache_key}_pages.pkl"
                )
                with open(pages_cache_path, "wb") as f:
                    pickle.dump(raw_pages, f)
            except Exception as e:
                print(f"   ⚠️ Raw alias cache write failed: {e}")

            return raw_text

        else:
            # Non-PDF: join chunks from standard parsing as alias window.
            # Section headers are preserved in chunk text via unstructured Title elements.
            chunks = self.parse_with_metadata(file_path)
            return "\n\n".join(c["text"] for c in chunks if c.get("text"))

    # ── Main parse method ─────────────────────────────────────────────────────

    def parse_with_metadata(self, file_path: str) -> List[Dict]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at: {file_path}")

        # Cache check — skip re-parse + re-chunk for unchanged files.
        # Cache key includes semantic chunking flag so toggling it invalidates cache.
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

        try:
            if ext == ".pdf":
                # ── PDF: LlamaParse ───────────────────────────────────────────
                # Cloud parser — burns LLAMA_CLOUD_API_KEY credits on first ingest.
                # Parse cache above means each unique file only costs credits once.
                print(f"📄 Parsing {os.path.basename(file_path)} with LlamaParse...")
                # Reuse raw pages cached by get_alias_window() if Stage 0
                # already called LlamaParse — avoids double API credit burn.
                pages_cache_path = os.path.join(
                    CACHE_DIR, f"{self._file_hash(file_path)}_pages.pkl"
                )
                if os.path.exists(pages_cache_path):
                    try:
                        with open(pages_cache_path, "rb") as f:
                            base_chunks = pickle.load(f)
                        print(f"   ⚡ Reusing LlamaParse pages from Stage 0 cache")
                    except Exception:
                        base_chunks = _parse_pdf_with_llamaparse(file_path)
                else:
                    base_chunks = _parse_pdf_with_llamaparse(file_path)
                final_chunks = self._apply_semantic_chunking(base_chunks)

            else:
                # ── Non-PDF: unstructured (unchanged) ─────────────────────────
                # NOTE: unstructured_inference + torch still load at startup even
                # though partition_pdf is gone — they're imported transitively by
                # the non-PDF partitioners. Removing that weight requires migrating
                # these formats to lighter libs. Tracked as follow-up tech debt.
                print(f"📄 Parsing {os.path.basename(file_path)} with Unstructured...")
                elements = []

                if ext == ".docx":
                    elements = partition_docx(filename=file_path)
                elif ext == ".txt":
                    elements = partition_text(filename=file_path)
                elif ext == ".md":
                    elements = partition_md(filename=file_path)
                elif ext in (".html", ".htm"):
                    elements = partition_html(filename=file_path)
                else:
                    return []

                element_sections = self._build_element_sections(elements)

                chunked_elements = chunk_by_title(
                    elements,
                    max_characters=2000,
                    new_after_n_chars=1800,
                    combine_text_under_n_chars=200,
                    multipage_sections=True
                )

                base_chunks = []
                for i, element in enumerate(chunked_elements):
                    section = self._recover_section(element, elements, element_sections)
                    start_page, end_page = self._recover_page_range(element)
                    page_range = (f"{start_page}-{end_page}"
                                  if start_page != end_page else str(start_page))
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

                    if element.category == "Table":
                        html_repr = getattr(element.metadata, "text_as_html", None)
                        if html_repr:
                            chunk["metadata"]["table_html"] = html_repr
                        chunk["metadata"]["is_authoritative"] = True

                    base_chunks.append(chunk)

                final_chunks = self._apply_semantic_chunking(base_chunks)

            print(f"   - Parsed {len(final_chunks)} chunks")

            # Save to cache
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
