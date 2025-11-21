import logging
import sys
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Load env (DATABASE_URL, etc.)
load_dotenv()

# Ensure project root is on sys.path so imports work regardless of CWD
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pkh.pkh_db import get_conn, insert_product_document, refresh_canonical
from pkh.pkh_models import ProductDocument

logger = logging.getLogger(__name__)

app = FastAPI(title="Product Knowledge Hub Ingestion API")


def get_connection():
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/product-documents")
def ingest_product_document(doc: ProductDocument, conn=Depends(get_connection)):
    try:
        new_id = insert_product_document(conn, doc)
        if not new_id:
            return JSONResponse(
                status_code=200,
                content={"status": "skipped", "reason": "duplicate_document_id"},
            )

        refresh_canonical(conn, doc.product.manufacturer_reference, doc.product.brand)
        return {"status": "ingested", "id": new_id}
    except Exception as exc:
        logger.exception("Failed to ingest document_id=%s", doc.meta.document_id)
        raise HTTPException(status_code=500, detail=str(exc))
