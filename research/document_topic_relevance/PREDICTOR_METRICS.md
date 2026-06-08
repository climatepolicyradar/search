# Document-topic relevance evaluation

- Dataset:
  `/Users/kalyan/Documents/CPR/search/research/document_topic_relevance/data/dataset.jsonl`
- Examples: 784 (49 documents × 16 topics)
- Predictors: any-mention-is-relevant, mention-count, mention-density,
  max-mentions-per-page, max-section-density, earliest-mention,
  earliest-mention-page, first-fraction, decay-weighted, first-3-pages,
  first-5-pages, first-10-pages, first-15-pages, first-10-pages-density, (count
  or density) and early, density and early

## Summary — pointwise over all pairs (sorted by F1 on classes 1 & 2)

| Predictor                    | Precision | Recall |    F1 | F1 (cls 1&2) | P (cls1) | R (cls1) | P (cls2) | R (cls2) | Support |
| ---------------------------- | --------: | -----: | ----: | -----------: | -------: | -------: | -------: | -------: | ------: |
| mention-density              |     0.702 |  0.748 | 0.717 |        0.615 |    0.514 |    0.736 |    0.622 |    0.630 |     784 |
| first-10-pages               |     0.660 |  0.733 | 0.659 |        0.575 |    0.359 |    0.806 |    0.625 |    0.685 |     784 |
| (count or density) and early |     0.687 |  0.709 | 0.686 |        0.574 |    0.475 |    0.744 |    0.623 |    0.521 |     784 |
| first-10-pages-density       |     0.635 |  0.758 | 0.658 |        0.574 |    0.371 |    0.744 |    0.541 |    0.822 |     784 |
| decay-weighted               |     0.747 |  0.682 | 0.687 |        0.569 |    0.519 |    0.744 |    0.784 |    0.397 |     784 |
| mention-count                |     0.741 |  0.704 | 0.686 |        0.568 |    0.495 |    0.853 |    0.757 |    0.384 |     784 |
| first-5-pages                |     0.647 |  0.723 | 0.649 |        0.559 |    0.355 |    0.791 |    0.590 |    0.671 |     784 |
| first-15-pages               |     0.649 |  0.709 | 0.643 |        0.550 |    0.341 |    0.775 |    0.610 |    0.644 |     784 |
| density and early            |     0.680 |  0.681 | 0.670 |        0.547 |    0.481 |    0.690 |    0.607 |    0.466 |     784 |
| max-mentions-per-page        |     0.652 |  0.691 | 0.664 |        0.539 |    0.447 |    0.659 |    0.541 |    0.548 |     784 |
| earliest-mention-page        |     0.616 |  0.702 | 0.644 |        0.525 |    0.420 |    0.612 |    0.463 |    0.685 |     784 |
| first-fraction               |     0.652 |  0.643 | 0.646 |        0.512 |    0.509 |    0.426 |    0.545 |    0.575 |     784 |
| first-3-pages                |     0.602 |  0.699 | 0.615 |        0.509 |    0.347 |    0.705 |    0.463 |    0.685 |     784 |
| earliest-mention             |     0.615 |  0.667 | 0.616 |        0.497 |    0.367 |    0.736 |    0.500 |    0.507 |     784 |
| max-section-density          |     0.620 |  0.630 | 0.610 |        0.464 |    0.413 |    0.682 |    0.491 |    0.356 |     784 |
| any-mention-is-relevant      |     0.397 |  0.569 | 0.386 |        0.165 |    0.000 |    0.000 |    0.197 |    1.000 |     784 |

## Summary — macro-averaged by document (sorted by F1 on classes 1 & 2)

| Predictor                    | Precision | Recall |    F1 | F1 (cls 1&2) | P (cls1) | R (cls1) | P (cls2) | R (cls2) | Support |
| ---------------------------- | --------: | -----: | ----: | -----------: | -------: | -------: | -------: | -------: | ------: |
| mention-density              |     0.680 |  0.725 | 0.670 |        0.546 |    0.502 |    0.672 |    0.570 |    0.620 |     784 |
| first-10-pages-density       |     0.641 |  0.710 | 0.610 |        0.524 |    0.346 |    0.641 |    0.580 |    0.808 |     784 |
| first-5-pages                |     0.653 |  0.685 | 0.610 |        0.523 |    0.400 |    0.720 |    0.562 |    0.657 |     784 |
| first-10-pages               |     0.645 |  0.697 | 0.609 |        0.521 |    0.381 |    0.765 |    0.557 |    0.645 |     784 |
| (count or density) and early |     0.647 |  0.689 | 0.633 |        0.498 |    0.475 |    0.705 |    0.506 |    0.500 |     784 |
| first-15-pages               |     0.627 |  0.667 | 0.586 |        0.487 |    0.367 |    0.730 |    0.519 |    0.593 |     784 |
| mention-count                |     0.632 |  0.674 | 0.619 |        0.478 |    0.509 |    0.808 |    0.413 |    0.355 |     784 |
| density and early            |     0.625 |  0.674 | 0.618 |        0.472 |    0.486 |    0.677 |    0.442 |    0.452 |     784 |
| earliest-mention-page        |     0.597 |  0.685 | 0.598 |        0.463 |    0.411 |    0.576 |    0.418 |    0.674 |     784 |
| max-mentions-per-page        |     0.620 |  0.664 | 0.606 |        0.460 |    0.467 |    0.652 |    0.422 |    0.488 |     784 |
| first-3-pages                |     0.583 |  0.661 | 0.559 |        0.446 |    0.333 |    0.630 |    0.418 |    0.674 |     784 |
| decay-weighted               |     0.594 |  0.640 | 0.591 |        0.432 |    0.437 |    0.652 |    0.401 |    0.372 |     784 |
| earliest-mention             |     0.569 |  0.637 | 0.553 |        0.419 |    0.374 |    0.724 |    0.354 |    0.453 |     784 |
| first-fraction               |     0.596 |  0.622 | 0.580 |        0.417 |    0.431 |    0.400 |    0.452 |    0.547 |     784 |
| max-section-density          |     0.539 |  0.581 | 0.532 |        0.359 |    0.388 |    0.616 |    0.271 |    0.297 |     784 |
| any-mention-is-relevant      |     0.414 |  0.560 | 0.387 |        0.189 |    0.000 |    0.000 |    0.245 |    1.000 |     784 |

## Summary — macro-averaged by topic (sorted by F1 on classes 1 & 2)

| Predictor                    | Precision | Recall |    F1 | F1 (cls 1&2) | P (cls1) | R (cls1) | P (cls2) | R (cls2) | Support |
| ---------------------------- | --------: | -----: | ----: | -----------: | -------: | -------: | -------: | -------: | ------: |
| first-10-pages-density       |     0.636 |  0.724 | 0.609 |        0.524 |    0.410 |    0.794 |    0.503 |    0.715 |     784 |
| mention-density              |     0.673 |  0.670 | 0.632 |        0.510 |    0.566 |    0.692 |    0.475 |    0.495 |     784 |
| first-5-pages                |     0.644 |  0.695 | 0.597 |        0.506 |    0.393 |    0.844 |    0.544 |    0.577 |     784 |
| first-10-pages               |     0.641 |  0.690 | 0.592 |        0.498 |    0.395 |    0.854 |    0.533 |    0.553 |     784 |
| (count or density) and early |     0.638 |  0.649 | 0.602 |        0.467 |    0.502 |    0.702 |    0.450 |    0.427 |     784 |
| earliest-mention-page        |     0.587 |  0.652 | 0.581 |        0.452 |    0.435 |    0.602 |    0.365 |    0.590 |     784 |
| first-3-pages                |     0.583 |  0.672 | 0.559 |        0.449 |    0.388 |    0.760 |    0.365 |    0.590 |     784 |
| density and early            |     0.640 |  0.617 | 0.590 |        0.446 |    0.523 |    0.608 |    0.448 |    0.405 |     784 |
| mention-count                |     0.611 |  0.648 | 0.596 |        0.444 |    0.518 |    0.825 |    0.348 |    0.270 |     784 |
| first-15-pages               |     0.592 |  0.654 | 0.551 |        0.436 |    0.363 |    0.832 |    0.417 |    0.467 |     784 |
| decay-weighted               |     0.625 |  0.598 | 0.589 |        0.435 |    0.502 |    0.677 |    0.454 |    0.238 |     784 |
| max-mentions-per-page        |     0.591 |  0.642 | 0.584 |        0.432 |    0.475 |    0.695 |    0.341 |    0.394 |     784 |
| earliest-mention             |     0.574 |  0.638 | 0.555 |        0.423 |    0.399 |    0.723 |    0.349 |    0.469 |     784 |
| max-section-density          |     0.543 |  0.605 | 0.539 |        0.371 |    0.444 |    0.697 |    0.243 |    0.294 |     784 |
| first-fraction               |     0.545 |  0.571 | 0.541 |        0.365 |    0.409 |    0.376 |    0.346 |    0.432 |     784 |
| any-mention-is-relevant      |     0.391 |  0.555 | 0.354 |        0.141 |    0.000 |    0.000 |    0.176 |    1.000 |     784 |

## Summary — binary: relevant (1 or 2) vs not (0), sorted by F1

| Predictor                    | Precision | Recall |    F1 | Positives |
| ---------------------------- | --------: | -----: | ----: | --------: |
| mention-count                |     0.722 |  0.926 | 0.811 |       202 |
| mention-density              |     0.722 |  0.926 | 0.811 |       202 |
| max-mentions-per-page        |     0.705 |  0.921 | 0.798 |       202 |
| density and early            |     0.726 |  0.866 | 0.790 |       202 |
| decay-weighted               |     0.752 |  0.827 | 0.788 |       202 |
| (count or density) and early |     0.696 |  0.906 | 0.787 |       202 |
| max-section-density          |     0.677 |  0.891 | 0.769 |       202 |
| earliest-mention-page        |     0.625 |  0.916 | 0.743 |       202 |
| first-fraction               |     0.773 |  0.708 | 0.739 |       202 |
| earliest-mention             |     0.577 |  0.950 | 0.718 |       202 |
| any-mention-is-relevant      |     0.541 |  0.990 | 0.699 |       202 |
| first-3-pages                |     0.541 |  0.990 | 0.699 |       202 |
| first-5-pages                |     0.541 |  0.990 | 0.699 |       202 |
| first-10-pages               |     0.541 |  0.990 | 0.699 |       202 |
| first-15-pages               |     0.541 |  0.990 | 0.699 |       202 |
| first-10-pages-density       |     0.541 |  0.990 | 0.699 |       202 |

## Pointwise (over all pairs)

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     0.995 |  0.708 | 0.827 |     582 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |     129 |
| any-mention-is-relevant      |     2 |     0.197 |  1.000 | 0.330 |      73 |
| mention-count                |     0 |     0.971 |  0.876 | 0.921 |     582 |
| mention-count                |     1 |     0.495 |  0.853 | 0.627 |     129 |
| mention-count                |     2 |     0.757 |  0.384 | 0.509 |      73 |
| mention-density              |     0 |     0.971 |  0.876 | 0.921 |     582 |
| mention-density              |     1 |     0.514 |  0.736 | 0.605 |     129 |
| mention-density              |     2 |     0.622 |  0.630 | 0.626 |      73 |
| max-mentions-per-page        |     0 |     0.969 |  0.866 | 0.915 |     582 |
| max-mentions-per-page        |     1 |     0.447 |  0.659 | 0.533 |     129 |
| max-mentions-per-page        |     2 |     0.541 |  0.548 | 0.544 |      73 |
| max-section-density          |     0 |     0.958 |  0.852 | 0.902 |     582 |
| max-section-density          |     1 |     0.413 |  0.682 | 0.515 |     129 |
| max-section-density          |     2 |     0.491 |  0.356 | 0.413 |      73 |
| earliest-mention             |     0 |     0.978 |  0.758 | 0.854 |     582 |
| earliest-mention             |     1 |     0.367 |  0.736 | 0.490 |     129 |
| earliest-mention             |     2 |     0.500 |  0.507 | 0.503 |      73 |
| earliest-mention-page        |     0 |     0.965 |  0.809 | 0.880 |     582 |
| earliest-mention-page        |     1 |     0.420 |  0.612 | 0.498 |     129 |
| earliest-mention-page        |     2 |     0.463 |  0.685 | 0.552 |      73 |
| first-fraction               |     0 |     0.902 |  0.928 | 0.914 |     582 |
| first-fraction               |     1 |     0.509 |  0.426 | 0.464 |     129 |
| first-fraction               |     2 |     0.545 |  0.575 | 0.560 |      73 |
| decay-weighted               |     0 |     0.938 |  0.905 | 0.921 |     582 |
| decay-weighted               |     1 |     0.519 |  0.744 | 0.611 |     129 |
| decay-weighted               |     2 |     0.784 |  0.397 | 0.527 |      73 |
| first-3-pages                |     0 |     0.995 |  0.708 | 0.827 |     582 |
| first-3-pages                |     1 |     0.347 |  0.705 | 0.465 |     129 |
| first-3-pages                |     2 |     0.463 |  0.685 | 0.552 |      73 |
| first-5-pages                |     0 |     0.995 |  0.708 | 0.827 |     582 |
| first-5-pages                |     1 |     0.355 |  0.791 | 0.490 |     129 |
| first-5-pages                |     2 |     0.590 |  0.671 | 0.628 |      73 |
| first-10-pages               |     0 |     0.995 |  0.708 | 0.827 |     582 |
| first-10-pages               |     1 |     0.359 |  0.806 | 0.496 |     129 |
| first-10-pages               |     2 |     0.625 |  0.685 | 0.654 |      73 |
| first-15-pages               |     0 |     0.995 |  0.708 | 0.827 |     582 |
| first-15-pages               |     1 |     0.341 |  0.775 | 0.474 |     129 |
| first-15-pages               |     2 |     0.610 |  0.644 | 0.627 |      73 |
| first-10-pages-density       |     0 |     0.995 |  0.708 | 0.827 |     582 |
| first-10-pages-density       |     1 |     0.371 |  0.744 | 0.495 |     129 |
| first-10-pages-density       |     2 |     0.541 |  0.822 | 0.652 |      73 |
| (count or density) and early |     0 |     0.964 |  0.863 | 0.910 |     582 |
| (count or density) and early |     1 |     0.475 |  0.744 | 0.580 |     129 |
| (count or density) and early |     2 |     0.623 |  0.521 | 0.567 |      73 |
| density and early            |     0 |     0.950 |  0.887 | 0.917 |     582 |
| density and early            |     1 |     0.481 |  0.690 | 0.567 |     129 |
| density and early            |     2 |     0.607 |  0.466 | 0.527 |      73 |

## Macro average across documents (skipping zero-support groups per class)

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     0.996 |  0.679 | 0.784 |     582 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |     129 |
| any-mention-is-relevant      |     2 |     0.245 |  1.000 | 0.377 |      73 |
| mention-count                |     0 |     0.976 |  0.858 | 0.902 |     582 |
| mention-count                |     1 |     0.509 |  0.808 | 0.593 |     129 |
| mention-count                |     2 |     0.413 |  0.355 | 0.363 |      73 |
| mention-density              |     0 |     0.966 |  0.882 | 0.917 |     582 |
| mention-density              |     1 |     0.502 |  0.672 | 0.541 |     129 |
| mention-density              |     2 |     0.570 |  0.620 | 0.551 |      73 |
| max-mentions-per-page        |     0 |     0.972 |  0.850 | 0.898 |     582 |
| max-mentions-per-page        |     1 |     0.467 |  0.652 | 0.511 |     129 |
| max-mentions-per-page        |     2 |     0.422 |  0.488 | 0.409 |      73 |
| max-section-density          |     0 |     0.960 |  0.829 | 0.878 |     582 |
| max-section-density          |     1 |     0.388 |  0.616 | 0.457 |     129 |
| max-section-density          |     2 |     0.271 |  0.297 | 0.262 |      73 |
| earliest-mention             |     0 |     0.980 |  0.733 | 0.821 |     582 |
| earliest-mention             |     1 |     0.374 |  0.724 | 0.473 |     129 |
| earliest-mention             |     2 |     0.354 |  0.453 | 0.365 |      73 |
| earliest-mention-page        |     0 |     0.962 |  0.804 | 0.867 |     582 |
| earliest-mention-page        |     1 |     0.411 |  0.576 | 0.438 |     129 |
| earliest-mention-page        |     2 |     0.418 |  0.674 | 0.489 |      73 |
| first-fraction               |     0 |     0.906 |  0.918 | 0.905 |     582 |
| first-fraction               |     1 |     0.431 |  0.400 | 0.380 |     129 |
| first-fraction               |     2 |     0.452 |  0.547 | 0.455 |      73 |
| decay-weighted               |     0 |     0.943 |  0.896 | 0.911 |     582 |
| decay-weighted               |     1 |     0.437 |  0.652 | 0.498 |     129 |
| decay-weighted               |     2 |     0.401 |  0.372 | 0.366 |      73 |
| first-3-pages                |     0 |     0.996 |  0.679 | 0.784 |     582 |
| first-3-pages                |     1 |     0.333 |  0.630 | 0.404 |     129 |
| first-3-pages                |     2 |     0.418 |  0.674 | 0.489 |      73 |
| first-5-pages                |     0 |     0.996 |  0.679 | 0.784 |     582 |
| first-5-pages                |     1 |     0.400 |  0.720 | 0.486 |     129 |
| first-5-pages                |     2 |     0.562 |  0.657 | 0.560 |      73 |
| first-10-pages               |     0 |     0.996 |  0.679 | 0.784 |     582 |
| first-10-pages               |     1 |     0.381 |  0.765 | 0.488 |     129 |
| first-10-pages               |     2 |     0.557 |  0.645 | 0.555 |      73 |
| first-15-pages               |     0 |     0.996 |  0.679 | 0.784 |     582 |
| first-15-pages               |     1 |     0.367 |  0.730 | 0.463 |     129 |
| first-15-pages               |     2 |     0.519 |  0.593 | 0.510 |      73 |
| first-10-pages-density       |     0 |     0.996 |  0.679 | 0.784 |     582 |
| first-10-pages-density       |     1 |     0.346 |  0.641 | 0.421 |     129 |
| first-10-pages-density       |     2 |     0.580 |  0.808 | 0.627 |      73 |
| (count or density) and early |     0 |     0.961 |  0.862 | 0.903 |     582 |
| (count or density) and early |     1 |     0.475 |  0.705 | 0.535 |     129 |
| (count or density) and early |     2 |     0.506 |  0.500 | 0.462 |      73 |
| density and early            |     0 |     0.947 |  0.893 | 0.912 |     582 |
| density and early            |     1 |     0.486 |  0.677 | 0.531 |     129 |
| density and early            |     2 |     0.442 |  0.452 | 0.412 |      73 |

## Macro-average across topics (skipping zero-support groups per class)

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     0.996 |  0.664 | 0.780 |     582 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |     129 |
| any-mention-is-relevant      |     2 |     0.176 |  1.000 | 0.281 |      73 |
| mention-count                |     0 |     0.966 |  0.850 | 0.900 |     582 |
| mention-count                |     1 |     0.518 |  0.825 | 0.619 |     129 |
| mention-count                |     2 |     0.348 |  0.270 | 0.270 |      73 |
| mention-density              |     0 |     0.977 |  0.824 | 0.876 |     582 |
| mention-density              |     1 |     0.566 |  0.692 | 0.600 |     129 |
| mention-density              |     2 |     0.475 |  0.495 | 0.421 |      73 |
| max-mentions-per-page        |     0 |     0.957 |  0.836 | 0.888 |     582 |
| max-mentions-per-page        |     1 |     0.475 |  0.695 | 0.541 |     129 |
| max-mentions-per-page        |     2 |     0.341 |  0.394 | 0.324 |      73 |
| max-section-density          |     0 |     0.942 |  0.824 | 0.876 |     582 |
| max-section-density          |     1 |     0.444 |  0.697 | 0.516 |     129 |
| max-section-density          |     2 |     0.243 |  0.294 | 0.226 |      73 |
| earliest-mention             |     0 |     0.973 |  0.721 | 0.818 |     582 |
| earliest-mention             |     1 |     0.399 |  0.723 | 0.482 |     129 |
| earliest-mention             |     2 |     0.349 |  0.469 | 0.365 |      73 |
| earliest-mention-page        |     0 |     0.962 |  0.763 | 0.838 |     582 |
| earliest-mention-page        |     1 |     0.435 |  0.602 | 0.480 |     129 |
| earliest-mention-page        |     2 |     0.365 |  0.590 | 0.425 |      73 |
| first-fraction               |     0 |     0.880 |  0.907 | 0.892 |     582 |
| first-fraction               |     1 |     0.409 |  0.376 | 0.382 |     129 |
| first-fraction               |     2 |     0.346 |  0.432 | 0.348 |      73 |
| decay-weighted               |     0 |     0.919 |  0.879 | 0.896 |     582 |
| decay-weighted               |     1 |     0.502 |  0.677 | 0.564 |     129 |
| decay-weighted               |     2 |     0.454 |  0.238 | 0.306 |      73 |
| first-3-pages                |     0 |     0.996 |  0.664 | 0.780 |     582 |
| first-3-pages                |     1 |     0.388 |  0.760 | 0.472 |     129 |
| first-3-pages                |     2 |     0.365 |  0.590 | 0.425 |      73 |
| first-5-pages                |     0 |     0.996 |  0.664 | 0.780 |     582 |
| first-5-pages                |     1 |     0.393 |  0.844 | 0.504 |     129 |
| first-5-pages                |     2 |     0.544 |  0.577 | 0.508 |      73 |
| first-10-pages               |     0 |     0.996 |  0.664 | 0.780 |     582 |
| first-10-pages               |     1 |     0.395 |  0.854 | 0.506 |     129 |
| first-10-pages               |     2 |     0.533 |  0.553 | 0.490 |      73 |
| first-15-pages               |     0 |     0.996 |  0.664 | 0.780 |     582 |
| first-15-pages               |     1 |     0.363 |  0.832 | 0.483 |     129 |
| first-15-pages               |     2 |     0.417 |  0.467 | 0.389 |      73 |
| first-10-pages-density       |     0 |     0.996 |  0.664 | 0.780 |     582 |
| first-10-pages-density       |     1 |     0.410 |  0.794 | 0.498 |     129 |
| first-10-pages-density       |     2 |     0.503 |  0.715 | 0.549 |      73 |
| (count or density) and early |     0 |     0.961 |  0.817 | 0.871 |     582 |
| (count or density) and early |     1 |     0.502 |  0.702 | 0.557 |     129 |
| (count or density) and early |     2 |     0.450 |  0.427 | 0.376 |      73 |
| density and early            |     0 |     0.951 |  0.840 | 0.879 |     582 |
| density and early            |     1 |     0.523 |  0.608 | 0.534 |     129 |
| density and early            |     2 |     0.448 |  0.405 | 0.359 |      73 |

## Per-document breakdowns

### `CCLW.document.i00002213.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.500 | 0.667 |      14 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant      |     2 |     0.222 |  1.000 | 0.364 |       2 |
| mention-count                |     0 |     1.000 |  0.643 | 0.783 |      14 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| mention-density              |     0 |     1.000 |  0.714 | 0.833 |      14 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.643 | 0.783 |      14 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-section-density          |     0 |     1.000 |  0.714 | 0.833 |      14 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     2 |     0.500 |  0.500 | 0.500 |       2 |
| earliest-mention             |     0 |     1.000 |  0.571 | 0.727 |      14 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.571 | 0.727 |      14 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-fraction               |     0 |     1.000 |  0.714 | 0.833 |      14 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     2 |     0.500 |  0.500 | 0.500 |       2 |
| decay-weighted               |     0 |     1.000 |  0.643 | 0.783 |      14 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-3-pages                |     0 |     1.000 |  0.500 | 0.667 |      14 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-5-pages                |     0 |     1.000 |  0.500 | 0.667 |      14 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-10-pages               |     0 |     1.000 |  0.500 | 0.667 |      14 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-15-pages               |     0 |     1.000 |  0.500 | 0.667 |      14 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.500 | 0.667 |      14 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     2 |     0.667 |  1.000 | 0.800 |       2 |
| (count or density) and early |     0 |     1.000 |  0.643 | 0.783 |      14 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       2 |
| density and early            |     0 |     1.000 |  0.714 | 0.833 |      14 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       2 |

