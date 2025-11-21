# Product Data Ingestion Architecture

This document describes a simple, modular architecture for extracting product data from various sources, normalizing it, and ingesting it into a PostgreSQL product knowledge hub.

The current repo implements one extractor: **single‑product PDF → structured JSON** (`single-product-pdf.py`). The same patterns can be reused for other source types later (PDF catalogs, Excel, APIs, etc.).

## Goals

- Keep each piece small and replaceable.
- Use a single, shared JSON **contract** for all product data.
- Track provenance, language, and timestamps for every piece of data.
- Ingest into PostgreSQL through one simple “front door”.

---

## Core Data Contract: `ProductDocument`

Every extractor produces the same logical JSON shape, regardless of source.  
For single‑product PDFs there will be one `ProductDocument`; for multi‑product sources (PDF catalogs, Excel, HTML, …) there will be **one `ProductDocument` per product** extracted from the same `source_document`.

```jsonc
{
  "meta": {
    "document_id": "6205-deep-groove-ball-bearings-skf--p00",
    "source_type": "pdf_single_product",
    "source_document": {
      "id": "6205-deep-groove-ball-bearings-skf",
      "kind": "file",                  // file | url | api | other
      "format": "pdf",                 // pdf | excel | json | html | ...
      "mime_type": "application/pdf",
      "filename": "6205 - Deep groove ball bearings _ SKF.pdf",
      "path": "input/6205 - Deep groove ball bearings _ SKF.pdf",
      "url": null,
      "source_system": "bosch_pdf_2025"
    },
    "source_product": {
      "index": 0,                      // position of this product within source_document
      "page_range": [1, 3],           // or null for non‑paged formats like Excel/JSON
      "anchor": null                  // e.g. "sheet1-row-42" for Excel
    },
    "artifacts": {
      "markdown_path": "output/markdown/6205 - Deep groove ball bearings _ SKF.md",
      "images_dir": "extracted_images/6205 - Deep groove ball bearings _ SKF/",
      "json_path": "output/json/6205 - Deep groove ball bearings _ SKF.json"
    },
    "language": {
      "code": "fr",
      "name": "French"
    },
    "extracted_at": "2025-11-16T12:34:56Z"
  },
  "product": {
    "product_name": "",
    "brand": "",
    "ean_codes": [],
    "gtin_codes": [],
    "manufacturer_reference": "",
    "manufacturer_reference_aliases": [],
    "short_descriptions": [],
    "long_descriptions": [],
    "strengths": [],
    "applications": [],              // domain of application / use
    "marketing": [],
    "compatible_with": [
      {
        "raw_text": "",
        "brand": null,
        "manufacturer_reference": null,
        "gtin": null,
        "type": null                  // e.g. "tool", "accessory", "battery"
      }
    ],
    "categories": [],
    "tags": [],
    "regulatory": [],                // e.g. ["CE", "RoHS", "IP65"]
    "attributes": [
      { "name": "Tension de la batterie", "value": "18", "unit": "V" }
    ],
    "images": [
      {
        "id": "page02_01",
        "source": "pdf_docling",
        "page": 2,
        "file_path": "extracted_images/6205-deep-groove-ball-bearings-skf/page02_01.png",
        "filename": "page02_01.png",
        "url": null,
        "classification": "product_image",
        "description": "Three-quarter view of the tool",
        "product_name_from_image": "GDR 18V-220 C",
        "brand_from_image": "Bosch"
      }
    ],
    "media": [
      {
        "type": "technical_datasheet_pdf",
        "title": "Technical data sheet",
        "language_code": "fr",
        "url": "https://bosch.com/docs/tech-datasheet-6205.pdf",
        "source": "bosch_excel"
      }
    ],
    "other_texts": []
  }
}
```

Notes:

- `meta` captures provenance, including the original `source_document` (file/URL/API), the location of the product within that source (`source_product`), paths to all derived artifacts, language, and extraction time.
- `product` is the structured product sheet (fields from `single-product-pdf.py`), including:
  - `attributes` – technical specs as name/value/unit rows.
  - `images` – all image assets (local files or URLs) with rich metadata.
  - `media` – non-image assets like PDFs, videos, and web pages.
- When the same product appears in multiple sources, you will have **multiple** `ProductDocument` objects for that product, each with its own `meta`. All extractions coming from the same raw file share the same `meta.source_document.id`.

---

## Extractors (source‑specific modules)

Each extractor is a small module dedicated to one source type. Its only job:

- Read the source.
- Use whatever logic/LLMs it needs.
- Output one or more `ProductDocument` JSON files into a **drop folder**.

Examples of extractors:

- `pdf_single_product` – current script in this repo (one product per PDF) via `single-product-pdf.py`.
- `excel_bosch_pim_export` – mapping a Bosch PIM export (one product per row) via `bosch-excel-pim.py`.
- `pdf_catalog` – later: split a multi‑product catalog into many products.
- `excel_sheet` – later: read rows from Excel and map to the same contract.

### Current extractor (this repo)

`single-product-pdf.py` does:

- Reads all single‑product PDFs from `input/`.
- Uses Docling to:
  - Convert to a structured document.
  - Export markdown (`output/markdown/<stem>.md`).
  - Extract and classify images (`extracted_images/<stem>/pageXX_YY.png`).
