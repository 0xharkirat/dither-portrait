# dither-portrait

<a href="https://0xharkirat.github.io/dither-portrait/">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/example-dark.svg">
    <img alt="An animated dithered portrait, its grain rippling while the face stays still" src="docs/example-light.svg" width="300">
  </picture>
</a>

[![test](https://github.com/0xharkirat/dither-portrait/actions/workflows/test.yml/badge.svg)](https://github.com/0xharkirat/dither-portrait/actions/workflows/test.yml)

Turn a photo into an animated dithered SVG for your GitHub profile README.

[Try it on your own photo](https://0xharkirat.github.io/dither-portrait/) without
installing anything.

## Table of contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Inputs](#inputs)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Background

A 1-bit Floyd-Steinberg dither, with the grain animated by a field of slow travelling
waves. The picture never moves. Only the dots sitting near the dither threshold flip,
so it reads as a surface rather than as static.

Light and dark variants are generated with opposite polarity, the background is
transparent, and the animation stops for anyone whose system asks for reduced motion.

Output is deterministic, so a scheduled run commits nothing unless the photo changed.

## Install

No installation. Reference the action from a workflow:

```yaml
- uses: 0xharkirat/dither-portrait@v1
```

To run it locally, install [Pillow](https://pypi.org/project/pillow/):

```bash
pip install pillow
```

## Usage

The quickest route is the
[playground](https://0xharkirat.github.io/dither-portrait/): enter your username and
press **Add workflow to my profile**. GitHub opens with the file already filled in, so
you only have to commit it. Committing also runs it once.

To do it by hand, add this workflow. Committing it runs it once, and it rebuilds
monthly in case the avatar changes:

```yaml
name: portrait
on:
  push:
    paths: [.github/workflows/portrait.yml]
  workflow_dispatch:
  schedule:
    - cron: "0 4 1 * *"

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
          git commit -m "chore: refresh portrait" || echo "No change"
          git push
```

Then embed the result in your README:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="portrait-dark.svg">
  <img alt="portrait" src="portrait-light.svg" width="330">
</picture>
```

The commit step is yours rather than built in, so you can send the files to a branch,
an artifact, or nowhere at all.

### CLI

```bash
python portrait.py --username octocat
python portrait.py --photo me.jpg --motion shimmer --frames 12
```

## Inputs

Every input is optional.

| Input | Default | Description |
| --- | --- | --- |
| `username` | repository owner | GitHub user whose avatar to dither |
| `photo` | | Path to a local image. Overrides `username` |
| `out-dir` | `.` | Directory to write into |
| `prefix` | `portrait` | Output is `<prefix>-dark.svg` and `<prefix>-light.svg` |
| `themes` | `dark,light` | Which variants to emit |
| `size` | `330` | Rendered width in pixels |
| `max-height` | `520` | Cap on rendered height, for tall photos |
| `grid` | `120` | Dither cells across. The main size lever |
| `frames` | `16` | Animation frames. More is smoother and larger |
| `duration` | `2.8` | Seconds per loop |
| `motion` | `water` | `water`, `shimmer`, or `none` |
| `ink-dark` | `#c9d1d9` | Ink color on the dark variant |
| `ink-light` | `#24292f` | Ink color on the light variant |
| `radius` | `14` | Corner radius in pixels |
| `invert` | `false` | Swap which tones become ink |

Output `files` lists the paths written.

## Documentation

- [Choose a photo that dithers well](docs/choosing-a-photo.md) covers what to feed it
  and what to change when the result looks wrong.
- [How it works](docs/how-it-works.md) explains the constraints behind the design.
- The [playground](https://0xharkirat.github.io/dither-portrait/) dithers a photo in
  your browser and gives you the matching workflow. Nothing is uploaded.
- The [gallery](https://0xharkirat.github.io/dither-portrait/gallery.html) shows the
  defaults across 19 real avatars.

## Contributing

Open an issue for a question or a bug. Pull requests are welcome.

Run the tests before opening one:

```bash
python -m unittest discover -s tests -v
```

Any change must keep the output deterministic. The test suite and CI both enforce it.

## License

MIT © Harkirat Singh
