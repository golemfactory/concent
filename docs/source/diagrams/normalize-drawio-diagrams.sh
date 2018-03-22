#!/bin/bash

# Files saved and exported by draw.io are minified, with all text on a single line.
# Every single change is seen as replacing the whole file with a completely new one.
# For storing these files in the repo it's much better to have them broken into separate lines.
# This script uses xmllint to do it for all files that require such treatment.
#
# Always run it before committing your changes.

# TODO: Do it for the .xml files too. The problem is that they contain a single tag with zip-compressed XML content.
# They need to be extracted first.

XMLLINT_INDENT="    " xmllint --format concent-verification-sequence.svg --output concent-verification-sequence.svg