### `CCLW.document.i00003683.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.769 | 0.870 |      13 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant      |     2 |     0.167 |  1.000 | 0.286 |       1 |
| mention-count                |     0 |     1.000 |  0.923 | 0.960 |      13 |
| mention-count                |     1 |     0.667 |  1.000 | 0.800 |       2 |
| mention-count                |     2 |     1.000 |  1.000 | 1.000 |       1 |
| mention-density              |     0 |     1.000 |  0.846 | 0.917 |      13 |
| mention-density              |     1 |     0.333 |  0.500 | 0.400 |       2 |
| mention-density              |     2 |     0.500 |  1.000 | 0.667 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.923 | 0.960 |      13 |
| max-mentions-per-page        |     1 |     0.500 |  0.500 | 0.500 |       2 |
| max-mentions-per-page        |     2 |     0.500 |  1.000 | 0.667 |       1 |
| max-section-density          |     0 |     1.000 |  0.846 | 0.917 |      13 |
| max-section-density          |     1 |     0.333 |  0.500 | 0.400 |       2 |
| max-section-density          |     2 |     0.500 |  1.000 | 0.667 |       1 |
| earliest-mention             |     0 |     1.000 |  0.769 | 0.870 |      13 |
| earliest-mention             |     1 |     0.250 |  0.500 | 0.333 |       2 |
| earliest-mention             |     2 |     0.500 |  1.000 | 0.667 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.769 | 0.870 |      13 |
| earliest-mention-page        |     1 |     0.400 |  1.000 | 0.571 |       2 |
| earliest-mention-page        |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-fraction               |     0 |     0.929 |  1.000 | 0.963 |      13 |
| first-fraction               |     1 |     1.000 |  0.500 | 0.667 |       2 |
| first-fraction               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| decay-weighted               |     0 |     1.000 |  1.000 | 1.000 |      13 |
| decay-weighted               |     1 |     1.000 |  1.000 | 1.000 |       2 |
| decay-weighted               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.769 | 0.870 |      13 |
| first-3-pages                |     1 |     0.400 |  1.000 | 0.571 |       2 |
| first-3-pages                |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-5-pages                |     0 |     1.000 |  0.769 | 0.870 |      13 |
| first-5-pages                |     1 |     0.400 |  1.000 | 0.571 |       2 |
| first-5-pages                |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.769 | 0.870 |      13 |
| first-10-pages               |     1 |     0.250 |  0.500 | 0.333 |       2 |
| first-10-pages               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-15-pages               |     0 |     1.000 |  0.769 | 0.870 |      13 |
| first-15-pages               |     1 |     0.250 |  0.500 | 0.333 |       2 |
| first-15-pages               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.769 | 0.870 |      13 |
| first-10-pages-density       |     1 |     0.250 |  0.500 | 0.333 |       2 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       1 |
| (count or density) and early |     0 |     1.000 |  0.846 | 0.917 |      13 |
| (count or density) and early |     1 |     0.500 |  1.000 | 0.667 |       2 |
| (count or density) and early |     2 |     1.000 |  1.000 | 1.000 |       1 |
| density and early            |     0 |     1.000 |  0.846 | 0.917 |      13 |
| density and early            |     1 |     0.500 |  1.000 | 0.667 |       2 |
| density and early            |     2 |     1.000 |  1.000 | 1.000 |       1 |

### `CCLW.document.i00005517.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.909 | 0.952 |      11 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.333 |  1.000 | 0.500 |       2 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      11 |
| mention-count                |     1 |     0.750 |  1.000 | 0.857 |       3 |
| mention-count                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| mention-density              |     0 |     1.000 |  1.000 | 1.000 |      11 |
| mention-density              |     1 |     0.750 |  1.000 | 0.857 |       3 |
| mention-density              |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  1.000 | 1.000 |      11 |
| max-mentions-per-page        |     1 |     0.750 |  1.000 | 0.857 |       3 |
| max-mentions-per-page        |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-section-density          |     0 |     1.000 |  0.909 | 0.952 |      11 |
| max-section-density          |     1 |     0.600 |  1.000 | 0.750 |       3 |
| max-section-density          |     2 |     1.000 |  0.500 | 0.667 |       2 |
| earliest-mention             |     0 |     1.000 |  0.909 | 0.952 |      11 |
| earliest-mention             |     1 |     0.600 |  1.000 | 0.750 |       3 |
| earliest-mention             |     2 |     1.000 |  0.500 | 0.667 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.909 | 0.952 |      11 |
| earliest-mention-page        |     1 |     0.667 |  0.667 | 0.667 |       3 |
| earliest-mention-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-fraction               |     0 |     0.733 |  1.000 | 0.846 |      11 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       3 |
| first-fraction               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| decay-weighted               |     0 |     0.846 |  1.000 | 0.917 |      11 |
| decay-weighted               |     1 |     0.333 |  0.333 | 0.333 |       3 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.909 | 0.952 |      11 |
| first-3-pages                |     1 |     0.667 |  0.667 | 0.667 |       3 |
| first-3-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-5-pages                |     0 |     1.000 |  0.909 | 0.952 |      11 |
| first-5-pages                |     1 |     0.600 |  1.000 | 0.750 |       3 |
| first-5-pages                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  0.909 | 0.952 |      11 |
| first-10-pages               |     1 |     0.600 |  1.000 | 0.750 |       3 |
| first-10-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-15-pages               |     0 |     1.000 |  0.909 | 0.952 |      11 |
| first-15-pages               |     1 |     0.600 |  1.000 | 0.750 |       3 |
| first-15-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.909 | 0.952 |      11 |
| first-10-pages-density       |     1 |     0.600 |  1.000 | 0.750 |       3 |
| first-10-pages-density       |     2 |     1.000 |  0.500 | 0.667 |       2 |
| (count or density) and early |     0 |     1.000 |  1.000 | 1.000 |      11 |
| (count or density) and early |     1 |     0.750 |  1.000 | 0.857 |       3 |
| (count or density) and early |     2 |     1.000 |  0.500 | 0.667 |       2 |
| density and early            |     0 |     1.000 |  1.000 | 1.000 |      11 |
| density and early            |     1 |     0.750 |  1.000 | 0.857 |       3 |
| density and early            |     2 |     1.000 |  0.500 | 0.667 |       2 |

### `CCLW.document.i00006704.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.692 | 0.818 |      13 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.286 |  1.000 | 0.444 |       2 |
| mention-count                |     0 |     1.000 |  0.846 | 0.917 |      13 |
| mention-count                |     1 |     0.200 |  1.000 | 0.333 |       1 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     1.000 |  0.846 | 0.917 |      13 |
| mention-density              |     1 |     0.333 |  1.000 | 0.500 |       1 |
| mention-density              |     2 |     1.000 |  1.000 | 1.000 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.923 | 0.960 |      13 |
| max-mentions-per-page        |     1 |     0.500 |  1.000 | 0.667 |       1 |
| max-mentions-per-page        |     2 |     1.000 |  1.000 | 1.000 |       2 |
| max-section-density          |     0 |     1.000 |  0.769 | 0.870 |      13 |
| max-section-density          |     1 |     0.167 |  1.000 | 0.286 |       1 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  0.692 | 0.818 |      13 |
| earliest-mention             |     1 |     0.250 |  1.000 | 0.400 |       1 |
| earliest-mention             |     2 |     0.667 |  1.000 | 0.800 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.692 | 0.818 |      13 |
| earliest-mention-page        |     1 |     0.250 |  1.000 | 0.400 |       1 |
| earliest-mention-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-fraction               |     0 |     1.000 |  0.923 | 0.960 |      13 |
| first-fraction               |     1 |     0.500 |  1.000 | 0.667 |       1 |
| first-fraction               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| decay-weighted               |     0 |     1.000 |  0.923 | 0.960 |      13 |
| decay-weighted               |     1 |     0.250 |  1.000 | 0.400 |       1 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-3-pages                |     1 |     0.250 |  1.000 | 0.400 |       1 |
| first-3-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-5-pages                |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-5-pages                |     1 |     0.167 |  1.000 | 0.286 |       1 |
| first-5-pages                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-10-pages               |     1 |     0.200 |  1.000 | 0.333 |       1 |
| first-10-pages               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-15-pages               |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-10-pages-density       |     1 |     0.250 |  1.000 | 0.400 |       1 |
| first-10-pages-density       |     2 |     0.667 |  1.000 | 0.800 |       2 |
| (count or density) and early |     0 |     1.000 |  0.846 | 0.917 |      13 |
| (count or density) and early |     1 |     0.333 |  1.000 | 0.500 |       1 |
| (count or density) and early |     2 |     1.000 |  1.000 | 1.000 |       2 |
| density and early            |     0 |     1.000 |  0.846 | 0.917 |      13 |
| density and early            |     1 |     0.333 |  1.000 | 0.500 |       1 |
| density and early            |     2 |     1.000 |  1.000 | 1.000 |       2 |

### `CCLW.document.i00007888.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.857 | 0.923 |      14 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant      |     2 |     0.500 |  1.000 | 0.667 |       2 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      14 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     1.000 |  0.857 | 0.923 |      14 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  1.000 | 1.000 |      14 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       2 |
| max-section-density          |     0 |     1.000 |  0.857 | 0.923 |      14 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  0.929 | 0.963 |      14 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     2 |     0.667 |  1.000 | 0.800 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.857 | 0.923 |      14 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-fraction               |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| decay-weighted               |     0 |     1.000 |  1.000 | 1.000 |      14 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.857 | 0.923 |      14 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-5-pages                |     0 |     1.000 |  0.857 | 0.923 |      14 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-10-pages               |     0 |     1.000 |  0.857 | 0.923 |      14 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-15-pages               |     0 |     1.000 |  0.857 | 0.923 |      14 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.857 | 0.923 |      14 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     2 |     0.667 |  1.000 | 0.800 |       2 |
| (count or density) and early |     0 |     1.000 |  0.857 | 0.923 |      14 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     2 |     1.000 |  0.500 | 0.667 |       2 |
| density and early            |     0 |     1.000 |  0.857 | 0.923 |      14 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     2 |     1.000 |  0.500 | 0.667 |       2 |

### `CCLW.executive.10182.4764`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.867 | 0.929 |      15 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant      |     2 |     0.333 |  1.000 | 0.500 |       1 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      15 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     1.000 |  0.867 | 0.929 |      15 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     2 |     0.500 |  1.000 | 0.667 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.933 | 0.966 |      15 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     1.000 |  0.933 | 0.966 |      15 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  1.000 | 1.000 |      15 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.867 | 0.929 |      15 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-fraction               |     0 |     0.938 |  1.000 | 0.968 |      15 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.938 |  1.000 | 0.968 |      15 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.867 | 0.929 |      15 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-5-pages                |     0 |     1.000 |  0.867 | 0.929 |      15 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages               |     0 |     1.000 |  0.867 | 0.929 |      15 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.867 | 0.929 |      15 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.867 | 0.929 |      15 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     2 |     0.333 |  1.000 | 0.500 |       1 |
| (count or density) and early |     0 |     1.000 |  0.867 | 0.929 |      15 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     2 |     0.500 |  1.000 | 0.667 |       1 |
| density and early            |     0 |     1.000 |  0.867 | 0.929 |      15 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     2 |     0.500 |  1.000 | 0.667 |       1 |

### `CCLW.executive.10356.4997`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.750 | 0.857 |      12 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.143 |  1.000 | 0.250 |       1 |
| mention-count                |     0 |     1.000 |  0.833 | 0.909 |      12 |
| mention-count                |     1 |     0.500 |  1.000 | 0.667 |       3 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     1.000 |  0.750 | 0.857 |      12 |
| mention-density              |     1 |     0.250 |  0.333 | 0.286 |       3 |
| mention-density              |     2 |     0.333 |  1.000 | 0.500 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.833 | 0.909 |      12 |
| max-mentions-per-page        |     1 |     0.500 |  0.667 | 0.571 |       3 |
| max-mentions-per-page        |     2 |     0.500 |  1.000 | 0.667 |       1 |
| max-section-density          |     0 |     1.000 |  0.750 | 0.857 |      12 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       3 |
| max-section-density          |     2 |     0.200 |  1.000 | 0.333 |       1 |
| earliest-mention             |     0 |     1.000 |  0.750 | 0.857 |      12 |
| earliest-mention             |     1 |     0.250 |  0.333 | 0.286 |       3 |
| earliest-mention             |     2 |     0.333 |  1.000 | 0.500 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.750 | 0.857 |      12 |
| earliest-mention-page        |     1 |     0.250 |  0.333 | 0.286 |       3 |
| earliest-mention-page        |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-fraction               |     0 |     0.923 |  1.000 | 0.960 |      12 |
| first-fraction               |     1 |     1.000 |  0.333 | 0.500 |       3 |
| first-fraction               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| decay-weighted               |     0 |     1.000 |  0.917 | 0.957 |      12 |
| decay-weighted               |     1 |     0.600 |  1.000 | 0.750 |       3 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.750 | 0.857 |      12 |
| first-3-pages                |     1 |     0.250 |  0.333 | 0.286 |       3 |
| first-3-pages                |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-5-pages                |     0 |     1.000 |  0.750 | 0.857 |      12 |
| first-5-pages                |     1 |     0.250 |  0.333 | 0.286 |       3 |
| first-5-pages                |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-10-pages               |     0 |     1.000 |  0.750 | 0.857 |      12 |
| first-10-pages               |     1 |     0.250 |  0.333 | 0.286 |       3 |
| first-10-pages               |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-15-pages               |     0 |     1.000 |  0.750 | 0.857 |      12 |
| first-15-pages               |     1 |     0.250 |  0.333 | 0.286 |       3 |
| first-15-pages               |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.750 | 0.857 |      12 |
| first-10-pages-density       |     1 |     0.250 |  0.333 | 0.286 |       3 |
| first-10-pages-density       |     2 |     0.333 |  1.000 | 0.500 |       1 |
| (count or density) and early |     0 |     1.000 |  0.750 | 0.857 |      12 |
| (count or density) and early |     1 |     0.250 |  0.333 | 0.286 |       3 |
| (count or density) and early |     2 |     0.333 |  1.000 | 0.500 |       1 |
| density and early            |     0 |     1.000 |  0.750 | 0.857 |      12 |
| density and early            |     1 |     0.250 |  0.333 | 0.286 |       3 |
| density and early            |     2 |     0.333 |  1.000 | 0.500 |       1 |

### `CCLW.executive.9192.1221`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.933 | 0.966 |      15 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant      |     2 |     0.500 |  1.000 | 0.667 |       1 |
| mention-count                |     0 |     0.938 |  1.000 | 0.968 |      15 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     1.000 |  0.933 | 0.966 |      15 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     0.938 |  1.000 | 0.968 |      15 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.938 |  1.000 | 0.968 |      15 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.933 | 0.966 |      15 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.933 | 0.966 |      15 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-fraction               |     0 |     0.938 |  1.000 | 0.968 |      15 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.938 |  1.000 | 0.968 |      15 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.933 | 0.966 |      15 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-5-pages                |     0 |     1.000 |  0.933 | 0.966 |      15 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.933 | 0.966 |      15 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.933 | 0.966 |      15 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.933 | 0.966 |      15 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       1 |
| (count or density) and early |     0 |     1.000 |  0.933 | 0.966 |      15 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     1.000 |  0.933 | 0.966 |      15 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `CCLW.legislative.10843.6116`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.692 | 0.818 |      13 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.286 |  1.000 | 0.444 |       2 |
| mention-count                |     0 |     1.000 |  0.923 | 0.960 |      13 |
| mention-count                |     1 |     0.250 |  1.000 | 0.400 |       1 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     1.000 |  0.692 | 0.818 |      13 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.923 | 0.960 |      13 |
| max-mentions-per-page        |     1 |     0.333 |  1.000 | 0.500 |       1 |
| max-mentions-per-page        |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-section-density          |     0 |     0.867 |  1.000 | 0.929 |      13 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  0.692 | 0.818 |      13 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     2 |     0.667 |  1.000 | 0.800 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.692 | 0.818 |      13 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-fraction               |     0 |     1.000 |  1.000 | 1.000 |      13 |
| first-fraction               |     1 |     0.333 |  1.000 | 0.500 |       1 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| decay-weighted               |     0 |     1.000 |  0.923 | 0.960 |      13 |
| decay-weighted               |     1 |     0.250 |  1.000 | 0.400 |       1 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-5-pages                |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages               |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-15-pages               |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       2 |
| (count or density) and early |     0 |     1.000 |  0.692 | 0.818 |      13 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     2 |     0.667 |  1.000 | 0.800 |       2 |
| density and early            |     0 |     1.000 |  0.692 | 0.818 |      13 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     2 |     0.667 |  1.000 | 0.800 |       2 |

### `CCLW.legislative.rtl_3.rtl_5`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.750 | 0.857 |      12 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.143 |  1.000 | 0.250 |       1 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      12 |
| mention-count                |     1 |     0.750 |  1.000 | 0.857 |       3 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     1.000 |  1.000 | 1.000 |      12 |
| mention-density              |     1 |     0.750 |  1.000 | 0.857 |       3 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  1.000 | 1.000 |      12 |
| max-mentions-per-page        |     1 |     0.750 |  1.000 | 0.857 |       3 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     1.000 |  0.833 | 0.909 |      12 |
| max-section-density          |     1 |     0.400 |  0.667 | 0.500 |       3 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.917 | 0.957 |      12 |
| earliest-mention             |     1 |     0.600 |  1.000 | 0.750 |       3 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.917 | 0.957 |      12 |
| earliest-mention-page        |     1 |     0.667 |  0.667 | 0.667 |       3 |
| earliest-mention-page        |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-fraction               |     0 |     0.857 |  1.000 | 0.923 |      12 |
| first-fraction               |     1 |     0.500 |  0.333 | 0.400 |       3 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     1.000 |  1.000 | 1.000 |      12 |
| decay-weighted               |     1 |     0.750 |  1.000 | 0.857 |       3 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.750 | 0.857 |      12 |
| first-3-pages                |     1 |     0.400 |  0.667 | 0.500 |       3 |
| first-3-pages                |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-5-pages                |     0 |     1.000 |  0.750 | 0.857 |      12 |
| first-5-pages                |     1 |     0.400 |  0.667 | 0.500 |       3 |
| first-5-pages                |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages               |     0 |     1.000 |  0.750 | 0.857 |      12 |
| first-10-pages               |     1 |     0.429 |  1.000 | 0.600 |       3 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.750 | 0.857 |      12 |
| first-15-pages               |     1 |     0.500 |  1.000 | 0.667 |       3 |
| first-15-pages               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.750 | 0.857 |      12 |
| first-10-pages-density       |     1 |     0.429 |  1.000 | 0.600 |       3 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     0 |     1.000 |  1.000 | 1.000 |      12 |
| (count or density) and early |     1 |     0.750 |  1.000 | 0.857 |       3 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     1.000 |  1.000 | 1.000 |      12 |
| density and early            |     1 |     0.750 |  1.000 | 0.857 |       3 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `CPR.document.i00003375.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.600 | 0.750 |      10 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       6 |
| any-mention-is-relevant      |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      10 |
| mention-count                |     1 |     1.000 |  1.000 | 1.000 |       6 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     0 |     1.000 |  1.000 | 1.000 |      10 |
| mention-density              |     1 |     1.000 |  1.000 | 1.000 |       6 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     0 |     1.000 |  0.900 | 0.947 |      10 |
| max-mentions-per-page        |     1 |     0.857 |  1.000 | 0.923 |       6 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     0 |     0.875 |  0.700 | 0.778 |      10 |
| max-section-density          |     1 |     0.500 |  0.500 | 0.500 |       6 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     0 |     1.000 |  0.600 | 0.750 |      10 |
| earliest-mention             |     1 |     0.600 |  1.000 | 0.750 |       6 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     0 |     1.000 |  0.600 | 0.750 |      10 |
| earliest-mention-page        |     1 |     0.600 |  1.000 | 0.750 |       6 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     0 |     0.750 |  0.900 | 0.818 |      10 |
| first-fraction               |     1 |     0.750 |  0.500 | 0.600 |       6 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     0 |     1.000 |  1.000 | 1.000 |      10 |
| decay-weighted               |     1 |     1.000 |  1.000 | 1.000 |       6 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     0 |     1.000 |  0.600 | 0.750 |      10 |
| first-3-pages                |     1 |     0.600 |  1.000 | 0.750 |       6 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     0 |     1.000 |  0.600 | 0.750 |      10 |
| first-5-pages                |     1 |     0.556 |  0.833 | 0.667 |       6 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     0 |     1.000 |  0.600 | 0.750 |      10 |
| first-10-pages               |     1 |     0.556 |  0.833 | 0.667 |       6 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     0 |     1.000 |  0.600 | 0.750 |      10 |
| first-15-pages               |     1 |     0.500 |  0.667 | 0.571 |       6 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     0 |     1.000 |  0.600 | 0.750 |      10 |
| first-10-pages-density       |     1 |     0.556 |  0.833 | 0.667 |       6 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     0 |     1.000 |  1.000 | 1.000 |      10 |
| (count or density) and early |     1 |     1.000 |  1.000 | 1.000 |       6 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     0 |     1.000 |  1.000 | 1.000 |      10 |
| density and early            |     1 |     1.000 |  1.000 | 1.000 |       6 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `CPR.document.i00004424.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.500 | 0.667 |       8 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       7 |
| any-mention-is-relevant      |     2 |     0.083 |  1.000 | 0.154 |       1 |
| mention-count                |     0 |     1.000 |  0.750 | 0.857 |       8 |
| mention-count                |     1 |     0.778 |  1.000 | 0.875 |       7 |
| mention-count                |     2 |     1.000 |  1.000 | 1.000 |       1 |
| mention-density              |     0 |     1.000 |  1.000 | 1.000 |       8 |
| mention-density              |     1 |     0.875 |  1.000 | 0.933 |       7 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.875 | 0.933 |       8 |
| max-mentions-per-page        |     1 |     0.750 |  0.429 | 0.545 |       7 |
| max-mentions-per-page        |     2 |     0.200 |  1.000 | 0.333 |       1 |
| max-section-density          |     0 |     1.000 |  0.625 | 0.769 |       8 |
| max-section-density          |     1 |     0.600 |  0.857 | 0.706 |       7 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.500 | 0.667 |       8 |
| earliest-mention             |     1 |     0.667 |  0.857 | 0.750 |       7 |
| earliest-mention             |     2 |     0.333 |  1.000 | 0.500 |       1 |
| earliest-mention-page        |     0 |     0.778 |  0.875 | 0.824 |       8 |
| earliest-mention-page        |     1 |     1.000 |  0.571 | 0.727 |       7 |
| earliest-mention-page        |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-fraction               |     0 |     1.000 |  0.625 | 0.769 |       8 |
| first-fraction               |     1 |     0.333 |  0.143 | 0.200 |       7 |
| first-fraction               |     2 |     0.125 |  1.000 | 0.222 |       1 |
| decay-weighted               |     0 |     1.000 |  0.750 | 0.857 |       8 |
| decay-weighted               |     1 |     0.750 |  0.857 | 0.800 |       7 |
| decay-weighted               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-3-pages                |     0 |     1.000 |  0.500 | 0.667 |       8 |
| first-3-pages                |     1 |     0.667 |  0.857 | 0.750 |       7 |
| first-3-pages                |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-5-pages                |     0 |     1.000 |  0.500 | 0.667 |       8 |
| first-5-pages                |     1 |     0.600 |  0.857 | 0.706 |       7 |
| first-5-pages                |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages               |     0 |     1.000 |  0.500 | 0.667 |       8 |
| first-10-pages               |     1 |     0.600 |  0.857 | 0.706 |       7 |
| first-10-pages               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-15-pages               |     0 |     1.000 |  0.500 | 0.667 |       8 |
| first-15-pages               |     1 |     0.583 |  1.000 | 0.737 |       7 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.500 | 0.667 |       8 |
| first-10-pages-density       |     1 |     0.600 |  0.857 | 0.706 |       7 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       1 |
| (count or density) and early |     0 |     0.778 |  0.875 | 0.824 |       8 |
| (count or density) and early |     1 |     0.833 |  0.714 | 0.769 |       7 |
| (count or density) and early |     2 |     1.000 |  1.000 | 1.000 |       1 |
| density and early            |     0 |     0.800 |  1.000 | 0.889 |       8 |
| density and early            |     1 |     0.833 |  0.714 | 0.769 |       7 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `GCF.document.FP051_16090.21078`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.800 | 0.889 |      10 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant      |     2 |     0.250 |  1.000 | 0.400 |       2 |
| mention-count                |     0 |     0.889 |  0.800 | 0.842 |      10 |
| mention-count                |     1 |     0.429 |  0.750 | 0.545 |       4 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     0.900 |  0.900 | 0.900 |      10 |
| mention-density              |     1 |     0.400 |  0.500 | 0.444 |       4 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       2 |
| max-mentions-per-page        |     0 |     0.889 |  0.800 | 0.842 |      10 |
| max-mentions-per-page        |     1 |     0.333 |  0.500 | 0.400 |       4 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       2 |
| max-section-density          |     0 |     1.000 |  0.800 | 0.889 |      10 |
| max-section-density          |     1 |     0.571 |  1.000 | 0.727 |       4 |
| max-section-density          |     2 |     1.000 |  0.500 | 0.667 |       2 |
| earliest-mention             |     0 |     0.889 |  0.800 | 0.842 |      10 |
| earliest-mention             |     1 |     0.429 |  0.750 | 0.545 |       4 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention-page        |     0 |     0.889 |  0.800 | 0.842 |      10 |
| earliest-mention-page        |     1 |     0.500 |  0.500 | 0.500 |       4 |
| earliest-mention-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-fraction               |     0 |     0.900 |  0.900 | 0.900 |      10 |
| first-fraction               |     1 |     0.600 |  0.750 | 0.667 |       4 |
| first-fraction               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| decay-weighted               |     0 |     0.800 |  0.800 | 0.800 |      10 |
| decay-weighted               |     1 |     0.333 |  0.500 | 0.400 |       4 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.800 | 0.889 |      10 |
| first-3-pages                |     1 |     0.600 |  0.750 | 0.667 |       4 |
| first-3-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-5-pages                |     0 |     1.000 |  0.800 | 0.889 |      10 |
| first-5-pages                |     1 |     0.600 |  0.750 | 0.667 |       4 |
| first-5-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages               |     0 |     1.000 |  0.800 | 0.889 |      10 |
| first-10-pages               |     1 |     0.600 |  0.750 | 0.667 |       4 |
| first-10-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-15-pages               |     0 |     1.000 |  0.800 | 0.889 |      10 |
| first-15-pages               |     1 |     0.750 |  0.750 | 0.750 |       4 |
| first-15-pages               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.800 | 0.889 |      10 |
| first-10-pages-density       |     1 |     0.600 |  0.750 | 0.667 |       4 |
| first-10-pages-density       |     2 |     0.667 |  1.000 | 0.800 |       2 |
| (count or density) and early |     0 |     0.800 |  0.800 | 0.800 |      10 |
| (count or density) and early |     1 |     0.200 |  0.250 | 0.222 |       4 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       2 |
| density and early            |     0 |     0.818 |  0.900 | 0.857 |      10 |
| density and early            |     1 |     0.250 |  0.250 | 0.250 |       4 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       2 |

