# Product Knowledge Hub – Implementation Plan

## Scope
- Build a small, extractor‑agnostic ingestion flow that:
  - Receives `ProductDocument` JSONs (drop folder or FastAPI).
  - Validates via lightweight Pydantic.
  - Inserts into Postgres (`product_documents`).
  - Immediately triggers canonical generation (`products_canonical`) per product key.
- No bulk mode for now; keep it simple and idempotent (no re‑ingest of already ingested docs).

## Database (recap)
- Tables:
  - `product_documents` (append‑only evidence): id (UUID PK), document_id, source_type, language_code, manufacturer_reference, brand, product_name, source_document (jsonb), artifacts (jsonb), extracted_at, ingested_at, payload (jsonb).
  - `products_canonical` (merged view): id (UUID PK), manufacturer_reference, brand, canonical_product_name, language_code_preferred, canonical_payload (jsonb), last_updated_at. Unique index on (manufacturer_reference, brand).
- Minimal indexes: `(manufacturer_reference, brand)`, `(document_id)`, `(source_document->>'id')` if needed.

## Idempotency (ne pas ré-ingérer)
- Simple rule: enforce unique `document_id` in `product_documents`. On insert conflict, skip (no re‑ingest).
  - Add unique index on `document_id`.
  - In ingestion code: `INSERT ... ON CONFLICT (document_id) DO NOTHING`.

## Ingestion Module (FastAPI + drop folder option)
- Responsibilities:
  - Validate incoming JSON against Pydantic `ProductDocument` model (shape identical au contrat).
  - Extract promoted fields (for indexing): document_id, source_type, language_code, manufacturer_reference, brand, product_name, source_document, artifacts, extracted_at, payload.
    - Note: “promoted” = champs mis en colonne pour requêtes/index. Le payload complet est conservé dans `payload`.
  - Insert into `product_documents` with `ingested_at = now()`, skip if conflict on `document_id`.
  - Trigger canonical refresh for `(manufacturer_reference, brand)`.
- API endpoints (FastAPI):
  - `POST /product-documents` – body: `ProductDocument`.
    - Validate; insert; run canonical refresh; return status.
  - (Optional later) `GET /health`.
- Drop folder ingestion (script option):
  - Lit tous les JSON du dossier, POST vers l’API ou insère directement (selon mode), archive après succès.

## Canonical Data Generator (post-ingest)
- Triggered right after successful insert.
- Logic:
  - If no existing `products_canonical` for `(manufacturer_reference, brand)`: create with current payload (and set `canonical_product_name = product_name`, `language_code_preferred = language.code`).
  - Else: fetch all `product_documents` for the key, rank/merge by:
    - Freshness (`extracted_at`, puis `ingested_at`).
    - Source priority (if a mapping exists; otherwise freshness only).
  - For each field (texts, arrays, attributes, images/media): pick highest‑ranked non‑empty; dedupe arrays.
  - Write/update `products_canonical`, `last_updated_at = now()`.
- Keep it simple: no LLM here; deterministic selection only.

## Validation (Pydantic léger)
- Define Pydantic models mirroring `ProductDocument` (meta + product).
- Use for FastAPI request body validation and for drop‑folder ingestion before insert.
- Accept arrays empty; strings can be empty; require presence of keys per contract.

## Steps to implement
1) **DB setup**: add unique index on `product_documents(document_id)` if not present.
2) **Pydantic models**: `ProductDocumentMeta`, `ProductDocumentProduct`, `ProductDocument`.
3) **FastAPI service**:
   - `POST /product-documents`: validate, insert (`ON CONFLICT DO NOTHING`), trigger canonical refresh, respond.
   - DB access via async or sync pool (psycopg/asyncpg).
4) **Canonical refresh function** (shared):
   - Given `(manufacturer_reference, brand)`, load all evidence, apply ranking, upsert `products_canonical`.
5) **Drop-folder ingestor** (optional first pass):
   - Script that scans `drop/product-documents/`, loads JSON, calls API or direct insert+canonical, archives on success.
6) **Config**:
   - `.env` for DB URL; paths for drop folder; optional source priority map.
7) **Testing**:
   - Unit tests: validation, insert with conflict skip, canonical when first doc, canonical when merging fresher doc.
   - Manual test: run API locally, `curl` a ProductDocument, check DB rows in both tables.

## Notes
- No bulk mode for now; simple per-document flow is fine for tests.
- Canonical run est synchrone post‑ingestion pour avoir les données de test immédiatement.
- Tous les champs du JSON sont conservés dans `payload`; les colonnes “promues” facilitent les recherches et la clé métier (`manufacturer_reference`, `brand`).
