import ctypes
import functools
import logging
import os
import queue
import subprocess
import threading
import time
from ctypes import byref, wintypes

import pytest

from JABWrapper.context_tree import ContextNode, ContextTree, SearchElement
from JABWrapper.jab_types import JavaObject
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper

PeekMessage = ctypes.windll.user32.PeekMessageW
GetMessage = ctypes.windll.user32.GetMessageW
TranslateMessage = ctypes.windll.user32.TranslateMessage
DispatchMessage = ctypes.windll.user32.DispatchMessageW


def _pump_background(pipe: queue.Queue):
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


@pytest.fixture(scope="session")
def jab_wrapper():
    logging.info("Starting the JAB wrapper")
    pipe = queue.Queue()
    thread = threading.Thread(target=_pump_background, daemon=True, args=[pipe])
    thread.start()
    jab_wrapper = pipe.get()
    if not jab_wrapper:
        raise Exception("Failed to initialize Java Access Bridge Wrapper")

    yield jab_wrapper

    logging.info("Shutting down the JAB wrapper")
    jab_wrapper.shutdown()


def parse_elements(jab_wrapper) -> ContextTree:
    # Parse the element tree of the window
    logging.info("Getting context tree")
    context_info_tree = ContextTree(jab_wrapper)
    write_to_file("context.txt", repr(context_info_tree))
    return context_info_tree


def shutdown_app(jab_wrapper, context_info_tree):
    open_menu_item_file(jab_wrapper, context_info_tree)
    exit_menu = click_exit_menu(context_info_tree)
    click_exit(jab_wrapper, exit_menu)


@pytest.fixture(params=["title", "pid"])
def test_application(jab_wrapper, request):
    app_path = os.path.join(os.path.abspath(os.path.curdir), "tests", "test-app")
    run = functools.partial(subprocess.run, check=True, cwd=app_path, close_fds=True)
    # Compile a simple Java program.
    run(["makejar.bat"])
    # Run the swing program in the background.
    logging.info("Opening Java Swing application...")
    by_attr = request.param
    title = f"Chat Frame - By {by_attr}"
    run(["java", "BasicSwing", title])

    windows = jab_wrapper.get_windows()
    window = windows[0]
    assert window.title == title, f"Invalid found window {window.title!r}"
    window_id = getattr(window, by_attr)

    select_window(jab_wrapper, window_id)
    context_info_tree = parse_elements(jab_wrapper)

    yield context_info_tree

    shutdown_app(jab_wrapper, context_info_tree)


def write_to_file(name: str, data: str, mode="w") -> None:
    with open(name, mode) as f:
        f.write(data)


def wait_until_text_contains(element: ContextNode, text: str, retries=10):
    logging.info(element.text)
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

    def wait_until_menu_clicked(self, retries=100):
        for i in range(retries):
            if self._file_menu_clicked:
                logging.info("File menu clicked")
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
    logging.info(f"Window PID={pid}")
    assert pid is not None, "PID is null"
    version_info = jab_wrapper.get_version_info()
    logging.info(
        "VMversion={}; BridgeJavaClassVersion={}; BridgeJavaDLLVersion={}; BridgeWinDLLVersion={}\n".format(
            version_info.VMversion,
            version_info.bridgeJavaClassVersion,
            version_info.bridgeJavaDLLVersion,
            version_info.bridgeWinDLLVersion,
        )
    )


def type_text_into_text_field(context_info_tree) -> ContextNode:
    # Type text into text field
    text = "Hello World"
    logging.info("Typing text into text field")
    text_area = context_info_tree.get_by_attrs([SearchElement("role", "text")])[0]
    logging.debug("Found element by role (text): {}".format(text_area))
    text_area.insert_text(text)
    wait_until_text_contains(text_area, text)
    return text_area


def set_focus(context_info_tree):
    # Set focus to main frame
    logging.info("Setting focus to main frame")
    root_pane = context_info_tree.get_by_attrs([SearchElement("role", "frame")])[0]
    logging.info("Found element by role (frame): {}".format(root_pane))
    root_pane.request_focus()


