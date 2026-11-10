# Cutest dog — make.fun `cutest-dog-01` entry

`main.py` draws a chibi puppy from scratch and writes it as a 768×768 PNG to
`/output/entry.png`. Python 3.13, standard library only, no input files.

A fluffy golden puppy sits in a sunlit meadow, raising one paw (with pink toe
beans) in a little wave to a butterfly that has come to visit. A small heart floats
between them. It has a big tilted head, huge layered glossy eyes with a lower-lid
glint, small sweet eyebrows, scalloped cheek and chest fluff, floppy ears, rosy
cheeks, a tiny tongue, cream paw tips, a red collar with a gold heart tag, and a
wagging tail. Behind it are pastel hills, a few daisies and soft bokeh.

## How it works
- Every part is a signed-distance shape (ellipses, strokes, polygons, hearts),
  merged with smooth-min unions for soft, rounded silhouettes. A `fluffy` modifier
  scallops chosen edges into rounded fur bumps.
- Anti-aliasing, the inner outline and rim shading all come from the distance value,
  so no supersampling is needed. It renders in a few seconds.
- A minimal PNG encoder (`zlib` + `struct`) writes the file. There is no randomness and
  no timestamp, so every run writes identical bytes.

## Run
```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python main.py   # writes out/entry.png
```
Without `MAKEFUN_OUTPUT_DIR` it writes to `/output/entry.png`.
