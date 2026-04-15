import csv
import json
import re
import unicodedata
import urllib3
from pathlib import Path
from typing import Optional

from wikibase_client import WikibaseClient, load_config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CLASSES_CSV = Path(__file__).parent / "classes_with_english_translations.csv"


# -----------------------------------------------------------------------------
# Search
# -----------------------------------------------------------------------------

def normalize_label(label: str) -> str:
    """Normalize a label for comparison: lowercase, strip, normalize apostrophes."""
    label = unicodedata.normalize("NFC", label)
    label = label.replace("\u2019", "'").replace("\u2018", "'")
    return label.strip().lower()


def search_entity_by_label(client: WikibaseClient, label: str, entity_type: str, language: str = "fr") -> Optional[str]:
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


# -----------------------------------------------------------------------------
# Create
# -----------------------------------------------------------------------------

def create_item(client: WikibaseClient, fr_label: str, en_label: str, fr_desc: str, en_desc: str,
                fr_aliases: list = None, en_aliases: list = None) -> str:
    data = {"labels": {}, "descriptions": {}, "aliases": {}}
    if fr_label:
        data["labels"]["fr"] = {"language": "fr", "value": fr_label}
    if en_label:
        data["labels"]["en"] = {"language": "en", "value": en_label}
    if fr_desc:
        data["descriptions"]["fr"] = {"language": "fr", "value": fr_desc}
    if en_desc:
        data["descriptions"]["en"] = {"language": "en", "value": en_desc}
    if fr_aliases:
        data["aliases"]["fr"] = [{"language": "fr", "value": a} for a in fr_aliases]
    if en_aliases:
        data["aliases"]["en"] = [{"language": "en", "value": a} for a in en_aliases]

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
        error = result["error"]
        if error.get("code") == "modification-failed":
            # Item already exists with same label+description — extract its ID
            for msg in error.get("messages", []):
                if msg.get("name") == "wikibase-validator-label-with-description-conflict":
                    match = re.search(r'\[\[Item:(Q\d+)', msg["parameters"][2])
                    if match:
                        return match.group(1)
        raise RuntimeError(f"Error creating item '{fr_label}': {error}")
    return result["entity"]["id"]


def update_item(client: WikibaseClient, entity_id: str, fr_label: str, en_label: str,
                fr_desc: str, en_desc: str, fr_aliases: list = None, en_aliases: list = None) -> None:
    """Updates labels, descriptions, and aliases on an existing item."""
    data = {"labels": {}, "descriptions": {}, "aliases": {}}
    if fr_label:
        data["labels"]["fr"] = {"language": "fr", "value": fr_label}
    if en_label:
        data["labels"]["en"] = {"language": "en", "value": en_label}
    if fr_desc:
        data["descriptions"]["fr"] = {"language": "fr", "value": fr_desc}
    if en_desc:
        data["descriptions"]["en"] = {"language": "en", "value": en_desc}
    if fr_aliases:
        data["aliases"]["fr"] = [{"language": "fr", "value": a, "add": ""} for a in fr_aliases]
    if en_aliases:
        data["aliases"]["en"] = [{"language": "en", "value": a, "add": ""} for a in en_aliases]

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
        raise RuntimeError(f"Error updating item {entity_id}: {result['error']}")


def create_property(client: WikibaseClient, fr_label: str, en_label: str, fr_desc: str, en_desc: str, datatype: str) -> str:
    data = {
        "labels": {},
        "descriptions": {},
        "datatype": datatype,
    }
    if fr_label:
        data["labels"]["fr"] = {"language": "fr", "value": fr_label}
    if en_label:
        data["labels"]["en"] = {"language": "en", "value": en_label}
    if fr_desc:
        data["descriptions"]["fr"] = {"language": "fr", "value": fr_desc}
    if en_desc:
        data["descriptions"]["en"] = {"language": "en", "value": en_desc}

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
        error = result["error"]
        if error.get("code") == "failed-save":
            for msg in error.get("messages", []):
                if msg.get("name") == "wikibase-validator-label-conflict":
                    match = re.search(r'\[\[Property:(P\d+)', msg["parameters"][2])
                    if match:
                        return match.group(1)
        raise RuntimeError(f"Error creating property '{fr_label}': {error}")
    return result["entity"]["id"]


