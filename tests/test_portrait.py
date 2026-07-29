"""Tests for the dither pipeline.

The fixture is generated rather than committed, so there is no binary in the repo and
no real person's face in the test suite.

    python3 -m unittest discover -s tests -v
"""

import os
import re
import sys
import unittest
import xml.dom.minidom

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

import portrait  # noqa: E402


def fixture(w=200, h=200):
    """A synthetic head-and-shoulders shape with a soft tonal ramp, so the dither has
    real midtones to work with rather than a flat mask."""
    img = Image.new("L", (w, h), 235)
    d = ImageDraw.Draw(img)
    for i in range(60, 0, -1):                       # soft radial falloff for the head
        shade = int(40 + (60 - i) * 2.2)
        d.ellipse([w // 2 - i, h // 2 - i - 20, w // 2 + i, h // 2 + i - 20], fill=shade)
    d.ellipse([w // 2 - 90, h - 60, w // 2 + 90, h + 90], fill=70)   # shoulders
    d.ellipse([w // 2 - 26, h // 2 - 34, w // 2 - 12, h // 2 - 22], fill=20)  # eyes
    d.ellipse([w // 2 + 12, h // 2 - 34, w // 2 + 26, h // 2 - 22], fill=20)
    return img


class TestOutput(unittest.TestCase):
    def setUp(self):
        self.svgs = portrait.build(fixture(), grid=48, frames=6)

    def test_emits_both_themes(self):
        self.assertEqual(set(self.svgs), {"dark", "light"})

    def test_valid_xml(self):
        for name, text in self.svgs.items():
            with self.subTest(theme=name):
                xml.dom.minidom.parseString(text)

    def test_frame_count_matches_request(self):
        for name, text in self.svgs.items():
            with self.subTest(theme=name):
                self.assertEqual(len(re.findall(r'id="p\d+"', text)), 6)

    def test_respects_reduced_motion(self):
        """Every frame is opacity:0 with the animation revealing one at a time, so the
        rule has to pin a frame visible too. Without that it would render blank."""
        marker = "@media (prefers-reduced-motion: reduce)"
        for name, text in self.svgs.items():
            with self.subTest(theme=name):
                self.assertIn(marker, text)
                # brace-counting a regex over nested CSS is not worth it; the rule is
                # short, so assert on the text just after the marker
                block = text.split(marker, 1)[1][:120]
                self.assertIn("animation:none", block)
                self.assertRegex(block, r"#p0\{opacity:\s*1")

    def test_background_is_transparent(self):
        """Non-ink pixels must stay transparent so the page colour shows through."""
        for name, text in self.svgs.items():
            with self.subTest(theme=name):
                self.assertNotIn("<rect", text.split("<clipPath")[0])

    def test_themes_have_opposite_polarity(self):
        self.assertNotEqual(portrait.POLARITY["dark"], portrait.POLARITY["light"])

    def test_single_theme_when_asked(self):
        only = portrait.build(fixture(), grid=32, frames=4, themes=("dark",))
        self.assertEqual(set(only), {"dark"})


class TestDeterminism(unittest.TestCase):
    """The whole scheduled-Action model depends on this. If output varied run to run,
    the workflow would commit a change every day for no reason."""

    def test_identical_across_runs(self):
        a = portrait.build(fixture(), grid=48, frames=6)
        b = portrait.build(fixture(), grid=48, frames=6)
        for name in a:
            with self.subTest(theme=name):
                self.assertEqual(a[name], b[name])

    def test_shimmer_is_deterministic_too(self):
        a = portrait.build(fixture(), grid=32, frames=4, motion="shimmer")
        b = portrait.build(fixture(), grid=32, frames=4, motion="shimmer")
        self.assertEqual(a["dark"], b["dark"])

    def test_frames_actually_differ(self):
        """Determinism must not be achieved by accidentally emitting the same frame."""
        text = portrait.build(fixture(), grid=48, frames=6)["dark"]
        payloads = re.findall(r"base64,([^\"]+)", text)
        self.assertEqual(len(payloads), 6)
        self.assertGreater(len(set(payloads)), 4, "frames are barely changing")


class TestMotionModes(unittest.TestCase):
    def test_none_emits_one_static_frame(self):
        text = portrait.build(fixture(), grid=32, motion="none")["dark"]
        self.assertEqual(len(re.findall(r'id="p\d+"', text)), 1)
        self.assertNotIn("@keyframes", text)
        self.assertNotIn("prefers-reduced-motion", text)   # nothing moves, nothing to stop

    def test_unknown_motion_is_rejected(self):
        with self.assertRaises(SystemExit):
            portrait.build(fixture(), grid=16, motion="disco")


class TestWaveField(unittest.TestCase):
    def test_loop_closes(self):
        portrait.check_waves()

    def test_fractional_cycles_are_caught(self):
        with self.assertRaises(AssertionError):
            portrait.check_waves([(12, 17, 1.5, 8, 0.0)])


class TestSizeGuard(unittest.TestCase):
    def test_default_settings_stay_reasonable(self):
        """A README image people wait on is a bad README image."""
        text = portrait.build(fixture(400, 400), grid=120, frames=16)["dark"]
        self.assertLess(len(text) / 1024, 150, "output too heavy for a README")


if __name__ == "__main__":
    unittest.main()
