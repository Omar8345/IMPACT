"""Fetch a public GitHub PR at a fixed head commit and optionally comment on it."""

import json
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


PR_PATH = re.compile(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/(\d+)/?$")
SHA = re.compile(r"^[0-9a-f]{40}$")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def parse_pr_url(url):
    parts = urlsplit(url)
    match = PR_PATH.fullmatch(parts.path)
    if (parts.scheme != "https" or parts.netloc != "github.com" or
            parts.query or parts.fragment or not match):
        raise ValueError("Expected a URL like https://github.com/owner/repo/pull/123")
    owner, repo, number = match.groups()
    if owner in {".", ".."} or repo in {".", ".."} or repo.endswith(".git"):
        raise ValueError("Invalid GitHub repository in PR URL")
    return owner, repo, int(number)


def get_pr(url):
    owner, repo, number = parse_pr_url(url)
    endpoint = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    request = Request(endpoint, headers={"Accept": "application/vnd.github+json",
                                         "User-Agent": "IMPACT-PR-review"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"GitHub could not load this public PR (HTTP {exc.code}).") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach GitHub: {exc.reason}") from exc
    base = payload.get("base", {})
    head = payload.get("head", {})
    base_sha, head_sha, base_ref = base.get("sha", ""), head.get("sha", ""), base.get("ref", "")
    if not SHA.fullmatch(base_sha) or not SHA.fullmatch(head_sha) or not REF.fullmatch(base_ref):
        raise RuntimeError("GitHub returned incomplete PR commit information.")
    return {"owner": owner, "repo": repo, "number": number,
            "url": f"https://github.com/{owner}/{repo}/pull/{number}",
            "base_sha": base_sha, "head_sha": head_sha, "base_ref": base_ref}


def _git(args, cwd=None, timeout=180):
    try:
        result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("GitHub checkout timed out.") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError(f"Git command failed: {detail[-1] if detail else 'unknown error'}")
    return result.stdout.strip()


@contextmanager
def checkout_pr(pr):
    """Yield (head checkout, merge-base-to-head diff), then remove the checkout."""
    with tempfile.TemporaryDirectory(prefix="impact-pr-") as temporary:
        repo = Path(temporary) / "repo"
        remote = f"https://github.com/{pr['owner']}/{pr['repo']}.git"
        _git(["-c", "protocol.file.allow=never", "clone", "--filter=blob:none",
              "--no-checkout", "--single-branch", "--branch", pr["base_ref"],
              remote, str(repo)], timeout=300)
        _git(["fetch", "--no-tags", "origin", f"pull/{pr['number']}/head"], cwd=repo)
        fetched_head = _git(["rev-parse", "FETCH_HEAD"], cwd=repo)
        if fetched_head != pr["head_sha"]:
            raise RuntimeError("The PR changed during checkout. Run the command again.")
        try:
            base_type = _git(["cat-file", "-t", pr["base_sha"]], cwd=repo)
        except RuntimeError:
            base_type = None
        if base_type != "commit":
            _git(["fetch", "--no-tags", "origin", pr["base_sha"]], cwd=repo)
        merge_base = _git(["merge-base", pr["base_sha"], pr["head_sha"]], cwd=repo)
        _git(["-c", "core.hooksPath=/dev/null", "checkout", "--detach", pr["head_sha"]], cwd=repo)
        diff = _git(["diff", "--no-ext-diff", "--unified=3", merge_base, pr["head_sha"]], cwd=repo)
        yield repo, diff


def post_comment(pr, body):
    """Post a timeline comment using the user's existing gh authentication."""
    endpoint = f"repos/{pr['owner']}/{pr['repo']}/issues/{pr['number']}/comments"
    try:
        result = subprocess.run(["gh", "api", endpoint, "--method", "POST", "--input", "-"],
                                input=json.dumps({"body": body}), text=True, capture_output=True,
                                timeout=30, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("Install GitHub CLI (gh) to use --post-comment.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("GitHub comment request timed out. Check the PR before retrying.") from exc
    if result.returncode:
        raise RuntimeError("Could not post the PR comment. Run `gh auth login` and check PR write access.")
    return json.loads(result.stdout).get("html_url", pr["url"])
