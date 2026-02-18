import os
from typing import List, Dict
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.docx import partition_docx
from unstructured.partition.text import partition_text
from unstructured.chunking.title import chunk_by_title

class SmartPDFParser:
    def __init__(self):
        pass

    def parse_with_metadata(self, file_path: str) -> List[Dict]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        elements = []

        try:
            print(f"📄 Parsing {file_path} with Unstructured...")
            if ext == ".pdf":
                # 'hi_res' uses layout analysis (detects tables vs text columns)
                elements = partition_pdf(
                    filename=file_path,
                    strategy="auto",   # hi_res if you want layout analysis but will take time on cpu
                    infer_table_structure=True
                )
            elif ext == ".docx":
                elements = partition_docx(filename=file_path)
            elif ext == ".txt":
                elements = partition_text(filename=file_path)
            else:
                return []

            # --- 🆕 TEMPORAL ANCHORING (STICKY HEADERS) ---
            # We explicitly tag every element with its parent section before chunking
            current_section = "General"
            for el in elements:
                if el.category == "Title":
                    current_section = str(el)
                
                # Inject the section into the metadata so it survives chunking
                if not hasattr(el, "metadata"):
                    el.metadata = {}
                el.metadata.section = current_section

            # SEMANTIC CHUNKING
            chunked_elements = chunk_by_title(
                elements,
                max_characters=2000,
                new_after_n_chars=1800,
                combine_text_under_n_chars=500
            )

            final_chunks = []
            for i, element in enumerate(chunked_elements):
                page_num = element.metadata.page_number if element.metadata.page_number else 1
                
                # Retrieve our sticky section (Unstructured might bury it in orig_elements)
                # Fallback to the text content if metadata is lost
                section = getattr(element.metadata, "section", "General")
                
                final_chunks.append({
                    "text": str(element),
                    "metadata": {
                        "source": os.path.basename(file_path),
                        "page": page_num,
                        "chunk_id": i,
                        "type": element.category,
                        "section": section # <--- CRITICAL: Time Context Saved Here
                    }
                })
            
            return final_chunks

        except Exception as e:
            print(f"❌ Error parsing {file_path}: {e}")
            return []