"""Guards for the `scrutineer-serve` entry point on an install without the `web` extra.

Importing a package runs its ``__init__`` *before* an entry point function gets control, so a
module-level ``from scrutineer.web.app import create_app`` made the command die with a bare
``ModuleNotFoundError: No module named 'fastapi'`` — before ``main()`` could report which extra
was missing. ``scrutineer.web.app`` is therefore imported lazily.

The end-to-end proof (a clean install without the extra, printing the missing extra instead of a
traceback) needs a process where fastapi is genuinely absent, so it lives in the wheel check and
not here. This file pins the mechanism that makes it possible.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


def test_web_package_exposes_create_app():
    import scrutineer.web as web

    assert callable(web.create_app)


def test_unknown_attribute_is_an_honest_attribute_error():
    import scrutineer.web as web

    with pytest.raises(AttributeError, match="has no attribute"):
        web.definitely_not_a_real_attribute


def test_package_init_imports_nothing_from_scrutineer():
    """A structural invariant, asserted structurally.

    "Import the package without fastapi installed" cannot be tested in this process — fastapi is
    present in the dev environment and other modules will have imported it already — so the
    property is pinned at the source level instead: ``__init__`` must perform no top-level import
    of ``scrutineer.web.*``, because that is exactly the import that dragged fastapi in.
    """
    import scrutineer.web as web

    tree = ast.parse(Path(web.__file__).read_text())
    top_level_scrutineer_imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom)) and "scrutineer" in ast.dump(node)
    ]

    assert top_level_scrutineer_imports == [], (
        "scrutineer/web/__init__.py imports scrutineer.web submodules at import time; "
        "that makes `scrutineer-serve` require the optional web extra just to load"
    )
