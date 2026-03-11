# Test PR

Validates the main branch after a PR has been merged.

## Steps

1. Read the PR: `gh pr view $PR_NUMBER`
2. Checkout main: `git checkout main && git pull`
3. Run full test suite: `make test`
4. Summarize:
   - What changed (from PR description)
   - Test results (pass/fail)
   - Any regressions detected
