"""
bosch-excel-pim.py – Extract Bosch PIM export rows into ProductDocument JSONs (mapping direct).

Usage:
    python bosch-excel-pim.py --input bosch-excel-example-10-products.xlsx
    python bosch-excel-pim.py --input bosch-excel-example-10-products\ -\ Sheet1.csv

Produces one ProductDocument per row into output/json/<doc_id>.json.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow running as a script from project root or this folder
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from extractors.shared.product_document_utils import (  # type: ignore
    build_meta,
    make_document_id,
    to_project_relative,
    write_product_document,
)


SOURCE_TYPE = "excel_bosch_pim_export"
SOURCE_SYSTEM = "bosch_pim"
JSON_ROOT = Path("output/json")
DROP_ROOT = Path("drop/product-documents")

# Column keys (exact as in CSV header)
COL_ORDER_NUMBER = "orderNumber"
COL_GTIN = "GTIN13/GTIN12"
COL_PRODUCT_NAME = "Nom du Produit"
COL_COMMERCIAL_NAME = "Désignation commerciale"
COL_SHORT_1 = "Positionnement (description succincte)"
COL_SHORT_2 = "Description du matériel (SAP)"
COL_LONG_1 = "Description longue 2"
COL_BRAND = "Marque"
COL_USER_GROUP = "Groupe d'utilisateurs"
COL_CAT_PATH = "Catégorie de produit Chemin d’accès Description 4"
COL_CAT_LAST = "Catégorie de produit Dernier Niveau Description 4"
COL_PRODUCT_TYPE = "Type de produit"
COL_PRODUCT_LINE = "Ligne de produits"

ADVANTAGE_PREFIX = "Avantages"
APPLICATION_PREFIX = "Application/Domaine d'application"
IMAGE_PREFIX = "Image"
ICON_PREFIX = "Icône"


def load_table(path: Path) -> List[Dict[str, Any]]:
    """Load CSV or Excel into a list of row dicts. Requires pandas for XLSX."""
    if path.suffix.lower() in {".csv"}:
        import csv

        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    else:
        try:
            import pandas as pd  # type: ignore
        except ImportError:
            raise SystemExit(
                "pandas is required to read Excel files. Install with:\n"
                "  pip install pandas openpyxl\n"
            )
        df = pd.read_excel(path)
        return df.fillna("").to_dict(orient="records")


def normalize(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float):
        # Keep ints clean (avoid .0 for likely integer IDs)
        if val.is_integer():
            return str(int(val))
    return str(val).strip()


def collect_non_empty(row: Dict[str, Any], columns: List[str]) -> List[str]:
    return [normalize(row.get(col, "")) for col in columns if normalize(row.get(col, ""))]


def collect_prefixed(row: Dict[str, Any], prefix: str) -> List[str]:
    out = []
    for key, val in row.items():
        if key.startswith(prefix):
            v = normalize(val)
            if v:
                out.append(v)
    return out


def is_image_column(col: str) -> bool:
    lower = col.lower()
    return lower.startswith(IMAGE_PREFIX.lower()) or lower.startswith(ICON_PREFIX.lower())


def classify_image_column(col: str) -> str:
    clower = col.lower()
    if "application" in clower:
        return "application_image"
    if "dimensions" in clower:
        return "dimension_image"
    if "emballage" in clower or "fourniture" in clower:
        return "packaging_image"
    if "caractéristique" in clower:
        return "feature_image"
    if "icône" in clower or "icone" in clower:
        return "icon"
    return "product_image"


def is_media_column(col: str) -> bool:
    lower = col.lower()
    return any(
        kw in lower
        for kw in [
            "fiche technique",
            "notice",
            "page détaillée",
            "page detaillee",
            "collection vidéo",
            "collection video",
            "youtube",
            "vidéo",
            "video",
            "embed",
        ]
    )


def classify_media_type(col: str) -> str:
    lower = col.lower()
    if "fiche technique" in lower:
        return "technical_datasheet_pdf"
    if "notice" in lower or "manuel" in lower:
        return "user_manual_pdf"
    if "page détaillée" in lower or "page detaillee" in lower:
        return "product_detail_page"
    if "collection vidéo" in lower or "collection video" in lower:
        return "product_video_collection"
    if "youtube" in lower or "video" in lower or "vidéo" in lower or "embed" in lower:
        return "product_video"
    return "other"


HIGH_MAG_HINTS = [
    "régime",
    "regime",
    "fréquence",
    "frequence",
    "vitesse",
    "tr/min",
    "rpm",
]


from typing import Optional


def normalize_number(num_str: str, attr_name: Optional[str] = None) -> str:
    """
    Heuristics to interpret comma/dot as decimal vs thousand separators.
    - If only a comma and fraction has 1-2 digits => decimal.
    - If only a comma and fraction has 3 digits => use attr hint: if high magnitude (régime/vitesse/etc) -> thousand; else decimal.
    - If pattern like 1,234,567 => thousand grouping.
    - If both comma and dot => assume last separator is decimal, others are thousands.
    Falls back to the raw compact form.
    """
    import re

    t = num_str.replace(" ", "")
    has_comma = "," in t
    has_dot = "." in t
    hint_high = bool(attr_name and any(h in attr_name.lower() for h in HIGH_MAG_HINTS))

    if has_comma and not has_dot:
        parts = t.split(",")
        if len(parts) == 2:
            left, right = parts
            if right == "":
                return left  # trailing comma, treat as integer
            if len(right) <= 2:
                return f"{left}.{right}"
            if len(right) == 3:
                # Ambiguous: 22,230 could be 22.230 or 22,230 -> 22230
                if hint_high or len(left) >= 3:
                    return f"{left}{right}"
                return f"{left}.{right}"
        # Thousand grouping like 1,234,567
        if re.fullmatch(r"\d{1,3}(,\d{3})+", t):
            return t.replace(",", "")

    if has_dot and not has_comma:
        parts = t.split(".")
        if len(parts) == 2 and len(parts[1]) <= 2:
            return t  # dot as decimal
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            return t.replace(".", "")

    if has_comma and has_dot:
        # Assume the rightmost separator is decimal, others are thousands
        last_comma = t.rfind(",")
        last_dot = t.rfind(".")
        if last_comma > last_dot:
            # comma is decimal, dots are thousands
            return t.replace(".", "").replace(",", ".")
        else:
            # dot is decimal, commas are thousands
            return t.replace(",", "")

    return t


def split_value_unit(raw: str, attr_name: Optional[str] = None) -> (str, str):
    """
    Split number/unit and normalize number with heuristic decimal/thousand detection.
    Keeps the unit (if any) after the number.
    """
    import re

    text = raw.strip()
    if not text:
        return "", ""

    m = re.match(r"^([+-]?[0-9][0-9., ]*)(.*)$", text)
    if not m:
        return raw, ""

    num_part = m.group(1).strip()
    unit_part = (m.group(2) or "").strip()

    normalized_num = normalize_number(num_part, attr_name)
    return normalized_num, unit_part


def build_product(row: Dict[str, Any], source_doc_id: str) -> Dict[str, Any]:
    # Identifiants
    manufacturer_reference = normalize(row.get(COL_ORDER_NUMBER, ""))
    ean = normalize(row.get(COL_GTIN, ""))
    ean_codes = [ean] if ean else []
    gtin_codes = [ean] if ean else []

    # Noms
    name_candidates = [
        normalize(row.get(COL_PRODUCT_NAME, "")),
        normalize(row.get(COL_COMMERCIAL_NAME, "")),
        normalize(row.get(COL_SHORT_2, "")),
    ]
    product_name = next((n for n in name_candidates if n), "")

    # Descriptions
    short_candidates = [
        normalize(row.get(COL_SHORT_1, "")),
        normalize(row.get(COL_SHORT_2, "")),
        product_name,
    ]
    short_descriptions = [c for c in short_candidates if c]

    long_candidates = [normalize(row.get(COL_LONG_1, ""))]
    long_descriptions = [c for c in long_candidates if c]

    # Strengths / applications
    strengths = collect_prefixed(row, ADVANTAGE_PREFIX)
    applications = collect_prefixed(row, APPLICATION_PREFIX)

    # Categories / tags
    categories = collect_non_empty(
        row,
        [COL_CAT_PATH, COL_CAT_LAST, COL_PRODUCT_TYPE, COL_PRODUCT_LINE],
    )
    tags = collect_non_empty(row, [COL_USER_GROUP])

    brand = normalize(row.get(COL_BRAND, ""))

    # Images
    images = []
    for col, val in row.items():
        if not is_image_column(col):
            continue
        url = normalize(val)
        if not url:
            continue
        classification = classify_image_column(col)
        images.append(
            {
                "id": f"{col}",
                "source": SOURCE_SYSTEM,
                "page": None,
                "file_path": None,
                "filename": None,
                "url": url,
                "classification": classification,
                "description": "",
                "product_name_from_image": "",
                "brand_from_image": "",
            }
        )

    # Media
    media = []
    for col, val in row.items():
        if not is_media_column(col):
            continue
        url = normalize(val)
        if not url:
            continue
        media.append(
            {
                "type": classify_media_type(col),
                "title": col,
                "language_code": "fr",
                "url": url,
                "source": SOURCE_SYSTEM,
            }
        )

    # Attributes: all other non-empty columns not already mapped or media/images
    mapped_cols = {
        COL_ORDER_NUMBER,
        COL_GTIN,
        COL_PRODUCT_NAME,
        COL_COMMERCIAL_NAME,
        COL_SHORT_1,
        COL_SHORT_2,
        COL_LONG_1,
        COL_BRAND,
        COL_USER_GROUP,
        COL_CAT_PATH,
        COL_CAT_LAST,
        COL_PRODUCT_TYPE,
        COL_PRODUCT_LINE,
    }
    # Include all advantage/application columns in mapped to avoid duplicating as attributes
    mapped_cols.update(
        {k for k in row.keys() if k.startswith(ADVANTAGE_PREFIX) or k.startswith(APPLICATION_PREFIX)}
    )
    attributes = []
    for col, val in row.items():
        if col in mapped_cols:
            continue
        if is_image_column(col) or is_media_column(col):
            continue
        v = normalize(val)
        if not v:
            continue
        value, unit = split_value_unit(v, attr_name=col)
        attributes.append({"name": col, "value": value, "unit": unit})

    product = {
        "product_name": product_name,
        "brand": brand,
        "ean_codes": ean_codes,
        "gtin_codes": gtin_codes,
        "manufacturer_reference": manufacturer_reference,
        "manufacturer_reference_aliases": [],
        "short_descriptions": short_descriptions,
        "long_descriptions": long_descriptions,
        "strengths": strengths,
        "applications": applications,
        "marketing": [],
        "compatible_with": [],
        "categories": categories,
        "tags": tags,
        "regulatory": [],
        "attributes": attributes,
        "images": images,
        "media": media,
        "other_texts": [],
    }
    return product


def process_file(path: Path, *, write_drop: bool = False) -> None:
    rows = load_table(path)
    print(f"Loaded {len(rows)} rows from {path.name}")

    format_hint = "excel" if path.suffix.lower() in {".xlsx", ".xls"} else "csv"
    mime_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if format_hint == "excel"
        else "text/csv"
    )
    source_document_id = path.stem

    JSON_ROOT.mkdir(parents=True, exist_ok=True)
    if write_drop:
        DROP_ROOT.mkdir(parents=True, exist_ok=True)

    for idx, row in enumerate(rows):
        product = build_product(row, source_document_id)
        meta = build_meta(
            source_type=SOURCE_TYPE,
            file_path=path,
            product_index=idx,
            page_range=None,
            anchor=f"Sheet1!{idx+2}",  # header at row 1, data starts at 2
            artifacts={},
            language={"code": "fr", "name": "French"},
            source_system=SOURCE_SYSTEM,
            format=format_hint,
            kind="file",
            mime_type=mime_type,
            source_document_id=source_document_id,
            document_id=make_document_id(source_document_id, idx),
        )
        doc = {"meta": meta, "product": product}

        out_path = JSON_ROOT / f"{meta['document_id']}.json"
        write_product_document(doc, out_path)
        if write_drop:
            drop_path = DROP_ROOT / f"{meta['document_id']}.json"
            write_product_document(doc, drop_path)

    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Bosch Excel/CSV PIM export to ProductDocument JSON.")
    parser.add_argument("--input", required=True, help="Path to Excel or CSV file")
    parser.add_argument(
        "--write-drop",
        action="store_true",
        help="Also write each ProductDocument to drop/product-documents/",
    )
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f"Input file not found: {path}")

    process_file(path, write_drop=args.write_drop)


if __name__ == "__main__":
    main()
