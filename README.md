
Python wrapper around the Java Access Bridge / Windows Access Bridge.

# Prerequisites

* 64-bit Windows
* Java >= 8 (https://docs.aws.amazon.com/corretto/latest/corretto-8-ug/downloads-list.html)
* Python >= 3.7 (https://www.python.org/downloads/release/python-375/)
* Install poetry: https://python-poetry.org/docs/

# Test

Enable the Java Access Bridge in windows

* `C:\path\to\java\bin\jabswitch -enable`.

Run test script against simple Swing application

* set environment variable `set WindowsAccessBridge=C:\Program Files\Java\jre1.8.0_261\bin\WindowsAccessBridge-64.dll`
* `poetry run python tests\test.py`

# Packaging

* poetry build
* poetry publish

# TODO:

* Support for 32-bit Java Access Bridge version
* Add rest of the callback handlers
* Add rest of the parsing functions
* Better API to the ContextNode component

