import pathlib

PACKAGE_NAME = 'apify'
REPO_ROOT = pathlib.Path(__file__).parent.resolve() / '..'
VERSION_FILE_PATH = REPO_ROOT / f'src/{PACKAGE_NAME}/_version.py'


# Load the current version number from src/package_name/_version.py
# It is on a line in the format __version__ = 1.2.3
def get_current_package_version() -> str:
    with open(VERSION_FILE_PATH, 'r') as version_file:
        for line in version_file:
            if line.startswith('__version__'):
                delim = '"' if '"' in line else "'"
                version = line.split(delim)[1]
                return version
        else:
            raise RuntimeError('Unable to find version string.')


# Write the given version number from src/package_name/_version.py
# It replaces the version number on the line with the format __version__ = 1.2.3
def set_current_package_version(version: str) -> None:
    with open(VERSION_FILE_PATH, 'r+') as version_file:
        updated_version_file_lines = []
        version_string_found = False
        for line in version_file:
            if line.startswith('__version__'):
                version_string_found = True
                line = f"__version__ = '{version}'"
            updated_version_file_lines.append(line)

        if not version_string_found:
            raise RuntimeError('Unable to find version string.')

        version_file.seek(0)
        version_file.write('\n'.join(updated_version_file_lines))
        version_file.truncate()
