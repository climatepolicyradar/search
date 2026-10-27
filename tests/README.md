# Tests

This directory contains tests for the search codebase. Tests are split into two
major categories:

## Functional tests

Functional tests are located in the root of the `tests/` directory. They use a
combination of pytest and hypothesis to ensure that the code is working as
expected.

If you want to run the functional tests, you can use the following command:

```bash
just test-functional
```

If you start seeing odd results, you can clear the local test data cache by
running the following commands:

```bash
just clean
just install
just test-functional
```

## Relevance tests

Relevance tests live in `relevance_tests/suites/` as pydantic-evals datasets.
They grade the relevance of a search engine's results using a set of real search
terms, and the IDs of the results we expect to be returned.

You can run every suite with the following command:

```bash
just test-relevance
```

or one suite, optionally writing an HTML report:

```bash
uv run python -m relevance_tests --suite passages --report html
```
