# Fix Issue

Takes a GitHub issue number and implements it end-to-end.

## Steps

1. Read the issue: `gh issue view $ISSUE_NUMBER`
2. Create a feature branch: `git checkout -b feature/issue-$ISSUE_NUMBER-<short-description> main`
3. Implement the changes described in the issue
4. Write or update tests for all new/modified functions
5. Run `make test` — all tests must pass
6. Run `make lint` — no linting errors
7. Stage and commit: `git add <files> && git commit -m "feat(<module>): <description> (#$ISSUE_NUMBER)"`
8. Push: `git push -u origin feature/issue-$ISSUE_NUMBER-<short-description>`
9. Create PR: `gh pr create --title "<description>" --body "Closes #$ISSUE_NUMBER"`
