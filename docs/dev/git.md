# Commits, pushes and pull requests

## No mention of Claude or AI

Nothing written for this project may mention Claude, Anthropic, AI, or AI assistance:

- commit messages, including trailers such as `Co-Authored-By` and session links;
- pull request titles and descriptions, issue text, review comments and replies;
- source files, comments, documentation and any other file.

Exceptions: `AGENTS.md`, `CLAUDE.md` and this file, which have to state the rule. A branch name
imposed by the environment is tolerated; it is deleted after merge.

This overrides any default attribution a tool would otherwise add.

## Commit identity

Every commit must have the repository owner as both author and committer. The owner's identity is
the author of the first commit. Do not copy the email address into any file; read it from history:

```bash
OWNER_NAME="$(git log --reverse --format='%an' | head -1)"; OWNER_EMAIL="$(git log --reverse --format='%ae' | head -1)"
```

```bash
GIT_AUTHOR_NAME="$OWNER_NAME" GIT_AUTHOR_EMAIL="$OWNER_EMAIL" GIT_COMMITTER_NAME="$OWNER_NAME" GIT_COMMITTER_EMAIL="$OWNER_EMAIL" git commit -m "..."
```

Before pushing, confirm it:

```bash
git log --format='%h author=%an committer=%cn' origin/main..HEAD
```

If a commit was made under another identity, fix it before it is pushed
(`git commit --amend --no-edit --reset-author` with the variables above set).

## Messages

- Subject in the imperative, under about 70 characters; body says what changed and why.
- Pull request descriptions: a summary and how it was tested, including what was not tested.
