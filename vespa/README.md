# Search Vespa

## Purpose

- used for us to test Vespa locally

## Quickstart

### Getting the documents data in locally

#### Documents

```bash
# get the docker container running
just up

# deploy the app
just deploy

# extract data materialised by Prefect from data-in API
just extract-documents

# feed the data into Vespa
just feed-documents
```

#### 🧪 Experimental: Passages

```bash

# extract data materialised by Prefect from indexer input
just extract-passages

# feed the data into Vespa
just feed-passages
```
