from unittest.mock import MagicMock
from app.schemas.verification import ClaimVerdict
from eval.run_eval import run_track_2


def test_track_2_bypasses_search_and_retrieval():
    mock_verifier = MagicMock()
    mock_verifier.call_structured.return_value = MagicMock(
        verdict="supported",
        confidence=0.95,
        reasoning="Direct match.",
        audit_chunk_text="sample chunk",
    )

    results = run_track_2(mock_verifier, max_samples=2)

    assert mock_verifier.call_structured.call_count == 2
    assert "verifier_f1" in results
    assert "verifier_precision" in results
    assert "verifier_recall" in results
    assert "confusion_matrix" in results
