"""Data-source layer: produce the pipeline's schema dict + row lists from either the
offline JSON files (default, for experiments) or a live SQL database (production).

The rest of the pipeline (``classify_selection``, ``recommend``, the renderers and the
filter/aggregate/join stages) consumes a fixed schema dict and row dicts; this package is
the only thing that changes when the data comes from a live DB instead of JSON files.
"""

from .base import DataSource, LazyTables
from .factory import make_datasource

__all__ = ["DataSource", "LazyTables", "make_datasource"]