### `GCF.document.FP199_23210.17324`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.818 | 0.900 |      11 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant      |     2 |     0.143 |  1.000 | 0.250 |       1 |
| mention-count                |     0 |     0.917 |  1.000 | 0.957 |      11 |
| mention-count                |     1 |     0.667 |  0.500 | 0.571 |       4 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     0.917 |  1.000 | 0.957 |      11 |
| mention-density              |     1 |     1.000 |  0.500 | 0.667 |       4 |
| mention-density              |     2 |     0.500 |  1.000 | 0.667 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.818 | 0.900 |      11 |
| max-mentions-per-page        |     1 |     0.500 |  0.750 | 0.600 |       4 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     1.000 |  0.909 | 0.952 |      11 |
| max-section-density          |     1 |     0.500 |  0.500 | 0.500 |       4 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.818 | 0.900 |      11 |
| earliest-mention             |     1 |     0.667 |  1.000 | 0.800 |       4 |
| earliest-mention             |     2 |     1.000 |  1.000 | 1.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.818 | 0.900 |      11 |
| earliest-mention-page        |     1 |     0.500 |  0.500 | 0.500 |       4 |
| earliest-mention-page        |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-fraction               |     0 |     0.833 |  0.909 | 0.870 |      11 |
| first-fraction               |     1 |     0.500 |  0.250 | 0.333 |       4 |
| first-fraction               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| decay-weighted               |     0 |     0.846 |  1.000 | 0.917 |      11 |
| decay-weighted               |     1 |     0.667 |  0.500 | 0.571 |       4 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.818 | 0.900 |      11 |
| first-3-pages                |     1 |     0.500 |  0.500 | 0.500 |       4 |
| first-3-pages                |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-5-pages                |     0 |     1.000 |  0.818 | 0.900 |      11 |
| first-5-pages                |     1 |     0.500 |  0.500 | 0.500 |       4 |
| first-5-pages                |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-10-pages               |     0 |     1.000 |  0.818 | 0.900 |      11 |
| first-10-pages               |     1 |     0.500 |  0.500 | 0.500 |       4 |
| first-10-pages               |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-15-pages               |     0 |     1.000 |  0.818 | 0.900 |      11 |
| first-15-pages               |     1 |     0.500 |  0.500 | 0.500 |       4 |
| first-15-pages               |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.818 | 0.900 |      11 |
| first-10-pages-density       |     1 |     0.500 |  0.500 | 0.500 |       4 |
| first-10-pages-density       |     2 |     0.333 |  1.000 | 0.500 |       1 |
| (count or density) and early |     0 |     0.917 |  1.000 | 0.957 |      11 |
| (count or density) and early |     1 |     1.000 |  0.500 | 0.667 |       4 |
| (count or density) and early |     2 |     0.500 |  1.000 | 0.667 |       1 |
| density and early            |     0 |     0.917 |  1.000 | 0.957 |      11 |
| density and early            |     1 |     1.000 |  0.500 | 0.667 |       4 |
| density and early            |     2 |     0.500 |  1.000 | 0.667 |       1 |

### `GCF.document.FP215_24850.16116`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.500 | 0.667 |      10 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant      |     2 |     0.182 |  1.000 | 0.308 |       2 |
| mention-count                |     0 |     1.000 |  0.900 | 0.947 |      10 |
| mention-count                |     1 |     0.750 |  0.750 | 0.750 |       4 |
| mention-count                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| mention-density              |     0 |     1.000 |  0.900 | 0.947 |      10 |
| mention-density              |     1 |     0.750 |  0.750 | 0.750 |       4 |
| mention-density              |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  1.000 | 1.000 |      10 |
| max-mentions-per-page        |     1 |     1.000 |  0.750 | 0.857 |       4 |
| max-mentions-per-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-section-density          |     0 |     0.800 |  0.800 | 0.800 |      10 |
| max-section-density          |     1 |     0.400 |  0.500 | 0.444 |       4 |
| max-section-density          |     2 |     1.000 |  0.500 | 0.667 |       2 |
| earliest-mention             |     0 |     1.000 |  0.600 | 0.750 |      10 |
| earliest-mention             |     1 |     0.500 |  0.750 | 0.600 |       4 |
| earliest-mention             |     2 |     0.500 |  1.000 | 0.667 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.700 | 0.824 |      10 |
| earliest-mention-page        |     1 |     0.750 |  0.750 | 0.750 |       4 |
| earliest-mention-page        |     2 |     0.400 |  1.000 | 0.571 |       2 |
| first-fraction               |     0 |     0.900 |  0.900 | 0.900 |      10 |
| first-fraction               |     1 |     0.500 |  0.250 | 0.333 |       4 |
| first-fraction               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| decay-weighted               |     0 |     1.000 |  0.900 | 0.947 |      10 |
| decay-weighted               |     1 |     0.750 |  0.750 | 0.750 |       4 |
| decay-weighted               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-3-pages                |     0 |     1.000 |  0.500 | 0.667 |      10 |
| first-3-pages                |     1 |     0.500 |  0.750 | 0.600 |       4 |
| first-3-pages                |     2 |     0.400 |  1.000 | 0.571 |       2 |
| first-5-pages                |     0 |     1.000 |  0.500 | 0.667 |      10 |
| first-5-pages                |     1 |     0.375 |  0.750 | 0.500 |       4 |
| first-5-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages               |     0 |     1.000 |  0.500 | 0.667 |      10 |
| first-10-pages               |     1 |     0.375 |  0.750 | 0.500 |       4 |
| first-10-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-15-pages               |     0 |     1.000 |  0.500 | 0.667 |      10 |
| first-15-pages               |     1 |     0.375 |  0.750 | 0.500 |       4 |
| first-15-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.500 | 0.667 |      10 |
| first-10-pages-density       |     1 |     0.375 |  0.750 | 0.500 |       4 |
| first-10-pages-density       |     2 |     0.667 |  1.000 | 0.800 |       2 |
| (count or density) and early |     0 |     1.000 |  0.900 | 0.947 |      10 |
| (count or density) and early |     1 |     0.750 |  0.750 | 0.750 |       4 |
| (count or density) and early |     2 |     0.667 |  1.000 | 0.800 |       2 |
| density and early            |     0 |     1.000 |  0.900 | 0.947 |      10 |
| density and early            |     1 |     0.750 |  0.750 | 0.750 |       4 |
| density and early            |     2 |     0.667 |  1.000 | 0.800 |       2 |

### `GCF.document.FP228_27310.17090`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.444 | 0.615 |       9 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       5 |
| any-mention-is-relevant      |     2 |     0.167 |  1.000 | 0.286 |       2 |
| mention-count                |     0 |     0.875 |  0.778 | 0.824 |       9 |
| mention-count                |     1 |     0.571 |  0.800 | 0.667 |       5 |
| mention-count                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| mention-density              |     0 |     0.900 |  1.000 | 0.947 |       9 |
| mention-density              |     1 |     1.000 |  0.600 | 0.750 |       5 |
| mention-density              |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.667 | 0.800 |       9 |
| max-mentions-per-page        |     1 |     0.571 |  0.800 | 0.667 |       5 |
| max-mentions-per-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-section-density          |     0 |     0.889 |  0.889 | 0.889 |       9 |
| max-section-density          |     1 |     0.800 |  0.800 | 0.800 |       5 |
| max-section-density          |     2 |     1.000 |  1.000 | 1.000 |       2 |
| earliest-mention             |     0 |     0.833 |  0.556 | 0.667 |       9 |
| earliest-mention             |     1 |     0.375 |  0.600 | 0.462 |       5 |
| earliest-mention             |     2 |     0.500 |  0.500 | 0.500 |       2 |
| earliest-mention-page        |     0 |     0.833 |  0.556 | 0.667 |       9 |
| earliest-mention-page        |     1 |     0.429 |  0.600 | 0.500 |       5 |
| earliest-mention-page        |     2 |     0.333 |  0.500 | 0.400 |       2 |
| first-fraction               |     0 |     0.875 |  0.778 | 0.824 |       9 |
| first-fraction               |     1 |     0.667 |  0.800 | 0.727 |       5 |
| first-fraction               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| decay-weighted               |     0 |     0.900 |  1.000 | 0.947 |       9 |
| decay-weighted               |     1 |     1.000 |  0.800 | 0.889 |       5 |
| decay-weighted               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.444 | 0.615 |       9 |
| first-3-pages                |     1 |     0.444 |  0.800 | 0.571 |       5 |
| first-3-pages                |     2 |     0.333 |  0.500 | 0.400 |       2 |
| first-5-pages                |     0 |     1.000 |  0.444 | 0.615 |       9 |
| first-5-pages                |     1 |     0.375 |  0.600 | 0.462 |       5 |
| first-5-pages                |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  0.444 | 0.615 |       9 |
| first-10-pages               |     1 |     0.444 |  0.800 | 0.571 |       5 |
| first-10-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-15-pages               |     0 |     1.000 |  0.444 | 0.615 |       9 |
| first-15-pages               |     1 |     0.375 |  0.600 | 0.462 |       5 |
| first-15-pages               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.444 | 0.615 |       9 |
| first-10-pages-density       |     1 |     0.444 |  0.800 | 0.571 |       5 |
| first-10-pages-density       |     2 |     0.667 |  1.000 | 0.800 |       2 |
| (count or density) and early |     0 |     0.875 |  0.778 | 0.824 |       9 |
| (count or density) and early |     1 |     0.500 |  0.600 | 0.545 |       5 |
| (count or density) and early |     2 |     0.500 |  0.500 | 0.500 |       2 |
| density and early            |     0 |     0.900 |  1.000 | 0.947 |       9 |
| density and early            |     1 |     0.750 |  0.600 | 0.667 |       5 |
| density and early            |     2 |     0.500 |  0.500 | 0.500 |       2 |

### `GEF.document.11136.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.700 | 0.824 |      10 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant      |     2 |     0.222 |  1.000 | 0.364 |       2 |
| mention-count                |     0 |     1.000 |  0.900 | 0.947 |      10 |
| mention-count                |     1 |     0.571 |  1.000 | 0.727 |       4 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     1.000 |  0.900 | 0.947 |      10 |
| mention-density              |     1 |     0.600 |  0.750 | 0.667 |       4 |
| mention-density              |     2 |     0.500 |  0.500 | 0.500 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.900 | 0.947 |      10 |
| max-mentions-per-page        |     1 |     0.600 |  0.750 | 0.667 |       4 |
| max-mentions-per-page        |     2 |     0.500 |  0.500 | 0.500 |       2 |
| max-section-density          |     0 |     1.000 |  0.900 | 0.947 |      10 |
| max-section-density          |     1 |     0.500 |  0.750 | 0.600 |       4 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  0.700 | 0.824 |      10 |
| earliest-mention             |     1 |     0.429 |  0.750 | 0.545 |       4 |
| earliest-mention             |     2 |     0.500 |  0.500 | 0.500 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.900 | 0.947 |      10 |
| earliest-mention-page        |     1 |     0.750 |  0.750 | 0.750 |       4 |
| earliest-mention-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-fraction               |     0 |     1.000 |  0.900 | 0.947 |      10 |
| first-fraction               |     1 |     0.667 |  0.500 | 0.571 |       4 |
| first-fraction               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| decay-weighted               |     0 |     1.000 |  0.900 | 0.947 |      10 |
| decay-weighted               |     1 |     0.500 |  0.750 | 0.600 |       4 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.700 | 0.824 |      10 |
| first-3-pages                |     1 |     0.500 |  0.750 | 0.600 |       4 |
| first-3-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-5-pages                |     0 |     1.000 |  0.700 | 0.824 |      10 |
| first-5-pages                |     1 |     0.500 |  0.750 | 0.600 |       4 |
| first-5-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages               |     0 |     1.000 |  0.700 | 0.824 |      10 |
| first-10-pages               |     1 |     0.500 |  0.750 | 0.600 |       4 |
| first-10-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-15-pages               |     0 |     1.000 |  0.700 | 0.824 |      10 |
| first-15-pages               |     1 |     0.500 |  0.750 | 0.600 |       4 |
| first-15-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.700 | 0.824 |      10 |
| first-10-pages-density       |     1 |     0.400 |  0.500 | 0.444 |       4 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       2 |
| (count or density) and early |     0 |     1.000 |  0.900 | 0.947 |      10 |
| (count or density) and early |     1 |     0.600 |  0.750 | 0.667 |       4 |
| (count or density) and early |     2 |     0.500 |  0.500 | 0.500 |       2 |
| density and early            |     0 |     1.000 |  0.900 | 0.947 |      10 |
| density and early            |     1 |     0.600 |  0.750 | 0.667 |       4 |
| density and early            |     2 |     0.500 |  0.500 | 0.500 |       2 |

### `GEF.document.11143.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.700 | 0.824 |      10 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant      |     2 |     0.222 |  1.000 | 0.364 |       2 |
| mention-count                |     0 |     1.000 |  0.900 | 0.947 |      10 |
| mention-count                |     1 |     0.500 |  0.750 | 0.600 |       4 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     1.000 |  0.900 | 0.947 |      10 |
| mention-density              |     1 |     0.667 |  0.500 | 0.571 |       4 |
| mention-density              |     2 |     0.500 |  1.000 | 0.667 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.900 | 0.947 |      10 |
| max-mentions-per-page        |     1 |     0.667 |  0.500 | 0.571 |       4 |
| max-mentions-per-page        |     2 |     0.500 |  1.000 | 0.667 |       2 |
| max-section-density          |     0 |     1.000 |  0.800 | 0.889 |      10 |
| max-section-density          |     1 |     0.500 |  1.000 | 0.667 |       4 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  0.800 | 0.889 |      10 |
| earliest-mention             |     1 |     0.429 |  0.750 | 0.545 |       4 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.800 | 0.889 |      10 |
| earliest-mention-page        |     1 |     0.500 |  0.500 | 0.500 |       4 |
| earliest-mention-page        |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-fraction               |     0 |     1.000 |  0.900 | 0.947 |      10 |
| first-fraction               |     1 |     0.667 |  0.500 | 0.571 |       4 |
| first-fraction               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| decay-weighted               |     0 |     1.000 |  0.900 | 0.947 |      10 |
| decay-weighted               |     1 |     0.750 |  0.750 | 0.750 |       4 |
| decay-weighted               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-3-pages                |     0 |     1.000 |  0.700 | 0.824 |      10 |
| first-3-pages                |     1 |     0.400 |  0.500 | 0.444 |       4 |
| first-3-pages                |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-5-pages                |     0 |     1.000 |  0.700 | 0.824 |      10 |
| first-5-pages                |     1 |     0.400 |  0.500 | 0.444 |       4 |
| first-5-pages                |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  0.700 | 0.824 |      10 |
| first-10-pages               |     1 |     0.400 |  0.500 | 0.444 |       4 |
| first-10-pages               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-15-pages               |     0 |     1.000 |  0.700 | 0.824 |      10 |
| first-15-pages               |     1 |     0.400 |  0.500 | 0.444 |       4 |
| first-15-pages               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.700 | 0.824 |      10 |
| first-10-pages-density       |     1 |     0.400 |  0.500 | 0.444 |       4 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       2 |
| (count or density) and early |     0 |     1.000 |  0.900 | 0.947 |      10 |
| (count or density) and early |     1 |     0.667 |  0.500 | 0.571 |       4 |
| (count or density) and early |     2 |     0.500 |  1.000 | 0.667 |       2 |
| density and early            |     0 |     1.000 |  0.900 | 0.947 |      10 |
| density and early            |     1 |     0.667 |  0.500 | 0.571 |       4 |
| density and early            |     2 |     0.500 |  1.000 | 0.667 |       2 |

### `OEP.document.i00000091.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.462 | 0.632 |      13 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.200 |  1.000 | 0.333 |       2 |
| mention-count                |     0 |     1.000 |  0.769 | 0.870 |      13 |
| mention-count                |     1 |     0.200 |  1.000 | 0.333 |       1 |
| mention-count                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| mention-density              |     0 |     1.000 |  0.846 | 0.917 |      13 |
| mention-density              |     1 |     0.250 |  1.000 | 0.400 |       1 |
| mention-density              |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.692 | 0.818 |      13 |
| max-mentions-per-page        |     1 |     0.167 |  1.000 | 0.286 |       1 |
| max-mentions-per-page        |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-section-density          |     0 |     1.000 |  0.846 | 0.917 |      13 |
| max-section-density          |     1 |     0.250 |  1.000 | 0.400 |       1 |
| max-section-density          |     2 |     1.000 |  0.500 | 0.667 |       2 |
| earliest-mention             |     0 |     0.857 |  0.462 | 0.600 |      13 |
| earliest-mention             |     1 |     0.143 |  1.000 | 0.250 |       1 |
| earliest-mention             |     2 |     0.500 |  0.500 | 0.500 |       2 |
| earliest-mention-page        |     0 |     0.857 |  0.462 | 0.600 |      13 |
| earliest-mention-page        |     1 |     0.143 |  1.000 | 0.250 |       1 |
| earliest-mention-page        |     2 |     0.500 |  0.500 | 0.500 |       2 |
| first-fraction               |     0 |     0.917 |  0.846 | 0.880 |      13 |
| first-fraction               |     1 |     0.333 |  1.000 | 0.500 |       1 |
| first-fraction               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| decay-weighted               |     0 |     0.909 |  0.769 | 0.833 |      13 |
| decay-weighted               |     1 |     0.250 |  1.000 | 0.400 |       1 |
| decay-weighted               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-3-pages                |     0 |     1.000 |  0.462 | 0.632 |      13 |
| first-3-pages                |     1 |     0.125 |  1.000 | 0.222 |       1 |
| first-3-pages                |     2 |     0.500 |  0.500 | 0.500 |       2 |
| first-5-pages                |     0 |     1.000 |  0.462 | 0.632 |      13 |
| first-5-pages                |     1 |     0.111 |  1.000 | 0.200 |       1 |
| first-5-pages                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  0.462 | 0.632 |      13 |
| first-10-pages               |     1 |     0.111 |  1.000 | 0.200 |       1 |
| first-10-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-15-pages               |     0 |     1.000 |  0.462 | 0.632 |      13 |
| first-15-pages               |     1 |     0.111 |  1.000 | 0.200 |       1 |
| first-15-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.462 | 0.632 |      13 |
| first-10-pages-density       |     1 |     0.111 |  1.000 | 0.200 |       1 |
| first-10-pages-density       |     2 |     1.000 |  0.500 | 0.667 |       2 |
| (count or density) and early |     0 |     0.909 |  0.769 | 0.833 |      13 |
| (count or density) and early |     1 |     0.250 |  1.000 | 0.400 |       1 |
| (count or density) and early |     2 |     1.000 |  0.500 | 0.667 |       2 |
| density and early            |     0 |     0.917 |  0.846 | 0.880 |      13 |
| density and early            |     1 |     0.333 |  1.000 | 0.500 |       1 |
| density and early            |     2 |     1.000 |  0.500 | 0.667 |       2 |

