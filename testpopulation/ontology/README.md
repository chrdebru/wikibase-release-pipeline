# Ontology Population Scripts

These scripts populate a Wikibase instance with ontology data — classes and properties — sourced from CSV files. They are idempotent: re-running them will update existing entities rather than create duplicates.

## Prerequisites

Install the required Python dependencies:

```bash
pip install requests python-dotenv
```

The scripts read connection details from `deploy/.env` (relative to the repository root). That file must contain:

```
WIKIBASE_PUBLIC_HOST=your-wikibase-hostname
MW_ADMIN_NAME=your-admin-username
MW_ADMIN_PASS=your-admin-password
```

## Running order

Run the scripts from within the `ontology/` directory in this order:

```bash
cd testpopulation/ontology

python populate.py                   # 1. Classes
python populate_data_properties.py   # 2. Data properties
python populate_object_properties.py # 3. Object properties
```

Classes must be created first because the property scripts link properties to class items by label.

## What each script does

### `populate.py`

Reads `classes_with_english_translations.csv` and:

1. Creates or updates a Wikibase item for each class (French and English labels, descriptions, and aliases).
2. Ensures a `sous-classe de` / `subclass of` property exists.
3. Links each class to its parent class using that property.

### `populate_data_properties.py`

Reads `data_properties_with_english_translations.csv` and:

1. Ensures a `domaine` / `domain` meta-property exists.
2. Creates or updates each data property, mapping the CSV `Portée` column to a Wikibase datatype (`string`, `url`, `external-id`, or `time`).
3. Links each property to its domain class item.

### `populate_object_properties.py`

Reads `object_properties_with_english_translations.csv` and:

1. Ensures both `domaine` / `domain` and `portée` / `range` meta-properties exist.
2. Creates or updates each object property (all typed as `wikibase-item`).
3. Links each property to its domain and range class items.

## Verifying the connection

To verify that credentials and connectivity are correct before running the population scripts:

```bash
python wikibase_client.py
```

This logs in and prints a CSRF token if the connection succeeds.

## CSV files

| File | Used by |
|------|---------|
| `classes_with_english_translations.csv` | `populate.py` |
| `data_properties_with_english_translations.csv` | `populate_data_properties.py` |
| `object_properties_with_english_translations.csv` | `populate_object_properties.py` |

The files prefixed with `Classes`, `Propriétés de données`, and `Propriétés d'objet` are the original exports from Notion and are kept for reference.
