"""Pure standard-library arc-length sampling. Coordinates and tolerances are mm."""
from __future__ import annotations

import ast
import bisect
from dataclasses import dataclass
import math
from typing import Callable


class CurveError(ValueError):
    pass


class Cancelled(Exception):
    pass


FUNCTIONS = {name: getattr(math, name) for name in (
    'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'atan2', 'sinh', 'cosh',
    'tanh', 'sqrt', 'exp', 'log', 'log10', 'log2', 'hypot', 'fabs',
    'floor', 'ceil')}
FUNCTIONS.update(abs=abs, min=min, max=max, pow=pow)
CONSTANTS = {'pi': math.pi, 'e': math.e, 'tau': math.tau}
SCALES = {'mm': 1.0, 'cm': 10.0, 'in': 25.4}


def expression(text: str, variable: str = '') -> Callable:
    text = text.strip().replace('θ', 'theta').replace('π', 'pi').replace('^', '**')
    if '=' in text:
        lhs, text = text.split('=', 1)
        if lhs.strip() not in ('y', 'r', 'x(t)', 'y(t)', 'r(theta)'):
            raise CurveError('The expression left side must be y, r, x(t), y(t), or r(theta).')
    try:
        tree = ast.parse(text.strip(), mode='eval')
    except (SyntaxError, ValueError) as exc:
        raise CurveError('Expression syntax error: ' + str(exc)) from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 512:
        raise CurveError('The expression is too complex. Simplify it.')
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
               ast.Load, ast.Call, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
               ast.Mod, ast.UAdd, ast.USub)
    names = set(FUNCTIONS) | set(CONSTANTS) | ({variable} if variable else set())
    for node in nodes:
        if not isinstance(node, allowed):
            raise CurveError('Math modes support only numbers, variables, basic operators, and math functions.')
        if isinstance(node, ast.Constant) and (type(node.value) not in (int, float)):
            raise CurveError('Math expressions may contain only numeric constants.')
        if isinstance(node, ast.Name) and node.id not in names:
            raise CurveError('Unknown name: ' + node.id)
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords
        ):
            raise CurveError('Only direct calls to supported math functions are allowed.')
    compiled = compile(tree, '<formula>', 'eval')
    env = dict(FUNCTIONS, **CONSTANTS)

    def calculate(value=0.0):
        local = dict(env)
        if variable:
            local[variable] = value
        try:
            number = eval(compiled, {'__builtins__': {}}, local)
            if isinstance(number, bool) or not isinstance(number, (int, float)):
                raise ValueError('The result must be a real number.')
            number = float(number)
            if not math.isfinite(number):
                raise ValueError('The result must be a finite real number.')
            return number
        except Exception as exc:
            raise CurveError(f'Expression failed at {variable or "input"}={value:.12g} with error: {exc}') from exc
    return calculate


def scalar(text):
    return expression(text)()


@dataclass(frozen=True)
class Settings:
    mode: str = 'cartesian'
    first: str = '10*sin(x)'
    second: str = ''
    code: str = ''
    start: float = 0.0
    end: float = 10.0
    unit: str = 'mm'
    spacing_mm: float = 1.0
    accuracy_mm: float = 0.001

    def validate(self):
        if self.unit not in SCALES:
            raise CurveError('The unit must be mm, cm, or in.')
        if self.mode not in ('cartesian', 'parametric', 'polar', 'python'):
            raise CurveError('Unknown function type.')
        if not all(math.isfinite(x) for x in (self.start, self.end, self.spacing_mm, self.accuracy_mm)):
            raise CurveError('Range, spacing, and accuracy must be finite numbers.')
        if self.end <= self.start:
            raise CurveError('Range End must be greater than Range Start.')
        if self.spacing_mm <= 0 or self.accuracy_mm <= 0:
            raise CurveError('Arc-length spacing and accuracy must be greater than zero.')
        if self.accuracy_mm >= self.spacing_mm / 10:
            raise CurveError('Accuracy must be less than one tenth of the arc-length spacing.')

    def length_key(self):
        return (self.mode, self.first, self.second, self.code, self.start,
                self.end, self.unit, self.accuracy_mm)


