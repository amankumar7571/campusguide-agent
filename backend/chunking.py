"""Document chunking: split Markdown/text into section-aware chunks."""
import re

from .config import CHUNK_OVERLAP, CHUNK_SIZE


def split_sections(text: str):
    """Return [(section_title, section_text)] split on Markdown headings."""
    parts = re.split(r"(?m)^(#{1,3}\s+.*)$", text)
    sections, current_title, buf = [], "", []
    # parts alternates: text, heading, text, heading, ...
    for i, part in enumerate(parts):
        if i % 2 == 1:  # heading line
            if buf:
                sections.append((current_title, "\n".join(buf).strip()))
                buf = []
            current_title = re.sub(r"^#+\s*", "", part).strip()
        else:
            buf.append(part)
    if buf and "\n".join(buf).strip():
        sections.append((current_title, "\n".join(buf).strip()))
    return sections or [("", text.strip())]


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP):
    """Greedy paragraph packing with character overlap between chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for para in paragraphs:
        if len(cur) + len(para) + 2 <= chunk_size:
            cur = f"{cur}\n\n{para}".strip() if cur else para
        else:
            if cur:
                chunks.append(cur)
            if len(para) > chunk_size:  # hard-split a very long paragraph
                for i in range(0, len(para), chunk_size - overlap):
                    chunks.append(para[i:i + chunk_size])
                cur = ""
            else:
                cur = para
    if cur:
        chunks.append(cur)
    return chunks


def chunk_document(text: str):
    """Return [{section, text, chunk_index}] for a whole document."""
    out = []
    for section, body in split_sections(text):
        for chunk in chunk_text(body):
            out.append({"section": section, "text": chunk,
                        "chunk_index": len(out)})
    return out
