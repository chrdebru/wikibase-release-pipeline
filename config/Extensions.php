<?php

# SITYS customisations, loaded by /config/LocalSettings.php.
# Nuke is already loaded by the image (LoadExtensions.php); do not load it again.

$wgSitename = 'SITYS';

$wgWBRepoSettings['string-limits']['multilang']['length'] = 2048;

wfLoadExtension( 'Gadgets' );
