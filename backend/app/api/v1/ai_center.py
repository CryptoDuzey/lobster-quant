from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.database import get_connection


router = APIRouter(prefix="/api/v1/ai-center", tags=["ai-center"])

GITHUB_RE = re.compile(r"^https://github\.com/([^/]+)/([^/#?]+)")


class ImportGithubSkillRequest(BaseModel):
    url: str
    permissions: list[str] = []


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_github_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    match = GITHUB_RE.match(normalized)
    if not match:
        raise HTTPException(status_code=400, detail="请输入有效的 GitHub 仓库链接。")
    return match.group(1), match.group(2).removesuffix(".git")


@router.get("/skills")
def list_skills() -> dict[str, Any]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM skills ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return {"items": [_format_skill(dict(row)) for row in rows]}


@router.post("/skills/import-github")
def import_github_skill(payload: ImportGithubSkillRequest) -> dict[str, Any]:
    owner, repo = _parse_github_url(payload.url)
    repo_full_name = f"{owner}/{repo}"
    metadata = _fetch_github_metadata(owner, repo)
    skill_name = metadata.get("name") or repo
    description = metadata.get("description") or "从 GitHub 导入的待审核 Skill。"
    now = _now()
    permissions = payload.permissions or ["READ_MARKET"]
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO skills
            (name, description, source_url, repo_full_name, permissions, status, is_enabled, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
            ON CONFLICT(name, source_url) DO UPDATE SET
                description=excluded.description,
                permissions=excluded.permissions,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                skill_name,
                description,
                f"https://github.com/{repo_full_name}",
                repo_full_name,
                json.dumps(permissions, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM skills WHERE name = ? AND source_url = ?",
            (skill_name, f"https://github.com/{repo_full_name}"),
        ).fetchone()
    return {
        "success": True,
        "message": "已解析 GitHub 仓库并保存为待启用 Skill。当前版本不会执行外部代码。",
        "skill": _format_skill(dict(row)),
    }


@router.post("/skills/{skill_id}/enable")
def enable_skill(skill_id: int) -> dict[str, Any]:
    return _set_skill_enabled(skill_id, True)


@router.post("/skills/{skill_id}/disable")
def disable_skill(skill_id: int) -> dict[str, Any]:
    return _set_skill_enabled(skill_id, False)


@router.delete("/skills/{skill_id}")
def delete_skill(skill_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="未找到该 Skill。")
        conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
    return {"success": True, "deleted_id": skill_id}


def _set_skill_enabled(skill_id: int, enabled: bool) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            "UPDATE skills SET is_enabled = ?, status = ?, updated_at = ? WHERE id = ?",
            (int(enabled), "enabled" if enabled else "disabled", _now(), skill_id),
        )
        row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="未找到该 Skill。")
    return {"success": True, "skill": _format_skill(dict(row))}


def _fetch_github_metadata(owner: str, repo: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "name": repo,
        "repo_full_name": f"{owner}/{repo}",
        "safety_note": "MVP 阶段仅解析仓库信息，不执行外部代码。",
    }
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "LobsterQuant/0.1"}
    try:
        repo_response = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=12)
        if repo_response.ok:
            repo_payload = repo_response.json()
            metadata.update(
                {
                    "name": repo_payload.get("name") or repo,
                    "description": repo_payload.get("description") or "",
                    "stars": repo_payload.get("stargazers_count"),
                    "language": repo_payload.get("language"),
                    "license": (repo_payload.get("license") or {}).get("spdx_id"),
                    "updated_at": repo_payload.get("updated_at"),
                    "html_url": repo_payload.get("html_url"),
                }
            )
        readme_response = requests.get(f"https://api.github.com/repos/{owner}/{repo}/readme", headers=headers, timeout=12)
        if readme_response.ok:
            readme_payload = readme_response.json()
            metadata["readme_name"] = readme_payload.get("name")
            metadata["readme_url"] = readme_payload.get("html_url")
    except Exception as exc:
        metadata["fetch_warning"] = str(exc)
    return metadata


def _format_skill(row: dict[str, Any]) -> dict[str, Any]:
    try:
        permissions = json.loads(row.get("permissions") or "[]")
    except Exception:
        permissions = []
    try:
        metadata = json.loads(row.get("metadata_json") or "{}")
    except Exception:
        metadata = {}
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "description": row.get("description"),
        "source_url": row.get("source_url"),
        "repo_full_name": row.get("repo_full_name"),
        "permissions": permissions,
        "status": row.get("status"),
        "is_enabled": bool(row.get("is_enabled")),
        "metadata": metadata,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
