# TODO: Refactor this with pyttest entirely.

import ctypes
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from ctypes import byref, wintypes
from typing import Optional

from JABWrapper.context_tree import ContextNode, ContextTree, SearchElement
from JABWrapper.jab_types import JavaObject
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper

PeekMessage = ctypes.windll.user32.PeekMessageW
GetMessage = ctypes.windll.user32.GetMessageW
TranslateMessage = ctypes.windll.user32.TranslateMessage
DispatchMessage = ctypes.windll.user32.DispatchMessageW

IGNORE_CALLBACKS = False
LOG_LEVEL = logging.INFO

logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)
for handler in logger.handlers:
    handler.setLevel(LOG_LEVEL)


def dump(obj):
    for attr in dir(obj):
        print("obj.%s = %r" % (attr, getattr(obj, attr)))


def start_test_application(title):
    app_path = os.path.join(os.path.abspath(os.path.curdir), "tests", "test-app")
    # Compile the simple java program
    returncode = subprocess.call(
        ["makejar.bat"], shell=True, cwd=app_path, close_fds=True
    )
    if returncode > 0:
        logger.error(f"Failed to compile Swing application={returncode}")
        sys.exit(returncode)
    # Run the swing program in background
    logger.info("Opening Java Swing application")
    subprocess.Popen(
        ["java", "BasicSwing", title], shell=True, cwd=app_path, close_fds=True
    )
    # Wait a bit for application to open
    time.sleep(2)


def pump_background(pipe: queue.Queue):
    try:
        jab_wrapper = JavaAccessBridgeWrapper(ignore_callbacks=IGNORE_CALLBACKS)
        pipe.put(jab_wrapper)
        message = byref(wintypes.MSG())
        while GetMessage(message, 0, 0, 0) > 0:
            TranslateMessage(message)
            logger.debug("Dispatching msg={}".format(repr(message)))
            DispatchMessage(message)
    except Exception as err:
        logger.error(err)
        pipe.put(None)
    finally:
        logger.info("Stopped processing events")


def write_to_file(name: str, data: str, mode="w") -> None:
    with open(name, mode) as f:
        f.write(data)


def wait_until_text_contains(element: ContextNode, text: str, retries=10):
    logger.info(element.text)
    for i in range(retries):
        if text in element.text.items.sentence:
            return
        time.sleep(0.05)
    else:
        write_to_file("context.txt", "\n\n{}".format(str(element)), "a+")
        raise Exception(f"Text={text} not found in element={element}")


def wait_until_text_cleared(element: ContextNode, retries=10):
    for i in range(retries):
        if element.text.items.sentence == "":
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

    def wait_until_menu_clicked(self, retries=300):
        if IGNORE_CALLBACKS:
            return

        for i in range(retries):
            if self._file_menu_clicked:
                logger.info("File menu clicked")
                return
            time.sleep(0.01)
        else:
            raise Exception("File menu not clicked within timeout")


def select_window(jab_wrapper, window_id):
    # Init the JavaAccessBridge to certain window
    if isinstance(window_id, int):
        pid = jab_wrapper.switch_window_by_pid(window_id)
    else:
        pid = jab_wrapper.switch_window_by_title(window_id)
    logger.info(f"Window PID={pid}")
    assert pid is not None, "Pid is none"
    version_info = jab_wrapper.get_version_info()
    logger.info(
        "VMversion={}; BridgeJavaClassVersion={}; BridgeJavaDLLVersion={}; BridgeWinDLLVersion={}\n".format(
            version_info.VMversion,
            version_info.bridgeJavaClassVersion,
            version_info.bridgeJavaDLLVersion,
            version_info.bridgeWinDLLVersion,
        )
    )


def parse_elements(jab_wrapper) -> ContextTree:
    # Parse the element tree of the window
    logger.info("Getting context tree")
    context_info_tree = ContextTree(jab_wrapper)
    write_to_file("context.txt", repr(context_info_tree))
    return context_info_tree


