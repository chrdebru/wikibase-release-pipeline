import csv
import json
import re
import sys
import unicodedata
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

def strip_reference(value: str) -> str:
    """Remove any '(https://...)' or '(path/to/file.md)' parenthetical from a value."""
    value = re.sub(r'\s*\(https?://[^)]+\)', '', value)
    value = re.sub(r'\s*\([^)]*\.md\)', '', value)
    return value.strip()


def split_item_values(value: str) -> list[str]:
    """Split a comma-separated list of item references and strip each one."""
    return [label for part in value.split(",") if (label := strip_reference(part).strip())]


def normalize_label(label: str) -> str:
    """Lowercase + strip + replace typographic apostrophes so comparisons are
    not tripped up by curly-quote vs straight-quote mismatches between CSV
    data and Wikibase stored labels."""
    label = unicodedata.normalize("NFC", label)
    label = label.replace("\u2019", "'").replace("\u2018", "'")
    return label.strip().lower()


def search_entity_by_label(client: WikibaseClient, label: str, entity_type: str,
                            language: str = "fr") -> Optional[str]:
    """Returns the entity ID if an exact label match is found, else None."""
    response = client.session.get(client.api_url, params={
        "action": "wbsearchentities",
        "search": normalize_label(label),
        "language": language,
        "type": entity_type,
        "format": "json",
        "limit": 10,
    })
    response.raise_for_status()
    for result in response.json().get("search", []):
        if normalize_label(result["label"]) == normalize_label(label):
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

_item_cache: dict[str, str] = {}


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
    """Returns (entity_id, created).

    Checks the local cache first, then searches Wikibase by label.
    Only creates a new item if no existing item with that label is found.
    """
    cache_key = normalize_label(label)
    if cache_key in _item_cache:
        return _item_cache[cache_key], False

    existing_id = search_entity_by_label(client, label, "item", language=language)
    if existing_id:
        _item_cache[cache_key] = existing_id
        return existing_id, False

    item_id = create_item(client, label, language)
    _item_cache[cache_key] = item_id
    return item_id, True


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
        for label in split_item_values(value):
            target_id, created = find_or_create_item(client, label, language="fr")
            action = "CREATED" if created else "FOUND"
            if has_item_claim(client, item_id, prop_id, target_id):
                print(f"      EXISTS  [{column}] -> '{label}' ({target_id})")
            else:
                add_item_claim(client, item_id, prop_id, target_id)
                print(f"      LINKED  [{column}] -> '{label}' ({target_id}) [{action}]")

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


def find_equipment_csv(platform_folder: Path) -> Optional[Path]:
    """Finds the CSV file whose name contains 'Equipement' (not _all)."""
    for csv_file in platform_folder.rglob("Equipement*.csv"):
        if not csv_file.stem.endswith("_all"):
            return csv_file
    return None


def find_expertise_csv(platform_folder: Path) -> Optional[Path]:
    """Finds the CSV file whose name contains 'Expertise' (not _all)."""
    for csv_file in platform_folder.rglob("Expertise*.csv"):
        if not csv_file.stem.endswith("_all"):
            return csv_file
    return None


def find_equipe_csv(platform_folder: Path) -> Optional[Path]:
    """Finds the CSV file whose name contains 'Equipe' (not _all)."""
    for csv_file in platform_folder.rglob("Equipe*.csv"):
        if not csv_file.stem.endswith("_all"):
            return csv_file
    return None


