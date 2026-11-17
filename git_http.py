"""
git_http.py — Git smart HTTP protocol handler.

Implements the git-http-backend protocol using subprocess calls to git.
Handles:
  - GET  info/refs?service=git-upload-pack    (clone advertisement)
  - POST git-upload-pack                       (fetch / clone data)
  - GET  info/refs?service=git-receive-pack    (push advertisement)
  - POST git-receive-pack                      (push data)

Pure stdlib — no WSGI, no Flask.  Passes raw request body through to git
and streams raw git output back to the client.
"""

import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, unquote


class GitHTTPHandler:
    """Handle a single git smart-HTTP request on a bare repository."""

    def __init__(self, repos_dir: str):
        self.repos_dir = repos_dir

    # ── public entry point ──────────────────────────────────────

    def handle(self, req: BaseHTTPRequestHandler, repo: str,
               subpath: str, method: str) -> None:
        """Entry point called from the main request handler."""
        repo_path = os.path.join(self.repos_dir, repo)
        if not repo_path.endswith(".git"):
            repo_path += ".git"
        if not os.path.isdir(repo_path):
            req._send_plain(404, f"Repository '{repo}' not found")
            return

        if method == "GET" and subpath == "info/refs":
            self._handle_info_refs(req, repo_path)
        elif method == "POST" and subpath in ("git-upload-pack", "git-receive-pack"):
            self._handle_rpc(req, repo_path, subpath)
        else:
            req._send_plain(404, "Unknown git endpoint")

    # ── info/refs (advertisement) ───────────────────────────────

    def _handle_info_refs(self, req, repo_path: str) -> None:
        """GET /info/refs?service=git-upload-pack (or receive-pack).

        Returns the service advertisement — the list of refs the server
        offers, wrapped in the git packet-line format.
        """
        parsed = urlparse(req.path)
        qs = parse_qs(parsed.query)
        service = qs.get("service", [None])[0]

        if service not in ("git-upload-pack", "git-receive-pack"):
            req._send_plain(400, "Missing or unknown ?service= parameter")
            return

        # Map git-upload-pack → upload-pack (git subcommand)
        git_cmd = service.replace("git-", "", 1)

        try:
            output = subprocess.check_output(
                ["git", git_cmd, "--stateless-rpc", "--advertise-refs", repo_path],
                stderr=subprocess.STDOUT,
                timeout=30,
                env=self._git_env(),
            )
        except subprocess.CalledProcessError as exc:
            req._send_plain(500, f"git error: {exc.output.decode(errors='replace')}")
            return
        except FileNotFoundError:
            req._send_plain(500, f"git executable '{service}' not found on PATH")
            return

        # Wrap in packet-line format for HTTP transport
        packet = f"# service={service}\n"
        packet_len = len(packet) + 4  # 4-byte length prefix
        pkt_line = f"{packet_len:04x}{packet}0000"
        body = pkt_line.encode() + output

        content_type = f"application/x-{service}-advertisement"
        req.send_response(200)
        req.send_header("Content-Type", content_type)
        req.send_header("Cache-Control", "no-cache")
        req.send_header("Content-Length", str(len(body)))
        req.end_headers()
        req.wfile.write(body)

    # ── git-upload-pack / git-receive-pack ───────────────────────

    def _handle_rpc(self, req, repo_path: str, service: str) -> None:
        """POST git-upload-pack or git-receive-pack — the real data exchange."""
        content_length = int(req.headers.get("Content-Length", 0))
        if content_length == 0:
            req._send_plain(400, "Empty body — nothing to do")
            return

        input_data = req.rfile.read(content_length)
        git_cmd = service.replace("git-", "", 1)

        proc = subprocess.Popen(
            ["git", git_cmd, "--stateless-rpc", repo_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._git_env(),
        )
        stdout, stderr = proc.communicate(input_data, timeout=120)

        if proc.returncode != 0:
            err_text = stderr.decode(errors="replace")
            req._send_plain(500, f"git {service} failed (rc={proc.returncode}): {err_text}")
            return

        content_type = f"application/x-{service}-result"
        req.send_response(200)
        req.send_header("Content-Type", content_type)
        req.send_header("Cache-Control", "no-cache")
        req.send_header("Content-Length", str(len(stdout)))
        req.end_headers()
        req.wfile.write(stdout)

    # ── helpers ─────────────────────────────────────────────────

    @staticmethod
    def _git_env() -> dict:
        """Return an environment dict that prevents git from doing anything
        interactive or reading user-level config."""
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_NOGLOBAL"] = "1"
        return env