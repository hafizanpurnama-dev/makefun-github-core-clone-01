"""
Web UI: browse repos, files, and commits via HTML pages.
Simple template rendering without external dependencies.
"""
import os
import html
import urllib.parse

import repo_manager as rm

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

# File extension -> emoji icon mapping
FILE_ICONS = {
    ".py": "🐍", ".js": "🟨", ".ts": "🔷", ".tsx": "⚛️", ".jsx": "⚛️",
    ".html": "🌐", ".htm": "🌐", ".css": "🎨", ".scss": "🎨", ".less": "🎨",
    ".json": "📋", ".xml": "📋", ".yaml": "📋", ".yml": "📋", ".toml": "📋",
    ".md": "📝", ".markdown": "📝", ".rst": "📝", ".txt": "📄",
    ".sh": "🐚", ".bash": "🐚", ".zsh": "🐚",
    ".rs": "🦀", ".go": "🐹", ".java": "☕", ".kt": "🅱️", ".swift": "🍎",
    ".c": "⚙️", ".cpp": "⚙️", ".h": "⚙️", ".hpp": "⚙️",
    ".rb": "💎", ".php": "🐘", ".pl": "🐪",
    ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".gif": "🖼️",
    ".svg": "🖼️", ".ico": "🖼️", ".webp": "🖼️",
    ".mp4": "🎬", ".mov": "🎬", ".avi": "🎬",
    ".mp3": "🎵", ".wav": "🎵", ".ogg": "🎵",
    ".pdf": "📕", ".doc": "📕", ".docx": "📕",
    ".zip": "📦", ".tar": "📦", ".gz": "📦", ".bz2": "📦",
    ".lock": "🔒", ".gitignore": "🙈", ".dockerignore": "🙈",
    "Dockerfile": "🐳", "Makefile": "🔧", "LICENSE": "⚖️",
}


def file_icon(name: str) -> str:
    """Get an emoji icon for a file based on its name/extension."""
    basename = os.path.basename(name)
    if basename in FILE_ICONS:
        return FILE_ICONS[basename]
    _, ext = os.path.splitext(basename)
    return FILE_ICONS.get(ext.lower(), "📄")


