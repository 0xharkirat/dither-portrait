"""Turn a photo into an animated dithered SVG pair for a GitHub profile README.

Writes portrait-dark.svg and portrait-light.svg: a one-bit Floyd-Steinberg dither of
the source photo, with the grain animated by a field of slow travelling waves.

Two properties drive most of the design:

  Deterministic. The same photo and settings always produce byte-identical output.
  That is what lets this run on a schedule without committing a change every day.
  Nothing here may use random(), the clock, or dict iteration order.

  Renderable by GitHub. README images are served through <img>, which blocks scripts
  and external fetches but does run CSS. Embedded data: URIs cycled by a CSS keyframe
  are the only way to animate inside that sandbox.

    python3 portrait.py --username octocat
    python3 portrait.py --photo me.jpg --motion shimmer --frames 12
"""

import argparse
import base64
import io
import json
import math
import os
import sys
import urllib.request

from PIL import Image, ImageOps

# Travelling waves that displace the dither threshold, in 0-255 levels.
#
# Independent random jitter per cell reads as television static, and slowing that down
# only turns it into a strobe. Coherent motion needs neighbouring cells to move
# together, so the eye can follow a ripple across the surface.
#
# Each entry is (wavelength x, wavelength y, cycles per loop, amplitude, phase). Cycles
# per loop must be a whole number or the loop jumps when it wraps; check_waves()
# enforces that. Wavelengths are deliberately not multiples of each other, otherwise
# the crests line up and it reads as corduroy rather than water. Two components travel
# one way and one comes back against them, and that interference is what stops it
# looking like a light sweeping across.
WAVES = [
    (12, 17, 1, 8, 0.0),
    (-14, 9, 1, 7, 1.7),
    (8, -21, 2, 5, 3.1),
    (19, 13, -1, 5, 5.0),
]

# Which bit becomes ink, per theme. Everything else is transparent, so the page shows
# through and the portrait has no rectangle around it.
#
# The themes need opposite polarity to both look photographic. Light is ink on paper,
# so shadows are the ink. Dark is light on a screen, so the lit parts of the face glow
# and shadows fall away into the background. Map it the other way and a face renders as
# a solid pale blob.
POLARITY = {"dark": 1, "light": 0}

# Whether that default suits a photo depends on the subject, not the background. A
# sweep over 18 real avatars found roughly a third where the dark variant turns into a
# solid block, so `invert` swaps which tone becomes ink. It is deliberately a switch
# rather than a guess: auto-detecting from background brightness was tried and made
# some portraits worse, because a bright-background photo whose subject carries its own
# dark structure still reads better under the default.

DEFAULTS = {
    "size": 330,
    "max_height": 520,
    "grid": 120,
    "frames": 16,
    "duration": 2.8,
    "motion": "water",
    "themes": "dark,light",
    "ink_dark": "#c9d1d9",
    "ink_light": "#24292f",
    "radius": 14,
    "prefix": "portrait",
    "out_dir": ".",
}


def check_waves(waves=WAVES):
    """A fractional cycle count makes the last frame jump back to the first."""
    for lx, ly, cycles, amp, phase in waves:
        assert cycles == int(cycles), f"wave {lx}x{ly} has a fractional cycle count"
    start, wrap = ripple(6, 6, 0.0, waves), ripple(6, 6, 1.0, waves)
    worst = max(abs(a - b) for ra, rb in zip(start, wrap) for a, b in zip(ra, rb))
    assert worst < 1e-9, f"loop does not close: {worst:.4f} levels of jump at the wrap"


# --- source -----------------------------------------------------------------

def load_source(photo=None, username=None):
    """A local file if given, otherwise the user's GitHub avatar."""
    if photo:
        return Image.open(photo)
    if not username:
        raise SystemExit("need --photo or --username")
    api = f"https://api.github.com/users/{username}"
    req = urllib.request.Request(api, headers={"user-agent": "dither-portrait"})
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        req.add_header("authorization", "token " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        url = json.load(r)["avatar_url"]
    with urllib.request.urlopen(f"{url}&s=640", timeout=30) as r:
        return Image.open(io.BytesIO(r.read()))


# --- motion -----------------------------------------------------------------

def ripple(w, h, t, waves=WAVES):
    """Threshold displacement field at loop position `t` (0 to 1)."""
    field = []
    for y in range(h):
        row = []
        for x in range(w):
            v = 0.0
            for lx, ly, cycles, amp, phase in waves:
                v += amp * math.sin(2 * math.pi * (x / lx + y / ly - cycles * t) + phase)
            row.append(v)
        field.append(row)
    return field


def _hash_noise(x, y, i):
    """Deterministic value in -1..1. A seeded PRNG would also work, but a pure hash of
    the coordinates cannot be knocked out of step by changing the iteration order."""
    n = (x * 374761393 + y * 668265263 + i * 1274126177) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) / 0xFFFFFFFF) * 2.0 - 1.0


