# Cheat Sheet – Extractors / PKH / PIM Enricher

## Prérequis env
```bash
# Dans .env (non versionné)
DATABASE_URL=postgresql://pkhuser:pkhpass@127.0.0.1:55432/pkhdb
OPENAI_API_KEY=...
PKH_BASE_URL=http://127.0.0.1:8000
```

## PKH (API + ingestion)
- Lancer l’API FastAPI (PKH) :
```bash
uvicorn pkh.pkh_api:app --reload
```

- Ingestion drop folder → Postgres (+ canonical) :
```bash
python pkh/ingest_dropfolder.py
```

- Recalcul canonique pour tous les produits (exemple) :
```bash
python - <<'PY'
from pkh.pkh_db import get_conn, refresh_canonical
with get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT manufacturer_reference, brand FROM product_documents")
        for r in cur.fetchall():
            refresh_canonical(conn, r["manufacturer_reference"], r["brand"])
PY
```

- Vérifications DB (psql) :
```bash
psql "$DATABASE_URL" -c "SELECT count(*) FROM product_documents;"
psql "$DATABASE_URL" -c "SELECT count(*) FROM products_canonical;"
psql "$DATABASE_URL" -c "SELECT document_id, manufacturer_reference, brand, ingested_at FROM product_documents ORDER BY ingested_at DESC LIMIT 10;"
psql "$DATABASE_URL" -c "SELECT manufacturer_reference, brand, canonical_product_name, last_updated_at FROM products_canonical ORDER BY last_updated_at DESC LIMIT 10;"

- Vider les tables PKH (attention, supprime tout) :
```bash
python pkh/clear_pkh.py
```
```

## Extracteurs
- PDF single-product → ProductDocument :
```bash
python extractors/pdf_single/single-product-pdf.py
```

- Bosch PIM (mapping direct, pas de LLM) :
```bash
python extractors/bosch_pim/bosch-excel-pim.py \
  --input extractors/bosch_pim/bosch-existing-5.xlsx
# Résultats dans output/json/ et drop/product-documents/ si --write-drop
```

- Bosch PIM (LLM batch, Responses API) :
```bash
# Générer le batch JSONL
python extractors/bosch_pim/bosch-llm.py prepare \
  --input extractors/bosch_pim/bosch-existing-5.xlsx \
  --output extractors/bosch_pim/bosch-llm-batch.jsonl

# Envoyer le batch (note batch_id)
python extractors/bosch_pim/bosch-llm.py send \
  --batch-file extractors/bosch_pim/bosch-llm-batch.jsonl

# Merger les résultats LLM en JSON ProductDocument
python extractors/bosch_pim/bosch-llm.py merge \
  --batch-id <batch_id> \
  --input extractors/bosch_pim/bosch-existing-5.xlsx \
  --out-dir output/json-llm
```

## PIM Enricher (consumer)
- Générer un batch LLM pour enrichir les attributs PIM depuis le PKH :
```bash
python consumers/pim_enricher/pim_enricher.py prepare \
  --input consumers/pim_enricher/pim-45-products-to-enrich.xlsx \
  --output batch.jsonl
# Le batch et not_found_report.json sont écrits dans consumers/pim_enricher/
```
- Envoyer et merger (si besoin) suit la même logique Responses API (send/merge) que ci-dessus, en adaptant les chemins/batch_id.

- Envoyer le batch
```bash
python consumers/pim_enricher/pim_enricher.py send \
  --batch-file consumers/pim_enricher/batch.jsonl
# note le batch_id affiché
```

- Récupérer le batch
```bash
python consumers/pim_enricher/pim_enricher.py merge \
  --batch-id <batch_id> \
  --input consumers/pim_enricher/fr_global_vision_export_20251121T160941.xlsx \
  --out-dir consumers/pim_enricher/output  # ou un dossier de ton choix
```

---

## Divers
- Drop folder (PKH) : `drop/product-documents/` (ingestion), `drop/archive/`, `drop/error/`
- Outputs bruts extracteurs : `output/json/`, LLM : `output/json-llm/`
- Schéma SQL : `pkh/schema.sql`
