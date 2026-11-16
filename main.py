#!/usr/bin/env python3
"""
git-forge — A minimal GitHub-compatible git forge implementing the
git smart HTTP protocol (RFC 2616 + git protocol v2).

Supported operations:
  - git clone   (info/refs + git-upload-pack)
  - git pull    (info/refs + git-upload-pack)
  - git push    (info/refs + git-receive-pack)

Usage:
  python3 main.py [--host HOST] [--port PORT] [--repo-root PATH]

Environment:
  GIT_PROJECT_ROOT  — override the repo root directory (default: ./repos)
  GIT_HTTP_BACKEND  — path to git-http-backend (auto-detected if unset)

Stdlib-only.  Python 3.13+.
"""

import argparse
import http.server
import io
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_REPO_ROOT = os.environ.get("GIT_PROJECT_ROOT", os.path.join(os.getcwd(), "repos"))

# Locate git-http-backend
def _find_git_http_backend() -> str:
    env = os.environ.get("GIT_HTTP_BACKEND", "")
    if env:
        return env
    for candidate in (
        "/usr/lib/git-core/git-http-backend",
        "/usr/libexec/git-core/git-http-backend",
        "/usr/local/libexec/git-core/git-http-backend",
    ):
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("git-http-backend") or "git-http-backend"

GIT_HTTP_BACKEND = _find_git_http_backend()

# ── HTTP constants ───────────────────────────────────────────────────────────

# The git client sends these as Accept: and Content-Type:
GIT_UPLOAD_PACK_REQUEST = "application/x-git-upload-pack-request"
GIT_UPLOAD_PACK_RESULT = "application/x-git-upload-pack-result"
GIT_UPLOAD_PACK_ADVERT = "application/x-git-upload-pack-advertisement"
GIT_RECEIVE_PACK_REQUEST = "application/x-git-receive-pack-request"
GIT_RECEIVE_PACK_RESULT = "application/x-git-receive-pack-result"
GIT_RECEIVE_PACK_ADVERT = "application/x-git-receive-pack-advertisement"

SERVICE_UPLOAD = "git-upload-pack"
SERVICE_RECEIVE = "git-receive-pack"

def get_repo_name(path_info: str, suffixes: list[str]) -> str | None:
    """Strip a known git-http suffix from the path to get the repo name.
    E.g., '/user/repo.git/info/refs' -> 'user/repo.git'
    """
    for suffix in suffixes:
        if path_info.endswith(suffix):
            return path_info[: -len(suffix)].strip("/") or None
    return None


# ── Helpers ──────────────────────────────────────────────────────────────────

def parse_service(query: str) -> str | None:
    """Extract the git service name from a query string like ?service=git-upload-pack."""
    qs = urllib.parse.parse_qs(query)
    svc = qs.get("service", [None])[0]
    if svc in (SERVICE_UPLOAD, SERVICE_RECEIVE):
        return svc
    return None


def repo_path(repo_root: str, path_info: str) -> Path | None:
    """
    Map a URL path like /user/repo.git to a filesystem directory.
    Rejects directory-traversal attempts.
    """
    p = path_info.strip("/")
    if not p:
        return None
    # Security: reject paths with .. or leading .
    parts = p.split("/")
    for part in parts:
        if part in ("", ".", "..") or part.startswith(".."):
            return None
    full = Path(repo_root) / p
    # Resolve to catch any sneaky symlink tricks, then verify it's under repo_root
    try:
        resolved = full.resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    root_resolved = Path(repo_root).resolve(strict=False)
    if os.path.commonpath([str(resolved), str(root_resolved)]) != str(root_resolved):
        return None
    return resolved


def ensure_bare_repo(path: Path) -> bool:
    """Create a bare git repository if it doesn't exist."""
    if (path / "HEAD").is_file():
        return True
    try:
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "--bare", str(path)],
            capture_output=True,
            check=True,
            timeout=30,
        )
        return True
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return False


