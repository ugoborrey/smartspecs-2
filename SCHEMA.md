# Schéma de Base de Données PostgreSQL : Product Knowledge Hub (V2.0)

Ce document détaille le schéma PostgreSQL pour le "Product Knowledge Hub". L'architecture repose sur quatre tables :

1.  **Preuves Brutes** (`product_documents`)
2.  **Vue Canonique** (`products_canonical`)
3.  **Référence PIM** (`pim_canonical_attributes`)
4.  **Mappage Hybride** (`attribute_mappings`)

-----

## 1\. Schéma SQL Complet (4 Tables)

Voici le script SQL complet pour créer toutes les tables, les extensions et les index nécessaires.

```sql
-- Active l'extension pour générer des UUIDs (à n'exécuter qu'une fois par base de données)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-------------------------------------------------
-- TABLE 3 (Nouveau): pim_canonical_attributes (Référence PIM Officielle)
-- Liste de tous les attributs acceptés dans le PIM.
-------------------------------------------------
CREATE TABLE pim_canonical_attributes (
    id SERIAL PRIMARY KEY,
    canonical_key TEXT NOT NULL UNIQUE,  -- Ex: 'battery_voltage', 'bore_diameter'
    canonical_name_fr TEXT,              -- Nom convivial français
    canonical_name_en TEXT,              -- Nom convivial anglais
    data_type TEXT,                      -- Ex: 'number', 'text', 'unit_of_measure'
    pim_source_reference TEXT            -- ID ou référence de l'attribut dans le PIM source
);

-- Index pour la Foreign Key
CREATE UNIQUE INDEX idx_pim_canonical_attributes_key ON pim_canonical_attributes (canonical_key);


-------------------------------------------------
-- TABLE 4 (Nouveau): attribute_mappings (Le Thésaurus Hybride)
-- Mappe les noms d'attributs bruts vers la clé canonique PIM.
-------------------------------------------------
CREATE TABLE attribute_mappings (
    id SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,       -- Le nom brut trouvé (ex: "Voltage batterie")
    language_code TEXT NOT NULL,     -- La langue du source_name
    
    -- La clé officielle PIM. Référence pim_canonical_attributes
    canonical_key TEXT NOT NULL REFERENCES pim_canonical_attributes(canonical_key),

    UNIQUE(source_name, language_code)
);

-- Index de lookup pour le processus d'ingestion (CRUCIAL)
CREATE INDEX idx_attribute_mappings_source ON attribute_mappings (source_name, language_code);


-------------------------------------------------
-- TABLE 1: product_documents (Preuves brutes)
-- Source de vérité immuable.
-------------------------------------------------
CREATE TABLE product_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    document_id TEXT NOT NULL,
    source_type TEXT,
    language_code TEXT,
    source_document JSONB,
    artifacts JSONB,
    
    -- CORRECTION DE TYPO : TIMESTAMPTZ (avec le Z)
    extracted_at TIMESTAMPTZ, 

    ingested_at TIMESTAMPTZ DEFAULT NOW(),

    -- Champs "promus"
    manufacturer_reference TEXT,
    brand TEXT,
    product_name TEXT,

    payload JSONB NOT NULL
);

-------------------------------------------------
-- TABLE 2: products_canonical (Vue unifiée)
-- La meilleure vue actuelle du produit.
-------------------------------------------------
CREATE TABLE products_canonical (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Clé métier
    manufacturer_reference TEXT NOT NULL,
    brand TEXT NOT NULL,

    -- Champs canoniques
    canonical_product_name TEXT,
    language_code_preferred TEXT,
    canonical_payload JSONB,

    last_updated_at TIMESTAMPTZ
);

-------------------------------------------------
-- 5. Index et Contraintes
-------------------------------------------------

-- Index pour product_documents (recherches par produit/document/contenu)
CREATE INDEX idx_product_documents_mfg_ref_brand ON product_documents (manufacturer_reference, brand);
CREATE INDEX idx_product_documents_document_id ON product_documents (document_id);
CREATE INDEX idx_product_documents_payload_gin ON product_documents USING GIN (payload);

-- Contrainte UNIQUE sur products_canonical (une seule ligne par produit logique)
CREATE UNIQUE INDEX idx_products_canonical_mfg_ref_brand ON products_canonical (manufacturer_reference, brand);
```

