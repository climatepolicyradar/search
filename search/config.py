import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

AWS_PROFILE_NAME = os.getenv("AWS_PROFILE_NAME", "labs")
AWS_REGION_NAME = os.getenv("AWS_REGION_NAME", "eu-west-1")

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
