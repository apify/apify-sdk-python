#!/usr/bin/env python3

from utils import get_current_package_version

# Print the current package version from the src/package_name/_version.py file to stdout
if __name__ == '__main__':
    print(get_current_package_version(), end='')
