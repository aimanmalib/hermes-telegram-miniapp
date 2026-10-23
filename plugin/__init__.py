"""Hermes plugin entry point for the Telegram Mini App.

Everything this plugin does lives in the dashboard extension (``dashboard/manifest.json``
and ``dashboard/plugin_api.py``), which the dashboard loads on its own. It registers no
tools, hooks or commands, so ``register`` has nothing to add.
"""


def register(ctx) -> None:  # noqa: ARG001 - required entry point, nothing to register
    return None
