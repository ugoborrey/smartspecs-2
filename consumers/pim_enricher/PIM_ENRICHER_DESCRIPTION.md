# 🚀 PIM ENRICHER : ARCHITECTURE DE RÉFÉRENCE ET CONTEXTE

## I. Contexte Général du Projet (PIM et PKH)

Le projet s'inscrit dans une démarche de fiabilisation et d'enrichissement massif des données produits en vue d'une diffusion omnicanale (sites e-commerce, catalogue, etc.).

### A. Le PIM (Product Information Management)

Le PIM (système de gestion des informations produit) est la **source de vérité (System of Record)** pour la gestion quotidienne des fiches produits.

* **Rôle :** Gérer les codes articles (SKU), les références fournisseurs, les prix, la logistique et les attributs structurés.
* **Problématique :** Les données y sont souvent incomplètes, hétérogènes, et les valeurs d'attributs peuvent ne pas être normalisées (ex: attributs de type **List of Value (LoV)** non renseignés ou mal renseignés).
* **Format d'Entrée :** Le PIM Enricher utilise un **export PIM** (fichiers Excel/CSV Rubix) qui contient les produits à mettre à jour et les règles de validation (via la feuille "AttributesPossibleValues").

### B. Le PKH (Product Knowledge Hub)

Le PKH est le référentiel central de **données produit normalisées, nettoyées et enrichies**.

* **Rôle :** Servir de **source de connaissance canonique** (standardisée) pour tous les produits du catalogue.
* **Contenu :** Chaque fiche produit dans le PKH possède un `canonical_payload` riche, incluant des attributs, des textes, et des métadonnées (documents, liens), tous normalisés selon un modèle de données cohérent, indépendant des nomenclatures PIM.
* **Communication :** Le PIM Enricher communique avec le PKH via une **API REST** pour récupérer cette fiche canonique.

### C. Le Rôle du PIM Enricher

Le PIM Enricher est la passerelle métier qui **boucle la boucle** : il consomme la donnée riche et standardisée du PKH pour la réinjecter dans la structure rigide et technique du PIM, en respectant ses contraintes (LoV, format).

---

## II. Objectif et Rôle du Module PIM Enricher

| Rôle | Détail |
| :--- | :--- |
| **Objectif Principal** | Recevoir un export PIM, effectuer un mapping sémantique entre les données canoniques du PKH et les attributs PIM cibles, et générer un fichier de sortie conforme. |
| **Mode d'Enrichissement (MVP)** | **`OVERWRITE_ALL`** : Toutes les valeurs existantes dans les colonnes d'attributs ciblées sont écrasées par les propositions du LLM. |
| **Scope d'Enrichissement** | Uniquement les **attributs structurés** (LoV, Unité, Texte Libre). Les grands textes descriptifs sont exclus de l'enrichissement direct, mais leur contenu sert de contexte au LLM. |

---

## III. Flux Architectural Global

Le module est une application d'orchestration **orientée-fichier** et **orientée-API**.

1.  **Parsing des Inputs** : Lecture de l'Excel (Produits) et de la feuille des règles LoV ("AttributesPossibleValues").
2.  **Pré-traitement/Filtrage** : Création des tables de correspondance internes et nettoyage des données techniques (codes, classes) avant l'envoi au LLM.
3.  **Recherche PKH (API)** : Pour chaque produit, appel à l'API REST du PKH (clé de recherche : `Manufacturer Reference` + `Brand`).
4.  **Génération du Schéma Pydantic** : Construction dynamique du schéma de sortie JSON pour le LLM, intégrant les contraintes LoV spécifiques au produit.
5.  **Appel LLM (Mapping Déterministe)** : Envoi du Prompt (contexte PKH maximal + cibles nettoyées) et du Schéma Pydantic (contrainte de réponse).
6.  **Post-traitement/Reconstruction** : Utilisation des tables de correspondance pour réintégrer les codes PIM et remplir le fichier Excel d'origine.
7.  **Output** : Mise à disposition du fichier Excel enrichi pour le téléchargement.

---

## IV. Pré-traitement : Nettoyage et Tables Internes

Cette phase garantit l'efficacité du LLM en le concentrant sur la sémantique.

### A. Table de Correspondance LoV

Le PIM Enricher doit associer les `Possible Value` à une clé composite rigide :

* **Clé de Look-up :** Combinaison de la **PIM M Class** du produit (ex: `'40-10-15-25-30'`) et de l'**Attribute Code** (ex: `'5110'`).
* **Valeur :** La liste exacte des valeurs de la LoV (ex: `['Oui', 'Non', 'IP65']`).

### B. Décomposition de la Cible (Input LLM)

Le PIM Enricher isole les données techniques du PIM pour le LLM et crée une table de correspondance interne (ex: `ETANCHEITE` $\leftrightarrow$ `5110_Etancheité`) :

**Données Exclues du LLM (Gérées en interne) :**
* `PIM M Class` (ex: `'40-10-15-25-30'`)
* `Attribute Code` (ex: `'5110'`)
* `Variant ID`, `Product Range Code`

---

## V. Stratégie LLM : Contexte et Contrainte

### A. Input JSON (Contexte Maximal)

Le JSON d'entrée est structuré pour maximiser l'information contextuelle pour le LLM.

* `data_source_pkh` : Contient la fiche canonique complète (attributs canoniques, `product_name`, `brand`, tous les textes descriptifs).
* `enrichment_targets` : Liste des attributs à enrichir, utilisant des clés sémantiques (ex: `attribute_key`: `"ETANCHEITE"`) et les règles de LoV spécifiques à cette clé.

### B. Contrainte Pydantic Dynamique

C'est le mécanisme de validation. Le PIM Enricher :

1.  Génère une classe **Pydantic** de sortie pour chaque appel LLM.
2.  Mappe les cibles de type **LoV** à des champs **`Enum`** au sein de cette classe, avec les valeurs exactes des LoV extraites par le pré-traitement.
3.  **Résultat :** Le LLM est contraint par l'API à ne répondre qu'avec des valeurs qui existent dans les LoV, ou `null` si aucune preuve n'est trouvée (laissant la cellule vide).

### C. Instructions du Prompt

Le Prompt doit insister sur :
1.  Le **Mapping Sémantique** entre les clés PKH (canoniques) et les clés PIM (sémantiques).
2.  L'obligation de **respecter le schéma JSON** (Pydantic).
3.  La règle de laisser la valeur vide (`null` dans le JSON) si le LLM n'est pas certain du mapping.

---

## VI. Post-traitement : Reconstruction du Fichier

1.  **Réception et Validation** : Le PIM Enricher reçoit le JSON validé du LLM.
2.  **Mapping Inverse** : Il utilise la **Table de Correspondance Interne** pour mapper les clés sémantiques (ex: `ETANCHEITE`) à leur nom de colonne complet (ex: `5110_Etancheité`).
3.  **Mise à Jour** : Les valeurs sont insérées dans la ligne Excel du produit concerné, écrasant les données précédentes selon le mode `OVERWRITE_ALL`.
4.  **Finalisation** : Le fichier Excel est sauvegardé en conservant strictement le format d'origine, y compris l'ordre des colonnes et les données non enrichies.