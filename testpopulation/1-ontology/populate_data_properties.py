import csv
import json
import re
import unicodedata
import urllib3
from pathlib import Path
from typing import Optional

from wikibase_client import WikibaseClient, load_config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_PROPERTIES_CSV = Path(__file__).parent / "data_properties_with_english_translations.csv"

# Map CSV range values to Wikibase property datatypes
DATATYPE_MAP = {
    "string":   "string",
    "url":      "url",
    "uri":      "external-id",
    "pdf":      "url",
    "datetime": "time",
}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def extract_label(value: str) -> Optional[str]:
    """Strips Notion URLs from values like 'Ressource (https://...)' → 'Ressource'."""
    if not value:
        return None
    cleaned = re.sub(r'\s*\(https?://[^\)]+\)', '', value).strip()
    return cleaned or None


def map_datatype(portee: str) -> str:
    """Maps a CSV Portée value to a Wikibase property datatype."""
    return DATATYPE_MAP.get(portee.strip().lower(), "string")


# -----------------------------------------------------------------------------
# Search
# -----------------------------------------------------------------------------

def normalize_label(label: str) -> str:
    """Normalize a label for search and comparison: lowercase, strip, normalize apostrophes."""
    label = unicodedata.normalize("NFC", label)
    label = label.replace("\u2019", "'").replace("\u2018", "'")
    return label.strip().lower()


def search_entity_by_label(client: WikibaseClient, label: str, entity_type: str,
                            language: str = "fr") -> Optional[str]:
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
# Create / Update
# -----------------------------------------------------------------------------

def create_property(client: WikibaseClient, fr_label: str, fr_desc: str, datatype: str,
                    en_label: str = None, en_desc: str = None) -> str:
    data = {"labels": {}, "descriptions": {}, "datatype": datatype}
    if fr_label:
        data["labels"]["fr"] = {"language": "fr", "value": fr_label}
    if fr_desc:
        data["descriptions"]["fr"] = {"language": "fr", "value": fr_desc}
    if en_label:
        data["labels"]["en"] = {"language": "en", "value": en_label}
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
        if error.get("code") in ("failed-save", "modification-failed"):
            for msg in error.get("messages", []):
                if msg.get("name") == "wikibase-validator-label-conflict":
                    match = re.search(r'\[\[Property:(P\d+)', msg["parameters"][2])
                    if match:
                        return match.group(1)
        raise RuntimeError(f"Error creating property '{fr_label}': {error}")
    return result["entity"]["id"]


def update_property(client: WikibaseClient, prop_id: str, fr_label: str, fr_desc: str,
                    en_label: str = None, en_desc: str = None) -> None:
    labels, descriptions = {}, {}
    if fr_label:
        labels["fr"] = {"language": "fr", "value": fr_label}
    if en_label:
        labels["en"] = {"language": "en", "value": en_label}
    if fr_desc:
        descriptions["fr"] = {"language": "fr", "value": fr_desc}
    if en_desc:
        descriptions["en"] = {"language": "en", "value": en_desc}
    data = {}
    if labels:
        data["labels"] = labels
    if descriptions:
        data["descriptions"] = descriptions

    response = client.session.post(client.api_url, data={
        "action": "wbeditentity",
        "id": prop_id,
        "data": json.dumps(data),
        "token": client.get_csrf_token(),
        "format": "json",
    })
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise RuntimeError(f"Error updating property {prop_id}: {result['error']}")


def has_claim(client: WikibaseClient, entity_id: str, property_id: str, value_id: str) -> bool:
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


def add_item_claim(client: WikibaseClient, entity_id: str, property_id: str, value_id: str) -> None:
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

def load_data_properties() -> list:
    with open(DATA_PROPERTIES_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    config = load_config()
    client = WikibaseClient(**config)
    rows = load_data_properties()

    # ------------------------------------------------------------------
    # Step 1: Ensure "domaine" meta-property exists
    # ------------------------------------------------------------------
    print("\n=== Step 1: Ensuring 'domaine' meta-property ===")
    domaine_prop_id = search_entity_by_label(client, "domaine", "property")
    if domaine_prop_id:
        print(f"  EXISTS  domaine ({domaine_prop_id})")
    else:
        domaine_prop_id = create_property(
            client,
            fr_label="domaine",
            fr_desc="Classe sujet d'une propriété.",
            datatype="wikibase-item",
            en_label="domain",
            en_desc="Subject class of a property.",
        )
        print(f"  CREATED domaine ({domaine_prop_id})")

    # ------------------------------------------------------------------
    # Step 2: Create / update data properties
    # ------------------------------------------------------------------
    print("\n=== Step 2: Creating data properties ===")
    prop_label_to_id: dict = {}

    for row in rows:
        fr_label   = row["Nom"].strip()
        en_label   = row["English name"].strip()
        fr_desc    = row["Description"].strip()
        en_desc    = row["Description (EN)"].strip()
        en_aliases = [a.strip() for a in row["Alternative labels (EN)"].split(",") if a.strip()]
        portee     = row["Portée"].strip()
        domain     = extract_label(row["Domaine"])

        if not fr_label:
            continue

        datatype = map_datatype(portee)

        existing_id = search_entity_by_label(client, fr_label, "property")
        if existing_id:
            update_property(client, existing_id, fr_label, fr_desc, en_label=en_label, en_desc=en_desc)
            print(f"  UPDATED {fr_label} ({existing_id}) [{datatype}]")
            prop_label_to_id[fr_label] = existing_id
        else:
            prop_id = create_property(client, fr_label, fr_desc, datatype, en_label=en_label, en_desc=en_desc)
            print(f"  CREATED {fr_label} ({prop_id}) [{datatype}]")
            prop_label_to_id[fr_label] = prop_id

    # ------------------------------------------------------------------
    # Step 3: Add domain claims to properties
    # ------------------------------------------------------------------
    print("\n=== Step 3: Adding domain claims ===")
    for row in rows:
        fr_label = row["Nom"].strip()
        domain   = extract_label(row["Domaine"])

        if not fr_label or not domain:
            continue

        prop_id = prop_label_to_id.get(fr_label)
        if not prop_id:
            print(f"  SKIP    {fr_label}: property not found")
            continue

        domain_item_id = search_entity_by_label(client, domain, "item")
        if not domain_item_id:
            print(f"  SKIP    {fr_label} -> {domain}: domain item not found")
            continue

        if has_claim(client, prop_id, domaine_prop_id, domain_item_id):
            print(f"  EXISTS  {fr_label} -> {domain}")
        else:
            add_item_claim(client, prop_id, domaine_prop_id, domain_item_id)
            print(f"  LINKED  {fr_label} ({prop_id}) -> {domain} ({domain_item_id})")

    print("\nDone.")


if __name__ == "__main__":
    main()
