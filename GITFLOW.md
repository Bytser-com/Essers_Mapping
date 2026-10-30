# Git Branching Guide

This guide explains how we work with Git branches in this project.

---

## Core Rule: Keep `Development` Working!

> **Important:** The `Development` branch must **always** remain in a working, deployable state.  
> Never merge untested or incomplete code into `Development`. All feature branches must be completely finished and tested locally before merging.

---

---

## Core Rule: Commit Messages are **ALWAYS** multiline.

> **Important:** The commit messages are **NEVER** one single line, so we do never use the command `git commit -m ""`
> **ALWAYS** use the command `git commit` which opens your default teskt-editor where you can write your commit message.
> **ALWAYS** save your file withint the tekst-editor (CTRL+S) before closing, otherwise you have a empty commit message.

---

## Commit Messages

A well-structured commit message follows the **50/72 rule**:
- The **header/subject line** is at most 50 characters, written in the imperative mood ("Add", "Fix", "Refactor", not "Added" or "Fixes").
- Followed by a blank line.
- The **body** is wrapped at roughly 72 characters per line, explaining the *why* and *what*, rather than repeating the *how* (which is visible in the diff).


## Example: Feature with Breaking Change (Conventional Commits)

```gitcommit
feat(api)!: migrate search endpoint to cursor-based pagination

Replace page-offset query parameters (`?page=2&limit=50`) with
opaque cursor tokens (`?after=eyJpZ...`) on `/api/v2/search`.

Offset-based pagination caused severe degradation on datasets with
more than 50,000 items due to deep `OFFSET` scanning in PostgreSQL.
Cursor-based pagination keeps response times under 20ms regardless of
dataset depth.

BREAKING CHANGE: The `page` parameter has been removed from
`/api/v2/search`. Clients must now supply `after` or `before` query
parameters using cursors provided in the response metadata.
```

## Example: Bug Fix with Context

```gitcommit
fix(auth): prevent session timeout during active token refresh

Extend the client-side session timeout window by 60 seconds whenever
a background token refresh handshake is in flight.

Previously, requests that took longer than 1.5 seconds under high
network latency caused the frontend timer to expire before the renewed
JWT was received, forcing the user to re-login unnecessarily.

- Add `isRefreshing` state flag to auth provider
- Delay session expiration trigger if refresh is active
- Add unit test covering slow refresh responses
```

---


## Branch Overview

* **`main`**: Production-running code. This branch is live and what the clients are using in real-time.
* **`Testing`**: Production-ready code. Represents a production ready releases. This branch gets used by stakeholders and test-/beta-users.
* **`Development`**: Active working product. A working deployment which can be turned into a new release at any given time.
* **`Feature/<feature-name>`**: Temporary branches for creating new features or bug fixes. **Always branch off of `Development`**.

---

## Step-by-Step Workflow

### 1. Get the Latest Code
Before starting any new work, make sure your local copy of `Development` is completely up to date.

```bash
# Switch to the development branch
git checkout Development

# Download the latest updates from the remote repository
git pull origin Development
```

---

### 2. Create a Feature Branch
Give your branch a descriptive name explaining what you are building.

```bash
# Create and switch to a new feature branch
git checkout -b Feature/login-page
```

---

### 3. Work and Save Your Progress
Write your code and make regular, clear commits as you go.

```bash
# Check which files have been modified
git status

# Stage the files you want to include in the commit
git add .

# Save your changes with a descriptive message
git commit
```

---

### 4. Test Everything Thoroughly
Before preparing to merge, verify that your feature works and does not break existing features.

* Run **all** automated tests for this service (e.g., `npm test`, `pytest`, etc.).
* Runn **all** automated integration tests, end-to-end tests and other extra tests locally.
* Test the application manually in your browser or terminal.
* Run the required code quality tests **local** (`SonarLint`, `Semgrep`, `Gitleaks`, `jscpd` )
* Fix any bugs or broken functionality before continuing.

---

### 5. Sync with `development` Before Merging
Other team members may have added code while you were working on your Feature. Update **your** branch to avoid merge conflicts later.

```bash
# Fetch the latest changes from GitHub
git fetch origin

# Merge the newest development code into your feature branch
git merge origin/development

# If there are merge conflicts:
# 0. Find the merge conflicts using `git status`.
# 1. Open the conflicted files in a editor to your choice.
# 2. Search for the merge markers (<<<<<<<, =======, >>>>>>>).
# 3. Edit the code to keep the changes you want and delete ALL the conflict markers.
# 4. Stage the resolved files using git add <filename>.
# 3. Complete the merge commit: git commit
```

Run your tests one more time to confirm everything still works after syncing.

---

### 6. Push Your Feature and Open a Pull Request (PR)
Once the feature is finished, tested, and conflict-free, share it with the team.

```bash
# Push your branch to the remote repository
git push -u origin Feature/login-page
```

1. Open the repository on GitHub.
2. Create a **Pull Request** with your Feature branch as source branch.
3. Ensure the **Pull Request** is targeting the `Development` branch.
4. Ask a teammate to review your code.
5. Once approved and **all** checks pass, merge into `Development`.

---

### 7. Clean Up
After your branch has been merged into `Development`, clean up your workspace.

```bash
# Switch back to the development branch
git checkout Development

# Pull the freshly merged changes
git pull origin Development

# Safely delete the local feature branch
git branch -d Feature/login-page
```

---

## Quick Reference Summary

| Task | Command |
|---|---|
| Update development | `git checkout Development && git pull origin Development` |
| Create a new branch | `git checkout -b Feature/<name>` |
| Check status | `git status` |
| Commit changes | `git add . && git commit` |
| Push to remote | `git push -u origin Feature/<name>` |
| Delete local branch | `git branch -d Feature/<name>` |
| Rename local branch | `git checkout <old_name> && git branch -m Feature/<name>` |
