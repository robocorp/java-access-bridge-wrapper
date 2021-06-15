import logging

import time
import sys
import os

import ctypes
from ctypes import wintypes, byref

import subprocess
import threading
import queue

from context_tree import ContextNode, ContextTree, SearchElement
from jab_wrapper import JavaAccessBridgeWrapper

PeekMessage = ctypes.windll.user32.PeekMessageW
GetMessage = ctypes.windll.user32.GetMessageW
TranslateMessage = ctypes.windll.user32.TranslateMessage
DispatchMessage = ctypes.windll.user32.DispatchMessageW

def start_test_application():
    app_path = os.path.join(os.path.curdir, "test-app")
    # Compile the simple java program
    returncode = subprocess.call(["makejar.bat"], shell=True, cwd=app_path, close_fds=True)
    if returncode > 0:
        logging.error(f"Failed to compile Swing application={returncode}")
        sys.exit(returncode)
    # Run the swing program in background
    logging.info("Opening Java Swing application")
    subprocess.Popen(["java", "-jar", "BasicSwing.jar"], shell=True, cwd=app_path, close_fds=True)

def pump_background(pipe: queue.Queue):
    jab_wrapper = JavaAccessBridgeWrapper()
    pipe.put(jab_wrapper)
    message = byref(wintypes.MSG())
    while GetMessage(message, 0, 0, 0) > 0:
        TranslateMessage(message)
        logging.debug("Dispatching msg={}".format(repr(message)))
        DispatchMessage(message)
    logging.info("Stopped processing events", flush=True)

def write_to_file(name: str, data: str, mode = 'w') -> None:
    with open(name, mode) as f:
        f.write(data)

def wait_until_text_contains(element: ContextNode, text: str, retries = 10):
    for i in range(retries):
        if text in element.atp.items.sentence:
            return
        time.sleep(0.01)
    else:
        write_to_file("context.txt", "\n\n{}".format(str(element)), "a+")
        raise Exception(f"Text={text} not found in element={element}")

def wait_until_text_cleared(element: ContextNode, retries = 10):
    for i in range(retries):
        if element.atp.items.sentence == '':
            return
        time.sleep(0.01)
    else:
        write_to_file("context.txt", "\n\n{}".format(str(element)), "a+")
        raise Exception(f"Text element not cleared={element}")

def main():
    try:
        start_test_application()

        # Looks like Windows message pump must be run in the main thread, so
        # we'll have to keep invoking it...
        pipe = queue.Queue()
        thread = threading.Thread(target=pump_background, daemon=True, args=[pipe])
        thread.start()
        jab_wrapper = pipe.get()
        time.sleep(1)

        # Init the JavaAccessBridge to certain window
        jab_wrapper.switch_window_by_title("Chat Frame")
        version_info = jab_wrapper.get_version_info()
        logging.info("VMversion={}; BridgeJavaClassVersion={}; BridgeJavaDLLVersion={}; BridgeWinDLLVersion={}\n".format(
            version_info.VMversion,
            version_info.bridgeJavaClassVersion,
            version_info.bridgeJavaDLLVersion,
            version_info.bridgeWinDLLVersion
        ))

        # Parse the element tree of the window
        logging.info("Getting context tree")
        context_info_tree = ContextTree(jab_wrapper)
        write_to_file("context.txt", repr(context_info_tree))

        # Set focus to main frame
        logging.info("Setting focus to main frame")
        root_pane = context_info_tree.get_by_attrs([SearchElement("role", "frame")])[0]
        logging.debug("Found element by role (frame): {}".format(root_pane))
        root_pane.request_focus()

        # Type text into text field
        text = "Hello World"
        logging.info("Typing text into text field")
        text_field = context_info_tree.get_by_attrs([SearchElement("role", "text")])[0]
        logging.debug("Found element by role (text): {}".format(text_field))
        text_field.insert_text(text)
        wait_until_text_contains(text_field, text)

        # Click the send button
        logging.info("Clicking the send button")
        send_button = context_info_tree.get_by_attrs([SearchElement("role", "push button"), SearchElement("name", "Send")])[0]
        logging.debug("Found element by role (push button) and name (Send): {}".format(send_button))
        send_button.click()
        wait_until_text_contains(text_field, "default text")

        # Click the clear button
        logging.info("Clicking the clear button")
        clear_button = context_info_tree.get_by_attrs([SearchElement("role", "push button"), SearchElement("name", "Clear")])[0]
        logging.debug("Found element by role (push button) and name (Clear): {}".format(clear_button))
        clear_button.click()
        wait_until_text_cleared(text_field)

        # Open Menu item FILE
        logging.info("Opening Menu item FILE")
        file_menu = context_info_tree.get_by_attrs([SearchElement("role", "menu"), SearchElement("name", "FILE")])[0]
        logging.debug("Found element by role (push button) and name (FILE): {}".format(clear_button))
        file_menu.click()

        # Click the exit menu
        logging.info("Clicking the exit menu")
        exit_menu = context_info_tree.get_by_attrs([SearchElement("role", "menu item"), SearchElement("name", "Exit")])[0]
        logging.debug("Found element by role (menu item) and name (Exit): {}".format(exit_menu))
        exit_menu.click()

        write_to_file("context.txt", "\n\n{}".format(repr(context_info_tree)), "a+")

        # Switch to new exit window and click the exit button
        logging.info("Switching to exit frame and clicking the exit button")
        jab_wrapper.switch_window_by_title("Exit")
        context_info_tree_for_exit_frame = ContextTree(jab_wrapper)
        write_to_file("context.txt", "\n\n{}".format(repr(context_info_tree_for_exit_frame)), "a+")
        exit_button = context_info_tree_for_exit_frame.get_by_attrs([SearchElement("role", "push button"), SearchElement("name", "Exit ok")])[0]
        logging.debug("Found element by role (push button) and name (Exit ok): {}".format(exit_menu))
        exit_button.click()
    finally:
        logging.info("Shutting down JAB wrapper")
        jab_wrapper.shutdown()


if __name__ == "__main__":
    main()
