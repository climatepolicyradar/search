import json
from pathlib import Path

import requests

API_URL = "https://yiihg2zeuc.eu-west-1.awsapprunner.com/documents"
CACHE_DIR = Path(".data_cache/data-in-api")
CACHE_FILE = CACHE_DIR / "documents.json"
VESPA_ENDPOINT = "http://localhost:8000/document/v1/documents/documents/docid"


def fetch_and_cache_data():
    """Fetches data from the API and caches it locally."""
    print(f"Fetching data from {API_URL}...")
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        data = response.json()

        # Ensure cache directory exists
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Data cached to {CACHE_FILE}")
        return data
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


def load_data_to_vespa(data):
    """Loads cached data into Vespa."""
    if not data or "data" not in data:
        print("No documents found in data.")
        return

    documents = data["data"]
    print(f"Found {len(documents)} documents. Loading into Vespa...")

    for doc in documents:
        doc_id = doc.get("id")
        if not doc_id:
            print("Skipping document without ID")
            continue

        # Construct Vespa document ID
        # Converting raw ID to a safe Vespa ID format if needed, but assuming ID is safe for now
        # Format: id:namespace:document-type:user-specified-unique-id
        # We use the raw ID as the unique part.
        vespa_id = f"{VESPA_ENDPOINT}/{doc_id}"

        # Prepare fields match schema
        fields = {"title": doc.get("title"), "description": doc.get("description")}

        vespa_doc = {"fields": fields}

        try:
            response = requests.post(vespa_id, json=vespa_doc)
            if response.status_code == requests.codes.ok:
                print(f"Successfully fed document: {doc_id}")
            else:
                print(
                    f"Failed to feed document {doc_id}: {response.status_code} - {response.text}"
                )
        except Exception as e:
            print(f"Error feeding document {doc_id}: {e}")


def main():
    # Check if we should fetch fresh data or use cache (optional logic, but per requirements: fetch then cache then load)
    # Requirement: "fetches... then caches... then loads"
    data = fetch_and_cache_data()
    if data:
        load_data_to_vespa(data)


if __name__ == "__main__":
    main()
