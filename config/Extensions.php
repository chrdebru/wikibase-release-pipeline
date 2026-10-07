<?php

# SITYS customisations, loaded by /config/LocalSettings.php.
# Nuke is already loaded by the image (LoadExtensions.php); do not load it again.

$wgSitename = 'SITYS';

# Site language and time zone. Fresh installs also get the language through
# MW_WG_LANGUAGE_CODE in docker-compose.yml, so that the main page is created in French.
$wgLanguageCode = 'fr';
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