### `Sabin.document.10287.10288`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.786 | 0.880 |      14 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.200 |  1.000 | 0.333 |       1 |
| mention-count                |     0 |     1.000 |  0.929 | 0.963 |      14 |
| mention-count                |     1 |     0.500 |  1.000 | 0.667 |       1 |
| mention-count                |     2 |     1.000 |  1.000 | 1.000 |       1 |
| mention-density              |     0 |     1.000 |  0.857 | 0.923 |      14 |
| mention-density              |     1 |     0.333 |  1.000 | 0.500 |       1 |
| mention-density              |     2 |     1.000 |  1.000 | 1.000 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.786 | 0.880 |      14 |
| max-mentions-per-page        |     1 |     0.250 |  1.000 | 0.400 |       1 |
| max-mentions-per-page        |     2 |     1.000 |  1.000 | 1.000 |       1 |
| max-section-density          |     0 |     0.933 |  1.000 | 0.966 |      14 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.857 | 0.923 |      14 |
| earliest-mention             |     1 |     0.250 |  1.000 | 0.400 |       1 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.857 | 0.923 |      14 |
| earliest-mention-page        |     1 |     0.250 |  1.000 | 0.400 |       1 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     0 |     0.933 |  1.000 | 0.966 |      14 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| decay-weighted               |     0 |     0.933 |  1.000 | 0.966 |      14 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.786 | 0.880 |      14 |
| first-3-pages                |     1 |     0.200 |  1.000 | 0.333 |       1 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     0 |     1.000 |  0.786 | 0.880 |      14 |
| first-5-pages                |     1 |     0.200 |  1.000 | 0.333 |       1 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.786 | 0.880 |      14 |
| first-10-pages               |     1 |     0.250 |  1.000 | 0.400 |       1 |
| first-10-pages               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.786 | 0.880 |      14 |
| first-15-pages               |     1 |     0.250 |  1.000 | 0.400 |       1 |
| first-15-pages               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.786 | 0.880 |      14 |
| first-10-pages-density       |     1 |     0.250 |  1.000 | 0.400 |       1 |
| first-10-pages-density       |     2 |     1.000 |  1.000 | 1.000 |       1 |
| (count or density) and early |     0 |     1.000 |  0.929 | 0.963 |      14 |
| (count or density) and early |     1 |     0.333 |  1.000 | 0.500 |       1 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     1.000 |  0.929 | 0.963 |      14 |
| density and early            |     1 |     0.333 |  1.000 | 0.500 |       1 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `Sabin.document.109700.130909`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.667 | 0.800 |      12 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.125 |  1.000 | 0.222 |       1 |
| mention-count                |     0 |     1.000 |  0.917 | 0.957 |      12 |
| mention-count                |     1 |     0.600 |  1.000 | 0.750 |       3 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     1.000 |  0.917 | 0.957 |      12 |
| mention-density              |     1 |     0.750 |  1.000 | 0.857 |       3 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     0.909 |  0.833 | 0.870 |      12 |
| max-mentions-per-page        |     1 |     0.500 |  0.667 | 0.571 |       3 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.909 |  0.833 | 0.870 |      12 |
| max-section-density          |     1 |     0.400 |  0.667 | 0.500 |       3 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.833 | 0.909 |      12 |
| earliest-mention             |     1 |     0.500 |  1.000 | 0.667 |       3 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.917 | 0.957 |      12 |
| earliest-mention-page        |     1 |     0.667 |  0.667 | 0.667 |       3 |
| earliest-mention-page        |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-fraction               |     0 |     1.000 |  0.917 | 0.957 |      12 |
| first-fraction               |     1 |     0.750 |  1.000 | 0.857 |       3 |
| first-fraction               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| decay-weighted               |     0 |     1.000 |  0.917 | 0.957 |      12 |
| decay-weighted               |     1 |     0.600 |  1.000 | 0.750 |       3 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.667 | 0.800 |      12 |
| first-3-pages                |     1 |     0.333 |  0.667 | 0.444 |       3 |
| first-3-pages                |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-5-pages                |     0 |     1.000 |  0.667 | 0.800 |      12 |
| first-5-pages                |     1 |     0.429 |  1.000 | 0.600 |       3 |
| first-5-pages                |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.667 | 0.800 |      12 |
| first-10-pages               |     1 |     0.375 |  1.000 | 0.545 |       3 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.667 | 0.800 |      12 |
| first-15-pages               |     1 |     0.375 |  1.000 | 0.545 |       3 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.667 | 0.800 |      12 |
| first-10-pages-density       |     1 |     0.333 |  0.667 | 0.444 |       3 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       1 |
| (count or density) and early |     0 |     1.000 |  0.917 | 0.957 |      12 |
| (count or density) and early |     1 |     0.600 |  1.000 | 0.750 |       3 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     1.000 |  0.917 | 0.957 |      12 |
| density and early            |     1 |     0.600 |  1.000 | 0.750 |       3 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `Sabin.document.126888.126889`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  1.000 | 1.000 |      13 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.667 |  1.000 | 0.800 |       2 |
| mention-count                |     0 |     0.929 |  1.000 | 0.963 |      13 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     1.000 |  1.000 | 1.000 |      13 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-mentions-per-page        |     0 |     0.929 |  1.000 | 0.963 |      13 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       2 |
| max-section-density          |     0 |     1.000 |  1.000 | 1.000 |      13 |
| max-section-density          |     1 |     0.333 |  1.000 | 0.500 |       1 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  1.000 | 1.000 |      13 |
| earliest-mention             |     1 |     0.333 |  1.000 | 0.500 |       1 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention-page        |     0 |     1.000 |  1.000 | 1.000 |      13 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-fraction               |     0 |     0.867 |  1.000 | 0.929 |      13 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| decay-weighted               |     0 |     0.867 |  1.000 | 0.929 |      13 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  1.000 | 1.000 |      13 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-5-pages                |     0 |     1.000 |  1.000 | 1.000 |      13 |
| first-5-pages                |     1 |     1.000 |  1.000 | 1.000 |       1 |
| first-5-pages                |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-10-pages               |     0 |     1.000 |  1.000 | 1.000 |      13 |
| first-10-pages               |     1 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-15-pages               |     0 |     1.000 |  1.000 | 1.000 |      13 |
| first-15-pages               |     1 |     0.333 |  1.000 | 0.500 |       1 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-10-pages-density       |     0 |     1.000 |  1.000 | 1.000 |      13 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     2 |     0.667 |  1.000 | 0.800 |       2 |
| (count or density) and early |     0 |     1.000 |  1.000 | 1.000 |      13 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     2 |     0.667 |  1.000 | 0.800 |       2 |
| density and early            |     0 |     1.000 |  1.000 | 1.000 |      13 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     2 |     0.667 |  1.000 | 0.800 |       2 |

### `Sabin.document.12885.14299`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.833 | 0.909 |      12 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.167 |  1.000 | 0.286 |       1 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      12 |
| mention-count                |     1 |     0.750 |  1.000 | 0.857 |       3 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     1.000 |  0.833 | 0.909 |      12 |
| mention-density              |     1 |     0.500 |  0.667 | 0.571 |       3 |
| mention-density              |     2 |     0.500 |  1.000 | 0.667 |       1 |
| max-mentions-per-page        |     0 |     0.923 |  1.000 | 0.960 |      12 |
| max-mentions-per-page        |     1 |     0.667 |  0.667 | 0.667 |       3 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.923 |  1.000 | 0.960 |      12 |
| max-section-density          |     1 |     0.667 |  0.667 | 0.667 |       3 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.833 | 0.909 |      12 |
| earliest-mention             |     1 |     0.500 |  1.000 | 0.667 |       3 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.833 | 0.909 |      12 |
| earliest-mention-page        |     1 |     0.500 |  0.667 | 0.571 |       3 |
| earliest-mention-page        |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-fraction               |     0 |     0.857 |  1.000 | 0.923 |      12 |
| first-fraction               |     1 |     0.500 |  0.333 | 0.400 |       3 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.923 |  1.000 | 0.960 |      12 |
| decay-weighted               |     1 |     0.667 |  0.667 | 0.667 |       3 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.833 | 0.909 |      12 |
| first-3-pages                |     1 |     0.500 |  0.667 | 0.571 |       3 |
| first-3-pages                |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-5-pages                |     0 |     1.000 |  0.833 | 0.909 |      12 |
| first-5-pages                |     1 |     0.600 |  1.000 | 0.750 |       3 |
| first-5-pages                |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.833 | 0.909 |      12 |
| first-10-pages               |     1 |     0.500 |  0.667 | 0.571 |       3 |
| first-10-pages               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-15-pages               |     0 |     1.000 |  0.833 | 0.909 |      12 |
| first-15-pages               |     1 |     0.400 |  0.667 | 0.500 |       3 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.833 | 0.909 |      12 |
| first-10-pages-density       |     1 |     0.500 |  0.667 | 0.571 |       3 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       1 |
| (count or density) and early |     0 |     1.000 |  0.833 | 0.909 |      12 |
| (count or density) and early |     1 |     0.500 |  0.667 | 0.571 |       3 |
| (count or density) and early |     2 |     0.500 |  1.000 | 0.667 |       1 |
| density and early            |     0 |     1.000 |  0.833 | 0.909 |      12 |
| density and early            |     1 |     0.500 |  0.667 | 0.571 |       3 |
| density and early            |     2 |     0.500 |  1.000 | 0.667 |       1 |

### `Sabin.document.14285.14286`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.938 | 0.968 |      16 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant      |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      16 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     0 |     1.000 |  0.938 | 0.968 |      16 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     0 |     1.000 |  1.000 | 1.000 |      16 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     0 |     1.000 |  1.000 | 1.000 |      16 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     0 |     1.000 |  0.938 | 0.968 |      16 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     0 |     1.000 |  0.938 | 0.968 |      16 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     0 |     1.000 |  1.000 | 1.000 |      16 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     0 |     1.000 |  1.000 | 1.000 |      16 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     0 |     1.000 |  0.938 | 0.968 |      16 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     0 |     1.000 |  0.938 | 0.968 |      16 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     0 |     1.000 |  0.938 | 0.968 |      16 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     0 |     1.000 |  0.938 | 0.968 |      16 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     0 |     1.000 |  0.938 | 0.968 |      16 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     0 |     1.000 |  0.938 | 0.968 |      16 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     0 |     1.000 |  0.938 | 0.968 |      16 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `Sabin.document.155.7947`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.231 | 0.375 |      13 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant      |     2 |     0.077 |  1.000 | 0.143 |       1 |
| mention-count                |     0 |     1.000 |  0.538 | 0.700 |      13 |
| mention-count                |     1 |     0.250 |  1.000 | 0.400 |       2 |
| mention-count                |     2 |     1.000 |  1.000 | 1.000 |       1 |
| mention-density              |     0 |     1.000 |  0.923 | 0.960 |      13 |
| mention-density              |     1 |     0.500 |  1.000 | 0.667 |       2 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.385 | 0.556 |      13 |
| max-mentions-per-page        |     1 |     0.182 |  1.000 | 0.308 |       2 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.812 |  1.000 | 0.897 |      13 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       2 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.538 | 0.700 |      13 |
| earliest-mention             |     1 |     0.250 |  1.000 | 0.400 |       2 |
| earliest-mention             |     2 |     1.000 |  1.000 | 1.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  1.000 | 1.000 |      13 |
| earliest-mention-page        |     1 |     0.667 |  1.000 | 0.800 |       2 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     0 |     1.000 |  0.692 | 0.818 |      13 |
| first-fraction               |     1 |     0.200 |  0.500 | 0.286 |       2 |
| first-fraction               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| decay-weighted               |     0 |     1.000 |  0.615 | 0.762 |      13 |
| decay-weighted               |     1 |     0.286 |  1.000 | 0.444 |       2 |
| decay-weighted               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.231 | 0.375 |      13 |
| first-3-pages                |     1 |     0.154 |  1.000 | 0.267 |       2 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     0 |     1.000 |  0.231 | 0.375 |      13 |
| first-5-pages                |     1 |     0.154 |  1.000 | 0.267 |       2 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.231 | 0.375 |      13 |
| first-10-pages               |     1 |     0.154 |  1.000 | 0.267 |       2 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.231 | 0.375 |      13 |
| first-15-pages               |     1 |     0.154 |  1.000 | 0.267 |       2 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.231 | 0.375 |      13 |
| first-10-pages-density       |     1 |     0.154 |  1.000 | 0.267 |       2 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     0 |     1.000 |  1.000 | 1.000 |      13 |
| (count or density) and early |     1 |     0.667 |  1.000 | 0.800 |       2 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     1.000 |  1.000 | 1.000 |      13 |
| density and early            |     1 |     0.667 |  1.000 | 0.800 |       2 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `Sabin.document.16314.67362`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.929 | 0.963 |      14 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.333 |  1.000 | 0.500 |       1 |
| mention-count                |     0 |     0.933 |  1.000 | 0.966 |      14 |
| mention-count                |     1 |     1.000 |  1.000 | 1.000 |       1 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     1.000 |  0.929 | 0.963 |      14 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     0.933 |  1.000 | 0.966 |      14 |
| max-mentions-per-page        |     1 |     1.000 |  1.000 | 1.000 |       1 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.933 |  1.000 | 0.966 |      14 |
| max-section-density          |     1 |     1.000 |  1.000 | 1.000 |       1 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     0.929 |  0.929 | 0.929 |      14 |
| earliest-mention             |     1 |     0.500 |  1.000 | 0.667 |       1 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.929 | 0.963 |      14 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-fraction               |     0 |     0.875 |  1.000 | 0.933 |      14 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.875 |  1.000 | 0.933 |      14 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-5-pages                |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-10-pages               |     1 |     0.333 |  1.000 | 0.500 |       1 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-15-pages               |     1 |     0.333 |  1.000 | 0.500 |       1 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     2 |     0.333 |  1.000 | 0.500 |       1 |
| (count or density) and early |     0 |     1.000 |  0.929 | 0.963 |      14 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     1.000 |  0.929 | 0.963 |      14 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `Sabin.document.18913.67778`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     0.889 |  0.571 | 0.696 |      14 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.143 |  1.000 | 0.250 |       1 |
| mention-count                |     0 |     0.867 |  0.929 | 0.897 |      14 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     0.889 |  0.571 | 0.696 |      14 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     0.857 |  0.857 | 0.857 |      14 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.867 |  0.929 | 0.897 |      14 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     0.909 |  0.714 | 0.800 |      14 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     0.889 |  0.571 | 0.696 |      14 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     0 |     0.867 |  0.929 | 0.897 |      14 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.867 |  0.929 | 0.897 |      14 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     0.889 |  0.571 | 0.696 |      14 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     0 |     0.889 |  0.571 | 0.696 |      14 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     0.889 |  0.571 | 0.696 |      14 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     0.889 |  0.571 | 0.696 |      14 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     0.889 |  0.571 | 0.696 |      14 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     0 |     0.889 |  0.571 | 0.696 |      14 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     0.889 |  0.571 | 0.696 |      14 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `Sabin.document.19022.19276`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.857 | 0.923 |      14 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.250 |  1.000 | 0.400 |       1 |
| mention-count                |     0 |     0.857 |  0.857 | 0.857 |      14 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     1.000 |  0.857 | 0.923 |      14 |
| mention-density              |     1 |     0.250 |  1.000 | 0.400 |       1 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     0.857 |  0.857 | 0.857 |      14 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     1.000 |  0.857 | 0.923 |      14 |
| max-section-density          |     1 |     0.250 |  1.000 | 0.400 |       1 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     0.857 |  0.857 | 0.857 |      14 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.857 | 0.923 |      14 |
| earliest-mention-page        |     1 |     0.500 |  1.000 | 0.667 |       1 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     0 |     0.875 |  1.000 | 0.933 |      14 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.857 |  0.857 | 0.857 |      14 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.857 | 0.923 |      14 |
| first-3-pages                |     1 |     0.500 |  1.000 | 0.667 |       1 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     0 |     1.000 |  0.857 | 0.923 |      14 |
| first-5-pages                |     1 |     0.500 |  1.000 | 0.667 |       1 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.857 | 0.923 |      14 |
| first-10-pages               |     1 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.857 | 0.923 |      14 |
| first-15-pages               |     1 |     0.250 |  1.000 | 0.400 |       1 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.857 | 0.923 |      14 |
| first-10-pages-density       |     1 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     0 |     1.000 |  0.857 | 0.923 |      14 |
| (count or density) and early |     1 |     0.250 |  1.000 | 0.400 |       1 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     1.000 |  0.857 | 0.923 |      14 |
| density and early            |     1 |     0.250 |  1.000 | 0.400 |       1 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `Sabin.document.3635.3636`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     0.923 |  0.857 | 0.889 |      14 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.333 |  1.000 | 0.500 |       1 |
| mention-count                |     0 |     0.929 |  0.929 | 0.929 |      14 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     0.923 |  0.857 | 0.889 |      14 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     0.929 |  0.929 | 0.929 |      14 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.929 |  0.929 | 0.929 |      14 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     0.923 |  0.857 | 0.889 |      14 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     0.923 |  0.857 | 0.889 |      14 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     0 |     0.875 |  1.000 | 0.933 |      14 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.929 |  0.929 | 0.929 |      14 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     0.923 |  0.857 | 0.889 |      14 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     0 |     0.923 |  0.857 | 0.889 |      14 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     0.923 |  0.857 | 0.889 |      14 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     0.923 |  0.857 | 0.889 |      14 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     0.923 |  0.857 | 0.889 |      14 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       1 |
| (count or density) and early |     0 |     0.923 |  0.857 | 0.889 |      14 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     0.923 |  0.857 | 0.889 |      14 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `Sabin.document.43062.43063`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.182 | 0.308 |      11 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant      |     2 |     0.071 |  1.000 | 0.133 |       1 |
| mention-count                |     0 |     1.000 |  0.364 | 0.533 |      11 |
| mention-count                |     1 |     0.364 |  1.000 | 0.533 |       4 |
| mention-count                |     2 |     1.000 |  1.000 | 1.000 |       1 |
| mention-density              |     0 |     1.000 |  0.636 | 0.778 |      11 |
| mention-density              |     1 |     0.500 |  1.000 | 0.667 |       4 |
| mention-density              |     2 |     1.000 |  1.000 | 1.000 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.455 | 0.625 |      11 |
| max-mentions-per-page        |     1 |     0.250 |  0.500 | 0.333 |       4 |
| max-mentions-per-page        |     2 |     0.333 |  1.000 | 0.500 |       1 |
| max-section-density          |     0 |     1.000 |  0.455 | 0.625 |      11 |
| max-section-density          |     1 |     0.400 |  1.000 | 0.571 |       4 |
| max-section-density          |     2 |     1.000 |  1.000 | 1.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.182 | 0.308 |      11 |
| earliest-mention             |     1 |     0.286 |  1.000 | 0.444 |       4 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     0.733 |  1.000 | 0.846 |      11 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       4 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     0 |     0.667 |  0.727 | 0.696 |      11 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       4 |
| first-fraction               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| decay-weighted               |     0 |     1.000 |  0.364 | 0.533 |      11 |
| decay-weighted               |     1 |     0.364 |  1.000 | 0.533 |       4 |
| decay-weighted               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.182 | 0.308 |      11 |
| first-3-pages                |     1 |     0.286 |  1.000 | 0.444 |       4 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     0 |     1.000 |  0.182 | 0.308 |      11 |
| first-5-pages                |     1 |     0.286 |  1.000 | 0.444 |       4 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.182 | 0.308 |      11 |
| first-10-pages               |     1 |     0.286 |  1.000 | 0.444 |       4 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.182 | 0.308 |      11 |
| first-15-pages               |     1 |     0.286 |  1.000 | 0.444 |       4 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.182 | 0.308 |      11 |
| first-10-pages-density       |     1 |     0.286 |  1.000 | 0.444 |       4 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     0 |     0.733 |  1.000 | 0.846 |      11 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       4 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     0.733 |  1.000 | 0.846 |      11 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       4 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `Sabin.document.6700.6809`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.750 | 0.857 |      16 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant      |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      16 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     0 |     1.000 |  0.750 | 0.857 |      16 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     0 |     1.000 |  1.000 | 1.000 |      16 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     0 |     1.000 |  0.938 | 0.968 |      16 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     0 |     1.000 |  0.875 | 0.933 |      16 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     0 |     1.000 |  0.750 | 0.857 |      16 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     0 |     1.000 |  1.000 | 1.000 |      16 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     0 |     1.000 |  1.000 | 1.000 |      16 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     0 |     1.000 |  0.750 | 0.857 |      16 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     0 |     1.000 |  0.750 | 0.857 |      16 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     0 |     1.000 |  0.750 | 0.857 |      16 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     0 |     1.000 |  0.750 | 0.857 |      16 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     0 |     1.000 |  0.750 | 0.857 |      16 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     0 |     1.000 |  0.750 | 0.857 |      16 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     0 |     1.000 |  0.750 | 0.857 |      16 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `Sabin.document.7023.7024`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.933 | 0.966 |      15 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      15 |
| mention-count                |     1 |     1.000 |  1.000 | 1.000 |       1 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     0 |     1.000 |  0.933 | 0.966 |      15 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     0 |     0.938 |  1.000 | 0.968 |      15 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     0 |     0.938 |  1.000 | 0.968 |      15 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     0 |     1.000 |  0.933 | 0.966 |      15 |
| earliest-mention             |     1 |     0.500 |  1.000 | 0.667 |       1 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     0 |     1.000 |  0.933 | 0.966 |      15 |
| earliest-mention-page        |     1 |     0.500 |  1.000 | 0.667 |       1 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     0 |     0.938 |  1.000 | 0.968 |      15 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     0 |     0.938 |  1.000 | 0.968 |      15 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     0 |     1.000 |  0.933 | 0.966 |      15 |
| first-3-pages                |     1 |     0.500 |  1.000 | 0.667 |       1 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     0 |     1.000 |  0.933 | 0.966 |      15 |
| first-5-pages                |     1 |     0.500 |  1.000 | 0.667 |       1 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     0 |     1.000 |  0.933 | 0.966 |      15 |
| first-10-pages               |     1 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     0 |     1.000 |  0.933 | 0.966 |      15 |
| first-15-pages               |     1 |     0.500 |  1.000 | 0.667 |       1 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     0 |     1.000 |  0.933 | 0.966 |      15 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     0 |     1.000 |  0.933 | 0.966 |      15 |
| (count or density) and early |     1 |     0.500 |  1.000 | 0.667 |       1 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     0 |     1.000 |  0.933 | 0.966 |      15 |
| density and early            |     1 |     0.500 |  1.000 | 0.667 |       1 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `Sabin.document.8001.8002`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  1.000 | 1.000 |      16 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant      |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      16 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     0 |     1.000 |  1.000 | 1.000 |      16 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     0 |     1.000 |  1.000 | 1.000 |      16 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     0 |     1.000 |  1.000 | 1.000 |      16 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     0 |     1.000 |  1.000 | 1.000 |      16 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     0 |     1.000 |  1.000 | 1.000 |      16 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     0 |     1.000 |  1.000 | 1.000 |      16 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     0 |     1.000 |  1.000 | 1.000 |      16 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     0 |     1.000 |  1.000 | 1.000 |      16 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     0 |     1.000 |  1.000 | 1.000 |      16 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     0 |     1.000 |  1.000 | 1.000 |      16 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     0 |     1.000 |  1.000 | 1.000 |      16 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     0 |     1.000 |  1.000 | 1.000 |      16 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     0 |     1.000 |  1.000 | 1.000 |      16 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     0 |     1.000 |  1.000 | 1.000 |      16 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.document.i00000279.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.923 | 0.960 |      13 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant      |     2 |     0.250 |  1.000 | 0.400 |       1 |
| mention-count                |     0 |     0.923 |  0.923 | 0.923 |      13 |
| mention-count                |     1 |     0.333 |  0.500 | 0.400 |       2 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     1.000 |  0.923 | 0.960 |      13 |
| mention-density              |     1 |     0.500 |  0.500 | 0.500 |       2 |
| mention-density              |     2 |     0.500 |  1.000 | 0.667 |       1 |
| max-mentions-per-page        |     0 |     0.923 |  0.923 | 0.923 |      13 |
| max-mentions-per-page        |     1 |     0.333 |  0.500 | 0.400 |       2 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.923 |  0.923 | 0.923 |      13 |
| max-section-density          |     1 |     0.333 |  0.500 | 0.400 |       2 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.923 | 0.960 |      13 |
| earliest-mention             |     1 |     0.500 |  1.000 | 0.667 |       2 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.923 | 0.960 |      13 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention-page        |     2 |     0.250 |  1.000 | 0.400 |       1 |
| first-fraction               |     0 |     0.929 |  1.000 | 0.963 |      13 |
| first-fraction               |     1 |     0.500 |  0.500 | 0.500 |       2 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.923 |  0.923 | 0.923 |      13 |
| decay-weighted               |     1 |     0.333 |  0.500 | 0.400 |       2 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.923 | 0.960 |      13 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     2 |     0.250 |  1.000 | 0.400 |       1 |
| first-5-pages                |     0 |     1.000 |  0.923 | 0.960 |      13 |
| first-5-pages                |     1 |     1.000 |  0.500 | 0.667 |       2 |
| first-5-pages                |     2 |     0.333 |  1.000 | 0.500 |       1 |
| first-10-pages               |     0 |     1.000 |  0.923 | 0.960 |      13 |
| first-10-pages               |     1 |     0.500 |  0.500 | 0.500 |       2 |
| first-10-pages               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-15-pages               |     0 |     1.000 |  0.923 | 0.960 |      13 |
| first-15-pages               |     1 |     0.500 |  0.500 | 0.500 |       2 |
| first-15-pages               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.923 | 0.960 |      13 |
| first-10-pages-density       |     1 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages-density       |     2 |     0.333 |  1.000 | 0.500 |       1 |
| (count or density) and early |     0 |     1.000 |  0.923 | 0.960 |      13 |
| (count or density) and early |     1 |     0.500 |  0.500 | 0.500 |       2 |
| (count or density) and early |     2 |     0.500 |  1.000 | 0.667 |       1 |
| density and early            |     0 |     1.000 |  0.923 | 0.960 |      13 |
| density and early            |     1 |     0.500 |  0.500 | 0.500 |       2 |
| density and early            |     2 |     0.500 |  1.000 | 0.667 |       1 |