-----

# 💡 Comprendre l'Architecture : La Stratégie derrière les Tables

L'architecture de ce **Product Knowledge Hub** est conçue pour résoudre le conflit classique entre la **flexibilité** (nécessaire pour ingérer des documents bruts variés) et la **rigueur** (nécessaire pour fournir des données fiables au PIM et aux applications).

Votre schéma repose sur la doctrine **séparation des préoccupations** (`Separation of Concerns`), divisant les données en trois couches logiques : la Preuve, la Référence et le Canon.

---

## I. Couche de Preuve et d'Exploration (Les Sources)

### 1. `product_documents` (La Preuve Brute, Immuable)

* **Rôle :** **Ce que nous avons vu.** Cette table est le **Data Lake** des données brutes structurées. Chaque ligne représente une *extraction* spécifique issue d'un document (PDF, Excel, Web).
* **Pourquoi le JSONB (`payload`) ?** Pour l'exploration. Le `JSONB` permet de stocker *toutes* les données non normalisées (y compris les erreurs et les incohérences) sans avoir à modifier le schéma SQL à chaque nouveau type de document ou attribut découvert. C'est idéal pour le machine learning, la recherche sémantique, et l'audit.
* **Contrainte :** Cette table est en mode **append-only** (on n'ajoute que des données). On ne modifie jamais une preuve après son ingestion.

---

## II. Couche de Référence et de Normalisation (Le Moteur)

Ces deux tables sont le pont entre le monde brut (`product_documents`) et le monde propre (`products_canonical`).

### 2. `pim_canonical_attributes` (La Référence Officielle)

* **Rôle :** **Ce qui doit être.** C'est le **catalogue de référence** des attributs définis par votre PIM. Elle impose la rigueur en définissant les seules clés d'attributs valides (ex: `battery_voltage`, `bore_diameter`).
* **Pourquoi séparer ?** Pour garantir que la structure et les règles (types de données, contraintes) de votre système central sont respectées, même lorsque vous traitez des données brutes.

### 3. `attribute_mappings` (Le Thésaurus Dynamique)

* **Rôle :** **Comment l'atteindre.** Cette table est le **dictionnaire de traduction** qui résout les synonymes (ex: "Tension Batterie" en `battery_voltage`).
* **Pourquoi l'Hybride (LLM + SQL) ?**
    * **LLM :** Gère la **maintenabilité** en automatisant la détection et la traduction des milliers de variations de langage et de fautes de frappe.
    * **SQL :** Assure la **performance** en production. Une fois le mapping résolu, le script de canonicalisation utilise un `JOIN` SQL très rapide, sans dépendre d'un appel API LLM en temps réel.

---

## III. Couche Canonique et d'Exploitation (La Sortie)

### 4. `products_canonical` (Le Fichier Produit Maître)

* **Rôle :** **Ce que nous fournissons.** C'est la **vue unique, propre et unifiée** de chaque produit logique (`manufacturer_reference` + `brand`).
* **Pourquoi une table séparée ?** C'est la table que toutes vos applications (E-commerce, API, ERP) interrogent. En la gardant séparée des preuves brutes, vous assurez une vitesse de lecture maximale et garantissez que les données sont toujours normalisées (attributs mappés, textes fusionnés).
* **Processus :** Elle est reconstruite périodiquement par le script de canonicalisation, qui agrège et résout les conflits à partir de toutes les preuves stockées dans `product_documents`, en utilisant le mapping des tables `pim_canonical_attributes` et `attribute_mappings`.

Cette structure garantit que **le PIM dicte la structure (la Référence)**, que **le LLM résout le bruit (le Mappage)**, et que **votre Hub stocke la vérité historique (la Preuve)** pour produire la donnée finale **(le Canon)**.
