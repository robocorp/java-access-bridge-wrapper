import logging
import time

CALLBACK_RETRIES = 10


def log_exec_time(name):
    def decorator(func):
        def exec_time(*args, **kwargs):
            start = time.perf_counter()
            func(*args, **kwargs)
            stop = time.perf_counter()
            logging.debug(f"Executed {name} in {(stop - start):.04f}s")

        return exec_time

    return decorator


def retry_callback(func):
    def execute(*args, **kwargs):
        for index in range(CALLBACK_RETRIES):
            try:
                func(*args, **kwargs)
                return
            except Exception as e:
                if index == CALLBACK_RETRIES - 1:
                    logging.error(f"Callback failure={e}")
                else:
                    time.sleep(0.01)

    return execute


class ReleaseEvent:
    def __init__(self, context, vmID, name, event, source) -> None:
        self._context = context
        self._vmID = vmID
        self._name = name
        self._event = event
        self._source = source
        self._start_exec: float = 0

    def __enter__(self):
        logging.debug(f"Received {self._name} event={self._source}")
        self._start_exec = time.perf_counter()

    def __exit__(self, type, value, traceback):
        stop_exec = time.perf_counter()
        logging.debug(f"Executed {self._name} in {(stop_exec - self._start_exec):.04f}s")
        self._context._wab.releaseJavaObject(self._vmID, self._event)


class SearchElement:
    def __init__(self, name, value, strict=False) -> None:
        self.name = name
        self.value = value
        self.strict = strict
