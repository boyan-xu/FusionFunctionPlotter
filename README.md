# Fusion Function Plotter

An Autodesk Fusion add-in for plotting functions in the active sketch. Current version: **1.0.1 (English)**.

- Cartesian, parametric, polar, and Python `curve(t)` inputs.
- Equal arc-length sampling with configurable spacing and accuracy.
- Live point count; more than 200 points warns without blocking generation.
- Line Segments or Fit Point Spline, with cancellation and cleanup.

Download this repository using **Code > Download ZIP**, extract it, and select the inner **FusionFunctionPlotter** folder in **Scripts and Add-Ins > Script or add-in from device**. Enable **Run**, edit your sketch, then open **Sketch > Create > Function Plotter**.

See [installation, examples, and verification details](FusionFunctionPlotter/README.md). Windows checks passed; Mac has not been tested. The English release passed all 23 automated checks; its UI has not yet been rechecked in Fusion.
