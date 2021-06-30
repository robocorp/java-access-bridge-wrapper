[![Version](https://img.shields.io/pypi/v/java-access-bridge-wrapper.svg?label=version)](https://pypi.org/project/java-access-bridge-wrapper/)
[![License](https://img.shields.io/pypi/l/java-access-bridge-wrapper.svg)](http://www.apache.org/licenses/LICENSE-2.0.html)

# Introduction

Python wrapper around the Java Access Bridge / Windows Access Bridge.

# Prerequisites

* 64-bit Windows
* Java >= 8 (https://docs.aws.amazon.com/corretto/latest/corretto-8-ug/downloads-list.html)
* Python >= 3.7 (https://www.python.org/downloads/release/python-375/)

Enable the Java Access Bridge in windows

    C:\path\to\java\bin\jabswitch -enable

# Install

    pip install java-access-bridge-wrapper

# How to use

Import the Java Access Bridge (JAB) wrapper and optionally the context tree

    from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
    from JABWrapper.context_tree import ContextNode, ContextTree, SearchElement

The JAB creates an virtual GUI window when it is opened. For the JAB to operate and receive events from the GUI, the calling code needs to implement the windows
message pump and call it in a loop. The JABWrapper object needs to be in the same thread.

This can be achieved for example by starting the message pump in a separate thread, where the JAB object is also initialized.

    GetMessage = ctypes.windll.user32.GetMessageW
    TranslateMessage = ctypes.windll.user32.TranslateMessage
    DispatchMessage = ctypes.windll.user32.DispatchMessageW

    def pump_background(pipe: queue.Queue):
        try:
            jab_wrapper = JavaAccessBridgeWrapper()
            pipe.put(jab_wrapper)
            message = byref(wintypes.MSG())
            while GetMessage(message, 0, 0, 0) > 0:
                TranslateMessage(message)
                logging.debug("Dispatching msg={}".format(repr(message)))
                DispatchMessage(message)
        except Exception as err:
            pipe.put(None)

    def main():
        pipe = queue.Queue()
            thread = threading.Thread(target=pump_background, daemon=True, args=[pipe])
            thread.start()
            jab_wrapper = pipe.get()
            if not jab_wrapper:
                raise Exception("Failed to initialize Java Access Bridge Wrapper")
            time.sleep(0.1) # Wait until the initial messages are parsed, before accessing frames

    if __name__ == "__main__":
        main()

Once the JABWrapper object is initialized, attach to some frame and optionally create the context tree to get the element tree of the application.

    jab_wrapper.switch_window_by_title("Frame title")
    context_tree = ContextTree(jab_wrapper)

# Development

## Development prerequisites

* Install poetry: https://python-poetry.org/docs/

## Test

Run test script against simple Swing application

set environment variable

    set RC_JAVA_ACCESS_BRIDGE_DLL="C:\path\to\Java\bin\WindowsAccessBridge-64.dll"

Run test with poetry

    poetry run python tests\test.py

## Packaging

    poetry build
    poetry publish

## TODO:

* Support for 32-bit Java Access Bridge version
* Implement rest of the utility functions to the JABWrapper
