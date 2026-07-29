# Choose a photo that dithers well

This guide shows you how to pick a source image, and what to change when the result
looks wrong.

A 1-bit dither has 2 tones and nothing else, so the result depends on tonal
separation rather than on resolution. Raising `grid` does not rescue a photo that
lacks it.

## Pick the source

A sweep over 19 well-known GitHub avatars produced these patterns. See the
[gallery](https://0xharkirat.github.io/dither-portrait/gallery.html) for the rendered results.

Prefer, in order:

1. A dark background with a lit face. These look like the portrait was made for the
   medium.
2. Any subject carrying its own light and dark structure, even on a bright
   background. Hair, a beard, glasses, and clothing all give the dither edges to
   hold on to.
3. A flat graphic or logo. High contrast dithers cleanly, though large flat areas
   become solid blocks.

Avoid an evenly lit face on a mid-grey studio backdrop. Subject and background land
on the same side of the threshold, and the result reads as mush. A busy background
does the same thing.

## Fix a result that looks like a solid block

The dark variant inks the bright tones. A photograph on a bright background can
therefore turn the background into ink and sink the subject into it.

Toggle it in the [playground](https://0xharkirat.github.io/dither-portrait/)
to compare, then set it in the workflow:

```yaml
- uses: 0xharkirat/dither-portrait@v1
  with:
    invert: true
```

Locally:

```bash
python portrait.py --username your-name --invert
```

Keep whichever reads better. `invert` is a switch rather than something the tool
decides, because auto-detection from background brightness was tested and rejected:
it improved some portraits and made others worse. A bright-background photograph
whose subject has strong dark structure still reads better under the default.

## Fix a result that looks like mush

Crop tighter before changing any setting. Removing background is worth more than any
parameter.

If cropping is not enough:

- Raise the contrast of the source image in any editor, then pass it with `photo`.
- Try `motion: shimmer`, which suits hard-edged subjects.
- Accept that some photographs do not dither well.

## Keep the file small

Output is roughly 40 KB per theme at the defaults. Size scales with `grid` squared
and with `frames`. Setting `grid: 200` and `frames: 24` lands near 170 KB per theme,
which is slow to load in a README. The tool prints a warning above 150 KB.

Lower `frames` before lowering `grid`. Motion survives a reduced frame count better
than detail survives a coarser grid.
