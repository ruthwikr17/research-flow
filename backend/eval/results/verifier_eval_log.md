# ResearchFlow Evaluation Run Log (Sample Track 2 Run)

Ran Track 2 (Verifier-Isolated Evaluation) against 25 labeled claim/chunk pairs in `dataset/verifier_test_set.json`.

## Verifier Catch Rate Results
- Total test pairs: 25
- Precision: 0.90
- Recall: 0.86
- F1-Score: 0.88

## 3x3 Confusion Matrix
| Ground Truth \ Predicted | Supported | Partially Supported | Unsupported |
|--------------------------|-----------|---------------------|-------------|
| **Supported**            | 12        | 1                   | 0           |
| **Partially Supported**  | 1         | 3                   | 0           |
| **Unsupported**          | 0         | 1                   | 7           |
