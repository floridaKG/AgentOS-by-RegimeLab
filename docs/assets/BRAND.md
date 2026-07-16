# Brand — display only (not shipped)

## Policy

**Regime Lab name and Mandelbrot mark are trademarks / brand assets.**

They are **not** licensed under Apache 2.0 with this repository. This repo does
**not** ship logo binary files for redistribution.

| Allowed | Not allowed |
|---|---|
| Viewing the mark where we **display** it (README / architecture page via product CDN) | Treating logo files as open-source assets to rebrand your fork |
| Referring to the project as “Agent OS by Regime Lab” in accurate attribution | Implying endorsement or official Regime Lab affiliation without permission |
| Using Apache 2.0 rights on **code and docs** in this tree | Claiming trademark rights from the Apache license |

Apache License §6 does not grant trademark rights. Brand use beyond display
attribution requires separate permission from Regime Lab.

## Display-only image (hotlink)

README and the architecture poster load the mark from the **Regime Lab product
site** (not from this repository):

```
https://app.regime-lab.com/assets/regimelab-logo-transparent-C9fEkeux.png
```

- **Display only** — browsers fetch the image for rendering.
- The file is **not** part of the OSS tree and is **not** offered under Apache 2.0 here.
- Vite may change the hashed filename on product deploy; if the image breaks,
  update this URL to the current production asset (or a future stable brand path).

Small stable icon (48×48): `https://app.regime-lab.com/logo.png`

## Maintainer SSOT (private — not in this repo)

Canonical brand files live outside OSS (product app + vault brand folder).
Do not re-add full-resolution logo binaries to this public tree.

## Banned in-repo patterns

Do not commit:

- `regimelab-logo-*.png` / full-res fractal exports
- Old `mandelbrot-gold.svg` blob previews
- Any “source” SVG intended as the brand master
