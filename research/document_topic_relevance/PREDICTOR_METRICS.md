# Document-topic relevance evaluation

- Dataset:
  `/Users/kalyan/Documents/CPR/search/research/document_topic_relevance/data/dataset.jsonl`
- Examples: 617 (49 documents × 16 topics)
- Predictors: any-mention-is-relevant

## Pointwise (over all pairs)

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     0.995 |  0.819 | 0.899 |     503 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |      77 |
| any-mention-is-relevant |     2 |     0.182 |  1.000 | 0.308 |      37 |

## Macro average across documents (skipping zero-support groups per class)

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     0.996 |  0.831 | 0.887 |     503 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |      77 |
| any-mention-is-relevant |     2 |     0.248 |  1.000 | 0.374 |      37 |

## Macro-average across topics (skipping zero-support groups per class)

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     0.996 |  0.779 | 0.867 |     503 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |      77 |
| any-mention-is-relevant |     2 |     0.255 |  1.000 | 0.353 |      37 |

## Per-document breakdowns

### `CCLW.document.i00002213.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       7 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `CCLW.document.i00003683.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.769 | 0.870 |      13 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant |     2 |     0.167 |  1.000 | 0.286 |       1 |

### `CCLW.document.i00005517.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.909 | 0.952 |      11 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant |     2 |     0.333 |  1.000 | 0.500 |       2 |

### `CCLW.document.i00006704.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       9 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `CCLW.document.i00007888.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.857 | 0.923 |      14 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.500 |  1.000 | 0.667 |       2 |

### `CCLW.executive.10182.4764`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |      13 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `CCLW.executive.10356.4997`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       9 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `CCLW.executive.9192.1221`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |      14 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `CCLW.legislative.10843.6116`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.692 | 0.818 |      13 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant |     2 |     0.286 |  1.000 | 0.444 |       2 |

### `CCLW.legislative.rtl_3.rtl_5`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.750 | 0.857 |      12 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant |     2 |     0.143 |  1.000 | 0.250 |       1 |

### `CPR.document.i00003375.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.600 | 0.750 |      10 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       6 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `CPR.document.i00004424.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.500 | 0.667 |       8 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       7 |
| any-mention-is-relevant |     2 |     0.083 |  1.000 | 0.154 |       1 |

### `GCF.document.FP051_16090.21078`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.800 | 0.889 |      10 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant |     2 |     0.250 |  1.000 | 0.400 |       2 |

### `GCF.document.FP199_23210.17324`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.818 | 0.900 |      11 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant |     2 |     0.143 |  1.000 | 0.250 |       1 |

### `GCF.document.FP215_24850.16116`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       5 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `GCF.document.FP228_27310.17090`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.444 | 0.615 |       9 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant |     2 |     0.182 |  1.000 | 0.308 |       2 |

### `GEF.document.11136.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       7 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `GEF.document.11143.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.700 | 0.824 |      10 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant |     2 |     0.222 |  1.000 | 0.364 |       2 |

### `OEP.document.i00000091.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       6 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `Sabin.document.10287.10288`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |      11 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `Sabin.document.109700.130909`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.667 | 0.800 |      12 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant |     2 |     0.125 |  1.000 | 0.222 |       1 |

### `Sabin.document.126888.126889`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |      13 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant |     2 |     0.667 |  1.000 | 0.800 |       2 |

### `Sabin.document.12885.14299`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.833 | 0.909 |      12 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant |     2 |     0.167 |  1.000 | 0.286 |       1 |

### `Sabin.document.14285.14286`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |      15 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `Sabin.document.155.7947`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.231 | 0.375 |      13 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant |     2 |     0.077 |  1.000 | 0.143 |       1 |

### `Sabin.document.16314.67362`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |      13 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `Sabin.document.18913.67778`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     0.889 |  0.571 | 0.696 |      14 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant |     2 |     0.143 |  1.000 | 0.250 |       1 |

### `Sabin.document.19022.19276`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.857 | 0.923 |      14 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant |     2 |     0.250 |  1.000 | 0.400 |       1 |