def type_text_into_text_field(context_info_tree) -> ContextNode:
    # Type text into text field
    text = "Hello World"
    logger.info("Typing text into text field")
    text_area = context_info_tree.get_by_attrs([SearchElement("role", "text")])[0]
    logger.debug("Found element by role (text): {}".format(text_area))
    text_area.insert_text(text)
    wait_until_text_contains(text_area, text)
    return text_area


def set_focus(context_info_tree):
    # Set focus to main frame
    logger.info("Setting focus to main frame")
    root_pane = context_info_tree.get_by_attrs([SearchElement("role", "frame")])[0]
    logger.info("Found element by role (frame): {}".format(root_pane))
    root_pane.request_focus()


def click_send_button(context_info_tree, text_area):
    # Click the send button
    logger.info("Clicking the send button")
    send_button = context_info_tree.get_by_attrs(
        [
            SearchElement("role", "push button"),
            SearchElement("name", "Send"),
            SearchElement("indexInParent", 0),
        ]
    )[0]
    logger.debug(
        "Found element by role (push button) and name (Send): {}".format(send_button)
    )
    send_button.click()
    wait_until_text_contains(text_area, "default text")


def select_combobox(jab_wrapper, context_info_tree, text_area):
    # Select combobox
    logger.info("Selecting text area")
    combo_box_menu = context_info_tree.get_by_attrs(
        [SearchElement("role", "combo box")]
    )[0]
    sel_count = jab_wrapper.get_accessible_selection_count_from_context(
        combo_box_menu.context
    )
    assert sel_count == 1, f"Count 1!={sel_count}"
    jab_wrapper.add_accessible_selection_from_context(combo_box_menu.context, 1)
    should_be_selected = jab_wrapper.is_accessible_child_selected_from_context(
        combo_box_menu.context, 1
    )
    should_not_be_selected = jab_wrapper.is_accessible_child_selected_from_context(
        combo_box_menu.context, 0
    )
    assert should_be_selected, "was not selected"
    assert not should_not_be_selected, "was not not selected"
    jab_wrapper.clear_accessible_selection_from_context(combo_box_menu.context)


def click_clear_button(context_info_tree, text_area):
    # Click the clear button
    logger.info("Clicking the clear button")
    clear_button = context_info_tree.get_by_attrs(
        [
            SearchElement("role", "push button", True),
            SearchElement("name", "Clear"),
            SearchElement("indexInParent", 3),
        ]
    )[0]
    logger.debug(
        "Found element by role (push button) and name (Clear): {}".format(clear_button)
    )
    clear_button.click()
    wait_until_text_cleared(text_area)


def verify_table_content(context_info_tree):
    # Assert visible children are found under the table object
    table = context_info_tree.get_by_attrs([SearchElement("role", "table")])[0]
    visible_children = table.get_visible_children()
    assert table.visible_children_count == len(
        visible_children
    ), "visible child count incorrect"


def open_menu_item_file(jab_wrapper, context_info_tree):
    # Open Menu item FILE
    menu_clicked = MenuClicked()
    jab_wrapper.register_callback("menu_selected", menu_clicked.menu_clicked_callback)
    logger.info("Opening Menu item FILE")
    file_menu = context_info_tree.get_by_attrs(
        [SearchElement("role", "menu"), SearchElement("name", "FILE")]
    )[0]
    logger.debug(
        "Found element by role (push button) and name (FILE): {}".format(file_menu)
    )
    file_menu.click()
    menu_clicked.wait_until_menu_clicked()


def click_exit_menu(context_info_tree) -> ContextNode:
    # Click the exit menu
    logger.info("Clicking the exit menu")
    exit_menu = context_info_tree.get_by_attrs(
        [SearchElement("role", "menu item"), SearchElement("name", "Exit")]
    )[0]
    logger.debug(
        "Found element by role (menu item) and name (Exit): {}".format(exit_menu)
    )
    exit_menu.click()
    return exit_menu


