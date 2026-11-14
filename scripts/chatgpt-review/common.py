"""Trusted policy and anonymous, read-only GitHub access. Python 3.11+, stdlib only."""

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BOT = "openwrt-ai"
BOT_ID = 276137552
REVIEWER = "chatgpt-work-v1"
SHA = re.compile(r"[0-9a-f]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+\Z")


class ReviewError(Exception):
    """An expected failure which must never be interpreted as a clean review."""


def require(condition, message):
    if not condition:
        raise ReviewError(message)


def repo_name(value):
    require(isinstance(value, str) and REPO.fullmatch(value), "invalid repository name")
    require(value.split("/")[1] not in {".", ".."}, "invalid repository name")
    return value.lower()


def positive_int(value, label):
    require(type(value) is int and value > 0, f"invalid {label}")
    return value


def commit_sha(value):
    require(isinstance(value, str) and SHA.fullmatch(value), "invalid commit SHA")
    return value


def read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def emit(value):
    json.dump(value, sys.stdout, indent=2, ensure_ascii=True)
    sys.stdout.write("\n")


def run_cli(main):
    try:
        main()
    except (ReviewError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"chatgpt-review: {error}", file=sys.stderr)
        sys.exit(1)


def config_argument(parser):
    parser.add_argument(
        "--config", required=True, type=Path, help="trusted policy JSON"
    )


class Policy:
    def __init__(self, data):
        require(isinstance(data, dict), "policy must be an object")
        allowed = {
            "version",
            "repositories",
            "max_prs",
            "max_comments",
            "max_comment_chars",
            "max_commit_checks",
            "reference_repositories",
        }
        require(not data.keys() - allowed, "unknown policy key")
        require(data.get("version") == 1, "unsupported policy version")
        repos = data.get("repositories")
        require(isinstance(repos, list) and repos, "repository allowlist is required")
        self.repositories = tuple(dict.fromkeys(repo_name(repo) for repo in repos))
        self.max_prs = data.get("max_prs", 8)
        require(
            type(self.max_prs) is int and 1 <= self.max_prs <= 16,
            "max_prs must be between 1 and 16",
        )
        self.max_comments = data.get("max_comments", 20)
        self.max_comment_chars = data.get("max_comment_chars", 3000)
        self.max_commit_checks = data.get("max_commit_checks", 20)
        for name in ("max_comments", "max_comment_chars", "max_commit_checks"):
            positive_int(getattr(self, name), name)
        require(
            self.max_comments <= 50
            and self.max_comment_chars <= 10000
            and self.max_commit_checks <= 50,
            "policy limits exceed hard limits",
        )
        self.references = data.get("reference_repositories", [])
        require(
            isinstance(self.references, list), "reference_repositories must be a list"
        )
        for reference in self.references:
            require(
                isinstance(reference, dict) and set(reference) == {"url", "ref"},
                "reference requires exactly url and ref",
            )
            parsed = urllib.parse.urlsplit(reference["url"])
            require(
                parsed.scheme == "https"
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not parsed.query
                and not parsed.fragment
                and parsed.port in (None, 443),
                "reference must use public HTTPS",
            )
            require(
                isinstance(reference["ref"], str)
                and reference["ref"]
                and not reference["ref"].startswith("-")
                and not any(ord(char) < 33 for char in reference["ref"]),
                "invalid reference ref",
            )

    @classmethod
    def load(cls, path):
        return cls(read_json(path))

    def allow(self, repository):
        repository = repo_name(repository)
        require(repository in self.repositories, "repository is not allowlisted")
        return repository


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReviewError(
            "GitHub API redirected; update the trusted allowlist explicitly"
        )


class GitHub:
    """GET only; use the runtime's proxy without GitHub tokens, netrc or cookies."""

    def __init__(self):
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(), NoRedirect()
        )

    def get(self, path):
        require(
            path.startswith("/repos/") and not any(char in path for char in "\r\n#"),
            "invalid GitHub API path",
        )
        request = urllib.request.Request(
            "https://api.github.com" + path,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": REVIEWER,
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="GET",
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            reset = error.headers.get("X-RateLimit-Reset", "unknown")
            raise ReviewError(
                f"GitHub GET {path}: HTTP {error.code}; "
                f"rate limit reset (Unix seconds): {reset}"
            ) from error
        except urllib.error.URLError as error:
            raise ReviewError(f"GitHub GET failed: {error.reason}") from error

    def pages(self, path):
        require("?" not in path, "pagination path must not include query parameters")
        page = 1
        while True:
            data = self.get(f"{path}?per_page=100&page={page}")
            require(isinstance(data, list), "GitHub pagination response is not a list")
            yield from data
            if len(data) < 100:
                break
            page += 1

    def public_repo(self, repository):
        repository = repo_name(repository)
        data = self.get(f"/repos/{repository}")
        require(
            data.get("private") is False
            and data.get("visibility", "public") == "public",
            "repository is not public",
        )
        require(
            repo_name(data["full_name"]) == repository, "repository identity changed"
        )
        return data


def marker(sha):
    return f"<!-- {REVIEWER}:complete:{commit_sha(sha)} -->"


def last_review(reviews):
    """Only submitted COMMENT reviews with this reviewer's exact completion marker."""
    matches = []
    for review in reviews:
        sha = review.get("commit_id", "")
        if (
            review.get("user", {}).get("login") == BOT
            and review.get("user", {}).get("id") == BOT_ID
            and review.get("state") == "COMMENTED"
            and review.get("submitted_at")
            and isinstance(sha, str)
            and SHA.fullmatch(sha)
            and marker(sha) in (review.get("body") or "").splitlines()
        ):
            matches.append(review)
    return max(
        matches, key=lambda review: (review["submitted_at"], review["id"]), default=None
    )


def snapshot(repository, pr, previous=None):
    number = positive_int(pr["number"], "PR number")
    require(pr["state"] == "open" and not pr.get("merged_at"), "PR is closed or merged")
    require(
        repo_name(pr["base"]["repo"]["full_name"]) == repository,
        "unexpected PR base repository",
    )
    require(pr["base"]["repo"].get("private") is False, "PR base is not public")
    head_repo = pr["head"].get("repo")
    require(
        head_repo is not None and head_repo.get("private") is False,
        "PR head repository is deleted or not public",
    )
    return {
        "repository": repository,
        "number": number,
        "head_sha": commit_sha(pr["head"]["sha"]),
        "base_sha": commit_sha(pr["base"]["sha"]),
        "base_ref": pr["base"]["ref"],
        "head_repository": repo_name(head_repo["full_name"]),
        "previous_sha": commit_sha(previous["commit_id"]) if previous else None,
        "previous_review_id": previous["id"] if previous else None,
    }
