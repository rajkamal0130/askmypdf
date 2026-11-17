"""Step 2 of the upload pipeline: split page text into overlapping chunks."""
from backend.config import CHUNK_SIZE, CHUNK_OVERLAP

SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _recursive_split(text: str, size: int, seps: list[str]) -> list[str]:
    if len(text) <= size:
        return [text]
    sep = seps[0]
    rest = seps[1:]
    if sep == "":
        return [text[i : i + size] for i in range(0, len(text), size)]

    pieces = text.split(sep)
    out, buf = [], ""
    for piece in pieces:
        candidate = f"{buf}{sep}{piece}" if buf else piece
        if len(candidate) <= size:
            buf = candidate
        else:
            if buf:
                out.append(buf)
            if len(piece) > size:
                out.extend(_recursive_split(piece, size, rest))
                buf = ""
            else:
                buf = piece
    if buf:
        out.append(buf)
    return out


def split_segments(segments: list[dict]) -> list[dict]:
    """Turn loader segments into chunks with overlap and metadata."""
    chunks = []
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        parts = _recursive_split(text, CHUNK_SIZE - CHUNK_OVERLAP, SEPARATORS)
        for i, part in enumerate(parts):
            # prepend tail of previous part as overlap
            if i > 0 and CHUNK_OVERLAP > 0:
                part = parts[i - 1][-CHUNK_OVERLAP:] + part
            part = part.strip()
            if part:
                chunks.append(
                    {"text": part, "source": seg["source"], "page": seg["page"]}
                )
    return chunks
