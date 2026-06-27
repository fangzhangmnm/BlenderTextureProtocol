"""
Cross-thread dispatcher.

HTTP handlers run in background threads. They cannot touch
bpy directly (bpy is not thread-safe; mutations must happen on the
main thread). They submit a callable to dispatch_to_main(), which
queues it; the main thread drains the queue via bpy.app.timers and
runs each callable, then signals completion.
"""
import queue
import threading

import bpy


_request_queue = queue.Queue()
_running = False


class _Request:
    __slots__ = ("handler", "args", "kwargs", "event", "result", "error")

    def __init__(self, handler, args, kwargs):
        self.handler = handler
        self.args = args
        self.kwargs = kwargs
        self.event = threading.Event()
        self.result = None
        self.error = None


def dispatch_to_main(handler, *args, **kwargs):
    if not _running:
        raise RuntimeError("BTP bridge not running")
    req = _Request(handler, args, kwargs)
    _request_queue.put(req)
    req.event.wait()
    if req.error is not None:
        raise req.error
    return req.result


def _drain_queue():
    if not _running:
        return None
    while True:
        try:
            req = _request_queue.get_nowait()
        except queue.Empty:
            break
        try:
            req.result = req.handler(*req.args, **req.kwargs)
        except Exception as e:
            req.error = e
        req.event.set()
    return 0.05


def start():
    global _running
    _running = True
    if not bpy.app.timers.is_registered(_drain_queue):
        bpy.app.timers.register(_drain_queue, persistent=True)


def stop():
    global _running
    _running = False
    while True:
        try:
            req = _request_queue.get_nowait()
        except queue.Empty:
            break
        req.error = RuntimeError("BTP shutting down")
        req.event.set()
