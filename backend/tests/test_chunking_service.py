from app.services.chunking_service import chunk_text


def test_chunking_has_expected_overlap():
    words = [f"w{i}" for i in range(34)]
    chunks = chunk_text(" ".join(words), chunk_size_words=20, overlap_words=5)
    assert len(chunks) == 2
    assert chunks[0].split()[-5:] == chunks[1].split()[:5]


def test_near_empty_trailing_chunk_is_dropped():
    words = [f"w{i}" for i in range(44)]
    chunks = chunk_text(" ".join(words), chunk_size_words=20, overlap_words=5)
    assert len(chunks) == 2