def build_curve(cfg: Settings):
    cfg.validate()
    scale = SCALES[cfg.unit]
    if cfg.mode == 'cartesian':
        fn = expression(cfg.first, 'x')
        raw = lambda t: (t, fn(t))
    elif cfg.mode == 'parametric':
        fx, fy = expression(cfg.first, 't'), expression(cfg.second, 't')
        raw = lambda t: (fx(t), fy(t))
    elif cfg.mode == 'polar':
        fr = expression(cfg.first, 'theta')
        def raw(t):
            r = fr(t)
            return r * math.cos(t), r * math.sin(t)
    else:
        env = dict(FUNCTIONS, **CONSTANTS, math=math)
        try:
            exec(compile(cfg.code, '<curve.py>', 'exec'), env, env)
        except Exception as exc:
            raise CurveError('Python code error: ' + str(exc)) from exc
        raw = env.get('curve')
        if not callable(raw):
            raise CurveError('Python mode must define def curve(t) returning (x, y).')

    def point(t):
        try:
            values = raw(t)
            if not isinstance(values, (tuple, list)) or len(values) != 2:
                raise ValueError('curve(t) must return two coordinates (x, y).')
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
                raise ValueError('Coordinates must be real numbers.')
            x, y = (float(v) * scale for v in values)
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError('Coordinates must be finite real numbers.')
            return x, y
        except CurveError:
            raise
        except Exception as exc:
            raise CurveError(f'Curve failed at parameter={t:.12g} with error: {exc}') from exc
    return point


def warning_text(count):
    return f'Currently {count:,} points. Generation may be slow.' if count > 200 else ''


def check_cancel(cancel):
    if cancel():
        raise Cancelled()


