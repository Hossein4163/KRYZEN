"""Images for K.R.Y.Z.E.N: uploads (paste / attach / screen share), project images, page screenshots, analysis.

- Uploads are validated with Pillow, downscaled to MAX_SIDE (fewer vision tokens) and stored once by content hash
  in jarvis/sessions/_images/<sha>.<png|jpg>.
- Project images are read only inside the selected project folder and only for image extensions.
- Page screenshots go through the PC bridge (agent-browser, same sandbox as agents) into
  <project>/.devpilot/screenshots/, which is also the project's screenshot gallery.
- ANALYZE_SCRIPT runs inside the bridge sandbox with Pillow/numpy: stats, palette, contrast, compare (visual diff).
"""
import base64
import hashlib
import io
import json
import re
import time
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

MAX_UPLOAD = 12_000_000
MAX_SIDE = 1600
EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
IMAGE_ID = re.compile(r"^[0-9a-f]{32}\.(png|jpg)$")
SHOT_DIR = ".devpilot/screenshots"
URL = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):\d{2,5}[^\s'\"<>)]*")


def images_dir(sessions):
    d = Path(sessions) / "_images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def normalize(data):
    """Validate + downscale image bytes. Returns (bytes, ext, width, height)."""
    if len(data) > MAX_UPLOAD:
        raise ValueError("image is larger than 12 MB")
    if Image is None:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            if len(data) < 24:
                raise ValueError("not a readable image (truncated PNG)")
            import struct
            w, h = struct.unpack(">II", data[16:24])
            if w * h > 60_000_000:
                raise ValueError("image dimensions are too large")
            if max(w, h) > MAX_SIDE:
                scale = MAX_SIDE / max(w, h)
                w, h = int(w * scale), int(h * scale)
            return data, "png", w, h
        elif data.startswith(b"\xff\xd8"):
            return data, "jpg", 800, 600
        else:
            raise ValueError("not a readable image (unsupported or invalid image format)")
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:
        raise ValueError(f"not a readable image ({type(e).__name__})") from e
    if im.width * im.height > 60_000_000:
        raise ValueError("image dimensions are too large")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    if im.mode in ("RGBA", "LA", "P") or im.format == "PNG":
        im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
        im.save(out, "PNG", optimize=True)
        ext = "png"
    else:
        im.convert("RGB").save(out, "JPEG", quality=86)
        ext = "jpg"
    return out.getvalue(), ext, im.width, im.height


def save_upload(sessions, data):
    blob, ext, w, h = normalize(data)
    sha = hashlib.sha256(blob).hexdigest()[:32]
    path = images_dir(sessions) / f"{sha}.{ext}"
    if not path.exists():
        path.write_bytes(blob)
    return {"id": path.name, "url": f"/api/image?id={path.name}", "width": w, "height": h, "bytes": len(blob)}


def decode_data_url(value):
    m = re.match(r"^data:image/[\w.+-]+;base64,(.+)$", value or "", re.S)
    if not m:
        raise ValueError("expected a base64 image data URL")
    return base64.b64decode(m.group(1), validate=False)


def upload_path(sessions, image_id):
    if not IMAGE_ID.fullmatch(image_id or ""):
        raise ValueError("invalid image id")
    path = images_dir(sessions) / image_id
    if not path.exists():
        raise FileNotFoundError("image not found")
    return path


def project_image(root, rel):
    """Resolve an image path inside a project; refuses anything outside it or non-image files."""
    base = Path(root).resolve()
    p = Path(rel).expanduser()
    p = (p if p.is_absolute() else base / p).resolve()
    if p != base and base not in p.parents:
        raise PermissionError("image is outside the project")
    if p.suffix.lower() not in EXTS:
        raise ValueError("not an image file (png, jpg, webp, gif)")
    if not p.is_file():
        raise FileNotFoundError(f"no such image: {rel}")
    return p


def as_part(data, max_side=1280):
    """OpenAI-style content part for vision models: JPEG, ≤1280 px — small enough for prompts and checkpoints."""
    if Image is None:
        b64 = base64.b64encode(data).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        im = bg
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=80)
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()}}


