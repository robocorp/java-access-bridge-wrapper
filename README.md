[![Version](https://img.shields.io/pypi/v/java-access-bridge-wrapper.svg?label=version)](https://pypi.org/project/java-access-bridge-wrapper/)
[![License](https://img.shields.io/pypi/l/java-access-bridge-wrapper.svg)](http://www.apache.org/licenses/LICENSE-2.0.html)

# Introduction

Python wrapper around the Java Access Bridge / Windows Access Bridge.

# Requirements

* 64-bit Windows
* Java >= 8 (https://docs.aws.amazon.com/corretto/latest/corretto-8-ug/downloads-list.html)
  * If you are doing development install JDK, otherwise JRE is enough
* Python >= 3.8 (https://www.python.org/downloads/release/python-375/)

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

## Prerequisites

1. Install Invoke, Poetry and the other required dependencies in order to be able to develop and package the library:
   `pip install -Ur requirements.txt`.
   - If you want to isolate these from the other projects and not rely on the OS
     Python, enable a (_pyenv_) virtual environment first by following these
     [instructions](https://github.com/robocorp/rpaframework/blob/master/docs/source/contributing/development.md#virtual-environments).
2. Now you're ready to set-up Poetry for the first time with `inv setup`.
   - Check with `-h` on how to pass credentials for ensuring that both your production  PyPI and CI DevPI are
     configured. You'll find these in our **Robocorp** > **Shared** 1Password by searching for keywords like "pypi"
     (where we recommend a personal _token_ instead) and "devpi".
3. Run `inv update` so the library gets ready for development.

## Testing

Run test script against a simple Swing application.

Set environment variable

    set RC_JAVA_ACCESS_BRIDGE_DLL="C:\path\to\Java\bin\WindowsAccessBridge-64.dll"

Update requirements and install the library in development mode

    inv update

Run tests

    inv test  # runs all the tests in all scenarios
    inv test -s -t test_jab_wrapper.py  # runs all the tests from a file in one simple common scenario
    inv test -s -c -t test_jab_wrapper.py::test_depth  # as above, but specific test and captures output

## Packaging

Check linting

    inv lint  # apply with '-a'

Building and publishing

    inv publish  # '-c' for DevPI

## TODO:

* Support for 32-bit Java Access Bridge version
* Implement rest of the utility functions to the JABWrapper