def find_responsable_csv(platform_folder: Path) -> Optional[Path]:
    """Finds the CSV file whose name contains 'Responsable' (not _all)."""
    for csv_file in platform_folder.rglob("Responsable*.csv"):
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
    print("\n=== Step 1: Resolving required properties and class items ===")

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

    equipment_class_id = search_entity_by_label(client, "Equipement", "item", language="fr")
    if not equipment_class_id:
        print("  ERROR: Could not find item 'Equipement' in Wikibase. Run populate.py first.")
        sys.exit(1)
    print(f"  FOUND  'Equipement' item ({equipment_class_id})")

    est_mutualise_avec_prop_id = search_entity_by_label(client, "est mutualisé avec", "property", language="fr")
    if not est_mutualise_avec_prop_id:
        print("  ERROR: Could not find property 'est mutualisé avec' in Wikibase. Run populate_object_properties.py first.")
        sys.exit(1)
    print(f"  FOUND  'est mutualisé avec' property ({est_mutualise_avec_prop_id})")

    expertise_class_id = search_entity_by_label(client, "Expertise", "item", language="fr")
    if not expertise_class_id:
        print("  ERROR: Could not find item 'Expertise' in Wikibase. Run populate.py first.")
        sys.exit(1)
    print(f"  FOUND  'Expertise' item ({expertise_class_id})")

    a_comme_ressource_prop_id = search_entity_by_label(client, "a comme ressource", "property", language="fr")
    if not a_comme_ressource_prop_id:
        print("  ERROR: Could not find property 'a comme ressource' in Wikibase. Run populate_object_properties.py first.")
        sys.exit(1)
    print(f"  FOUND  'a comme ressource' property ({a_comme_ressource_prop_id})")

    personne_class_id = search_entity_by_label(client, "Personne", "item", language="fr")
    if not personne_class_id:
        print("  ERROR: Could not find item 'Personne' in Wikibase. Run populate.py first.")
        sys.exit(1)
    print(f"  FOUND  'Personne' item ({personne_class_id})")

    equipe_class_id = search_entity_by_label(client, "Equipe", "item", language="fr")
    if not equipe_class_id:
        print("  ERROR: Could not find item 'Equipe' in Wikibase. Run populate.py first.")
        sys.exit(1)
    print(f"  FOUND  'Equipe' item ({equipe_class_id})")

    responsable_class_id = search_entity_by_label(client, "Responsable", "item", language="fr")
    if not responsable_class_id:
        print("  ERROR: Could not find item 'Responsable' in Wikibase. Run populate.py first.")
        sys.exit(1)
    print(f"  FOUND  'Responsable' item ({responsable_class_id})")

    a_comme_equipe_prop_id = search_entity_by_label(client, "a comme équipe", "property", language="fr")
    if not a_comme_equipe_prop_id:
        print("  ERROR: Could not find property 'a comme équipe' in Wikibase. Run populate_object_properties.py first.")
        sys.exit(1)
    print(f"  FOUND  'a comme équipe' property ({a_comme_equipe_prop_id})")

    fait_partie_de_equipe_prop_id = search_entity_by_label(client, "fait partie de l'équipe", "property", language="fr")
    if not fait_partie_de_equipe_prop_id:
        print("  ERROR: Could not find property 'fait partie de l\\'équipe' in Wikibase. Run populate_object_properties.py first.")
        sys.exit(1)
    print(f"  FOUND  'fait partie de l\\'équipe' property ({fait_partie_de_equipe_prop_id})")

    a_comme_responsable_prop_id = search_entity_by_label(client, "a comme responsable", "property", language="fr")
    if not a_comme_responsable_prop_id:
        print("  ERROR: Could not find property 'a comme responsable' in Wikibase. Run populate_object_properties.py first.")
        sys.exit(1)
    print(f"  FOUND  'a comme responsable' property ({a_comme_responsable_prop_id})")

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

            # ------------------------------------------------------------------
            # Process equipment belonging to this platform
            # ------------------------------------------------------------------
            equip_csv_path = find_equipment_csv(folder)
            if not equip_csv_path:
                print(f"    No equipment CSV found in {folder.name}")
                continue

            equip_rows = read_platform_rows(equip_csv_path)
            print(f"\n    Processing equipment from '{equip_csv_path.name}' ({len(equip_rows)} entries)")

            for equip_row in equip_rows:
                equip_name = equip_row.get("Nom", "").strip()
                if not equip_name:
                    continue

                print(f"\n      Equipment: {equip_name}")

                equip_id, created = find_or_create_item(client, equip_name, language="fr")
                print(f"        {'CREATED' if created else 'EXISTS '}  item '{equip_name}' ({equip_id})")

                # instance of -> Equipement
                if has_item_claim(client, equip_id, instance_of_prop_id, equipment_class_id):
                    print(f"        EXISTS   instance of -> Equipement")
                else:
                    add_item_claim(client, equip_id, instance_of_prop_id, equipment_class_id)
                    print(f"        LINKED   {equip_name} ({equip_id}) -[instance of]-> Equipement ({equipment_class_id})")

                # est mutualisé avec -> platform
                if has_item_claim(client, equip_id, est_mutualise_avec_prop_id, item_id):
                    print(f"        EXISTS   est mutualisé avec -> {platform_name}")
                else:
                    add_item_claim(client, equip_id, est_mutualise_avec_prop_id, item_id)
                    print(f"        LINKED   {equip_name} ({equip_id}) -[est mutualisé avec]-> {platform_name} ({item_id})")

                # Process remaining columns (skip 'est mutualisé avec' — handled above)
                for column, value in equip_row.items():
                    if column in SKIP_COLUMNS or column == "est mutualisé avec":
                        continue
                    if not value or not value.strip():
                        continue
                    value = value.strip()
                    if column == DESCRIPTION_COLUMN:
                        set_description(client, equip_id, value, language="fr")
                        print(f"        SET     description (fr) = '{value[:60]}{'...' if len(value) > 60 else ''}'")
                    else:
                        process_column(client, equip_id, column, value)

            # ------------------------------------------------------------------
            # Process expertise belonging to this platform
            # ------------------------------------------------------------------
            expertise_csv_path = find_expertise_csv(folder)
            if not expertise_csv_path:
                print(f"    No expertise CSV found in {folder.name}")
                continue

            expertise_rows = read_platform_rows(expertise_csv_path)
            print(f"\n    Processing expertise from '{expertise_csv_path.name}' ({len(expertise_rows)} entries)")

            for expertise_row in expertise_rows:
                expertise_name = expertise_row.get("Intitulé", "").strip()
                if not expertise_name:
                    continue

                print(f"\n      Expertise: {expertise_name[:80]}{'...' if len(expertise_name) > 80 else ''}")

                expertise_id, created = find_or_create_item(client, expertise_name, language="fr")
                print(f"        {'CREATED' if created else 'EXISTS '}  item '{expertise_name[:60]}' ({expertise_id})")

                # instance of -> Expertise
                if has_item_claim(client, expertise_id, instance_of_prop_id, expertise_class_id):
                    print(f"        EXISTS   instance of -> Expertise")
                else:
                    add_item_claim(client, expertise_id, instance_of_prop_id, expertise_class_id)
                    print(f"        LINKED   -[instance of]-> Expertise ({expertise_class_id})")

                # platform -[a comme ressource]-> expertise
                if has_item_claim(client, item_id, a_comme_ressource_prop_id, expertise_id):
                    print(f"        EXISTS   {platform_name} -[a comme ressource]-> expertise")
                else:
                    add_item_claim(client, item_id, a_comme_ressource_prop_id, expertise_id)
                    print(f"        LINKED   {platform_name} ({item_id}) -[a comme ressource]-> expertise ({expertise_id})")

                # Process remaining columns (skip 'Intitulé' — used as label)
                for column, value in expertise_row.items():
                    if column == "Intitulé" or not value or not value.strip():
                        continue
                    value = value.strip()
                    if column == DESCRIPTION_COLUMN:
                        set_description(client, expertise_id, value, language="fr")
                        print(f"        SET     description (fr) = '{value[:60]}{'...' if len(value) > 60 else ''}'")
                    else:
                        process_column(client, expertise_id, column, value)

            # ------------------------------------------------------------------
            # Process equipe belonging to this platform
            # ------------------------------------------------------------------
            equipe_csv_path = find_equipe_csv(folder)
            if not equipe_csv_path:
                print(f"    No equipe CSV found in {folder.name}")
            else:
                equipe_rows = read_platform_rows(equipe_csv_path)
                print(f"\n    Processing equipe from '{equipe_csv_path.name}' ({len(equipe_rows)} entries)")

                # Create one Equipe entity per platform to act as the team node
                equipe_label = f"Equipe - {platform_name}"
                equipe_node_id, created = find_or_create_item(client, equipe_label, language="fr")
                print(f"      {'CREATED' if created else 'EXISTS '}  team item '{equipe_label}' ({equipe_node_id})")

                if has_item_claim(client, equipe_node_id, instance_of_prop_id, equipe_class_id):
                    print(f"      EXISTS   instance of -> Equipe")
                else:
                    add_item_claim(client, equipe_node_id, instance_of_prop_id, equipe_class_id)
                    print(f"      LINKED   '{equipe_label}' ({equipe_node_id}) -[instance of]-> Equipe ({equipe_class_id})")

                if has_item_claim(client, item_id, a_comme_equipe_prop_id, equipe_node_id):
                    print(f"      EXISTS   {platform_name} -[a comme équipe]-> '{equipe_label}'")
                else:
                    add_item_claim(client, item_id, a_comme_equipe_prop_id, equipe_node_id)
                    print(f"      LINKED   {platform_name} ({item_id}) -[a comme équipe]-> '{equipe_label}' ({equipe_node_id})")

                for equipe_row in equipe_rows:
                    nom = equipe_row.get("Nom", "").strip()
                    prenom = equipe_row.get("Prénom", "").strip()
                    person_name = f"{prenom} {nom}".strip()
                    if not person_name:
                        continue

                    print(f"\n      Person: {person_name}")

                    person_id, created = find_or_create_item(client, person_name, language="fr")
                    print(f"        {'CREATED' if created else 'EXISTS '}  item '{person_name}' ({person_id})")

                    if has_item_claim(client, person_id, instance_of_prop_id, personne_class_id):
                        print(f"        EXISTS   instance of -> Personne")
                    else:
                        add_item_claim(client, person_id, instance_of_prop_id, personne_class_id)
                        print(f"        LINKED   '{person_name}' ({person_id}) -[instance of]-> Personne ({personne_class_id})")

                    if has_item_claim(client, person_id, fait_partie_de_equipe_prop_id, equipe_node_id):
                        print(f"        EXISTS   fait partie de l'équipe -> '{equipe_label}'")
                    else:
                        add_item_claim(client, person_id, fait_partie_de_equipe_prop_id, equipe_node_id)
                        print(f"        LINKED   '{person_name}' ({person_id}) -[fait partie de l'équipe]-> '{equipe_label}' ({equipe_node_id})")

                    for column, value in equipe_row.items():
                        if column in {"Nom", "Prénom"} or not value or not value.strip():
                            continue
                        value = value.strip()
                        if column == DESCRIPTION_COLUMN:
                            set_description(client, person_id, value, language="fr")
                            print(f"        SET     description (fr) = '{value[:60]}{'...' if len(value) > 60 else ''}'")
                        else:
                            process_column(client, person_id, column, value)

            # ------------------------------------------------------------------
            # Process responsable belonging to this platform
            # ------------------------------------------------------------------
            responsable_csv_path = find_responsable_csv(folder)
            if not responsable_csv_path:
                print(f"    No responsable CSV found in {folder.name}")
            else:
                responsable_rows = read_platform_rows(responsable_csv_path)
                print(f"\n    Processing responsable from '{responsable_csv_path.name}' ({len(responsable_rows)} entries)")

                for resp_row in responsable_rows:
                    nom = resp_row.get("Nom", "").strip()
                    prenom = resp_row.get("Prénom", "").strip()
                    person_name = f"{prenom} {nom}".strip()
                    if not person_name:
                        continue

                    print(f"\n      Responsable: {person_name}")

                    person_id, created = find_or_create_item(client, person_name, language="fr")
                    print(f"        {'CREATED' if created else 'EXISTS '}  item '{person_name}' ({person_id})")

                    if has_item_claim(client, person_id, instance_of_prop_id, responsable_class_id):
                        print(f"        EXISTS   instance of -> Responsable")
                    else:
                        add_item_claim(client, person_id, instance_of_prop_id, responsable_class_id)
                        print(f"        LINKED   '{person_name}' ({person_id}) -[instance of]-> Responsable ({responsable_class_id})")

                    if has_item_claim(client, item_id, a_comme_responsable_prop_id, person_id):
                        print(f"        EXISTS   {platform_name} -[a comme responsable]-> '{person_name}'")
                    else:
                        add_item_claim(client, item_id, a_comme_responsable_prop_id, person_id)
                        print(f"        LINKED   {platform_name} ({item_id}) -[a comme responsable]-> '{person_name}' ({person_id})")

                    for column, value in resp_row.items():
                        if column in {"Nom", "Prénom"} or not value or not value.strip():
                            continue
                        value = value.strip()
                        if column == DESCRIPTION_COLUMN:
                            set_description(client, person_id, value, language="fr")
                            print(f"        SET     description (fr) = '{value[:60]}{'...' if len(value) > 60 else ''}'")
                        else:
                            process_column(client, person_id, column, value)

    print("\nDone.")


if __name__ == "__main__":
    main()
