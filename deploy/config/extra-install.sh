#!/usr/bin/env bash
set -eu

# Create a SPARQL examples page on first install
php /var/www/html/maintenance/edit.php \
    --user="$MW_ADMIN_NAME" \
    --summary="Initial SPARQL examples" \
    "Project:SPARQL_examples" \
    <<'WIKITEXT'
== Basic examples ==

=== All items ===
<syntaxhighlight lang="sparql">
SELECT ?item ?itemLabel WHERE {
  ?item wikibase:sitelinks [] .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
}
LIMIT 10
</syntaxhighlight>

=== All types ===
<syntaxhighlight lang="sparql">
SELECT DISTINCT ?type WHERE {
  [] rdf:type ?type .
}
</syntaxhighlight>

WIKITEXT
