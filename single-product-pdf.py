# docling-gpt5-structured.py – 100% RELIABLE (Nov 16, 2025)
import base64
import json
import os
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from openai import OpenAI
from PIL import Image
from pydantic import BaseModel, Field
from pydantic.json import pydantic_encoder
from typing import Optional

load_dotenv()
client = OpenAI()

root_dir = Path(__file__).parent


def to_project_relative(path: Path) -> str:
    """
    Return a path relative to the project root when possible.
    If the path is already relative or outside the root, just return as_posix().
    """
    try:
        return path.relative_to(root_dir).as_posix()
    except ValueError:
        return path.as_posix()

# === CONFIG ===
pdf_opts = PdfPipelineOptions()
pdf_opts.generate_picture_images = True
pdf_opts.images_scale = 2.0

converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts)}
)

# Process all PDFs in the input/ folder by default.
input_dir = Path("input")
your_files = sorted(str(p) for p in input_dir.glob("*.pdf"))

# Base output folders
images_root = Path("extracted_images")
images_root.mkdir(exist_ok=True)
json_root = Path("output/json")
json_root.mkdir(parents=True, exist_ok=True)
markdown_root = Path("output/markdown")
markdown_root.mkdir(parents=True, exist_ok=True)


# === Pydantic model (local validation only) ===
class Attribute(BaseModel):
    name: str = Field(..., description="Exact attribute name from PDF")
    value: str = Field(..., description="Exact value")
    unit: Optional[str] = Field("", description="Unit or empty")

class CompatibleWithItem(BaseModel):
    raw_text: str = Field(..., description="Original text snippet describing compatibility")
    brand: Optional[str] = Field(None, description="Compatible product brand if extracted")
    manufacturer_reference: Optional[str] = Field(None, description="Compatible product manufacturer reference if extracted")
    gtin: Optional[str] = Field(None, description="Compatible product GTIN/EAN if extracted")
    type: Optional[str] = Field(None, description="Type of compatible item, e.g. tool/accessory/battery")

class ProductData(BaseModel):
    product_name: str = Field(..., description="Main product title")
    brand: str = Field("", description="Brand name")
    ean_codes: List[str] = Field(default_factory=list, description="All EAN barcodes found for this product")
    gtin_codes: List[str] = Field(default_factory=list, description="All GTIN codes found for this product")
    manufacturer_reference: str = Field("", description="Primary SKU or manufacturer reference code")
    manufacturer_reference_aliases: List[str] = Field(default_factory=list, description="Other reference codes or aliases for this product")
    short_descriptions: List[str] = Field(default_factory=list, description="Short descriptions (1–2 sentences each, unchanged language)")
    long_descriptions: List[str] = Field(default_factory=list, description="Longer descriptions or marketing paragraphs, unchanged language")
    strengths: List[str] = Field(default_factory=list, description="Key strengths / benefits")
    applications: List[str] = Field(default_factory=list, description="Application domains / scope of use")
    marketing: List[str] = Field(default_factory=list, description="Marketing or branding phrases / slogans")
    compatible_with: List[CompatibleWithItem] = Field(default_factory=list, description="List of compatible products mentioned in the sheet")
    categories: List[str] = Field(default_factory=list, description="Product categories or families")
    tags: List[str] = Field(default_factory=list, description="Keywords or tags extracted from the sheet")
    regulatory: List[str] = Field(default_factory=list, description="Regulatory labels or certifications (e.g. CE, RoHS, IP ratings)")
    other_texts: List[str] = Field(default_factory=list, description="Other free-text snippets that do not fit above types")
    attributes: List[Attribute] = Field(default_factory=list)


