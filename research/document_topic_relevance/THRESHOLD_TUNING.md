# Threshold tuning

Document-grouped cross-validation; objective = macro-F1 over classes 1 & 2.
`CV F1` is the honest held-out estimate; `full-set F1` is optimistic (thresholds
chosen on the same data).

| Predictor              |      low |    high | CV F1(1&2) mean | CV F1(1&2) std | full-set F1(1&2) |
| ---------------------- | -------: | ------: | --------------: | -------------: | ---------------: |
| mention-density        | 0.001874 | 0.04477 |           0.591 |          0.050 |            0.615 |
| tfidf-density-cf       |  0.00969 | 0.09477 |           0.585 |          0.068 |            0.615 |
| tfidf-density-df       |   0.0017 | 0.03091 |           0.580 |          0.066 |            0.609 |
| decay-weighted         |    1.984 |   97.36 |           0.573 |          0.085 |            0.569 |
| first-10-pages         |        0 |       7 |           0.572 |          0.034 |            0.575 |
| first-10-pages-density |        0 | 0.01564 |           0.566 |          0.038 |            0.574 |
| first-5-pages          |        0 |       3 |           0.558 |          0.035 |            0.559 |
| mention-count          |      3.7 |   308.6 |           0.550 |          0.075 |            0.568 |
| max-mentions-per-page  |        2 |    11.2 |           0.539 |          0.069 |            0.539 |
| tfidf-count-cf         |    20.73 |   404.2 |           0.536 |          0.059 |            0.554 |
| first-15-pages         |        0 |      11 |           0.533 |          0.061 |            0.550 |
| earliest-mention-page  |        2 |    43.2 |           0.517 |          0.027 |            0.525 |
| tfidf-count-df         |    3.809 |    73.6 |           0.504 |          0.051 |            0.512 |
| first-fraction         |      1.5 |      16 |           0.476 |          0.063 |            0.512 |
| earliest-mention       |   0.3823 |  0.9854 |           0.460 |          0.036 |            0.497 |
| first-3-pages          |        0 |       1 |           0.455 |          0.055 |            0.509 |
| max-section-density    |  0.09091 |       1 |           0.446 |          0.076 |            0.464 |
| tfidf-lognorm-df       |   0.2851 |   3.514 |           0.303 |          0.042 |            0.324 |
