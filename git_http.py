"""
Git smart HTTP protocol handler.
Implements git-upload-pack (fetch/clone) and git-receive-pack (push).

The git smart HTTP protocol works as follows:
1. GET /info/refs?service=git-upload-pack  → advertise refs (for clone/fetch)
2. POST /git-upload-pack with pkt-line body → actual pack transfer
3. GET /info/refs?service=git-receive-pack → advertise refs (for push)
4. POST /git-receive-pack with pkt-line body → receive pack
"""
import os
import subprocess

GIT_PATH = "/usr/bin/git"


class GitHTTPHandler:
    """Handles git HTTP protocol requests for a given repo path."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def _run_git(self, args: list, input_data: bytes | None = None) -> tuple:
        """Run a git subprocess. Returns (rc, stdout, stderr)."""
        env = os.environ.copy()
        # Required for git-http-backend behavior
        env["GIT_PROJECT_ROOT"] = os.path.dirname(self.repo_path)
        env["GIT_HTTP_EXPORT_ALL"] = "1"
        env["PATH"] = "/usr/bin:/usr/lib/git-core:" + env.get("PATH", "")

        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                input=input_data,
                timeout=300,
                env=env,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            return -1, b"", b"git operation timed out"
        except Exception as e:
            return -1, b"", str(e).encode()

    def handle_get_info_refs(self, service: str) -> tuple:
        """Handle GET /info/refs?service=<service>.
        Returns (status_code, headers_dict, body_bytes)."""
        if service not in ("git-upload-pack", "git-receive-pack"):
            return 400, {}, b"Bad service"

        # Convert git-upload-pack → upload-pack (git subcommand)
        git_service = service.replace("git-", "", 1)

        rc, stdout, stderr = self._run_git(
            [GIT_PATH, git_service, "--stateless-rpc", "--advertise-refs", self.repo_path]
        )

        if rc != 0:
            error_msg = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else str(stderr)
            return 500, {}, f"Git error: {error_msg}".encode()

        # Format pkt-line header: service advertisement
        packet = f"# service={service}\n"
        length = len(packet) + 4
        prefix = f"{length:04x}{packet}0000"
        body = prefix.encode() + stdout

        content_type = f"application/x-{service}-advertisement"
        headers = {
            "Content-Type": content_type,
            "Cache-Control": "no-cache",
        }
        return 200, headers, body

    def handle_post_rpc(self, service: str, body: bytes) -> tuple:
        """Handle POST /git-upload-pack or /git-receive-pack.
        Returns (status_code, headers_dict, body_bytes)."""
        if service not in ("git-upload-pack", "git-receive-pack"):
            return 400, {}, b"Bad service"

        git_service = service.replace("git-", "", 1)

        rc, stdout, stderr = self._run_git(
            [GIT_PATH, git_service, "--stateless-rpc", self.repo_path],
            input_data=body,
        )

        content_type = f"application/x-{service}-result"
        headers = {
            "Content-Type": content_type,
            "Cache-Control": "no-cache",
        }

        if rc != 0:
            return 500, headers, stderr

        return 200, headers, stdout