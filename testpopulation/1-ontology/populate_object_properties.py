import csv
import json
import re
import urllib3
from pathlib import Path
from typing import Optional

from wikibase_client import WikibaseClient, load_config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OBJECT_PROPERTIES_CSV = Path(__file__).parent / "object_properties_with_english_translations.csv"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def extract_label(value: str) -> Optional[str]:
    """Strips Notion URLs from values like 'Ressource (https://...)' → 'Ressource'."""
    if not value:
        return None
    cleaned = re.sub(r'\s*\(https?://[^\)]+\)', '', value).strip()
    return cleaned or None


# -----------------------------------------------------------------------------
# Search
# -----------------------------------------------------------------------------

def search_entity_by_label(client: WikibaseClient, label: str, entity_type: str,
                            language: str = "fr") -> Optional[str]:
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


# -----------------------------------------------------------------------------
# Create / Update
# -----------------------------------------------------------------------------

def create_property(client: WikibaseClient, fr_label: str, en_label: str,
                    fr_desc: str, en_desc: str, en_aliases: list = None) -> str:
    labels, descriptions, aliases = {}, {}, {}
    if fr_label:
        labels["fr"] = {"language": "fr", "value": fr_label}
    if en_label:
        labels["en"] = {"language": "en", "value": en_label}
    if fr_desc:
        descriptions["fr"] = {"language": "fr", "value": fr_desc}
    if en_desc:
        descriptions["en"] = {"language": "en", "value": en_desc}
    if en_aliases:
        aliases["en"] = [{"language": "en", "value": a} for a in en_aliases]
    data = {"datatype": "wikibase-item"}
    if labels:
        data["labels"] = labels
    if descriptions:
        data["descriptions"] = descriptions
    if aliases:
        data["aliases"] = aliases

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


def update_property(client: WikibaseClient, prop_id: str, fr_label: str, en_label: str,
                    fr_desc: str, en_desc: str, en_aliases: list = None) -> None:
    labels, descriptions, aliases = {}, {}, {}
    if fr_label:
        labels["fr"] = {"language": "fr", "value": fr_label}
    if en_label:
        labels["en"] = {"language": "en", "value": en_label}
    if fr_desc:
        descriptions["fr"] = {"language": "fr", "value": fr_desc}
    if en_desc:
        descriptions["en"] = {"language": "en", "value": en_desc}
    if en_aliases:
        aliases["en"] = [{"language": "en", "value": a, "add": ""} for a in en_aliases]
    data = {}
    if labels:
        data["labels"] = labels
    if descriptions:
        data["descriptions"] = descriptions
    if aliases:
        data["aliases"] = aliases

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


def create_meta_property(client: WikibaseClient, fr_label: str, fr_desc: str,
                         en_label: str = None, en_desc: str = None) -> str:
    data = {
        "labels": {"fr": {"language": "fr", "value": fr_label}},
        "descriptions": {"fr": {"language": "fr", "value": fr_desc}},
        "datatype": "wikibase-item",
    }
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
        raise RuntimeError(f"Error creating meta-property '{fr_label}': {error}")
    return result["entity"]["id"]


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

def load_object_properties() -> list:
    with open(OBJECT_PROPERTIES_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    config = load_config()
    client = WikibaseClient(**config)
    rows = load_object_properties()

    # ------------------------------------------------------------------
    # Step 1: Ensure domaine and portée meta-properties exist
    # ------------------------------------------------------------------
    print("\n=== Step 1: Ensuring meta-properties ===")
    domaine_prop_id = search_entity_by_label(client, "domaine", "property")
    if domaine_prop_id:
        print(f"  EXISTS  domaine ({domaine_prop_id})")
    else:
        domaine_prop_id = create_meta_property(
            client,
            fr_label="domaine", fr_desc="Classe sujet d'une propriété.",
            en_label="domain", en_desc="Subject class of a property.",
        )
        print(f"  CREATED domaine ({domaine_prop_id})")

    portee_prop_id = search_entity_by_label(client, "portée", "property")
    if portee_prop_id:
        print(f"  EXISTS  portée ({portee_prop_id})")
    else:
        portee_prop_id = create_meta_property(
            client,
            fr_label="portée", fr_desc="Classe objet d'une propriété.",
            en_label="range", en_desc="Object class of a property.",
        )
        print(f"  CREATED portée ({portee_prop_id})")

    # ------------------------------------------------------------------
    # Step 2: Create / update object properties
    # ------------------------------------------------------------------
    print("\n=== Step 2: Creating object properties ===")
    prop_label_to_id: dict = {}

    for row in rows:
        fr_label   = row["Nom"].strip()
        en_label   = row["English name"].strip()
        fr_desc    = row["Description"].strip()
        en_desc    = row["Description (EN)"].strip()
        en_aliases = [a.strip() for a in row["Alternative labels (EN)"].split(",") if a.strip()]

        if not fr_label:
            continue

        existing_id = search_entity_by_label(client, fr_label, "property")
        if existing_id:
            update_property(client, existing_id, fr_label, en_label, fr_desc, en_desc, en_aliases)
            print(f"  UPDATED {fr_label} ({existing_id})")
            prop_label_to_id[fr_label] = existing_id
        else:
            prop_id = create_property(client, fr_label, en_label, fr_desc, en_desc, en_aliases)
            update_property(client, prop_id, fr_label, en_label, fr_desc, en_desc, en_aliases)
            print(f"  CREATED {fr_label} ({prop_id})")
            prop_label_to_id[fr_label] = prop_id

    # ------------------------------------------------------------------
    # Step 3: Add domain and range claims
    # ------------------------------------------------------------------
    print("\n=== Step 3: Adding domain and range claims ===")
    for row in rows:
        fr_label = row["Nom"].strip()
        domain   = extract_label(row["Domaine"])
        scope    = extract_label(row["Portée"])

        if not fr_label:
            continue

        prop_id = prop_label_to_id.get(fr_label)
        if not prop_id:
            print(f"  SKIP    {fr_label}: property not found")
            continue

        if domain:
            domain_id = search_entity_by_label(client, domain, "item")
            if not domain_id:
                print(f"  SKIP    {fr_label} domain -> {domain}: item not found")
            elif has_claim(client, prop_id, domaine_prop_id, domain_id):
                print(f"  EXISTS  {fr_label} domain -> {domain}")
            else:
                add_item_claim(client, prop_id, domaine_prop_id, domain_id)
                print(f"  LINKED  {fr_label} domain -> {domain} ({domain_id})")

        if scope:
            scope_id = search_entity_by_label(client, scope, "item")
            if not scope_id:
                print(f"  SKIP    {fr_label} portée -> {scope}: item not found")
            elif has_claim(client, prop_id, portee_prop_id, scope_id):
                print(f"  EXISTS  {fr_label} portée -> {scope}")
            else:
                add_item_claim(client, prop_id, portee_prop_id, scope_id)
                print(f"  LINKED  {fr_label} portée -> {scope} ({scope_id})")

    print("\nDone.")


if __name__ == "__main__":
    main()
