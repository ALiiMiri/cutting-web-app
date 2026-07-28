# Repository workflow

## Automatic Git handoff after Codex changes

For every task in this repository that changes files:

1. Finish the requested implementation and run the appropriate verification.
2. Review the diff and stage only the files that belong to the current task.
3. Create a clear, task-specific commit.
4. Push the current branch to its configured upstream before the final response.
   If the branch has no upstream, push it with `git push -u origin HEAD`.
5. Report the pushed branch and commit SHA to the user.

This is the default behavior; the user should not need to ask for commit and push
on every task.

Do not commit or push when:

- The user explicitly asks to keep the work local or not to commit/push.
- The task is read-only and makes no file changes.
- Required verification fails and the change is not ready.
- Authentication or the remote is unavailable.
- The intended commit cannot be isolated safely from unrelated existing changes.

When blocked, preserve the work and explain exactly what prevented the commit or
push.

## Git safety

- Preserve unrelated user changes already present in the worktree.
- Never use `git add .` or `git add -A`; stage explicit task-owned paths only.
- Never commit runtime data, databases, SQLite sidecar files, backups, exports,
  logs, `.env` files, credentials, tokens, keys, or other secrets.
- Never rewrite published history or force-push unless the user explicitly asks.
- Push the current task branch; do not merge into or push directly to `main`
  unless the user explicitly requests that destination.
