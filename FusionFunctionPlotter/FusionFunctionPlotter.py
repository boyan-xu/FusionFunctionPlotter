"""Fusion add-in entry point. All adsk geometry/UI access stays on main thread."""
import html
import queue
import threading
import time
import traceback
import uuid

import adsk.core
import adsk.fusion

try:
    from .curve_engine import Settings, scalar, warning_text, CurveError, Cancelled
    from .preview import PreviewController
    from .geometry import create_geometry
except ImportError:
    from curve_engine import Settings, scalar, warning_text, CurveError, Cancelled
    from preview import PreviewController
    from geometry import create_geometry


COMMAND_ID = 'HggstFusionFunctionPlotter'
EVENT_ID = 'HggstFusionFunctionPlotterPreview'
MODE_NAMES = ('Cartesian y=f(x)', 'Parametric x(t), y(t)', 'Polar r(theta)', 'Python curve(t)')
MODE_KEYS = ('cartesian', 'parametric', 'polar', 'python')
EXAMPLES = {
    'cartesian': ('10*sin(x)', '', '0', '2*pi'),
    'parametric': ('20*cos(t)', '10*sin(t)', '0', '2*pi'),
    'polar': ('20*(1+0.3*cos(5*theta))', '', '0', '2*pi'),
    'python': ('', '', '0', '2*pi'),
}
PYTHON_EXAMPLE = 'def curve(t):\n    # Coordinates use the selected unit; trigonometric functions use radians.\n    return (20*cos(t), 10*sin(t))'
_app = None
_handlers = []
_controls = []
_sessions = {}
_messages = queue.SimpleQueue()
_registered = False
_stopping = False


def bind(event, handler, keep):
    event.add(handler)
    keep.append(handler)


