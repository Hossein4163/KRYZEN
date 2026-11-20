"""Prepare a fresh vault using the same tools as a manual install."""
import subprocess
import sys
from pathlib import Path

AGENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT / "workflow"))
sys.path.insert(0, str(AGENT / "bridge"))
from vaultnotes import AGENT_NOTES, SYS
from pc_bridge import WORKSPACE


def invoke(path, *args):
    subprocess.run([sys.executable, "-B", str(AGENT / path), *args], check=True)


def main():
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    if not (SYS / "Templates" / "project" / "PROJECT.md").is_file():
        invoke("workflow/create_templates.py")
    if not any(AGENT_NOTES.glob("*.md")):
        invoke("workflow/setup_product_mesh.py")
        invoke("jarvis/skill_pack.py", "--install")
        invoke("jarvis/capability_pack.py", "--install")


if __name__ == "__main__":
    main()