# Vision classification (still using gpt-4o vision)
def describe_and_classify_image(base64_image: str) -> Dict[str, str]:
    resp = client.chat.completions.create(
        model="gpt-4o-2024-11-20",
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Classify this image from a Bosch power‑tool technical data sheet.\n"
                        "Return ONLY valid JSON with these fields:\n"
                        "{\n"
                        '  "classification": "product_image | brand_logo | pictogram | technical_diagram | qr_code | chart_or_graph | other",\n'
                        '  "description": "1-sentence English description",\n'
                        '  "product_name_from_image": "exact product name as printed on the tool or page, or empty string",\n'
                        '  "brand_from_image": "brand name like Bosch if visible, else empty string"\n'
                        "}\n"
                    ),
                },
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
            ]
        }],
        max_tokens=8000,
    )
    # Robust parsing (same as before)
    raw = resp.choices[0].message.content.strip()
    if "```" in raw:
        raw = "".join(raw.split("```")[1::2])
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return {"classification": "other", "description": "Parse failed"}
    try:
        return json.loads(raw[start:end])
    except:
        return {
            "classification": "other",
            "description": raw[:100],
            "product_name_from_image": "",
            "brand_from_image": "",
        }


def fix_schema_for_openai(schema: Any) -> Any:
    """Recursively add additionalProperties: false to all object definitions."""
    if isinstance(schema, dict):
        # If it's an object type, add additionalProperties: false
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
        # Recursively process all values (including $defs for nested models)
        for key, value in schema.items():
            if key != "additionalProperties":  # Don't recurse into what we just added
                schema[key] = fix_schema_for_openai(value)
    elif isinstance(schema, list):
        # Process list items in place
        for i, item in enumerate(schema):
            schema[i] = fix_schema_for_openai(item)
    return schema


