#!/usr/bin/env python3
"""Discover public PRs needing ChatGPT review; never write to GitHub."""

import argparse
from datetime import UTC, datetime

from common import (
    REVIEWER,
    GitHub,
    Policy,
    ReviewError,
    config_argument,
    emit,
    last_review,
    positive_int,
    require,
    run_cli,
    snapshot,
)


def discover(api, policy, maximum=None):
    maximum = policy.max_prs if maximum is None else maximum
    require(
        type(maximum) is int and 1 <= maximum <= 16, "max-prs must be between 1 and 16"
    )
    candidates, skipped, failures = [], [], []
    for repository in policy.repositories:
        api.public_repo(repository)
        # Fetch all PR pages. Sorting pending work oldest-first prevents a busy
        # repository's newest updates from starving the same older PRs forever.
        for pr in api.pages(f"/repos/{repository}/pulls"):
            if pr.get("state") != "open":
                continue
            try:
                number = positive_int(pr["number"], "PR number")
                previous = last_review(
                    api.pages(f"/repos/{repository}/pulls/{number}/reviews")
                )
                item = snapshot(repository, pr, previous)
                if item["head_sha"] == item["previous_sha"]:
                    skipped.append({**item, "reason": "already reviewed by ChatGPT"})
                else:
                    candidates.append((pr.get("updated_at", ""), item))
            except (ReviewError, KeyError, ValueError, TypeError) as error:
                # Keep successful discoveries reviewable, but make failures
                # explicit and return a failing exit status from the CLI.
                failures.append(
                    {
                        "repository": repository,
                        "number": pr.get("number"),
                        "error": str(error),
                    }
                )
    candidates.sort(
        key=lambda entry: (entry[0], entry[1]["repository"], entry[1]["number"])
    )
    return {
        "version": 1,
        "reviewer": REVIEWER,
        "mode": "dry-run",
        "generated_at": datetime.now(UTC).isoformat(),
        "prs": [item for _, item in candidates[:maximum]],
        "deferred": len(candidates[maximum:]),
        "skipped": skipped,
        "failed": failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    config_argument(parser)
    parser.add_argument("--max-prs", type=int)
    args = parser.parse_args()
    result = discover(GitHub(), Policy.load(args.config), args.max_prs)
    emit(result)
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    run_cli(main)
