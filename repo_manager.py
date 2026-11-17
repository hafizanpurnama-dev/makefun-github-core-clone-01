"""
repo_manager.py — Manage bare git repositories on the filesystem.

Operations:
  - clone(url)       — clone a remote repository as a bare mirror
  - fetch(name)      — fetch latest refs into an existing bare mirror
  - delete(name)     — remove a repo directory
  - list_repos()     — enumerate all bare repos on disk
  - repo_exists(name)— check if a repo directory is present
  - repo_path(name)  — return the full filesystem path for a repo
  - repo_size(name)  — estimate on-disk size of a repo in bytes

All operations are synchronous; cloning runs git in a subprocess.
"""

import os
import shutil
import subprocess
import sys
import re
from urllib.parse import urlparse


# ── helpers ─────────────────────────────────────────────────────

def _slug_from_url(url: str) -> str:
    """Extract 'owner/repo' from a URL and produce a directory name.

    Handles:
      https://github.com/user/repo.git
      https://github.com/user/repo
      git@github.com:user/repo.git
      https://gitlab.com/ns/project/subgroup/repo.git  → ns_project_subgroup_repo.git
    """
    url = url.rstrip("/")

    # SSH-style: git@github.com:owner/repo.git
    m = re.match(r"^git@([^:]+):(.+)$", url)
    if m:
        path_part = m.group(2)
    else:
        parsed = urlparse(url)
        path_part = parsed.path.lstrip("/")

    # Drop trailing .git
    path_part = path_part.rstrip(".git") if path_part.endswith(".git") else path_part

    # Replace slashes with underscores
    slug = path_part.replace("/", "_")
    if not slug:
        slug = "unknown"
    return f"{slug}.git"


# ── RepoManager ─────────────────────────────────────────────────

class RepoManager:
    """Filesystem-backed manager for bare git repositories."""

    def __init__(self, repos_dir: str):
        self.repos_dir = repos_dir
        os.makedirs(repos_dir, exist_ok=True)

    # ── queries ─────────────────────────────────────────────────

    def list_repos(self) -> list[str]:
        """Return a sorted list of bare-repo directory names (without .git)."""
        try:
            entries = os.listdir(self.repos_dir)
            repos = []
            for name in entries:
                full = os.path.join(self.repos_dir, name)
                if not os.path.isdir(full):
                    continue
                # A bare repo has a HEAD file at minimum
                if os.path.isfile(os.path.join(full, "HEAD")):
                    clean = name[:-4] if name.endswith(".git") else name
                    repos.append(clean)
            repos.sort()
            return repos
        except FileNotFoundError:
            return []

    def repo_path(self, name: str) -> str:
        """Return the on-disk path for a repo by its display name."""
        path = os.path.join(self.repos_dir, name)
        if os.path.isdir(path):
            return path
        path_git = path + ".git"
        if os.path.isdir(path_git):
            return path_git
        return path  # caller can check existence

    def repo_exists(self, name: str) -> bool:
        """Check whether a repo (bare directory) exists."""
        path = self.repo_path(name)
        return os.path.isdir(path) and os.path.isfile(os.path.join(path, "HEAD"))

    # ── mutations ───────────────────────────────────────────────

    def clone(self, url: str) -> tuple[bool, str]:
        """Clone a remote URL as a bare mirror.

        Returns (success, message) where message is the repo name on success
        or an error string on failure.
        """
        dest_name = _slug_from_url(url)
        dest_path = os.path.join(self.repos_dir, dest_name)

        if os.path.exists(dest_path):
            return False, f"Repository '{dest_name}' already exists"

        try:
            subprocess.run(
                ["git", "clone", "--bare", "--mirror", url, dest_path],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
                env=self._git_env(),
            )
        except subprocess.CalledProcessError as exc:
            # Clean up partial clone
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path, ignore_errors=True)
            err = exc.stderr.strip() if exc.stderr else str(exc)
            return False, f"Clone failed: {err}"
        except FileNotFoundError:
            return False, "git executable not found — is git installed?"
        except subprocess.TimeoutExpired:
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path, ignore_errors=True)
            return False, "Clone timed out (> 5 minutes)"

        display = dest_name[:-4] if dest_name.endswith(".git") else dest_name
        return True, display

    def delete(self, name: str) -> tuple[bool, str]:
        """Remove a repository directory.

        Returns (success, message).
        """
        path = self.repo_path(name)
        if not os.path.isdir(path):
            return False, f"Repository '{name}' does not exist"
        try:
            shutil.rmtree(path)
            return True, f"Deleted '{name}'"
        except OSError as exc:
            return False, f"Could not delete '{name}': {exc}"

    def fetch(self, name: str) -> tuple[bool, str]:
        """Fetch latest refs into an existing bare mirror.

        Returns (success, message).
        """
        path = self.repo_path(name)
        if not self.repo_exists(name):
            return False, f"Repository '{name}' not found"
        try:
            result = subprocess.run(
                ["git", "fetch", "--all", "--prune"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=120,
                env=self._git_env(),
            )
            if result.returncode != 0:
                err = result.stderr.strip() or "unknown error"
                return False, f"Fetch failed: {err}"
            return True, f"Fetched updates for '{name}'"
        except FileNotFoundError:
            return False, "git executable not found"
        except subprocess.TimeoutExpired:
            return False, "Fetch timed out (> 2 minutes)"

    def repo_size(self, name: str) -> int:
        """Return the total on-disk size of a repo in bytes, or -1 if unknown."""
        path = self.repo_path(name)
        if not os.path.isdir(path):
            return -1
        total = 0
        try:
            for dirpath, _, filenames in os.walk(path):
                for fn in filenames:
                    fp = os.path.join(dirpath, fn)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
        except OSError:
            return -1
        return total

    # ── helpers ─────────────────────────────────────────────────

    @staticmethod
    def _git_env() -> dict:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        return env