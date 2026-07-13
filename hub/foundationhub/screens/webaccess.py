"""Programs → WEB ACCESS — open DuckDuckGo when the machine is online.

Thin Hub face over `foundationhub.webaccess`: checks connectivity, picks a
text browser (w3m) that runs in the same terminal the Hub owns, and hands
the console over via Launch. Quit the browser (q in w3m) to return.
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
