# dither-portrait

Turn a photo into an animated dithered SVG for your GitHub profile README.

One-bit Floyd-Steinberg dither, with the grain animated by a field of slow travelling
waves. The picture never moves; only the dots that sit near the dither threshold flip,
so it reads as a surface rather than as static.

Light and dark variants are generated with opposite polarity, the background is
transparent, and the animation stops for anyone who has asked their system to reduce
motion.

## Use it

```yaml
name: portrait
on:
  workflow_dispatch:
  schedule:
    - cron: "0 4 * * 0"      # weekly is plenty; the output only changes when you do

permissions:
  contents: write

jobs:
  portrait:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: 0xharkirat/dither-portrait@v1
        with:
          username: ${{ github.repository_owner }}

      - name: Commit if it changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add portrait-dark.svg portrait-light.svg
          git commit -m "chore: refresh portrait" || echo "no change"
          git push
```

Then put it in your README:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="portrait-dark.svg">
  <img alt="portrait" src="portrait-light.svg" width="330">
</picture>
```

The commit step is deliberately yours rather than built in, so you can send the files
to a branch, an artifact, or nowhere at all.

## Locally

```bash
pip install pillow
python portrait.py --username octocat
python portrait.py --photo me.jpg --motion shimmer --frames 12
```

## Inputs

| input | default | what it does |
| --- | --- | --- |
| `username` | repo owner | whose GitHub avatar to dither |
| `photo` | | a local image; overrides `username` |
| `out-dir` | `.` | where to write |
| `prefix` | `portrait` | output is `<prefix>-dark.svg`, `<prefix>-light.svg` |
| `themes` | `dark,light` | emit one or both |
| `size` | `330` | rendered width in px |
| `max-height` | `520` | cap for tall photos |
| `grid` | `120` | dither cells across; the main size lever |
| `frames` | `16` | more is smoother and bigger |
| `duration` | `2.8` | seconds per loop |
| `motion` | `water` | `water`, `shimmer`, or `none` |
| `ink-dark` | `#c9d1d9` | ink colour on the dark variant |
| `ink-light` | `#24292f` | ink colour on the light variant |
| `radius` | `14` | corner radius in px |
| `invert` | `false` | swap which tones become ink |

Output `files` lists the paths written.

## Motion

**`water`** is the default. Four sine waves displace the dither threshold, two
travelling one way and one against them. The interference is what makes it read as a
surface. Independent per-cell noise looks like television static, and slowing that
down turns it into a strobe rather than calming it.

**`shimmer`** is that per-cell jitter, kept because it suits hard-edged graphics where
ripples read as a wobble.

**`none`** emits a single static frame.

## What photographs well

The dither has two tones and nothing else, so it lives or dies on separation. I ran
the defaults over 18 well-known GitHub avatars to find out where they hold up.

**Best:** a dark background with a lit face. Those come out looking like the portrait
was made for the medium.

**Usually fine:** any photo whose subject carries its own light and dark structure,
even on a bright background. Hair, beard, glasses, and clothing all give the dither
edges to hang on.

**Struggles:** an evenly lit face on a mid-grey studio backdrop. There is no tonal
edge between subject and background, so both land on the same side of the threshold
and the result reads as mush. A busy background does the same thing.

Roughly a third of the avatars I tested produced a solid block on the dark variant.
If yours does, set `invert: true` and compare. It is a switch rather than something
the tool decides, because I tried auto-detecting it from background brightness and it
made other portraits worse: a bright-background photo whose subject has strong dark
structure still reads better under the default.

Cropping tightly helps more than raising `grid`.

## File size

Roughly 40 KB per theme at the defaults. It scales with `grid` squared and with
`frames`, so `grid: 200` and `frames: 24` lands near 170 KB per theme, which is slow
in a README. The tool warns above 150 KB.

## How it works

GitHub serves README images through `<img>`, which blocks scripts and external
fetches but does run CSS. So each frame is a 1-bit PNG embedded as a `data:` URI, and
a CSS keyframe with `steps(1, end)` cycles them. Hard cuts, no crossfade, because
blending two dithers just makes grey.

Every frame is `opacity: 0` by default with the animation revealing one at a time,
which means disabling the animation alone would leave a blank image. The
reduced-motion rule pins the first frame visible as well.

## Determinism

The same photo and settings always produce byte-identical output. No random numbers,
no clock, no dependence on iteration order. That is what makes it safe on a schedule:
the workflow will not commit a change unless something actually changed. There is a
test for it, and the CI job runs the action twice and diffs the results.

## Prior art

The dithering idea is not new. [Dithering Studio](https://ditheringstudio.com) is a
good place to explore the parameters by hand. This packages one particular treatment,
animated and sized for a README.

## Licence

MIT. The code is mine; your photo is yours.
