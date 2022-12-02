import os
import sys

sys.path.insert(0, os.path.abspath('../../src/'))

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx_autodoc_typehints',
    'sphinx_markdown_builder',
]

autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
}

add_module_names = False

napoleon_preprocess_types = True
