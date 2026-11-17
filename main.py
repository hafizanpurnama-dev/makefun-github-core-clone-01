#!/usr/bin/env python3
"""
git-forge — a lightweight git forge HTTP server.

Routes:
  GET  /                     → repo listing (web_ui)
  GET  /<repo>               → repo overview (web_ui)
  GET  /<repo>/tree/<path>   → file browser (web_ui)
  GET  /<repo>/commits       → commit log (web_ui)
  GET  /<repo>/blob/<path>   → file content (web_ui)
  *    /git/<repo>/*         → git smart HTTP protocol (git_http)

Environment:
  PORT      — listen port (default 8000)
  REPOS_DIR — directory holding bare repos (default ./repos)
"""

import os
import sys
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote, parse_qs

from repo_manager import RepoManager
from web_ui import WebUI
from git_http import GitHTTPHandler


PORT = int(os.environ.get("PORT", 8000))
REPOS_DIR = os.environ.get("REPOS_DIR", os.path.join(os.getcwd(), "repos"))

# ── Route patterns ──────────────────────────────────────────────
GIT_ROUTE    = re.compile(r"^/git/([^/]+)/(.*)$")
REPO_TREE    = re.compile(r"^/([^/]+)/tree/(.*)$")
REPO_BLOB    = re.compile(r"^/([^/]+)/blob/(.*)$")
REPO_COMMITS = re.compile(r"^/([^/]+)/commits$")
REPO_ROOT    = re.compile(r"^/([^/]+)/?$")
CLONE_ROUTE  = re.compile(r"^/-/clone$")
DELETE_ROUTE = re.compile(r"^/-/delete/([^/]+)$")
FETCH_ROUTE  = re.compile(r"^/-/fetch/([^/]+)$")


class ForgeHandler(BaseHTTPRequestHandler):
    """Dispatch incoming requests to the correct subsystem."""

    def log_message(self, fmt, *args):
        """Quiet logging — only write to stderr."""
        sys.stderr.write("[forge] %s\n" % (fmt % args))

    def _send_html(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_plain(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    # ── routing ─────────────────────────────────────────────────

    def _dispatch(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        # POST /-/clone — clone a new repo from URL
        if self.command == "POST" and CLONE_ROUTE.match(path):
            return self._handle_clone()

        # POST /-/delete/<repo>
        m = DELETE_ROUTE.match(path)
        if m and self.command == "POST":
            return self._handle_delete(m.group(1))

        # POST /-/fetch/<repo>
        m = FETCH_ROUTE.match(path)
        if m and self.command == "POST":
            return self._handle_fetch(m.group(1))

        # /git/<repo>/... → smart HTTP
        m = GIT_ROUTE.match(path)
        if m:
            repo, subpath = m.group(1), m.group(2)
            handler = GitHTTPHandler(REPOS_DIR)
            return handler.handle(self, repo, subpath, self.command)

        # /<repo>/tree/...
        m = REPO_TREE.match(path)
        if m:
            repo, tree_path = m.group(1), m.group(2)
            ui = WebUI(REPOS_DIR, port=PORT)
            self._send_html(200, ui.render_tree(repo, tree_path))
            return

        # /<repo>/blob/...
        m = REPO_BLOB.match(path)
        if m:
            repo, blob_path = m.group(1), m.group(2)
            ui = WebUI(REPOS_DIR, port=PORT)
            self._send_html(200, ui.render_blob(repo, blob_path))
            return

        # /<repo>/commits
        m = REPO_COMMITS.match(path)
        if m:
            repo = m.group(1)
            ui = WebUI(REPOS_DIR, port=PORT)
            self._send_html(200, ui.render_commits(repo))
            return

        # /<repo> or /<repo>/
        m = REPO_ROOT.match(path)
        if m:
            repo = m.group(1)
            ui = WebUI(REPOS_DIR, port=PORT)
            self._send_html(200, ui.render_repo_home(repo))
            return

        # / → repo listing
        if path == "/" or path == "":
            mgr = RepoManager(REPOS_DIR)
            repos = mgr.list_repos()
            qs = parse_qs(parsed.query)
            flash = qs.get("success", qs.get("error", [None]))[0]
            kind = "success" if "success" in (parsed.query or "") else "error" if "error" in (parsed.query or "") else ""
            ui = WebUI(REPOS_DIR, port=PORT)
            self._send_html(200, ui.render_index(repos, flash_message=flash or "", flash_kind=kind))
            return

        # 404
        self._send_html(404, WebUI._page("Not Found", "<h1>404 — Nothing here</h1>"))

    # ── POST handlers ───────────────────────────────────────────

    def _handle_clone(self):
        """Handle POST /-/clone — extract url from form body, trigger clone."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8", errors="replace")

        # Parse www-form-urlencoded body
        form = parse_qs(body)
        url = form.get("url", [None])[0]

        if not url:
            self._redirect("/?error=" + quote("Missing URL"))
            return

        mgr = RepoManager(REPOS_DIR)
        ok, msg = mgr.clone(url)
        if ok:
            self._redirect("/?success=" + quote(f"Cloned {msg}"))
        else:
            self._redirect("/?error=" + quote(msg))

    def _handle_delete(self, repo: str):
        """Handle POST /-/delete/<repo> — remove a repository."""
        mgr = RepoManager(REPOS_DIR)
        ok, msg = mgr.delete(repo)
        if ok:
            self._redirect("/?success=" + quote(msg))
        else:
            self._redirect("/?error=" + quote(msg))

    def _handle_fetch(self, repo: str):
        """Handle POST /-/fetch/<repo> — fetch latest from remotes."""
        mgr = RepoManager(REPOS_DIR)
        ok, msg = mgr.fetch(repo)
        if ok:
            self._redirect(f"/{quote(repo)}/?success=" + quote(msg))
        else:
            self._redirect(f"/{quote(repo)}/?error=" + quote(msg))

    def _redirect(self, location: str):
        """Issue a 303 redirect."""
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()


def main():
    os.makedirs(REPOS_DIR, exist_ok=True)
    server = HTTPServer(("0.0.0.0", PORT), ForgeHandler)
    print(f"[forge] listening on 0.0.0.0:{PORT} — repos in {REPOS_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[forge] shutting down")
        server.server_close()


if __name__ == "__main__":
    main()