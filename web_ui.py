"""
web_ui.py — HTML rendering for the git forge web interface.

Pure Python 3 stdlib — no template engine.  Renders:
  - Repo index (list all repos, clone form)
  - Repo home  (overview with tree / commits links)
  - File tree  (browse directories; uses `git ls-tree`)
  - File blob  (view file content; uses `git show`)
  - Commit log (uses `git log`)

Every public render_* method returns a full HTML string.
"""

import os
import subprocess
import html
from urllib.parse import quote, unquote


# ── shared CSS ──────────────────────────────────────────────────

_BASE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #0d1117; color: #c9d1d9; max-width: 960px;
  margin: 0 auto; padding: 24px 16px;
}
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2, h3 { color: #f0f6fc; margin: 16px 0 8px; }
pre, code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  background: #161b22; border-radius: 6px; padding: 2px 6px;
  font-size: 13px;
}
pre { padding: 16px; overflow-x: auto; line-height: 1.5; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #21262d; }
th { color: #8b949e; font-weight: 600; }
input, button {
  background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
  border-radius: 6px; padding: 8px 12px; font-size: 14px;
}
button { cursor: pointer; background: #238636; border-color: #2ea043; }
button:hover { background: #2ea043; }
input { width: 100%; max-width: 500px; }
.nav { margin-bottom: 20px; padding-bottom: 8px; border-bottom: 1px solid #21262d; }
.nav a { margin-right: 16px; }
.breadcrumb { color: #8b949e; font-size: 14px; margin: 8px 0; }
.breadcrumb a { color: #8b949e; }
.flash { padding: 12px; border-radius: 6px; margin: 12px 0; }
.flash-success { background: #0d3325; border: 1px solid #1a7f4b; }
.flash-error   { background: #3d1215; border: 1px solid #8b3d40; }
.empty { color: #8b949e; font-style: italic; margin: 16px 0; }
.commit-hash { font-family: monospace; color: #7ee787; }
.file-icon { margin-right: 6px; }
.mode { color: #8b949e; font-size: 12px; }
"""


def _html_page(title: str, body: str) -> str:
    """Wrap body content in a full HTML document with CSS."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — git-forge</title>
<style>{_BASE_CSS}</style>
</head>
<body>
<div class="nav">
  <a href="/"><strong>git-forge</strong></a>
  <a href="/">Repositories</a>
</div>
{body}
</body>
</html>"""


def _run_git(repo_path: str, args: list[str], timeout: int = 15) -> str:
    """Run a git command in the repo and return its stdout, or '' on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _format_size(size: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024:
            return f"{size} {unit}"
        size //= 1024
    return f"{size} TB"


def _breadcrumb(repo: str, path: str = "") -> str:
    """Render a breadcrumb trail for a repo path."""
    parts = [html.escape(repo)]
    if path:
        segments = path.strip("/").split("/")
        for i, seg in enumerate(segments):
            link = "/".join([""] + [repo, "tree"] + list(segments[: i + 1]))
            parts.append(f'<a href="{html.escape(link)}">{html.escape(seg)}</a>')
    return '<span class="breadcrumb">' + " / ".join(parts) + "</span>"


# ═══════════════════════════════════════════════════════════════════
# WebUI
# ═══════════════════════════════════════════════════════════════════

class WebUI:
    """Render HTML pages for the forge web interface."""

    def __init__(self, repos_dir: str, port: int = 8000):
        self.repos_dir = repos_dir
        self.port = port

    # ── index ───────────────────────────────────────────────────

    def render_index(self, repos: list[str], flash_message: str = "",
                     flash_kind: str = "") -> str:
        """List all repositories with a clone form. Optionally show a flash."""
        flash_html = ""
        if flash_message:
            css_class = "flash-success" if flash_kind == "success" else "flash-error"
            flash_html = (
                f'<div class="flash {css_class}">'
                f'{html.escape(flash_message)}'
                f'</div>'
            )

        if repos:
            rows = "".join(
                f'<tr><td><a href="/{html.escape(r)}/">{html.escape(r)}</a></td></tr>'
                for r in repos
            )
            repo_table = f"<table><thead><tr><th>Repository</th></tr></thead><tbody>{rows}</tbody></table>"
        else:
            repo_table = '<p class="empty">No repositories yet. Clone one below.</p>'

        body = f"""
<h1>Repositories</h1>
{flash_html}
{repo_table}
<h2>Clone a Repository</h2>
<form method="POST" action="/-/clone">
  <input type="text" name="url" placeholder="https://github.com/user/repo.git" required>
  <button type="submit">Clone</button>
</form>
"""
        return _html_page("Repositories", body)

    # ── repo home ───────────────────────────────────────────────

    def render_repo_home(self, repo: str) -> str:
        """Landing page for a single repository."""
        repo_path = self._resolve(repo)
        if not repo_path:
            return _html_page("Not Found", "<h1>Repository not found</h1>")

        desc = _run_git(repo_path, ["log", "-1", "--format=%s", "HEAD"]).strip()
        if not desc:
            desc = "(empty repository)"

        # Clone URL using the server's port
        clone_cmd = f"git clone http://localhost:{self.port}/git/{repo}"

        body = f"""
<h1>{html.escape(repo)}</h1>
<p class="empty">{html.escape(desc)}</p>

<h2>Clone</h2>
<pre>{html.escape(clone_cmd)}</pre>

<p style="margin-top:16px">
  <a href="/{html.escape(repo)}/tree/">📁 Browse files</a>
  &nbsp;|&nbsp;
  <a href="/{html.escape(repo)}/commits">📋 Commits</a>
</p>

<div style="margin-top:24px; display:flex; gap:12px">
  <form method="POST" action="/-/fetch/{html.escape(repo)}">
    <button type="submit">🔄 Fetch updates</button>
  </form>
  <form method="POST" action="/-/delete/{html.escape(repo)}"
        onsubmit="return confirm('Delete {html.escape(repo)}? This is permanent.')">
    <button type="submit" style="background:#da3633;border-color:#f85149">Delete Repository</button>
  </form>
</div>
"""
        return _html_page(repo, body)

    # ── tree ────────────────────────────────────────────────────

    def render_tree(self, repo: str, path: str = "") -> str:
        """File tree browser."""
        repo_path = self._resolve(repo)
        if not repo_path:
            return _html_page("Not Found", "<h1>Repository not found</h1>")

        # git ls-tree expects no leading slash, and a trailing slash
        # when listing a subdirectory's contents.
        ls_path = path.strip("/")
        if ls_path:
            ls_path += "/"

        output = _run_git(repo_path, ["ls-tree", "-l", "HEAD", ls_path])
        if not output and ls_path:
            # Empty directory or error — show breadcrumb + empty state
            body = (
                f"<h1>{html.escape(repo)}</h1>"
                f"{_breadcrumb(repo, path)}"
                f'<p class="empty">Nothing here — empty directory or invalid path.</p>'
            )
            return _html_page(f"{repo} — tree", body)
        if not output:
            # No HEAD yet (empty repo)
            body = (
                f"<h1>{html.escape(repo)}</h1>"
                f'<p class="empty">No commits yet — the repository is empty.</p>'
            )
            return _html_page(f"{repo} — tree", body)

        # Build a parent-directory link when inside a subdirectory
        parent_link = ""
        if path and path.strip("/"):
            parent_parts = path.strip("/").split("/")
            if len(parent_parts) > 1:
                parent_path = "/".join(parent_parts[:-1])
                parent_url = f"/{quote(repo)}/tree/{quote(parent_path)}"
            else:
                parent_url = f"/{quote(repo)}/tree/"
            parent_link = (
                f'<tr><td colspan="3">'
                f'<a href="{html.escape(parent_url)}">📂 .. (parent directory)</a>'
                f'</td></tr>'
            )

        rows = parent_link
        for line in output.strip().split("\n"):
            if not line:
                continue
            # Format: <mode> <type> <hash> <size>\t<name>
            # (size is - for trees)
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            mode_str, obj_type, obj_hash, size_str, name = parts
            name = name.strip()

            if obj_type == "tree":
                icon = "📁"
                subpath = f"{path.rstrip('/')}/{name}" if path else name
                link = f"/{quote(repo)}/tree/{quote(subpath)}"
                size_display = ""
            else:
                icon = "📄"
                blob_path = f"{path.rstrip('/')}/{name}" if path else name
                link = f"/{quote(repo)}/blob/{quote(blob_path)}"
                size_display = _format_size(int(size_str)) if size_str != "-" else ""

            row = (
                f'<tr>'
                f'<td><span class="file-icon">{icon}</span>'
                f'<a href="{html.escape(link)}">{html.escape(name)}</a></td>'
                f'<td><span class="mode">{html.escape(mode_str)}</span></td>'
                f'<td>{size_display}</td>'
                f'</tr>'
            )
            rows += row

        body = f"""
<h1>{html.escape(repo)}</h1>
{_breadcrumb(repo, path)}
<table>
  <thead><tr><th>Name</th><th>Mode</th><th>Size</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
"""
        return _html_page(f"{repo} — tree", body)

    # ── blob ────────────────────────────────────────────────────

    def render_blob(self, repo: str, path: str) -> str:
        """Show file contents."""
        repo_path = self._resolve(repo)
        if not repo_path:
            return _html_page("Not Found", "<h1>Repository not found</h1>")

        content = _run_git(repo_path, ["show", f"HEAD:{path}"])
        if not content:
            return _html_page("Not Found", f"<h1>File not found</h1>{_breadcrumb(repo, path)}")

        body = f"""
<h1>{html.escape(repo)}</h1>
{_breadcrumb(repo, path)}
<pre><code>{html.escape(content)}</code></pre>
"""
        return _html_page(f"{repo} — {path.split('/')[-1]}", body)

    # ── commits ─────────────────────────────────────────────────

    def render_commits(self, repo: str) -> str:
        """Commit log for a repository."""
        repo_path = self._resolve(repo)
        if not repo_path:
            return _html_page("Not Found", "<h1>Repository not found</h1>")

        output = _run_git(
            repo_path,
            ["log", "--format=%H%x00%an%x00%ai%x00%s", "-n", "50"],
            timeout=15,
        )
        if not output:
            body = f"<h1>{html.escape(repo)} — Commits</h1><p class='empty'>No commits yet.</p>"
            return _html_page(f"{repo} — commits", body)

        rows = ""
        for line in output.strip().split("\n"):
            if not line:
                continue
            fields = line.split("\x00")
            if len(fields) < 4:
                continue
            obj_hash, author, date, subject = fields[0], fields[1], fields[2], fields[3]
            short_hash = obj_hash[:8]
            # Trim timezone offset for display
            display_date = " ".join(date.split(" ")[:2])

            rows += (
                f'<tr>'
                f'<td><span class="commit-hash">{html.escape(short_hash)}</span></td>'
                f'<td>{html.escape(subject)}</td>'
                f'<td>{html.escape(author)}</td>'
                f'<td>{html.escape(display_date)}</td>'
                f'</tr>'
            )

        body = f"""
<h1>{html.escape(repo)} — Commits</h1>
<table>
  <thead><tr><th>Hash</th><th>Message</th><th>Author</th><th>Date</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
"""
        return _html_page(f"{repo} — commits", body)

    # ── helpers ─────────────────────────────────────────────────

    def _resolve(self, name: str) -> str | None:
        """Resolve a repo display name to its filesystem path."""
        path = os.path.join(self.repos_dir, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "HEAD")):
            return path
        path_git = path + ".git"
        if os.path.isdir(path_git) and os.path.isfile(os.path.join(path_git, "HEAD")):
            return path_git
        return None

    @staticmethod
    def _page(title: str, body: str) -> str:
        """Convenience: render a full page without needing an instance."""
        return _html_page(title, body)