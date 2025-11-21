
# 🚀 Stratégie de Normalisation Hybride des Attributs

## Objectif

La stratégie hybride vise à résoudre le problème de la maintenance manuelle des tables de mappage d'attributs, tout en garantissant que le processus de canonicalisation reste **rapide**, **déterministe** et **cohérent** avec la liste officielle des attributs de votre PIM (Product Information Management).

Cette approche utilise un **LLM** pour le travail lent et intelligent de **découverte** et de **proposition de mapping** (une tâche de maintenance), et le **SQL** pour l'exécution rapide et fiable du **lookup** (la tâche de production).

-----

## I. Schéma des Tables Clés

Nous aurons besoin de deux tables principales pour ce workflow, en plus de `product_documents` et `products_canonical`.

### 1\. Table de Référence : `pim_canonical_attributes`

C'est la liste de tous les attributs acceptés dans votre écosystème. Elle est alimentée par une synchronisation avec votre PIM.

```sql
CREATE TABLE pim_canonical_attributes (
    -- ID technique
    id SERIAL PRIMARY KEY,

    -- Clé du dictionnaire d'attributs (la clé de fusion)
    canonical_key TEXT NOT NULL UNIQUE,  -- Ex: 'battery_voltage', 'bore_diameter'

    -- Nom convivial dans une langue de référence (pour le Data Steward)
    canonical_name_fr TEXT,              -- Ex: 'Tension de la batterie'
    canonical_name_en TEXT,              -- Ex: 'Battery Voltage'

    -- Type de donnée (pour validation, ex: 'number', 'text', 'unit_of_measure')
    data_type TEXT, 
    
    -- ID ou référence de l'attribut dans le PIM source
    pim_source_reference TEXT
);

-- Index pour une recherche rapide par clé de fusion
CREATE UNIQUE INDEX idx_pim_canonical_attributes_key ON pim_canonical_attributes (canonical_key);
```

### 2\. Table de Mappage : `attribute_mappings` (Le Thésaurus)

C'est la table construite et maintenue par le LLM. Elle mappe les noms trouvés dans les PDF bruts vers la clé officielle du PIM.

```sql
CREATE TABLE attribute_mappings (
    id SERIAL PRIMARY KEY,

    -- Le nom brut trouvé dans le document (Source)
    source_name TEXT NOT NULL,       -- Ex: "Voltage batterie", "Diam. Alésage"
    
    -- La langue du source_name
    language_code TEXT NOT NULL,     -- Ex: 'fr', 'en'
    
    -- La clé officielle PIM vers laquelle ce source_name mappe (Cible)
    canonical_key TEXT NOT NULL REFERENCES pim_canonical_attributes(canonical_key),

    -- Clé unique pour éviter les doublons
    UNIQUE(source_name, language_code)
);

-- Index de lookup pour le processus d'ingestion (CRUCIAL)
CREATE INDEX idx_attribute_mappings_source ON attribute_mappings (source_name, language_code);
```

-----

## II. Workflow 1 : Maintenance du Mapping (LLM-Assistée)

Ce script de maintenance est exécuté en *batch* (ex: une fois par jour ou après l'ingestion d'un nouveau lot de documents) pour découvrir les nouveaux termes et mettre à jour la table `attribute_mappings`.

### Étape A : Découverte des Orphelins (SQL)

Le script identifie tous les `source_name` dans `product_documents` qui n'ont pas encore de mapping dans `attribute_mappings`.

**Action SQL** : Utiliser la requête `LEFT JOIN` ou `NOT EXISTS` pour identifier les attributs non mappés.

### Étape B : Mappage en Batch (LLM)

Le script envoie les termes non mappés (max. 100-200 à la fois pour rester sous les limites des tokens) au LLM, en lui fournissant la liste officielle du PIM comme contexte.

#### Prompt du LLM

| Rôle | Contenu |
| :--- | :--- |
| **Système** | Tu es un expert en normalisation de données produit. Ta mission est de mapper des noms d'attributs source vers la liste canonique. Ton jugement doit être strict. Réponds *uniquement* avec un objet JSON. |
| **Contexte** | **Liste Officielle Canonique PIM :** Fournir la liste `canonical_key` de la table `pim_canonical_attributes`. Ex: `['battery_voltage', 'bore_diameter', 'outside_diameter', ...]` |
| **Utilisateur** | Mappe les attributs source non résolus suivants vers une clé de la liste canonique fournie. Utilise `null` si aucune correspondance claire n'est trouvée. <br><br> Liste à mapper : `[ { "source_name": "Voltage batterie", "lang": "fr" }, { "source_name": "Diam. Alésage", "lang": "fr" }, { "source_name": "Longueur fil", "lang": "fr" } ]` |

### Étape C : Insertion (SQL)

Le script reçoit le JSON du LLM et insère les nouveaux mappings (où `canonical_key` est valide) dans la table `attribute_mappings`.

  * **Contrôle Humain (Optionnel) :** Les cas mappés sur `null` (ou les 10% des cas les moins sûrs selon l'API LLM) peuvent être mis de côté pour une revue manuelle par le Data Steward, minimisant ainsi le travail manuel.

-----

## III. Workflow 2 : Canonicalisation (Chemin Rapide SQL)

Lorsqu'un nouveau `ProductDocument` est ingéré et que la fiche `products_canonical` doit être rafraîchie, la performance est cruciale.

### Processus

1.  Le script de canonicalisation récupère tous les `product_documents` pour un produit.
2.  Pour la phase de fusion des attributs, il ne fait **aucun appel LLM**.
3.  Il utilise une **requête SQL** pour normaliser chaque attribut avant la fusion :

<!-- end list -->

```sql
SELECT
    m.canonical_key AS name,
    attr.value,
    attr.unit
FROM
    product_documents p,
    -- Décomposition des attributs du document brut
    jsonb_to_recordset(p.payload -> 'attributes') AS attr(name TEXT, value TEXT, unit TEXT)
JOIN
    attribute_mappings m ON m.source_name = attr.name AND m.language_code = p.language_code
WHERE
    p.manufacturer_reference = '...'
    AND p.brand = '...'
-- Les attributs pour lesquels aucun mapping n'existe sont ignorés (ou mis en quarantaine)
```

### Avantages de l'Exécution (Production)

  * **Vitesse :** L'opération se résume à une décomposition JSONB suivie d'un `JOIN` sur des tables indexées. L'exécution prend des millisecondes.
  * **Déterminisme :** Le résultat dépend uniquement du contenu de la table `attribute_mappings`, qui est une source de vérité stable.
  * **Coût :** Zéro coût d'API LLM en production.

Cette stratégie permet de concilier la complexité des données brutes hétérogènes avec le besoin de rigueur et de performance de votre Product Knowledge Hub.