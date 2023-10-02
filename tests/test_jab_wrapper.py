import ctypes
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


CALLBACKS_SWITCHES = [{"enable": False, "simple": True}, {"enable": True, "simple": False}]
WINDOW_SELECTIONS = [{"by_attr": "title", "simple": True}, {"by_attr": "pid", "simple": False}]


# Initialize and launch the Java test app.


def _pump_background(pipe: queue.Queue, *, enable_callbacks: bool):
    try:
        jab_wrapper = JavaAccessBridgeWrapper(ignore_callbacks=not enable_callbacks)
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


@pytest.fixture(scope="session", params=CALLBACKS_SWITCHES)
def enable_callbacks(request):
    enable, simple = request.param["enable"], request.param["simple"]
    if request.config.option.simple and not simple:
        pytest.skip("not simple")

    yield enable


@pytest.fixture(scope="session")
def jab_wrapper(enable_callbacks):
    logging.info("Starting the JAB wrapper")
    pipe = queue.Queue()
    thread = threading.Thread(
        target=_pump_background, daemon=True, args=[pipe], kwargs={"enable_callbacks": enable_callbacks}
    )
    thread.start()
    jab_wrapper = pipe.get()
    if not jab_wrapper:
        raise Exception("Failed to initialize Java Access Bridge Wrapper")

    yield jab_wrapper

    logging.info("Shutting down the JAB wrapper")
    jab_wrapper.shutdown()


def _write_to_file(data: str, name: str = "context.txt", mode: str = "a+") -> None:
    with open(name, mode) as stream:
        stream.write(data)


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


def parse_elements(jab_wrapper, max_depth=None) -> ContextTree:
    # Parse the element tree of the window
    logging.info("Getting context tree")
    context_info_tree = ContextTree(jab_wrapper, max_depth=max_depth)
    _write_to_file(repr(context_info_tree), mode="w")
    return context_info_tree


def application_launcher(jab_wrapper, *, by_attr):
    app_path = os.path.join(os.path.abspath(os.path.curdir), "tests", "test-app")
    # Compile a simple Java program.
    subprocess.run(["makejar.bat"], check=True, shell=True, cwd=app_path, close_fds=True)
    # Run the swing program in the background.
    logging.info("Opening Java Swing application...")
    title = f"Chat Frame - By {by_attr}"
    subprocess.Popen(["java", "BasicSwing", title], cwd=app_path, close_fds=True)

    window = None
    while not window:
        windows = jab_wrapper.get_windows()
        if windows:
            window = windows[0]
        else:
            logging.info("Waiting for window to spawn...")
            time.sleep(0.5)
    assert window.title == title, f"Invalid found window {window.title!r}"

    window_id = getattr(window, by_attr)
    select_window(jab_wrapper, window_id)
    context_info_tree = parse_elements(jab_wrapper)

    return context_info_tree


# Close the Java test app.


class MenuClicked:
    def __init__(self, jab_wrapper: JavaAccessBridgeWrapper) -> None:
        self._jab_wrapper = jab_wrapper
        self._file_menu_clicked = False

    def menu_clicked_callback(self, _: JavaObject):
        self._file_menu_clicked = True

    def wait_until_menu_clicked(self, retries=300):
        if self._jab_wrapper.ignore_callbacks:
            return

        for i in range(retries):
            if self._file_menu_clicked:
                logging.info("File menu clicked")
                return
            time.sleep(0.01)
        else:
            raise Exception("File menu not clicked within timeout")


def open_menu_item_file(jab_wrapper, context_info_tree):
    # Open Menu item FILE
    menu_clicked = MenuClicked(jab_wrapper)
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
    _write_to_file("\n\n{}".format(repr(context_info_tree_for_exit_frame)))
    exit_button = context_info_tree_for_exit_frame.get_by_attrs(
        [SearchElement("role", "push button"), SearchElement("name", "Exit ok")]
    )[0]
    logging.debug("Found element by role (push button) and name (Exit ok): {}".format(exit_menu))
    exit_button.click()


def shutdown_app(jab_wrapper, context_info_tree):
    open_menu_item_file(jab_wrapper, context_info_tree)
    exit_menu = click_exit_menu(context_info_tree)
    click_exit(jab_wrapper, exit_menu)


# Test a basic app flow with multiple window selections and callback switches.


@pytest.fixture(scope="session", params=WINDOW_SELECTIONS)
def window_selection(request):
    by_attr, simple = request.param["by_attr"], request.param["simple"]
    if request.config.option.simple and not simple:
        pytest.skip("not simple")

    yield by_attr


@pytest.fixture(scope="session")
def app_context(jab_wrapper, window_selection):
    context_info_tree = application_launcher(jab_wrapper, by_attr=window_selection)
    yield context_info_tree
    shutdown_app(jab_wrapper, context_info_tree)


def wait_until_text_contains(element: ContextNode, text: str, *, jab_wrapper, retries=10):
    if jab_wrapper.ignore_callbacks:
        element.refresh()

    logging.info(element.text)
    for i in range(retries):
        if text in element.text.items.sentence:
            return
        time.sleep(0.05)
    else:
        _write_to_file("\n\n{}".format(str(element)))
        raise Exception(f"Text={text} not found in element={element}")


