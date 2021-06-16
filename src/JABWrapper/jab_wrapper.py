import os
import sys
import time
import logging

from ctypes import (
    CFUNCTYPE,
    c_long,
    c_short,
    c_void_p,
    c_wchar_p,
    wintypes,
    POINTER,
    byref,
    windll,
    c_int,
    cdll,
    WINFUNCTYPE,
    WinError,
    create_unicode_buffer
)

from typing import Callable

from JABWrapper.jab_types import (
    AccessBridgeVersionInfo,
    AccessibleActions,
    AccessibleActionsToDo,
    AccessibleKeyBindings,
    AccessibleTextItemsInfo,
    JavaObject,
    AccessibleContextInfo,
    AccessibleTextInfo,
    AccessibleTextSelectionInfo,
    MAX_STRING_SIZE,
    SHORT_STRING_SIZE
)


logging_file_handler = logging.FileHandler("jab_wrapper.log", "w", "utf-8")
logging_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(threadName)s] [%(levelname)s] %(message)s"))
logging_file_handler.setLevel(logging.DEBUG)

logging_stream_handler = logging.StreamHandler(sys.stdout)
logging_stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging_stream_handler.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[logging_file_handler, logging_stream_handler]
)


# https://stackoverflow.com/questions/21175922/enumerating-windows-trough-ctypes-in-python
WNDENUMPROC = WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32 = windll.user32
user32.EnumWindows.argtypes = [
    WNDENUMPROC,
    wintypes.LPARAM]
user32.GetWindowTextLengthW.argtypes = [
    wintypes.HWND]
user32.GetWindowTextW.argtypes = [
    wintypes.HWND,
    wintypes.LPWSTR,
    c_int]


PropertyChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, c_wchar_p, c_wchar_p, c_wchar_p)
PropertyTextChangedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
PropertyNameChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, c_wchar_p, c_wchar_p)
PropertyDescriptionChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, c_wchar_p, c_wchar_p)
PropertStateChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, c_wchar_p, c_wchar_p)
MenuSelectedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MenuDeselectedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MenuCanceledFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
FocusGainedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
FocusLostFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MouseClickedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MouseEnteredFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MouseExitedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MousePressedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MouseReleasedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
PopupMenuCanceledFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
PopupMenuWillBecomeInvisibleFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
PopupMenuWillBecomeVisibleFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)


class APIException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class _ReleaseEvent:
    def __init__(self, context, vmID, name, event, source) -> None:
        self._context = context
        self._vmID = vmID
        self._name = name
        self._event = event
        self._source = source
        self._start_exec: float = 0

    def __enter__(self):
        logging.debug(f"Received {self._name} event={self._source}")
        self._start_exec = time.perf_counter()

    def __exit__(self, type, value, traceback):
        stop_exec = time.perf_counter()
        logging.debug(f"Executed {self._name} in {(stop_exec - self._start_exec):.04f}s")
        self._context._wab.releaseJavaObject(self._vmID, self._event)