### `UNFCCC.document.i00000326.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  1.000 | 1.000 |      11 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.400 |  1.000 | 0.571 |       2 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      11 |
| mention-count                |     1 |     0.600 |  1.000 | 0.750 |       3 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     1.000 |  1.000 | 1.000 |      11 |
| mention-density              |     1 |     1.000 |  1.000 | 1.000 |       3 |
| mention-density              |     2 |     1.000 |  1.000 | 1.000 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  1.000 | 1.000 |      11 |
| max-mentions-per-page        |     1 |     0.750 |  1.000 | 0.857 |       3 |
| max-mentions-per-page        |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-section-density          |     0 |     1.000 |  1.000 | 1.000 |      11 |
| max-section-density          |     1 |     0.600 |  1.000 | 0.750 |       3 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     0.917 |  1.000 | 0.957 |      11 |
| earliest-mention             |     1 |     0.500 |  0.667 | 0.571 |       3 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention-page        |     0 |     1.000 |  1.000 | 1.000 |      11 |
| earliest-mention-page        |     1 |     1.000 |  0.333 | 0.500 |       3 |
| earliest-mention-page        |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-fraction               |     0 |     0.786 |  1.000 | 0.880 |      11 |
| first-fraction               |     1 |     0.500 |  0.333 | 0.400 |       3 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| decay-weighted               |     0 |     0.846 |  1.000 | 0.917 |      11 |
| decay-weighted               |     1 |     0.333 |  0.333 | 0.333 |       3 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  1.000 | 1.000 |      11 |
| first-3-pages                |     1 |     1.000 |  0.333 | 0.500 |       3 |
| first-3-pages                |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-5-pages                |     0 |     1.000 |  1.000 | 1.000 |      11 |
| first-5-pages                |     1 |     0.750 |  1.000 | 0.857 |       3 |
| first-5-pages                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  1.000 | 1.000 |      11 |
| first-10-pages               |     1 |     0.750 |  1.000 | 0.857 |       3 |
| first-10-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-15-pages               |     0 |     1.000 |  1.000 | 1.000 |      11 |
| first-15-pages               |     1 |     1.000 |  1.000 | 1.000 |       3 |
| first-15-pages               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-10-pages-density       |     0 |     1.000 |  1.000 | 1.000 |      11 |
| first-10-pages-density       |     1 |     1.000 |  1.000 | 1.000 |       3 |
| first-10-pages-density       |     2 |     1.000 |  1.000 | 1.000 |       2 |
| (count or density) and early |     0 |     1.000 |  1.000 | 1.000 |      11 |
| (count or density) and early |     1 |     1.000 |  1.000 | 1.000 |       3 |
| (count or density) and early |     2 |     1.000 |  1.000 | 1.000 |       2 |
| density and early            |     0 |     1.000 |  1.000 | 1.000 |      11 |
| density and early            |     1 |     1.000 |  1.000 | 1.000 |       3 |
| density and early            |     2 |     1.000 |  1.000 | 1.000 |       2 |

### `UNFCCC.document.i00002301.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.385 | 0.556 |      13 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       1 |
| any-mention-is-relevant      |     2 |     0.182 |  1.000 | 0.308 |       2 |
| mention-count                |     0 |     1.000 |  0.615 | 0.762 |      13 |
| mention-count                |     1 |     0.167 |  1.000 | 0.286 |       1 |
| mention-count                |     2 |     1.000 |  1.000 | 1.000 |       2 |
| mention-density              |     0 |     1.000 |  0.846 | 0.917 |      13 |
| mention-density              |     1 |     0.250 |  1.000 | 0.400 |       1 |
| mention-density              |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.769 | 0.870 |      13 |
| max-mentions-per-page        |     1 |     0.250 |  1.000 | 0.400 |       1 |
| max-mentions-per-page        |     2 |     1.000 |  1.000 | 1.000 |       2 |
| max-section-density          |     0 |     1.000 |  0.538 | 0.700 |      13 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     2 |     0.667 |  1.000 | 0.800 |       2 |
| earliest-mention             |     0 |     1.000 |  0.385 | 0.556 |      13 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     2 |     0.500 |  1.000 | 0.667 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.769 | 0.870 |      13 |
| earliest-mention-page        |     1 |     0.200 |  1.000 | 0.333 |       1 |
| earliest-mention-page        |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-fraction               |     0 |     1.000 |  0.769 | 0.870 |      13 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| decay-weighted               |     0 |     1.000 |  0.769 | 0.870 |      13 |
| decay-weighted               |     1 |     0.250 |  1.000 | 0.400 |       1 |
| decay-weighted               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.385 | 0.556 |      13 |
| first-3-pages                |     1 |     0.100 |  1.000 | 0.182 |       1 |
| first-3-pages                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-5-pages                |     0 |     1.000 |  0.385 | 0.556 |      13 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     2 |     0.500 |  0.500 | 0.500 |       2 |
| first-10-pages               |     0 |     1.000 |  0.385 | 0.556 |      13 |
| first-10-pages               |     1 |     0.100 |  1.000 | 0.182 |       1 |
| first-10-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-15-pages               |     0 |     1.000 |  0.385 | 0.556 |      13 |
| first-15-pages               |     1 |     0.100 |  1.000 | 0.182 |       1 |
| first-15-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.385 | 0.556 |      13 |
| first-10-pages-density       |     1 |     0.100 |  1.000 | 0.182 |       1 |
| first-10-pages-density       |     2 |     1.000 |  0.500 | 0.667 |       2 |
| (count or density) and early |     0 |     1.000 |  0.846 | 0.917 |      13 |
| (count or density) and early |     1 |     0.250 |  1.000 | 0.400 |       1 |
| (count or density) and early |     2 |     1.000 |  0.500 | 0.667 |       2 |
| density and early            |     0 |     1.000 |  0.846 | 0.917 |      13 |
| density and early            |     1 |     0.250 |  1.000 | 0.400 |       1 |
| density and early            |     2 |     1.000 |  0.500 | 0.667 |       2 |

### `UNFCCC.document.i00003501.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.545 | 0.706 |      11 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.200 |  1.000 | 0.333 |       2 |
| mention-count                |     0 |     1.000 |  0.727 | 0.842 |      11 |
| mention-count                |     1 |     0.429 |  1.000 | 0.600 |       3 |
| mention-count                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| mention-density              |     0 |     1.000 |  0.818 | 0.900 |      11 |
| mention-density              |     1 |     0.500 |  1.000 | 0.667 |       3 |
| mention-density              |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.727 | 0.842 |      11 |
| max-mentions-per-page        |     1 |     0.400 |  0.667 | 0.500 |       3 |
| max-mentions-per-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-section-density          |     0 |     1.000 |  0.727 | 0.842 |      11 |
| max-section-density          |     1 |     0.200 |  0.333 | 0.250 |       3 |
| max-section-density          |     2 |     0.333 |  0.500 | 0.400 |       2 |
| earliest-mention             |     0 |     1.000 |  0.636 | 0.778 |      11 |
| earliest-mention             |     1 |     0.375 |  1.000 | 0.545 |       3 |
| earliest-mention             |     2 |     1.000 |  0.500 | 0.667 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.636 | 0.778 |      11 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       3 |
| earliest-mention-page        |     2 |     0.167 |  0.500 | 0.250 |       2 |
| first-fraction               |     0 |     1.000 |  0.818 | 0.900 |      11 |
| first-fraction               |     1 |     0.500 |  0.667 | 0.571 |       3 |
| first-fraction               |     2 |     0.333 |  0.500 | 0.400 |       2 |
| decay-weighted               |     0 |     1.000 |  0.818 | 0.900 |      11 |
| decay-weighted               |     1 |     0.500 |  1.000 | 0.667 |       3 |
| decay-weighted               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-3-pages                |     0 |     1.000 |  0.545 | 0.706 |      11 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       3 |
| first-3-pages                |     2 |     0.167 |  0.500 | 0.250 |       2 |
| first-5-pages                |     0 |     1.000 |  0.545 | 0.706 |      11 |
| first-5-pages                |     1 |     0.400 |  0.667 | 0.500 |       3 |
| first-5-pages                |     2 |     0.400 |  1.000 | 0.571 |       2 |
| first-10-pages               |     0 |     1.000 |  0.545 | 0.706 |      11 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       3 |
| first-10-pages               |     2 |     0.286 |  1.000 | 0.444 |       2 |
| first-15-pages               |     0 |     1.000 |  0.545 | 0.706 |      11 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       3 |
| first-15-pages               |     2 |     0.333 |  1.000 | 0.500 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.545 | 0.706 |      11 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       3 |
| first-10-pages-density       |     2 |     0.286 |  1.000 | 0.444 |       2 |
| (count or density) and early |     0 |     1.000 |  0.727 | 0.842 |      11 |
| (count or density) and early |     1 |     0.429 |  1.000 | 0.600 |       3 |
| (count or density) and early |     2 |     1.000 |  0.500 | 0.667 |       2 |
| density and early            |     0 |     1.000 |  0.818 | 0.900 |      11 |
| density and early            |     1 |     0.500 |  1.000 | 0.667 |       3 |
| density and early            |     2 |     1.000 |  0.500 | 0.667 |       2 |

### `UNFCCC.document.i00003855.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.444 | 0.615 |       9 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       5 |
| any-mention-is-relevant      |     2 |     0.167 |  1.000 | 0.286 |       2 |
| mention-count                |     0 |     1.000 |  0.667 | 0.800 |       9 |
| mention-count                |     1 |     0.625 |  1.000 | 0.769 |       5 |
| mention-count                |     2 |     1.000 |  1.000 | 1.000 |       2 |
| mention-density              |     0 |     0.900 |  1.000 | 0.947 |       9 |
| mention-density              |     1 |     1.000 |  0.800 | 0.889 |       5 |
| mention-density              |     2 |     1.000 |  1.000 | 1.000 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.667 | 0.800 |       9 |
| max-mentions-per-page        |     1 |     0.571 |  0.800 | 0.667 |       5 |
| max-mentions-per-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-section-density          |     0 |     1.000 |  0.556 | 0.714 |       9 |
| max-section-density          |     1 |     0.500 |  0.800 | 0.615 |       5 |
| max-section-density          |     2 |     0.667 |  1.000 | 0.800 |       2 |
| earliest-mention             |     0 |     1.000 |  0.444 | 0.615 |       9 |
| earliest-mention             |     1 |     0.375 |  0.600 | 0.462 |       5 |
| earliest-mention             |     2 |     0.500 |  1.000 | 0.667 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.667 | 0.800 |       9 |
| earliest-mention-page        |     1 |     0.500 |  1.000 | 0.667 |       5 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-fraction               |     0 |     0.889 |  0.889 | 0.889 |       9 |
| first-fraction               |     1 |     0.667 |  0.400 | 0.500 |       5 |
| first-fraction               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| decay-weighted               |     0 |     0.875 |  0.778 | 0.824 |       9 |
| decay-weighted               |     1 |     0.667 |  0.800 | 0.727 |       5 |
| decay-weighted               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.444 | 0.615 |       9 |
| first-3-pages                |     1 |     0.417 |  1.000 | 0.588 |       5 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-5-pages                |     0 |     1.000 |  0.444 | 0.615 |       9 |
| first-5-pages                |     1 |     0.455 |  1.000 | 0.625 |       5 |
| first-5-pages                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  0.444 | 0.615 |       9 |
| first-10-pages               |     1 |     0.455 |  1.000 | 0.625 |       5 |
| first-10-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-15-pages               |     0 |     1.000 |  0.444 | 0.615 |       9 |
| first-15-pages               |     1 |     0.500 |  1.000 | 0.667 |       5 |
| first-15-pages               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.444 | 0.615 |       9 |
| first-10-pages-density       |     1 |     0.455 |  1.000 | 0.625 |       5 |
| first-10-pages-density       |     2 |     1.000 |  0.500 | 0.667 |       2 |
| (count or density) and early |     0 |     1.000 |  0.667 | 0.800 |       9 |
| (count or density) and early |     1 |     0.500 |  1.000 | 0.667 |       5 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       2 |
| density and early            |     0 |     0.900 |  1.000 | 0.947 |       9 |
| density and early            |     1 |     0.667 |  0.800 | 0.727 |       5 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       2 |

### `UNFCCC.document.i00004003.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.429 | 0.600 |       7 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       5 |
| any-mention-is-relevant      |     2 |     0.308 |  1.000 | 0.471 |       4 |
| mention-count                |     0 |     1.000 |  0.714 | 0.833 |       7 |
| mention-count                |     1 |     0.500 |  0.800 | 0.615 |       5 |
| mention-count                |     2 |     0.667 |  0.500 | 0.571 |       4 |
| mention-density              |     0 |     0.667 |  0.857 | 0.750 |       7 |
| mention-density              |     1 |     0.500 |  0.600 | 0.545 |       5 |
| mention-density              |     2 |     1.000 |  0.250 | 0.400 |       4 |
| max-mentions-per-page        |     0 |     1.000 |  0.714 | 0.833 |       7 |
| max-mentions-per-page        |     1 |     0.500 |  0.600 | 0.545 |       5 |
| max-mentions-per-page        |     2 |     0.600 |  0.750 | 0.667 |       4 |
| max-section-density          |     0 |     1.000 |  0.714 | 0.833 |       7 |
| max-section-density          |     1 |     0.600 |  0.600 | 0.600 |       5 |
| max-section-density          |     2 |     0.500 |  0.750 | 0.600 |       4 |
| earliest-mention             |     0 |     1.000 |  0.857 | 0.923 |       7 |
| earliest-mention             |     1 |     0.571 |  0.800 | 0.667 |       5 |
| earliest-mention             |     2 |     0.667 |  0.500 | 0.571 |       4 |
| earliest-mention-page        |     0 |     0.857 |  0.857 | 0.857 |       7 |
| earliest-mention-page        |     1 |     0.571 |  0.800 | 0.667 |       5 |
| earliest-mention-page        |     2 |     0.500 |  0.250 | 0.333 |       4 |
| first-fraction               |     0 |     0.750 |  0.857 | 0.800 |       7 |
| first-fraction               |     1 |     0.667 |  0.400 | 0.500 |       5 |
| first-fraction               |     2 |     0.600 |  0.750 | 0.667 |       4 |
| decay-weighted               |     0 |     0.857 |  0.857 | 0.857 |       7 |
| decay-weighted               |     1 |     0.500 |  0.800 | 0.615 |       5 |
| decay-weighted               |     2 |     1.000 |  0.250 | 0.400 |       4 |
| first-3-pages                |     0 |     1.000 |  0.429 | 0.600 |       7 |
| first-3-pages                |     1 |     0.364 |  0.800 | 0.500 |       5 |
| first-3-pages                |     2 |     0.500 |  0.250 | 0.333 |       4 |
| first-5-pages                |     0 |     1.000 |  0.429 | 0.600 |       7 |
| first-5-pages                |     1 |     0.417 |  1.000 | 0.588 |       5 |
| first-5-pages                |     2 |     1.000 |  0.250 | 0.400 |       4 |
| first-10-pages               |     0 |     1.000 |  0.429 | 0.600 |       7 |
| first-10-pages               |     1 |     0.455 |  1.000 | 0.625 |       5 |
| first-10-pages               |     2 |     1.000 |  0.500 | 0.667 |       4 |
| first-15-pages               |     0 |     1.000 |  0.429 | 0.600 |       7 |
| first-15-pages               |     1 |     0.500 |  1.000 | 0.667 |       5 |
| first-15-pages               |     2 |     1.000 |  0.750 | 0.857 |       4 |
| first-10-pages-density       |     0 |     1.000 |  0.429 | 0.600 |       7 |
| first-10-pages-density       |     1 |     0.455 |  1.000 | 0.625 |       5 |
| first-10-pages-density       |     2 |     1.000 |  0.500 | 0.667 |       4 |
| (count or density) and early |     0 |     0.857 |  0.857 | 0.857 |       7 |
| (count or density) and early |     1 |     0.625 |  1.000 | 0.769 |       5 |
| (count or density) and early |     2 |     1.000 |  0.250 | 0.400 |       4 |
| density and early            |     0 |     0.667 |  0.857 | 0.750 |       7 |
| density and early            |     1 |     0.429 |  0.600 | 0.500 |       5 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       4 |

### `UNFCCC.document.i00004212.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.500 | 0.667 |      10 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant      |     2 |     0.364 |  1.000 | 0.533 |       4 |
| mention-count                |     0 |     1.000 |  0.900 | 0.947 |      10 |
| mention-count                |     1 |     0.333 |  1.000 | 0.500 |       2 |
| mention-count                |     2 |     1.000 |  0.250 | 0.400 |       4 |
| mention-density              |     0 |     1.000 |  0.900 | 0.947 |      10 |
| mention-density              |     1 |     0.333 |  1.000 | 0.500 |       2 |
| mention-density              |     2 |     1.000 |  0.250 | 0.400 |       4 |
| max-mentions-per-page        |     0 |     1.000 |  0.900 | 0.947 |      10 |
| max-mentions-per-page        |     1 |     0.333 |  1.000 | 0.500 |       2 |
| max-mentions-per-page        |     2 |     1.000 |  0.250 | 0.400 |       4 |
| max-section-density          |     0 |     1.000 |  0.500 | 0.667 |      10 |
| max-section-density          |     1 |     0.125 |  0.500 | 0.200 |       2 |
| max-section-density          |     2 |     0.667 |  0.500 | 0.571 |       4 |
| earliest-mention             |     0 |     1.000 |  0.500 | 0.667 |      10 |
| earliest-mention             |     1 |     0.222 |  1.000 | 0.364 |       2 |
| earliest-mention             |     2 |     1.000 |  0.500 | 0.667 |       4 |
| earliest-mention-page        |     0 |     1.000 |  0.500 | 0.667 |      10 |
| earliest-mention-page        |     1 |     0.143 |  0.500 | 0.222 |       2 |
| earliest-mention-page        |     2 |     0.750 |  0.750 | 0.750 |       4 |
| first-fraction               |     0 |     1.000 |  1.000 | 1.000 |      10 |
| first-fraction               |     1 |     0.400 |  1.000 | 0.571 |       2 |
| first-fraction               |     2 |     1.000 |  0.250 | 0.400 |       4 |
| decay-weighted               |     0 |     1.000 |  1.000 | 1.000 |      10 |
| decay-weighted               |     1 |     0.400 |  1.000 | 0.571 |       2 |
| decay-weighted               |     2 |     1.000 |  0.250 | 0.400 |       4 |
| first-3-pages                |     0 |     1.000 |  0.500 | 0.667 |      10 |
| first-3-pages                |     1 |     0.143 |  0.500 | 0.222 |       2 |
| first-3-pages                |     2 |     0.750 |  0.750 | 0.750 |       4 |
| first-5-pages                |     0 |     1.000 |  0.500 | 0.667 |      10 |
| first-5-pages                |     1 |     0.125 |  0.500 | 0.200 |       2 |
| first-5-pages                |     2 |     0.667 |  0.500 | 0.571 |       4 |
| first-10-pages               |     0 |     1.000 |  0.500 | 0.667 |      10 |
| first-10-pages               |     1 |     0.143 |  0.500 | 0.222 |       2 |
| first-10-pages               |     2 |     0.750 |  0.750 | 0.750 |       4 |
| first-15-pages               |     0 |     1.000 |  0.500 | 0.667 |      10 |
| first-15-pages               |     1 |     0.200 |  1.000 | 0.333 |       2 |
| first-15-pages               |     2 |     1.000 |  0.250 | 0.400 |       4 |
| first-10-pages-density       |     0 |     1.000 |  0.500 | 0.667 |      10 |
| first-10-pages-density       |     1 |     0.143 |  0.500 | 0.222 |       2 |
| first-10-pages-density       |     2 |     0.750 |  0.750 | 0.750 |       4 |
| (count or density) and early |     0 |     1.000 |  0.900 | 0.947 |      10 |
| (count or density) and early |     1 |     0.333 |  1.000 | 0.500 |       2 |
| (count or density) and early |     2 |     1.000 |  0.250 | 0.400 |       4 |
| density and early            |     0 |     1.000 |  0.900 | 0.947 |      10 |
| density and early            |     1 |     0.333 |  1.000 | 0.500 |       2 |
| density and early            |     2 |     1.000 |  0.250 | 0.400 |       4 |

### `UNFCCC.document.i00005049.n0000`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.636 | 0.778 |      11 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.222 |  1.000 | 0.364 |       2 |
| mention-count                |     0 |     1.000 |  0.909 | 0.952 |      11 |
| mention-count                |     1 |     0.600 |  1.000 | 0.750 |       3 |
| mention-count                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| mention-density              |     0 |     1.000 |  0.909 | 0.952 |      11 |
| mention-density              |     1 |     0.750 |  1.000 | 0.857 |       3 |
| mention-density              |     2 |     1.000 |  1.000 | 1.000 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.909 | 0.952 |      11 |
| max-mentions-per-page        |     1 |     0.600 |  1.000 | 0.750 |       3 |
| max-mentions-per-page        |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-section-density          |     0 |     0.889 |  0.727 | 0.800 |      11 |
| max-section-density          |     1 |     0.286 |  0.667 | 0.400 |       3 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  0.727 | 0.842 |      11 |
| earliest-mention             |     1 |     0.500 |  1.000 | 0.667 |       3 |
| earliest-mention             |     2 |     1.000 |  1.000 | 1.000 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.727 | 0.842 |      11 |
| earliest-mention-page        |     1 |     0.400 |  0.667 | 0.500 |       3 |
| earliest-mention-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-fraction               |     0 |     1.000 |  0.909 | 0.952 |      11 |
| first-fraction               |     1 |     0.750 |  1.000 | 0.857 |       3 |
| first-fraction               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| decay-weighted               |     0 |     1.000 |  0.909 | 0.952 |      11 |
| decay-weighted               |     1 |     0.600 |  1.000 | 0.750 |       3 |
| decay-weighted               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-3-pages                |     0 |     1.000 |  0.636 | 0.778 |      11 |
| first-3-pages                |     1 |     0.333 |  0.667 | 0.444 |       3 |
| first-3-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-5-pages                |     0 |     1.000 |  0.636 | 0.778 |      11 |
| first-5-pages                |     1 |     0.429 |  1.000 | 0.600 |       3 |
| first-5-pages                |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-10-pages               |     0 |     1.000 |  0.636 | 0.778 |      11 |
| first-10-pages               |     1 |     0.429 |  1.000 | 0.600 |       3 |
| first-10-pages               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-15-pages               |     0 |     1.000 |  0.636 | 0.778 |      11 |
| first-15-pages               |     1 |     0.333 |  0.667 | 0.444 |       3 |
| first-15-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.636 | 0.778 |      11 |
| first-10-pages-density       |     1 |     0.429 |  1.000 | 0.600 |       3 |
| first-10-pages-density       |     2 |     1.000 |  1.000 | 1.000 |       2 |
| (count or density) and early |     0 |     1.000 |  0.909 | 0.952 |      11 |
| (count or density) and early |     1 |     0.750 |  1.000 | 0.857 |       3 |
| (count or density) and early |     2 |     1.000 |  1.000 | 1.000 |       2 |
| density and early            |     0 |     1.000 |  0.909 | 0.952 |      11 |
| density and early            |     1 |     0.750 |  1.000 | 0.857 |       3 |
| density and early            |     2 |     1.000 |  1.000 | 1.000 |       2 |

### `UNFCCC.non-party.1262.0`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.929 | 0.963 |      14 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant      |     2 |     0.667 |  1.000 | 0.800 |       2 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      14 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     1.000 |  0.929 | 0.963 |      14 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  1.000 | 1.000 |      14 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       2 |
| max-section-density          |     0 |     1.000 |  0.929 | 0.963 |      14 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  0.929 | 0.963 |      14 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     2 |     1.000 |  0.500 | 0.667 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.929 | 0.963 |      14 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-fraction               |     0 |     0.875 |  1.000 | 0.933 |      14 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| decay-weighted               |     0 |     0.933 |  1.000 | 0.966 |      14 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-5-pages                |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-10-pages               |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-15-pages               |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     2 |     0.667 |  1.000 | 0.800 |       2 |
| (count or density) and early |     0 |     1.000 |  0.929 | 0.963 |      14 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     2 |     0.667 |  1.000 | 0.800 |       2 |
| density and early            |     0 |     1.000 |  0.929 | 0.963 |      14 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     2 |     0.667 |  1.000 | 0.800 |       2 |

