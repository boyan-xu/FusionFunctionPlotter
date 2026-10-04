# Fusion Function Plotter

Plot a function in the sketch you are currently editing. Sample the original curve at equal arc-length intervals, then generate **Line Segments** or a **Fit Point Spline**.

## Install and open

1. Extract `FusionFunctionPlotter.zip` to a stable local location. Keep the entire `FusionFunctionPlotter` folder together.
2. In Fusion, open **Utilities > Add-Ins > Scripts and Add-Ins**.
3. Open the dropdown beside **+**, select **Script or add-in from device**, and choose the extracted **FusionFunctionPlotter folder**. Older versions have a **+** button on the **Add-Ins** tab.
4. Select **FusionFunctionPlotter** and enable **Run**. Older versions use a **Run** button. To load automatically whenever Fusion starts, enable **Run on Startup**.
5. Create or edit the target sketch. Select **Sketch > Create > Function Plotter**. An entry is also provided in the Utilities Add-Ins panel; if these panels are unavailable, the add-in uses the Design Create panel.
6. Enter the function and range, wait for **Live Statistics**, select **Curve Type**, and click **Generate in Current Sketch**.

Every generation adds new geometry and preserves existing sketch content. Fusion Undo can remove the result of one generation.

When updating an installed copy, close any Function Plotter dialog, turn **Run** off, replace the folder contents, then turn **Run** on again. If the old labels remain, restart Fusion to reload its Python modules. Remove the previous Chinese documentation file when replacing an older release; it is not used by the add-in.

## Function types

### Cartesian y=f(x)

Set **Expression 1** to `10*sin(x)` or `y=x^2`. The example range is `0` to `2*pi`. Both x and the calculated y use the selected coordinate unit; expressions operate on numeric values.

### Parametric x(t), y(t)

Set **Expression 1** to `20*cos(t)` and **Expression 2** to `10*sin(t)`. The range `0` to `2*pi` produces an ellipse.

### Polar r(theta)

Set **Expression 1** to `20*(1+0.3*cos(5*theta))`, with a range of `0` to `2*pi`. The variable may be written as `theta` or the Greek theta character. Radius uses the selected coordinate unit.

### Python curve(t)

Enter a function in the multiline editor:

```python
def curve(t):
    return (20*cos(t), 10*sin(t))
```

You can also use `math.sin(t)`, intermediate variables, and branches. Return two finite real numbers `(x, y)`. The environment includes `math`, common math functions, `pi`, `e`, and `tau`.

This mode executes local Python code. The function must be deterministic, have no side effects, and return promptly. Preview and differentiation call it repeatedly. Do not use the Fusion API, modify files, or access the network from the background function. A single Python call stuck in an infinite loop cannot be interrupted by the Cancel button.

Changing function type loads the expression and range example for that type. Existing code in the Python editor is retained.

## Arc-length spacing and live count

- **Arc-Length Spacing is always entered in mm**, regardless of Coordinate Unit. A value of `2` places a sample after each 2 mm along the original curve.
- Sampling does not use equal x or angle increments. The add-in numerically integrates curve speed, then solves for positions at the requested cumulative lengths.
- A 10.5 mm curve with 2 mm spacing is sampled at arc lengths `0, 2, 4, 6, 8, 10, 10.5 mm`. The endpoint is retained, so the last interval may be shorter.
- For closed curves, coincident start and end positions count as one sample point. The count describes the current function curve, not every existing point in the sketch.
- Statistics update about 300 ms after typing stops. **Calculating...** is shown while work is pending. Changing only spacing reuses the total-length calculation.
- **Up to 200 points: no warning. More than 200 points: a performance warning, with generation still allowed.** There is no fixed point-count limit or automatic reduction in density. Time and memory depend on the function and Fusion.
- Default Calculation Accuracy is 0.001 mm and must be less than one tenth of the spacing. This is a numerical error target, not an analytical proof or a guarantee about the final spline shape.

## Curve types and cancellation

- **Line Segments** connect the sample points. Closed curves include a final closing segment.
- **Fit Point Spline** creates an editable spline through the same sample points. Closed curves use a periodic closed spline.

Spacing refers to the **original function arc length**. Segment lengths are chord lengths and may be shorter; fitted spline arc length may also differ. Reduce spacing to capture more detail. The add-in does not create an additional set of standalone sketch-point markers.

Generation provides progress and cancellation. Cancellation or creation failure removes geometry added during the operation and preserves existing content. A single Fusion call that creates an entire spline must return before cancellation can take effect.

Coordinates use the active sketch local XY plane, including sketches on tilted planes.

## Expressions and errors

Math modes support `+ - * / ^ ** %` and functions including `sin cos tan asin acos atan atan2 sinh cosh tanh sqrt exp log log10 log2 hypot abs min max pow floor ceil`. Constants include `pi e tau`. `log` is the natural logarithm. Trigonometric functions use radians.

Range values must be finite, with Range End greater than Range Start. Range fields accept constants such as `pi` and math expressions. Curves should be continuous, piecewise smooth, and have finite length. Split ranges containing discontinuities, asymptotes, divergent endpoint derivatives, sharp corners, or very high frequencies. Nonconvergent differentiation, integration, or arc-length inversion produces an error instead of geometry.

Errors also identify insufficient points, coincident adjacent sample positions, invalid Python returns, missing sketch-edit mode, and Fusion creation failures. Large spacing may miss curve details; a point-count warning is independent of these errors.

## Platforms and verification

The add-in uses Fusion Python and the Python standard library. Its manifest supports Windows and Mac. Copy the whole folder to the other computer and register it locally; it does not automatically transfer with the Fusion account. Keep the linked folder in place so Fusion can find it after restarting.

The Windows version was verified on 2026-10-04 in **Fusion 2705.1.25**: standard Scripts and Add-Ins loading, sketch menus, statistics, 42-point splines, 201-point line and spline generation, and preservation of existing geometry.

Native Fusion API checks also passed for closed parametric and polar circles with 63 points, a Python curve with nonuniform parameter speed, centimeter conversion, 1001 points creating 1000 segments, local sketch XY coordinates on an XZ plane, and geometry cleanup after cancellation and injected failure. Real custom-event checks covered the 199/200/201 warning boundary, spacing-cache reuse, clearing stale results for invalid input, and keeping the latest result after rapid changes. Those event checks used API-set inputs and explicit scheduling; keyboard-driven updates were observed separately.

The 23 automated checks cover known-length lines and circles, parameter-speed changes, all four function types, endpoints and closed counts, 199/200/201/1201 points, caching, stale results, cancellation, and cleanup. They are rerun for the English release. These sample results do not prove numerical accuracy for every function.

Mac, arbitrary tilted-plane angles, and manually clicking Cancel during large-point generation remain untested. Native cancellation callbacks and failure cleanup were tested with real Fusion geometry. English-release UI verification is recorded separately in the project validation report.
