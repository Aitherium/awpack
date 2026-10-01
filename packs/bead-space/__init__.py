# ruff: noqa: N999 -- the directory name IS the pack id (bead-space); it loads by file path
"""bead-space tool pack -- an agent reads the work universe and manages its OWN beads.

Five tools over the platform's BeadSpace API (``/api/beadspace/*`` on
api.aitherium.com, Genesis ``routers/beadspace.py``):

    bead_graph   read the universe (public view; ``view="operator"`` needs an operator)
    bead_list    the beads you own
    bead_add     create a bead -- owned by YOU, whoever you claim to be
    bead_update  change one of your beads
    bead_link    link one of your beads to anyone's (delegation / A2A)

SCOPING LIVES ON THE SERVER. This module never sends an owner it was not given and
never asserts who the caller is: Genesis takes the actor from the verified bearer
and refuses (403) an edit to someone else's bead. A client-side check here would
only be a second opinion that a modified client skips.

Configuration: ``AITHER_BEADSPACE_URL`` (default ``https://api.aitherium.com``);
the bearer comes from adk's own credential resolution (``adk login``).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("awpack.bead_space")

DEFAULT_BASE_URL = "https://api.aitherium.com"
TIMEOUT_S = 15.0


def _base_url() -> str:
    return (os.environ.get("AITHER_BEADSPACE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _bearer() -> str:
    """The signed-in agent's bearer, from adk's credential store. '' when absent."""
    try:
        from adk.auth import resolve_credentials
    except ImportError:
        return ""
    try:
        return (resolve_credentials().access_token or "").strip()
    except Exception:  # noqa: BLE001 - no credentials is a state, reported per call
        return ""


#: Seam for tests: returns an object with ``request(method, url, **kw)``.
_client_factory: Callable[[], Any] = lambda: __import__("httpx").Client(timeout=TIMEOUT_S)  # noqa: E731


def _call(method: str, path: str, *, auth: bool, params: Optional[Dict[str, Any]] = None,
          json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    headers = {"Accept": "application/json"}
    if auth:
        token = _bearer()
        if not token:
            return {"ok": False, "status": 401,
                    "error": "not signed in: run `adk login` so beads are written as you"}
        headers["Authorization"] = f"Bearer {token}"
    url = f"{_base_url()}/api/beadspace/{path}"
    try:
        with _client_factory() as client:
            resp = client.request(method, url, headers=headers, params=params, json=json)
    except Exception as exc:  # noqa: BLE001 - surface transport failure to the agent
        return {"ok": False, "status": 0, "error": f"{type(exc).__name__}: {exc}"}
    try:
        body = resp.json()
    except ValueError:
        body = {"detail": resp.text[:300]}
    if resp.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else body
        return {"ok": False, "status": resp.status_code, "error": str(detail or body)}
    return {"ok": True, "status": resp.status_code, "data": body}


def bead_graph(agent: str = "", view: str = "public", max_nodes: int = 160) -> dict:
    """Read the BeadSpace work universe: every agent's constellation of beads (Atlas PM items,
    tasks, salon threads, agent-written beads) with links. Pass agent to scope to one agent."""
    params: Dict[str, Any] = {"view": "operator" if view == "operator" else "public",
                              "max_nodes": max(1, min(int(max_nodes), 400))}
    if agent:
        params["agent"] = agent.strip().lower()
    return _call("GET", "graph", auth=params["view"] == "operator", params=params)


def bead_list() -> dict:
    """List the beads you own in the BeadSpace work universe."""
    return _call("GET", "beads", auth=True)


def bead_add(title: str, status: str = "open", visibility: str = "internal",
             parent_id: str = "") -> dict:
    """Add a bead (a unit of your work) to the BeadSpace universe. It is owned by you.
    status: open|in_progress|blocked|deferred|done. visibility: internal|public (public
    beads show their title on your public Space page)."""
    body: Dict[str, Any] = {"title": title, "status": status, "visibility": visibility}
    if parent_id:
        body["parent_id"] = parent_id
    return _call("POST", "beads", auth=True, json=body)


def bead_update(bead_id: str, title: str = "", status: str = "", visibility: str = "") -> dict:
    """Update one of YOUR beads (title, status, visibility). Another agent's bead is refused."""
    body = {k: v for k, v in (("title", title), ("status", status), ("visibility", visibility)) if v}
    if not body:
        return {"ok": False, "status": 422, "error": "nothing to update"}
    return _call("PATCH", f"beads/{bead_id}", auth=True, json=body)


def bead_link(source: str, target: str, kind: str = "related") -> dict:
    """Link one of YOUR beads (source) to any bead (target): kind related|blocks|parent-child.
    Linking to another agent's bead is how delegation and A2A show in the universe."""
    return _call("POST", "links", auth=True, json={"source": source, "target": target, "kind": kind})


TOOLS = (bead_graph, bead_list, bead_add, bead_update, bead_link)
_ACTION_CLASS = {"bead_graph": "read", "bead_list": "read"}


def register(registry: Any) -> int:
    """Register the five bead tools on an adk ToolRegistry. Returns the count."""
    n = 0
    for fn in TOOLS:
        try:
            registry.register(fn, name=fn.__name__, description=(fn.__doc__ or "").strip(),
                              action_class=_ACTION_CLASS.get(fn.__name__, "write"))
            n += 1
        except Exception as exc:  # noqa: BLE001 - a registry refusal must not kill agent boot
            logger.warning("bead-space: could not register %s (%s)", fn.__name__, exc)
    return n
