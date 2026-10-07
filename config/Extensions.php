<?php

# SITYS customisations, loaded by /config/LocalSettings.php.
# Nuke is already loaded by the image (LoadExtensions.php); do not load it again.

$wgSitename = 'SITYS';

# The site language stays English (set at install), so that built-in pages keep their
# standard names (Special:EntityData, Main Page). Visitors still get the interface in their
# browser's language, through the UniversalLanguageSelector extension.
$wgLocaltimezone = 'Europe/Brussels';

# Copyright line in the page footer.
$wgRightsText = '© Université de Liège - Tous droits réservés';
$wgRightsUrl = 'https://www.uliege.be/';

# RDF exports state the licence as a link (cc:license), not as text. Wikibase's default is
# CC0, which would contradict the footer, so this points to the same link as the footer.
$wgWBRepoSettings['rdfDataRightsUrl'] = $wgRightsUrl;

# Branding: the ULiège logo and the SITYS theme, both in config/branding/.
# docker-compose.yml mounts the logo into the web root.
$wgLogos = [
	'icon' => "$wgScriptPath/resources/assets/uliege-logo.svg",
];

$wgResourceModules['sitys.branding'] = [
	'localBasePath' => '/config/branding',
	'styles' => [ 'sitys.css' ],
];

$wgHooks['BeforePageDisplay'][] = static function ( $out, $skin ) {
	if ( $skin->getSkinName() === 'vector-2022' ) {
		$out->addModuleStyles( [ 'sitys.branding' ] );
	}
};

$wgWBRepoSettings['string-limits']['multilang']['length'] = 2048;

wfLoadExtension( 'Gadgets' );
