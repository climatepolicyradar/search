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

Relevance tests live in the `tests/relevance/` directory. They use the core
classes in this repo to grade the relevance of a search engine's results using a
set of real search terms, and the IDs of the results we expect to be returned.

You can run the relevance tests with the following command:

```bash
just test-relevance
```
