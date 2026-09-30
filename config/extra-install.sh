#!/usr/bin/env bash
set -eu

# Register the relateditems gadget as site-wide default
php /var/www/html/maintenance/edit.php \
    --user="$MW_ADMIN_NAME" \
    --summary="Register relateditems gadget" \
    "MediaWiki:Gadgets-definition" \
    <<'WIKITEXT'
== General ==
* relateditems[ResourceLoader|default]|Gadget-relateditems.js
WIKITEXT

# Add the relateditems gadget script
php /var/www/html/maintenance/edit.php \
    --user="$MW_ADMIN_NAME" \
    --summary="Add relateditems gadget script" \
    "MediaWiki:Gadget-relateditems.js" \
    <<'JAVASCRIPT'
/**
 * Related items gadget for Wikibase
 * Shows items in this wiki that reference the current entity via any property.
 * Adapted from the Wikidata gadget for use with a local Wikibase + WDQS instance.
 */
( function ( mw, $ ) {
    'use strict';

    if ( mw.config.get( 'wgNamespaceNumber' ) !== 0 || !mw.config.exists( 'wbEntityId' ) ) {
        return;
    }

    var entityId = mw.config.get( 'wbEntityId' );
    var lang = mw.config.get( 'wgUserLanguage' );
    var wikiBase = mw.config.get( 'wgServer' ) + ( mw.config.get( 'wgScriptPath' ) || '' );
    var sparqlEndpoint = location.protocol + '//' + location.hostname + '/sparql';

    var messages = {
        title: 'Related items',
        loading: 'Loading\u2026',
        show: 'Show related items',
        none: 'No related items found.',
        more: 'More\u2026'
    };

    var html =
        '<h2 class="wb-section-heading section-heading wikibase-statements" dir="auto">' +
        '<span id="inverseclaims" class="mw-headline"></span></h2>' +
        '<div class="wikibase-statementgrouplistview" id="inversesection">' +
        '<div class="wikibase-listview"></div>' +
        '<div class="wikibase-showinverse"></div>' +
        '</div>';

    function loadItems() {
        $( 'span#inverseclaims' ).text( messages.title );
        $( '#inversesection .wikibase-showinverse' ).html( messages.loading );

        var query =
            'SELECT DISTINCT ?subject ?subjectLabel ?property ?propertyLabel WHERE {' +
            '  ?subject ?claimpred ?statement .' +
            '  ?statement ?valpred wd:' + entityId + ' .' +
            '  ?property wikibase:claim ?claimpred ;' +
            '            wikibase:statementProperty ?valpred .' +
            '  SERVICE wikibase:label { bd:serviceParam wikibase:language "' + lang + ',en" . }' +
            '} ORDER BY ?property LIMIT 300';

        $.ajax( {
            url: sparqlEndpoint,
            data: { query: query, format: 'json' },
            dataType: 'json'
        } ).done( function ( data ) {
            var bindings = data.results.bindings;
            var lastProp = null;

            for ( var i = 0; i < bindings.length; i++ ) {
                var row = bindings[ i ];
                var propId = row.property.value.replace( /.*\/entity\//, '' );
                var propLabel = ( row.propertyLabel && row.propertyLabel.value ) ? row.propertyLabel.value : propId;
                var subjId = row.subject.value.replace( /.*\/entity\//, '' );
                var subjLabel = ( row.subjectLabel && row.subjectLabel.value ) ? row.subjectLabel.value : subjId;
                var subjUrl = wikiBase + '/wiki/' + subjId;

                if ( propId !== lastProp ) {
                    var group =
                        '<div id="ri-' + propId + '" class="wikibase-statementgroupview listview-item">' +
                        '<div class="wikibase-statementgroupview-property">' +
                        '<div class="wikibase-statementgroupview-property-label" dir="auto">' +
                        '<a href="' + wikiBase + '/wiki/Property:' + propId + '">' + mw.html.escape( propLabel ) + '</a>' +
                        '</div></div>' +
                        '<div class="wikibase-statementlistview"><div class="wikibase-statementlistview-listview"></div></div>' +
                        '</div>';
                    $( '#inversesection .wikibase-listview' ).append( group );
                    lastProp = propId;
                }

                var stmt =
                    '<div class="wikibase-statementview wb-normal listview-item">' +
                    '<div class="wikibase-statementview-mainsnak-container">' +
                    '<div class="wikibase-statementview-mainsnak" dir="auto">' +
                    '<div class="wikibase-snakview"><div class="wikibase-snakview-value-container" dir="auto">' +
                    '<div class="wikibase-snakview-value wikibase-snakview-variation-valuesnak">' +
                    '<a href="' + mw.html.escape( subjUrl ) + '">' + mw.html.escape( subjLabel ) + '</a>' +
                    '</div></div></div></div></div></div>';
                $( '#ri-' + propId + ' .wikibase-statementlistview-listview' ).append( stmt );
            }

            if ( bindings.length === 0 ) {
                $( '#inversesection .wikibase-showinverse' ).html( messages.none );
            } else if ( bindings.length === 300 ) {
                $( '#inversesection .wikibase-showinverse' ).html(
                    '<a href="' + mw.util.getUrl( 'Special:WhatLinksHere/' + entityId ) + '">' + messages.more + '</a>'
                );
            } else {
                $( '#inversesection .wikibase-showinverse' ).html( '' );
            }
        } ).fail( function () {
            $( '#inversesection .wikibase-showinverse' ).html( 'SPARQL query failed.' );
        } );
    }

    function init() {
        $( '.wikibase-entityview-main' ).append( html );
        $( 'span#inverseclaims' ).text( messages.title );
        $( '#inversesection .wikibase-showinverse' ).append(
            $( '<a>' ).attr( 'href', '#' ).text( messages.show ).on( 'click', function ( e ) {
                e.preventDefault();
                loadItems();
            } )
        );
    }

    $( init );

}( mediaWiki, jQuery ) );
JAVASCRIPT

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