def click_exit(jab_wrapper, exit_menu):
    # Switch to new exit window and click the exit button
    logger.info("Switching to exit frame and clicking the exit button")
    jab_wrapper.switch_window_by_title("Exit")
    context_info_tree_for_exit_frame = ContextTree(jab_wrapper)
    write_to_file(
        "context.txt", "\n\n{}".format(repr(context_info_tree_for_exit_frame)), "a+"
    )
    exit_button = context_info_tree_for_exit_frame.get_by_attrs(
        [SearchElement("role", "push button"), SearchElement("name", "Exit ok")]
    )[0]
    logger.debug(
        "Found element by role (push button) and name (Exit ok): {}".format(exit_menu)
    )
    exit_button.click()


def update_and_refresh_table(context_info_tree):
    table = context_info_tree.get_by_attrs(
        [
            SearchElement("role", "table"),
        ]
    )[0]
    logger.debug("Found table: %s", table)
    initial_children = len(table.children)
    logger.info("Initial children: %d", initial_children)

    update_button = context_info_tree.get_by_attrs(
        [
            SearchElement("role", "push button"),
            SearchElement("name", "Update"),
        ]
    )[0]
    logger.debug("Found 'Update' button: %s", update_button)
    update_button.click()

    expected_total_children = initial_children
    err = "children number changed without refresh"
    if not IGNORE_CALLBACKS:
        # Populating the table will trigger a callback which will automatically
        #  refresh it. We just need to wait a while and adjust our expectations.
        time.sleep(0.1)
        expected_total_children = 2 * initial_children
        err = "children number didn't change after an automatic refresh"
    total_children = len(table.children)
    logger.info(
        "Total children (pre-refresh; callbacks: %s): %d",
        "OFF" if IGNORE_CALLBACKS else "ON",
        total_children,
    )
    assert (
        total_children == expected_total_children
    ), err

    table.refresh()
    total_children = len(table.children)
    logger.info("Total children (post-refresh): %d", total_children)
    assert (
        total_children == 2 * initial_children
    ), "children number didn't change after a manual refresh"


def shutdown_app(jab_wrapper, context_info_tree):
    open_menu_item_file(jab_wrapper, context_info_tree)
    exit_menu = click_exit_menu(context_info_tree)
    click_exit(jab_wrapper, exit_menu)


def run_app_tests(jab_wrapper, window_id):
    select_window(jab_wrapper, window_id)
    context_info_tree = parse_elements(jab_wrapper)
    set_focus(context_info_tree)
    text_area = type_text_into_text_field(context_info_tree)
    click_send_button(context_info_tree, text_area)
    click_clear_button(context_info_tree, text_area)
    verify_table_content(context_info_tree)
    update_and_refresh_table(context_info_tree)
    shutdown_app(jab_wrapper, context_info_tree)


def main():
    jab_wrapper: Optional[JavaAccessBridgeWrapper] = None
    try:
        # Looks like Windows message pump must be run in the main thread, so
        # we'll have to keep invoking it...
        pipe = queue.Queue()
        thread = threading.Thread(target=pump_background, daemon=True, args=[pipe])
        thread.start()
        # FIXME: Get the JAB wrapper (and the context tree) as a fixture.
        jab_wrapper = pipe.get()
        if not jab_wrapper:
            raise Exception("Failed to initialize Java Access Bridge Wrapper")
        time.sleep(0.5)

        start_test_application("Chat Frame")
        windows = jab_wrapper.get_windows()
        title = windows[0].title
        assert title == "Chat Frame", f"Invalid window found={title}"
        run_app_tests(jab_wrapper, title)

        # start_test_application("Foo bar")
        # windows = jab_wrapper.get_windows()
        # title = windows[0].title
        # assert title == "Foo bar", f"Invalid window found={title}"
        # run_app_tests(jab_wrapper, windows[0].pid)  # TODO: parametrize this
    except Exception as e:
        logger.error(f"error={type(e)} - {e}")
    finally:
        logger.info("Shutting down JAB wrapper")
        if jab_wrapper:
            jab_wrapper.shutdown()


if __name__ == "__main__":
    main()