class JavaAccessBridgeWrapper:
    def __init__(self) -> None:
        self._wab: cdll = cdll.LoadLibrary(os.environ['WindowsAccessBridge'])
        self._define_functions()
        self._define_callbacks()
        self._set_callbacks()
        self._wab.Windows_run()

        self._hwnd: wintypes.HWND = None
        self._vmID = c_long()
        self.context = JavaObject()

        self._current_window: str = ''

        # Any reader can register callbacks here that are executed when AccessBridge events are seen
        self._context_callbacks: dict[str, Callable[[JavaObject], None]] = dict()

    def shutdown(self):
        self._context_callbacks = dict()
        self._remove_callbacks()

    def _define_functions(self) -> None:
        # BOOL isJavaWindow(HWND window)
        self._wab.isJavaWindow.argtypes = [wintypes.HWND]
        self._wab.isJavaWindow.restype = wintypes.BOOL
        # void Windows_run()
        self._wab.Windows_run.argtypes = []
        self._wab.Windows_run.restype = None
        # BOOL GetAccessibleContextFromHWND(HWND window, *vmID, *context)
        self._wab.getAccessibleContextFromHWND.argtypes = [wintypes.HWND, POINTER(c_long), POINTER(JavaObject)]
        self._wab.getAccessibleContextFromHWND.restype = wintypes.BOOL
        # void ReleaseJavaObject(long vmID, AccessibleContext context)
        self._wab.releaseJavaObject.argtypes = [c_long, JavaObject]
        self._wab.releaseJavaObject.restype = None
        # BOOL getAccessibleContextInfo(long vmID, AccessibleContext context, AccessibleContextInfo *info)
        self._wab.getAccessibleContextInfo.argtypes = [c_long, JavaObject, POINTER(AccessibleContextInfo)]
        self._wab.getAccessibleContextInfo.restype = wintypes.BOOL
        # AccessibleContext getAccessibleChildFromContext(long vmID, AccessibleContext context, int integer)
        self._wab.getAccessibleChildFromContext.argtypes = [c_long, JavaObject, c_int]
        self._wab.getAccessibleChildFromContext.restype = JavaObject
        # BOOL GetVersionInfo(long vmID, AccessBridgeVersionInfo *info)
        self._wab.getVersionInfo.argtypes = [c_long, POINTER(AccessBridgeVersionInfo)]
        self._wab.getVersionInfo.restype = wintypes.BOOL
        # AccessibleTextInfo GetAccessibleTextInfo(long vmID, AccessibleContext context, AccessibleTextInfo *info, int x, int y)
        self._wab.getAccessibleTextInfo.argtypes = [c_long, JavaObject, POINTER(AccessibleTextInfo), c_int, c_int]
        self._wab.getAccessibleTextInfo.restype = wintypes.BOOL
        # AccesibleTextItems GetAccessibleTextItems(long vmID, AccessibleContext context, AccesibleTextItems *items, int index)
        self._wab.getAccessibleTextItems.argtypes = [c_long, JavaObject, POINTER(AccessibleTextItemsInfo), c_int]
        self._wab.getAccessibleTextItems.restype = wintypes.BOOL
        # BOOL GetAccessibleTextSelectionInfo(long vmID, AccessibleContext context, AccessibleTextSelectionInfo *textSelection)
        self._wab.getAccessibleTextSelectionInfo.argtypes = [c_long, JavaObject, POINTER(AccessibleTextSelectionInfo)]
        self._wab.getAccessibleTextSelectionInfo.restype = wintypes.BOOL
        # BOOL GetCurrentAccessibleValueFromContext(long vmID, AccessibleContext context, wintypes.WCHAR *value, short len)
        self._wab.getCurrentAccessibleValueFromContext.argtypes = [c_long, JavaObject, POINTER(wintypes.WCHAR), c_short]
        self._wab.getCurrentAccessibleValueFromContext.restype = wintypes.BOOL
        # BOOL getAccessibleActions(long vmID, AccessibleContext context, AccessibleActions *actions)
        self._wab.getAccessibleActions.argtypes = [c_long, JavaObject, POINTER(AccessibleActions)]
        self._wab.getAccessibleActions.restypes = wintypes.BOOL
        # BOOL doAccessibleActions(long vmID, AccessibleContext context, AccessibleActionsToDo actionsToDo, bool *result, int *failure_index)
        self._wab.doAccessibleActions.argtypes = [c_long, JavaObject, AccessibleActionsToDo, POINTER(c_int)]
        self._wab.doAccessibleActions.restypes = wintypes.BOOL
        # BOOL setTextContents(long vmID, AccessibleContext context, str text)
        self._wab.setTextContents.argtypes = [c_long, JavaObject, wintypes.WCHAR * MAX_STRING_SIZE]
        self._wab.setTextContents.restypes = wintypes.BOOL
        # BOOL requestFocus(long vmID, AccessibleContext context)
        self._wab.requestFocus.argtypes = [c_long, JavaObject]
        self._wab.requestFocus.restypes = wintypes.BOOL
        # BOOL getAccessibleKeyBindings(long vmID, AccessibleContext context, AccessibleKeyBindings *bindings)
        self._wab.getAccessibleKeyBindings.argtypes = [c_long, JavaObject, POINTER(AccessibleKeyBindings)]
        self._wab.getAccessibleKeyBindings.restypes = wintypes.BOOL
        # BOOL isSameObject(long vmID, AccessibleContext context1, AccessibleContext context2)
        self._wab.isSameObject.argtypes = [c_long, JavaObject, JavaObject]
        self._wab.isSameObject.restypes = wintypes.BOOL

    def _define_callbacks(self) -> None:
        # void setPropertyChangeFP(void *f)
        self._wab.setPropertyChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyChangeFP.restype = None
        # void setPropertyTextChangeFP(void *f)
        self._wab.setPropertyTextChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyTextChangeFP.restype = None
        # void setPropertyNameChangeFP(void *f)
        self._wab.setPropertyNameChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyNameChangeFP.restype = None
        # void setPropertyDescriptionChangeFP(void *f)
        self._wab.setPropertyDescriptionChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyDescriptionChangeFP.restype = None
        # void setPropertyDescriptionChangeFP(void *f)
        self._wab.setPropertyStateChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyStateChangeFP.restype = None
        # void setMenuSelectedFP(void *f)
        self._wab.setMenuSelectedFP.argtypes = [c_void_p]
        self._wab.setMenuSelectedFP.restype = None
        # void setMenuSelectedFP(void *f)
        self._wab.setMenuDeselectedFP.argtypes = [c_void_p]
        self._wab.setMenuDeselectedFP.restype = None
        # void setMenuSelectedFP(void *f)
        self._wab.setMenuCanceledFP.argtypes = [c_void_p]
        self._wab.setMenuCanceledFP.restype = None
        # void setFocusGainedFP
        self._wab.setFocusGainedFP.argtypes = [c_void_p]
        self._wab.setFocusGainedFP.restype = None
        # void setFocusLostFP
        self._wab.setFocusLostFP.argtypes = [c_void_p]
        self._wab.setFocusLostFP.restype = None
        # void setMouseClickedFP(void *f)
        self._wab.setMouseClickedFP.argtypes = [c_void_p]
        self._wab.setMouseClickedFP.restype = None
        # void setMouseEnteredFP(void *f)
        self._wab.setMouseEnteredFP.argtypes = [c_void_p]
        self._wab.setMouseEnteredFP.restype = None
        # void setMouseExitedFP(void *f)
        self._wab.setMouseExitedFP.argtypes = [c_void_p]
        self._wab.setMouseExitedFP.restype = None
        # void setMousePressedFP(void *f)
        self._wab.setMousePressedFP.argtypes = [c_void_p]
        self._wab.setMousePressedFP.restype = None
        # void setMouseReleasedFP(void *f)
        self._wab.setMouseReleasedFP.argtypes = [c_void_p]
        self._wab.setMouseReleasedFP.restype = None
        # void setPopupMenuCanceledFP(void *f)
        self._wab.setPopupMenuCanceledFP.argtypes = [c_void_p]
        self._wab.setPopupMenuCanceledFP.restype = None
        # void setPopupMenuWillBecomeInvisibleFP(void *f)
        self._wab.setPopupMenuWillBecomeInvisibleFP.argtypes = [c_void_p]
        self._wab.setPopupMenuWillBecomeInvisibleFP.restype = None
        # void setPopupMenuWillBecomeVisibleFP(void *f)
        self._wab.setPopupMenuWillBecomeVisibleFP.argtypes = [c_void_p]
        self._wab.setPopupMenuWillBecomeVisibleFP.restype = None

    def _set_callbacks(self) -> None:
        # Property events
        self._wab.setPropertyChangeFP(self._get_callback_func("setPropertyChangeFP", PropertyChangeFP, self.property_changed))
        self._wab.setPropertyTextChangeFP(self._get_callback_func("setPropertyTextChangeFP", PropertyTextChangedFP, self.property_text_changed))
        self._wab.setPropertyNameChangeFP(self._get_callback_func("setPropertyNameChangeFP", PropertyNameChangeFP, self.property_name_change))
        self._wab.setPropertyDescriptionChangeFP(self._get_callback_func("setPropertyDescriptionChangeFP", PropertyDescriptionChangeFP,
                                                                         self.property_description_change))
        self._wab.setPropertyStateChangeFP(self._get_callback_func("setPropertyStateChangeFP", PropertStateChangeFP, self.property_state_change))
        # Menu events
        self._wab.setMenuSelectedFP(self._get_callback_func("setMenuSelectedFP", MenuSelectedFP, self.menu_selected))
        self._wab.setMenuDeselectedFP(self._get_callback_func("setMenuSelectedFP", MenuSelectedFP, self.menu_deselected))
        self._wab.setMenuCanceledFP(self._get_callback_func("setMenuCanceledFP", MenuCanceledFP, self.menu_canceled))
        # Focus events
        self._wab.setFocusGainedFP(self._get_callback_func("setFocusGainedFP", FocusGainedFP, self.focus_gained))
        self._wab.setFocusLostFP(self._get_callback_func("setFocusLostFP", FocusLostFP, self.focus_lost))
        # Mouse events
        self._wab.setMouseClickedFP(self._get_callback_func("setMouseClickedFP", MouseClickedFP, self.mouse_clicked))
        self._wab.setMouseEnteredFP(self._get_callback_func("SetMouseEnteredFP", MouseEnteredFP, self.mouse_entered))
        self._wab.setMouseExitedFP(self._get_callback_func("setMouseExitedFP", MouseExitedFP, self.mouse_exited))
        self._wab.setMousePressedFP(self._get_callback_func("setMousePressedFP", MousePressedFP, self.mouse_pressed))
        self._wab.setMouseReleasedFP(self._get_callback_func("setMouseReleasedFP", MouseReleasedFP, self.mouse_released))
        # Popup menu events
        self._wab.setPopupMenuCanceledFP(self._get_callback_func("setPopupMenuCanceledFP", PopupMenuCanceledFP, self.popup_menu_canceled))
        self._wab.setPopupMenuWillBecomeInvisibleFP(self._get_callback_func("setPopupMenuWillBecomeInvisibleFP", PopupMenuWillBecomeInvisibleFP,
                                                    self.popup_menu_will_become_invisible))
        self._wab.setPopupMenuWillBecomeVisibleFP(self._get_callback_func("setPopupMenuWillBecomeVisibleFP", PopupMenuWillBecomeVisibleFP,
                                                  self.popup_menu_will_become_visible))

    def _remove_callbacks(self) -> None:
        # Property events
        self._wab.setPropertyChangeFP(None)
        self._wab.setPropertyTextChangeFP(None)
        self._wab.setPropertyNameChangeFP(None)
        self._wab.setPropertyDescriptionChangeFP(None)
        self._wab.setPropertyStateChangeFP(None)
        # Menu events
        self._wab.setMenuSelectedFP(None)
        self._wab.setMenuDeselectedFP(None)
        self._wab.setMenuCanceledFP(None)
        # Focus events
        self._wab.setFocusGainedFP(None)
        self._wab.setFocusLostFP(None)
        # Mouse events
        self._wab.setMouseClickedFP(None)
        self._wab.setMouseEnteredFP(None)
        self._wab.setMouseExitedFP(None)
        self._wab.setMousePressedFP(None)
        self._wab.setMouseReleasedFP(None)
        # Popup menu events
        self._wab.setPopupMenuCanceledFP(None)
        self._wab.setPopupMenuWillBecomeInvisibleFP(None)
        self._wab.setPopupMenuWillBecomeVisibleFP(None)

    def _enumerate_windows(self, hwnd, lParam) -> bool:
        if not hwnd:
            logging.error("Invalid window handle={hwnd}")
            return True

        length = user32.GetWindowTextLengthW(hwnd) + 1
        buffer = create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buffer, length)
        isJava = False
        title = buffer.value
        try:
            isJava = self._wab.isJavaWindow(hwnd)
        except OSError as e:
            logging.error(f"Failed to enumerate window={hwnd} error={e}")
            return True
        if isJava:
            logging.debug(f"found java window={title}")
            if self._current_window == title:
                logging.debug(f"found matching window={title}")
                self._hwnd = hwnd
                self._vmID = c_long()
                self.context = JavaObject()
                self._wab.getAccessibleContextFromHWND(self._hwnd, byref(self._vmID), byref(self.context))

        return True

    def get_current_windows_handle(self) -> wintypes.HWND:
        return self._hwnd

    def release_object(self, context: JavaObject) -> None:
        if self._vmID and self.context:
            logging.debug(f"Releasing object={context}")
            self._wab.releaseJavaObject(self._vmID, c_long(context.value).value)

    def switch_window_by_title(self, title: str) -> None:
        """
        Switch the context to window by title
        """
        # Add the title as the current context and find the correct window
        self._current_window = title
        self._vmID = None
        self.context = None
        windows = WNDENUMPROC(self._enumerate_windows)
        if not windll.user32.EnumWindows(windows, 0):
            raise WinError()
        if not self._hwnd or not self._vmID or not self.context:
            raise Exception("Window not found")
        logging.info("Found Java window text={}, hwnd={} vmID={} context={}\n".format(
            self._current_window,
            self._hwnd,
            self._vmID,
            self.context,
        ))

    def get_child_context(self, context: JavaObject, index: c_int, ) -> JavaObject:
        return self._wab.getAccessibleChildFromContext(self._vmID, context, index)

    def get_context_info(self, context: JavaObject) -> AccessibleContextInfo:
        info = AccessibleContextInfo()
        ok = self._wab.getAccessibleContextInfo(self._vmID, context, byref(info))
        if not ok:
            raise APIException("Failed to get accessible context info")
        return info

    def get_version_info(self) -> AccessBridgeVersionInfo:
        info = AccessBridgeVersionInfo()
        ok = self._wab.getVersionInfo(self._vmID, byref(info))
        if not ok:
            raise APIException("Failed to get version info")
        return info

    def get_context_text_info(self, context: JavaObject, x: c_int, y: c_int) -> AccessibleTextInfo:
        info = AccessibleTextInfo()
        ok = self._wab.getAccessibleTextInfo(self._vmID, context, byref(info), x, y)
        if not ok:
            raise APIException("Failed to get accessible text info")
        return info

    def get_accessible_text_items(self, context: JavaObject, index: c_int) -> AccessibleTextItemsInfo:
        info = AccessibleTextItemsInfo()
        ok = self._wab.getAccessibleTextItems(self._vmID, context, byref(info), 0)
        if not ok:
            raise APIException("Failed to get accessible text  context")
        return info

    def get_accessible_text_selection_info(self, context: JavaObject) -> AccessibleTextSelectionInfo:
        info = AccessibleTextSelectionInfo()
        ok = self._wab.getAccessibleTextSelectionInfo(self._vmID, context, byref(info))
        if not ok:
            raise APIException("Failed to get accessible text selection info")
        return info

    def get_current_accessible_value_from_context(self, context: JavaObject) -> str:
        buf = create_unicode_buffer(SHORT_STRING_SIZE + 1)
        ok = self._wab.getCurrentAccessibleValueFromContext(self._vmID, context, buf, SHORT_STRING_SIZE)
        if not ok:
            raise APIException("Failed to get current accessible value from context")
        return buf.value

    def get_accessible_actions(self, context: JavaObject) -> AccessibleActions:
        actions = AccessibleActions()
        ok = self._wab.getAccessibleActions(self._vmID, context, byref(actions))
        if not ok:
            raise APIException("Failed to get accessible actions")
        return actions

    def do_accessible_actions(self, context: JavaObject, actions: AccessibleActionsToDo) -> None:
        index = c_int()
        ok = self._wab.doAccessibleActions(self._vmID, context, actions, byref(index))
        if not ok:
            raise APIException("Action failed at index={}".format(index))

    def set_text_contents(self, context: JavaObject, text: str) -> None:
        buf = create_unicode_buffer(text, MAX_STRING_SIZE)
        ok = self._wab.setTextContents(self._vmID, context, buf)
        if not ok:
            raise APIException("Failed to set field contents")

    def request_focus(self, context: JavaObject) -> None:
        ok = self._wab.requestFocus(self._vmID, context)
        if not ok:
            raise APIException("Failed to request focus")

    def get_accessible_key_bindings(self, context: JavaObject) -> AccessibleKeyBindings:
        key_bindings = AccessibleKeyBindings()
        ok = self._wab.getAccessibleKeyBindings(self._vmID, context, byref(key_bindings))
        if not ok:
            raise APIException("Failed to get key bindings")
        return key_bindings

    def is_same_object(self, context_from: JavaObject, context_to: JavaObject) -> bool:
        return self._wab.isSameObject(self._vmID, context_from, context_to)

    def register_callback(self, name: str, callback: Callable[[JavaObject], None]) -> None:
        self._context_callbacks[name] = callback

    """
    Define the callback handlers
    """
    def _get_callback_func(self, name, wrapper, callback):
        def func(*args):
            callback(*args)
        runner = wrapper(func)
        setattr(self, name, runner)
        return runner

    # TODO: handle additional values (need to find an element to test this)
    def property_changed(self, vmID: c_long, event: JavaObject, source: JavaObject, property, old_value, new_value):
        with _ReleaseEvent(self, vmID, "property_change", event, source):
            if 'property_change' in self._context_callbacks:
                self._context_callbacks['property_change'](source, property, old_value, new_value)

    def property_text_changed(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "property_text_changed", event, source):
            if 'property_text_changed' in self._context_callbacks:
                self._context_callbacks['property_text_changed'](source)

    def property_name_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str):
        with _ReleaseEvent(self, vmID, "property_name_change", event, source):
            if 'property_name_change' in self._context_callbacks:
                self._context_callbacks['property_name_change'](source, old_value, new_value)

    def property_description_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str):
        with _ReleaseEvent(self, vmID, "property_description_change", event, source):
            if 'property_description_change' in self._context_callbacks:
                self._context_callbacks['property_description_change'](source, old_value, new_value)

    def property_state_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str):
        with _ReleaseEvent(self, vmID, "property_state_change", event, source):
            if 'property_state_change' in self._context_callbacks:
                self._context_callbacks['property_state_change'](source, old_value, new_value)

    def menu_selected(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "menu_selected", event, source):
            if 'menu_selected' in self._context_callbacks:
                self._context_callbacks['menu_selected'](source)

    def menu_deselected(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "menu_deselected", event, source):
            if 'menu_deselected' in self._context_callbacks:
                self._context_callbacks['menu_deselected'](source)

    def menu_canceled(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "menu_canceled", event, source):
            if 'menu_canceled' in self._context_callbacks:
                self._context_callbacks['menu_canceled'](source)

    def focus_gained(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "focus_gained", event, source):
            if 'focus_gained' in self._context_callbacks:
                self._context_callbacks['focus_gained'](source)

    def focus_lost(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "focus_lost", event, source):
            if 'focus_lost' in self._context_callbacks:
                self._context_callbacks['focus_lost'](source)

    def mouse_clicked(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "mouse_clicked", event, source):
            if 'mouse_clicked' in self._context_callbacks:
                self._context_callbacks['mouse_clicked'](source)

    def mouse_entered(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "mouse_entered", event, source):
            if 'mouse_entered' in self._context_callbacks:
                self._context_callbacks['mouse_entered'](source)

    def mouse_exited(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "mouse_exited", event, source):
            if 'mouse_exited' in self._context_callbacks:
                self._context_callbacks['mouse_exited'](source)

    def mouse_pressed(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "mouse_pressed", event, source):
            if 'mouse_pressed' in self._context_callbacks:
                self._context_callbacks['mouse_pressed'](source)

    def mouse_released(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "mouse_released", event, source):
            if 'mouse_released' in self._context_callbacks:
                self._context_callbacks['mouse_released'](source)

    def popup_menu_canceled(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "popup_menu_canceled", event, source):
            if 'popup_menu_canceled' in self._context_callbacks:
                self._context_callbacks['popup_menu_canceled'](source)

    def popup_menu_will_become_invisible(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "popup_menu_will_become_invisible", event, source):
            if 'popup_menu_will_become_invisible' in self._context_callbacks:
                self._context_callbacks['popup_menu_will_become_invisible'](source)

    def popup_menu_will_become_visible(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "popup_menu_will_become_visible", event, source):
            if 'popup_menu_will_become_visible' in self._context_callbacks:
                self._context_callbacks['popup_menu_will_become_visible'](source)