def run_git_http_backend(environ: dict[str, str], body: bytes | None) -> tuple[int, bytes, list[tuple[str, str]]]:
    """
    Call git-http-backend as a subprocess with CGI-like environment variables.
    Returns (status_code, body, headers_list).
    """
    proc = subprocess.Popen(
        [GIT_HTTP_BACKEND],
        stdin=subprocess.PIPE if body else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, **environ},
    )
    out, err = proc.communicate(input=body, timeout=120)

    # Parse CGI-style output: headers followed by \r\n\r\n then body
    header_bytes, sep, body_out = out.partition(b"\r\n\r\n")
    if not sep:
        return proc.returncode or 500, out, []

    headers: list[tuple[str, str]] = []
    status_code = proc.returncode or 200
    for line in header_bytes.decode("utf-8", errors="replace").split("\r\n"):
        if not line.strip():
            break
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if key.lower() == "status":
            # Status: 200 OK
            parts = val.split(" ", 1)
            try:
                status_code = int(parts[0])
            except ValueError:
                pass
        elif key.lower() == "content-type":
            headers.append(("Content-Type", val))
        elif key.lower() not in ("content-length", "transfer-encoding", "connection"):
            headers.append((key, val))

    return status_code, body_out, headers


# ── HTTP Request Handler ─────────────────────────────────────────────────────

class GitHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """
    Handles the git smart HTTP protocol.

    Discovery phase (GET):
      GET /repo.git/info/refs?service=git-upload-pack
      GET /repo.git/info/refs?service=git-receive-pack

    Transfer phase (POST):
      POST /repo.git/git-upload-pack
      POST /repo.git/git-receive-pack
    """

    repo_root: str = DEFAULT_REPO_ROOT
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        """Minimal logging to stderr."""
        sys.stderr.write(f"[git-forge] {args[0] if args else fmt}\n")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length) if length > 0 else b""

    def _send_response(self, code: int, body: bytes, headers: list[tuple[str, str]] | None = None):
        self.send_response(code)
        for h, v in (headers or []):
            self.send_header(h, v)
        if body:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _handle_info_refs(self, repo: Path, service: str):
        """GET /repo.git/info/refs?service=git-upload-pack (or receive-pack)"""
        if not ensure_bare_repo(repo):
            self._send_response(500, b"Failed to create repo")
            return

        # Strip 'git-' prefix: git-upload-pack -> upload-pack
        git_cmd = service.removeprefix("git-")
        cmd = ["git", git_cmd, "--stateless-rpc", "--advertise-refs", str(repo)]
        proc = subprocess.run(cmd, capture_output=True, timeout=30, cwd=str(repo))
        if proc.returncode != 0:
            self._send_response(500, proc.stderr)
            return

        # Prepend the service header: 4-byte hex length + # service=...
        pkt_line = f"# service={service}\n"
        prefix = f"{len(pkt_line) + 4:04x}{pkt_line}0000".encode()
        body = prefix + proc.stdout

        mime = (GIT_UPLOAD_PACK_ADVERT if service == SERVICE_UPLOAD
                else GIT_RECEIVE_PACK_ADVERT)

        self._send_response(200, body, [
            ("Content-Type", mime),
            ("Cache-Control", "no-cache, max-age=0, must-revalidate"),
            ("Expires", "Fri, 01 Jan 1980 00:00:00 GMT"),
        ])

    def _handle_git_rpc(self, repo: Path, service: str, body: bytes):
        """POST /repo.git/git-upload-pack (or receive-pack)"""
        if not ensure_bare_repo(repo):
            self._send_response(500, b"Failed to create repo")
            return

        cmd = ["git", service.removeprefix("git-"), "--stateless-rpc", str(repo)]
        proc = subprocess.run(
            cmd,
            input=body,
            capture_output=True,
            timeout=120,
            cwd=str(repo),
        )
        result_mime = (
            GIT_UPLOAD_PACK_RESULT if service == SERVICE_UPLOAD
            else GIT_RECEIVE_PACK_RESULT
        )

        if proc.returncode != 0:
            self._send_response(200, proc.stderr or b"error", [
                ("Content-Type", result_mime),
            ])
            return

        self._send_response(200, proc.stdout, [
            ("Content-Type", result_mime),
            ("Cache-Control", "no-cache, max-age=0, must-revalidate"),
        ])

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path_info = parsed.path

        # info/refs discovery
        info_refs_repo = get_repo_name(path_info, ["/info/refs"])
        if info_refs_repo:
            repo = repo_path(self.repo_root, "/" + info_refs_repo)
            if repo:
                svc = parse_service(parsed.query)
                if svc:
                    return self._handle_info_refs(repo, svc)

        # Dumb HTTP: allow fetching loose objects (for older clients)
        repo = repo_path(self.repo_root, path_info)

        # Dumb HTTP: allow fetching loose objects (for older clients)
        if repo:
            mapped = repo / urllib.parse.unquote(path_info.split("/", 1)[-1]).lstrip("/")
            try:
                resolved = mapped.resolve(strict=True)
                root_resolved = Path(self.repo_root).resolve(strict=True)
                if os.path.commonpath([str(resolved), str(root_resolved)]) == str(root_resolved) and resolved.is_file():
                    content = resolved.read_bytes()
                    self._send_response(200, content, [
                        ("Content-Type", "application/octet-stream"),
                    ])
                    return
            except (OSError, RuntimeError):
                pass

        # Root info page or not found
        if not path_info or path_info == "/":
            body = self._root_page()
            self._send_response(200, body, [("Content-Type", "text/html; charset=utf-8")])
        else:
            self._send_response(200, b"Not a git repository.\n", [("Content-Type", "text/plain")])

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path_info = parsed.path
        body = self._read_body()

        # git-upload-pack / git-receive-pack RPC
        upload_repo = get_repo_name(path_info, [f"/{SERVICE_UPLOAD}"])
        receive_repo = get_repo_name(path_info, [f"/{SERVICE_RECEIVE}"])

        if upload_repo:
            repo = repo_path(self.repo_root, "/" + upload_repo)
            if repo:
                return self._handle_git_rpc(repo, SERVICE_UPLOAD, body)
        if receive_repo:
            repo = repo_path(self.repo_root, "/" + receive_repo)
            if repo:
                return self._handle_git_rpc(repo, SERVICE_RECEIVE, body)

        self._send_response(404, b"Not found\n")

    def _root_page(self) -> bytes:
        """Render a minimal index page listing available repos."""
        lines = [
            "<!DOCTYPE html>",
            '<html lang="en"><head><meta charset="utf-8">',
            "<title>git-forge</title>",
            "<style>body{font-family:monospace;max-width:720px;margin:2rem auto;padding:0 1rem;}",
            "h1{font-size:1.4rem}a{color:#0366d6}</style>",
            "</head><body>",
            "<h1>git-forge</h1>",
            "<p>A minimal git server implementing the git smart HTTP protocol.</p>",
            "<h2>Repositories</h2><ul>",
        ]
        root = Path(self.repo_root)
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if d.is_dir() and (d / "HEAD").is_file():
                    name = d.name
                    lines.append(f'<li><a href="/{name}">{name}</a></li>')
        if not any('<li>' in l for l in lines):
            lines.append("<li><em>No repositories yet. Create one:</em>")
            lines.append('<pre>git init --bare repos/my-project.git</pre></li>')
        lines.extend(["</ul></body></html>"])

        return "\n".join(lines).encode()


class GitForgeServer(http.server.HTTPServer):
    allow_reuse_address = True

    def __init__(self, host: str, port: int, repo_root: str):
        self.repo_root = repo_root
        # Bind repo_root into the handler class
        def _handler(*args):
            GitHTTPRequestHandler.repo_root = repo_root
            return GitHTTPRequestHandler(*args)
        super().__init__((host, port), _handler)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="git-forge — a minimal git smart HTTP server",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bind address (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Listen port (default: {DEFAULT_PORT})")
    parser.add_argument("--repo-root", default=DEFAULT_REPO_ROOT, help=f"Repository root (default: {DEFAULT_REPO_ROOT})")
    args = parser.parse_args()

    os.makedirs(args.repo_root, exist_ok=True)

    print(f"git-forge starting on http://{args.host}:{args.port}")
    print(f"Repository root: {os.path.abspath(args.repo_root)}")
    print(f"git-http-backend: {GIT_HTTP_BACKEND}")
    sys.stdout.flush()

    server = GitForgeServer(args.host, args.port, args.repo_root)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()