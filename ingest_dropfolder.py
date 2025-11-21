"""
Ingest all ProductDocument JSON files from drop/product-documents/ into Postgres.
Validates via Pydantic, inserts with ON CONFLICT(document_id) DO NOTHING,
and triggers canonical refresh for new documents. Moves processed files to
drop/archive/ (or drop/error/ on failure).
"""

import json
import shutil
from pathlib import Path

from pkh_db import get_conn, insert_product_document, refresh_canonical
from pkh_models import ProductDocument

DROP_DIR = Path("drop/product-documents")
ARCHIVE_DIR = Path("drop/archive")
ERROR_DIR = Path("drop/error")


def ensure_dirs():
    for d in [DROP_DIR, ARCHIVE_DIR, ERROR_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def ingest_all() -> None:
    ensure_dirs()
    files = sorted(p for p in DROP_DIR.glob("*.json") if p.is_file())
    if not files:
        print("No files to ingest.")
        return

    with get_conn() as conn:
        for path in files:
            try:
                with path.open("r", encoding="utf-8") as f:
                    doc_data = json.load(f)
                doc = ProductDocument.model_validate(doc_data)
                new_id = insert_product_document(conn, doc)
                if new_id:
                    refresh_canonical(
                        conn,
                        doc.product.manufacturer_reference,
                        doc.product.brand,
                    )
                    dest = ARCHIVE_DIR / path.name
                    print(f"Ingested {path.name} → {new_id}")
                else:
                    dest = ARCHIVE_DIR / path.name
                    print(f"Skipped (duplicate) {path.name}")
                shutil.move(str(path), dest)
            except Exception as exc:  # noqa: BLE001
                # Roll back this transaction and move file to error
                try:
                    conn.rollback()
                except Exception:
                    pass
                print(f"Error ingesting {path.name}: {exc!r}")
                dest = ERROR_DIR / path.name
                shutil.move(str(path), dest)


if __name__ == "__main__":
    ingest_all()
