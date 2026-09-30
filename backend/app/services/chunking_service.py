def chunk_text(text: str, chunk_size_words: int = 150, overlap_words: int = 30) -> list[str]:
    """Create overlapping verification chunks, excluding unusable short fragments."""
    if chunk_size_words <= 0 or overlap_words < 0 or overlap_words >= chunk_size_words:
        raise ValueError("chunk_size_words must be positive and overlap_words must be smaller")
    words = text.split()
    chunks: list[str] = []
    step = chunk_size_words - overlap_words
    for start in range(0, len(words), step):
        chunk = words[start:start + chunk_size_words]
        if len(chunk) < 15:
            continue
        chunks.append(" ".join(chunk))
        if start + chunk_size_words >= len(words):
            break
    return chunks
