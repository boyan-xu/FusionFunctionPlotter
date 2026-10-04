# Fusion Function Plotter

An Autodesk Fusion add-in for plotting functions in the active sketch. Current version: **1.0.1 (English)**.

- Cartesian, parametric, polar, and Python `curve(t)` inputs.
- Equal arc-length sampling with configurable spacing and accuracy.
- Live point count; more than 200 points warns without blocking generation.
- Line Segments or Fit Point Spline, with cancellation and cleanup.

## Direct download for AI assistants

Use these public HTTPS links with a download client that follows redirects. No GitHub sign-in or browser clicks are required.

- **Latest source ZIP:** https://github.com/boyan-xu/FusionFunctionPlotter/archive/refs/heads/main.zip
- **Fixed version 1.0.1 source ZIP:** https://github.com/boyan-xu/FusionFunctionPlotter/archive/85758f26b56a1de542b91de937f3d3636b7edbfb.zip
- **Plain-text instructions:** https://raw.githubusercontent.com/boyan-xu/FusionFunctionPlotter/main/README.md

The latest link tracks `main`; the fixed link selects the published 1.0.1 source commit. Extract the archive and locate the inner **FusionFunctionPlotter** folder containing `FusionFunctionPlotter.py`, `FusionFunctionPlotter.manifest`, `curve_engine.py`, `preview.py`, `geometry.py`, and `README.md`. Keep all six files together in a stable local folder. This is a Fusion add-in, so run it from Fusion rather than launching the Python entry point by itself.

Copy this request to an AI assistant with download and filesystem tools:

```text
Download the English Fusion Function Plotter 1.0.1 add-in from:
https://github.com/boyan-xu/FusionFunctionPlotter/archive/85758f26b56a1de542b91de937f3d3636b7edbfb.zip
Follow redirects, verify that it is a valid ZIP, and extract it into a stable local project folder. Locate the inner FusionFunctionPlotter folder and keep all six plugin files together. Tell me its actual saved path, then guide me through adding that folder in Fusion Scripts and Add-Ins. Preserve any existing installation when choosing the destination.
```

## Manual download and installation

You can still download this repository using **Code > Download ZIP**, extract it, and select the inner **FusionFunctionPlotter** folder in **Scripts and Add-Ins > Script or add-in from device**. Enable **Run**, edit your sketch, then open **Sketch > Create > Function Plotter**.

See [installation, examples, and verification details](FusionFunctionPlotter/README.md). Windows checks passed; Mac has not been tested. The English release passed all 23 automated checks; its UI has not yet been rechecked in Fusion.
