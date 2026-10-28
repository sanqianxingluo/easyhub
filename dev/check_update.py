#!/usr/bin/env python3
"""Offline self-test for the updater: local fake GitHub + full check/download/apply flow.

Why a local server: the real GitHub is flaky through this network (anonymous API 403s),
and what we need to verify is *our* logic - version compare, 302 parsing, zip extraction,
and the directory swap performed by the generated helper script.

    python dev\\check_update.py
"""
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _testbase  # noqa: F401  (puts src\\ on sys.path)

import updater
from version import APP_VERSION

REPO = updater.REPO
TAG = "v9.9.9"
ZIP_NAME = "EasyHub-Portable-9.9.9.zip"

FAILS = []


def check(name, cond, extra=""):
    print(("  [ok]   " if cond else "  [FAIL] ") + name + (("  " + extra) if extra else ""))
    if not cond:
        FAILS.append(name)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.endswith("/releases/latest"):
            # real GitHub answers with a 302 to /releases/tag/<tag>
            self.send_response(302)
            self.send_header("Location", "/%s/releases/tag/%s" % (REPO, TAG))
            self.end_headers()
            return
        if "/releases/tag/" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.endswith(ZIP_NAME):
            data = self.server.zip_bytes
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(404)
        self.end_headers()


def make_zip(path):
    """Same layout as the real package: Easyhub\\app\\EasyHub.exe + extra files."""
    src = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "whoami.exe")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(src, "Easyhub/app/EasyHub.exe")
        zf.writestr("Easyhub/app/_internal/marker.txt", "new build")
        zf.writestr("Easyhub/config/", "")
        zf.writestr("Easyhub/README.txt", "fake package")


def main():
    work = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "..", "verify", "update_test"))
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)

    zpath = os.path.join(work, "fake.zip")
    make_zip(zpath)
    with open(zpath, "rb") as f:
        zip_bytes = f.read()

    srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    srv.zip_bytes = zip_bytes
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    updater.BASE = base
    print("fake github: %s   fake tag %s, current %s" % (base, TAG, APP_VERSION))

    print("\n[1] version compare")
    check("1.3.2 > 1.3.1", updater.is_newer("v1.3.2", "1.3.1"))
    check("1.3.10 > 1.3.9", updater.is_newer("v1.3.10", "1.3.9"))
    check("same is not newer", not updater.is_newer("v1.3.2", "1.3.2"))
    check("older is not newer", not updater.is_newer("v1.2.9", "1.3.2"))

    print("\n[2] latest_tag (follows 302)")
    tag = updater.latest_tag()
    check("got tag", tag == TAG, tag)

    print("\n[3] prepare: download / extract / write helper")
    root = os.path.join(work, "Easyhub")
    os.makedirs(os.path.join(root, "app"))
    with open(os.path.join(root, "app", "EasyHub.exe"), "wb") as f:
        f.write(b"old build")
    os.makedirs(os.path.join(root, "config"), exist_ok=True)
    cfg = os.path.join(root, "config", "servers.json")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write('{"servers": [], "prefs": {}}')

    seen = []
    helper, got_tag = updater.prepare(root=root, progress=lambda a, b: seen.append((a, b)))
    check("tag matches", got_tag == TAG, got_tag)
    check("progress callback fired", len(seen) > 0, "%d calls" % len(seen))
    check("helper written", bool(helper) and os.path.exists(helper), helper)
    check("new app\\EasyHub.exe staged",
          os.path.exists(os.path.join(root, ".update", "app", "EasyHub.exe")))
    check("zip removed after extract",
          not os.path.exists(os.path.join(root, ".update", "update.zip")))
    check("config untouched", os.path.exists(cfg))

    # The helper waits for the *current* process name to disappear. We are python.exe,
    # so rewrite the wait name - otherwise this test would wait forever.
    with open(helper, encoding="mbcs", errors="replace") as f:
        text = f.read()
    text = text.replace(os.path.basename(sys.executable), "EasyHubNotRunning.exe")
    with open(helper, "w", encoding="mbcs", errors="replace") as f:
        f.write(text)

    print("\n[4] run the helper (simulates swap after restart)")
    subprocess.run(["cmd", "/c", helper], timeout=120)
    exe = os.path.join(root, "app", "EasyHub.exe")
    size = os.path.getsize(exe) if os.path.exists(exe) else 0
    check("app\\EasyHub.exe replaced", size > 1024, "%d bytes" % size)
    check("new _internal in place",
          os.path.exists(os.path.join(root, "app", "_internal", "marker.txt")))
    check("app.old cleaned", not os.path.exists(os.path.join(root, "app.old")))
    check(".update cleaned", not os.path.exists(os.path.join(root, ".update")))
    check("servers.json survived", os.path.exists(cfg))

    srv.shutdown()
    print("\nRESULT: %s" % ("all passed" if not FAILS
                            else "FAILED %d: %s" % (len(FAILS), ", ".join(FAILS))))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