### `UNFCCC.non-party.1720.0`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.615 | 0.762 |      13 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant      |     2 |     0.125 |  1.000 | 0.222 |       1 |
| mention-count                |     0 |     1.000 |  0.846 | 0.917 |      13 |
| mention-count                |     1 |     0.400 |  1.000 | 0.571 |       2 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     1.000 |  0.615 | 0.762 |      13 |
| mention-density              |     1 |     0.167 |  0.500 | 0.250 |       2 |
| mention-density              |     2 |     0.500 |  1.000 | 0.667 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.769 | 0.870 |      13 |
| max-mentions-per-page        |     1 |     0.200 |  0.500 | 0.286 |       2 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.929 |  1.000 | 0.963 |      13 |
| max-section-density          |     1 |     0.500 |  0.500 | 0.500 |       2 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.692 | 0.818 |      13 |
| earliest-mention             |     1 |     0.286 |  1.000 | 0.444 |       2 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.615 | 0.762 |      13 |
| earliest-mention-page        |     1 |     0.250 |  1.000 | 0.400 |       2 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     0 |     0.929 |  1.000 | 0.963 |      13 |
| first-fraction               |     1 |     0.500 |  0.500 | 0.500 |       2 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     1.000 |  0.846 | 0.917 |      13 |
| decay-weighted               |     1 |     0.400 |  1.000 | 0.571 |       2 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.615 | 0.762 |      13 |
| first-3-pages                |     1 |     0.250 |  1.000 | 0.400 |       2 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     0 |     1.000 |  0.615 | 0.762 |      13 |
| first-5-pages                |     1 |     0.167 |  0.500 | 0.250 |       2 |
| first-5-pages                |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages               |     0 |     1.000 |  0.615 | 0.762 |      13 |
| first-10-pages               |     1 |     0.167 |  0.500 | 0.250 |       2 |
| first-10-pages               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-15-pages               |     0 |     1.000 |  0.615 | 0.762 |      13 |
| first-15-pages               |     1 |     0.167 |  0.500 | 0.250 |       2 |
| first-15-pages               |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.615 | 0.762 |      13 |
| first-10-pages-density       |     1 |     0.200 |  0.500 | 0.286 |       2 |
| first-10-pages-density       |     2 |     0.333 |  1.000 | 0.500 |       1 |
| (count or density) and early |     0 |     1.000 |  0.615 | 0.762 |      13 |
| (count or density) and early |     1 |     0.250 |  1.000 | 0.400 |       2 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     1.000 |  0.615 | 0.762 |      13 |
| density and early            |     1 |     0.250 |  1.000 | 0.400 |       2 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `UNFCCC.non-party.1820.0`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.727 | 0.842 |      11 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.250 |  1.000 | 0.400 |       2 |
| mention-count                |     0 |     0.833 |  0.909 | 0.870 |      11 |
| mention-count                |     1 |     0.250 |  0.333 | 0.286 |       3 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     1.000 |  0.727 | 0.842 |      11 |
| mention-density              |     1 |     0.600 |  1.000 | 0.750 |       3 |
| mention-density              |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-mentions-per-page        |     0 |     0.909 |  0.909 | 0.909 |      11 |
| max-mentions-per-page        |     1 |     0.500 |  0.667 | 0.571 |       3 |
| max-mentions-per-page        |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-section-density          |     0 |     1.000 |  0.818 | 0.900 |      11 |
| max-section-density          |     1 |     0.429 |  1.000 | 0.600 |       3 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  0.727 | 0.842 |      11 |
| earliest-mention             |     1 |     0.375 |  1.000 | 0.545 |       3 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.727 | 0.842 |      11 |
| earliest-mention-page        |     1 |     0.250 |  0.333 | 0.286 |       3 |
| earliest-mention-page        |     2 |     0.250 |  0.500 | 0.333 |       2 |
| first-fraction               |     0 |     0.714 |  0.909 | 0.800 |      11 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       3 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| decay-weighted               |     0 |     0.714 |  0.909 | 0.800 |      11 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       3 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.727 | 0.842 |      11 |
| first-3-pages                |     1 |     0.250 |  0.333 | 0.286 |       3 |
| first-3-pages                |     2 |     0.250 |  0.500 | 0.333 |       2 |
| first-5-pages                |     0 |     1.000 |  0.727 | 0.842 |      11 |
| first-5-pages                |     1 |     0.500 |  0.667 | 0.571 |       3 |
| first-5-pages                |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  0.727 | 0.842 |      11 |
| first-10-pages               |     1 |     0.600 |  1.000 | 0.750 |       3 |
| first-10-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-15-pages               |     0 |     1.000 |  0.727 | 0.842 |      11 |
| first-15-pages               |     1 |     0.429 |  1.000 | 0.600 |       3 |
| first-15-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.727 | 0.842 |      11 |
| first-10-pages-density       |     1 |     0.333 |  0.333 | 0.333 |       3 |
| first-10-pages-density       |     2 |     0.400 |  1.000 | 0.571 |       2 |
| (count or density) and early |     0 |     1.000 |  0.727 | 0.842 |      11 |
| (count or density) and early |     1 |     0.500 |  1.000 | 0.667 |       3 |
| (count or density) and early |     2 |     0.500 |  0.500 | 0.500 |       2 |
| density and early            |     0 |     1.000 |  0.727 | 0.842 |      11 |
| density and early            |     1 |     0.500 |  1.000 | 0.667 |       3 |
| density and early            |     2 |     0.500 |  0.500 | 0.500 |       2 |

### `UNFCCC.party.1513.0`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.333 | 0.500 |       9 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       5 |
| any-mention-is-relevant      |     2 |     0.154 |  1.000 | 0.267 |       2 |
| mention-count                |     0 |     1.000 |  0.667 | 0.800 |       9 |
| mention-count                |     1 |     0.556 |  1.000 | 0.714 |       5 |
| mention-count                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| mention-density              |     0 |     1.000 |  1.000 | 1.000 |       9 |
| mention-density              |     1 |     0.714 |  1.000 | 0.833 |       5 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.667 | 0.800 |       9 |
| max-mentions-per-page        |     1 |     0.250 |  0.200 | 0.222 |       5 |
| max-mentions-per-page        |     2 |     0.333 |  1.000 | 0.500 |       2 |
| max-section-density          |     0 |     1.000 |  1.000 | 1.000 |       9 |
| max-section-density          |     1 |     0.800 |  0.800 | 0.800 |       5 |
| max-section-density          |     2 |     0.500 |  0.500 | 0.500 |       2 |
| earliest-mention             |     0 |     1.000 |  0.556 | 0.714 |       9 |
| earliest-mention             |     1 |     0.333 |  0.200 | 0.250 |       5 |
| earliest-mention             |     2 |     0.250 |  1.000 | 0.400 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.556 | 0.714 |       9 |
| earliest-mention-page        |     1 |     0.500 |  0.800 | 0.615 |       5 |
| earliest-mention-page        |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-fraction               |     0 |     1.000 |  0.667 | 0.800 |       9 |
| first-fraction               |     1 |     0.400 |  0.400 | 0.400 |       5 |
| first-fraction               |     2 |     0.400 |  1.000 | 0.571 |       2 |
| decay-weighted               |     0 |     1.000 |  0.667 | 0.800 |       9 |
| decay-weighted               |     1 |     0.500 |  0.800 | 0.615 |       5 |
| decay-weighted               |     2 |     0.500 |  0.500 | 0.500 |       2 |
| first-3-pages                |     0 |     1.000 |  0.333 | 0.500 |       9 |
| first-3-pages                |     1 |     0.400 |  0.800 | 0.533 |       5 |
| first-3-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-5-pages                |     0 |     1.000 |  0.333 | 0.500 |       9 |
| first-5-pages                |     1 |     0.400 |  0.800 | 0.533 |       5 |
| first-5-pages                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages               |     0 |     1.000 |  0.333 | 0.500 |       9 |
| first-10-pages               |     1 |     0.400 |  0.800 | 0.533 |       5 |
| first-10-pages               |     2 |     0.667 |  1.000 | 0.800 |       2 |
| first-15-pages               |     0 |     1.000 |  0.333 | 0.500 |       9 |
| first-15-pages               |     1 |     0.222 |  0.400 | 0.286 |       5 |
| first-15-pages               |     2 |     0.250 |  0.500 | 0.333 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.333 | 0.500 |       9 |
| first-10-pages-density       |     1 |     0.400 |  0.800 | 0.533 |       5 |
| first-10-pages-density       |     2 |     0.667 |  1.000 | 0.800 |       2 |
| (count or density) and early |     0 |     1.000 |  0.667 | 0.800 |       9 |
| (count or density) and early |     1 |     0.556 |  1.000 | 0.714 |       5 |
| (count or density) and early |     2 |     1.000 |  0.500 | 0.667 |       2 |
| density and early            |     0 |     1.000 |  1.000 | 1.000 |       9 |
| density and early            |     1 |     0.714 |  1.000 | 0.833 |       5 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       2 |

### `UNFCCC.party.1785.0`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.929 | 0.963 |      14 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant      |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     0 |     0.933 |  1.000 | 0.966 |      14 |
| mention-count                |     1 |     1.000 |  0.500 | 0.667 |       2 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     0 |     1.000 |  0.929 | 0.963 |      14 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     0 |     0.933 |  1.000 | 0.966 |      14 |
| max-mentions-per-page        |     1 |     1.000 |  0.500 | 0.667 |       2 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     0 |     1.000 |  0.929 | 0.963 |      14 |
| max-section-density          |     1 |     0.667 |  1.000 | 0.800 |       2 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     0 |     0.929 |  0.929 | 0.929 |      14 |
| earliest-mention             |     1 |     0.500 |  0.500 | 0.500 |       2 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     0 |     1.000 |  0.929 | 0.963 |      14 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     0 |     0.875 |  1.000 | 0.933 |      14 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       2 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     0 |     0.875 |  1.000 | 0.933 |      14 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       2 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-5-pages                |     1 |     0.500 |  0.500 | 0.500 |       2 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-10-pages               |     1 |     0.667 |  1.000 | 0.800 |       2 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-15-pages               |     1 |     0.667 |  1.000 | 0.800 |       2 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     0 |     1.000 |  0.929 | 0.963 |      14 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       2 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     0 |     1.000 |  0.929 | 0.963 |      14 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       2 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     0 |     1.000 |  0.929 | 0.963 |      14 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       2 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `UNFCCC.party.631.0`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.167 | 0.286 |       6 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       8 |
| any-mention-is-relevant      |     2 |     0.133 |  1.000 | 0.235 |       2 |
| mention-count                |     0 |     1.000 |  0.333 | 0.500 |       6 |
| mention-count                |     1 |     0.636 |  0.875 | 0.737 |       8 |
| mention-count                |     2 |     0.667 |  1.000 | 0.800 |       2 |
| mention-density              |     0 |     0.625 |  0.833 | 0.714 |       6 |
| mention-density              |     1 |     0.833 |  0.625 | 0.714 |       8 |
| mention-density              |     2 |     1.000 |  1.000 | 1.000 |       2 |
| max-mentions-per-page        |     0 |     0.750 |  0.500 | 0.600 |       6 |
| max-mentions-per-page        |     1 |     0.500 |  0.375 | 0.429 |       8 |
| max-mentions-per-page        |     2 |     0.333 |  1.000 | 0.500 |       2 |
| max-section-density          |     0 |     0.667 |  0.333 | 0.444 |       6 |
| max-section-density          |     1 |     0.556 |  0.625 | 0.588 |       8 |
| max-section-density          |     2 |     0.500 |  1.000 | 0.667 |       2 |
| earliest-mention             |     0 |     1.000 |  0.333 | 0.500 |       6 |
| earliest-mention             |     1 |     0.429 |  0.375 | 0.400 |       8 |
| earliest-mention             |     2 |     0.286 |  1.000 | 0.444 |       2 |
| earliest-mention-page        |     0 |     0.833 |  0.833 | 0.833 |       6 |
| earliest-mention-page        |     1 |     0.700 |  0.875 | 0.778 |       8 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-fraction               |     0 |     0.833 |  0.833 | 0.833 |       6 |
| first-fraction               |     1 |     1.000 |  0.625 | 0.769 |       8 |
| first-fraction               |     2 |     0.400 |  1.000 | 0.571 |       2 |
| decay-weighted               |     0 |     1.000 |  0.833 | 0.909 |       6 |
| decay-weighted               |     1 |     0.889 |  1.000 | 0.941 |       8 |
| decay-weighted               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.167 | 0.286 |       6 |
| first-3-pages                |     1 |     0.533 |  1.000 | 0.696 |       8 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-5-pages                |     0 |     1.000 |  0.167 | 0.286 |       6 |
| first-5-pages                |     1 |     0.533 |  1.000 | 0.696 |       8 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-10-pages               |     0 |     1.000 |  0.167 | 0.286 |       6 |
| first-10-pages               |     1 |     0.533 |  1.000 | 0.696 |       8 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-15-pages               |     0 |     1.000 |  0.167 | 0.286 |       6 |
| first-15-pages               |     1 |     0.615 |  1.000 | 0.762 |       8 |
| first-15-pages               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.167 | 0.286 |       6 |
| first-10-pages-density       |     1 |     0.615 |  1.000 | 0.762 |       8 |
| first-10-pages-density       |     2 |     1.000 |  1.000 | 1.000 |       2 |
| (count or density) and early |     0 |     0.833 |  0.833 | 0.833 |       6 |
| (count or density) and early |     1 |     0.700 |  0.875 | 0.778 |       8 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       2 |
| density and early            |     0 |     0.625 |  0.833 | 0.714 |       6 |
| density and early            |     1 |     0.625 |  0.625 | 0.625 |       8 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       2 |

### `UNFCCC.party.770.0`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.667 | 0.800 |       6 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       8 |
| any-mention-is-relevant      |     2 |     0.167 |  1.000 | 0.286 |       2 |
| mention-count                |     0 |     1.000 |  0.667 | 0.800 |       6 |
| mention-count                |     1 |     0.667 |  0.750 | 0.706 |       8 |
| mention-count                |     2 |     0.333 |  0.500 | 0.400 |       2 |
| mention-density              |     0 |     0.857 |  1.000 | 0.923 |       6 |
| mention-density              |     1 |     0.857 |  0.750 | 0.800 |       8 |
| mention-density              |     2 |     0.500 |  0.500 | 0.500 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.667 | 0.800 |       6 |
| max-mentions-per-page        |     1 |     0.625 |  0.625 | 0.625 |       8 |
| max-mentions-per-page        |     2 |     0.250 |  0.500 | 0.333 |       2 |
| max-section-density          |     0 |     1.000 |  0.667 | 0.800 |       6 |
| max-section-density          |     1 |     0.636 |  0.875 | 0.737 |       8 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  0.667 | 0.800 |       6 |
| earliest-mention             |     1 |     0.667 |  0.750 | 0.706 |       8 |
| earliest-mention             |     2 |     0.333 |  0.500 | 0.400 |       2 |
| earliest-mention-page        |     0 |     0.556 |  0.833 | 0.667 |       6 |
| earliest-mention-page        |     1 |     0.833 |  0.625 | 0.714 |       8 |
| earliest-mention-page        |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-fraction               |     0 |     0.545 |  1.000 | 0.706 |       6 |
| first-fraction               |     1 |     1.000 |  0.375 | 0.545 |       8 |
| first-fraction               |     2 |     0.500 |  0.500 | 0.500 |       2 |
| decay-weighted               |     0 |     0.833 |  0.833 | 0.833 |       6 |
| decay-weighted               |     1 |     0.750 |  0.750 | 0.750 |       8 |
| decay-weighted               |     2 |     0.500 |  0.500 | 0.500 |       2 |
| first-3-pages                |     0 |     1.000 |  0.667 | 0.800 |       6 |
| first-3-pages                |     1 |     0.727 |  1.000 | 0.842 |       8 |
| first-3-pages                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-5-pages                |     0 |     1.000 |  0.667 | 0.800 |       6 |
| first-5-pages                |     1 |     0.727 |  1.000 | 0.842 |       8 |
| first-5-pages                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  0.667 | 0.800 |       6 |
| first-10-pages               |     1 |     0.727 |  1.000 | 0.842 |       8 |
| first-10-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-15-pages               |     0 |     1.000 |  0.667 | 0.800 |       6 |
| first-15-pages               |     1 |     0.727 |  1.000 | 0.842 |       8 |
| first-15-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.667 | 0.800 |       6 |
| first-10-pages-density       |     1 |     0.727 |  1.000 | 0.842 |       8 |
| first-10-pages-density       |     2 |     1.000 |  0.500 | 0.667 |       2 |
| (count or density) and early |     0 |     0.556 |  0.833 | 0.667 |       6 |
| (count or density) and early |     1 |     0.833 |  0.625 | 0.714 |       8 |
| (count or density) and early |     2 |     1.000 |  0.500 | 0.667 |       2 |
| density and early            |     0 |     0.545 |  1.000 | 0.706 |       6 |
| density and early            |     1 |     1.000 |  0.500 | 0.667 |       8 |
| density and early            |     2 |     1.000 |  0.500 | 0.667 |       2 |

### `UNFCCC.party.82.0`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.286 | 0.444 |       7 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       6 |
| any-mention-is-relevant      |     2 |     0.214 |  1.000 | 0.353 |       3 |
| mention-count                |     0 |     1.000 |  0.714 | 0.833 |       7 |
| mention-count                |     1 |     0.714 |  0.833 | 0.769 |       6 |
| mention-count                |     2 |     0.750 |  1.000 | 0.857 |       3 |
| mention-density              |     0 |     0.778 |  1.000 | 0.875 |       7 |
| mention-density              |     1 |     0.800 |  0.667 | 0.727 |       6 |
| mention-density              |     2 |     1.000 |  0.667 | 0.800 |       3 |
| max-mentions-per-page        |     0 |     1.000 |  0.714 | 0.833 |       7 |
| max-mentions-per-page        |     1 |     0.714 |  0.833 | 0.769 |       6 |
| max-mentions-per-page        |     2 |     0.750 |  1.000 | 0.857 |       3 |
| max-section-density          |     0 |     1.000 |  0.429 | 0.600 |       7 |
| max-section-density          |     1 |     0.500 |  0.667 | 0.571 |       6 |
| max-section-density          |     2 |     0.600 |  1.000 | 0.750 |       3 |
| earliest-mention             |     0 |     1.000 |  0.286 | 0.444 |       7 |
| earliest-mention             |     1 |     0.375 |  0.500 | 0.429 |       6 |
| earliest-mention             |     2 |     0.500 |  1.000 | 0.667 |       3 |
| earliest-mention-page        |     0 |     1.000 |  1.000 | 1.000 |       7 |
| earliest-mention-page        |     1 |     1.000 |  0.500 | 0.667 |       6 |
| earliest-mention-page        |     2 |     0.500 |  1.000 | 0.667 |       3 |
| first-fraction               |     0 |     1.000 |  0.857 | 0.923 |       7 |
| first-fraction               |     1 |     1.000 |  0.500 | 0.667 |       6 |
| first-fraction               |     2 |     0.429 |  1.000 | 0.600 |       3 |
| decay-weighted               |     0 |     1.000 |  0.714 | 0.833 |       7 |
| decay-weighted               |     1 |     0.714 |  0.833 | 0.769 |       6 |
| decay-weighted               |     2 |     0.750 |  1.000 | 0.857 |       3 |
| first-3-pages                |     0 |     1.000 |  0.286 | 0.444 |       7 |
| first-3-pages                |     1 |     0.375 |  0.500 | 0.429 |       6 |
| first-3-pages                |     2 |     0.500 |  1.000 | 0.667 |       3 |
| first-5-pages                |     0 |     1.000 |  0.286 | 0.444 |       7 |
| first-5-pages                |     1 |     0.500 |  0.833 | 0.625 |       6 |
| first-5-pages                |     2 |     0.750 |  1.000 | 0.857 |       3 |
| first-10-pages               |     0 |     1.000 |  0.286 | 0.444 |       7 |
| first-10-pages               |     1 |     0.500 |  0.833 | 0.625 |       6 |
| first-10-pages               |     2 |     0.750 |  1.000 | 0.857 |       3 |
| first-15-pages               |     0 |     1.000 |  0.286 | 0.444 |       7 |
| first-15-pages               |     1 |     0.500 |  0.833 | 0.625 |       6 |
| first-15-pages               |     2 |     0.750 |  1.000 | 0.857 |       3 |
| first-10-pages-density       |     0 |     1.000 |  0.286 | 0.444 |       7 |
| first-10-pages-density       |     1 |     0.545 |  1.000 | 0.706 |       6 |
| first-10-pages-density       |     2 |     1.000 |  1.000 | 1.000 |       3 |
| (count or density) and early |     0 |     1.000 |  1.000 | 1.000 |       7 |
| (count or density) and early |     1 |     1.000 |  0.833 | 0.909 |       6 |
| (count or density) and early |     2 |     0.750 |  1.000 | 0.857 |       3 |
| density and early            |     0 |     0.778 |  1.000 | 0.875 |       7 |
| density and early            |     1 |     0.800 |  0.667 | 0.727 |       6 |
| density and early            |     2 |     1.000 |  0.667 | 0.800 |       3 |

## Per-topic breakdowns

### `concept::Q1282`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     0.962 |  0.625 | 0.758 |      40 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       7 |
| any-mention-is-relevant      |     2 |     0.087 |  1.000 | 0.160 |       2 |
| mention-count                |     0 |     0.968 |  0.750 | 0.845 |      40 |
| mention-count                |     1 |     0.333 |  0.857 | 0.480 |       7 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     0.927 |  0.950 | 0.938 |      40 |
| mention-density              |     1 |     0.571 |  0.571 | 0.571 |       7 |
| mention-density              |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-mentions-per-page        |     0 |     0.970 |  0.800 | 0.877 |      40 |
| max-mentions-per-page        |     1 |     0.400 |  0.857 | 0.545 |       7 |
| max-mentions-per-page        |     2 |     1.000 |  0.500 | 0.667 |       2 |
| max-section-density          |     0 |     0.971 |  0.825 | 0.892 |      40 |
| max-section-density          |     1 |     0.400 |  0.857 | 0.545 |       7 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     0.962 |  0.625 | 0.758 |      40 |
| earliest-mention             |     1 |     0.261 |  0.857 | 0.400 |       7 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention-page        |     0 |     0.969 |  0.775 | 0.861 |      40 |
| earliest-mention-page        |     1 |     0.400 |  0.857 | 0.545 |       7 |
| earliest-mention-page        |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-fraction               |     0 |     0.923 |  0.900 | 0.911 |      40 |
| first-fraction               |     1 |     0.444 |  0.571 | 0.500 |       7 |
| first-fraction               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| decay-weighted               |     0 |     0.919 |  0.850 | 0.883 |      40 |
| decay-weighted               |     1 |     0.364 |  0.571 | 0.444 |       7 |
| decay-weighted               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-3-pages                |     0 |     0.962 |  0.625 | 0.758 |      40 |
| first-3-pages                |     1 |     0.286 |  0.857 | 0.429 |       7 |
| first-3-pages                |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-5-pages                |     0 |     0.962 |  0.625 | 0.758 |      40 |
| first-5-pages                |     1 |     0.286 |  0.857 | 0.429 |       7 |
| first-5-pages                |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-10-pages               |     0 |     0.962 |  0.625 | 0.758 |      40 |
| first-10-pages               |     1 |     0.273 |  0.857 | 0.414 |       7 |
| first-10-pages               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-15-pages               |     0 |     0.962 |  0.625 | 0.758 |      40 |
| first-15-pages               |     1 |     0.286 |  0.857 | 0.429 |       7 |
| first-15-pages               |     2 |     1.000 |  1.000 | 1.000 |       2 |
| first-10-pages-density       |     0 |     0.962 |  0.625 | 0.758 |      40 |
| first-10-pages-density       |     1 |     0.273 |  0.857 | 0.414 |       7 |
| first-10-pages-density       |     2 |     1.000 |  0.500 | 0.667 |       2 |
| (count or density) and early |     0 |     0.971 |  0.825 | 0.892 |      40 |
| (count or density) and early |     1 |     0.429 |  0.857 | 0.571 |       7 |
| (count or density) and early |     2 |     1.000 |  0.500 | 0.667 |       2 |
| density and early            |     0 |     0.927 |  0.950 | 0.938 |      40 |
| density and early            |     1 |     0.571 |  0.571 | 0.571 |       7 |
| density and early            |     2 |     1.000 |  0.500 | 0.667 |       2 |

