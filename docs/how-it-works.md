# How it works

An explanation of the constraints that shaped dither-portrait, for anyone deciding
whether to use it or wondering why it is built this way.

## Animating inside GitHub's sandbox

GitHub serves README images through `<img>`. That blocks scripts and external
fetches, but it does run CSS. So an SVG cannot fetch anything, cannot respond to a
click, and cannot contain a working link.

What it can do is animate. Each frame is a 1-bit PNG embedded as a `data:` URI, and a
CSS keyframe cycles them. Every frame sits at `opacity: 0`, and a staggered negative
`animation-delay` reveals exactly 1 at a time.

The cut is hard, using `steps(1, end)`. Crossfading 2 dithers blends them into grey
and loses the point of a 1-bit image.

## Why the grain moves and the picture does not

The animation displaces the dither threshold, not the photo. Cells sitting near the
threshold flip between frames; deep blacks and bright highlights never move. The
result reads as a surface with something moving across it.

The `water` mode uses 4 sine waves. 2 travel one way and 1 comes back against them,
and that interference is what makes it read as a surface. Wavelengths are deliberately
not multiples of each other, because crests that line up read as corduroy.

Each wave completes a whole number of cycles per loop. A fractional count makes the
last frame jump back to the first, so the build fails rather than shipping a visible
seam.

`shimmer` replaces the waves with independent per-cell jitter. It looks like
television static, and slowing it down turns it into a strobe rather than calming it.
It suits hard-edged graphics where coherent ripples read as a wobble.

## Reduced motion

The animation stops for anyone whose system asks for reduced motion.

Stopping the animation alone would leave a blank image, because every frame defaults
to `opacity: 0` and only the animation reveals one. The rule therefore pins the 1st
frame visible as well:

```css
@media (prefers-reduced-motion: reduce) {
  .fr { animation: none }
  #p0 { opacity: 1 }
}
```

An `<img>`-loaded SVG is an isolated document, so DevTools media emulation does not
always reach inside it. To check the behavior, set the system-level preference and
reload.

## Determinism

The same photo and settings always produce byte-identical output.

This is a hard constraint rather than a nice property. A scheduled workflow that
produced different bytes on every run would commit a change every day for no reason.
Nothing in the pipeline uses a random number generator, the clock, or dictionary
iteration order. The `shimmer` mode uses a hash of the cell coordinates rather than a
seeded generator, because a hash cannot be knocked out of step by a reordering.

2 tests cover it, and the CI job runs the action twice and diffs the output.

## Transparency and theme polarity

Only the ink is drawn. The other tone is transparent, so the page color shows through
and the portrait has no rectangle around it.

The 2 variants use opposite polarity. The light variant is ink on paper, so shadows
become the ink. The dark variant is light on a screen, so the lit parts of the face
glow. Mapping both the same way renders a face as a solid pale blob on one of them.

Whether that default suits a given photograph depends on the subject rather than the
background. See [Choosing a photo](choosing-a-photo.md).

## Prior art

Dithering is not new, and neither is putting generated SVG in a profile README.
[Dithering Studio](https://ditheringstudio.com) is a good place to explore the
parameters by hand. This project packages 1 treatment, animated and sized for a
README.
