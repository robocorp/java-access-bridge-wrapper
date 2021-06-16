import time
import logging


def log_exec_time(name):
    def decorator(func):
        def exec_time(*args, **kwargs):
            start = time.perf_counter()
            func(*args, **kwargs)
            stop = time.perf_counter()
            logging.debug(f"Executed {name} in {(stop - start):.04f}s")
        return exec_time
    return decorator
