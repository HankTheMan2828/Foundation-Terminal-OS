"""Programs → WEB ACCESS — open DuckDuckGo when the machine is online.

Thin Hub face over `foundationhub.webaccess`: checks connectivity, prefers
Firefox via `foundationhub-web` (temporary sway kiosk + keyboard pointer),
falls back to a text browser, and hands the console over via Launch.
Ctrl+Q (or closing Firefox) returns to Programs.
"""
from __future__ import annotations

from .. import labels, webaccess
from ..app import Launch


def open_web_access(app):
    """Menu action: Launch a browser, or set a status-bar error and stay."""
    plan = webaccess.plan_launch()
    if not plan.ok:
        app.status_message = plan.error or labels.WEB_NO_BROWSER
        return None
    return Launch(plan.argv, missing_hint=plan.missing_hint)
