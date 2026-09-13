"""The Novayagraph client.

Cloud owns indexing, the graph, retrieval and the API. This owns auth,
discovery, agent adapters and request transport. Nothing else, ever: see
build.md, LAW 2.
"""
from __future__ import annotations

__version__ = "0.1.7"

# The typed command. Distribution is `novaya`: the obvious short names are
# taken on PyPI by live unrelated projects, so a guess installs the wrong
# tool.
COMMAND = "novgraph"
