from typing import List, Optional

from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    id: str
    kind: str
    format: str
    mime_type: Optional[str] = None
    filename: str
    path: str
    url: Optional[str] = None
    source_system: Optional[str] = None

    model_config = {"extra": "forbid"}


class SourceProduct(BaseModel):
    index: int
    page_range: Optional[List[int]] = None
    anchor: Optional[str] = None

    model_config = {"extra": "forbid"}


class Artifacts(BaseModel):
    markdown_path: Optional[str] = None
    images_dir: Optional[str] = None
    json_path: Optional[str] = None

    model_config = {"extra": "forbid"}


class Language(BaseModel):
    code: str
    name: str

    model_config = {"extra": "forbid"}


class Meta(BaseModel):
    document_id: str
    source_type: str
    source_document: SourceDocument
    source_product: SourceProduct
    artifacts: Artifacts
    language: Language
    extracted_at: str

    model_config = {"extra": "forbid"}


class CompatibleWithItem(BaseModel):
    raw_text: str
    brand: Optional[str] = None
    manufacturer_reference: Optional[str] = None
    gtin: Optional[str] = None
    type: Optional[str] = None

    model_config = {"extra": "forbid"}


class Attribute(BaseModel):
    name: str
    value: str
    unit: str

    model_config = {"extra": "forbid"}


class Image(BaseModel):
    id: str
    source: str
    page: Optional[int] = None
    file_path: Optional[str] = None
    filename: Optional[str] = None
    url: Optional[str] = None
    classification: str
    description: str
    product_name_from_image: str
    brand_from_image: str

    model_config = {"extra": "forbid"}


class Media(BaseModel):
    type: str
    title: str
    language_code: str
    url: str
    source: str

    model_config = {"extra": "forbid"}


class Product(BaseModel):
    product_name: str
    brand: str
    ean_codes: List[str] = Field(default_factory=list)
    gtin_codes: List[str] = Field(default_factory=list)
    manufacturer_reference: str
    manufacturer_reference_aliases: List[str] = Field(default_factory=list)
    short_descriptions: List[str] = Field(default_factory=list)
    long_descriptions: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    applications: List[str] = Field(default_factory=list)
    marketing: List[str] = Field(default_factory=list)
    compatible_with: List[CompatibleWithItem] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    regulatory: List[str] = Field(default_factory=list)
    attributes: List[Attribute] = Field(default_factory=list)
    images: List[Image] = Field(default_factory=list)
    media: List[Media] = Field(default_factory=list)
    other_texts: List[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class ProductDocument(BaseModel):
    meta: Meta
    product: Product

    model_config = {"extra": "forbid"}