- Calls `gpt-5-chat-latest` once per PDF to:
  - Fill `product` fields (name, brand, attributes, etc.).
  - Detect the main language (`language.code`, `language.name`).
- Builds a `meta` block with:
  - `document_id` = `<pdf_stem>--p00` (one product per PDF in this extractor).
  - `source_type = "pdf_single_product"`.
  - `source_document` describing the original file (kind, format, filename, path, etc.).
  - `source_product` with a trivial index (`0`) for this single‑product case.
  - `artifacts` paths (markdown, images, JSON).
  - `language` from the LLM.
  - `extracted_at` (UTC timestamp).
- Writes the final `ProductDocument` JSON both:
  - To `output/json/<stem>.json` (for local inspection).
  - Optionally to a **drop folder** (see below) for ingestion when you introduce the ingestion service.

---

## Drop Folder

The drop folder decouples extraction from ingestion. Extractors don’t need to know about Postgres or APIs; they just write JSON files.

Suggested structure:

- `drop/product-documents/` – all ready‑to‑ingest `ProductDocument` JSON files.

Naming:

- `drop/product-documents/<document_id>.<uuid>.json`
  - e.g. `drop/product-documents/6205-deep-groove-ball-bearings-skf.7f9e3c83.json`

Responsibilities:

- Extractors:
  - Write new `ProductDocument` files into this folder.
- Ingestion process:
  - Periodically scans this folder, sends each file to the ingestion API (or writes directly to Postgres), then moves/archives the file (e.g. to `drop/archive/`).

This keeps things simple:

- You can rerun ingestion without re‑running extraction.
- New extractors only need write access to the drop folder.

---

## Ingestion API Service

All writes to PostgreSQL should go through a tiny ingestion service. This avoids coupling extractors to DB details and gives you one place to enforce validation and business rules.

Minimal design (e.g. FastAPI/Flask):

- `POST /product-documents`
  - Body: one `ProductDocument` JSON.
  - Behavior:
    - Validate JSON against the contract.
    - Insert into `product_documents` table.
    - Set `ingested_at` timestamp.
    - Optionally trigger/queue canonical recalculation.

Optional additions (later if needed):

- `GET /product-documents/{id}` – retrieve raw evidence row.
- `GET /products/{manufacturer_reference}` – retrieve canonical view for a product.

The drop‑folder ingestion script is then just a small client:

- Reads each file in `drop/product-documents/`.
- POSTs it to `/product-documents`.
- On success, moves the file to an archive folder.

---

## PostgreSQL Schema (two core tables)

Start with two tables: one for **evidence**, one for the **canonical view**.

### 1. `product_documents` – raw evidence

One row per `ProductDocument` (per document, per product, per extraction).

At a minimum you store:

- `id` (PK, UUID or serial).
- `document_id` (text).
- `source_type` (text).
- `language_code` (text, e.g. `fr`).
- `manufacturer_reference` (text).
- `brand` (text).
- `product_name` (text).
- `source_document` (jsonb) – stores `meta.source_document` (file/URL metadata).
- `artifacts` (jsonb) – stores `meta.artifacts`.
- `extracted_at` (timestamptz).
- `ingested_at` (timestamptz, set by the API).
- `payload` (jsonb) – full `product` object (including attributes and text fields).

Indexes to consider:

- `(manufacturer_reference, brand)`
- `(document_id)`
- `( (source_document->>'id') )` if you need to group all extractions coming from the same raw file.

### 2. `products_canonical` – single best view per product

One row per logical product (e.g. `(manufacturer_reference, brand)`).

It holds:

- `id` (PK).
- `manufacturer_reference` (text).
- `brand` (text).
- `canonical_product_name` (text).
- `language_code_preferred` (text).
- `canonical_payload` (jsonb) – best‑effort merged product sheet.
- `last_updated_at` (timestamptz).

Canonicalization logic (simple strategy):

- For a given `(manufacturer_reference, brand)`:
  - Gather all rows from `product_documents`.
  - Rank them by:
    - **Source importance** (e.g. `source_type` or per‑document ranking).
    - **Freshness** (`extracted_at` / `ingested_at`).
    - Optionally **language preference** (e.g. prefer `en` for canonical, keep others as alternates).
  - For each field/attribute:
    - Pick the highest‑ranked non‑empty value.
  - Save the merged result to `canonical_payload`.

This logic can live in:

- A small Python job that runs after ingestion, or
- A simple SQL / PL/pgSQL function triggered by inserts, depending on how dynamic you want it.

---

## Summary

- **Extractors**: small, source‑specific modules that output standardized `ProductDocument` JSONs and write them to a **drop folder**.
- **Contract**: a shared `ProductDocument` shape with `meta` (provenance, artifacts, language, timestamps) and `product` (structured data).
- **Ingestion API**: tiny service with `POST /product-documents`, responsible for validating and writing to PostgreSQL.
- **Database**: two tables:
  - `product_documents` – immutable evidence, one row per extraction.
  - `products_canonical` – best current view per product, derived from evidence and source priorities.

This keeps the system modular, easy to extend to new source types, and transparent about where each piece of product data came from and when it was extracted.