### `concept::Q1346`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     0.978 |  1.000 | 0.989 |      44 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       4 |
| any-mention-is-relevant      |     2 |     0.250 |  1.000 | 0.400 |       1 |
| mention-count                |     0 |     0.936 |  1.000 | 0.967 |      44 |
| mention-count                |     1 |     0.500 |  0.250 | 0.333 |       4 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     0.978 |  1.000 | 0.989 |      44 |
| mention-density              |     1 |     1.000 |  0.500 | 0.667 |       4 |
| mention-density              |     2 |     0.500 |  1.000 | 0.667 |       1 |
| max-mentions-per-page        |     0 |     0.936 |  1.000 | 0.967 |      44 |
| max-mentions-per-page        |     1 |     0.500 |  0.250 | 0.333 |       4 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.957 |  1.000 | 0.978 |      44 |
| max-section-density          |     1 |     0.667 |  0.500 | 0.571 |       4 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     0.957 |  1.000 | 0.978 |      44 |
| earliest-mention             |     1 |     1.000 |  0.500 | 0.667 |       4 |
| earliest-mention             |     2 |     1.000 |  1.000 | 1.000 |       1 |
| earliest-mention-page        |     0 |     0.978 |  1.000 | 0.989 |      44 |
| earliest-mention-page        |     1 |     1.000 |  0.500 | 0.667 |       4 |
| earliest-mention-page        |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-fraction               |     0 |     0.898 |  1.000 | 0.946 |      44 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       4 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.936 |  1.000 | 0.967 |      44 |
| decay-weighted               |     1 |     0.500 |  0.250 | 0.333 |       4 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     0.978 |  1.000 | 0.989 |      44 |
| first-3-pages                |     1 |     1.000 |  0.500 | 0.667 |       4 |
| first-3-pages                |     2 |     0.500 |  1.000 | 0.667 |       1 |
| first-5-pages                |     0 |     0.978 |  1.000 | 0.989 |      44 |
| first-5-pages                |     1 |     1.000 |  0.750 | 0.857 |       4 |
| first-5-pages                |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-10-pages               |     0 |     0.978 |  1.000 | 0.989 |      44 |
| first-10-pages               |     1 |     1.000 |  0.750 | 0.857 |       4 |
| first-10-pages               |     2 |     1.000 |  1.000 | 1.000 |       1 |
| first-15-pages               |     0 |     0.978 |  1.000 | 0.989 |      44 |
| first-15-pages               |     1 |     0.750 |  0.750 | 0.750 |       4 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     0.978 |  1.000 | 0.989 |      44 |
| first-10-pages-density       |     1 |     1.000 |  0.500 | 0.667 |       4 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       1 |
| (count or density) and early |     0 |     0.978 |  1.000 | 0.989 |      44 |
| (count or density) and early |     1 |     1.000 |  0.500 | 0.667 |       4 |
| (count or density) and early |     2 |     0.500 |  1.000 | 0.667 |       1 |
| density and early            |     0 |     0.978 |  1.000 | 0.989 |      44 |
| density and early            |     1 |     1.000 |  0.500 | 0.667 |       4 |
| density and early            |     2 |     0.500 |  1.000 | 0.667 |       1 |

### `concept::Q1652`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.730 | 0.844 |      37 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       8 |
| any-mention-is-relevant      |     2 |     0.182 |  1.000 | 0.308 |       4 |
| mention-count                |     0 |     0.923 |  0.973 | 0.947 |      37 |
| mention-count                |     1 |     0.600 |  0.750 | 0.667 |       8 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       4 |
| mention-density              |     0 |     0.900 |  0.973 | 0.935 |      37 |
| mention-density              |     1 |     0.625 |  0.625 | 0.625 |       8 |
| mention-density              |     2 |     1.000 |  0.250 | 0.400 |       4 |
| max-mentions-per-page        |     0 |     0.895 |  0.919 | 0.907 |      37 |
| max-mentions-per-page        |     1 |     0.455 |  0.625 | 0.526 |       8 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       4 |
| max-section-density          |     0 |     0.917 |  0.892 | 0.904 |      37 |
| max-section-density          |     1 |     0.462 |  0.750 | 0.571 |       8 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       4 |
| earliest-mention             |     0 |     0.966 |  0.757 | 0.848 |      37 |
| earliest-mention             |     1 |     0.412 |  0.875 | 0.560 |       8 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       4 |
| earliest-mention-page        |     0 |     0.935 |  0.784 | 0.853 |      37 |
| earliest-mention-page        |     1 |     0.429 |  0.750 | 0.545 |       8 |
| earliest-mention-page        |     2 |     0.500 |  0.500 | 0.500 |       4 |
| first-fraction               |     0 |     0.837 |  0.973 | 0.900 |      37 |
| first-fraction               |     1 |     0.500 |  0.250 | 0.333 |       8 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       4 |
| decay-weighted               |     0 |     0.878 |  0.973 | 0.923 |      37 |
| decay-weighted               |     1 |     0.500 |  0.500 | 0.500 |       8 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       4 |
| first-3-pages                |     0 |     1.000 |  0.730 | 0.844 |      37 |
| first-3-pages                |     1 |     0.333 |  0.750 | 0.462 |       8 |
| first-3-pages                |     2 |     0.500 |  0.500 | 0.500 |       4 |
| first-5-pages                |     0 |     1.000 |  0.730 | 0.844 |      37 |
| first-5-pages                |     1 |     0.381 |  1.000 | 0.552 |       8 |
| first-5-pages                |     2 |     1.000 |  0.250 | 0.400 |       4 |
| first-10-pages               |     0 |     1.000 |  0.730 | 0.844 |      37 |
| first-10-pages               |     1 |     0.381 |  1.000 | 0.552 |       8 |
| first-10-pages               |     2 |     1.000 |  0.250 | 0.400 |       4 |
| first-15-pages               |     0 |     1.000 |  0.730 | 0.844 |      37 |
| first-15-pages               |     1 |     0.381 |  1.000 | 0.552 |       8 |
| first-15-pages               |     2 |     1.000 |  0.250 | 0.400 |       4 |
| first-10-pages-density       |     0 |     1.000 |  0.730 | 0.844 |      37 |
| first-10-pages-density       |     1 |     0.368 |  0.875 | 0.519 |       8 |
| first-10-pages-density       |     2 |     0.667 |  0.500 | 0.571 |       4 |
| (count or density) and early |     0 |     0.921 |  0.946 | 0.933 |      37 |
| (count or density) and early |     1 |     0.700 |  0.875 | 0.778 |       8 |
| (count or density) and early |     2 |     1.000 |  0.250 | 0.400 |       4 |
| density and early            |     0 |     0.878 |  0.973 | 0.923 |      37 |
| density and early            |     1 |     0.714 |  0.625 | 0.667 |       8 |
| density and early            |     2 |     1.000 |  0.250 | 0.400 |       4 |

### `concept::Q1829`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.400 | 0.571 |      15 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |      19 |
| any-mention-is-relevant      |     2 |     0.349 |  1.000 | 0.517 |      15 |
| mention-count                |     0 |     0.909 |  0.667 | 0.769 |      15 |
| mention-count                |     1 |     0.531 |  0.895 | 0.667 |      19 |
| mention-count                |     2 |     0.500 |  0.200 | 0.286 |      15 |
| mention-density              |     0 |     1.000 |  0.467 | 0.636 |      15 |
| mention-density              |     1 |     0.583 |  0.737 | 0.651 |      19 |
| mention-density              |     2 |     0.611 |  0.733 | 0.667 |      15 |
| max-mentions-per-page        |     0 |     0.750 |  0.600 | 0.667 |      15 |
| max-mentions-per-page        |     1 |     0.519 |  0.737 | 0.609 |      19 |
| max-mentions-per-page        |     2 |     0.600 |  0.400 | 0.480 |      15 |
| max-section-density          |     0 |     0.833 |  0.667 | 0.741 |      15 |
| max-section-density          |     1 |     0.333 |  0.421 | 0.372 |      19 |
| max-section-density          |     2 |     0.231 |  0.200 | 0.214 |      15 |
| earliest-mention             |     0 |     0.900 |  0.600 | 0.720 |      15 |
| earliest-mention             |     1 |     0.522 |  0.632 | 0.571 |      19 |
| earliest-mention             |     2 |     0.438 |  0.467 | 0.452 |      15 |
| earliest-mention-page        |     0 |     1.000 |  0.533 | 0.696 |      15 |
| earliest-mention-page        |     1 |     0.611 |  0.579 | 0.595 |      19 |
| earliest-mention-page        |     2 |     0.522 |  0.800 | 0.632 |      15 |
| first-fraction               |     0 |     0.550 |  0.733 | 0.629 |      15 |
| first-fraction               |     1 |     0.625 |  0.526 | 0.571 |      19 |
| first-fraction               |     2 |     0.538 |  0.467 | 0.500 |      15 |
| decay-weighted               |     0 |     0.647 |  0.733 | 0.688 |      15 |
| decay-weighted               |     1 |     0.560 |  0.737 | 0.636 |      19 |
| decay-weighted               |     2 |     0.429 |  0.200 | 0.273 |      15 |
| first-3-pages                |     0 |     1.000 |  0.400 | 0.571 |      15 |
| first-3-pages                |     1 |     0.550 |  0.579 | 0.564 |      19 |
| first-3-pages                |     2 |     0.522 |  0.800 | 0.632 |      15 |
| first-5-pages                |     0 |     1.000 |  0.400 | 0.571 |      15 |
| first-5-pages                |     1 |     0.565 |  0.684 | 0.619 |      19 |
| first-5-pages                |     2 |     0.600 |  0.800 | 0.686 |      15 |
| first-10-pages               |     0 |     1.000 |  0.400 | 0.571 |      15 |
| first-10-pages               |     1 |     0.524 |  0.579 | 0.550 |      19 |
| first-10-pages               |     2 |     0.591 |  0.867 | 0.703 |      15 |
| first-15-pages               |     0 |     1.000 |  0.400 | 0.571 |      15 |
| first-15-pages               |     1 |     0.458 |  0.579 | 0.512 |      19 |
| first-15-pages               |     2 |     0.526 |  0.667 | 0.588 |      15 |
| first-10-pages-density       |     0 |     1.000 |  0.400 | 0.571 |      15 |
| first-10-pages-density       |     1 |     0.556 |  0.526 | 0.541 |      19 |
| first-10-pages-density       |     2 |     0.560 |  0.933 | 0.700 |      15 |
| (count or density) and early |     0 |     1.000 |  0.533 | 0.696 |      15 |
| (count or density) and early |     1 |     0.600 |  0.789 | 0.682 |      19 |
| (count or density) and early |     2 |     0.625 |  0.667 | 0.645 |      15 |
| density and early            |     0 |     1.000 |  0.533 | 0.696 |      15 |
| density and early            |     1 |     0.593 |  0.842 | 0.696 |      19 |
| density and early            |     2 |     0.643 |  0.600 | 0.621 |      15 |

### `concept::Q1832`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.636 | 0.778 |      33 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |      14 |
| any-mention-is-relevant      |     2 |     0.071 |  1.000 | 0.133 |       2 |
| mention-count                |     0 |     0.962 |  0.758 | 0.847 |      33 |
| mention-count                |     1 |     0.565 |  0.929 | 0.703 |      14 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       2 |
| mention-density              |     0 |     0.963 |  0.788 | 0.867 |      33 |
| mention-density              |     1 |     0.632 |  0.857 | 0.727 |      14 |
| mention-density              |     2 |     0.667 |  1.000 | 0.800 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.758 | 0.862 |      33 |
| max-mentions-per-page        |     1 |     0.591 |  0.929 | 0.722 |      14 |
| max-mentions-per-page        |     2 |     0.500 |  0.500 | 0.500 |       2 |
| max-section-density          |     0 |     0.962 |  0.758 | 0.847 |      33 |
| max-section-density          |     1 |     0.600 |  0.857 | 0.706 |      14 |
| max-section-density          |     2 |     0.333 |  0.500 | 0.400 |       2 |
| earliest-mention             |     0 |     1.000 |  0.697 | 0.821 |      33 |
| earliest-mention             |     1 |     0.571 |  0.857 | 0.686 |      14 |
| earliest-mention             |     2 |     0.400 |  1.000 | 0.571 |       2 |
| earliest-mention-page        |     0 |     0.920 |  0.697 | 0.793 |      33 |
| earliest-mention-page        |     1 |     0.529 |  0.643 | 0.581 |      14 |
| earliest-mention-page        |     2 |     0.286 |  1.000 | 0.444 |       2 |
| first-fraction               |     0 |     0.848 |  0.848 | 0.848 |      33 |
| first-fraction               |     1 |     0.583 |  0.500 | 0.538 |      14 |
| first-fraction               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| decay-weighted               |     0 |     0.931 |  0.818 | 0.871 |      33 |
| decay-weighted               |     1 |     0.600 |  0.857 | 0.706 |      14 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-3-pages                |     0 |     1.000 |  0.636 | 0.778 |      33 |
| first-3-pages                |     1 |     0.524 |  0.786 | 0.629 |      14 |
| first-3-pages                |     2 |     0.286 |  1.000 | 0.444 |       2 |
| first-5-pages                |     0 |     1.000 |  0.636 | 0.778 |      33 |
| first-5-pages                |     1 |     0.542 |  0.929 | 0.684 |      14 |
| first-5-pages                |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  0.636 | 0.778 |      33 |
| first-10-pages               |     1 |     0.542 |  0.929 | 0.684 |      14 |
| first-10-pages               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-15-pages               |     0 |     1.000 |  0.636 | 0.778 |      33 |
| first-15-pages               |     1 |     0.500 |  0.857 | 0.632 |      14 |
| first-15-pages               |     2 |     0.500 |  1.000 | 0.667 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.636 | 0.778 |      33 |
| first-10-pages-density       |     1 |     0.565 |  0.929 | 0.703 |      14 |
| first-10-pages-density       |     2 |     0.400 |  1.000 | 0.571 |       2 |
| (count or density) and early |     0 |     0.897 |  0.788 | 0.839 |      33 |
| (count or density) and early |     1 |     0.588 |  0.714 | 0.645 |      14 |
| (count or density) and early |     2 |     0.667 |  1.000 | 0.800 |       2 |
| density and early            |     0 |     0.900 |  0.818 | 0.857 |      33 |
| density and early            |     1 |     0.625 |  0.714 | 0.667 |      14 |
| density and early            |     2 |     0.667 |  1.000 | 0.800 |       2 |

### `concept::Q218`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.462 | 0.632 |      26 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       9 |
| any-mention-is-relevant      |     2 |     0.378 |  1.000 | 0.549 |      14 |
| mention-count                |     0 |     0.955 |  0.808 | 0.875 |      26 |
| mention-count                |     1 |     0.533 |  0.889 | 0.667 |       9 |
| mention-count                |     2 |     1.000 |  0.857 | 0.923 |      14 |
| mention-density              |     0 |     1.000 |  0.577 | 0.732 |      26 |
| mention-density              |     1 |     0.389 |  0.778 | 0.519 |       9 |
| mention-density              |     2 |     0.688 |  0.786 | 0.733 |      14 |
| max-mentions-per-page        |     0 |     0.955 |  0.808 | 0.875 |      26 |
| max-mentions-per-page        |     1 |     0.467 |  0.778 | 0.583 |       9 |
| max-mentions-per-page        |     2 |     0.917 |  0.786 | 0.846 |      14 |
| max-section-density          |     0 |     0.895 |  0.654 | 0.756 |      26 |
| max-section-density          |     1 |     0.381 |  0.889 | 0.533 |       9 |
| max-section-density          |     2 |     1.000 |  0.643 | 0.783 |      14 |
| earliest-mention             |     0 |     0.933 |  0.538 | 0.683 |      26 |
| earliest-mention             |     1 |     0.304 |  0.778 | 0.438 |       9 |
| earliest-mention             |     2 |     0.909 |  0.714 | 0.800 |      14 |
| earliest-mention-page        |     0 |     1.000 |  0.462 | 0.632 |      26 |
| earliest-mention-page        |     1 |     0.250 |  0.556 | 0.345 |       9 |
| earliest-mention-page        |     2 |     0.471 |  0.571 | 0.516 |      14 |
| first-fraction               |     0 |     0.875 |  0.808 | 0.840 |      26 |
| first-fraction               |     1 |     0.417 |  0.556 | 0.476 |       9 |
| first-fraction               |     2 |     0.923 |  0.857 | 0.889 |      14 |
| decay-weighted               |     0 |     0.913 |  0.808 | 0.857 |      26 |
| decay-weighted               |     1 |     0.462 |  0.667 | 0.545 |       9 |
| decay-weighted               |     2 |     0.923 |  0.857 | 0.889 |      14 |
| first-3-pages                |     0 |     1.000 |  0.462 | 0.632 |      26 |
| first-3-pages                |     1 |     0.250 |  0.556 | 0.345 |       9 |
| first-3-pages                |     2 |     0.471 |  0.571 | 0.516 |      14 |
| first-5-pages                |     0 |     1.000 |  0.462 | 0.632 |      26 |
| first-5-pages                |     1 |     0.261 |  0.667 | 0.375 |       9 |
| first-5-pages                |     2 |     0.643 |  0.643 | 0.643 |      14 |
| first-10-pages               |     0 |     1.000 |  0.462 | 0.632 |      26 |
| first-10-pages               |     1 |     0.273 |  0.667 | 0.387 |       9 |
| first-10-pages               |     2 |     0.733 |  0.786 | 0.759 |      14 |
| first-15-pages               |     0 |     1.000 |  0.462 | 0.632 |      26 |
| first-15-pages               |     1 |     0.292 |  0.778 | 0.424 |       9 |
| first-15-pages               |     2 |     0.846 |  0.786 | 0.815 |      14 |
| first-10-pages-density       |     0 |     1.000 |  0.462 | 0.632 |      26 |
| first-10-pages-density       |     1 |     0.294 |  0.556 | 0.385 |       9 |
| first-10-pages-density       |     2 |     0.600 |  0.857 | 0.706 |      14 |
| (count or density) and early |     0 |     1.000 |  0.577 | 0.732 |      26 |
| (count or density) and early |     1 |     0.318 |  0.778 | 0.452 |       9 |
| (count or density) and early |     2 |     0.583 |  0.500 | 0.538 |      14 |
| density and early            |     0 |     1.000 |  0.577 | 0.732 |      26 |
| density and early            |     1 |     0.304 |  0.778 | 0.438 |       9 |
| density and early            |     2 |     0.545 |  0.429 | 0.480 |      14 |

### `concept::Q226`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.846 | 0.917 |      39 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       8 |
| any-mention-is-relevant      |     2 |     0.125 |  1.000 | 0.222 |       2 |
| mention-count                |     0 |     1.000 |  0.974 | 0.987 |      39 |
| mention-count                |     1 |     0.778 |  0.875 | 0.824 |       8 |
| mention-count                |     2 |     0.500 |  0.500 | 0.500 |       2 |
| mention-density              |     0 |     1.000 |  0.974 | 0.987 |      39 |
| mention-density              |     1 |     0.727 |  1.000 | 0.842 |       8 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       2 |
| max-mentions-per-page        |     0 |     1.000 |  0.974 | 0.987 |      39 |
| max-mentions-per-page        |     1 |     0.667 |  0.500 | 0.571 |       8 |
| max-mentions-per-page        |     2 |     0.200 |  0.500 | 0.286 |       2 |
| max-section-density          |     0 |     1.000 |  0.974 | 0.987 |      39 |
| max-section-density          |     1 |     0.800 |  0.500 | 0.615 |       8 |
| max-section-density          |     2 |     0.333 |  1.000 | 0.500 |       2 |
| earliest-mention             |     0 |     1.000 |  0.872 | 0.932 |      39 |
| earliest-mention             |     1 |     0.444 |  0.500 | 0.471 |       8 |
| earliest-mention             |     2 |     0.333 |  1.000 | 0.500 |       2 |
| earliest-mention-page        |     0 |     0.947 |  0.923 | 0.935 |      39 |
| earliest-mention-page        |     1 |     0.429 |  0.375 | 0.400 |       8 |
| earliest-mention-page        |     2 |     0.250 |  0.500 | 0.333 |       2 |
| first-fraction               |     0 |     0.950 |  0.974 | 0.962 |      39 |
| first-fraction               |     1 |     0.667 |  0.500 | 0.571 |       8 |
| first-fraction               |     2 |     0.333 |  0.500 | 0.400 |       2 |
| decay-weighted               |     0 |     1.000 |  0.974 | 0.987 |      39 |
| decay-weighted               |     1 |     0.800 |  1.000 | 0.889 |       8 |
| decay-weighted               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-3-pages                |     0 |     1.000 |  0.846 | 0.917 |      39 |
| first-3-pages                |     1 |     0.417 |  0.625 | 0.500 |       8 |
| first-3-pages                |     2 |     0.250 |  0.500 | 0.333 |       2 |
| first-5-pages                |     0 |     1.000 |  0.846 | 0.917 |      39 |
| first-5-pages                |     1 |     0.533 |  1.000 | 0.696 |       8 |
| first-5-pages                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-10-pages               |     0 |     1.000 |  0.846 | 0.917 |      39 |
| first-10-pages               |     1 |     0.500 |  0.875 | 0.636 |       8 |
| first-10-pages               |     2 |     0.500 |  0.500 | 0.500 |       2 |
| first-15-pages               |     0 |     1.000 |  0.846 | 0.917 |      39 |
| first-15-pages               |     1 |     0.467 |  0.875 | 0.609 |       8 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.846 | 0.917 |      39 |
| first-10-pages-density       |     1 |     0.500 |  0.875 | 0.636 |       8 |
| first-10-pages-density       |     2 |     0.500 |  0.500 | 0.500 |       2 |
| (count or density) and early |     0 |     0.950 |  0.974 | 0.962 |      39 |
| (count or density) and early |     1 |     0.667 |  0.750 | 0.706 |       8 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       2 |
| density and early            |     0 |     0.950 |  0.974 | 0.962 |      39 |
| density and early            |     1 |     0.667 |  0.750 | 0.706 |       8 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       2 |

### `concept::Q557`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.333 | 0.500 |      21 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |      10 |
| any-mention-is-relevant      |     2 |     0.429 |  1.000 | 0.600 |      18 |
| mention-count                |     0 |     0.923 |  0.571 | 0.706 |      21 |
| mention-count                |     1 |     0.321 |  0.900 | 0.474 |      10 |
| mention-count                |     2 |     0.875 |  0.389 | 0.538 |      18 |
| mention-density              |     0 |     1.000 |  0.333 | 0.500 |      21 |
| mention-density              |     1 |     0.292 |  0.700 | 0.412 |      10 |
| mention-density              |     2 |     0.722 |  0.722 | 0.722 |      18 |
| max-mentions-per-page        |     0 |     0.917 |  0.524 | 0.667 |      21 |
| max-mentions-per-page        |     1 |     0.250 |  0.500 | 0.333 |      10 |
| max-mentions-per-page        |     2 |     0.706 |  0.667 | 0.686 |      18 |
| max-section-density          |     0 |     0.812 |  0.619 | 0.703 |      21 |
| max-section-density          |     1 |     0.250 |  0.600 | 0.353 |      10 |
| max-section-density          |     2 |     0.667 |  0.333 | 0.444 |      18 |
| earliest-mention             |     0 |     1.000 |  0.429 | 0.600 |      21 |
| earliest-mention             |     1 |     0.308 |  0.800 | 0.444 |      10 |
| earliest-mention             |     2 |     0.714 |  0.556 | 0.625 |      18 |
| earliest-mention-page        |     0 |     0.900 |  0.429 | 0.581 |      21 |
| earliest-mention-page        |     1 |     0.400 |  0.600 | 0.480 |      10 |
| earliest-mention-page        |     2 |     0.625 |  0.833 | 0.714 |      18 |
| first-fraction               |     0 |     0.667 |  0.667 | 0.667 |      21 |
| first-fraction               |     1 |     0.308 |  0.400 | 0.348 |      10 |
| first-fraction               |     2 |     0.800 |  0.667 | 0.727 |      18 |
| decay-weighted               |     0 |     0.800 |  0.571 | 0.667 |      21 |
| decay-weighted               |     1 |     0.346 |  0.900 | 0.500 |      10 |
| decay-weighted               |     2 |     1.000 |  0.444 | 0.615 |      18 |
| first-3-pages                |     0 |     1.000 |  0.333 | 0.500 |      21 |
| first-3-pages                |     1 |     0.389 |  0.700 | 0.500 |      10 |
| first-3-pages                |     2 |     0.625 |  0.833 | 0.714 |      18 |
| first-5-pages                |     0 |     1.000 |  0.333 | 0.500 |      21 |
| first-5-pages                |     1 |     0.261 |  0.600 | 0.364 |      10 |
| first-5-pages                |     2 |     0.684 |  0.722 | 0.703 |      18 |
| first-10-pages               |     0 |     1.000 |  0.333 | 0.500 |      21 |
| first-10-pages               |     1 |     0.269 |  0.700 | 0.389 |      10 |
| first-10-pages               |     2 |     0.750 |  0.667 | 0.706 |      18 |
| first-15-pages               |     0 |     1.000 |  0.333 | 0.500 |      21 |
| first-15-pages               |     1 |     0.333 |  0.800 | 0.471 |      10 |
| first-15-pages               |     2 |     0.778 |  0.778 | 0.778 |      18 |
| first-10-pages-density       |     0 |     1.000 |  0.333 | 0.500 |      21 |
| first-10-pages-density       |     1 |     0.353 |  0.600 | 0.444 |      10 |
| first-10-pages-density       |     2 |     0.600 |  0.833 | 0.698 |      18 |
| (count or density) and early |     0 |     0.900 |  0.429 | 0.581 |      21 |
| (count or density) and early |     1 |     0.280 |  0.700 | 0.400 |      10 |
| (count or density) and early |     2 |     0.786 |  0.611 | 0.688 |      18 |
| density and early            |     0 |     0.900 |  0.429 | 0.581 |      21 |
| density and early            |     1 |     0.269 |  0.700 | 0.389 |      10 |
| density and early            |     2 |     0.769 |  0.556 | 0.645 |      18 |

