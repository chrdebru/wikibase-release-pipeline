import csv
import json
import sys
import urllib3
from pathlib import Path
from typing import Optional

# Allow importing WikibaseClient from the ontology scripts
sys.path.insert(0, str(Path(__file__).parent.parent / "1-ontology"))
from wikibase_client import WikibaseClient, load_config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_DIR = Path(__file__).parent

SKIP_COLUMNS = {"Nom"}
DESCRIPTION_COLUMN = "Description"

# Datatypes whose values are stored as plain strings in the Wikibase API
STRING_DATATYPES = {"string", "url", "external-id", "monolingualtext", "commonsMedia"}


# -----------------------------------------------------------------------------
# Search
# -----------------------------------------------------------------------------

def search_entity_by_label(client: WikibaseClient, label: str, entity_type: str,
                            language: str = "fr") -> Optional[str]:
    """Returns the entity ID if an exact label match is found, else None."""
    response = client.session.get(client.api_url, params={
        "action": "wbsearchentities",
        "search": label,
        "language": language,
        "type": entity_type,
        "format": "json",
        "limit": 10,
    })
    response.raise_for_status()
    for result in response.json().get("search", []):
        if result["label"].strip().lower() == label.strip().lower():
            return result["id"]
    return None


def get_property_datatype(client: WikibaseClient, prop_id: str) -> Optional[str]:
    """Returns the Wikibase datatype of a property (e.g. 'string', 'url', 'wikibase-item')."""
    response = client.session.get(client.api_url, params={
        "action": "wbgetentities",
        "ids": prop_id,
        "props": "datatype",
        "format": "json",
    })
    response.raise_for_status()
    entity = response.json().get("entities", {}).get(prop_id, {})
    return entity.get("datatype")


# -----------------------------------------------------------------------------
# Create / Update
# -----------------------------------------------------------------------------

def create_item(client: WikibaseClient, label: str, language: str = "fr") -> str:
    data = {"labels": {language: {"language": language, "value": label}}}
    response = client.session.post(client.api_url, data={
        "action": "wbeditentity",
        "new": "item",
        "data": json.dumps(data),
        "token": client.get_csrf_token(),
        "format": "json",
    })
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise RuntimeError(f"Error creating item '{label}': {result['error']}")
    return result["entity"]["id"]


def find_or_create_item(client: WikibaseClient, label: str,
                        language: str = "fr") -> tuple[str, bool]:
    """Returns (entity_id, created). Creates the item if it does not exist."""
    existing_id = search_entity_by_label(client, label, "item", language=language)
    if existing_id:
        return existing_id, False
    return create_item(client, label, language), True


def set_description(client: WikibaseClient, entity_id: str,
                    description: str, language: str = "fr") -> None:
    data = {"descriptions": {language: {"language": language, "value": description}}}
    response = client.session.post(client.api_url, data={
        "action": "wbeditentity",
        "id": entity_id,
        "data": json.dumps(data),
        "token": client.get_csrf_token(),
        "format": "json",
    })
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise RuntimeError(f"Error setting description on {entity_id}: {result['error']}")


def has_item_claim(client: WikibaseClient, entity_id: str,
                   property_id: str, value_id: str) -> bool:
    response = client.session.get(client.api_url, params={
        "action": "wbgetclaims",
        "entity": entity_id,
        "property": property_id,
        "format": "json",
    })
    response.raise_for_status()
    for claim in response.json().get("claims", {}).get(property_id, []):
        snak = claim.get("mainsnak", {})
        if snak.get("snaktype") == "value":
            if snak["datavalue"]["value"].get("id") == value_id:
                return True
    return False


def has_string_claim(client: WikibaseClient, entity_id: str,
                     property_id: str, value: str) -> bool:
    response = client.session.get(client.api_url, params={
        "action": "wbgetclaims",
        "entity": entity_id,
        "property": property_id,
        "format": "json",
    })
    response.raise_for_status()
    for claim in response.json().get("claims", {}).get(property_id, []):
        snak = claim.get("mainsnak", {})
        if snak.get("snaktype") == "value":
            if snak.get("datavalue", {}).get("value") == value:
                return True
    return False


def create_property(client: WikibaseClient, fr_label: str,
                    datatype: str = "string") -> str:
    data = {
        "labels": {"fr": {"language": "fr", "value": fr_label}},
        "datatype": datatype,
    }
    response = client.session.post(client.api_url, data={
        "action": "wbeditentity",
        "new": "property",
        "data": json.dumps(data),
        "token": client.get_csrf_token(),
        "format": "json",
    })
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise RuntimeError(f"Error creating property '{fr_label}': {result['error']}")
    return result["entity"]["id"]


def add_item_claim(client: WikibaseClient, entity_id: str,
                   property_id: str, value_id: str) -> None:
    response = client.session.post(client.api_url, data={
        "action": "wbcreateclaim",
        "entity": entity_id,
        "snaktype": "value",
        "property": property_id,
        "value": json.dumps({"entity-type": "item", "numeric-id": int(value_id[1:])}),
        "token": client.get_csrf_token(),
        "format": "json",
    })
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise RuntimeError(f"Error adding item claim on {entity_id}: {result['error']}")


def add_string_claim(client: WikibaseClient, entity_id: str,
                     property_id: str, value: str) -> None:
    response = client.session.post(client.api_url, data={
        "action": "wbcreateclaim",
        "entity": entity_id,
        "snaktype": "value",
        "property": property_id,
        "value": json.dumps(value),
        "token": client.get_csrf_token(),
        "format": "json",
    })
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise RuntimeError(f"Error adding string claim on {entity_id}: {result['error']}")


