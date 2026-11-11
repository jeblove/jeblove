#!/usr/bin/env python3
"""Update the recent public repositories section in the GitHub profile README."""

from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

START = "<!-- RECENT_REPOS:START -->"
END = "<!-- RECENT_REPOS:END -->"
BEIJING = ZoneInfo("Asia/Shanghai")


def fetch_public_repositories(username: str, token: str) -> list[dict]:
    results: list[dict] = []
    for page in range(1, 21):
        url = (
            f"https://api.github.com/users/{username}/repos"
            f"?type=owner&sort=pushed&direction=desc&per_page=100&page={page}"
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "jeblove-profile-recent-repos",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            with urlopen(Request(url, headers=headers), timeout=25) as response:
                batch = json.load(response)
        except (HTTPError, URLError) as exc:
            raise RuntimeError(f"GitHub repository query failed: {exc}") from exc
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected GitHub API response: expected a list")
        results.extend(batch)
        if len(batch) < 100:
            break
    return results


def markdown_cell(value: str | None) -> str:
    clean = re.sub(r"\s+", " ", value or "").strip()
    return html.escape(clean, quote=False).replace("|", r"\|")


def build_recent_table(repos: list[dict], username: str, limit: int) -> str:
    candidates = [
        repo for repo in repos
        if not repo.get("private")
        and not repo.get("fork")
        and not repo.get("archived")
        and repo.get("name", "").lower() != username.lower()
        and repo.get("pushed_at")
        and repo.get("html_url")
    ]
    candidates.sort(key=lambda repo: repo["pushed_at"], reverse=True)
    recent = candidates[:limit]
    if not recent:
        return "暂无符合条件的公开原创仓库。"

    rows = [
        "| Repository | Description | Last push (UTC+8) |",
        "| --- | --- | --- |",
    ]
    for repo in recent:
        pushed = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
        pushed_local = pushed.astimezone(BEIJING).strftime("%Y-%m-%d")
        name = markdown_cell(repo["name"])
        description = markdown_cell(repo.get("description")) or "—"
        rows.append(
            f"| [{name}]({repo['html_url']}) | {description} | {pushed_local} |"
        )
    return "\n".join(rows)


def replace_section(readme: Path, section: str) -> bool:
    before = readme.read_text(encoding="utf-8")
    if before.count(START) != 1 or before.count(END) != 1:
        raise RuntimeError("README.md must contain exactly one pair of RECENT_REPOS markers")
    prefix, remaining = before.split(START, 1)
    _, suffix = remaining.split(END, 1)
    after = prefix + START + "\n" + section.rstrip() + "\n" + END + suffix
    if before == after:
        return False
    readme.write_text(after, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    username = os.environ.get("PROFILE_USERNAME", "jeblove").strip()
    token = os.environ.get("GITHUB_TOKEN", "")
    limit = int(os.environ.get("RECENT_REPOS_LIMIT", "6"))
    if not username or not (1 <= limit <= 20):
        raise ValueError("PROFILE_USERNAME or RECENT_REPOS_LIMIT invalid")
    table = build_recent_table(fetch_public_repositories(username, token), username, limit)
    changed = replace_section(Path("README.md"), table)
    print("README.md updated" if changed else "README.md unchanged")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
