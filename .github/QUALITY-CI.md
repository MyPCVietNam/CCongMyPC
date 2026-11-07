# Required GitHub Checks

After the workflow has run at least once on the actual source-carrying branch, go to repository Settings → Rules → Rulesets (or branch protection) and require successful `guard-contract`, `backend-linux`, `frontend`, `windows-contract`, with review and no force push. Do not configure arbitrary statuses before GitHub has registered them. Verify expected source app is `GitHub Actions`.

Use read-only `GITHUB_TOKEN` permissions, `pull_request` (never `pull_request_target` for untrusted fork code), immutable SHAs for checkout/setup actions and no sensitive secrets on runner.

Repository `main` was LICENSE-only on audit. A branch rule protecting `main` is important but **cannot validate absent application code**. Introduce guards into the real PR's source branch and review the merge base; reconcile source history before any production merge.

When CI fails: read the failing job, reproduce with no host side effects, repair the source or test harness. Do not remove jobs, add `continue-on-error`, or use blanket skips.
