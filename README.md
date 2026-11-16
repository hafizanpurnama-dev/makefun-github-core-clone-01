# git-forge

[![make.fun · github-core-clone-01](https://make.fun/badge/github-core-clone-01.svg)](https://make.fun/bounty/github-core-clone-01)
[![rank](https://make.fun/badge/github-core-clone-01/hafizanpurnama-dev/makefun-github-core-clone-01/rank.svg)](https://make.fun/bounty/github-core-clone-01)
[![reward](https://make.fun/badge/github-core-clone-01/hafizanpurnama-dev/makefun-github-core-clone-01/reward.svg)](https://make.fun/bounty/github-core-clone-01)

A minimal, zero-dependency git forge implementing the [git smart HTTP protocol](https://git-scm.com/docs/http-protocol).  
Built in Python 3.13+ using only the standard library.

## Quick Start

```bash
python3 main.py --host 0.0.0.0 --port 8080 --repo-root ./repos
```

The server auto-creates bare repositories on first push.  Clone an existing one:

```bash
git clone http://localhost:8080/my-project.git
```

## How It Works

| Operation | HTTP | Endpoint |
|-----------|------|----------|
| Discovery (clone/pull) | `GET` | `/repo.git/info/refs?service=git-upload-pack` |
| Discovery (push) | `GET` | `/repo.git/info/refs?service=git-receive-pack` |
| Transfer (clone/pull) | `POST` | `/repo.git/git-upload-pack` |
| Transfer (push) | `POST` | `/repo.git/git-receive-pack` |

The server shells out to `git upload-pack` / `git receive-pack` with the
`--stateless-rpc` flag, producing the exact pkt-line protocol that every
Git client already understands.  No CGI wrapper needed.

## Features

- **Full git workflow** — clone, pull, push, branches, tags
- **Auto-creates repos** — push to any path and the bare repo is created on first contact
- **Stdlib only** — zero dependencies beyond Python 3.13+ and a local `git` binary
- **Directory traversal safe** — rejects `..` and symlink escape attempts
- **Dumb HTTP fallback** — serves loose objects for older clients

## Requirements

- Python 3.13+ (stdlib-only; works on 3.14 as well)
- Git 2.x (`git` on `$PATH`)

## License

MIT — see [LICENSE](LICENSE)