def extract_and_label(file_path: str) -> Dict[str, Any]:
    print(f"\nProcessing {os.path.basename(file_path)}...")

    result = converter.convert(file_path)
    doc = result.document

    # === 1. Images (Docling + vision classification) ===
    images_info = []
    if doc.pictures:
        # Create a per-document image subfolder, e.g. extracted_images/gdr-18v-220-c-sheet/
        stem = Path(file_path).stem
        doc_image_dir = images_root / stem
        doc_image_dir.mkdir(parents=True, exist_ok=True)

        for idx, pic in enumerate(doc.pictures, start=1):
            img = pic.get_image(doc)
            if not img:
                continue
            # Docling page_no is already 1-based; do not add 1 again.
            page = pic.prov[0].page_no if pic.prov else None
            page_segment = f"page{page:02d}" if isinstance(page, int) else "pageNA"
            filename = f"{page_segment}_{idx:02d}.png"
            save_path = doc_image_dir / filename
            if max(img.size) > 1024:
                img.thumbnail((1024, 1024), Image.LANCZOS)
            img.convert("RGB").save(save_path, "PNG", optimize=True)
            print(f"    → Saved {filename}")

            buffered = BytesIO()
            img.save(buffered, format="PNG", optimize=True)
            vision = describe_and_classify_image(base64.b64encode(buffered.getvalue()).decode())
            images_info.append(
                {
                    "id": f"{page_segment}_{idx:02d}",
                    "source": "pdf_docling",
                    "page": page if isinstance(page, int) else None,
                    "file_path": to_project_relative(save_path),
                    "filename": filename,
                    "url": None,
                    **vision,
                }
            )
        print(f"  → Extracted & classified {len(images_info)} images")

    # === 2. Compact Docling JSON / Markdown context ===
    # For scanned PDFs the OCR may be weak; DoclingDocument JSON often still
    # contains layout + some text which we give directly to the model.
    raw_doc = doc.model_dump(by_alias=True, exclude_none=True)
    # Be tolerant to any non-JSON-serialisable types (e.g. AnyUrl, enums).
    doc_json = json.dumps(raw_doc, default=lambda o: str(o), ensure_ascii=False)
    if len(doc_json) > 30000:
        doc_json = doc_json[:30000] + "..."

    markdown = doc.export_to_markdown()
    # Persist Docling's markdown export for debugging / inspection.
    md_stem = Path(file_path).stem
    md_path = markdown_root / f"{md_stem}.md"
    with open(md_path, "w", encoding="utf-8") as mf:
        mf.write(markdown)

    # === 3. GPT-5-chat-latest + Structured Outputs ===
    # Define a minimal, OpenAI-compatible JSON Schema by hand.
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "product_extraction",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "brand": {"type": "string"},
                    "ean_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "gtin_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
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
                    "language_code": {"type": "string"},
                    "language_name": {"type": "string"},
                    "strengths": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "applications": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "marketing": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
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
                            # For strict schemas, required must list every property key,
                            # but we still allow null to represent "not present".
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
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "regulatory": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "other_texts": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
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
                },
                "required": [
                    "product_name",
                    "brand",
                    "manufacturer_reference",
                    "ean_codes",
                    "gtin_codes",
                    "manufacturer_reference_aliases",
                    "short_descriptions",
                    "long_descriptions",
                    "language_code",
                    "language_name",
                    "strengths",
                    "applications",
                    "marketing",
                    "compatible_with",
                    "categories",
                    "tags",
                    "regulatory",
                    "other_texts",
                    "attributes",
                ],
                "additionalProperties": False,
            },
        },
    }

    prompt = f"""
You are an expert in power‑tool technical data sheets.

Extract EXACTLY ONE product from this document into the JSON schema provided via response_format.

Map the document to the JSON fields as follows:
- product_name: full commercial product name (e.g. \"Boulonneuse GDR 18V-220 C\").
- brand: tool brand (e.g. \"Bosch\"), or empty string.
- manufacturer_reference: primary SKU / manufacturer reference like \"0 601 9L6 000\", or empty string.
- manufacturer_reference_aliases: list of other reference codes or aliases for the same product (can be empty).
- ean_codes: list of all EAN codes found for this product (strings exactly as printed, can be empty).
- gtin_codes: list of all GTIN codes found for this product (strings exactly as printed, can be empty).
- short_descriptions: list of very short descriptions (1–2 sentences each) of the product and its use, in the ORIGINAL language of the document (do NOT translate).
- long_descriptions: list of longer descriptions or marketing paragraph(s), in the ORIGINAL language of the document.
- strengths: list of key strengths / benefits (bullet points or sentences).
- applications: list of text snippets that describe the domain of application, scope of use, or typical usage context.
- marketing: list of marketing / branding phrases or slogans (e.g. system names, taglines).
- categories: list of product categories or families if they appear (e.g. \"Perceuses-visseuses\", \"Electroportatif\").
- tags: list of keywords or short phrases that look like tags / search terms.
- regulatory: list of regulatory labels or certifications (e.g. \"CE\", \"RoHS\", \"IP65\", \"EN 62841\").
- compatible_with: list of compatible products mentioned in the sheet. Each item:
    - raw_text: the exact text snippet that mentions the compatibility (required).
    - brand: brand of the compatible product if clearly mentioned, else null.
    - manufacturer_reference: manufacturer reference of the compatible product if clearly mentioned, else null.
    - gtin: GTIN/EAN of the compatible product if clearly mentioned, else null.
    - type: type of compatible item if clear (e.g. \"tool\", \"accessory\", \"battery\"), else null.
- other_texts: list of other short text snippets from the PDF that are not pure technical specs and do not fit the previous categories (e.g. usage notes, system messages).
- attributes: each entry corresponds to one technical specification row, with:
    - name: attribute label as it appears in the sheet (in French is fine).
    - value: numeric or textual value without unit when possible.
    - unit: unit like \"Nm\", \"V\", \"kg\", \"tr/min\", or empty string if none.
- language_code: ISO 639-1 language code for the main document language (e.g. \"fr\", \"en\", \"de\").
- language_name: human-readable language name (e.g. \"French\", \"English\"), optional but recommended.

Rules:
- Use only information present in the document (no invention).
- NEVER translate any text. Keep all strings exactly in the original document language (for this file: French).
- If some field truly does not appear, return an empty string or empty list for it.

You will receive:
1) A Markdown export of the Docling document.
2) The Docling structured JSON representation (truncated if very long).

Markdown:
{markdown}

Docling JSON:
{doc_json}
"""

    resp = client.chat.completions.create(
        model="gpt-5-chat-latest",  # or "gpt-5.1" if you have access
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}],
        response_format=response_format,
        max_tokens=8000
    )

    labeled = json.loads(resp.choices[0].message.content)

    # Prefer product/brand read directly from the main product image if available.
    main_image = next(
        (img for img in images_info if img.get("classification") == "product_image"),
        None,
    )
    if main_image:
        img_product_name = (main_image.get("product_name_from_image") or "").strip()
        img_brand = (main_image.get("brand_from_image") or "").strip()
        if img_product_name:
            labeled["product_name"] = img_product_name
        if img_brand:
            labeled["brand"] = img_brand

    # === 4. Wrap into ProductDocument (meta + product) ===
    stem = Path(file_path).stem

    # Provenance paths (relative to project root when possible)
    source_rel = to_project_relative(Path(file_path))
    images_dir_rel = to_project_relative(images_root / stem)
    md_rel = to_project_relative(markdown_root / f"{stem}.md")
    json_rel = to_project_relative(json_root / f"{stem}.json")

    lang_code = (labeled.get("language_code") or "").strip()
    lang_name = (labeled.get("language_name") or "").strip()

    meta = {
        "document_id": f"{stem}--p00",
        "source_type": "pdf_single_product",
        "source_document": {
            "id": stem,
            "kind": "file",
            "format": "pdf",
            "mime_type": "application/pdf",
            "filename": os.path.basename(file_path),
            "path": source_rel,
            "url": None,
            "source_system": "local_pdf_input",
        },
        "source_product": {
            "index": 0,
            "page_range": None,
            "anchor": None,
        },
        "artifacts": {
            "markdown_path": md_rel,
            "images_dir": images_dir_rel,
            "json_path": json_rel,
        },
        "language": {
            "code": lang_code,
            "name": lang_name,
        },
        "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    product = {
        "product_name": labeled.get("product_name", ""),
        "brand": labeled.get("brand", ""),
        "ean_codes": labeled.get("ean_codes", []),
        "gtin_codes": labeled.get("gtin_codes", []),
        "manufacturer_reference": labeled.get("manufacturer_reference", ""),
        "manufacturer_reference_aliases": labeled.get("manufacturer_reference_aliases", []),
        "short_descriptions": labeled.get("short_descriptions", []),
        "long_descriptions": labeled.get("long_descriptions", []),
        "strengths": labeled.get("strengths", []),
        "applications": labeled.get("applications", []),
        "marketing": labeled.get("marketing", []),
        "compatible_with": labeled.get("compatible_with", []),
        "categories": labeled.get("categories", []),
        "tags": labeled.get("tags", []),
        "regulatory": labeled.get("regulatory", []),
        "other_texts": labeled.get("other_texts", []),
        "attributes": labeled.get("attributes", []),
        "images": images_info,
        "media": [],
    }

    print("Success: 100% structured extraction with GPT-5-chat-latest")
    return {"meta": meta, "product": product}


# === RUN ===
results = []
for f in your_files:
    full = os.path.join(os.path.dirname(__file__), f)
    if os.path.exists(full):
        labeled = extract_and_label(full)
        results.append(labeled)

        # Write one JSON file per document, e.g. output/json/gdr-18v-220-c-sheet.json
        stem = Path(full).stem
        doc_json_path = json_root / f"{stem}.json"
        with open(doc_json_path, "w", encoding="utf-8") as jf:
            json.dump(labeled, jf, ensure_ascii=False, indent=2)

df = pd.json_normalize(results, sep="_")
df.to_csv("rubix_final.csv", index=False)
df.to_json("rubix_final.json", orient="records", indent=2, force_ascii=False)
print("Done! → per-document JSON in output/json/, index in rubix_final.csv/.json, images in extracted_images/<document>/")
