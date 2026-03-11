# Workflow Rules

## GitHub-Driven Development
- All work MUST be tied to a GitHub issue
- Never commit directly to `main`
- Branch naming: `feature/issue-N-short-description` (e.g., `feature/issue-3-scenario-yamls`)
- Commit messages reference issue: `feat(module): description (#N)` or `fix(module): description (#N)`

## Branch Lifecycle
1. `gh issue view N` — read the issue
2. `git checkout -b feature/issue-N-description main`
3. Implement changes with tests
4. `make test` and `make lint` must pass
5. `git push -u origin feature/issue-N-description`
6. `gh pr create --title "..." --body "Closes #N"` — PR links to issue

## PR Requirements
- All tests pass (`make test`)
- Linting passes (`make lint`)
- PR description includes what changed and how to verify
- Merge via squash merge to keep main clean
