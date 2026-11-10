# Cutest dog — make.fun `cutest-dog-01` entry

`main.py` draws a chibi puppy from scratch and writes it as a 768×768 PNG to
`/output/entry.png`. Python 3.13, standard library only, no input files.

The puppy has a big tilted head, large glossy eyes set low with sparkle highlights,
floppy ears, rosy cheeks, a tiny tongue, a red collar with a gold heart tag, chubby
paws, a curled tail and its tennis ball, on a soft sky-blue background.

## How it works
- Every part is a signed-distance shape (ellipses, strokes, polygons, hearts),
  merged with smooth-min unions for soft, rounded silhouettes.
- Anti-aliasing, the inner outline and rim shading all come from the distance value,
  so no supersampling is needed. It renders in a few seconds.
- A minimal PNG encoder (`zlib` + `struct`) writes the file. There is no randomness and
  no timestamp, so every run writes identical bytes.

## Run
```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python main.py   # writes out/entry.png
```
Without `MAKEFUN_OUTPUT_DIR` it writes to `/output/entry.png`.
