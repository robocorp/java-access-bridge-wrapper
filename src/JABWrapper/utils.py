import time
import logging


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
