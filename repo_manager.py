"""
Repo manager: clone GitHub repos, list local repos, get repo info.
Uses subprocess to call git CLI.
"""
import os
import subprocess
import shlex

REPOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repos")


def ensure_repos_dir():
    os.makedirs(REPOS_DIR, exist_ok=True)


def clone_repo(github_url: str) -> dict:
    """Clone a GitHub repo as bare into repos/.
    Returns dict with status, name, path."""
    ensure_repos_dir()
    name = github_url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]

    target = os.path.join(REPOS_DIR, name)

    if os.path.exists(target):
        return {"status": "exists", "name": name, "path": target}

    cmd = ["git", "clone", "--bare", github_url, target]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return {"status": "cloned", "name": name, "path": target}
        else:
            return {"status": "error", "name": name, "error": result.stderr}
    except subprocess.TimeoutExpired:
        return {"status": "error", "name": name, "error": "Clone timed out"}
    except Exception as e:
        return {"status": "error", "name": name, "error": str(e)}


def list_repos() -> list:
    """List all cloned repos."""
    ensure_repos_dir()
    repos = []
    if not os.path.exists(REPOS_DIR):
        return repos
    for entry in sorted(os.listdir(REPOS_DIR)):
        full = os.path.join(REPOS_DIR, entry)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, "HEAD")):
            repos.append({"name": entry, "path": full})
    return repos


def get_repo(name: str) -> dict | None:
    """Get a repo by name."""
    path = os.path.join(REPOS_DIR, name)
    if os.path.isdir(path) and os.path.exists(os.path.join(path, "HEAD")):
        return {"name": name, "path": path}
    return None


def git_command(repo_path: str, args: list, timeout: int = 30) -> tuple:
    """Run a git command in a repo and return (rc, stdout, stderr)."""
    cmd = ["git"] + args
    env = os.environ.copy()
    env["GIT_DIR"] = repo_path
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)


def get_branches(repo_path: str) -> list:
    """List branches in a bare repo."""
    rc, stdout, stderr = git_command(repo_path, ["branch"])
    if rc != 0:
        return []
    branches = [b.strip().lstrip("* ") for b in stdout.strip().split("\n") if b.strip()]
    return branches


def get_files(repo_path: str, branch: str = "HEAD", path: str = "") -> list:
    """List files in a tree at given path.
    Returns list of dicts with {name, type, mode}."""
    treeish = f"{branch}:{path}" if path else branch
    rc, stdout, stderr = git_command(repo_path, ["ls-tree", treeish])
    if rc != 0:
        return []
    entries = []
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        # Format: <mode> <type> <hash>\t<name>
        parts = line.split(None, 3)
        if len(parts) >= 4:
            entries.append({
                "mode": parts[0],
                "type": parts[1],  # "tree" or "blob"
                "hash": parts[2],
                "name": parts[3].split("\t", 1)[-1] if "\t" in parts[3] else parts[3],
            })
    return entries


def get_file_names(repo_path: str, branch: str = "HEAD", path: str = "") -> list:
    """List just file/dir names (for backward compat)."""
    treeish = f"{branch}:{path}" if path else branch
    rc, stdout, stderr = git_command(repo_path, ["ls-tree", "--name-only", treeish])
    if rc != 0:
        return []
    return [f for f in stdout.strip().split("\n") if f]


def get_file_content(repo_path: str, branch: str, filepath: str) -> str | None:
    """Get file content at a given path in a branch."""
    treeish = f"{branch}:{filepath}"
    rc, stdout, stderr = git_command(repo_path, ["show", treeish])
    if rc != 0:
        return None
    return stdout


def get_commits(repo_path: str, branch: str = "HEAD", limit: int = 50) -> list:
    """Get commit log."""
    rc, stdout, stderr = git_command(
        repo_path,
        ["log", f"--max-count={limit}", "--format=%H|%an|%ae|%ai|%s", branch],
        timeout=10,
    )
    if rc != 0 or not stdout.strip():
        return []
    commits = []
    for line in stdout.strip().split("\n"):
        parts = line.split("|", 4)
        if len(parts) == 5:
            commits.append({
                "hash": parts[0],
                "author": parts[1],
                "email": parts[2],
                "date": parts[3],
                "message": parts[4],
                "short_hash": parts[0][:7],
            })
    return commits


def get_readme(repo_path: str, branch: str = "HEAD") -> str | None:
    """Find and return README content."""
    files = get_file_names(repo_path, branch)
    for f in files:
        if f.lower().startswith("readme"):
            return get_file_content(repo_path, branch, f)
    return None


def delete_repo(name: str) -> bool:
    """Delete a cloned repo. Returns True if deleted."""
    import shutil
    path = os.path.join(REPOS_DIR, name)
    if os.path.isdir(path) and os.path.exists(os.path.join(path, "HEAD")):
        shutil.rmtree(path)
        return True
    return False


def get_repo_stat(repo_path: str) -> dict:
    """Get repo statistics: branch count, commit count, last commit."""
    branches = get_branches(repo_path)
    default_branch = get_default_branch(repo_path)
    commits = get_commits(repo_path, default_branch, limit=1)
    return {
        "branch_count": len(branches),
        "default_branch": default_branch,
        "last_commit": commits[0] if commits else None,
    }


def get_default_branch(repo_path: str) -> str:
    """Get the default branch name."""
    rc, stdout, stderr = git_command(repo_path, ["symbolic-ref", "HEAD"])
    if rc == 0:
        return stdout.strip().replace("refs/heads/", "")
    return "main"