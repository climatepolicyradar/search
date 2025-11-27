# Search API

FastAPI app for searching documents, passages, and labels, with configurable underlying search engine implementations for each endpoint.

## Installation

Install dependencies and set up the project:

```bash
just install
```

## Running the API

Start the development server:

```bash
just serve-api
```

The API will be available at `http://localhost:8000` with interactive documentation and type details at `http://localhost:8000/docs`.

## Endpoints

- `GET /` - top-level API info, health check
- `GET /documents` - Search documents
- `GET /passages` - Search passages
- `GET /labels` - Search labels

Each of the search endpoints takes a `search_terms` query parameter, and optionally supports pagination via the `page` and `page_size` query parameters.