def click_send_button(context_info_tree, text_area):
    # Click the send button
    logging.info("Clicking the send button")
    send_button = context_info_tree.get_by_attrs(
        [SearchElement("role", "push button"), SearchElement("name", "Send"), SearchElement("indexInParent", 0)]
    )[0]
    logging.debug("Found element by role (push button) and name (Send): {}".format(send_button))
    send_button.click()
    wait_until_text_contains(text_area, "default text")


def select_combobox(jab_wrapper, context_info_tree, text_area):
    # Select combobox
    logging.info("Selecting text area")
    combo_box_menu = context_info_tree.get_by_attrs([SearchElement("role", "combo box")])[0]
    sel_count = jab_wrapper.get_accessible_selection_count_from_context(combo_box_menu.context)
    assert sel_count == 1, f"Count 1!={sel_count}"
    jab_wrapper.add_accessible_selection_from_context(combo_box_menu.context, 1)
    should_be_selected = jab_wrapper.is_accessible_child_selected_from_context(combo_box_menu.context, 1)
    should_not_be_selected = jab_wrapper.is_accessible_child_selected_from_context(combo_box_menu.context, 0)
    assert should_be_selected, "was not selected"
    assert not should_not_be_selected, "was not not selected"
    jab_wrapper.clear_accessible_selection_from_context(combo_box_menu.context)


def click_clear_button(context_info_tree, text_area):
    # Click the clear button
    logging.info("Clicking the clear button")
    clear_button = context_info_tree.get_by_attrs(
        [SearchElement("role", "push button", True), SearchElement("name", "Clear"), SearchElement("indexInParent", 3)]
    )[0]
    logging.debug("Found element by role (push button) and name (Clear): {}".format(clear_button))
    clear_button.click()
    wait_until_text_cleared(text_area)


def verify_table_content(context_info_tree):
    # Assert visible children are found under the table object
    table = context_info_tree.get_by_attrs([SearchElement("role", "table")])[0]
    visible_children = table.get_visible_children()
    assert table.visible_children_count == len(visible_children), "visible child count incorrect"


def open_menu_item_file(jab_wrapper, context_info_tree):
    # Open Menu item FILE
    menu_clicked = MenuClicked()
    jab_wrapper.register_callback("menu_selected", menu_clicked.menu_clicked_callback)
    logging.info("Opening Menu item FILE")
    file_menu = context_info_tree.get_by_attrs([SearchElement("role", "menu"), SearchElement("name", "FILE")])[0]
    logging.debug("Found element by role (push button) and name (FILE): {}".format(file_menu))
    file_menu.click()
    menu_clicked.wait_until_menu_clicked()


def click_exit_menu(context_info_tree) -> ContextNode:
    # Click the exit menu
    logging.info("Clicking the exit menu")
    exit_menu = context_info_tree.get_by_attrs([SearchElement("role", "menu item"), SearchElement("name", "Exit")])[0]
    logging.debug("Found element by role (menu item) and name (Exit): {}".format(exit_menu))
    exit_menu.click()
    return exit_menu


def click_exit(jab_wrapper, exit_menu):
    # Switch to new exit window and click the exit button
    logging.info("Switching to exit frame and clicking the exit button")
    jab_wrapper.switch_window_by_title("Exit")
    context_info_tree_for_exit_frame = ContextTree(jab_wrapper)
    write_to_file("context.txt", "\n\n{}".format(repr(context_info_tree_for_exit_frame)), "a+")
    exit_button = context_info_tree_for_exit_frame.get_by_attrs(
        [SearchElement("role", "push button"), SearchElement("name", "Exit ok")]
    )[0]
    logging.debug("Found element by role (push button) and name (Exit ok): {}".format(exit_menu))
    exit_button.click()


def test_app_flow(context_info_tree):
    set_focus(context_info_tree)
    text_area = type_text_into_text_field(context_info_tree)
    click_send_button(context_info_tree, text_area)
    click_clear_button(context_info_tree, text_area)
    verify_table_content(context_info_tree)