### `Sabin.document.3635.3636`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     0.923 |  0.857 | 0.889 |      14 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant |     2 |     0.333 |  1.000 | 0.500 |       1 |

### `Sabin.document.43062.43063`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.182 | 0.308 |      11 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant |     2 |     0.071 |  1.000 | 0.133 |       1 |

### `Sabin.document.6700.6809`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.750 | 0.857 |      16 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `Sabin.document.7023.7024`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.933 | 0.966 |      15 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `Sabin.document.8001.8002`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |      16 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.document.i00000279.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |      12 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.document.i00000326.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |      11 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant |     2 |     0.400 |  1.000 | 0.571 |       2 |

### `UNFCCC.document.i00002301.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       5 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.document.i00003501.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       6 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.document.i00003855.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.444 | 0.615 |       9 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant |     2 |     0.182 |  1.000 | 0.308 |       2 |

### `UNFCCC.document.i00004003.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       3 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.document.i00004212.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       5 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.document.i00005049.n0000`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.636 | 0.778 |      11 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant |     2 |     0.222 |  1.000 | 0.364 |       2 |

### `UNFCCC.non-party.1262.0`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.929 | 0.963 |      14 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.667 |  1.000 | 0.800 |       2 |

### `UNFCCC.non-party.1720.0`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       8 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.non-party.1820.0`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       8 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.party.1513.0`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.333 | 0.500 |       9 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant |     2 |     0.167 |  1.000 | 0.286 |       2 |

### `UNFCCC.party.1785.0`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |      13 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.party.631.0`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       1 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.party.770.0`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.667 | 0.800 |       6 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       8 |
| any-mention-is-relevant |     2 |     0.167 |  1.000 | 0.286 |       2 |

### `UNFCCC.party.82.0`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  1.000 | 1.000 |       2 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

## Per-topic breakdowns

### `concept::Q1282`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     0.962 |  0.781 | 0.862 |      32 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant |     2 |     0.167 |  1.000 | 0.286 |       2 |

### `concept::Q1346`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     0.978 |  1.000 | 0.989 |      44 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant |     2 |     1.000 |  1.000 | 1.000 |       1 |

### `concept::Q1652`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.818 | 0.900 |      33 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant |     2 |     0.100 |  1.000 | 0.182 |       1 |

### `concept::Q1829`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.667 | 0.800 |       9 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |      13 |
| any-mention-is-relevant |     2 |     0.360 |  1.000 | 0.529 |       9 |

### `concept::Q1832`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.808 | 0.894 |      26 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |      10 |
| any-mention-is-relevant |     2 |     0.062 |  1.000 | 0.118 |       1 |

### `concept::Q218`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.706 | 0.828 |      17 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       6 |
| any-mention-is-relevant |     2 |     0.389 |  1.000 | 0.560 |       7 |

### `concept::Q226`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.917 | 0.957 |      36 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `concept::Q557`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.538 | 0.700 |      13 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       6 |
| any-mention-is-relevant |     2 |     0.455 |  1.000 | 0.625 |      10 |

### `concept::Q567`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.500 | 0.667 |      22 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |      10 |
| any-mention-is-relevant |     2 |     0.087 |  1.000 | 0.160 |       2 |

### `concept::Q615`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.933 | 0.966 |      45 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `concept::Q69`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.837 | 0.911 |      43 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `concept::Q701`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.875 | 0.933 |      40 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant |     2 |     0.125 |  1.000 | 0.222 |       1 |

### `concept::Q704`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.750 | 0.857 |      28 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       9 |
| any-mention-is-relevant |     2 |     0.059 |  1.000 | 0.111 |       1 |

### `concept::Q715`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.621 | 0.766 |      29 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       5 |
| any-mention-is-relevant |     2 |     0.059 |  1.000 | 0.111 |       1 |

### `concept::Q979`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.791 | 0.883 |      43 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `concept::Q983`

| Predictor               | Class | Precision | Recall |    F1 | Support |
| ----------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant |     0 |     1.000 |  0.930 | 0.964 |      43 |
| any-mention-is-relevant |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant |     2 |     0.200 |  1.000 | 0.333 |       1 |