BASE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Git Forge</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0d1117; color: #c9d1d9; }}
a {{ color: #58a6ff; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.header {{ background: #161b22; border-bottom: 1px solid #30363d; padding: 16px 24px; display: flex; align-items: center; gap: 16px; }}
.header h1 {{ font-size: 20px; }}
.header h1 a {{ color: #f0f6fc; }}
.header .header-links {{ font-size: 14px; }}
.header .header-links a {{ color: #8b949e; margin-left: 16px; }}
.nav {{ background: #161b22; border-bottom: 1px solid #30363d; padding: 8px 24px; font-size: 14px; }}
.nav a {{ margin-right: 16px; color: #8b949e; }}
.nav a.active {{ color: #f0f6fc; font-weight: 600; }}
.container {{ max-width: 960px; margin: 24px auto; padding: 0 24px; }}
.repo-list {{ list-style: none; }}
.repo-item {{ border: 1px solid #30363d; border-radius: 6px; padding: 16px; margin-bottom: 12px; background: #161b22; }}
.repo-item h3 {{ font-size: 18px; margin-bottom: 4px; }}
.repo-item .desc {{ color: #8b949e; margin-top: 4px; font-size: 13px; }}
.repo-item .meta {{ font-size: 12px; color: #484f58; margin-top: 8px; }}
.breadcrumb {{ font-size: 14px; padding: 12px 0; color: #8b949e; }}
.breadcrumb a {{ color: #58a6ff; }}
.file-list {{ list-style: none; border: 1px solid #30363d; border-radius: 6px; }}
.file-row {{ display: flex; align-items: center; padding: 8px 16px; border-bottom: 1px solid #21262d; font-size: 14px; }}
.file-row:last-child {{ border-bottom: none; }}
.file-row:hover {{ background: #1c2128; }}
.file-icon {{ width: 24px; margin-right: 8px; text-align: center; flex-shrink: 0; }}
.file-name {{ flex: 1; }}
.file-name.dir {{ font-weight: 600; }}
.file-mode {{ font-size: 12px; color: #484f58; margin-left: 8px; font-family: monospace; }}
.commit-list {{ list-style: none; border: 1px solid #30363d; border-radius: 6px; }}
.commit-item {{ padding: 12px 16px; border-bottom: 1px solid #21262d; font-size: 14px; }}
.commit-item:last-child {{ border-bottom: none; }}
.commit-hash {{ font-family: monospace; font-size: 12px; color: #8b949e; background: #21262d; padding: 2px 6px; border-radius: 4px; }}
.commit-msg {{ font-weight: 600; }}
.commit-meta {{ font-size: 12px; color: #8b949e; margin-top: 4px; }}
.code-block {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 16px; overflow-x: auto; }}
.code-block pre {{ font-family: "SF Mono", "Fira Code", monospace; font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }}
.code-block .line {{ display: table-row; }}
.code-block .line-num {{ display: table-cell; text-align: right; padding-right: 12px; color: #484f58; user-select: none; min-width: 40px; }}
.code-block .line-code {{ display: table-cell; }}
.btn {{ display: inline-block; padding: 8px 16px; border-radius: 6px; font-size: 14px; font-weight: 500; border: 1px solid #30363d; background: #21262d; color: #c9d1d9; cursor: pointer; text-decoration: none; }}
.btn:hover {{ background: #30363d; text-decoration: none; }}
.btn-primary {{ background: #238636; border-color: #2ea043; color: #fff; }}
.btn-primary:hover {{ background: #2ea043; }}
.btn-danger {{ color: #f85149; border-color: #f85149; }}
.btn-danger:hover {{ background: #da3633; color: #fff; }}
.clone-bar {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 10px 16px; margin-bottom: 16px; font-family: monospace; font-size: 13px; display: flex; align-items: center; gap: 12px; }}
.clone-bar code {{ color: #7ee787; }}
.clone-bar .clone-label {{ color: #8b949e; flex-shrink: 0; }}
.stat-bar {{ display: flex; gap: 24px; margin-bottom: 16px; font-size: 13px; color: #8b949e; }}
.stat-bar span {{ display: flex; align-items: center; gap: 4px; }}
.readme-box {{ border: 1px solid #30363d; border-radius: 6px; padding: 24px; background: #161b22; margin-top: 16px; font-size: 14px; line-height: 1.6; }}
.readme-box h1, .readme-box h2, .readme-box h3 {{ margin-top: 16px; margin-bottom: 8px; color: #f0f6fc; border-bottom: 1px solid #21262d; padding-bottom: 8px; }}
.readme-box code {{ background: #21262d; padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
.readme-box pre {{ background: #0d1117; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 13px; }}
.readme-box a {{ color: #58a6ff; }}
.readme-box ul, .readme-box ol {{ padding-left: 24px; margin: 8px 0; }}
form {{ margin: 24px 0; }}
input[type="text"] {{ padding: 8px 12px; border-radius: 6px; border: 1px solid #30363d; background: #0d1117; color: #c9d1d9; font-size: 14px; width: 400px; max-width: 100%; }}
.empty-state {{ text-align: center; padding: 48px 0; color: #8b949e; }}
.empty-state p {{ margin: 8px 0; font-size: 16px; }}
.error-box {{ background: #490202; border: 1px solid #f85149; border-radius: 6px; padding: 16px; margin: 16px 0; color: #f85149; }}
</style>
</head>
<body>
<div class="header">
  <h1><a href="/">⚡ Git Forge</a></h1>
  <div class="header-links">
    <a href="/">Repositories</a>
  </div>
</div>
{nav}
<div class="container">
{content}
</div>
</body>
</html>"""


def render_page(title: str, content: str, nav: str = "") -> str:
    return BASE_HTML.format(title=html.escape(title), content=content, nav=nav)


def nav_for_repo(repo_name: str, active: str = "") -> str:
    """Navigation bar for inside a repo."""
    tabs = [("files", "Code"), ("commits", "Commits")]
    links = []
    for key, label in tabs:
        cls = ' class="active"' if key == active else ""
        links.append(f'<a href="/{html.escape(repo_name)}/{key}"{cls}>{label}</a>')
    repo_link = f'<a href="/{html.escape(repo_name)}/files">{html.escape(repo_name)}</a>'
    return f'<div class="nav"><strong>{repo_link}</strong> {" ".join(links)}</div>'


def _simple_markdown(text: str) -> str:
    """Very basic markdown-to-HTML for README rendering (headings, code, links)."""
    import re
    lines = text.split("\n")
    out = []
    in_code = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
            if in_code:
                out.append("<pre>")
            else:
                out.append("</pre>")
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        # Headings
        if line.startswith("### "):
            out.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        else:
            # Basic inline formatting
            line = html.escape(line)
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'`([^`]+)`', r'<code>\1</code>', line)
            line = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', line)
            if line.strip():
                out.append(f"<p>{line}</p>")
            else:
                out.append("<br>")

    return "\n".join(out)


def index_page() -> str:
    """Homepage: list repos + clone form."""
    repos = rm.list_repos()
    items = []
    for repo in repos:
        name = repo["name"]
        default_branch = rm.get_default_branch(repo["path"])
        readme = rm.get_readme(repo["path"], default_branch)
        stat = rm.get_repo_stat(repo["path"])
        desc = ""
        if readme:
            first_line = readme.strip().split("\n")[0].lstrip("#").strip()
            desc = first_line[:120]
        last = stat.get("last_commit")
        meta = ""
        if last:
            meta = f'<span>🕐 {last["date"][:10]}</span> <span>🌿 {stat["default_branch"]}</span>'
        items.append(f"""
        <li class="repo-item">
          <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
              <h3><a href="/{html.escape(name)}/files">{html.escape(name)}</a></h3>
              <div class="desc">{html.escape(desc) if desc else '<em>No description</em>'}</div>
              <div class="meta">{meta}</div>
            </div>
            <form method="POST" action="/{html.escape(name)}/delete" onsubmit="return confirm('Delete {html.escape(name)}?')" style="margin:0;">
              <button type="submit" class="btn btn-danger" style="font-size:12px;padding:4px 10px;">🗑 Delete</button>
            </form>
          </div>
        </li>""")

    repos_html = "".join(items) if items else '<div class="empty-state"><p>📂 No repositories yet</p><p>Clone one below to get started</p></div>'

    content = f"""
    <form method="POST" action="/clone" style="display: flex; gap: 8px; align-items: center;">
      <input type="text" name="url" placeholder="https://github.com/user/repo.git" required>
      <button type="submit" class="btn btn-primary">Clone</button>
    </form>
    <ul class="repo-list">{repos_html}</ul>
    """
    return render_page("Repositories", content)


def files_page(repo_name: str, branch: str = "HEAD", subpath: str = "", host: str = "localhost:8000") -> str:
    """Browse files in a repo."""
    repo = rm.get_repo(repo_name)
    if not repo:
        return render_page("Not Found", "<p>Repository not found.</p>")

    if branch == "HEAD":
        branch = rm.get_default_branch(repo["path"])

    entries = rm.get_files(repo["path"], branch, subpath)
    is_file = False
    file_content = None

    if not entries and subpath:
        # Might be a single file
        file_content = rm.get_file_content(repo["path"], branch, subpath)
        if file_content is not None:
            is_file = True

    nav = nav_for_repo(repo_name, "files")

    # Breadcrumbs
    crumbs = [f'<a href="/{html.escape(repo_name)}/files">{html.escape(repo_name)}</a>']
    if subpath:
        parts = subpath.split("/")
        for i, part in enumerate(parts):
            link_path = "/".join(parts[:i + 1])
            crumbs.append(f'<a href="/{html.escape(repo_name)}/files/{html.escape(link_path)}">{html.escape(part)}</a>')
    breadcrumb = '<div class="breadcrumb"> / '.join(crumbs) + "</div>"

    # Clone URL
    clone_url = f"http://{host}/git/{html.escape(repo_name)}"
    clone_bar = f'<div class="clone-bar"><span class="clone-label">🔽 Clone</span> <code>git clone {clone_url}</code></div>'

    # Stat bar
    stat = rm.get_repo_stat(repo["path"])
    stat_html = ""
    if stat["last_commit"]:
        stat_html = f"""
    <div class="stat-bar">
      <span>🌿 <strong>{html.escape(stat['default_branch'])}</strong></span>
      <span>🕐 Last commit: {stat['last_commit']['date'][:10]}</span>
    </div>"""

    if is_file:
        file_content_html = html.escape(file_content or "")
        # Add line numbers
        numbered_lines = []
        for i, line in enumerate(file_content_html.split("\n"), 1):
            numbered_lines.append(
                f'<div class="line"><span class="line-num">{i}</span><span class="line-code">{line}</span></div>'
            )
        numbered_html = "\n".join(numbered_lines)
        body = f"""
        {clone_bar}
        {stat_html}
        {breadcrumb}
        <div class="code-block"><pre>{numbered_html}</pre></div>
        """
    else:
        rows = []
        # Sort: directories first, then files
        dirs = [e for e in entries if e["type"] == "tree"]
        files = [e for e in entries if e["type"] != "tree"]
        for e in dirs + files:
            is_dir = e["type"] == "tree"
            icon = "📁" if is_dir else file_icon(e["name"])
            row_class = "dir" if is_dir else ""
            link_path = f"{subpath}/{e['name']}" if subpath else e["name"]
            rows.append(f"""
            <div class="file-row">
              <span class="file-icon">{icon}</span>
              <span class="file-name {row_class}">
                <a href="/{html.escape(repo_name)}/files/{html.escape(link_path)}">{html.escape(e['name'])}</a>
              </span>
              <span class="file-mode">{'dir' if is_dir else e['mode']}</span>
            </div>""")

        body = f"""
        {clone_bar}
        {stat_html}
        {breadcrumb}
        <div class="file-list">{"".join(rows)}</div>
        """

    # If at root, show README
    if not subpath:
        readme = rm.get_readme(repo["path"], branch)
        if readme:
            readme_html = _simple_markdown(readme)
            body += f'<div class="readme-box">{readme_html}</div>'

    return render_page(f"{repo_name} at {subpath or '/'}", body, nav)


def commits_page(repo_name: str, branch: str = "HEAD") -> str:
    """Browse commits in a repo."""
    repo = rm.get_repo(repo_name)
    if not repo:
        return render_page("Not Found", "<p>Repository not found.</p>")

    if branch == "HEAD":
        branch = rm.get_default_branch(repo["path"])

    commits = rm.get_commits(repo["path"], branch)
    nav = nav_for_repo(repo_name, "commits")

    items = []
    for c in commits:
        items.append(f"""
        <div class="commit-item">
          <div class="commit-msg">{html.escape(c['message'])}</div>
          <div class="commit-meta">
            <span class="commit-hash">{c['short_hash']}</span>
            {html.escape(c['author'])} committed on {c['date'][:10]}
          </div>
        </div>""")

    commits_html = "".join(items) if items else "<p>No commits found.</p>"

    body = f"""
    <h2 style="margin-bottom: 16px;">Commits · {html.escape(branch)}</h2>
    <div class="commit-list">{commits_html}</div>
    """

    return render_page(f"{repo_name} — Commits", body, nav)


def error_page(title: str, message: str) -> str:
    """Render an error page."""
    content = f'<div class="error-box"><h2>{html.escape(title)}</h2><p>{html.escape(message)}</p></div><p><a href="/">← Back to repositories</a></p>'
    return render_page(title, content)