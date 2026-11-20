"""Run browser regressions against a disposable K.R.Y.Z.E.N instance."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

TESTS = Path(__file__).resolve().parent
JARVIS = TESTS.parent


def main():
    executable = shutil.which("agent-browser")
    chromium = shutil.which("chromium") or shutil.which("google-chrome")
    if not executable or not chromium:
        raise SystemExit("Browser QA needs agent-browser and Chromium or Google Chrome.")
    with tempfile.TemporaryDirectory(prefix="kryzen-browser-qa-") as temp:
        root = Path(temp)
        home = root / "home"
        home.mkdir()
        env = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
        env.update(HOME=str(home), TMPDIR=str(root), KRYZEN_VAULT=str(root / "vault"),
                   KRYZEN_WORKSPACE=str(root / "projects"), PYTHONDONTWRITEBYTECODE="1",
                   AGENT_BROWSER_EXECUTABLE_PATH=chromium, AGENT_BROWSER_SOCKET_DIR=str(root / "sockets"),
                   AGENT_BROWSER_ARGS="--no-sandbox,--disable-dev-shm-usage,--disable-background-networking")
        subprocess.run([sys.executable, str(JARVIS / "bootstrap.py")], env=env, check=True,
                       stdout=subprocess.DEVNULL)
        run_checks(executable, env, root)


@contextmanager
def running_fixture(env, root):
    with (root / "server.log").open("w+") as log:
        fixture = subprocess.Popen([sys.executable, str(TESTS / "browser_fixture.py"), "--port", "0"],
                                   env=env, stdout=subprocess.PIPE, stderr=log, text=True)
        try:
            url = json.loads(fixture.stdout.readline())["url"]
            yield url, fixture
        except Exception:
            log.seek(0)
            if details := log.read()[-6000:]:
                print(details, file=sys.stderr)
            raise
        finally:
            fixture.terminate()
            fixture.wait(timeout=5)
            fixture.stdout.close()


def run_checks(executable, env, root):
    checks = [(f"layout {width}×{height}", "browser_layout.js", width, height)
              for width, height in ((390, 844), (768, 1024), (1440, 900))]
    checks += [(name, f"browser_{name}.js", 1440, 900)
               for name in ("panel_resize", "editor", "checks", "execution", "capabilities")]
    checks += [(f"workspace {width}×{height}", "browser_workspace.js", width, height)
               for width, height in ((320, 760), (1440, 900))]
    checks.append(("PWA, pause, stop and gates", "browser_pwa.js", 390, 844))
    failures = []
    for label, path, width, height in checks:
        session = "kz-qa-" + uuid.uuid4().hex[:10]

        def browser(*args, source=None):
            result = subprocess.run([executable, "--session", session, *args], env=env, input=source,
                                    text=True, capture_output=True, timeout=45)
            if result.returncode:
                raise RuntimeError(f"{label}: {result.stderr or result.stdout}")
            return result.stdout.strip()

        try:
            with running_fixture(env, root) as (url, fixture):
                browser("open", url)
                browser("set", "viewport", str(width), str(height))
                result = json.loads(browser("eval", "--stdin", source=(TESTS / path).read_text()))
                if not result.get("ok"):
                    raise RuntimeError(f"{label} returned a failed result: {result}")
                print(f"{label}: {result['passed']} passed", flush=True)
                if path == "browser_pwa.js":
                    fixture.terminate()
                    fixture.wait(timeout=5)
                    browser("reload")
                    if browser("get", "text", "h1") != "Server unavailable":
                        raise RuntimeError("PWA did not show the offline fallback when the fixture stopped")
                    print("PWA offline fallback: passed", flush=True)
        except Exception as error:
            failures.append(str(error))
            print(f"FAIL {error}", flush=True)
        finally:
            browser("close")
    if failures:
        raise RuntimeError(f"{len(failures)} browser checks failed")


if __name__ == "__main__":
    main()
