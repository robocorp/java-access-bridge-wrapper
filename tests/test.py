import logging

import time
import sys
import os

import ctypes
from ctypes import wintypes, byref

import subprocess
import threading
import queue

from JABWrapper.context_tree import ContextNode, ContextTree, SearchElement
from JABWrapper.jab_types import JavaObject
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper


PeekMessage = ctypes.windll.user32.PeekMessageW
GetMessage = ctypes.windll.user32.GetMessageW
TranslateMessage = ctypes.windll.user32.TranslateMessage
DispatchMessage = ctypes.windll.user32.DispatchMessageW


def dump(obj):
    for attr in dir(obj):
        print("obj.%s = %r" % (attr, getattr(obj, attr)))


def start_test_application():
    app_path = os.path.join(os.path.abspath(os.path.curdir), "tests", "test-app")
    # Compile the simple java program
    returncode = subprocess.call(["makejar.bat"], shell=True, cwd=app_path, close_fds=True)
    if returncode > 0:
        logging.error(f"Failed to compile Swing application={returncode}")
        sys.exit(returncode)
    # Run the swing program in background
    logging.info("Opening Java Swing application")
    subprocess.Popen(["java", "BasicSwing"], shell=True, cwd=app_path, close_fds=True)
    # Wait a bit for application to open
    time.sleep(0.5)


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
        logging.error(err)
        pipe.put(None)
    finally:
        logging.info("Stopped processing events")


def write_to_file(name: str, data: str, mode='w') -> None:
    with open(name, mode) as f:
        f.write(data)


def wait_until_text_contains(element: ContextNode, text: str, retries=10):
    for i in range(retries):
        if text in element.text.items.sentence:
            return
        time.sleep(0.05)
    else:
        write_to_file("context.txt", "\n\n{}".format(str(element)), "a+")
        raise Exception(f"Text={text} not found in element={element}")


def wait_until_text_cleared(element: ContextNode, retries=10):
    for i in range(retries):
        if element.text.items.sentence == '':
            return
        time.sleep(0.05)
    else:
        write_to_file("context.txt", "\n\n{}".format(str(element)), "a+")
        raise Exception(f"Text element not cleared={element}")


class MenuClicked:
    def __init__(self) -> None:
        self._file_menu_clicked = False

    def menu_clicked_callback(self, _: JavaObject):
        self._file_menu_clicked = True

    def wait_until_menu_clicked(self, retries=100):
        for i in range(retries):
            if self._file_menu_clicked:
                logging.info("File menu clicked")
                return
            time.sleep(0.01)
        else:
            raise Exception("File menu not clicked within timeout")


