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

from typing import Callable, List, Tuple

from JABWrapper.jab_types import (
    AccessBridgeVersionInfo,
    AccessibleActions,
    AccessibleActionsToDo,
    AccessibleKeyBindings,
    AccessibleRelationSetInfo,
    AccessibleTextAttributesInfo,
    AccessibleTextItemsInfo,
    AccessibleTextRectInfo,
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
PropertyNameChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, c_wchar_p, c_wchar_p)
PropertyDescriptionChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, c_wchar_p, c_wchar_p)
PropertStateChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, c_wchar_p, c_wchar_p)
PropertyValueChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, c_wchar_p, c_wchar_p)
PropertySelectionChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
PropertyTextChangedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
PropertyCaretChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, c_int, c_int)
PropertyVisibleDataChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
PropertyChildChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, JavaObject, JavaObject)
PropertyActiveDescendentChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, JavaObject, JavaObject)
PropertyTableModelChangeFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject, c_wchar_p, c_wchar_p)
FocusGainedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
FocusLostFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
CaretUpdateFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MouseClickedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MouseEnteredFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MouseExitedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MousePressedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MouseReleasedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MenuSelectedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MenuDeselectedFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
MenuCanceledFP = CFUNCTYPE(None, c_long, JavaObject, JavaObject)
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
        logging.debug("Loading WindowsAccessBridge")
        if "RC_JAVA_ACCESS_BRIDGE_DLL" not in os.environ:
            raise OSError("Environment variable: RC_JAVA_ACCESS_BRIDGE_DLL not found")
        if not os.path.isfile(os.path.normpath(os.environ['RC_JAVA_ACCESS_BRIDGE_DLL'])):
            raise FileNotFoundError(f"File not found: {os.environ['RC_JAVA_ACCESS_BRIDGE_DLL']}")
        self._wab: cdll = cdll.LoadLibrary(os.path.normpath(os.environ['RC_JAVA_ACCESS_BRIDGE_DLL']))
        logging.debug("WindowsAccessBridge loaded succesfully")
        self._define_functions()
        self._define_callbacks()
        self._set_callbacks()
        self._wab.Windows_run()

        self._hwnd: wintypes.HWND = None
        self._vmID = c_long()
        self.context = JavaObject()

        self._current_window: str = ''

        # Any reader can register callbacks here that are executed when AccessBridge events are seen
        self._context_callbacks: dict[str, List[Callable[[JavaObject], None]]] = dict()

    def shutdown(self):
        self._context_callbacks = dict()
        self._remove_callbacks()

    def _define_functions(self) -> None:
        # void Windows_run()
        self._wab.Windows_run.argtypes = []
        self._wab.Windows_run.restype = None

        # void ReleaseJavaObject(long vmID, AccessibleContext context)
        self._wab.releaseJavaObject.argtypes = [c_long, JavaObject]
        self._wab.releaseJavaObject.restype = None

        # BOOL GetVersionInfo(long vmID, AccessBridgeVersionInfo *info)
        self._wab.getVersionInfo.argtypes = [c_long, POINTER(AccessBridgeVersionInfo)]
        self._wab.getVersionInfo.restype = wintypes.BOOL

        # Accessible context
        # BOOL isJavaWindow(HWND window)
        self._wab.isJavaWindow.argtypes = [wintypes.HWND]
        self._wab.isJavaWindow.restype = wintypes.BOOL
        # BOOL isSameObject(long vmID, AccessibleContext context_from, AccessibleContext context_to)
        self._wab.isSameObject.argtypes = [c_long, JavaObject, JavaObject]
        self._wab.isSameObject.restypes = wintypes.BOOL
        # BOOL GetAccessibleContextFromHWND(HWND window, long *vmID, AccessibleContext *context)
        self._wab.getAccessibleContextFromHWND.argtypes = [wintypes.HWND, POINTER(c_long), POINTER(JavaObject)]
        self._wab.getAccessibleContextFromHWND.restype = wintypes.BOOL
        # HWND getHWNDFromAccessibleContext(long vmID, AccessibleContext context)
        self._wab.getHWNDFromAccessibleContext.argtypes = [c_long, JavaObject]
        self._wab.getHWNDFromAccessibleContext.restype = wintypes.HWND
        # BOOL getAccessibleContextAt(long vmID, AccessibleContext parent, int x, int y, AccessibleContext *context)
        self._wab.getAccessibleContextAt.argtypes = [c_long, JavaObject, c_int, c_int, POINTER(JavaObject)]
        self._wab.getAccessibleContextAt.restype = wintypes.BOOL
        # TODO: getAccessibleContextWithFocus
        # BOOL getAccessibleContextInfo(long vmID, AccessibleContext context, AccessibleContextInfo *info)
        self._wab.getAccessibleContextInfo.argtypes = [c_long, JavaObject, POINTER(AccessibleContextInfo)]
        self._wab.getAccessibleContextInfo.restype = wintypes.BOOL
        # AccessibleContext getAccessibleChildFromContext(long vmID, AccessibleContext context, int integer)
        self._wab.getAccessibleChildFromContext.argtypes = [c_long, JavaObject, c_int]
        self._wab.getAccessibleChildFromContext.restype = JavaObject
        # JavaObject getAccessibleParentFromContext(c_long vmID, JavaObject child_context)
        self._wab.getAccessibleParentFromContext.argtypes = [c_long, JavaObject]
        self._wab.getAccessibleParentFromContext.restype = JavaObject

        # Accessible table
        # TODO: getAccessibleTableInfo
        # TODO: getAccessibleTableCellInfo
        # TODO: getAccessibleTableRowHeader
        # TODO: getAccessibleTableColumnHeader
        # TODO: getAccessibleTableRowDescription
        # TODO: getAccessibleTableColumnDescription
        # TODO: getAccessibleTableRowSelectionCount
        # TODO: isAccessibleTableRowSelected
        # TODO: getAccessibleTableRowSelections
        # TODO: getAccessibleTableColumnSelectionCount
        # TODO: isAccessibleTableColumnSelected
        # TODO: getAccessibleTableColumnSelections
        # TODO: getAccessibleTableRow
        # TODO: getAccessibleTableColumn
        # TODO: getAccessibleTableIndex

        # AccessibleRelationSet
        # BOOL getAccessibleRelationSet(long vmID, AccessibleContext accessibleContext, AccessibleRelationSetInfo *relationSetInfo)
        self._wab.getAccessibleRelationSet.argtypes = [c_long, JavaObject, POINTER(AccessibleRelationSetInfo)]
        self._wab.getAccessibleRelationSet.restype = wintypes.BOOL

        # AccessibleHypertext
        # TODO: getAccessibleHypertext
        # TODO: activateAccessibleHyperlink
        # TODO: getAccessibleHyperlinkCount
        # TODO: getAccessibleHypertextExt
        # TODO: getAccessibleHypertextLinkIndex
        # TODO: getAccessibleHyperlink

        # Accessible KeyBindings, Icons and Actions
        # BOOL getAccessibleKeyBindings(long vmID, AccessibleContext context, AccessibleKeyBindings *bindings)
        self._wab.getAccessibleKeyBindings.argtypes = [c_long, JavaObject, POINTER(AccessibleKeyBindings)]
        self._wab.getAccessibleKeyBindings.restypes = wintypes.BOOL
        # TODO: getAccessibleIcons
        # BOOL getAccessibleActions(long vmID, AccessibleContext context, AccessibleActions *actions)
        self._wab.getAccessibleActions.argtypes = [c_long, JavaObject, POINTER(AccessibleActions)]
        self._wab.getAccessibleActions.restypes = wintypes.BOOL
        # BOOL doAccessibleActions(long vmID, AccessibleContext context, AccessibleActionsToDo actionsToDo, bool *result, int *failure_index)
        self._wab.doAccessibleActions.argtypes = [c_long, JavaObject, AccessibleActionsToDo, POINTER(c_int)]
        self._wab.doAccessibleActions.restypes = wintypes.BOOL

        # AccessibleText
        # AccessibleTextInfo GetAccessibleTextInfo(long vmID, AccessibleContext context, AccessibleTextInfo *info, int x, int y)
        self._wab.getAccessibleTextInfo.argtypes = [c_long, JavaObject, POINTER(AccessibleTextInfo), c_int, c_int]
        self._wab.getAccessibleTextInfo.restype = wintypes.BOOL
        # AccesibleTextItems GetAccessibleTextItems(long vmID, AccessibleContext context, AccesibleTextItems *items, int index)
        self._wab.getAccessibleTextItems.argtypes = [c_long, JavaObject, POINTER(AccessibleTextItemsInfo), c_int]
        self._wab.getAccessibleTextItems.restype = wintypes.BOOL
        # BOOL GetAccessibleTextSelectionInfo(long vmID, AccessibleContext context, AccessibleTextSelectionInfo *textSelection)
        self._wab.getAccessibleTextSelectionInfo.argtypes = [c_long, JavaObject, POINTER(AccessibleTextSelectionInfo)]
        self._wab.getAccessibleTextSelectionInfo.restype = wintypes.BOOL
        # BOOL getAccessibleTextAttributes(long vmID, AccessibleContext context, int index, AccessibleTextAttributesInfo *attributesInfo)
        self._wab.getAccessibleTextAttributes.argtypes = [c_long, JavaObject, c_int, POINTER(AccessibleTextAttributesInfo)]
        self._wab.getAccessibleTextAttributes.restype = wintypes.BOOL
        # BOOL getAccessibleTextRect(long vmID, AccessibleContext context, AccessibleTextRectInfo *rectInfo, int index)
        self._wab.getAccessibleTextRect.argtypes = [c_long, JavaObject, POINTER(AccessibleTextRectInfo), c_int]
        self._wab.getAccessibleTextRect.restype = wintypes.BOOL
        # BOOL getAccessibleTextLineBounds(long vmID, AccessibleContext context, int index, int *startIndex, int *endIndex)
        self._wab.getAccessibleTextLineBounds.argtypes = [c_long, JavaObject, c_int, POINTER(c_int), POINTER(c_int)]
        self._wab.getAccessibleTextLineBounds.restype = wintypes.BOOL
        # BOOL getAccessibleTextRange(long vmID, AccessibleContext context, int start, int end, c_wchar_p *text, short len)
        self._wab.getAccessibleTextRange.argtypes = [c_long, JavaObject, c_int, c_int, c_wchar_p, c_short]
        self._wab.getAccessibleTextRange.restype = wintypes.BOOL

        # AccessibleValue
        # BOOL getCurrentAccessibleValueFromContext(long vmID, AccessibleContext context, wintypes.WCHAR *value, short len)
        self._wab.getCurrentAccessibleValueFromContext.argtypes = [c_long, JavaObject, c_wchar_p, c_short]
        self._wab.getCurrentAccessibleValueFromContext.restype = wintypes.BOOL
        # BOOL getMaximumAccessibleValueFromContext(long vmID, AccessibleContext context, wintypes.WCHAR *value, short len)
        self._wab.getMaximumAccessibleValueFromContext.argtypes = [c_long, JavaObject, c_wchar_p, c_short]
        self._wab.getMaximumAccessibleValueFromContext.restype = wintypes.BOOL
        # BOOL getMinimumAccessibleValueFromContext(long vmID, AccessibleContext context, wintypes.WCHAR *value, short len)
        self._wab.getMinimumAccessibleValueFromContext.argtypes = [c_long, JavaObject, c_wchar_p, c_short]
        self._wab.getMinimumAccessibleValueFromContext.restype = wintypes.BOOL

        # AccessibleSelection
        # TODO: addAccessibleSelectionFromContext
        # TODO: clearAccessibleSelectionFromContext
        # TODO: getAccessibleSelectionFromContext
        # TODO: getAccessibleSelectionCountFromContext
        # TODO: isAccessibleChildSelectedFromContext
        # TODO: removeAccessibleSelectionFromContext
        # TODO: selectAllAccessibleSelectionFromContext

        # Utility
        # BOOL setTextContents(long vmID, AccessibleContext context, str text)
        self._wab.setTextContents.argtypes = [c_long, JavaObject, wintypes.WCHAR * MAX_STRING_SIZE]
        self._wab.setTextContents.restypes = wintypes.BOOL
        # TODO: getParentWithRole
        # TODO: getParentWithRoleElseRoot
        # TODO: getTopLevelObject
        # TODO: getObjectDepth
        # TODO: getActiveDescendent
        # BOOL getVirtualAccessibleNameFP(long vmID, AccessibleContext context, str name, int len)
        self._wab.getVirtualAccessibleName.argtypes = [c_long, JavaObject, wintypes.WCHAR * MAX_STRING_SIZE, c_int]
        self._wab.getVirtualAccessibleName.restype = wintypes.BOOL
        # BOOL requestFocus(long vmID, AccessibleContext context)
        self._wab.requestFocus.argtypes = [c_long, JavaObject]
        self._wab.requestFocus.restypes = wintypes.BOOL
        # TODO: selectTextRange
        # TODO: getTextAttributesInRange
        # TODO: getVisibleChildrenCount
        # TODO: getVisibleChildren
        # TODO: setCaretPosition
        # TODO: getCaretLocation
        # TODO: getEventsWaitingFP

    def _define_callbacks(self) -> None:
        # Property events
        self._wab.setPropertyChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyChangeFP.restype = None
        self._wab.setPropertyNameChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyNameChangeFP.restype = None
        self._wab.setPropertyDescriptionChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyDescriptionChangeFP.restype = None
        self._wab.setPropertyStateChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyStateChangeFP.restype = None
        self._wab.setPropertyValueChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyValueChangeFP.restype = None
        self._wab.setPropertySelectionChangeFP.argtypes = [c_void_p]
        self._wab.setPropertySelectionChangeFP.restype = None
        self._wab.setPropertyTextChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyTextChangeFP.restype = None
        self._wab.setPropertyCaretChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyCaretChangeFP.restype = None
        self._wab.setPropertyVisibleDataChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyVisibleDataChangeFP.restype = None
        self._wab.setPropertyChildChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyChildChangeFP.restype = None
        self._wab.setPropertyActiveDescendentChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyActiveDescendentChangeFP.restype = None
        self._wab.setPropertyTableModelChangeFP.argtypes = [c_void_p]
        self._wab.setPropertyTableModelChangeFP.restype = None
        # Menu events
        self._wab.setMenuSelectedFP.argtypes = [c_void_p]
        self._wab.setMenuSelectedFP.restype = None
        self._wab.setMenuDeselectedFP.argtypes = [c_void_p]
        self._wab.setMenuDeselectedFP.restype = None
        self._wab.setMenuCanceledFP.argtypes = [c_void_p]
        self._wab.setMenuCanceledFP.restype = None
        # Focus events
        self._wab.setFocusGainedFP.argtypes = [c_void_p]
        self._wab.setFocusGainedFP.restype = None
        self._wab.setFocusLostFP.argtypes = [c_void_p]
        self._wab.setFocusLostFP.restype = None
        # Caret update events
        self._wab.setCaretUpdateFP.argtypes = [c_void_p]
        self._wab.setCaretUpdateFP.restype = None
        # Mouse events
        self._wab.setMouseClickedFP.argtypes = [c_void_p]
        self._wab.setMouseClickedFP.restype = None
        self._wab.setMouseEnteredFP.argtypes = [c_void_p]
        self._wab.setMouseEnteredFP.restype = None
        self._wab.setMouseExitedFP.argtypes = [c_void_p]
        self._wab.setMouseExitedFP.restype = None
        self._wab.setMousePressedFP.argtypes = [c_void_p]
        self._wab.setMousePressedFP.restype = None
        self._wab.setMouseReleasedFP.argtypes = [c_void_p]
        self._wab.setMouseReleasedFP.restype = None
        # Popup menu events
        self._wab.setPopupMenuCanceledFP.argtypes = [c_void_p]
        self._wab.setPopupMenuCanceledFP.restype = None
        self._wab.setPopupMenuWillBecomeInvisibleFP.argtypes = [c_void_p]
        self._wab.setPopupMenuWillBecomeInvisibleFP.restype = None
        self._wab.setPopupMenuWillBecomeVisibleFP.argtypes = [c_void_p]
        self._wab.setPopupMenuWillBecomeVisibleFP.restype = None

    def _set_callbacks(self) -> None:
        # Property events
        self._wab.setPropertyChangeFP(self._get_callback_func("setPropertyChangeFP", PropertyChangeFP, self.property_change))
        self._wab.setPropertyNameChangeFP(self._get_callback_func("setPropertyNameChangeFP", PropertyNameChangeFP, self.property_name_change))
        self._wab.setPropertyDescriptionChangeFP(self._get_callback_func("setPropertyDescriptionChangeFP", PropertyDescriptionChangeFP,
                                                                         self.property_description_change))
        self._wab.setPropertyStateChangeFP(self._get_callback_func("setPropertyStateChangeFP", PropertStateChangeFP, self.property_state_change))
        self._wab.setPropertyValueChangeFP(self._get_callback_func("setPropertyValueChangeFP", PropertyValueChangeFP, self.property_value_change))
        self._wab.setPropertySelectionChangeFP(self._get_callback_func("setPropertySelectionChangeFP", PropertySelectionChangeFP,
                                                                       self.property_selection_change))
        self._wab.setPropertyTextChangeFP(self._get_callback_func("setPropertyTextChangeFP", PropertyTextChangedFP, self.property_text_change))
        self._wab.setPropertyCaretChangeFP(self._get_callback_func("setPropertyCaretChangeFP", PropertyCaretChangeFP, self.property_caret_change))
        self._wab.setPropertyVisibleDataChangeFP(self._get_callback_func("setPropertyVisibleDataChangeFP", PropertyVisibleDataChangeFP,
                                                                         self.property_visible_data_change))
        self._wab.setPropertyChildChangeFP(self._get_callback_func("setPropertyChildChangeFP", PropertyChildChangeFP, self.property_child_change))
        self._wab.setPropertyActiveDescendentChangeFP(self._get_callback_func("setPropertyActiveDescendentChangeFP", PropertyActiveDescendentChangeFP,
                                                                              self.property_active_descendent_change))
        self._wab.setPropertyTableModelChangeFP(self._get_callback_func("setPropertyTableModelChangeFP", PropertyTableModelChangeFP,
                                                                        self.property_table_model_change))
        # Menu events
        self._wab.setMenuSelectedFP(self._get_callback_func("setMenuSelectedFP", MenuSelectedFP, self.menu_selected))
        self._wab.setMenuDeselectedFP(self._get_callback_func("setMenuDeselectedFP", MenuDeselectedFP, self.menu_deselected))
        self._wab.setMenuCanceledFP(self._get_callback_func("setMenuCanceledFP", MenuCanceledFP, self.menu_canceled))
        # Focus events
        self._wab.setFocusGainedFP(self._get_callback_func("setFocusGainedFP", FocusGainedFP, self.focus_gained))
        self._wab.setFocusLostFP(self._get_callback_func("setFocusLostFP", FocusLostFP, self.focus_lost))
        # Caret update events
        self._wab.setCaretUpdateFP(self._get_callback_func("setCaretUpdateFP", CaretUpdateFP, self.caret_update))
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
        self._wab.setPropertyNameChangeFP(None)
        self._wab.setPropertyDescriptionChangeFP(None)
        self._wab.setPropertyStateChangeFP(None)
        self._wab.setPropertyValueChangeFP(None)
        self._wab.setPropertySelectionChangeFP(None)
        self._wab.setPropertyTextChangeFP(None)
        self._wab.setPropertyCaretChangeFP(None)
        self._wab.setPropertyVisibleDataChangeFP(None)
        self._wab.setPropertyChildChangeFP(None)
        self._wab.setPropertyActiveDescendentChangeFP(None)
        self._wab.setPropertyTableModelChangeFP(None)
        # Menu events
        self._wab.setMenuSelectedFP(None)
        self._wab.setMenuDeselectedFP(None)
        self._wab.setMenuCanceledFP(None)
        # Focus events
        self._wab.setFocusGainedFP(None)
        self._wab.setFocusLostFP(None)
        # Caret update events
        self._wab.setCaretUpdateFP(None)
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

    def set_hwnd(self, hwnd: wintypes.HWND) -> None:
        self._hwnd = hwnd

    def set_context(self, vm_id: c_long, context: JavaObject) -> None:
        self._vmID = vm_id
        self.context = context

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

    def get_accessible_context_from_hwnd(self, hwnd: wintypes.HWND) -> Tuple[c_long, JavaObject]:
        vm_id = c_long()
        context = JavaObject()
        ok = self._wab.getAccessibleContextFromHWND(hwnd, byref(vm_id), byref(context))
        if not ok:
            raise APIException("Failed to get accessible context from HWND")
        return vm_id, context

    def get_hwnd_from_accessible_context(self, context) -> wintypes.HWND:
        return self._wab.getHWNDFromAccessibleContext(self._vmID, context)

    def get_accessible_context_at(self, parent: JavaObject, x: int, y: int) -> JavaObject:
        context = JavaObject()
        ok = self._wab.getAccessibleContextAt(self._vmID, parent, x, y, byref(context))
        if not ok:
            raise APIException("Failed to get accessible context at={x},{y}")
        return context

    def get_child_context(self, context: JavaObject, index: c_int, ) -> JavaObject:
        return self._wab.getAccessibleChildFromContext(self._vmID, context, index)

    def get_accessible_parent_from_context(self, context) -> JavaObject:
        return self._wab.getAccessibleParentFromContext(self._vmID, context)

    def get_accessible_relation_set_info(self, context: JavaObject) -> AccessibleRelationSetInfo:
        relation_set_info = AccessibleRelationSetInfo()
        logging.info("getting rel set")
        ok = self._wab.getAccessibleRelationSet(self._vmID, context, byref(relation_set_info))
        logging.info(f"rel set={ok}")
        if not ok:
            raise APIException("Failed to get accessible relation set info")
        return relation_set_info

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

    def get_accessible_text_attributes(self, context: JavaObject, index: int) -> AccessibleTextAttributesInfo:
        attributes_info = AccessibleTextAttributesInfo()
        ok = self._wab.getAccessibleTextAttributes(self._vmID, context, index, attributes_info)
        if not ok:
            raise APIException("Failed to get accessible text attributes info")
        return attributes_info

    def get_accessible_text_rect(self, context: JavaObject, index: int) -> AccessibleTextRectInfo:
        rect_info = AccessibleTextRectInfo()
        ok = self._wab.getAccessibleTextRect(self._vmID, context, byref(rect_info), index)
        if not ok:
            raise APIException("Failed to get accessible text rect info")
        return rect_info

    def get_accessible_text_line_bounds(self, context, index) -> Tuple[int, int]:
        start_index = c_int()
        end_index = c_int()
        ok = self._wab.getAccessibleTextLineBounds(self._vmID, context, index, byref(start_index), byref(end_index))
        if not ok:
            raise APIException(f"Failed to get accessible text line bounds at={index}")
        return start_index, end_index

    def get_accessible_text_range(self, context: JavaObject, start_index: c_int, end_index: c_int, length: c_short) -> str:
        buf = create_unicode_buffer(length)
        ok = self._wab.getAccessibleTextRange(self._vmID, context, start_index, end_index, buf, length)
        if not ok:
            raise APIException("Failed to get accessible range")
        return buf.value

    def get_current_accessible_value_from_context(self, context: JavaObject) -> str:
        buf = create_unicode_buffer(SHORT_STRING_SIZE)
        ok = self._wab.getCurrentAccessibleValueFromContext(self._vmID, context, buf, SHORT_STRING_SIZE)
        if not ok:
            raise APIException("Failed to get current accessible value from context")
        return buf.value

    def get_maximum_accessible_value_from_context(self, context: JavaObject) -> str:
        buf = create_unicode_buffer(SHORT_STRING_SIZE)
        ok = self._wab.getMaximumAccessibleValueFromContext(self._vmID, context, buf, SHORT_STRING_SIZE)
        if not ok:
            raise APIException("Failed to get maximum accessible value from context")
        return buf.value

    def get_minimum_accessible_value_from_context(self, context: JavaObject) -> str:
        buf = create_unicode_buffer(SHORT_STRING_SIZE)
        ok = self._wab.getMinimumAccessibleValueFromContext(self._vmID, context, buf, SHORT_STRING_SIZE)
        if not ok:
            raise APIException("Failed to get minimum accessible value from context")
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

    def get_virtual_accessible_name(self, context: JavaObject):
        buf = create_unicode_buffer(MAX_STRING_SIZE)
        ok = self._wab.getVirtualAccessibleName(self._vmID, context, buf, MAX_STRING_SIZE)
        if not ok:
            raise APIException("Failed to get virtual accessible name")
        return buf.value

    def register_callback(self, name: str, callback: Callable[[JavaObject], None]) -> None:
        logging.debug(f"Registering callback={name}")
        if name in self._context_callbacks:
            self._context_callbacks[name].append(callback)
        else:
            self._context_callbacks[name] = [callback]

    """
    Define the callback handlers
    """
    def _get_callback_func(self, name, wrapper, callback):
        def func(*args):
            callback(*args)
        runner = wrapper(func)
        setattr(self, name, runner)
        return runner

    def property_change(self, vmID: c_long, event: JavaObject, source: JavaObject, property, old_value, new_value):
        with _ReleaseEvent(self, vmID, "property_change", event, source):
            if 'property_change' in self._context_callbacks:
                for cp in self._context_callbacks['property_change']:
                    cp(source, property, old_value, new_value)

    def property_name_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str):
        with _ReleaseEvent(self, vmID, "property_name_change", event, source):
            if 'property_name_change' in self._context_callbacks:
                for cp in self._context_callbacks['property_name_change']:
                    cp(source, old_value, new_value)

    def property_description_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str):
        with _ReleaseEvent(self, vmID, "property_description_change", event, source):
            if 'property_description_change' in self._context_callbacks:
                for cp in self._context_callbacks['property_description_change']:
                    cp(source, old_value, new_value)

    def property_state_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str):
        with _ReleaseEvent(self, vmID, "property_state_change", event, source):
            if 'property_state_change' in self._context_callbacks:
                for cp in self._context_callbacks['property_state_change']:
                    cp(source, old_value, new_value)

    def property_value_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str):
        with _ReleaseEvent(self, vmID, "property_value_change", event, source):
            if 'property_value_change' in self._context_callbacks:
                for cp in self._context_callbacks['property_value_change']:
                    cp(source, old_value, new_value)

    def property_selection_change(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "property_selection_change", event, source):
            if 'property_selection_change' in self._context_callbacks:
                for cp in self._context_callbacks['property_selection_change']:
                    cp(source)

    def property_text_change(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "property_text_change", event, source):
            if 'property_text_change' in self._context_callbacks:
                for cp in self._context_callbacks['property_text_change']:
                    cp(source)

    def property_caret_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_pos: int, new_pos: int):
        with _ReleaseEvent(self, vmID, "set_property_caret_change", event, source):
            if 'set_property_caret_change' in self._context_callbacks:
                for cp in self._context_callbacks['set_property_caret_change']:
                    cp(source, old_pos, new_pos)

    def property_visible_data_change(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "property_visible_data_change", event, source):
            if 'property_visible_data_change' in self._context_callbacks:
                for cp in self._context_callbacks['property_visible_data_change']:
                    cp(source)

    def property_child_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_child: JavaObject, new_child: JavaObject):
        with _ReleaseEvent(self, vmID, "property_child_change", event, source):
            if 'property_child_change' in self._context_callbacks:
                for cp in self._context_callbacks['property_child_change']:
                    cp(source, old_child, new_child)

    def property_active_descendent_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_child: JavaObject, new_child: JavaObject):
        with _ReleaseEvent(self, vmID, "property_active_descendent_change", event, source):
            if 'property active descendent change' in self._context_callbacks:
                for cp in self._context_callbacks['property_active_descendent_change']:
                    cp(source, old_child, new_child)

    def property_table_model_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str):
        with _ReleaseEvent(self, vmID, "property_table_model_change", event, source):
            if 'property_table_model_change' in self._context_callbacks:
                for cp in self._context_callbacks['property_table_model_change']:
                    cp(source, old_value, new_value)

    def menu_selected(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "menu_selected", event, source):
            if 'menu_selected' in self._context_callbacks:
                for cp in self._context_callbacks['menu_selected']:
                    cp(source)

    def menu_deselected(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "menu_deselected", event, source):
            if 'menu_deselected' in self._context_callbacks:
                for cp in self._context_callbacks['menu_deselected']:
                    cp(source)

    def menu_canceled(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "menu_canceled", event, source):
            if 'menu_canceled' in self._context_callbacks:
                for cp in self._context_callbacks['menu_canceled']:
                    cp(source)

    def focus_gained(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "focus_gained", event, source):
            if 'focus_gained' in self._context_callbacks:
                for cp in self._context_callbacks['focus_gained']:
                    cp(source)

    def focus_lost(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "focus_lost", event, source):
            if 'focus_lost' in self._context_callbacks:
                for cp in self._context_callbacks['focus_lost']:
                    cp(source)

    def caret_update(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "caret_update", event, source):
            if 'caret_update' in self._context_callbacks:
                for cp in self._context_callbacks['caret_update']:
                    cp(source)

    def mouse_clicked(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "mouse_clicked", event, source):
            if 'mouse_clicked' in self._context_callbacks:
                for cp in self._context_callbacks['mouse_clicked']:
                    cp(source)

    def mouse_entered(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "mouse_entered", event, source):
            if 'mouse_entered' in self._context_callbacks:
                for cp in self._context_callbacks['mouse_entered']:
                    cp(source)

    def mouse_exited(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "mouse_exited", event, source):
            if 'mouse_exited' in self._context_callbacks:
                for cp in self._context_callbacks['mouse_exited']:
                    cp(source)

    def mouse_pressed(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "mouse_pressed", event, source):
            if 'mouse_pressed' in self._context_callbacks:
                for cp in self._context_callbacks['mouse_pressed']:
                    cp(source)

    def mouse_released(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "mouse_released", event, source):
            if 'mouse_released' in self._context_callbacks:
                for cp in self._context_callbacks['mouse_released']:
                    cp(source)

    def popup_menu_canceled(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "popup_menu_canceled", event, source):
            if 'popup_menu_canceled' in self._context_callbacks:
                for cp in self._context_callbacks['popup_menu_canceled']:
                    cp(source)

    def popup_menu_will_become_invisible(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "popup_menu_will_become_invisible", event, source):
            if 'popup_menu_will_become_invisible' in self._context_callbacks:
                for cp in self._context_callbacks['popup_menu_will_become_invisible']:
                    cp(source)

    def popup_menu_will_become_visible(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with _ReleaseEvent(self, vmID, "popup_menu_will_become_visible", event, source):
            if 'popup_menu_will_become_visible' in self._context_callbacks:
                for cp in self._context_callbacks['popup_menu_will_become_visible']:
                    cp(source)