def wait_until_text_cleared(element: ContextNode, *, jab_wrapper, retries=10):
    if jab_wrapper.ignore_callbacks:
        element.refresh()

    for i in range(retries):
        if element.text.items.sentence == "":
            return
        time.sleep(0.05)
    else:
        _write_to_file("\n\n{}".format(str(element)))
        raise Exception(f"Text element not cleared={element}")


def type_text_into_text_field(context_info_tree, *, jab_wrapper) -> ContextNode:
    # Type text into text field
    text = "Hello World"
    logging.info("Typing text into text field")
    text_area = context_info_tree.get_by_attrs([SearchElement("role", "text")])[0]
    logging.debug("Found element by role (text): {}".format(text_area))
    text_area.insert_text(text)
    wait_until_text_contains(text_area, text, jab_wrapper=jab_wrapper)
    return text_area


def set_focus(context_info_tree):
    # Set focus to main frame
    logging.info("Setting focus to main frame")
    root_pane = context_info_tree.get_by_attrs([SearchElement("role", "frame")])[0]
    logging.info("Found element by role (frame): {}".format(root_pane))
    root_pane.request_focus()


def click_send_button(context_info_tree, text_area, *, jab_wrapper):
    # Click the send button
    logging.info("Clicking the send button")
    send_button = context_info_tree.get_by_attrs(
        [SearchElement("role", "push button"), SearchElement("name", "Send"), SearchElement("indexInParent", 0)]
    )[0]
    logging.debug("Found element by role (push button) and name (Send): {}".format(send_button))
    send_button.click()
    wait_until_text_contains(text_area, "default text", jab_wrapper=jab_wrapper)


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


def click_clear_button(context_info_tree, text_area, *, jab_wrapper):
    # Click the clear button
    logging.info("Clicking the clear button")
    clear_button = context_info_tree.get_by_attrs(
        [SearchElement("role", "push button", True), SearchElement("name", "Clear"), SearchElement("indexInParent", 3)]
    )[0]
    logging.debug("Found element by role (push button) and name (Clear): {}".format(clear_button))
    clear_button.click()
    wait_until_text_cleared(text_area, jab_wrapper=jab_wrapper)


def verify_table_content(context_info_tree):
    # Assert visible children are found under the table object
    table = context_info_tree.get_by_attrs([SearchElement("role", "table")])[0]
    visible_children_count = len(table.get_visible_children())
    logging.info("Table returned %d visible children.", visible_children_count)
    assert table.visible_children_count == visible_children_count, "visible children count incorrect"


def update_and_refresh_table(context_info_tree, *, jab_wrapper):
    table = context_info_tree.get_by_attrs([SearchElement("role", "table")])[0]
    logging.debug("Found table: %s", table)
    initial_children = len(table.children)
    logging.info("Initial children: %d", initial_children)

    update_button = context_info_tree.get_by_attrs(
        [SearchElement("role", "push button"), SearchElement("name", "Update")]
    )[0]
    logging.debug("Found 'Update' button: %s", update_button)
    update_button.click()

    expected_total_children = initial_children
    err = "children number changed without refresh"
    no_callbacks = jab_wrapper.ignore_callbacks
    if not no_callbacks:
        # Populating the table will trigger a callback which will automatically
        #  refresh it. We just need to wait a while and adjust our expectations.
        time.sleep(0.1)
        expected_total_children = 2 * initial_children
        err = "children number didn't change after an automatic refresh"
    total_children = len(table.children)
    logging.info("Total children (pre-refresh; callbacks: %s): %d", "OFF" if no_callbacks else "ON", total_children)
    assert total_children == expected_total_children, err

    table.refresh()
    total_children = len(table.children)
    logging.info("Total children (post-refresh): %d", total_children)
    assert total_children == 2 * initial_children, "children number didn't change after a manual refresh"


def test_app_flow(jab_wrapper, app_context):
    set_focus(app_context)
    text_area = type_text_into_text_field(app_context, jab_wrapper=jab_wrapper)
    click_send_button(app_context, text_area, jab_wrapper=jab_wrapper)
    click_clear_button(app_context, text_area, jab_wrapper=jab_wrapper)
    verify_table_content(app_context)
    update_and_refresh_table(app_context, jab_wrapper=jab_wrapper)
    verify_table_content(app_context)  # should return more visible children


@pytest.fixture(
    params=[
        [["role", "push button", True], ["name", "Cl[a-z]{3}", False]],
        [["role", "push button", True], ["name", "S.*1", False]],
        [["role", "push button", True], ["name", ".*1", False]],
        [["role", "push.*", False], ["name", "Clear", False]],
    ]
)
def regex_elements(app_context, request):
    logging.info(request.param)
    search_elements = []
    for item in request.param:
        search_elements.append(SearchElement(item[0], item[1], item[2]))

    elements = app_context.get_by_attrs(search_elements)
    logging.debug("Found nodes: %s", elements)
    yield elements


def test_regex_locator_click(regex_elements):
    assert len(regex_elements) == 1, f"due to elements: {regex_elements}"
    regex_elements[0].click()


def test_depth(jab_wrapper, app_context):
    max_children = len(list(app_context))
    minimal_context = parse_elements(jab_wrapper, max_depth=2)
    min_children = len(list(minimal_context))
    logging.info("Found %d immediate nodes out of %d in total.", min_children, max_children)
    assert min_children != max_children
