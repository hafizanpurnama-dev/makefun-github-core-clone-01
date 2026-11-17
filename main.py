#!/usr/bin/env python3
"""
Git Forge — a GitHub-compatible git forge in Python stdlib.

Serves:
  - Git smart HTTP protocol at /git/<repo>/*
  - Web UI at / for browsing repos/files/commits
  - Clone & delete GitHub repos from the web UI
"""
import re
import sys
import os
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

import repo_manager as rm
import git_http
import web_ui

PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "0.0.0.0")

# URL patterns
RE_GIT_INFO_REFS = re.compile(r'^/git/([^/]+)/info/refs$')
RE_GIT_RPC = re.compile(r'^/git/([^/]+)/(git-upload-pack|git-receive-pack)$')
RE_REPO_FILES = re.compile(r'^/([^/]+)/files(?:/(.*))?$')
RE_REPO_COMMITS = re.compile(r'^/([^/]+)/commits$')
RE_REPO_ROOT = re.compile(r'^/([^/]+)$')


class ForgeHandler(BaseHTTPRequestHandler):
    """HTTP request handler that routes git protocol and web UI."""

    def log_message(self, format, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))

    def _send_response(self, status, headers, body):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if "Content-Type" not in headers:
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self, html: str, status: int = 200):
        self._send_response(status, {"Content-Type": "text/html; charset=utf-8"}, html)

    def _redirect(self, location: str, code: int = 302):
        self.send_response(code)
        self.send_header("Location", location)
        self.end_headers()

    def _read_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length)

    # ── Routing ────────────────────────────────────────────

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parsed.query

        # ── Git HTTP
        m = RE_GIT_INFO_REFS.match(path)
        if m:
            self._handle_git_get(m.group(1), query)
            return
        m = RE_GIT_RPC.match(path)
        if m:
            # Git doesn't use GET for RPC, but handle gracefully
            self._send_response(405, {}, b"Method Not Allowed")
            return

        # ── Web UI
        if path == "/":
            self._serve_html(web_ui.index_page())
            return

        m = RE_REPO_FILES.match(path)
        if m:
            repo_name = m.group(1)
            subpath = m.group(2) or ""
            host = self.headers.get("Host", "localhost:8000")
            self._serve_html(web_ui.files_page(repo_name, subpath=subpath, host=host))
            return

        m = RE_REPO_COMMITS.match(path)
        if m:
            self._serve_html(web_ui.commits_page(m.group(1)))
            return

        m = RE_REPO_ROOT.match(path)
        if m:
            self._redirect(f"/{m.group(1)}/files")
            return

        self._serve_html(web_ui.render_page("Not Found", "<p>Page not found.</p>"), 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # ── Git HTTP RPC
        m = RE_GIT_RPC.match(path)
        if m:
            repo_name = m.group(1)
            service = m.group(2)
            body = self._read_body()
            self._handle_git_post(repo_name, service, body)
            return

        # ── Clone repo
        if path == "/clone":
            body = self._read_body().decode("utf-8")
            params = urllib.parse.parse_qs(body)
            url = params.get("url", [None])[0]
            if not url:
                self._redirect("/")
                return

            # Validate URL
            if not url.startswith(("http://", "https://")):
                self._serve_html(
                    web_ui.error_page("Invalid URL", f"URL must start with http:// or https://: {url}"),
                    400,
                )
                return

            result = rm.clone_repo(url)
            if result["status"] in ("cloned", "exists"):
                self._redirect(f"/{result['name']}/files")
            else:
                self._serve_html(
                    web_ui.error_page(
                        "Clone Failed",
                        f"Could not clone {url}: {result.get('error', 'Unknown error')}",
                    ),
                    500,
                )
            return

        # ── Delete repo
        if path.startswith("/") and path.endswith("/delete"):
            repo_name = path[1:].rsplit("/", 1)[0]
            if rm.delete_repo(repo_name):
                self._redirect("/")
            else:
                self._serve_html(
                    web_ui.error_page("Delete Failed", f"Could not delete {repo_name}"),
                    500,
                )
            return

        self._serve_html(web_ui.render_page("Not Found", "<p>Not found.</p>"), 404)

    # ── Git HTTP handlers ──────────────────────────────────

    def _handle_git_get(self, repo_name: str, query: str):
        repo = rm.get_repo(repo_name)
        if not repo:
            self._send_response(404, {}, b"Repository not found")
            return

        qp = urllib.parse.parse_qs(query)
        service = qp.get("service", [None])[0]

        if not service:
            self._send_response(
                200,
                {"Content-Type": "text/plain"},
                "Git smart HTTP: use git clone http://host/git/repo\n",
            )
            return

        handler = git_http.GitHTTPHandler(repo["path"])
        status, headers, body = handler.handle_get_info_refs(service)
        self._send_response(status, headers, body)

    def _handle_git_post(self, repo_name: str, service: str, body: bytes):
        repo = rm.get_repo(repo_name)
        if not repo:
            self._send_response(404, {}, b"Repository not found")
            return

        handler = git_http.GitHTTPHandler(repo["path"])
        status, headers, resp_body = handler.handle_post_rpc(service, body)
        self._send_response(status, headers, resp_body)


def main():
    print(f"⚡ Git Forge starting on http://{HOST}:{PORT}")
    print(f"   Repos dir: {rm.REPOS_DIR}")
    rm.ensure_repos_dir()
    server = HTTPServer((HOST, PORT), ForgeHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()


if __name__ == "__main__":
    main()