def main():
    jab_wrapper: JavaAccessBridgeWrapper = None
    try:
        start_test_application()

        # Looks like Windows message pump must be run in the main thread, so
        # we'll have to keep invoking it...
        pipe = queue.Queue()
        thread = threading.Thread(target=pump_background, daemon=True, args=[pipe])
        thread.start()
        jab_wrapper = pipe.get()
        if not jab_wrapper:
            raise Exception("Failed to initialize Java Access Bridge Wrapper")
        time.sleep(0.1)

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

        # Get table data
        # logging.info("Getting table info")
        # table_field = context_info_tree.get_by_attrs([SearchElement("role", "table")])[0]
        # cell_info = jab_wrapper.get_accessible_table_cell_info(table_field.tp.table.accessibleTable, 1, 1)
        # row_header = jab_wrapper.get_accessible_table_row_header(table_field.context)
        # column_header = jab_wrapper.get_accessible_table_column_header(table_field.context)
        # row_context = jab_wrapper.get_accessible_table_row_description(table_field.context, 0)
        # column_context = jab_wrapper.get_accessible_table_column_description(table_field.context, 1)
        # row_sel_count = jab_wrapper.get_accessible_table_row_selection_count(table_field.tp.table.accessibleTable)
        # is_row_selected = jab_wrapper.is_accessible_table_row_selected(table_field.tp.table.accessibleTable, 0)
        # column_sel_count = jab_wrapper.get_accessible_table_column_selection_count(table_field.tp.table.accessibleTable)
        # is_column_selected = jab_wrapper.is_accessible_table_column_selected(table_field.tp.table.accessibleTable, 1)
        # row = jab_wrapper.get_accessible_table_row(table_field.tp.table.accessibleTable, 2)
        # column = jab_wrapper.get_accessible_table_column(table_field.tp.table.accessibleTable, 2)
        # index = jab_wrapper.get_accessible_table_index(table_field.tp.table.accessibleTable, 2, 2)

        # Type text into text field
        text = "Hello World"
        logging.info("Typing text into text field")
        text_area = context_info_tree.get_by_attrs([SearchElement("role", "text")])[0]
        logging.debug("Found element by role (text): {}".format(text_area))
        text_area.insert_text(text)
        wait_until_text_contains(text_area, text)

        # Click the send button
        logging.info("Clicking the send button")
        send_button = context_info_tree.get_by_attrs([SearchElement("role", "push button"), SearchElement("name", "Send")])[0]
        logging.debug("Found element by role (push button) and name (Send): {}".format(send_button))
        send_button.click()
        wait_until_text_contains(text_area, "default text")

        # Select combobox
        logging.info("Selecting text area")
        combo_box_menu = context_info_tree.get_by_attrs([SearchElement("role", "combo box")])[0]
        sel_count = jab_wrapper.get_accessible_selection_count_from_context(combo_box_menu.context)
        assert sel_count == 1
        jab_wrapper.add_accessible_selection_from_context(combo_box_menu.context, 1)
        should_be_selected = jab_wrapper.is_accessible_child_selected_from_context(combo_box_menu.context, 1)
        should_not_be_selected = jab_wrapper.is_accessible_child_selected_from_context(combo_box_menu.context, 0)
        assert should_be_selected
        assert not should_not_be_selected
        jab_wrapper.clear_accessible_selection_from_context(combo_box_menu.context)

        # Click the clear button
        logging.info("Clicking the clear button")
        clear_button = context_info_tree.get_by_attrs([SearchElement("role", "push button"), SearchElement("name", "Clear")])[0]
        logging.debug("Found element by role (push button) and name (Clear): {}".format(clear_button))
        clear_button.click()
        wait_until_text_cleared(text_area)

        # Open Menu item FILE
        menu_clicked = MenuClicked()
        jab_wrapper.register_callback("menu_selected", menu_clicked.menu_clicked_callback)
        logging.info("Opening Menu item FILE")
        file_menu = context_info_tree.get_by_attrs([SearchElement("role", "menu"), SearchElement("name", "FILE")])[0]
        logging.debug("Found element by role (push button) and name (FILE): {}".format(clear_button))
        file_menu.click()
        menu_clicked.wait_until_menu_clicked()

        # Click the exit menu
        logging.info("Clicking the exit menu")
        exit_menu = context_info_tree.get_by_attrs([SearchElement("role", "menu item"), SearchElement("name", "Exit")])[0]
        logging.debug("Found element by role (menu item) and name (Exit): {}".format(exit_menu))
        exit_menu.click()

        # Switch to new exit window and click the exit button
        logging.info("Switching to exit frame and clicking the exit button")
        jab_wrapper.switch_window_by_title("Exit")
        context_info_tree_for_exit_frame = ContextTree(jab_wrapper)
        write_to_file("context.txt", "\n\n{}".format(repr(context_info_tree_for_exit_frame)), "a+")
        exit_button = context_info_tree_for_exit_frame.get_by_attrs([SearchElement("role", "push button"), SearchElement("name", "Exit ok")])[0]
        logging.debug("Found element by role (push button) and name (Exit ok): {}".format(exit_menu))
        exit_button.click()
    except Exception as e:
        logging.error(f"error={e}")
    finally:
        logging.info("Shutting down JAB wrapper")
        if jab_wrapper:
            jab_wrapper.shutdown()


if __name__ == "__main__":
    main()