class ArcLength:
    """A reusable speed-integral table. No Fusion API calls occur here."""
    def __init__(self, cfg, cancel=lambda: False):
        cfg.validate()
        self.cfg = cfg
        self.curve = build_curve(cfg)
        self.cancel = cancel
        self.leaves = []
        self.ends = []
        self.cumulative = []
        self._speed_cache = {}
        self.first = self.point(0.0)
        self.last = self.point(1.0)
        # 32 initial panels reduce adaptive-quadrature aliasing. These panels
        # are integration work, never the user's output sampling grid.
        for i in range(32):
            a, b = i / 32, (i + 1) / 32
            self.integrate(a, b, cfg.accuracy_mm * 0.04 / 32, record=True)
        self.total_mm = math.fsum(leaf[2] for leaf in self.leaves)
        if self.total_mm <= cfg.accuracy_mm:
            raise CurveError('The curve length is zero or below the calculation accuracy.')
        cumulative = 0.0
        for a, b, length in self.leaves:
            cumulative = math.fsum((cumulative, length))
            self.ends.append(b)
            self.cumulative.append(cumulative)
        # Close only a genuine coincident seam, not arbitrary nearby ends.
        self.closed = math.dist(self.first, self.last) <= max(1e-9, cfg.accuracy_mm * 0.001)
        self.count = self.count_for(cfg.spacing_mm)

    def point(self, u):
        check_cancel(self.cancel)
        return self.curve(self.cfg.start + (self.cfg.end - self.cfg.start) * u)

    def _derivative(self, u, h):
        if u < 2*h:
            weights, offsets = (-25, 48, -36, 16, -3), (0, 1, 2, 3, 4)
        elif u > 1-2*h:
            weights, offsets = (25, -48, 36, -16, 3), (0, -1, -2, -3, -4)
        else:
            weights, offsets = (1, -8, 8, -1), (-2, -1, 1, 2)
        pts = [self.point(u + offset*h) for offset in offsets]
        # Subtract a reference point to avoid cancellation under translation.
        origin = pts[0]
        return tuple(math.fsum(w*(p[k]-origin[k]) for w, p in zip(weights, pts))/(12*h)
                     for k in (0, 1))

    def speed(self, u):
        check_cancel(self.cancel)
        if u in self._speed_cache:
            return self._speed_cache[u]
        # Avoid a decimal step systematically landing on whole periods of a
        # trigonometric curve before derivative refinement even begins.
        h = math.sqrt(2) * 0.001
        coarse = self._derivative(u, h)
        for _ in range(12):
            h /= 2
            fine = self._derivative(u, h)
            error = math.dist(coarse, fine) / 15
            norm = math.hypot(*fine)
            if error <= self.cfg.accuracy_mm * 0.0002 + norm * 1e-10:
                value = math.hypot(*(f + (f-c)/15 for f, c in zip(fine, coarse)))
                self._speed_cache[u] = value
                return value
            coarse = fine
        raise CurveError(f'Parameter={self.cfg.start+(self.cfg.end-self.cfg.start)*u:.12g} has a derivative that does not converge. Split the range or adjust the accuracy.')

    def integrate(self, a, b, tol, record=False):
        fa, fb, fm = self.speed(a), self.speed(b), self.speed((a+b)/2)
        whole = (b-a)*(fa+4*fm+fb)/6

        def refine(lo, hi, f0, f1, fc, estimate, budget, depth):
            check_cancel(self.cancel)
            mid = (lo+hi)/2
            fl, fr = self.speed((lo+mid)/2), self.speed((mid+hi)/2)
            left = (mid-lo)*(f0+4*fl+fc)/6
            right = (hi-mid)*(fc+4*fr+f1)/6
            delta = left+right-estimate
            if abs(delta) <= 15*budget:
                length = max(0.0, left+right+delta/15)
                if record:
                    self.leaves.append((lo, hi, length))
                return length
            if depth >= 22 or mid == lo or mid == hi:
                raise CurveError('Arc-length integration did not converge. Reduce or split the range, or adjust the accuracy.')
            return math.fsum((refine(lo, mid, f0, fc, fl, left, budget/2, depth+1),
                              refine(mid, hi, fc, f1, fr, right, budget/2, depth+1)))
        return refine(a, b, fa, fb, fm, whole, tol, 0)

    def _interior_count(self, spacing):
        # A grid point within the error budget of the endpoint is replaced by
        # that endpoint, never emitted twice. Use this policy for UI and output.
        ratio = self.total_mm/spacing
        if not math.isfinite(ratio):
            raise CurveError('Spacing is too small to represent the point count as a floating-point number.')
        n = math.floor(ratio)
        if n > 0 and abs(n*spacing-self.total_mm) <= self.cfg.accuracy_mm * 0.1:
            n -= 1
        return max(0, n)

    def count_for(self, spacing):
        if not math.isfinite(spacing) or spacing <= 0 or self.cfg.accuracy_mm >= spacing/10:
            raise CurveError('Spacing must be positive and greater than ten times the calculation accuracy.')
        return self._interior_count(spacing) + (1 if self.closed else 2)

    def at_length(self, length):
        idx = min(bisect.bisect_left(self.cumulative, length), len(self.leaves)-1)
        a, b, _ = self.leaves[idx]
        before = self.cumulative[idx-1] if idx else 0.0
        target = length-before
        lo, hi = a, b
        for _ in range(64):
            mid = (lo+hi)/2
            measured = self.integrate(a, mid, self.cfg.accuracy_mm * 0.02)
            if abs(measured-target) <= self.cfg.accuracy_mm * 0.1:
                return self.point(mid)
            if measured < target:
                lo = mid
            else:
                hi = mid
        raise CurveError('Arc-length inversion could not reach the calculation accuracy.')

    def sample(self, spacing, cancel=lambda: False, progress=lambda done, total: None):
        count = self.count_for(spacing)
        original_cancel = self.cancel
        self.cancel = lambda: cancel() or original_cancel()
        try:
            points = [self.first]
            progress(1, count)
            for k in range(1, self._interior_count(spacing)+1):
                check_cancel(self.cancel)
                points.append(self.at_length(k*spacing))
                progress(len(points), count)
            if not self.closed:
                points.append(self.last)
            if len(points) < (3 if self.closed else 2):
                raise CurveError('Too few sample points to create a curve. Reduce the arc-length spacing.')
            for a, b in zip(points, points[1:]):
                if math.dist(a, b) <= 1e-9:
                    raise CurveError('Adjacent sample positions coincide. Reduce spacing or split the range.')
            progress(count, count)
            return points
        finally:
            self.cancel = original_cancel


def analyze(cfg, cancel=lambda: False):
    return ArcLength(cfg, cancel)
