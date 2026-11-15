# ChatGPT Work PR review — setup

This is a **dry-run implementation** of the batched reviewer in
`llm-review-prompts/chatgpt-work-batched-pr-review.md`. It discovers public PRs,
prepares Git worktrees, and validates structured findings into manual publishing
previews. It makes no model/API calls and contains no GitHub publisher, review
schedule, or automatic reply operation. Existing Claude workflows are unchanged.

## Requirements and environment

Use your existing personal ChatGPT Pro account with Work and GitHub available.
Work/Codex consume the subscription's shared usage allowance; this workflow
does not need an OpenAI API key. Subscription access does not guarantee enough
allowance to review eight or sixteen large PRs in one run. Check actual usage
and reduce the batch when necessary.

The scripts need Python 3.11+, Git, a POSIX shell, disk space, and anonymous
HTTPS access to `api.github.com`, `github.com`, and explicitly configured public
reference hosts. They use the Python standard library only. Anonymous GitHub
API limits can be reached while scanning many PRs/reviews; failures include the
HTTP status and reset timestamp. Do not silently add personal credentials to
work around a rate limit. Retry after reset or use a separately designed bot-only
read service if the workload exceeds anonymous limits.

Hosted runtimes may route permitted HTTPS requests through an environment proxy.
The API client honors the runtime's standard proxy settings; Git retains only
the standard proxy/no-proxy variables and explicitly supported CA-bundle settings
alongside its restricted environment. GitHub requests still have no GitHub
authentication, and TLS verification remains enabled. Proxy routing/authentication
is separate from the GitHub account used by the connector. Do not copy proxy
credentials or environment values into the repository or execution logs.

If preliminary HTTPS probes succeed but discovery fails with `Temporary failure
in name resolution`, check that the pinned tooling includes proxy support. The
initial `4cc96ea` version disabled Python environment proxies and stripped them
from Git subprocesses. Use an updated tooling commit and repeat the dry run.
If the error persists, compare the probe and script execution environments and
report which transport failed; do not enable broader access or substitute tokens.

Start with a manually invoked Work task using a trusted local checkout of this
repository and an output directory outside every reviewed checkout. Test that
the actual environment can execute Python/Git and make the required GETs/fetches
before creating a schedule. Do not grant unrestricted shell/network access
solely to make background execution succeed. Trust and protect the script and
policy files separately from the PR worktrees.

The execution OS account must have no `.netrc` or `_netrc` file. Git/libcurl can
consult these independently of credential helpers, so preparation refuses to
run when either exists; it never reads their contents. Use a dedicated execution
account rather than relocating personal credentials into a checkout.

Scheduled web tasks can use connected tools and uploaded context, but do not
retain a local folder/worktree between runs. Desktop tasks needing local files
require the host to stay online with the app running. If using a cloud environment,
explicitly test shell/Git/network support, bootstrap the trusted scripts from an
operator-reviewed commit, and arrange durable output storage. Do not assume a
personal Work task inherits a Codex Cloud repository or its setup scripts.

