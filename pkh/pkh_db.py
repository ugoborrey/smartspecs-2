import os
from datetime import datetime, timezone
from typing import Optional, Tuple

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from pkh.pkh_models import ProductDocument


def get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL manquant dans l'environnement")
    # autocommit=False par défaut ; on commit manuellement
    return psycopg.connect(url, row_factory=dict_row)


def insert_product_document(conn, doc: ProductDocument) -> Optional[str]:
    """Insert ProductDocument; skip on conflict (document_id). Returns new id or None if skipped."""
    meta = doc.meta
    product = doc.product
    now = datetime.now(timezone.utc)

    params = {
        "document_id": meta.document_id,
        "source_type": meta.source_type,
        "language_code": meta.language.code,
        "manufacturer_reference": product.manufacturer_reference,
        "brand": product.brand,
        "product_name": product.product_name,
        "source_document": Json(meta.source_document.model_dump()),
        "artifacts": Json(meta.artifacts.model_dump()),
        "extracted_at": meta.extracted_at,
        "ingested_at": now,
        "payload": Json(product.model_dump()),
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO product_documents (
                document_id,
                source_type,
                language_code,
                manufacturer_reference,
                brand,
                product_name,
                source_document,
                artifacts,
                extracted_at,
                ingested_at,
                payload
            )
            VALUES (
                %(document_id)s,
                %(source_type)s,
                %(language_code)s,
                %(manufacturer_reference)s,
                %(brand)s,
                %(product_name)s,
                %(source_document)s::jsonb,
                %(artifacts)s::jsonb,
                %(extracted_at)s,
                %(ingested_at)s,
                %(payload)s::jsonb
            )
            ON CONFLICT (document_id) DO NOTHING
            RETURNING id;
            """,
            params,
        )
        row = cur.fetchone()
    conn.commit()
    return row["id"] if row else None


def _select_best_evidence(
    conn, manufacturer_reference: str, brand: str
) -> Optional[Tuple[dict, str, str]]:
    """Pick freshest evidence for a given product key."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT payload, language_code, product_name
            FROM product_documents
            WHERE manufacturer_reference = %(mr)s AND brand = %(brand)s
            ORDER BY extracted_at DESC NULLS LAST, ingested_at DESC NULLS LAST
            LIMIT 1;
            """,
            {"mr": manufacturer_reference, "brand": brand},
        )
        row = cur.fetchone()
    if not row:
        return None
    return row["payload"], row["language_code"], row["product_name"]


def refresh_canonical(conn, manufacturer_reference: str, brand: str) -> bool:
    """
    Generate/update canonical for (manufacturer_reference, brand) using freshest evidence.
    Returns True if upsert happened, False if no evidence exists.
    """
    best = _select_best_evidence(conn, manufacturer_reference, brand)
    if not best:
        return False
    payload, lang_code, fallback_name = best
    canonical_product_name = payload.get("product_name") or fallback_name or ""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO products_canonical (
                manufacturer_reference,
                brand,
                canonical_product_name,
                language_code_preferred,
                canonical_payload,
                last_updated_at
            ) VALUES (
                %(mr)s,
                %(brand)s,
                %(name)s,
                %(lang)s,
                %(payload)s::jsonb,
                NOW()
            )
            ON CONFLICT (manufacturer_reference, brand)
            DO UPDATE SET
                canonical_product_name = EXCLUDED.canonical_product_name,
                language_code_preferred = EXCLUDED.language_code_preferred,
                canonical_payload = EXCLUDED.canonical_payload,
                last_updated_at = EXCLUDED.last_updated_at;
            """,
            {
                "mr": manufacturer_reference,
                "brand": brand,
                "name": canonical_product_name,
                "lang": lang_code or "",
                "payload": Json(payload),
            },
        )
    conn.commit()
    return True