### `concept::Q567`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.440 | 0.611 |      25 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |      15 |
| any-mention-is-relevant      |     2 |     0.237 |  1.000 | 0.383 |       9 |
| mention-count                |     0 |     0.950 |  0.760 | 0.844 |      25 |
| mention-count                |     1 |     0.520 |  0.867 | 0.650 |      15 |
| mention-count                |     2 |     0.750 |  0.333 | 0.462 |       9 |
| mention-density              |     0 |     1.000 |  0.600 | 0.750 |      25 |
| mention-density              |     1 |     0.500 |  1.000 | 0.667 |      15 |
| mention-density              |     2 |     1.000 |  0.444 | 0.615 |       9 |
| max-mentions-per-page        |     0 |     0.947 |  0.720 | 0.818 |      25 |
| max-mentions-per-page        |     1 |     0.474 |  0.600 | 0.529 |      15 |
| max-mentions-per-page        |     2 |     0.545 |  0.667 | 0.600 |       9 |
| max-section-density          |     0 |     0.889 |  0.640 | 0.744 |      25 |
| max-section-density          |     1 |     0.480 |  0.800 | 0.600 |      15 |
| max-section-density          |     2 |     0.667 |  0.444 | 0.533 |       9 |
| earliest-mention             |     0 |     0.917 |  0.440 | 0.595 |      25 |
| earliest-mention             |     1 |     0.367 |  0.733 | 0.489 |      15 |
| earliest-mention             |     2 |     0.429 |  0.333 | 0.375 |       9 |
| earliest-mention-page        |     0 |     0.923 |  0.480 | 0.632 |      25 |
| earliest-mention-page        |     1 |     0.423 |  0.733 | 0.537 |      15 |
| earliest-mention-page        |     2 |     0.500 |  0.556 | 0.526 |       9 |
| first-fraction               |     0 |     0.852 |  0.920 | 0.885 |      25 |
| first-fraction               |     1 |     0.333 |  0.200 | 0.250 |      15 |
| first-fraction               |     2 |     0.385 |  0.556 | 0.455 |       9 |
| decay-weighted               |     0 |     0.864 |  0.760 | 0.809 |      25 |
| decay-weighted               |     1 |     0.500 |  0.800 | 0.615 |      15 |
| decay-weighted               |     2 |     1.000 |  0.333 | 0.500 |       9 |
| first-3-pages                |     0 |     1.000 |  0.440 | 0.611 |      25 |
| first-3-pages                |     1 |     0.429 |  0.800 | 0.558 |      15 |
| first-3-pages                |     2 |     0.500 |  0.556 | 0.526 |       9 |
| first-5-pages                |     0 |     1.000 |  0.440 | 0.611 |      25 |
| first-5-pages                |     1 |     0.407 |  0.733 | 0.524 |      15 |
| first-5-pages                |     2 |     0.545 |  0.667 | 0.600 |       9 |
| first-10-pages               |     0 |     1.000 |  0.440 | 0.611 |      25 |
| first-10-pages               |     1 |     0.500 |  1.000 | 0.667 |      15 |
| first-10-pages               |     2 |     0.750 |  0.667 | 0.706 |       9 |
| first-15-pages               |     0 |     1.000 |  0.440 | 0.611 |      25 |
| first-15-pages               |     1 |     0.438 |  0.933 | 0.596 |      15 |
| first-15-pages               |     2 |     0.833 |  0.556 | 0.667 |       9 |
| first-10-pages-density       |     0 |     1.000 |  0.440 | 0.611 |      25 |
| first-10-pages-density       |     1 |     0.542 |  0.867 | 0.667 |      15 |
| first-10-pages-density       |     2 |     0.571 |  0.889 | 0.696 |       9 |
| (count or density) and early |     0 |     0.933 |  0.560 | 0.700 |      25 |
| (count or density) and early |     1 |     0.467 |  0.933 | 0.622 |      15 |
| (count or density) and early |     2 |     1.000 |  0.444 | 0.615 |       9 |
| density and early            |     0 |     0.938 |  0.600 | 0.732 |      25 |
| density and early            |     1 |     0.467 |  0.933 | 0.622 |      15 |
| density and early            |     2 |     1.000 |  0.333 | 0.500 |       9 |

### `concept::Q615`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.857 | 0.923 |      49 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       0 |
| any-mention-is-relevant      |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     0 |     1.000 |  0.939 | 0.968 |      49 |
| mention-count                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     0 |     1.000 |  0.980 | 0.990 |      49 |
| mention-density              |     1 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     0 |     1.000 |  0.918 | 0.957 |      49 |
| max-mentions-per-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     0 |     1.000 |  0.959 | 0.979 |      49 |
| max-section-density          |     1 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     0 |     1.000 |  0.898 | 0.946 |      49 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     0 |     1.000 |  0.959 | 0.979 |      49 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     0 |     1.000 |  0.980 | 0.990 |      49 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     0 |     1.000 |  0.959 | 0.979 |      49 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     0 |     1.000 |  0.857 | 0.923 |      49 |
| first-3-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     0 |     1.000 |  0.857 | 0.923 |      49 |
| first-5-pages                |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     0 |     1.000 |  0.857 | 0.923 |      49 |
| first-10-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     0 |     1.000 |  0.857 | 0.923 |      49 |
| first-15-pages               |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     0 |     1.000 |  0.857 | 0.923 |      49 |
| first-10-pages-density       |     1 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     0 |     1.000 |  0.980 | 0.990 |      49 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     0 |     1.000 |  0.980 | 0.990 |      49 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `concept::Q69`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.783 | 0.878 |      46 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       2 |
| any-mention-is-relevant      |     2 |     0.077 |  1.000 | 0.143 |       1 |
| mention-count                |     0 |     0.977 |  0.935 | 0.956 |      46 |
| mention-count                |     1 |     0.200 |  0.500 | 0.286 |       2 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     0.978 |  0.978 | 0.978 |      46 |
| mention-density              |     1 |     0.333 |  0.500 | 0.400 |       2 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.913 | 0.955 |      46 |
| max-mentions-per-page        |     1 |     0.286 |  1.000 | 0.444 |       2 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.976 |  0.870 | 0.920 |      46 |
| max-section-density          |     1 |     0.125 |  0.500 | 0.200 |       2 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     0.927 |  0.826 | 0.874 |      46 |
| earliest-mention             |     1 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     0.933 |  0.913 | 0.923 |      46 |
| earliest-mention-page        |     1 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     0 |     0.938 |  0.978 | 0.957 |      46 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       2 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.938 |  0.978 | 0.957 |      46 |
| decay-weighted               |     1 |     0.000 |  0.000 | 0.000 |       2 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.783 | 0.878 |      46 |
| first-3-pages                |     1 |     0.167 |  1.000 | 0.286 |       2 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     0 |     1.000 |  0.783 | 0.878 |      46 |
| first-5-pages                |     1 |     0.154 |  1.000 | 0.267 |       2 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.783 | 0.878 |      46 |
| first-10-pages               |     1 |     0.154 |  1.000 | 0.267 |       2 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.783 | 0.878 |      46 |
| first-15-pages               |     1 |     0.154 |  1.000 | 0.267 |       2 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.783 | 0.878 |      46 |
| first-10-pages-density       |     1 |     0.154 |  1.000 | 0.267 |       2 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     0 |     0.936 |  0.957 | 0.946 |      46 |
| (count or density) and early |     1 |     0.000 |  0.000 | 0.000 |       2 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     0.938 |  0.978 | 0.957 |      46 |
| density and early            |     1 |     0.000 |  0.000 | 0.000 |       2 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `concept::Q701`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.778 | 0.875 |      45 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.071 |  1.000 | 0.133 |       1 |
| mention-count                |     0 |     0.977 |  0.933 | 0.955 |      45 |
| mention-count                |     1 |     0.500 |  1.000 | 0.667 |       3 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     0.978 |  1.000 | 0.989 |      45 |
| mention-density              |     1 |     0.667 |  0.667 | 0.667 |       3 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     0.977 |  0.933 | 0.955 |      45 |
| max-mentions-per-page        |     1 |     0.500 |  1.000 | 0.667 |       3 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.976 |  0.889 | 0.930 |      45 |
| max-section-density          |     1 |     0.375 |  1.000 | 0.545 |       3 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.844 | 0.916 |      45 |
| earliest-mention             |     1 |     0.300 |  1.000 | 0.462 |       3 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     1.000 |  0.911 | 0.953 |      45 |
| earliest-mention-page        |     1 |     0.500 |  1.000 | 0.667 |       3 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     0 |     0.935 |  0.956 | 0.945 |      45 |
| first-fraction               |     1 |     0.333 |  0.333 | 0.333 |       3 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     0.935 |  0.956 | 0.945 |      45 |
| decay-weighted               |     1 |     0.333 |  0.333 | 0.333 |       3 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.778 | 0.875 |      45 |
| first-3-pages                |     1 |     0.250 |  1.000 | 0.400 |       3 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     0 |     1.000 |  0.778 | 0.875 |      45 |
| first-5-pages                |     1 |     0.214 |  1.000 | 0.353 |       3 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.778 | 0.875 |      45 |
| first-10-pages               |     1 |     0.214 |  1.000 | 0.353 |       3 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.778 | 0.875 |      45 |
| first-15-pages               |     1 |     0.214 |  1.000 | 0.353 |       3 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.778 | 0.875 |      45 |
| first-10-pages-density       |     1 |     0.214 |  1.000 | 0.353 |       3 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       1 |
| (count or density) and early |     0 |     1.000 |  0.956 | 0.977 |      45 |
| (count or density) and early |     1 |     0.500 |  1.000 | 0.667 |       3 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     0.978 |  1.000 | 0.989 |      45 |
| density and early            |     1 |     0.667 |  0.667 | 0.667 |       3 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |

### `concept::Q704`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.618 | 0.764 |      34 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |      14 |
| any-mention-is-relevant      |     2 |     0.036 |  1.000 | 0.069 |       1 |
| mention-count                |     0 |     1.000 |  0.824 | 0.903 |      34 |
| mention-count                |     1 |     0.647 |  0.786 | 0.710 |      14 |
| mention-count                |     2 |     0.250 |  1.000 | 0.400 |       1 |
| mention-density              |     0 |     1.000 |  0.794 | 0.885 |      34 |
| mention-density              |     1 |     0.500 |  0.500 | 0.500 |      14 |
| mention-density              |     2 |     0.125 |  1.000 | 0.222 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  0.824 | 0.903 |      34 |
| max-mentions-per-page        |     1 |     0.455 |  0.357 | 0.400 |      14 |
| max-mentions-per-page        |     2 |     0.100 |  1.000 | 0.182 |       1 |
| max-section-density          |     0 |     0.967 |  0.853 | 0.906 |      34 |
| max-section-density          |     1 |     0.615 |  0.571 | 0.593 |      14 |
| max-section-density          |     2 |     0.167 |  1.000 | 0.286 |       1 |
| earliest-mention             |     0 |     1.000 |  0.647 | 0.786 |      34 |
| earliest-mention             |     1 |     0.429 |  0.643 | 0.514 |      14 |
| earliest-mention             |     2 |     0.167 |  1.000 | 0.286 |       1 |
| earliest-mention-page        |     0 |     0.929 |  0.765 | 0.839 |      34 |
| earliest-mention-page        |     1 |     0.385 |  0.357 | 0.370 |      14 |
| earliest-mention-page        |     2 |     0.125 |  1.000 | 0.222 |       1 |
| first-fraction               |     0 |     0.941 |  0.941 | 0.941 |      34 |
| first-fraction               |     1 |     0.778 |  0.500 | 0.609 |      14 |
| first-fraction               |     2 |     0.167 |  1.000 | 0.286 |       1 |
| decay-weighted               |     0 |     1.000 |  0.882 | 0.938 |      34 |
| decay-weighted               |     1 |     0.688 |  0.786 | 0.733 |      14 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.618 | 0.764 |      34 |
| first-3-pages                |     1 |     0.350 |  0.500 | 0.412 |      14 |
| first-3-pages                |     2 |     0.125 |  1.000 | 0.222 |       1 |
| first-5-pages                |     0 |     1.000 |  0.618 | 0.764 |      34 |
| first-5-pages                |     1 |     0.381 |  0.571 | 0.457 |      14 |
| first-5-pages                |     2 |     0.143 |  1.000 | 0.250 |       1 |
| first-10-pages               |     0 |     1.000 |  0.618 | 0.764 |      34 |
| first-10-pages               |     1 |     0.381 |  0.571 | 0.457 |      14 |
| first-10-pages               |     2 |     0.143 |  1.000 | 0.250 |       1 |
| first-15-pages               |     0 |     1.000 |  0.618 | 0.764 |      34 |
| first-15-pages               |     1 |     0.316 |  0.429 | 0.364 |      14 |
| first-15-pages               |     2 |     0.111 |  1.000 | 0.200 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.618 | 0.764 |      34 |
| first-10-pages-density       |     1 |     0.381 |  0.571 | 0.457 |      14 |
| first-10-pages-density       |     2 |     0.143 |  1.000 | 0.250 |       1 |
| (count or density) and early |     0 |     0.931 |  0.794 | 0.857 |      34 |
| (count or density) and early |     1 |     0.462 |  0.429 | 0.444 |      14 |
| (count or density) and early |     2 |     0.143 |  1.000 | 0.250 |       1 |
| density and early            |     0 |     0.933 |  0.824 | 0.875 |      34 |
| density and early            |     1 |     0.500 |  0.429 | 0.462 |      14 |
| density and early            |     2 |     0.143 |  1.000 | 0.250 |       1 |

### `concept::Q715`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.462 | 0.632 |      39 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       8 |
| any-mention-is-relevant      |     2 |     0.065 |  1.000 | 0.121 |       2 |
| mention-count                |     0 |     0.969 |  0.795 | 0.873 |      39 |
| mention-count                |     1 |     0.438 |  0.875 | 0.583 |       8 |
| mention-count                |     2 |     1.000 |  0.500 | 0.667 |       2 |
| mention-density              |     0 |     1.000 |  0.821 | 0.901 |      39 |
| mention-density              |     1 |     0.500 |  0.875 | 0.636 |       8 |
| mention-density              |     2 |     0.333 |  0.500 | 0.400 |       2 |
| max-mentions-per-page        |     0 |     0.968 |  0.769 | 0.857 |      39 |
| max-mentions-per-page        |     1 |     0.308 |  0.500 | 0.381 |       8 |
| max-mentions-per-page        |     2 |     0.200 |  0.500 | 0.286 |       2 |
| max-section-density          |     0 |     0.967 |  0.744 | 0.841 |      39 |
| max-section-density          |     1 |     0.333 |  0.750 | 0.462 |       8 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       2 |
| earliest-mention             |     0 |     1.000 |  0.615 | 0.762 |      39 |
| earliest-mention             |     1 |     0.304 |  0.875 | 0.452 |       8 |
| earliest-mention             |     2 |     0.500 |  0.500 | 0.500 |       2 |
| earliest-mention-page        |     0 |     1.000 |  0.718 | 0.836 |      39 |
| earliest-mention-page        |     1 |     0.333 |  0.750 | 0.462 |       8 |
| earliest-mention-page        |     2 |     0.333 |  0.500 | 0.400 |       2 |
| first-fraction               |     0 |     0.946 |  0.897 | 0.921 |      39 |
| first-fraction               |     1 |     0.571 |  0.500 | 0.533 |       8 |
| first-fraction               |     2 |     0.200 |  0.500 | 0.286 |       2 |
| decay-weighted               |     0 |     0.944 |  0.872 | 0.907 |      39 |
| decay-weighted               |     1 |     0.500 |  0.750 | 0.600 |       8 |
| decay-weighted               |     2 |     1.000 |  0.500 | 0.667 |       2 |
| first-3-pages                |     0 |     1.000 |  0.462 | 0.632 |      39 |
| first-3-pages                |     1 |     0.214 |  0.750 | 0.333 |       8 |
| first-3-pages                |     2 |     0.333 |  0.500 | 0.400 |       2 |
| first-5-pages                |     0 |     1.000 |  0.462 | 0.632 |      39 |
| first-5-pages                |     1 |     0.241 |  0.875 | 0.378 |       8 |
| first-5-pages                |     2 |     0.500 |  0.500 | 0.500 |       2 |
| first-10-pages               |     0 |     1.000 |  0.462 | 0.632 |      39 |
| first-10-pages               |     1 |     0.241 |  0.875 | 0.378 |       8 |
| first-10-pages               |     2 |     0.500 |  0.500 | 0.500 |       2 |
| first-15-pages               |     0 |     1.000 |  0.462 | 0.632 |      39 |
| first-15-pages               |     1 |     0.185 |  0.625 | 0.286 |       8 |
| first-15-pages               |     2 |     0.250 |  0.500 | 0.333 |       2 |
| first-10-pages-density       |     0 |     1.000 |  0.462 | 0.632 |      39 |
| first-10-pages-density       |     1 |     0.222 |  0.750 | 0.343 |       8 |
| first-10-pages-density       |     2 |     0.500 |  1.000 | 0.667 |       2 |
| (count or density) and early |     0 |     1.000 |  0.846 | 0.917 |      39 |
| (count or density) and early |     1 |     0.467 |  0.875 | 0.609 |       8 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       2 |
| density and early            |     0 |     1.000 |  0.846 | 0.917 |      39 |
| density and early            |     1 |     0.467 |  0.875 | 0.609 |       8 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       2 |

### `concept::Q979`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.773 | 0.872 |      44 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       5 |
| any-mention-is-relevant      |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-count                |     0 |     1.000 |  0.909 | 0.952 |      44 |
| mention-count                |     1 |     0.556 |  1.000 | 0.714 |       5 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| mention-density              |     0 |     0.933 |  0.955 | 0.944 |      44 |
| mention-density              |     1 |     0.500 |  0.400 | 0.444 |       5 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-mentions-per-page        |     0 |     1.000 |  0.909 | 0.952 |      44 |
| max-mentions-per-page        |     1 |     0.500 |  0.800 | 0.615 |       5 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| max-section-density          |     0 |     0.975 |  0.886 | 0.929 |      44 |
| max-section-density          |     1 |     0.444 |  0.800 | 0.571 |       5 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention             |     0 |     1.000 |  0.818 | 0.900 |      44 |
| earliest-mention             |     1 |     0.333 |  0.800 | 0.471 |       5 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       0 |
| earliest-mention-page        |     0 |     1.000 |  0.886 | 0.940 |      44 |
| earliest-mention-page        |     1 |     0.500 |  1.000 | 0.667 |       5 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-fraction               |     0 |     1.000 |  0.932 | 0.965 |      44 |
| first-fraction               |     1 |     0.571 |  0.800 | 0.667 |       5 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| decay-weighted               |     0 |     1.000 |  0.932 | 0.965 |      44 |
| decay-weighted               |     1 |     0.625 |  1.000 | 0.769 |       5 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-3-pages                |     0 |     1.000 |  0.773 | 0.872 |      44 |
| first-3-pages                |     1 |     0.333 |  1.000 | 0.500 |       5 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-5-pages                |     0 |     1.000 |  0.773 | 0.872 |      44 |
| first-5-pages                |     1 |     0.333 |  1.000 | 0.500 |       5 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages               |     0 |     1.000 |  0.773 | 0.872 |      44 |
| first-10-pages               |     1 |     0.333 |  1.000 | 0.500 |       5 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-15-pages               |     0 |     1.000 |  0.773 | 0.872 |      44 |
| first-15-pages               |     1 |     0.333 |  1.000 | 0.500 |       5 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       0 |
| first-10-pages-density       |     0 |     1.000 |  0.773 | 0.872 |      44 |
| first-10-pages-density       |     1 |     0.357 |  1.000 | 0.526 |       5 |
| first-10-pages-density       |     2 |     0.000 |  0.000 | 0.000 |       0 |
| (count or density) and early |     0 |     1.000 |  0.909 | 0.952 |      44 |
| (count or density) and early |     1 |     0.556 |  1.000 | 0.714 |       5 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       0 |
| density and early            |     0 |     0.933 |  0.955 | 0.944 |      44 |
| density and early            |     1 |     0.500 |  0.400 | 0.444 |       5 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       0 |

### `concept::Q983`

| Predictor                    | Class | Precision | Recall |    F1 | Support |
| ---------------------------- | ----: | --------: | -----: | ----: | ------: |
| any-mention-is-relevant      |     0 |     1.000 |  0.889 | 0.941 |      45 |
| any-mention-is-relevant      |     1 |     0.000 |  0.000 | 0.000 |       3 |
| any-mention-is-relevant      |     2 |     0.111 |  1.000 | 0.200 |       1 |
| mention-count                |     0 |     1.000 |  1.000 | 1.000 |      45 |
| mention-count                |     1 |     0.750 |  1.000 | 0.857 |       3 |
| mention-count                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| mention-density              |     0 |     0.978 |  1.000 | 0.989 |      45 |
| mention-density              |     1 |     0.667 |  0.667 | 0.667 |       3 |
| mention-density              |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-mentions-per-page        |     0 |     1.000 |  1.000 | 1.000 |      45 |
| max-mentions-per-page        |     1 |     0.750 |  1.000 | 0.857 |       3 |
| max-mentions-per-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| max-section-density          |     0 |     0.977 |  0.956 | 0.966 |      45 |
| max-section-density          |     1 |     0.400 |  0.667 | 0.500 |       3 |
| max-section-density          |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention             |     0 |     1.000 |  0.933 | 0.966 |      45 |
| earliest-mention             |     1 |     0.429 |  1.000 | 0.600 |       3 |
| earliest-mention             |     2 |     0.000 |  0.000 | 0.000 |       1 |
| earliest-mention-page        |     0 |     0.957 |  0.978 | 0.967 |      45 |
| earliest-mention-page        |     1 |     0.333 |  0.333 | 0.333 |       3 |
| earliest-mention-page        |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-fraction               |     0 |     0.918 |  1.000 | 0.957 |      45 |
| first-fraction               |     1 |     0.000 |  0.000 | 0.000 |       3 |
| first-fraction               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| decay-weighted               |     0 |     1.000 |  1.000 | 1.000 |      45 |
| decay-weighted               |     1 |     0.750 |  1.000 | 0.857 |       3 |
| decay-weighted               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-3-pages                |     0 |     1.000 |  0.889 | 0.941 |      45 |
| first-3-pages                |     1 |     0.333 |  1.000 | 0.500 |       3 |
| first-3-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-5-pages                |     0 |     1.000 |  0.889 | 0.941 |      45 |
| first-5-pages                |     1 |     0.333 |  1.000 | 0.500 |       3 |
| first-5-pages                |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages               |     0 |     1.000 |  0.889 | 0.941 |      45 |
| first-10-pages               |     1 |     0.333 |  1.000 | 0.500 |       3 |
| first-10-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-15-pages               |     0 |     1.000 |  0.889 | 0.941 |      45 |
| first-15-pages               |     1 |     0.333 |  1.000 | 0.500 |       3 |
| first-15-pages               |     2 |     0.000 |  0.000 | 0.000 |       1 |
| first-10-pages-density       |     0 |     1.000 |  0.889 | 0.941 |      45 |
| first-10-pages-density       |     1 |     0.375 |  1.000 | 0.545 |       3 |
| first-10-pages-density       |     2 |     1.000 |  1.000 | 1.000 |       1 |
| (count or density) and early |     0 |     0.957 |  1.000 | 0.978 |      45 |
| (count or density) and early |     1 |     0.500 |  0.333 | 0.400 |       3 |
| (count or density) and early |     2 |     0.000 |  0.000 | 0.000 |       1 |
| density and early            |     0 |     0.957 |  1.000 | 0.978 |      45 |
| density and early            |     1 |     0.500 |  0.333 | 0.400 |       3 |
| density and early            |     2 |     0.000 |  0.000 | 0.000 |       1 |
