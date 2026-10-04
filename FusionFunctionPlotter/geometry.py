"""Main-thread-only Fusion geometry adapter; all input coordinates are mm."""
try:
    from .curve_engine import check_cancel, CurveError
except ImportError:
    from curve_engine import check_cancel, CurveError


def create_geometry(sketch, points, closed, kind, core,
                    cancel=lambda: False, progress=lambda done, total: None):
    if kind not in ('lines', 'spline'):
        raise CurveError('Unknown curve type.')
    if len(points) < (3 if closed else 2):
        raise CurveError('Too few points. Reduce the spacing.')
    created = []
    deferred = sketch.isComputeDeferred
    try:
        sketch.isComputeDeferred = True
        if kind == 'lines':
            total = len(points) if closed else len(points)-1
            for i in range(total):
                check_cancel(cancel)
                a, b = points[i], points[(i+1) % len(points)]
                entity = sketch.sketchCurves.sketchLines.addByTwoPoints(
                    core.Point3D.create(a[0]/10, a[1]/10, 0),
                    core.Point3D.create(b[0]/10, b[1]/10, 0))
                if entity is None:
                    raise CurveError('Fusion could not create a line segment.')
                created.append(entity)
                progress(i+1, total)
        else:
            collection = core.ObjectCollection.create()
            for i, (x, y) in enumerate(points):
                check_cancel(cancel)
                collection.add(core.Point3D.create(x/10, y/10, 0))
                progress(i+1, len(points)+1)
            check_cancel(cancel)
            entity = sketch.sketchCurves.sketchFittedSplines.add(collection)
            if entity is None:
                raise CurveError('Fusion could not create a Fit Point Spline.')
            created.append(entity)
            if closed:
                entity.isClosed = True
            progress(len(points)+1, len(points)+1)
        check_cancel(cancel)
        sketch.isComputeDeferred = deferred
        return created
    except Exception as original:
        failures = []
        for entity in reversed(created):
            try:
                if entity.isValid and not entity.deleteMe():
                    # Some API versions return None on successful deletion.
                    if entity.isValid:
                        failures.append('Failed to delete newly created geometry.')
            except Exception as exc:
                failures.append(str(exc))
        try:
            sketch.isComputeDeferred = deferred
        except Exception as exc:
            failures.append(str(exc))
        if failures:
            raise CurveError(f'{original}; cleanup was incomplete. Undo this operation: ' + '; '.join(failures)) from original
        raise