def has_claim(client: WikibaseClient, entity_id: str, property_id: str, value_id: str) -> bool:
    """Returns True if entity already has a claim property -> value_id."""
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


def add_claim(client: WikibaseClient, entity_id: str, property_id: str, value_id: str) -> None:
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
        raise RuntimeError(f"Error adding claim on {entity_id}: {result['error']}")


# -----------------------------------------------------------------------------
# CSV
# -----------------------------------------------------------------------------

def load_classes() -> list[dict]:
    with open(CLASSES_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    config = load_config()
    client = WikibaseClient(**config)
    classes = load_classes()

    # ------------------------------------------------------------------
    # Step 1: Create items for each class
    # ------------------------------------------------------------------
    print("\n=== Step 1: Creating class items ===")
    label_to_id: dict = {}

    for row in classes:
        fr_label    = row["Nom de la classe"].strip()
        en_label    = row["English name"].strip()
        fr_desc     = row["Description"].strip()
        en_desc     = row["Description (EN)"].strip()
        fr_aliases  = [a.strip() for a in row["Autres labels"].split(",") if a.strip()]
        en_aliases  = [a.strip() for a in row["Alternative labels (EN)"].split(",") if a.strip()]

        if not fr_label:
            continue

        existing_id = search_entity_by_label(client, fr_label, "item")
        if existing_id:
            update_item(client, existing_id, fr_label, en_label, fr_desc, en_desc, fr_aliases, en_aliases)
            print(f"  UPDATED {fr_label} ({existing_id})")
            label_to_id[fr_label] = existing_id
        else:
            item_id = create_item(client, fr_label, en_label, fr_desc, en_desc, fr_aliases, en_aliases)
            print(f"  CREATED {fr_label} ({item_id})")
            label_to_id[fr_label] = item_id

    # ------------------------------------------------------------------
    # Step 2: Ensure "sous-classe de" property exists
    # ------------------------------------------------------------------
    print("\n=== Step 2: Creating 'sous-classe de' property ===")
    prop_id = search_entity_by_label(client, "sous-classe de", "property")
    if prop_id:
        print(f"  EXISTS  sous-classe de ({prop_id})")
    else:
        prop_id = create_property(
            client,
            fr_label="sous-classe de",
            en_label="subclass of",
            fr_desc="Indique que le sujet est une sous-classe de l'objet.",
            en_desc="Indicates that the subject is a subclass of the object.",
            datatype="wikibase-item",
        )
        print(f"  CREATED sous-classe de ({prop_id})")

    print("\n=== Step 2.b: Creating 'est instance de' property ===")
    prop_id = search_entity_by_label(client, "est instance de", "property")
    if prop_id:
        print(f"  EXISTS  est instance de ({prop_id})")
    else:
        prop_id = create_property(
            client,
            fr_label="est une instance de",
            en_label="instance of",
            fr_desc="Indique que le sujet est une instance de l'objet.",
            en_desc="Indicates that the subject is an instance of the object.",
            datatype="wikibase-item",
        )
        print(f"  CREATED est instance de ({prop_id})")

    # ------------------------------------------------------------------
    # Step 3: Create subclass relationships
    # ------------------------------------------------------------------
    print("\n=== Step 3: Creating subclass relationships ===")
    for row in classes:
        fr_label     = row["Nom de la classe"].strip()
        parent_label = row["Hiérarchie (classe parent)"].strip()

        if not fr_label or not parent_label:
            continue

        child_id  = label_to_id.get(fr_label)
        parent_id = label_to_id.get(parent_label)

        if not child_id:
            print(f"  SKIP    {fr_label}: item not found")
            continue
        if not parent_id:
            print(f"  SKIP    {fr_label} -> {parent_label}: parent not found")
            continue

        if has_claim(client, child_id, prop_id, parent_id):
            print(f"  EXISTS  {fr_label} -> {parent_label}")
        else:
            add_claim(client, child_id, prop_id, parent_id)
            print(f"  LINKED  {fr_label} ({child_id}) -> {parent_label} ({parent_id})")

    print("\nDone.")


if __name__ == "__main__":
    main()