# -----------------------------------------------------------------------------
# Column processing
# -----------------------------------------------------------------------------

# When a property is not found by exact column name, these prefixes are tried
# in order before falling back to creating a new property. Extend as needed.
PROPERTY_LABEL_PREFIXES = [
    "a ",
    "de "
]


def resolve_property(client: WikibaseClient, column: str) -> tuple[str, str]:
    """Finds or creates a property for the given column name.

    Tries the exact column name first, then each prefix in PROPERTY_LABEL_PREFIXES.
    Falls back to creating a new string property if nothing is found.

    Returns (prop_id, datatype).
    """
    candidates = [column] + [f"{prefix}{column}" for prefix in PROPERTY_LABEL_PREFIXES]

    for candidate in candidates:
        prop_id = search_entity_by_label(client, candidate, "property", language="fr")
        if prop_id:
            if candidate != column:
                print(f"      RESOLVED '{column}' -> property '{candidate}' ({prop_id})")
            return prop_id, get_property_datatype(client, prop_id)

    prop_id = create_property(client, column, datatype="string")
    print(f"      CREATED property '{column}' ({prop_id}) [string]")
    return prop_id, "string"


def process_column(client: WikibaseClient, item_id: str,
                   column: str, value: str) -> None:
    """Resolves the property for a column and adds the appropriate claim."""
    prop_id, datatype = resolve_property(client, column)

    if datatype == "wikibase-item":
        target_id, created = find_or_create_item(client, value, language="fr")
        action = "CREATED" if created else "FOUND"
        if has_item_claim(client, item_id, prop_id, target_id):
            print(f"      EXISTS  [{column}] -> '{value}' ({target_id})")
        else:
            add_item_claim(client, item_id, prop_id, target_id)
            print(f"      LINKED  [{column}] -> '{value}' ({target_id}) [{action}]")

    elif datatype in STRING_DATATYPES:
        if has_string_claim(client, item_id, prop_id, value):
            print(f"      EXISTS  [{column}] = '{value}'")
        else:
            add_string_claim(client, item_id, prop_id, value)
            print(f"      SET     [{column}] = '{value}'")

    else:
        print(f"      SKIP  column '{column}': unsupported datatype '{datatype}'")


# -----------------------------------------------------------------------------
# CSV helpers
# -----------------------------------------------------------------------------

def find_platform_csv(platform_folder: Path) -> Optional[Path]:
    """Finds the CSV file whose name contains 'Plateforme technologique' (not _all)."""
    for csv_file in platform_folder.rglob("Plateforme technologique*.csv"):
        if not csv_file.stem.endswith("_all"):
            return csv_file
    return None


def read_platform_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    config = load_config()
    client = WikibaseClient(**config)

    # ------------------------------------------------------------------
    # Step 1: Resolve required property and class IDs dynamically
    # ------------------------------------------------------------------
    print("\n=== Step 1: Resolving 'instance of' property and 'Plateforme technologique' item ===")

    instance_of_prop_id = search_entity_by_label(client, "est une instance de", "property", language="fr")
    if not instance_of_prop_id:
        print("  ERROR: Could not find property 'est une instance de' in Wikibase. Run populate_object_properties.py first.")
        sys.exit(1)
    print(f"  FOUND  'est une instance de' property ({instance_of_prop_id})")

    platform_class_id = search_entity_by_label(client, "Plateforme technologique", "item", language="fr")
    if not platform_class_id:
        print("  ERROR: Could not find item 'Plateforme technologique' in Wikibase. Run populate.py first.")
        sys.exit(1)
    print(f"  FOUND  'Plateforme technologique' item ({platform_class_id})")

    # ------------------------------------------------------------------
    # Step 2: Process each platform folder
    # ------------------------------------------------------------------
    print("\n=== Step 2: Processing platform folders ===")

    platform_folders = [p for p in DATA_DIR.iterdir() if p.is_dir()]
    if not platform_folders:
        print("  No platform folders found.")
        return

    for folder in sorted(platform_folders):
        csv_path = find_platform_csv(folder)
        if not csv_path:
            print(f"  SKIP  {folder.name}: no 'Plateforme technologique' CSV found")
            continue

        rows = read_platform_rows(csv_path)
        if not rows:
            print(f"  SKIP  {folder.name}: CSV is empty")
            continue

        for row in rows:
            platform_name = row.get("Nom", "").strip()
            if not platform_name:
                continue

            print(f"\n  Processing: {platform_name} (from {folder.name})")

            # Create or find the item
            existing_id = search_entity_by_label(client, platform_name, "item", language="fr")
            if existing_id:
                print(f"    EXISTS  item '{platform_name}' ({existing_id})")
                item_id = existing_id
            else:
                item_id = create_item(client, platform_name)
                print(f"    CREATED item '{platform_name}' ({item_id})")

            # Add 'instance of' -> 'Plateforme technologique' claim
            if has_item_claim(client, item_id, instance_of_prop_id, platform_class_id):
                print(f"    EXISTS  instance of -> Plateforme technologique")
            else:
                add_item_claim(client, item_id, instance_of_prop_id, platform_class_id)
                print(f"    LINKED  {platform_name} ({item_id}) -[instance of]-> Plateforme technologique ({platform_class_id})")

            # Process remaining columns
            for column, value in row.items():
                if column in SKIP_COLUMNS or not value or not value.strip():
                    continue

                value = value.strip()

                if column == DESCRIPTION_COLUMN:
                    set_description(client, item_id, value, language="fr")
                    print(f"    SET     description (fr) = '{value[:60]}{'...' if len(value) > 60 else ''}'")
                else:
                    process_column(client, item_id, column, value)

    print("\nDone.")


if __name__ == "__main__":
    main()