def list_shots(root, limit=60):
    d = Path(root) / SHOT_DIR
    if not d.exists():
        return []
    files = sorted((p for p in d.iterdir() if p.suffix.lower() in EXTS and p.is_file()),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for p in files:
        meta = {}
        side = p.with_suffix(p.suffix + ".json")
        if side.exists():
            try:
                meta = json.loads(side.read_text())
            except (OSError, ValueError):
                meta = {}
        out.append({"path": f"{SHOT_DIR}/{p.name}", "name": p.name, "t": p.stat().st_mtime, "bytes": p.stat().st_size, **meta})
    return out


def shot_name(label="shot"):
    safe = re.sub(r"[^a-z0-9-]+", "-", str(label).lower()).strip("-")[:40] or "shot"
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{safe}.png"


def screenshot(bridge, root, url, label="page", width=1440, height=900, meta=None):
    """Capture `url` with agent-browser (through the bridge sandbox) into the project screenshot gallery."""
    if not URL.fullmatch(url or "") and not re.fullmatch(r"https?://[\w.-]+(:\d+)?(/[^\s]*)?", url or ""):
        raise ValueError("give an http(s) URL, e.g. http://localhost:5173")
    out = f"{Path(root)}/{SHOT_DIR}/{shot_name(label)}"
    session = "kryzen-shot"
    steps = [["--session", session, "set", "viewport", str(width), str(height)], ["--session", session, "open", url],
             ["--session", session, "wait", "1200"], ["--session", session, "screenshot", out]]
    bridge("/shell", {"cmd": f"mkdir -p {json.dumps(str(Path(out).parent))}", "cwd": str(root), "timeout": 20})
    for args in steps:
        r = bridge("/browser", {"args": args, "cwd": str(root), "timeout": 90})
        if isinstance(r, dict) and (r.get("error") or r.get("exit_code") not in (None, 0)):
            if args[2] == "wait":
                continue
            raise RuntimeError(f"screenshot failed at '{args[2]}': {str(r.get('error') or r.get('stderr') or r.get('output'))[:300]}")
    if not Path(out).exists():
        raise RuntimeError("the browser did not write a screenshot")
    if meta:
        Path(out + ".json").write_text(json.dumps({**meta, "url": url}, ensure_ascii=False))
    return f"{SHOT_DIR}/{Path(out).name}"


def preview_urls(text):
    """Dev-server addresses printed in job output (Vite, Next, CRA, Astro, Python http.server …), newest last."""
    seen = []
    for m in URL.finditer(text or ""):
        u = m.group(0).rstrip("/.,;")
        u = u.replace("0.0.0.0", "127.0.0.1").replace("[::1]", "127.0.0.1")
        if u not in seen:
            seen.append(u)
    return seen


# Runs in the bridge sandbox: python3 -c ANALYZE_SCRIPT <mode> <image> [<other image>] [<diff out>]
ANALYZE_SCRIPT = r'''
import json, sys
try:
    from PIL import Image
except ImportError:
    Image = None, ImageChops
mode, path = sys.argv[1], sys.argv[2]
def lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4
    r, g, b = c[:3]
    return .2126 * ch(r) + .7152 * ch(g) + .0722 * ch(b)
def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return round((la + .05) / (lb + .05), 2)
im = Image.open(path)
out = {"file": path, "size": list(im.size), "mode": im.mode, "format": im.format}
rgb = im.convert("RGB")
if mode in ("stats", "palette", "contrast"):
    small = rgb.copy(); small.thumbnail((256, 256))
    q = small.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:24]; counts = sorted(q.getcolors(), reverse=True)
    total = sum(n for n, _ in counts)
    colors = [{"hex": "#%02x%02x%02x" % tuple(pal[i*3:i*3+3]), "share": round(n / total, 3)} for n, i in counts]
    out["palette"] = colors
    gray = small.convert("L"); px = list(gray.getdata())
    out["brightness"] = round(sum(px) / len(px) / 255, 3)
    out["has_transparency"] = im.mode in ("RGBA", "LA") and im.getextrema()[-1][0] < 255
    if len(colors) >= 2:
        hx = lambda h: tuple(int(h[i:i+2], 16) for i in (1, 3, 5))
        out["contrast_top_two"] = contrast(hx(colors[0]["hex"]), hx(colors[1]["hex"]))
        out["contrast_note"] = "WCAG AA needs 4.5 for body text, 3 for large text"
elif mode == "compare":
    other = Image.open(sys.argv[3]).convert("RGB")
    out["other"] = sys.argv[3]; out["other_size"] = list(other.size)
    if other.size != rgb.size:
        other = other.resize(rgb.size)
        out["note"] = "sizes differ; the second image was resized for comparison"
    diff = ImageChops.difference(rgb, other).convert("L").point(lambda v: 255 if v > 24 else 0)
    changed = sum(1 for v in diff.getdata() if v)
    out["changed_pixels"] = changed
    out["changed_percent"] = round(100 * changed / (rgb.width * rgb.height), 3)
    out["changed_box"] = diff.getbbox()
    if len(sys.argv) > 4 and changed:
        overlay = rgb.copy(); red = Image.new("RGB", rgb.size, (255, 40, 40))
        overlay.paste(red, mask=diff); Image.blend(rgb, overlay, .55).save(sys.argv[4])
        out["diff_image"] = sys.argv[4]
else:
    raise SystemExit("mode must be stats, palette, contrast or compare")
print(json.dumps(out))
'''


def extract_vibe_tokens(data_or_path=None, aesthetic="Swiss Grid"):
    """Extract design tokens (palette, spacing, typography, radii) from an image or aesthetic preset."""
    palette = ["#0A0A0A", "#141414", "#E60000", "#FFFFFF", "#737373"]
    if data_or_path:
        raw_bytes = None
        if isinstance(data_or_path, (str, Path)):
            p = Path(data_or_path)
            if p.is_file():
                raw_bytes = p.read_bytes()
        elif isinstance(data_or_path, bytes):
            raw_bytes = data_or_path

        if raw_bytes and Image is not None:
            try:
                im = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
                im.thumbnail((128, 128))
                q = im.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
                pal = q.getpalette()[:18]
                counts = sorted(q.getcolors() or [], reverse=True)
                extracted = ["#%02x%02x%02x" % tuple(pal[i * 3:i * 3 + 3]) for _, i in counts]
                if extracted:
                    palette = extracted
            except Exception:
                pass

    aesthetic_lower = (aesthetic or "swiss grid").lower()
    radius = "0px"
    if "saas" in aesthetic_lower:
        radius = "6px"
    elif "playful" in aesthetic_lower:
        radius = "12px"
    elif "cyberpunk" in aesthetic_lower or "brutalist" in aesthetic_lower or "swiss" in aesthetic_lower:
        radius = "0px"

    bg = palette[0] if len(palette) > 0 else "#0A0A0A"
    surface = palette[1] if len(palette) > 1 else "#141414"
    accent = next((c for c in palette if c.upper() not in ("#000000", "#0A0A0A", "#FFFFFF", "#141414")), "#E60000")
    text = "#FFFFFF" if bg.lower() in ("#000000", "#0a0a0a", "#141414", "#1a1a1a") else "#111111"
    border = "#262626" if text == "#FFFFFF" else "#E5E5E5"

    tokens = {
        "bg": bg,
        "surface": surface,
        "accent": accent,
        "text": text,
        "text_muted": "#737373" if text == "#FFFFFF" else "#666666",
        "border": border,
        "radius": radius,
        "font_sans": "'Archivo', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "font_mono": "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
        "space_xs": "4px",
        "space_sm": "8px",
        "space_md": "16px",
        "space_lg": "24px",
        "space_xl": "32px"
    }
    return tokens


def generate_vibe_tokens_css(tokens):
    """Generate production-ready CSS variables stylesheet from tokens."""
    return f"""/* K.R.Y.Z.E.N Vibe Studio Design Tokens */
:root {{
  --vibe-bg: {tokens.get('bg', '#0A0A0A')};
  --vibe-surface: {tokens.get('surface', '#141414')};
  --vibe-accent: {tokens.get('accent', '#E60000')};
  --vibe-text: {tokens.get('text', '#FFFFFF')};
  --vibe-text-muted: {tokens.get('text_muted', '#737373')};
  --vibe-border: {tokens.get('border', '#262626')};
  --vibe-radius: {tokens.get('radius', '0px')};

  --vibe-font-sans: {tokens.get('font_sans')};
  --vibe-font-mono: {tokens.get('font_mono')};

  --vibe-space-xs: {tokens.get('space_xs', '4px')};
  --vibe-space-sm: {tokens.get('space_sm', '8px')};
  --vibe-space-md: {tokens.get('space_md', '16px')};
  --vibe-space-lg: {tokens.get('space_lg', '24px')};
  --vibe-space-xl: {tokens.get('space_xl', '32px')};
}}
"""

