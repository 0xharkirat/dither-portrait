/* Browser port of the dither core, for the playground preview.
 *
 * This mirrors portrait.py closely enough to judge a photo by, but it is a preview
 * rather than a second source of truth. Pillow downsamples with Lanczos and a canvas
 * does not, so the grain differs slightly from what the action commits. Everything
 * that decides whether a photo works at all - the threshold, the error diffusion, the
 * wave field - is identical.
 */
(function (global) {
  "use strict";

  var WAVES = [
    [12, 17, 1, 8, 0.0],
    [-14, 9, 1, 7, 1.7],
    [8, -21, 2, 5, 3.1],
    [19, 13, -1, 5, 5.0],
  ];

  var POLARITY = { dark: 1, light: 0 };

  /* Threshold displacement at loop position t (0..1). */
  function ripple(w, h, t) {
    var field = new Float32Array(w * h);
    for (var k = 0; k < WAVES.length; k++) {
      var lx = WAVES[k][0], ly = WAVES[k][1];
      var cycles = WAVES[k][2], amp = WAVES[k][3], phase = WAVES[k][4];
      for (var y = 0; y < h; y++) {
        for (var x = 0; x < w; x++) {
          field[y * w + x] +=
            amp * Math.sin(2 * Math.PI * (x / lx + y / ly - cycles * t) + phase);
        }
      }
    }
    return field;
  }

  /* Matches the Python hash exactly: Math.imul keeps the 32-bit multiply from losing
   * precision the way a plain * would once the value exceeds 2^53. */
  function hashNoise(x, y, i) {
    var n = (x * 374761393 + y * 668265263 + i * 1274126177) >>> 0;
    n = Math.imul(n ^ (n >>> 13), 1274126177) >>> 0;
    return ((n ^ (n >>> 16)) / 0xffffffff) * 2 - 1;
  }

  function shimmer(w, h, frame) {
    var field = new Float32Array(w * h);
    for (var y = 0; y < h; y++)
      for (var x = 0; x < w; x++) field[y * w + x] = hashNoise(x, y, frame) * 26;
    return field;
  }

  function displacement(mode, w, h, frame, frames) {
    if (mode === "water") return ripple(w, h, frame / frames);
    if (mode === "shimmer") return shimmer(w, h, frame);
    return new Float32Array(w * h);
  }

  /* Floyd-Steinberg, serpentine, 1 bit out. */
  function dither(buf, w, h) {
    var work = Float32Array.from(buf);
    var out = new Uint8Array(w * h);
    for (var y = 0; y < h; y++) {
      var forward = y % 2 === 0;
      var step = forward ? 1 : -1;
      for (var n = 0; n < w; n++) {
        var x = forward ? n : w - 1 - n;
        var old = work[y * w + x];
        var next = old > 128 ? 255 : 0;
        out[y * w + x] = next ? 1 : 0;
        var err = old - next;
        var spread = [[step, 0, 7], [-step, 1, 3], [0, 1, 5], [step, 1, 1]];
        for (var s = 0; s < 4; s++) {
          var nx = x + spread[s][0], ny = y + spread[s][1];
          if (nx >= 0 && nx < w && ny >= 0 && ny < h)
            work[ny * w + nx] += (err * spread[s][2]) / 16;
        }
      }
    }
    return out;
  }

  /* ITU-R 601-2 luma, the same weights Pillow uses for convert("L"). */
  function toGray(rgba, w, h) {
    var g = new Float32Array(w * h);
    for (var i = 0; i < w * h; i++) {
      g[i] = (rgba[i * 4] * 299 + rgba[i * 4 + 1] * 587 + rgba[i * 4 + 2] * 114) / 1000;
    }
    return g;
  }

  /* Fit the box to the photo rather than cropping the photo to the box. */
  function fitBox(imgW, imgH, size, maxHeight) {
    var boxH = Math.min(maxHeight, Math.round((size * imgH) / imgW));
    var boxW = Math.round((boxH * imgW) / imgH);
    if (boxW > size) {
      boxW = size;
      boxH = Math.round((size * imgH) / imgW);
    }
    return { w: boxW, h: boxH };
  }

  /* Returns { frames: [Uint8Array], gridW, gridH, box }. */
  function build(image, opts) {
    var o = Object.assign(
      { size: 330, maxHeight: 520, grid: 120, frames: 16, motion: "water" },
      opts || {}
    );
    if (o.motion === "none") o.frames = 1;

    var box = fitBox(image.naturalWidth, image.naturalHeight, o.size, o.maxHeight);
    var gridW = o.grid;
    var gridH = Math.max(1, Math.round((o.grid * box.h) / box.w));

    var c = document.createElement("canvas");
    c.width = gridW;
    c.height = gridH;
    var ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(image, 0, 0, gridW, gridH);
    var gray = toGray(ctx.getImageData(0, 0, gridW, gridH).data, gridW, gridH);

    var frames = [];
    for (var i = 0; i < o.frames; i++) {
      var field = displacement(o.motion, gridW, gridH, i, o.frames);
      var shaken = new Float32Array(gridW * gridH);
      for (var p = 0; p < shaken.length; p++) shaken[p] = gray[p] + field[p];
      frames.push(dither(shaken, gridW, gridH));
    }
    return { frames: frames, gridW: gridW, gridH: gridH, box: box };
  }

  /* --- PNG writing --------------------------------------------------------
   * A canvas can only export RGBA, which is roughly 4 times the size of the 1-bit
   * indexed PNGs the action produces. Writing the PNG by hand keeps a downloaded
   * file the same weight as a committed one.
   */

  var CRC_TABLE = (function () {
    var t = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c >>> 0;
    }
    return t;
  })();

  function crc32(bytes) {
    var c = 0xffffffff;
    for (var i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  function chunk(type, data) {
    var out = new Uint8Array(12 + data.length);
    var dv = new DataView(out.buffer);
    dv.setUint32(0, data.length);
    for (var i = 0; i < 4; i++) out[4 + i] = type.charCodeAt(i);
    out.set(data, 8);
    var forCrc = out.subarray(4, 8 + data.length);
    dv.setUint32(8 + data.length, crc32(forCrc));
    return out;
  }

  function concat(parts) {
    var len = parts.reduce(function (a, p) { return a + p.length; }, 0);
    var out = new Uint8Array(len), at = 0;
    parts.forEach(function (p) { out.set(p, at); at += p.length; });
    return out;
  }

  async function deflate(bytes) {
    var cs = new CompressionStream("deflate");
    var stream = new Blob([bytes]).stream().pipeThrough(cs);
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }

  function hex(colour) {
    return [1, 3, 5].map(function (i) { return parseInt(colour.substr(i, 2), 16); });
  }

  /* 1-bit indexed PNG: `ink` is the bit that draws, the other index is transparent. */
  async function encodePng(bits, w, h, ink, colour) {
    var rowBytes = Math.ceil(w / 8);
    var raw = new Uint8Array((rowBytes + 1) * h);
    for (var y = 0; y < h; y++) {
      var base = y * (rowBytes + 1) + 1;          // leading 0 = filter type "none"
      for (var x = 0; x < w; x++) {
        if (bits[y * w + x]) raw[base + (x >> 3)] |= 0x80 >> (x & 7);
      }
    }
    var ihdr = new Uint8Array(13);
    var dv = new DataView(ihdr.buffer);
    dv.setUint32(0, w);
    dv.setUint32(4, h);
    ihdr[8] = 1;        // bit depth
    ihdr[9] = 3;        // colour type: indexed
    var rgb = hex(colour);
    var plte = new Uint8Array(6);
    plte.set(ink === 1 ? [0, 0, 0] : rgb, 0);
    plte.set(ink === 1 ? rgb : [0, 0, 0], 3);
    var trns = new Uint8Array(2);
    trns[ink === 1 ? 0 : 1] = 0;                  // the non-ink index is transparent
    trns[ink === 1 ? 1 : 0] = 255;

    var png = concat([
      new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]),
      chunk("IHDR", ihdr),
      chunk("PLTE", plte),
      chunk("tRNS", trns),
      chunk("IDAT", await deflate(raw)),
      chunk("IEND", new Uint8Array(0)),
    ]);
    var bin = "";
    for (var i = 0; i < png.length; i++) bin += String.fromCharCode(png[i]);
    return btoa(bin);
  }

  async function toSvg(result, theme, opts) {
    var o = Object.assign({ duration: 2.8, radius: 14, invert: false, ink: null }, opts);
    var ink = o.invert ? 1 - POLARITY[theme] : POLARITY[theme];
    var colour = o.ink || (theme === "dark" ? "#c9d1d9" : "#24292f");
    var w = result.box.w, h = result.box.h, n = result.frames.length;

    var encoded = [];
    for (var i = 0; i < n; i++) {
      encoded.push(await encodePng(result.frames[i], result.gridW, result.gridH, ink, colour));
    }

    var head =
      "<?xml version='1.0' encoding='UTF-8'?>\n" +
      '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + 'px" height="' + h +
      'px" viewBox="0 0 ' + w + " " + h + '">';
    var clip = '<clipPath id="r"><rect width="' + w + '" height="' + h +
      '" rx="' + o.radius + '"/></clipPath>';
    var layer = function (i, cls) {
      return '<image id="p' + i + '"' + cls + ' x="0" y="0" width="' + w +
        '" height="' + h + '" clip-path="url(#r)" href="data:image/png;base64,' +
        encoded[i] + '"/>';
    };

    if (n === 1) {
      return [head, "<style>image{image-rendering:pixelated}</style>", clip,
              layer(0, ""), "</svg>", ""].join("\n");
    }

    var css = [
      ".fr{opacity:0;animation:flick " + o.duration +
        "s steps(1,end) infinite;image-rendering:pixelated}",
      "@keyframes flick{0%{opacity:1}" + (100 / n).toFixed(4) + "%{opacity:0}}",
      "@media (prefers-reduced-motion: reduce){.fr{animation:none}#p0{opacity:1}}",
    ];
    var layers = [];
    for (var j = 0; j < n; j++) {
      css.push("#p" + j + "{animation-delay:" + (-o.duration * j / n).toFixed(4) + "s}");
      layers.push(layer(j, ' class="fr"'));
    }
    return [head, "<style>" + css.join("\n") + "</style>", clip,
            layers.join("\n"), "</svg>", ""].join("\n");
  }

  global.Dither = { build: build, toSvg: toSvg, POLARITY: POLARITY };
})(window);
