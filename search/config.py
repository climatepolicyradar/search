from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