class Session:
    def __init__(self, command, sketch):
        self.id = uuid.uuid4().hex
        self.command = command
        self.sketch = sketch
        self.closed = False
        self.result = None
        self.handlers = []
        self.updating = False
        self._sample_cancel = None
        self._last_pump = 0
        self.app = _app
        self.controller = PreviewController(self.post)
        command.setDialogInitialSize(580, 760)
        command.okButtonText = 'Generate in Current Sketch'
        inputs = command.commandInputs
        mode = inputs.addDropDownCommandInput('mode', 'Function Type', adsk.core.DropDownStyles.TextListDropDownStyle)
        for i, name in enumerate(MODE_NAMES):
            mode.listItems.add(name, i == 0)
        self.hint = inputs.addTextBoxCommandInput('hint', '', '', 3, True)
        self.first = inputs.addStringValueInput('first', 'Expression 1', EXAMPLES['cartesian'][0])
        self.second = inputs.addStringValueInput('second', 'Expression 2', EXAMPLES['parametric'][1])
        self.code = inputs.addTextBoxCommandInput('code', 'Python Function', '', 9, False)
        self.code.text = PYTHON_EXAMPLE
        inputs.addStringValueInput('start', 'Range Start', '0')
        inputs.addStringValueInput('end', 'Range End', '2*pi')
        unit = inputs.addDropDownCommandInput('unit', 'Coordinate Unit', adsk.core.DropDownStyles.TextListDropDownStyle)
        for i, name in enumerate(('mm', 'cm', 'in')):
            unit.listItems.add(name, i == 0)
        inputs.addStringValueInput('spacing', 'Arc-Length Spacing (mm)', '1')
        inputs.addStringValueInput('accuracy', 'Calculation Accuracy (mm)', '0.001')
        self.info = inputs.addTextBoxCommandInput('info', 'Live Statistics', 'Calculating...', 3, True)
        self.warning = inputs.addTextBoxCommandInput('warning', '', '', 2, True)
        self.warning.isVisible = False
        kind = inputs.addDropDownCommandInput('kind', 'Curve Type', adsk.core.DropDownStyles.TextListDropDownStyle)
        kind.listItems.add('Line Segments', False)
        kind.listItems.add('Fit Point Spline', True)
        inputs.addTextBoxCommandInput('note', '',
            'The endpoint is retained; the last interval may be shorter. Closed endpoints count as one point.<br>'
            'Spacing follows the original curve arc length; segment and spline lengths may differ slightly.', 3, True)
        bind(command.inputChanged, Changed(self), self.handlers)
        bind(command.validateInputs, Validate(self), self.handlers)
        bind(command.execute, Execute(self), self.handlers)
        bind(command.destroy, Destroy(self), self.handlers)
        _sessions[self.id] = self
        self.display_mode('cartesian')
        self.schedule()

    def item(self, name):
        return self.command.commandInputs.itemById(name)

    def mode(self):
        return MODE_KEYS[MODE_NAMES.index(self.item('mode').selectedItem.name)]

    def display_mode(self, mode):
        self.first.isVisible = mode != 'python'
        self.second.isVisible = mode == 'parametric'
        self.code.isVisible = mode == 'python'
        hints = {
            'cartesian': 'Expression 1: y=f(x), e.g. 10*sin(x) or y=x^2. The range is x.',
            'parametric': 'Expression 1: x(t); Expression 2: y(t). The range is t.',
            'polar': 'Expression 1: r(theta). Use theta or θ; the range and trigonometric functions use radians.',
            'python': 'Define curve(t) returning (x, y); use deterministic numerical calculations only.<br>'
                      'This mode runs local Python. Preview calls it repeatedly; do not access the Fusion API or write files.',
        }
        self.hint.formattedText = hints[mode]

    def settings(self):
        cfg = Settings(mode=self.mode(), first=self.first.value, second=self.second.value,
                       code=self.code.text, start=scalar(self.item('start').value),
                       end=scalar(self.item('end').value), unit=self.item('unit').selectedItem.name,
                       spacing_mm=scalar(self.item('spacing').value),
                       accuracy_mm=scalar(self.item('accuracy').value))
        cfg.validate()
        return cfg

    def schedule(self):
        self.result = None
        self.warning.isVisible = False
        self.info.formattedText = 'Calculating... (updates after 300 ms without input)'
        try:
            cfg = self.settings()
            self.controller.request(cfg)
        except Exception as exc:
            self.controller.invalidate()
            self.info.formattedText = '<font color="#D94040">' + html.escape(str(exc)) + '</font>'

    def post(self, result):
        if self.closed or not self.controller.current(result.generation):
            return
        _messages.put((self.id, result))
        # Autodesk explicitly allows this particular API from a worker thread.
        self.app.fireCustomEvent(EVENT_ID, self.id)

    def accept(self, result):
        if self.closed or not self.command.isValid or not self.controller.current(result.generation):
            return
        self.result = result
        self.warning.isVisible = False
        if result.error:
            self.info.formattedText = '<font color="#D94040">' + html.escape(result.error) + '</font>'
            return
        self.info.formattedText = (
            f'Original Curve Length: {result.table.total_mm:.9g} mm<br>'
            f'<b>Sample Points: {result.count:,}</b>'
            + (' (closed; endpoints counted once)' if result.table.closed else ' (endpoint included)'))
        warning = warning_text(result.count)
        if warning:
            self.warning.formattedText = '<font color="#D98000"><b>⚠ ' + warning + '</b></font>'
            self.warning.isVisible = True

    def ready(self):
        return (not self.closed and self.result is not None and not self.result.error
                and self.result.table is not None and self.controller.current(self.result.generation))

    def close(self):
        self.closed = True
        if self._sample_cancel:
            self._sample_cancel.set()
        self.controller.close()
        _sessions.pop(self.id, None)

    def generate(self):
        if not self.ready():
            raise CurveError('Wait for the latest point count and correct any input errors.')
        result = self.result
        if self.settings() != result.settings:
            raise CurveError('Inputs have changed. Wait for the updated point count.')
        active = adsk.fusion.Sketch.cast(self.app.activeEditObject)
        if not active or active != self.sketch or not self.sketch.isValid:
            raise CurveError('Generate while editing the original sketch.')
        kind = 'lines' if self.item('kind').selectedItem.name == 'Line Segments' else 'spline'
        progress = self.app.userInterface.createProgressDialog()
        progress.isCancelButtonShown = True
        progress.show('Function Plotter', 'Sampling by arc length... %p%', 0, 100, 0)
        cancel = threading.Event()
        self._sample_cancel = cancel
        completed = threading.Event()
        sampled = {}
        counts = [0, max(1, result.count)]

        def report(done, total):
            counts[:] = [done, total]

        def work():
            try:
                sampled['points'] = result.table.sample(result.settings.spacing_mm,
                                                        cancel=cancel.is_set, progress=report)
            except Exception as exc:
                sampled['error'] = exc
            finally:
                completed.set()

        worker = threading.Thread(target=work, daemon=True, name='FusionArcSample')
        worker.start()
        try:
            while not completed.wait(0.025):
                adsk.doEvents()
                if progress.wasCancelled or self.closed or _stopping:
                    cancel.set()
                progress.progressValue = int(60*counts[0]/max(1, counts[1]))
            if 'error' in sampled:
                raise sampled['error']
            if progress.wasCancelled or cancel.is_set() or self.closed or _stopping:
                raise Cancelled()
            points = sampled['points']
            if len(points) != result.count:
                raise CurveError('Sample count differs from the preview. Generation has stopped.')
            progress.message = 'Creating sketch geometry... %p%'
            self._last_pump = 0

            def pump(done, total):
                now = time.monotonic()
                if now-self._last_pump >= 0.04 or done == total:
                    progress.progressValue = 60+int(39*done/max(1, total))
                    adsk.doEvents()
                    self._last_pump = now

            def cancelled():
                return progress.wasCancelled or self.closed or _stopping

            made = create_geometry(self.sketch, points, result.table.closed, kind,
                                   adsk.core, cancel=cancelled, progress=pump)
            progress.progressValue = 100
            self.app.activeViewport.refresh()
            self.app.log(f'FusionFunctionPlotter: {len(points)} points, {len(made)} entities created')
        finally:
            cancel.set()
            self._sample_cancel = None
            progress.hide()


