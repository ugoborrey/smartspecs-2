-- Product Knowledge Hub schema (extracted from SCHEMA.md)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table pim_canonical_attributes
CREATE TABLE IF NOT EXISTS pim_canonical_attributes (
    id SERIAL PRIMARY KEY,
    canonical_key TEXT NOT NULL UNIQUE,
    canonical_name_fr TEXT,
    canonical_name_en TEXT,
    data_type TEXT,
    pim_source_reference TEXT
);

-- Table attribute_mappings
CREATE TABLE IF NOT EXISTS attribute_mappings (
    id SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    language_code TEXT NOT NULL,
    canonical_key TEXT NOT NULL REFERENCES pim_canonical_attributes(canonical_key),
    UNIQUE (source_name, language_code)
);
CREATE INDEX IF NOT EXISTS idx_attribute_mappings_source ON attribute_mappings (source_name, language_code);

-- Table product_documents (evidence)
CREATE TABLE IF NOT EXISTS product_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id TEXT NOT NULL,
    source_type TEXT,
    language_code TEXT,
    source_document JSONB,
    artifacts JSONB,
    extracted_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    manufacturer_reference TEXT,
    brand TEXT,
    product_name TEXT,
    payload JSONB NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_product_documents_document_id ON product_documents (document_id);
CREATE INDEX IF NOT EXISTS idx_product_documents_mfg_ref_brand ON product_documents (manufacturer_reference, brand);
CREATE INDEX IF NOT EXISTS idx_product_documents_document_id ON product_documents (document_id);
CREATE INDEX IF NOT EXISTS idx_product_documents_payload_gin ON product_documents USING GIN (payload);

-- Table products_canonical
CREATE TABLE IF NOT EXISTS products_canonical (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    manufacturer_reference TEXT NOT NULL,
    brand TEXT NOT NULL,
    canonical_product_name TEXT,
    language_code_preferred TEXT,
    canonical_payload JSONB,
    last_updated_at TIMESTAMPTZ,
    UNIQUE (manufacturer_reference, brand)
);
