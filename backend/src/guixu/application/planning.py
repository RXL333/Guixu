from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


def select_planning_samples(files: list[dict[str, Any]], *, per_scope: int = 48, total_limit: int = 200) -> list[dict[str, Any]]:
    """Deterministic round-robin over scope, modality and atomic top folder."""
    scopes: dict[str, dict[tuple[str, str], deque[dict[str, Any]]]] = defaultdict(lambda: defaultdict(deque))
    for item in sorted(files, key=lambda value: (value["scope_id"], value["file_id"])):
        relative = str(item.get("relative_path", "")).replace("\\", "/")
        atomic = relative.split("/", 1)[0] if "/" in relative else "(root)"
        scopes[item["scope_id"]][(item.get("modality", "other"), atomic)].append(item)
    selected = []
    for scope_id in sorted(scopes):
        groups = scopes[scope_id]
        scope_selected = 0
        while groups and scope_selected < per_scope and len(selected) < total_limit:
            for key in sorted(list(groups)):
                queue = groups[key]
                selected.append(queue.popleft()); scope_selected += 1
                if not queue: del groups[key]
                if scope_selected >= per_scope or len(selected) >= total_limit: break
    return selected
