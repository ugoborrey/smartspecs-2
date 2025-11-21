# Docling‑3 Product Sheet Extractor

This project processes PDF product data sheets with [Docling](https://github.com/DS4SD/docling) and OpenAI, extracting fully structured product data, images, and a tabular index.

## What it does

- Reads all PDF files from `input/`.
- Uses Docling to convert each PDF to structured text plus images.
- Classifies extracted images (product photo, logo, diagram, etc.).
- Calls `gpt-5-chat-latest` (and `gpt-4o` for vision) to extract a single product per PDF into a strict JSON schema.
- Writes:
  - Per‑document JSON to `output/json/<document-stem>.json`.
  - Per‑document images to `extracted_images/<document-stem>/`.
  - A flattened index of all products to `rubix_final.csv` and `rubix_final.json`.

## Project layout

- `single-product-pdf.py` – main script that runs the full pipeline for single-product PDFs.
- `bosch-excel-pim.py` – direct mapping from a Bosch PIM Excel/CSV export to ProductDocument (no LLM).
- `input/` – source PDFs to process.
- `extracted_images/` – classified PNG images extracted from each PDF.
- `output/json/` – structured JSON for each processed PDF.
- `rubix_final.csv` / `rubix_final.json` – aggregated table of all extracted products.

## Requirements

Python 3.10+ is recommended.

Required Python packages (install via `pip` or pin in your own `requirements.txt`):

- `openai`
- `docling`
- `pandas`
- `pillow`
- `python-dotenv`
- `pydantic`

You also need access to the OpenAI models:

- `gpt-5-chat-latest` (or `gpt-5.1` compatible model) for structured extraction.
- `gpt-4o-2024-11-20` (or a compatible GPT‑4o vision model) for image classification.

## Configuration

Authentication is handled via environment variables loaded by `python-dotenv`.

Create a `.env` file in the project root with at least:

```bash
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1  # or your endpoint
```

Adjust the base URL if you are using a gateway or proxy.

The script currently looks for input PDFs in `input/` and writes outputs relative to the project root; change `input_dir`, `images_root`, or `json_root` in `single-product-pdf.py` if you want different paths.

## Installation

1. Create and activate a virtual environment (optional but recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install openai docling pandas pillow python-dotenv pydantic
   ```
3. Create the `.env` file (see Configuration above).

## Usage

1. Place one or more PDF product data sheets into the `input/` folder.
2. Run the pipeline:
   ```bash
   python single-product-pdf.py

Run the Bosch Excel/CSV extractor:

   python bosch-excel-pim.py --input bosch-excel-example-10-products.xlsx
   ```
3. Inspect results:
   - Per‑PDF JSON: `output/json/<your-file-stem>.json`
   - Extracted + classified images: `extracted_images/<your-file-stem>/`
   - Combined table of all products: `rubix_final.csv` and `rubix_final.json`

The JSON schema captured in `single-product-pdf.py` includes fields such as `product_name`, `brand`, `ean`, `gtin`, `manufacturer_reference`, `short_description`, `long_description`, `advantages`, `strengths`, `scope`, `marketing`, `other`, and a list of `attributes` (name, value, unit) representing the technical data rows.

## Customization tips

- **Change model names** – update the `model=` parameters in `single-product-pdf.py` if your account exposes different model IDs.
- **Adapt schema** – modify the `response_format` JSON schema in `single-product-pdf.py` if you need additional fields or different naming.
- **Filter images** – adjust the logic around `classification` in `describe_and_classify_image` if you want to ignore certain image types or focus only on product photos.

## Limitations

- The extraction quality depends on the underlying OCR and layout analysis done by Docling; poor scans may yield incomplete text.
- Only one product per PDF is extracted; multi‑product catalog pages are not split out individually.
- The script assumes French for the included sample sheets and instructs the model not to translate, but it can be adapted to other languages by adjusting the prompt.