def shimmer(w, h, frame, amplitude=26.0):
    """Per-cell independent jitter: the static look, kept as an option because it suits
    a hard-edged photo where coherent ripples read as a wobble."""
    return [[_hash_noise(x, y, frame) * amplitude for x in range(w)] for y in range(h)]


def displacement(mode, w, h, frame, frames):
    if mode == "water":
        return ripple(w, h, frame / frames)
    if mode == "shimmer":
        return shimmer(w, h, frame)
    if mode == "none":
        return [[0.0] * w for _ in range(h)]
    raise SystemExit(f"unknown --motion {mode!r}; use water, shimmer or none")


# --- dither -----------------------------------------------------------------

def dither(buf, w, h):
    """Floyd-Steinberg, serpentine, binary output."""
    buf = [row[:] for row in buf]
    out = bytearray(w * h)
    for y in range(h):
        xs = range(w) if y % 2 == 0 else range(w - 1, -1, -1)
        step = 1 if y % 2 == 0 else -1
        for x in xs:
            old = buf[y][x]
            new = 255 if old > 128 else 0
            out[y * w + x] = 1 if new else 0
            err = old - new
            for dx, dy, wt in ((step, 0, 7), (-step, 1, 3), (0, 1, 5), (step, 1, 1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    buf[ny][nx] += err * wt / 16
    return out


def encode(bits, w, h, ink, colour):
    """1-bit indexed PNG: `ink` is the bit value that draws, the other is transparent.

    Saved straight from mode P. Converting with an adaptive palette here would
    requantise and reorder the entries, silently breaking which index means what.
    """
    img = Image.frombytes("P", (w, h), bytes(bits))
    rgb = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    palette = [0, 0, 0, 0, 0, 0]
    palette[ink * 3:ink * 3 + 3] = rgb
    img.putpalette(palette)
    blob = io.BytesIO()
    img.save(blob, format="PNG", optimize=True, bits=1, transparency=1 - ink)
    return base64.b64encode(blob.getvalue()).decode()


# --- svg --------------------------------------------------------------------

def svg(frames, w, h, duration, radius):
    """Stack the frames and cycle them with CSS.

    Each frame is visible for one slot of the loop; a negative animation-delay staggers
    them so exactly one shows at a time. steps(1, end) keeps the cut hard, because
    crossfading blurs the dots into grey and loses the point of a binary dither.
    """
    n = len(frames)
    head = ["<?xml version='1.0' encoding='UTF-8'?>",
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}px" height="{h}px" '
            f'viewBox="0 0 {w} {h}">']
    clip = f'<clipPath id="r"><rect width="{w}" height="{h}" rx="{radius}"/></clipPath>'

    def layer(i, data, cls=""):
        return (f'<image id="p{i}"{cls} x="0" y="0" width="{w}" height="{h}"'
                f' clip-path="url(#r)" href="data:image/png;base64,{data}"/>')

    if n == 1:                       # --motion none: no animation to declare
        body = [f"<style>image{{image-rendering:pixelated}}</style>", clip,
                layer(0, frames[0])]
        return "\n".join(head + body + ["</svg>\n"])

    css = [f".fr{{opacity:0;animation:flick {duration}s steps(1,end) infinite;"
           "image-rendering:pixelated}",
           f"@keyframes flick{{0%{{opacity:1}}{100 / n:.4f}%{{opacity:0}}}}",
           # Every frame is opacity:0 by default and the animation reveals one at a
           # time, so switching the animation off alone would leave a blank image.
           # Pin the first frame visible as well.
           "@media (prefers-reduced-motion: reduce){.fr{animation:none}#p0{opacity:1}}"]
    layers = []
    for i, data in enumerate(frames):
        css.append(f"#p{i}{{animation-delay:{-duration * i / n:.4f}s}}")
        layers.append(layer(i, data, ' class="fr"'))
    body = [f"<style>{chr(10).join(css)}</style>", clip, "\n".join(layers)]
    return "\n".join(head + body + ["</svg>\n"])


# --- build ------------------------------------------------------------------

def build(img, size=330, max_height=520, grid=120, frames=16, duration=2.8,
          motion="water", themes=("dark", "light"), inks=None, radius=14,
          invert=False):
    """Returns {theme: svg text}. Pure: same inputs, same bytes, every time."""
    if motion == "none":
        frames = 1
    inks = inks or {"dark": DEFAULTS["ink_dark"], "light": DEFAULTS["ink_light"]}
    img = ImageOps.exif_transpose(img).convert("L")

    # Fit the box to the photo rather than cropping the photo to a fixed box, so a
    # head-and-shoulders avatar and a full-length shot both sit properly.
    box_h = min(max_height, round(size * img.height / img.width))
    box_w = round(box_h * img.width / img.height)
    if box_w > size:
        box_w, box_h = size, round(size * img.height / img.width)

    grid_h = max(1, round(grid * box_h / box_w))
    small = img.resize((grid, grid_h), Image.LANCZOS)
    px = [[small.getpixel((x, y)) for x in range(grid)] for y in range(grid_h)]

    encoded = {name: [] for name in themes}
    for i in range(frames):
        field = displacement(motion, grid, grid_h, i, frames)
        shaken = [[px[y][x] + field[y][x] for x in range(grid)] for y in range(grid_h)]
        bits = dither(shaken, grid, grid_h)
        for name in themes:
            bit = 1 - POLARITY[name] if invert else POLARITY[name]
            encoded[name].append(encode(bits, grid, grid_h, bit, inks[name]))

    return {name: svg(encoded[name], box_w, box_h, duration, radius) for name in themes}


# --- cli --------------------------------------------------------------------

def env_default(name, fallback):
    """Composite GitHub Actions do not expose inputs as INPUT_* the way JS actions do,
    so action.yml passes them as DITHER_* env vars and they land here."""
    value = os.environ.get(name, "").strip()
    return value if value else fallback


def parse_args(argv=None):
    d = DEFAULTS
    p = argparse.ArgumentParser(description="Animated dithered portrait for a README.")
    p.add_argument("--photo", default=env_default("DITHER_PHOTO", None))
    p.add_argument("--username", default=env_default("DITHER_USERNAME", None))
    p.add_argument("--out-dir", default=env_default("DITHER_OUT_DIR", d["out_dir"]))
    p.add_argument("--prefix", default=env_default("DITHER_PREFIX", d["prefix"]))
    p.add_argument("--size", type=int, default=int(env_default("DITHER_SIZE", d["size"])))
    p.add_argument("--max-height", type=int,
                   default=int(env_default("DITHER_MAX_HEIGHT", d["max_height"])))
    p.add_argument("--grid", type=int, default=int(env_default("DITHER_GRID", d["grid"])))
    p.add_argument("--frames", type=int,
                   default=int(env_default("DITHER_FRAMES", d["frames"])))
    p.add_argument("--duration", type=float,
                   default=float(env_default("DITHER_DURATION", d["duration"])))
    p.add_argument("--motion", default=env_default("DITHER_MOTION", d["motion"]),
                   choices=["water", "shimmer", "none"])
    p.add_argument("--themes", default=env_default("DITHER_THEMES", d["themes"]))
    p.add_argument("--ink-dark", default=env_default("DITHER_INK_DARK", d["ink_dark"]))
    p.add_argument("--ink-light", default=env_default("DITHER_INK_LIGHT", d["ink_light"]))
    p.add_argument("--radius", type=int,
                   default=int(env_default("DITHER_RADIUS", d["radius"])))
    p.add_argument("--invert", action="store_true",
                   default=env_default("DITHER_INVERT", "").lower() in ("1", "true", "yes"),
                   help="swap which tones become ink; try it if the result looks solid")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    check_waves()

    themes = tuple(t.strip() for t in args.themes.split(",") if t.strip())
    unknown = [t for t in themes if t not in POLARITY]
    if unknown:
        raise SystemExit(f"unknown theme(s) {unknown}; use dark and/or light")

    svgs = build(
        load_source(args.photo, args.username),
        size=args.size, max_height=args.max_height, grid=args.grid,
        frames=args.frames, duration=args.duration, motion=args.motion,
        themes=themes, radius=args.radius, invert=args.invert,
        inks={"dark": args.ink_dark, "light": args.ink_light},
    )

    os.makedirs(args.out_dir, exist_ok=True)
    written = []
    for name, text in svgs.items():
        path = os.path.join(args.out_dir, f"{args.prefix}-{name}.svg")
        with open(path, "w") as f:
            f.write(text)
        kb = os.path.getsize(path) / 1024
        written.append(path)
        print(f"wrote {path} ({kb:.0f} KB)")
        if kb > 150:
            print(f"  warning: {kb:.0f} KB is heavy for a README image. Lower --grid "
                  f"or --frames.", file=sys.stderr)

    # so a workflow can reference the files it produced
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"files={' '.join(written)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