class Changed(adsk.core.InputChangedEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        session = self.session
        if session.closed or session.updating:
            return
        name = args.input.id
        if name not in ('mode', 'first', 'second', 'code', 'start', 'end', 'unit', 'spacing', 'accuracy'):
            return
        try:
            if name == 'mode':
                session.updating = True
                try:
                    mode = session.mode()
                    first, second, start, end = EXAMPLES[mode]
                    session.first.value = first
                    session.second.value = second
                    session.item('start').value = start
                    session.item('end').value = end
                    session.display_mode(mode)
                finally:
                    session.updating = False
            session.schedule()
        except Exception as exc:
            session.result = None
            session.controller.invalidate()
            session.info.text = 'Input error: ' + str(exc)


class Validate(adsk.core.ValidateInputsEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        # Point count is deliberately absent from this validity decision.
        args.areInputsValid = bool(self.session.ready())


class Execute(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        try:
            self.session.generate()
        except Cancelled:
            args.executeFailed = True
            args.executeFailedMessage = 'Cancelled. Geometry added during this operation has been removed.'
        except Exception as exc:
            args.executeFailed = True
            args.executeFailedMessage = str(exc)
            self.session.app.log(traceback.format_exc())


class Destroy(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        self.session.close()


class Created(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            sketch = adsk.fusion.Sketch.cast(_app.activeEditObject)
            if not sketch:
                args.command.isOKButtonVisible = False
                args.command.commandInputs.addTextBoxCommandInput(
                    'missingSketch', '', 'Edit the target sketch before opening Function Plotter.', 3, True)
                return
            Session(args.command, sketch)
        except Exception:
            _app.userInterface.messageBox('Unable to open Function Plotter: \n' + traceback.format_exc())


class Delivered(adsk.core.CustomEventHandler):
    def notify(self, args):
        while True:
            try:
                session_id, result = _messages.get_nowait()
            except queue.Empty:
                return
            session = _sessions.get(session_id)
            if session:
                try:
                    session.accept(result)
                except Exception:
                    if _app:
                        _app.log(traceback.format_exc())


def run(context):
    global _app, _registered, _stopping
    try:
        if _app is not None:
            stop(None)
        _app = adsk.core.Application.get()
        _stopping = False
        ui = _app.userInterface
        event = _app.registerCustomEvent(EVENT_ID)
        _registered = True
        bind(event, Delivered(), _handlers)
        definition = ui.commandDefinitions.itemById(COMMAND_ID)
        if definition:
            definition.deleteMe()
        definition = ui.commandDefinitions.addButtonDefinition(
            COMMAND_ID, 'Function Plotter', 'Sample the original curve by arc length and create Line Segments or a Fit Point Spline in the current sketch.')
        bind(definition.commandCreated, Created(), _handlers)
        # Prefer sketch Create; retain a discoverable Utilities entry as well.
        for panel_id in ('SketchCreatePanel', 'SolidScriptsAddinsPanel'):
            panel = ui.allToolbarPanels.itemById(panel_id)
            if panel:
                old = panel.controls.itemById(COMMAND_ID)
                if old:
                    old.deleteMe()
                control = panel.controls.addCommand(definition)
                control.isPromoted = panel_id == 'SketchCreatePanel'
                _controls.append(control)
        if not _controls:
            panel = ui.allToolbarPanels.itemById('SolidCreatePanel')
            if not panel:
                raise CurveError('Design toolbar not found. Switch to the Design workspace and restart the add-in.')
            _controls.append(panel.controls.addCommand(definition))
    except Exception:
        message = traceback.format_exc()
        app = _app or adsk.core.Application.get()
        stop(None)
        app.userInterface.messageBox('Function Plotter failed to start: \n' + message)


def stop(context):
    global _app, _registered, _stopping
    _stopping = True
    app = _app
    for session in list(_sessions.values()):
        session.close()
    for control in _controls:
        try:
            if control.isValid:
                control.deleteMe()
        except Exception:
            pass
    _controls.clear()
    if app:
        try:
            definition = app.userInterface.commandDefinitions.itemById(COMMAND_ID)
            if definition:
                definition.deleteMe()
        except Exception:
            pass
        if _registered:
            try:
                app.unregisterCustomEvent(EVENT_ID)
            except Exception:
                pass
    _registered = False
    _handlers.clear()
    while not _messages.empty():
        try:
            _messages.get_nowait()
        except queue.Empty:
            break
    _app = None
