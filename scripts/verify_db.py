import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is on sys.path when running this script directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from src.db.mongo import get_db


def main():
    db = get_db()
    print("DB:", db.name)
    cols = db.list_collection_names()
    print("Collections:", cols)
    for coll in ["users", "template"]:
        if coll in cols:
            print(f"Indexes for {coll}:")
            for name, idx in db[coll].index_information().items():
                print(" ", name, "=>", idx)
        else:
            print(f"Collection {coll} does not exist yet")


if __name__ == "__main__":
    main()
