"""`python -m novaya` -- the entrypoint a client config falls back to.

The console script is the normal path. This exists because an MCP config has to
name something that will still resolve when the client launches it from an
environment that is not the user's shell -- and on a checkout, or a PATH the
resolver cannot see, the module is the thing that always works.
"""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
