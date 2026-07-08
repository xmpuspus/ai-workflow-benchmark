"""Mine a private benchmark task from a merged GitHub pull request.

Pins the pre-merge commit as the task's repo.commit, then generates a
setup_commands entry that overlays the PR's own test files onto that
pre-merge workspace. Talks to GitHub exclusively through the `gh` CLI so no
new runtime dependency (token handling, HTTP client) is needed — `gh auth`
is assumed to already be configured on the machine running this.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import shlex
import subprocess
from pathlib import Path

_PR_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

_EXT_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
}

DEFAULT_TEST_COMMAND = "python -m pytest"


class PrMinerError(Exception):
    """User-facing failure while mining a task from a PR (bad URL, unmerged PR, gh failure)."""


@dataclasses.dataclass
class MinedTask:
    task: dict
    owner: str
    repo: str
    number: int
    merge_commit_sha: str
    premerge_sha: str
    test_files: list[str]
    source_files: list[str]


def parse_pr_url(url: str) -> tuple[str, str, int]:
    match = _PR_URL_RE.match((url or "").strip())
    if not match:
        raise PrMinerError(f"Not a GitHub pull request URL: {url}")
    return match.group("owner"), match.group("repo"), int(match.group("number"))


def _run_gh(*args: str, timeout: float = 30.0) -> str:
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise PrMinerError(
            "gh CLI not found — install and authenticate the GitHub CLI (gh auth login)"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PrMinerError(f"gh {' '.join(args)} timed out") from exc
    if result.returncode != 0:
        raise PrMinerError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _gh_api_json(path: str, extra_args: list[str] | None = None):
    out = _run_gh("api", path, *(extra_args or []))
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise PrMinerError(f"gh api {path} returned invalid JSON: {exc}") from exc


def fetch_pr_metadata(owner: str, repo: str, number: int) -> dict:
    return _gh_api_json(f"repos/{owner}/{repo}/pulls/{number}")


def fetch_pr_files(owner: str, repo: str, number: int) -> list[dict]:
    # 100 is the GitHub API's max per_page for this endpoint; larger PRs only
    # get their first 100 changed files considered (rare in practice for
    # tasks we'd want to turn into a benchmark item anyway).
    return _gh_api_json(f"repos/{owner}/{repo}/pulls/{number}/files", ["-F", "per_page=100"])


def resolve_premerge_sha(owner: str, repo: str, merge_commit_sha: str) -> str:
    commit = _gh_api_json(f"repos/{owner}/{repo}/commits/{merge_commit_sha}")
    parents = commit.get("parents") or []
    if not parents:
        raise PrMinerError(f"Merge commit {merge_commit_sha} has no parents")
    return parents[0]["sha"]


def _is_test_file(path: str) -> bool:
    basename = path.rsplit("/", 1)[-1]
    if "tests/" in path:
        return True
    if basename.startswith("test_"):
        return True
    if re.search(r"_test\.[^.]+$", basename):
        return True
    return ".spec." in basename or ".test." in basename


def split_test_and_source_files(paths: list[str]) -> tuple[list[str], list[str]]:
    test_files: list[str] = []
    source_files: list[str] = []
    for p in paths:
        (test_files if _is_test_file(p) else source_files).append(p)
    return test_files, source_files


def infer_languages(paths: list[str]) -> list[str]:
    langs: list[str] = []
    for p in paths:
        lang = _EXT_LANGUAGES.get(Path(p).suffix.lower())
        if lang and lang not in langs:
            langs.append(lang)
    return langs or ["python"]


def _clean_body(body: str | None) -> str:
    return _HTML_COMMENT_RE.sub("", body or "").strip()


def build_description(title: str, body: str | None) -> str:
    clean_body = _clean_body(body)
    return f"{title}\n\n{clean_body}" if clean_body else title


def _normalize_title(raw_title: str) -> str:
    title = (raw_title or "").strip() or "Untitled pull request"
    if len(title) < 10:
        title = f"{title} (mined from PR)"
    if len(title) > 120:
        title = title[:117].rstrip() + "..."
    return title


def build_test_overlay_command(merge_commit_sha: str, test_paths: list[str]) -> str:
    quoted = " ".join(shlex.quote(p) for p in test_paths)
    # The workspace's "origin" remote is the local bare-mirror cache
    # (RepoManager.prepare clones --local from it), not the GitHub URL, so
    # this fetch only pulls in the merge commit if the mirror itself already
    # has it — true whenever the mirror was cloned/refreshed after the PR
    # merged. It's a best-effort safety net for a stale mirror, not a
    # guarantee; `awb warmup --clear` forces a fresh mirror if this misses.
    fetch = f"git fetch origin {merge_commit_sha} || true"
    checkout = f"git checkout {merge_commit_sha} -- {quoted}"
    return f"{fetch} && {checkout}"


def build_test_command(test_command: str, test_paths: list[str]) -> str:
    if not test_paths:
        return test_command
    quoted = " ".join(shlex.quote(p) for p in test_paths)
    return f"{test_command} {quoted}"


def _primary_source_token(source_files: list[str], test_files: list[str]) -> str:
    candidates = source_files or test_files
    if not candidates:
        return "."
    first = candidates[0]
    return first.split("/", 1)[0] if "/" in first else first


def build_partial_credit(
    full_test_command: str,
    scoped_test_command: str,
    source_files: list[str],
    test_files: list[str],
) -> list[dict]:
    token = _primary_source_token(source_files, test_files)
    return [
        {
            "criterion": "PR's overlaid tests pass",
            "points": 60,
            "check": scoped_test_command,
        },
        {
            "criterion": "Full test suite has no regressions",
            "points": 30,
            "check": full_test_command,
        },
        {
            "criterion": "Source files were touched",
            "points": 10,
            "check": f"git diff --name-only HEAD | grep -q {shlex.quote(token)}",
        },
    ]


def mine_task_from_pr(
    pr_url: str,
    *,
    category: str = "feature-addition",
    difficulty: str = "medium",
    estimated_minutes: int = 30,
    test_command: str = DEFAULT_TEST_COMMAND,
    extra_setup_commands: list[str] | None = None,
    contamination_risk: str = "low",
) -> MinedTask:
    owner, repo, number = parse_pr_url(pr_url)
    pr = fetch_pr_metadata(owner, repo, number)

    if not pr.get("merged"):
        raise PrMinerError(f"PR #{number} is not merged — only merged PRs can become tasks")

    merge_commit_sha = pr.get("merge_commit_sha")
    if not merge_commit_sha:
        raise PrMinerError(f"PR #{number} has no merge_commit_sha")

    premerge_sha = resolve_premerge_sha(owner, repo, merge_commit_sha)

    files = fetch_pr_files(owner, repo, number)
    paths = [f["filename"] for f in files]
    test_files, source_files = split_test_and_source_files(paths)

    languages = infer_languages(paths)
    setup_commands = list(extra_setup_commands or [])
    if test_files:
        setup_commands.append(build_test_overlay_command(merge_commit_sha, test_files))

    scoped_test_command = build_test_command(test_command, test_files)
    now = dt.datetime.now(dt.UTC).isoformat()

    task: dict = {
        "category": category,
        "title": _normalize_title(pr.get("title", "")),
        "difficulty": difficulty,
        "estimated_minutes": estimated_minutes,
        "languages": languages,
        "repo": {
            "url": f"https://github.com/{owner}/{repo}",
            "commit": premerge_sha,
            "setup_commands": setup_commands,
        },
        "issue": {
            "description": build_description(pr.get("title", ""), pr.get("body")),
            "files_to_examine": source_files[:8],
        },
        "verification": {
            "test_commands": [scoped_test_command],
            "lint_commands": [],
            "security_commands": [],
            "partial_credit": build_partial_credit(
                test_command, scoped_test_command, source_files, test_files
            ),
        },
        "constraints": {
            "max_iterations": 20,
            "timeout_seconds": 1800,
        },
        "provenance": {
            "source_pr_url": pr.get("html_url", pr_url),
            "created_at": now,
            "last_verified_at": now,
        },
        "contamination_risk": contamination_risk,
        "label": "real_pr",
    }

    return MinedTask(
        task=task,
        owner=owner,
        repo=repo,
        number=number,
        merge_commit_sha=merge_commit_sha,
        premerge_sha=premerge_sha,
        test_files=test_files,
        source_files=source_files,
    )
