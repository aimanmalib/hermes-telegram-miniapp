"""Skills index and the agent's memory files (read-only)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

compat = sys.modules["hermes_tma_hermes_compat"]  # loaded first by plugin_api.py
router = APIRouter()
_log = logging.getLogger("hermes.plugin.telegram-app")


def _skills_root() -> Path:
    return compat.hermes_home() / "skills"


def _parse_skill_meta(skill_md: Path) -> Dict[str, Any]:
    """Pull name + description from the YAML frontmatter of a SKILL.md."""
    name = skill_md.parent.name
    description = ""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"name": name, "description": "", "size": 0}
    size = len(text.encode("utf-8"))
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            front = text[3:end]
            for line in front.splitlines():
                line = line.strip()
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("description:"):
                    description = (
                        line.split(":", 1)[1].strip().strip('"').strip("'")
                    )
    return {"name": name, "description": description, "size": size}


@router.get("/skills")
async def skills_list():
    """List all installed skills (one entry per SKILL.md)."""
    root = _skills_root()
    if not root.exists():
        return {"skills": [], "root": str(root)}

    items: List[Dict[str, Any]] = []
    for skill_md in sorted(root.rglob("SKILL.md")):
        try:
            rel = skill_md.parent.relative_to(root)
        except ValueError:
            continue
        category = rel.parts[0] if len(rel.parts) > 1 else None
        meta = _parse_skill_meta(skill_md)
        items.append(
            {
                "id": str(rel).replace("\\", "/"),
                "name": meta["name"],
                "description": meta["description"],
                "category": category,
                "size": meta["size"],
                "path": str(skill_md),
            }
        )
    items.sort(key=lambda x: ((x["category"] or "zzz"), x["name"]))
    return {"skills": items, "count": len(items), "root": str(root)}


def _safe_skill_path(skill_id: str) -> Optional[Path]:
    """Resolve a skill id to its absolute SKILL.md, refusing escapes."""
    if not skill_id or ".." in skill_id.split("/"):
        return None
    root = _skills_root().resolve()
    candidate = (root / skill_id / "SKILL.md").resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.exists() else None


@router.get("/skills/{skill_id:path}")
async def skill_view(skill_id: str):
    """Return the full SKILL.md text for a single skill."""
    p = _safe_skill_path(skill_id)
    if not p:
        raise HTTPException(status_code=404, detail="Skill not found")
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "id": skill_id,
        "content": text,
        "size": len(text.encode("utf-8")),
        "path": str(p),
    }


@router.get("/memory")
async def memory_dump():
    """Return the agent's persistent memory + user profile (read-only)."""
    base = compat.hermes_home() / "memories"
    out: Dict[str, Any] = {"root": str(base), "files": {}}
    for label, fname in (("memory", "MEMORY.md"), ("user", "USER.md")):
        path = base / fname
        if not path.exists():
            out["files"][label] = {
                "exists": False, "content": "", "size": 0, "mtime": 0,
            }
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            stat = path.stat()
            out["files"][label] = {
                "exists": True,
                "content": text,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "path": str(path),
            }
        except Exception as exc:
            out["files"][label] = {
                "exists": True,
                "content": f"<read error: {exc}>",
                "size": 0,
                "mtime": 0,
            }
    return out
