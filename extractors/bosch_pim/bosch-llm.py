"""
bosch-llm.py – Génère des ProductDocument via LLM (gpt-5-nano, Responses API, batch).

Approche : on envoie pour chaque produit toutes les paires clé/valeur non vides (ligne CSV/XLSX Bosch),
le LLM produit directement l'objet `product` complet du contrat ProductDocument.

Sous-commandes :
  prepare --input <csv|xlsx> --output <batch.jsonl>
  send --batch-file <batch.jsonl>
  merge --batch-id <batch_id> --input <csv|xlsx> --out-dir <dir> [--write-drop]

Prérequis : OPENAI_API_KEY dans .env, pandas/openpyxl pour XLSX.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

# Allow running as a script from project root or this folder
ROOT = Path(__file__).resolve().parents[2]
import sys
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from extractors.shared.product_document_utils import (
    build_meta,
    make_document_id,
    write_product_document,
)

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL = "gpt-5-nano"


# ---------------------------
# Lecture des données source
# ---------------------------
def load_rows(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        import csv

        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    else:
        try:
            import pandas as pd  # type: ignore
        except ImportError:
            raise SystemExit(
                "pandas est requis pour lire un fichier Excel. Installe : pip install pandas openpyxl"
            )
        df = pd.read_excel(path)
        df = df.fillna("")
        return df.to_dict(orient="records")


def row_to_context(row: Dict[str, Any]) -> Dict[str, str]:
    ctx = {}
    for k, v in row.items():
        if v is None:
            continue
        s = str(v).strip()
        if s != "":
            ctx[k] = s
    return ctx


# ---------------------------
# LLM payload
# ---------------------------
def build_response_format() -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "product_mapping",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "language_code": {"type": "string"},
                "language_name": {"type": "string"},
                "product": {
                    "type": "object",
                    "properties": {
                        "product_name": {"type": "string"},
                        "brand": {"type": "string"},
                        "ean_codes": {"type": "array", "items": {"type": "string"}},
                        "gtin_codes": {"type": "array", "items": {"type": "string"}},
                        "manufacturer_reference": {"type": "string"},
                        "manufacturer_reference_aliases": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "short_descriptions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "long_descriptions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "strengths": {"type": "array", "items": {"type": "string"}},
                        "applications": {"type": "array", "items": {"type": "string"}},
                        "marketing": {"type": "array", "items": {"type": "string"}},
                        "compatible_with": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "raw_text": {"type": "string"},
                                    "brand": {"type": ["string", "null"]},
                                    "manufacturer_reference": {"type": ["string", "null"]},
                                    "gtin": {"type": ["string", "null"]},
                                    "type": {"type": ["string", "null"]},
                                },
                                "required": [
                                    "raw_text",
                                    "brand",
                                    "manufacturer_reference",
                                    "gtin",
                                    "type",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "categories": {"type": "array", "items": {"type": "string"}},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "regulatory": {"type": "array", "items": {"type": "string"}},
                        "attributes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "value": {"type": "string"},
                                    "unit": {"type": "string"},
                                },
                                "required": ["name", "value", "unit"],
                                "additionalProperties": False,
                            },
                        },
                        "images": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "source": {"type": "string"},
                                    "page": {"type": ["number", "null"]},
                                    "file_path": {"type": ["string", "null"]},
                                    "filename": {"type": ["string", "null"]},
                                    "url": {"type": ["string", "null"]},
                                    "classification": {"type": "string"},
                                    "description": {"type": "string"},
                                    "product_name_from_image": {"type": "string"},
                                    "brand_from_image": {"type": "string"},
                                },
                                "required": [
                                    "id",
                                    "source",
                                    "page",
                                    "file_path",
                                    "filename",
                                    "url",
                                    "classification",
                                    "description",
                                    "product_name_from_image",
                                    "brand_from_image",
                                ],
                                "additionalProperties": False,
                            },
                        },
                        "media": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "title": {"type": "string"},
                                    "language_code": {"type": "string"},
                                    "url": {"type": "string"},
                                    "source": {"type": "string"},
                                },
                                "required": ["type", "title", "language_code", "url", "source"],
                                "additionalProperties": False,
                            },
                        },
                        "other_texts": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "product_name",
                        "brand",
                        "ean_codes",
                        "gtin_codes",
                        "manufacturer_reference",
                        "manufacturer_reference_aliases",
                        "short_descriptions",
                        "long_descriptions",
                        "strengths",
                        "applications",
                        "marketing",
                        "compatible_with",
                        "categories",
                        "tags",
                        "regulatory",
                        "attributes",
                        "images",
                        "media",
                        "other_texts",
                    ],
                    "additionalProperties": False,
                },
            },
            "required": ["language_code", "language_name", "product"],
            "additionalProperties": False,
        },
    }


def build_system_prompt() -> str:
    return (
        "Tu es un extracteur qui mappe ces données vers le JSON schema demandé. Tips: orderNumber is the manufacturer reference."
    )


# ---------------------------
# Batch preparation
# ---------------------------
def step_prepare(input_file: Path, batch_file: Path) -> None:
    rows = load_rows(input_file)
    system_prompt = build_system_prompt()
    json_schema = build_response_format()

    requests = []
    for idx, row in enumerate(rows):
        ctx = row_to_context(row)
        if not ctx:
            continue
        user_json = json.dumps({"attributes": ctx}, ensure_ascii=False)
        req = {
            "custom_id": make_document_id(input_file.stem, idx),
            "method": "POST",
            "url": "/v1/responses",
            "body": {
                "model": MODEL,
                "input": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_json},
                ],
                "text": {
                    "format": json_schema,
                },
                "max_output_tokens": 16000,
            },
        }
        requests.append(json.dumps(req, ensure_ascii=False))

    batch_file.parent.mkdir(parents=True, exist_ok=True)
    with batch_file.open("w", encoding="utf-8") as f:
        for r in requests:
            f.write(r + "\n")
    print(f"Écrit {len(requests)} requêtes dans {batch_file}")


# ---------------------------
# Batch send
# ---------------------------
def step_send(batch_file: Path) -> None:
    bf = client.files.create(file=open(batch_file, "rb"), purpose="batch")
    job = client.batches.create(
        input_file_id=bf.id,
        endpoint="/v1/responses",
        completion_window="24h",
    )
    print(f"Batch lancé : {job.id}")


# ---------------------------
# Merge results
# ---------------------------
def parse_response_line(line: str) -> Dict[str, Any]:
    obj = json.loads(line)
    cid = obj.get("custom_id")
    body = obj.get("response", {}).get("body", {})
    out = body.get("output") or []
    product = None
    language_code = ""
    language_name = ""
    for item in out:
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            ctype = c.get("type")
            data = None
            if ctype == "output_json":
                data = c.get("json", {})
            elif ctype == "output_text":
                try:
                    data = json.loads(c.get("text", "") or "{}")
                except json.JSONDecodeError:
                    data = None
            if data is None:
                continue
            product = data.get("product")
            language_code = data.get("language_code", "")
            language_name = data.get("language_name", "")
            break
    return {"custom_id": cid, "product": product, "language_code": language_code, "language_name": language_name}


def step_merge(batch_id: str, input_file: Path, out_dir: Path, write_drop: bool = False) -> None:
    job = client.batches.retrieve(batch_id)
    if job.status != "completed":
        raise SystemExit(f"Batch {batch_id} pas terminé, statut={job.status}")
    content = client.files.content(job.output_file_id).text

    result_map = {}
    for line in content.splitlines():
        if not line.strip():
            continue
        parsed = parse_response_line(line)
        cid = parsed.get("custom_id")
        if cid and parsed.get("product"):
            result_map[cid] = parsed

    rows = load_rows(input_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    drop_dir = Path("drop/product-documents")
    if write_drop:
        drop_dir.mkdir(parents=True, exist_ok=True)

    format_hint = "excel" if input_file.suffix.lower() in {".xlsx", ".xls"} else "csv"
    mime_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if format_hint == "excel"
        else "text/csv"
    )
    source_type = "excel_bosch_pim_llm"
    source_system = "bosch_pim"

    for idx, row in enumerate(rows):
        doc_id = make_document_id(input_file.stem, idx)
        mapped = result_map.get(doc_id)
        if not mapped:
            continue
        product = mapped["product"]
        language = {"code": mapped.get("language_code", ""), "name": mapped.get("language_name", "")}
        meta = build_meta(
            source_type=source_type,
            file_path=input_file,
            product_index=idx,
            page_range=None,
            anchor=f"Sheet1!{idx+2}",
            artifacts={},
            language=language,
            source_system=source_system,
            format=format_hint,
            mime_type=mime_type,
            source_document_id=input_file.stem,
            document_id=doc_id,
        )
        doc = {"meta": meta, "product": product}
        out_path = out_dir / f"{doc_id}.json"
        write_product_document(doc, out_path)
        if write_drop:
            drop_path = drop_dir / f"{doc_id}.json"
            write_product_document(doc, drop_path)
    print(f"Fusion terminée. Fichiers écrits dans {out_dir}")


# ---------------------------
# CLI
# ---------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="LLM full mapping (Bosch PIM) -> ProductDocument")
    sub = parser.add_subparsers(dest="cmd")

    p1 = sub.add_parser("prepare")
    p1.add_argument("--input", required=True, type=Path, help="Fichier source CSV/XLSX Bosch")
    p1.add_argument("--output", required=True, type=Path, help="Fichier batch .jsonl")

    p2 = sub.add_parser("send")
    p2.add_argument("--batch-file", required=True, type=Path, help="Fichier batch .jsonl")

    p3 = sub.add_parser("merge")
    p3.add_argument("--batch-id", required=True, help="ID du batch job")
    p3.add_argument("--input", required=True, type=Path, help="Fichier source CSV/XLSX Bosch")
    p3.add_argument("--out-dir", required=True, type=Path, help="Dossier de sortie JSON")
    p3.add_argument("--write-drop", action="store_true", help="Écrire aussi dans drop/product-documents/")

    args = parser.parse_args()
    if args.cmd == "prepare":
        step_prepare(args.input, args.output)
    elif args.cmd == "send":
        step_send(args.batch_file)
    elif args.cmd == "merge":
        step_merge(args.batch_id, args.input, args.out_dir, args.write_drop)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
