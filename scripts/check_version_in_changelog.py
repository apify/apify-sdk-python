#!/usr/bin/env python3

import re

from utils import REPO_ROOT, get_current_package_version

CHANGELOG_PATH = REPO_ROOT / 'CHANGELOG.md'

# Checks whether the current package version has an entry in the CHANGELOG.md file
if __name__ == '__main__':
    current_package_version = get_current_package_version()

    if not CHANGELOG_PATH.is_file():
        raise RuntimeError('Unable to find CHANGELOG.md file')

    with open(CHANGELOG_PATH, encoding='utf-8') as changelog_file:
        for line in changelog_file:
            # The heading for the changelog entry for the given version can start with either the version number, or the version number in a link
            if re.match(fr'\[?{current_package_version}([\] ]|$)', line):
                break
        else:
            raise RuntimeError(f'There is no entry in the changelog for the current package version ({current_package_version})')
