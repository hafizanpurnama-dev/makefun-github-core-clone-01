[![make.fun · github-core-clone-01](https://make.fun/badge/github-core-clone-01.svg)](https://make.fun/bounty/github-core-clone-01?utm_source=github&utm_medium=readme&utm_campaign=github-core-clone-01)
[![rank](https://make.fun/badge/github-core-clone-01/hafizanpurnama-dev/makefun-github-core-clone-01/rank.svg)](https://make.fun/bounty/github-core-clone-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=github-core-clone-01)
[![reward](https://make.fun/badge/github-core-clone-01/hafizanpurnama-dev/makefun-github-core-clone-01/reward.svg)](https://make.fun/bounty/github-core-clone-01?utm_source=github&utm_medium=readme&utm_campaign=github-core-clone-01)

🏆 Entry for [make.fun bounty: Build a GitHub-compatible git forge](https://make.fun/bounty/github-core-clone-01)

# Git Forge — GitHub-Compatible Git Forge in Python

A self-contained git forge written in pure Python (stdlib only). Clone GitHub repos, serve them over the git smart HTTP protocol, and browse files/commits in a dark-themed web UI.

## Features

- **Git Smart HTTP Protocol** — full clone/fetch/push support via `git upload-pack` and `git receive-pack`
- **Clone GitHub Repos** — paste any GitHub URL to clone it as a bare repo
- **Web UI** — GitHub-dark themed interface for browsing files and commits
- **File Browser** — navigate directory trees with proper file/directory icons
- **Commit History** — view commit logs with author, date, and message
- **README Rendering** — basic markdown rendering for repo READMEs
- **Line Numbers** — code files show with line numbers
- **Delete Repos** — remove cloned repos from the web UI
- **Zero Dependencies** — uses only Python stdlib and the system `git` CLI

## Quick Start

```bash
python3 main.py
```

Then open http://localhost:8000

## Usage

### Clone a repo
1. Open http://localhost:8000
2. Paste a GitHub URL (e.g. `https://github.com/torvalds/linux.git`)
3. Click **Clone**

### Browse a repo
- Click on a repo name → **Code** tab for files, **Commits** tab for history
- Click directories to navigate, click files to view with line numbers

### Git clone from the forge
```bash
git clone http://localhost:8000/git/<repo-name>
```

### Delete a repo
Click the **🗑 Delete** button next to any repo on the homepage.

## Architecture

```
main.py          — HTTP server, routing, request handling
git_http.py      — Git smart HTTP protocol (upload-pack / receive-pack)
repo_manager.py  — Repo lifecycle: clone, list, delete, git operations
web_ui.py        — HTML page rendering, dark theme, markdown
```

## Environment

- `PORT` — server port (default: 8000)
- `HOST` — bind address (default: 0.0.0.0)