See the official [scheduled-task documentation](https://learn.chatgpt.com/docs/automations),
[Work environment guidance](https://learn.chatgpt.com/docs/use-chatgpt), and
[subscription usage documentation](https://learn.chatgpt.com/docs/pricing).
Availability, approval behavior, model limits, and UI labels may vary by surface.

## Account and permission setup

1. In ChatGPT's GitHub connections, keep only the intended `openwrt-ai` identity
   available to the reviewer. Disconnect the personal `hauke` connection before
   automatic operation, as agreed for this setup. Review other enabled plugins
   and any signed-in browser sessions separately; disconnecting one GitHub app
   connection does not revoke other credentials or browser sessions.
2. Run the GitHub connector's authenticated-user read operation. Verify both
   `login: openwrt-ai` and `id: 276137552`. Repeat in the actual task environment,
   and again immediately before preparing a publishing preview. Never fall back
   to another account. Removing/reconnecting accounts can change tool parameters;
   use the actual tool schema, not a stale saved connection ID.
3. Keep all credentials in the connector's protected authorization mechanism.
   Do not put PATs, cookies, ChatGPT sessions, or tokens into scripts, configuration,
   the repository, logs, or untrusted worktrees. The scripts deliberately ignore
   Git credentials and use only unauthenticated GitHub GETs and HTTPS Git remotes.

The scripts enforce their own allowlist, anonymous access, and validation. They
cannot restrict what the Work model can do through another enabled tool. Prompt
instructions, identity JSON, a filesystem sandbox, and disconnecting `hauke` do
not provide a `COMMENT`-only permission boundary for the general GitHub connector.
There is no verified personal-Pro task-level connection lock implemented here.
Managed Team Tasks have a different service-account/connection model; do not
assume those controls exist for this personal task. See
[workspace connections](https://learn.chatgpt.com/docs/enterprise/shared-connections).

**Automatic publishing remains disabled.** A future publisher must have only
bot credentials, enforce the exact policy and payload itself, and exclude direct
unrestricted write tools from the reviewer. It must verify the live authenticated
identity, PR openness, head/base snapshots, and thread eligibility at submission,
use `COMMENT` with the explicit reviewed commit, and implement per-PR locking
and reconciliation after timeouts before retrying. Rechecking an SHA cannot
eliminate a concurrent push; submissions must remain pinned to the analyzed SHA.
The preview's payload hash identifies the reviewed payload; it is not a signature
or authorization token. Do not connect an automated publisher to these previews
without implementing that boundary and separately authorizing publication.

## Trusted policy

Copy `scripts/chatgpt-review/config.example.json` to a protected location outside
the reviewed worktrees. The example allowlists only
`hauke/actions-shared-workflows`; replace or extend `repositories` explicitly
with public targets such as `openwrt/openwrt`. Never infer an allowlist from PR
titles, repository files at PR head, model output, or comments.

`max_prs` defaults to 8 and must be 1–16. `--max-prs` on discovery can override
the batch limit up to 16. The policy also bounds inline/reply count, per-comment
characters, and commit-check count; hard upper limits still apply. Reference
repositories are optional entries like:

```json
{"url": "https://github.com/u-boot/u-boot.git", "ref": "master"}
```

Only public HTTPS remotes belong in this trusted list. Select kernel tags from
the trusted base's version files, rather than blindly tracking current Linux.
Repeat a URL with different refs to make multiple versions available. Reference
fetches are shallow, use separate detached worktrees, and share one bare clone
per URL. Source repositories retain full commit history for incremental review.
Neither submodules nor custom filters are followed. Private/internal reference
hosts must be excluded using the environment's network policy as well.

## Manual dry run

Use absolute paths in a Work task. The shell examples below assume this trusted
repository is the current directory and a trusted policy at `/tmp/review-policy.json`.
Put the task's output in a new private directory:

```sh
review_run=$(mktemp -d /tmp/chatgpt-review-run.XXXXXXXX)
python3 -E -s scripts/chatgpt-review/discover.py \
  --config /tmp/review-policy.json --max-prs 1 > "$review_run/discovery.json"
```

Check the exit status and JSON before continuing. A per-PR failure is included
in `failed` with exit status 1; successfully discovered PRs can still be reviewed
manually. API/listing failures return a manifest with `failed` and exit status 1,
then stop further scanning. Pending work is fetched oldest-update-first from
GitHub and merged across repositories. Discovery stops as soon as the batch is
full instead of checking every open PR's review history. Review pagination is
still complete for each inspected PR. Only complete, submitted ChatGPT bot
reviews count; unchanged heads are skipped. New PRs and changed heads are selected.

For the first dry run, select one known open PR directly (replace `12345` with
the actual PR number and ensure its repository is in the trusted policy):

```sh
python3 -E -s scripts/chatgpt-review/discover.py \
  --config /tmp/review-policy.json \
  --repository openwrt/openwrt --pr 12345 > "$review_run/discovery.json"
```

This reads only repository metadata, that PR, and its review history; it never
lists the repository's other open PRs. Use `--repository` and `--pr` together.
An ordinary one-PR batch also stops early, but may inspect unchanged PRs first.
When discovery stops early, `scan_complete` is false and `deferred` is null:
the remainder is unknown, not zero. Skipped/failed counts cover only inspected
PRs. Do not enumerate the rest just to calculate a log count.

The older `c81ec17` discovery scanned all reviews before applying the batch cap;
on large repositories such as OpenWrt this could exhaust the anonymous quota
even with `max_prs: 1`. Use the updated tooling and wait for the quota reset
reported by GitHub before retrying. Early stopping reduces requests but does
not remove rate limits, especially when many unchanged heads must be skipped
or a PR has a large review history. Never add personal credentials automatically.

```sh
sh scripts/chatgpt-review/prepare-worktrees.sh \
  --config /tmp/review-policy.json "$review_run/discovery.json" \
  > "$review_run/prepared.json"
```

Use `--reference 0` (repeatable, zero-based) only for relevant configured public
references. An empty batch creates no clone directory. `prepared.json` reports
its private temporary root, per-PR worktrees, trusted rule files, review diff,
full PR diff, commit metadata, and failures. Source PRs are fetched from the
**base repository's** `refs/pull/<number>/head`, including fork PRs. A missing or
changed ref is a failure, not a different checkout to review.

If the last reviewed SHA is an ancestor, review incrementally. If the SHA is
unavailable or history was rewritten, inspect the full PR from its merge base.
Rewritten commit messages are included in commit inspection even when the file
tree is unchanged. Shallow source history is rejected. Rules are extracted from
the discovered base SHA as a regular Git blob; a symlink cannot supply rules.
PR checkout symlinks are materialized as text to avoid following them off-tree.

Ask Work to follow the task prompt and produce one findings file per PR, based
on `scripts/chatgpt-review/findings.example.json`. It must inspect code and
discussion; scripts do not perform AI analysis. Keep the task rooted in the
trusted project, not the PR worktree, to avoid loading PR-controlled instructions.

Immediately after a real connector identity read, save its actual result with
the observation time in an identity file:

```json
{
  "login": "openwrt-ai",
  "id": 276137552,
  "observed_at": "2026-11-14T12:00:00+00:00"
}
```

Replace the example time with the current UTC observation time. Never fill in
identity from memory. Evidence must be at most five minutes old, with a timezone.
For proposed `fixed_threads`, capture the connector's thread state as:

```json
{
  "observed_at": "2026-11-14T12:00:00+00:00",
  "repository": "hauke/actions-shared-workflows",
  "number": 1,
  "head_sha": "0000000000000000000000000000000000000000",
  "threads": [{"comment_id": 7, "is_resolved": false, "comment_count": 1}]
}
```

Replace all example identifiers with actual observations from the target PR.
This is a normalized observation format, not the raw output of any particular
connector version. Public REST replies are rechecked, but unresolved state
comes from this recent connector observation because the public REST comment
list does not expose thread resolution. The code cannot prove that a finding
is semantically fixed or that a model-supplied observation is authentic.

```sh
python3 -E -s scripts/chatgpt-review/validate-review.py \
  --config /tmp/review-policy.json \
  --manifest "$review_run/discovery.json" \
  --identity "$review_run/identity.json" \
  "$review_run/findings-1.json" > "$review_run/preview-1.json"
```

Add `--threads "$review_run/threads-1.json"` only when proposing replies. The
validator checks policy, bot identity observation, snapshot, open/public state,
head and base freshness before and after reads, full file pagination, LEFT/RIGHT
line locations, same-hunk ranges, action, sizes/counts, duplicate payload entries,
commit membership, and eligible prior ChatGPT threads. Missing/truncated textual
patches are rejected for inline anchors. GitHub's 3,000-file listing limit is
detected using `changed_files`; commit-check validation rejects PRs above the
250-commit endpoint cap. Binary files have no textual inline anchors. Sentence
count, relevance, semantic duplicate findings, and correctness need model/human
review; size/location validation is not a proof of review quality.

**Stop after inspecting the previews.** No script accepts a publish/enable flag.
Each preview explicitly says `publishing_enabled: false`. Validation failure
returns nonzero and emits no preview. Identity evidence is not an authentication
mechanism, and a preview can become stale before someone submits it.

## Completion and retries

A future/manual authorized `COMMENT` review must use the exact analyzed
`commit_id` and the generated body. A hidden body marker of the form
`<!-- chatgpt-work-v1:complete:<40-character SHA> -->` records successful completion,
including reviews with no findings. Discovery requires both the fixed bot
login/numeric identity and this exact marker on a submitted `COMMENTED` review.
Old Claude reviews, pending reviews, and dismissed reviews do not count.

Dry-run previews do not advance published completion. Repeated dry runs will
review the same unpublished heads intentionally. Archive findings/previews and
logs in durable trusted storage if you want to reuse analysis manually. Do not
pretend an unpublished preview or an incomplete review was posted. Once a marked
review is actually submitted, unchanged heads will be skipped by discovery.

Never automatically retry a write after a timeout: verify whether the marked
review already exists first. This implementation checks existing completion
during preview validation but has no cross-run publisher lock and cannot prevent
two simultaneous users from later submitting the same preview. This is one
reason automatic publication is not part of this implementation.

## Fork test and future schedules

1. Open a small public fork PR against an explicitly allowlisted test repository.
   Include a known issue and optionally an untrusted instruction in its title or
   comment. Verify it remains inert data. Do not run its code.
2. Run discovery with one PR, prepare its worktree, analyze it, and validate the
   preview. Verify the checkout SHA matches the PR head and that trusted base
   rules were used. Inspect every proposed inline anchor and suggestion.
3. Push a fix and repeat. The stale old findings must fail validation. To test
   published-history skipping without posting, use the offline tests below.
   Live completion/reply tests require separate explicit authorization to post
   on a disposable test PR; none is granted by following this setup guide.
4. Test actual task tool/approval behavior before relying on unattended execution.
   Offline tests cannot establish that publishing or scheduling works in Work.

After the manual dry run is satisfactory, the operator may separately create
one standalone scheduled task using the version-controlled prompt, explicit
trusted paths, and UTC timezone. The intended times are **03:00 and 15:00 UTC**:

```text
RRULE:FREQ=DAILY;BYHOUR=3,15;BYMINUTE=0;BYSECOND=0
```

If the UI requires two schedules, use two triggers with identical task instructions
and prevent overlapping runs at the execution host. Check the saved timezone;
Berlin local time changes with daylight saving. Start with a one-PR batch and
inspect the first runs before increasing to eight (or sixteen). Scheduling a
dry-run task does not enable publishing. Before any future live activation,
disable the Claude reviewer to avoid two systems using `openwrt-ai` completion
history. This repository does not disable Claude for you.

To pause, disable the task in ChatGPT's Scheduled view. Also stop any running
task; disabling future triggers need not stop an already running invocation.
Revoking bot authorization is a separate emergency stop for connector access.

## Operations and security limits

Retain stdout JSON, stderr, exit codes, and the Work execution log outside the
reviewed worktrees. Distinguish skipped, deferred, failed, validated, and actually
published PRs. This implementation always publishes zero. On failure, repair
policy/access or retry discovery; do not edit the expected SHA to force acceptance.
Retain the temp root while investigating; afterward remove only that exact
reported temporary directory. Each preparation invocation uses a fresh root and
does not reuse previous or attacker-created clones.

The Git subprocess environment drops ambient tokens, askpass helpers, global
configuration, templates, hooks, custom attributes, and non-HTTPS protocols.
Arguments are arrays without a shell. PR numbers, repository names, SHAs and
diff anchors are validated. Push URLs in temporary clones are deliberately
unusable. These controls constrain the supplied scripts, not arbitrary future
commands issued by the model. Resource exhaustion from very large repositories
or diffs still requires host limits; run in a dedicated restricted environment.

Work versus Codex Cloud and Claude Routines:

| Capability | This Work implementation | Existing Claude routines / Codex Cloud |
| --- | --- | --- |
| Trigger | Operator-configured Work schedule, not activated here | Claude HTTP routine trigger; Codex Cloud has its own task/environment model |
| Model billing | Existing ChatGPT subscription allowance | Separate product-specific allowance/configuration |
| PR contexts | One worktree per PR; separate model contexts must be tested | Claude prompt delegates; no assumption of identical Work orchestration |
| Source setup | Trusted scripts and explicit runtime/network prerequisites | Existing consumer/routine or Cloud environment setup |
| Publishing | Preview only; future enforced bot-only publisher required | Existing Claude connector posts; not reused by these scripts |

Manual configuration still required: trusted policy and script commit, runtime
and network restrictions, durable output location, bot-only connector access,
manual fork test, then any separately requested schedule. Live posting also
requires a separately reviewed publisher/permission boundary and authorization.

## Offline checks

```sh
python3 -B -m unittest discover -s scripts/chatgpt-review/tests -v
ruff check scripts/chatgpt-review
shellcheck scripts/chatgpt-review/prepare-worktrees.sh
```

Tests mock public GitHub responses and use local Git fixtures only. They never
call a model or post a review. Local-file Git transport exists only in the test
fixture runner; production Git access allows HTTPS only.

`.github/workflows/chatgpt-review-checks.yml` runs these offline tests for tooling
PRs or manual dispatch. It has no review trigger, schedule, secrets, or write
permissions and does not run the discovery scripts against live GitHub.
