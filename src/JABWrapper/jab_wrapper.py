import logging
import os
import re
import sys
from ctypes import (
    CFUNCTYPE,
    POINTER,
    WINFUNCTYPE,
    WinError,
    byref,
    c_int,
    c_long,
    c_short,
    c_void_p,
    c_wchar,
    c_wchar_p,
    cdll,
    create_unicode_buffer,
    windll,
    wintypes,
)
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import win32process

from JABWrapper.jab_types import (
    MAX_STRING_SIZE,
    SHORT_STRING_SIZE,
    AccessBridgeVersionInfo,
    AccessibleActions,
    AccessibleActionsToDo,
    AccessibleContextInfo,
    AccessibleHyperlinkInfo,
    AccessibleHypertextInfo,
    AccessibleIcons,
    AccessibleKeyBindings,
    AccessibleRelationSetInfo,
    AccessibleTableCellInfo,
    AccessibleTableInfo,
    AccessibleTextAttributesInfo,
    AccessibleTextInfo,
    AccessibleTextItemsInfo,
    AccessibleTextRectInfo,
    AccessibleTextSelectionInfo,
    JavaObject,
    VisibleChildrenInfo,
)
from JABWrapper.utils import ReleaseEvent

log_path = os.path.join(os.path.abspath(os.getenv("ROBOT_ARTIFACTS", "")), "jab_wrapper.log")
if not os.path.exists(os.path.dirname(log_path)):
    os.mkdir(os.path.dirname(log_path))
logging_file_handler = logging.FileHandler(log_path, "w", "utf-8")
logging_file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(threadName)s] {%(filename)s:%(lineno)d} [%(levelname)s] %(message)s")
)
logging_file_handler.setLevel(logging.DEBUG)

logging_stream_handler = logging.StreamHandler(sys.stdout)
logging_stream_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] {%(filename)s:%(lineno)d} %(message)s")
)
logging_stream_handler.setLevel(logging.INFO)

logging.basicConfig(level=logging.DEBUG, handlers=[logging_file_handler, logging_stream_handler])


# https://stackoverflow.com/questions/21175922/enumerating-windows-trough-ctypes-in-python
WNDENUMPROC = WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32 = windll.user32
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, c_int]


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


@dataclass
class JavaWindow:
    pid: int
    hwnd: int
    title: str


class Enumerator:
    def __init__(self, wab) -> None:
        self._wab = wab
        self._windows: List[JavaWindow] = []

    @property
    def windows(self):
        return self._windows

    def find_by_title(self, title: str) -> JavaWindow:
        regex = re.compile(title)
        for window in self._windows:
            if re.match(regex, window.title):
                return window

    def find_by_pid(self, pid: int) -> JavaWindow:
        for window in self._windows:
            if window.pid == pid:
                return window

    def enumerate(self, hwnd, lParam) -> bool:
        if not hwnd:
            logging.error(f"Invalid window handle={hwnd}")
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
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            java_window = JavaWindow(found_pid, hwnd, title)
            logging.debug(f"found window title={java_window.title} pid={java_window.pid} hwnd={java_window.hwnd}")
            self._windows.append(java_window)

        return True


class JavaAccessBridgeWrapper:
    def __init__(self, ignore_callbacks=False) -> None:
        self.ignore_callbacks = ignore_callbacks
        self._init()

    def _init(self) -> None:
        logging.debug("Loading WindowsAccessBridge")
        if "RC_JAVA_ACCESS_BRIDGE_DLL" not in os.environ:
            raise OSError("Environment variable: RC_JAVA_ACCESS_BRIDGE_DLL not found")
        if not os.path.isfile(os.path.normpath(os.environ["RC_JAVA_ACCESS_BRIDGE_DLL"])):
            raise FileNotFoundError(f"File not found: {os.environ['RC_JAVA_ACCESS_BRIDGE_DLL']}")
        self._wab: cdll = cdll.LoadLibrary(os.path.normpath(os.environ["RC_JAVA_ACCESS_BRIDGE_DLL"]))
        logging.debug("WindowsAccessBridge loaded succesfully")

        # Any reader can register callbacks here that are executed when `AccessBridge` events are seen.
        self._context_callbacks: dict[str, List[Callable[[JavaObject], None]]] = dict()
        self._define_functions()
        if not self.ignore_callbacks:
            self._define_callbacks()
            self._set_callbacks()
        self._wab.Windows_run()

        self._hwnd: Optional[wintypes.HWND] = None
        self._vmID = c_long()
        self.context = JavaObject()

    def shutdown(self):
        if not self.ignore_callbacks:
            self._remove_callbacks()
        self._context_callbacks.clear()

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
        # BOOL getAccessibleTableInfo(long vmID, AccessibleContext context, AccessibleTableInfo *tableInfo)
        self._wab.getAccessibleTableInfo.argtypes = [c_long, JavaObject, POINTER(AccessibleTableInfo)]
        self._wab.getAccessibleTableInfo.restype = wintypes.BOOL
        # BOOL getAccessibleTableCellInfo(long vmID, AccessibleTable accessibleTable, int row, int column, AccessibleTableCellInfo *tableCellInfo)
        self._wab.getAccessibleTableCellInfo.argtypes = [
            c_long,
            JavaObject,
            c_int,
            c_int,
            POINTER(AccessibleTableCellInfo),
        ]
        self._wab.getAccessibleTableCellInfo.restype = wintypes.BOOL
        # BOOL getAccessibleTableRowHeader(long vmID, AccessibleContext context, AccessibleTableInfo *tableInfo)
        self._wab.getAccessibleTableRowHeader.argtypes = [c_long, JavaObject, POINTER(AccessibleTableInfo)]
        self._wab.getAccessibleTableRowHeader.restype = wintypes.BOOL
        # BOOL getAccessibleTableColumnHeader(long vmID, AccessibleContext context, AccessibleTableInfo *tableInfo)
        self._wab.getAccessibleTableColumnHeader.argtypes = [c_long, JavaObject, POINTER(AccessibleTableInfo)]
        self._wab.getAccessibleTableColumnHeader.restype = wintypes.BOOL
        # JavaObject getAccessibleTableRowDescription(long vmID, AccessibleContext context, int row)
        self._wab.getAccessibleTableRowDescription.argtypes = [c_long, JavaObject, c_int]
        self._wab.getAccessibleTableRowDescription.restype = JavaObject
        # JavaObject getAccessibleTableColumnDescription(long vmID, AccessibleContext context, int row)
        self._wab.getAccessibleTableColumnDescription.argtypes = [c_long, JavaObject, c_int]
        self._wab.getAccessibleTableColumnDescription.restype = JavaObject
        # int getAccessibleTableRowSelectionCount(long vmID, AccessibleTable table)
        self._wab.getAccessibleTableRowSelectionCount.argtypes = [c_long, JavaObject]
        self._wab.getAccessibleTableRowSelectionCount.restype = c_int
        # BOOL isAccessibleTableRowSelected(long vmID, AccessibleTable table, int row)
        self._wab.isAccessibleTableRowSelected.argtypes = [c_long, JavaObject, c_int]
        self._wab.isAccessibleTableRowSelected.restype = wintypes.BOOL
        # TODO: What interface is this? The java API doesn't shed any more light than the windows bridge implementation
        # int getAccessibleTableRowSelections(long vmID, AccessibleTable table, int count, int *selections)
        # int getAccessibleTableColumnSelectionCount(long vmID, AccessibleTable table)
        self._wab.getAccessibleTableColumnSelectionCount.argtypes = [c_long, JavaObject]
        self._wab.getAccessibleTableColumnSelectionCount.restype = c_int
        # BOOL isAccessibleTableColumnSelected(long vmID, AccessibleTable table, int row)
        self._wab.isAccessibleTableColumnSelected.argtypes = [c_long, JavaObject, c_int]
        self._wab.isAccessibleTableColumnSelected.restype = wintypes.BOOL
        # TODO: What interface is this? The java API doesn't shed any more light than the windows bridge implementation
        # int getAccessibleTableColumnSelections(long vmID, AccessibleTable table, int count, int *selections)
        # int getAccessibleTableRow(long vmID, AccessibleTable table, int index)
        self._wab.getAccessibleTableRow.argtypes = [c_long, JavaObject, c_int]
        self._wab.getAccessibleTableRow.restype = c_int
        # int getAccessibleTableColumn(long vmID, AccessibleTable table, int index)
        self._wab.getAccessibleTableColumn.argtypes = [c_long, JavaObject, c_int]
        self._wab.getAccessibleTableColumn.restype = c_int
        # int getAccessibleTableIndex(long vmID, AccessibleTable table, int row)
        self._wab.getAccessibleTableIndex.argtypes = [c_long, JavaObject, c_int, c_int]
        self._wab.getAccessibleTableIndex.restype = c_int

        # AccessibleRelationSet
        # BOOL getAccessibleRelationSet(long vmID, AccessibleContext accessibleContext, AccessibleRelationSetInfo *relationSetInfo)
        self._wab.getAccessibleRelationSet.argtypes = [c_long, JavaObject, POINTER(AccessibleRelationSetInfo)]
        self._wab.getAccessibleRelationSet.restype = wintypes.BOOL

        # AccessibleHypertext
        # BOOL getAccessibleHypertext(long vmID, AccessibleContext accessibleContext, AccessibleHypertextInfo *hypertextInfo)
        self._wab.getAccessibleHypertext.argtypes = [c_long, JavaObject, POINTER(AccessibleHypertextInfo)]
        self._wab.getAccessibleHypertext.restype = wintypes.BOOL
        # BOOL activateAccessibleHyperlink(long vmID, AccessibleContext accessibleContext, AccessibleHyperlink accessibleHyperlink)
        self._wab.activateAccessibleHyperlink.argtypes = [c_long, JavaObject, JavaObject]
        self._wab.activateAccessibleHyperlink.restype = wintypes.BOOL
        # BOOL getAccessibleHyperlinkCount(long vmID, AccessibleContext accessibleContext)
        self._wab.getAccessibleHyperlinkCount.argtypes = [c_long, JavaObject]
        self._wab.getAccessibleHyperlinkCount.restype = c_int
        # BOOL getAccessibleHypertextExt(long vmID, AccessibleContext accessibleContext, int nStartIndex, AccessibleHypertextInfo *hypertextInfo)
        self._wab.getAccessibleHypertextExt.argtypes = [c_long, JavaObject, c_int, POINTER(AccessibleHypertextInfo)]
        self._wab.getAccessibleHypertextExt.restype = wintypes.BOOL
        # BOOL getAccessibleHypertextLinkIndex(long vmID, AccessibleContext accessibleContext, int charIndex, int *linkIndex)
        self._wab.getAccessibleHypertextLinkIndex.argtypes = [c_long, JavaObject, c_int]
        self._wab.getAccessibleHypertextLinkIndex.restype = c_int
        # BOOL getAccessibleHyperlink(long vmID, AccessibleContext accessibleContext, int index, AccessibleHyperlinkInfo *hyperlinkInfo)
        self._wab.getAccessibleHyperlink.argtypes = [c_long, JavaObject, c_int, POINTER(AccessibleHyperlinkInfo)]
        self._wab.getAccessibleHyperlink.restype = wintypes.BOOL

        # Accessible KeyBindings, Icons and Actions
        # BOOL getAccessibleKeyBindings(long vmID, AccessibleContext context, AccessibleKeyBindings *bindings)
        self._wab.getAccessibleKeyBindings.argtypes = [c_long, JavaObject, POINTER(AccessibleKeyBindings)]
        self._wab.getAccessibleKeyBindings.restypes = wintypes.BOOL
        # BOOL getAccessibleIcons(long vmID, AccessibleContext accessibleContext, AccessibleIcons *icons)
        self._wab.getAccessibleIcons.argtypes = [c_long, JavaObject, POINTER(AccessibleIcons)]
        self._wab.getAccessibleIcons.restype = wintypes.BOOL
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
        self._wab.getAccessibleTextAttributes.argtypes = [
            c_long,
            JavaObject,
            c_int,
            POINTER(AccessibleTextAttributesInfo),
        ]
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
        # BOOL getCurrentAccessibleValueFromContext(long vmID, AccessibleContext context, c_wchar *value, short len)
        self._wab.getCurrentAccessibleValueFromContext.argtypes = [c_long, JavaObject, c_wchar_p, c_short]
        self._wab.getCurrentAccessibleValueFromContext.restype = wintypes.BOOL
        # BOOL getMaximumAccessibleValueFromContext(long vmID, AccessibleContext context, c_wchar *value, short len)
        self._wab.getMaximumAccessibleValueFromContext.argtypes = [c_long, JavaObject, c_wchar_p, c_short]
        self._wab.getMaximumAccessibleValueFromContext.restype = wintypes.BOOL
        # BOOL getMinimumAccessibleValueFromContext(long vmID, AccessibleContext context, c_wchar *value, short len)
        self._wab.getMinimumAccessibleValueFromContext.argtypes = [c_long, JavaObject, c_wchar_p, c_short]
        self._wab.getMinimumAccessibleValueFromContext.restype = wintypes.BOOL

        # AccessibleSelection
        # void addAccessibleSelectionFromContext(long vmID, AccessibleContext context, int index)
        self._wab.addAccessibleSelectionFromContext.argtypes = [c_long, JavaObject, c_int]
        self._wab.addAccessibleSelectionFromContext.restype = None
        # void clearAccessibleSelectionFromContext(long vmID, AccessibleContext context)
        self._wab.clearAccessibleSelectionFromContext.argtypes = [c_long, JavaObject]
        self._wab.clearAccessibleSelectionFromContext.restype = None
        # JavaObject getAccessibleSelectionFromContext(long vmID, AccessibleContext context, int index)
        self._wab.getAccessibleSelectionFromContext.argtypes = [c_long, JavaObject, c_int]
        self._wab.getAccessibleSelectionFromContext.restype = JavaObject
        # int getAccessibleSelectionCountFromContext(long vmID, AccessibleContext context)
        self._wab.getAccessibleSelectionCountFromContext.argtypes = [c_long, JavaObject]
        self._wab.getAccessibleSelectionCountFromContext.restype = c_int
        # BOOL isAccessibleChildSelectedFromContext(long vmID, AccessibleContext context, int index)
        self._wab.isAccessibleChildSelectedFromContext.argtypes = [c_long, JavaObject, c_int]
        self._wab.isAccessibleChildSelectedFromContext.restype = wintypes.BOOL
        # void removeAccessibleSelectionFromContext(long vmID, AccessibleContext context, int index)
        self._wab.removeAccessibleSelectionFromContext.argtypes = [c_long, JavaObject, c_int]
        self._wab.removeAccessibleSelectionFromContext.restype = None
        # void selectAllAccessibleSelectionFromContext(long vmID, AccessibleContext context)
        self._wab.selectAllAccessibleSelectionFromContext.argtypes = [c_long, JavaObject]
        self._wab.selectAllAccessibleSelectionFromContext.restype = None

        # Utility
        # BOOL setTextContents(long vmID, AccessibleContext context, str text)
        self._wab.setTextContents.argtypes = [c_long, JavaObject, c_wchar * MAX_STRING_SIZE]
        self._wab.setTextContents.restypes = wintypes.BOOL
        # TODO: getParentWithRole
        # TODO: getParentWithRoleElseRoot
        # TODO: getTopLevelObject
        # TODO: getObjectDepth
        # TODO: getActiveDescendent
        # BOOL getVirtualAccessibleNameFP(long vmID, AccessibleContext context, str name, int len)
        self._wab.getVirtualAccessibleName.argtypes = [c_long, JavaObject, c_wchar * MAX_STRING_SIZE, c_int]
        self._wab.getVirtualAccessibleName.restype = wintypes.BOOL
        # BOOL requestFocus(long vmID, AccessibleContext context)
        self._wab.requestFocus.argtypes = [c_long, JavaObject]
        self._wab.requestFocus.restypes = wintypes.BOOL
        # TODO: selectTextRange
        # TODO: getTextAttributesInRange
        # int getVisibleChildrenCount(long vmID, AccessibleContext context)
        self._wab.getVisibleChildrenCount.argtypes = [c_long, JavaObject]
        self._wab.getVisibleChildrenCount.restype = c_int
        # BOOL getVisibleChildren(long vmID, AccessibleContext context, int startIndex, VisibleChildrenInfo *visibleChilderInfo)
        self._wab.getVisibleChildren.argtypes = [c_long, JavaObject, c_int, POINTER(VisibleChildrenInfo)]
        self._wab.getVisibleChildren.restype = wintypes.BOOL
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
        self._wab.setPropertyChangeFP(
            self._get_callback_func("setPropertyChangeFP", PropertyChangeFP, self._property_change)
        )
        self._wab.setPropertyNameChangeFP(
            self._get_callback_func("setPropertyNameChangeFP", PropertyNameChangeFP, self._property_name_change)
        )
        self._wab.setPropertyDescriptionChangeFP(
            self._get_callback_func(
                "setPropertyDescriptionChangeFP", PropertyDescriptionChangeFP, self._property_description_change
            )
        )
        self._wab.setPropertyStateChangeFP(
            self._get_callback_func("setPropertyStateChangeFP", PropertStateChangeFP, self._property_state_change)
        )
        self._wab.setPropertyValueChangeFP(
            self._get_callback_func("setPropertyValueChangeFP", PropertyValueChangeFP, self._property_value_change)
        )
        self._wab.setPropertySelectionChangeFP(
            self._get_callback_func(
                "setPropertySelectionChangeFP", PropertySelectionChangeFP, self._property_selection_change
            )
        )
        self._wab.setPropertyTextChangeFP(
            self._get_callback_func("setPropertyTextChangeFP", PropertyTextChangedFP, self._property_text_change)
        )
        self._wab.setPropertyCaretChangeFP(
            self._get_callback_func("setPropertyCaretChangeFP", PropertyCaretChangeFP, self._property_caret_change)
        )
        self._wab.setPropertyVisibleDataChangeFP(
            self._get_callback_func(
                "setPropertyVisibleDataChangeFP", PropertyVisibleDataChangeFP, self._property_visible_data_change
            )
        )
        self._wab.setPropertyChildChangeFP(
            self._get_callback_func("setPropertyChildChangeFP", PropertyChildChangeFP, self._property_child_change)
        )
        self._wab.setPropertyActiveDescendentChangeFP(
            self._get_callback_func(
                "setPropertyActiveDescendentChangeFP",
                PropertyActiveDescendentChangeFP,
                self._property_active_descendent_change,
            )
        )
        self._wab.setPropertyTableModelChangeFP(
            self._get_callback_func(
                "setPropertyTableModelChangeFP", PropertyTableModelChangeFP, self._property_table_model_change
            )
        )
        # Menu events
        self._wab.setMenuSelectedFP(self._get_callback_func("setMenuSelectedFP", MenuSelectedFP, self._menu_selected))
        self._wab.setMenuDeselectedFP(
            self._get_callback_func("setMenuDeselectedFP", MenuDeselectedFP, self._menu_deselected)
        )
        self._wab.setMenuCanceledFP(self._get_callback_func("setMenuCanceledFP", MenuCanceledFP, self._menu_canceled))
        # Focus events
        self._wab.setFocusGainedFP(self._get_callback_func("setFocusGainedFP", FocusGainedFP, self._focus_gained))
        self._wab.setFocusLostFP(self._get_callback_func("setFocusLostFP", FocusLostFP, self._focus_lost))
        # Caret update events
        self._wab.setCaretUpdateFP(self._get_callback_func("setCaretUpdateFP", CaretUpdateFP, self._caret_update))
        # Mouse events
        self._wab.setMouseClickedFP(self._get_callback_func("setMouseClickedFP", MouseClickedFP, self._mouse_clicked))
        self._wab.setMouseEnteredFP(self._get_callback_func("SetMouseEnteredFP", MouseEnteredFP, self._mouse_entered))
        self._wab.setMouseExitedFP(self._get_callback_func("setMouseExitedFP", MouseExitedFP, self._mouse_exited))
        self._wab.setMousePressedFP(self._get_callback_func("setMousePressedFP", MousePressedFP, self._mouse_pressed))
        self._wab.setMouseReleasedFP(
            self._get_callback_func("setMouseReleasedFP", MouseReleasedFP, self._mouse_released)
        )
        # Popup menu events
        self._wab.setPopupMenuCanceledFP(
            self._get_callback_func("setPopupMenuCanceledFP", PopupMenuCanceledFP, self._popup_menu_canceled)
        )
        self._wab.setPopupMenuWillBecomeInvisibleFP(
            self._get_callback_func(
                "setPopupMenuWillBecomeInvisibleFP",
                PopupMenuWillBecomeInvisibleFP,
                self._popup_menu_will_become_invisible,
            )
        )
        self._wab.setPopupMenuWillBecomeVisibleFP(
            self._get_callback_func(
                "setPopupMenuWillBecomeVisibleFP", PopupMenuWillBecomeVisibleFP, self._popup_menu_will_become_visible
            )
        )

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

    def set_hwnd(self, hwnd: wintypes.HWND) -> None:
        self._hwnd = hwnd

    def set_context(self, vm_id: c_long, context: JavaObject) -> None:
        self._vmID = vm_id
        self.context = context

    def get_current_windows_handle(self) -> wintypes.HWND:
        return self._hwnd

    def release_object(self, context: JavaObject) -> None:
        """
        Release the java object received via the API.

        Mainly used to release the events received via the Windows event system.

        Note:
            If the element context is released, it may lower the object ref count to zero and crash the application.

        Args:
            context: JavaObject context.
        """
        if self._vmID and self.context:
            logging.debug(f"Releasing object={context}")
            self._wab.releaseJavaObject(self._vmID, c_long(context.value).value)

    def switch_window_by_title(self, title: str) -> int:
        """
        Switch the context to window by title.

        Args:
            title: name of the window title.

        Returns:
            PID

        Raises:
            Exception: Window not found.
        """
        self._context_callbacks.clear()
        self._hwnd: wintypes.HWND = None
        self._vmID = c_long()
        self.context = JavaObject()

        # Add the title as the current context and find the correct window
        enumerator = Enumerator(self._wab)
        windows = WNDENUMPROC(enumerator.enumerate)
        if not windll.user32.EnumWindows(windows, 0):
            raise WinError()

        java_window = enumerator.find_by_title(title)
        logging.debug(f"found matching window={title}")
        self._hwnd = java_window.hwnd
        self._vmID = c_long()
        self.context = JavaObject()
        self._wab.getAccessibleContextFromHWND(self._hwnd, byref(self._vmID), byref(self.context))

        if not self._hwnd or not self._vmID or not self.context:
            raise Exception("Window not found")

        if not self._hwnd:
            raise Exception(f"Window not found={title}")

        logging.info(
            "Found Java window text={} pid={} hwnd={} vmID={} context={}\n".format(
                java_window.title, java_window.pid, self._hwnd, self._vmID, self.context
            )
        )

        return java_window.pid

    def switch_window_by_pid(self, pid: int) -> int:
        """
        Switch the context to window by PID.

        Args:
            PID: process ID.

        Returns:
            PID

        Raises:
            Exception: Window not found.
        """
        self._context_callbacks.clear()
        self._hwnd: wintypes.HWND = None
        self._vmID = c_long()
        self.context = JavaObject()

        enumerator = Enumerator(self._wab)
        windows = WNDENUMPROC(enumerator.enumerate)
        if not windll.user32.EnumWindows(windows, 0):
            raise WinError()

        java_window = enumerator.find_by_pid(pid)
        logging.debug(f"found matching window={pid}")
        self._hwnd = java_window.hwnd
        self._vmID = c_long()
        self.context = JavaObject()
        self._wab.getAccessibleContextFromHWND(self._hwnd, byref(self._vmID), byref(self.context))

        if not self._hwnd or not self._vmID or not self.context:
            raise Exception("Window not found")

        if not self._hwnd:
            raise Exception(f"Window not found={pid}")

        logging.info(
            "Found Java window text={} pid={} hwnd={} vmID={} context={}\n".format(
                java_window.title,
                java_window.pid,
                self._hwnd,
                self._vmID,
                self.context,
            )
        )

        return java_window.pid

    def get_windows(self) -> List[JavaWindow]:
        """
        Find all available Java windows.

        Returns:
            List of JavaWindow objects, a dataclass that contains: pid, hwnd and title.

        Raises:
            Windows Exception.
        """
        enumerator = Enumerator(self._wab)
        windows = WNDENUMPROC(enumerator.enumerate)
        if not windll.user32.EnumWindows(windows, 0):
            raise WinError()
        return enumerator.windows

    def get_accessible_context_from_hwnd(self, hwnd: wintypes.HWND) -> Tuple[c_long, JavaObject]:
        """
        Get the context handle for interacting via the JAB API.

        Args:
            hwnd: pointer to the windows handle.

        Returns:
            [vm_id, context]: the window id and the context to the element.

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        vm_id = c_long()
        context = JavaObject()
        ok = self._wab.getAccessibleContextFromHWND(hwnd, byref(vm_id), byref(context))
        if not ok:
            raise APIException("Failed to get accessible context from HWND")
        return vm_id, context

    def get_hwnd_from_accessible_context(self, context) -> wintypes.HWND:
        return self._wab.getHWNDFromAccessibleContext(self._vmID, context)

    def get_accessible_context_at(self, parent: JavaObject, x: int, y: int) -> JavaObject:
        """
        Get the context handle for interacting via the JAB API at coordinates.

        Args:
            context: the JavaObject context handle.

        Returns:
            context: JavaObject to the element context at coordinates.

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        context = JavaObject()
        ok = self._wab.getAccessibleContextAt(self._vmID, parent, x, y, byref(context))
        if not ok:
            raise APIException("Failed to get accessible context at={x},{y}")
        return context

    def get_child_context(self, context: JavaObject, index: int) -> JavaObject:
        return self._wab.getAccessibleChildFromContext(self._vmID, context, index)

    def get_accessible_parent_from_context(self, context) -> JavaObject:
        """
        Get the element parent context.

        Args:
            context: the context handle.

        Returns:
            context: JavaObject to the element parent context.
        """
        return self._wab.getAccessibleParentFromContext(self._vmID, context)

    def get_accessible_table_info(self, context: JavaObject) -> AccessibleTableInfo:
        """
        Get table information.

        Args:
            context: the element context handle.

        Returns:
            The AccessibleTableInfo object. For example:

            {
                "caption": JavaObject,
                "summary": JavaObject,
                "rowCount": 1,
                "columnCount": 2,
                "accessibleContext": JavaObject,
                "accessibleTable": JavaObject
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        table_info = AccessibleTableInfo()
        ok = self._wab.getAccessibleTableInfo(self._vmID, context, byref(table_info))
        if not ok:
            raise APIException("Failed to get accessible table info")
        return table_info

    def get_accessible_table_cell_info(
        self, table_context: JavaObject, row: int, column: int
    ) -> AccessibleTableCellInfo:
        """
        Get table cell information.

        Args:
            context: the table element handle.

        Returns:
            The AccessibleTableCellInfo object. For example:

            {
                "accessibleContext": JavaObject,
                "index": 0,
                "row": 1,
                "column": 2,
                "rowExtent": 0,
                "columnExtent": 0,
                "isSelected": False
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.

        Example:
            table_info = jab_wrapper.get_accessible_table_info(context)

            cell_info = jab_wrapper.get_accessible_table_cell_info(table_info.accessibleTable, 1, 1)
        """
        table_cell_info = AccessibleTableCellInfo()
        ok = self._wab.getAccessibleTableCellInfo(self._vmID, table_context, row, column, byref(table_cell_info))
        if not ok:
            raise APIException(f"Failed to get accessible table cell info at={row},{column}")
        return table_cell_info

    def get_accessible_table_row_header(self, context) -> AccessibleTableInfo:
        """
        Get table row header information.

        Args:
            context: the element context handle.

        Returns:
            The AccessibleTableInfo object. For example:

            {
                "caption": JavaObject,
                "summary": JavaObject,
                "rowCount": 1,
                "columnCount": 2,
                "accessibleContext": JavaObject,
                "accessibleTable": JavaObject
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        table_info = AccessibleTableInfo()
        ok = self._wab.getAccessibleTableRowHeader(self._vmID, context, byref(table_info))
        if not ok:
            raise APIException("Failed to get accessible table row header")
        return table_info

    def get_accessible_table_column_header(self, context) -> AccessibleTableInfo:
        """
        Get table column header information.

        Args:
            context: the element context handle.

        Returns:
            The AccessibleTableInfo object. For example:

            {
                "caption": JavaObject,
                "summary": JavaObject,
                "rowCount": 1,
                "columnCount": 2,
                "accessibleContext": JavaObject,
                "accessibleTable": JavaObject
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        table_info = AccessibleTableInfo()
        ok = self._wab.getAccessibleTableColumnHeader(self._vmID, context, byref(table_info))
        if not ok:
            raise APIException("Failed to get accessible table column header")
        return table_info

    def get_accessible_table_row_description(self, context: JavaObject, row: int) -> JavaObject:
        """
        Get table row description.

        Args:
            context: the element context handle.
            row: index of the row.

        Returns:
            JavaObject: Table row description.
        """
        return self._wab.getAccessibleTableRowDescription(self._vmID, context, row)

    def get_accessible_table_column_description(self, context: JavaObject, column: int) -> JavaObject:
        """
        Get table column description.

        Args:
            context: the element context handle.
            column: index of the column.

        Returns:
            JavaObject: Table column description.
        """
        return self._wab.getAccessibleTableColumnDescription(self._vmID, context, column)

    def get_accessible_table_row_selection_count(self, table_context: JavaObject) -> int:
        """
        Get table row selection count.

        Args:
            context: the element context handle.

        Returns:
            int: Table row selection count.
        """
        return self._wab.getAccessibleTableRowSelectionCount(self._vmID, table_context)

    def is_accessible_table_row_selected(self, table_context: JavaObject, row: int) -> bool:
        """
        Validate if the row is selected.

        Args:
            context: the element context handle.
            row: index of the row.

        Returns:
            boolean.
        """
        return self._wab.isAccessibleTableRowSelected(self._vmID, table_context, row)

    def get_accessible_table_row(self, table_context: JavaObject, index: int) -> int:
        """
        Get the row number for a cell at a given index.

        Args:
            accessibleTable: the accessibleTable field in AccessibleTableInfo object.
            index: index of the cell.

        Returns:
            int: the row number of the cell at index.
        """
        return self._wab.getAccessibleTableRow(self._vmID, table_context, index)

    def get_accessible_table_column(self, table_context: JavaObject, index: int) -> int:
        """
        Get the column number for a cell at a given index.

        Args:
            accessibleTable: the accessibleTable field in AccessibleTableInfo object.
            index: index of the cell.

        Returns:
            int: the column number of the cell at index.
        """
        return self._wab.getAccessibleTableColumn(self._vmID, table_context, index)

    def get_accessible_table_index(self, table_context: JavaObject, row: int, column: int) -> int:
        """
        Get the cell index at a row and column.

        Args:
            accessibleTable: the accessibleTable field in AccessibleTableInfo object.
            row: index of the row.
            column: index of the column.

        Returns:
            int: the index of the cell at row and column.
        """
        return self._wab.getAccessibleTableIndex(self._vmID, table_context, row, column)

    def get_accessible_table_column_selection_count(self, table_context: JavaObject) -> int:
        """
        Get table column selection count.

        Args:
            context: the element context handle.

        Returns:
            int: Table column selection count.
        """
        return self._wab.getAccessibleTableColumnSelectionCount(self._vmID, table_context)

    def is_accessible_table_column_selected(self, table_context: JavaObject, row: int) -> bool:
        """
        Validate if the column is selected.

        Args:
            context: the element context handle.
            column: index of the row.

        Returns:
            boolean.
        """
        return self._wab.isAccessibleTableColumnSelected(self._vmID, table_context, row)

    def get_accessible_relation_set_info(self, context: JavaObject) -> AccessibleRelationSetInfo:
        """
        Get element relation set information.

        Args:
            context: the element context handle.

        Returns:
            The AccessibleRelationSetInfo object. For example:

            {
                "relationCount": 1,
                "AccessibleRelationInfo": [
                    {
                        "key": "random_key",
                        "targetCount": 1,
                        "targets": [ JavaObject, JavaObject ]
                    }
                ]
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        relation_set_info = AccessibleRelationSetInfo()
        logging.info("getting rel set")
        ok = self._wab.getAccessibleRelationSet(self._vmID, context, byref(relation_set_info))
        logging.info(f"rel set={ok}")
        if not ok:
            raise APIException("Failed to get accessible relation set info")
        return relation_set_info

    def get_context_info(self, context: JavaObject) -> AccessibleContextInfo:
        """
        Get element context information.

        Args:
            context: the element context handle.

        Returns:
            The AccessibleContextInfo object. For example:

            {
                "name": "Button",
                "description": "Click button",
                "role": "push button",
                "role_en_US": "push button",
                "states": "enabled,clicked",
                "states_en_US": "enabled,clicked",
                "indexInParent": 1,
                "childrenCount": 10,
                "x": 150,
                "y": 150,
                "width": 800,
                "height": 600,
                "accessibleComponent": True,
                "accessibleAction": True,
                "accessibleSelection": False,
                "accessibleText": False,
                "accessibleValue", False
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        info = AccessibleContextInfo()
        ok = self._wab.getAccessibleContextInfo(self._vmID, context, byref(info))
        if not ok:
            raise APIException("Failed to get accessible context info")
        return info

    def get_version_info(self) -> AccessBridgeVersionInfo:
        """
        Get window version information.

        Args:
            None.

        Returns:
            The AccessBridgeVersionInfo object. For example:

            {
                "VMversion": "1.8.0_292",
                "bridgeJavaClassVersion": "1.8.0_292",
                "bridgeJavaDLLVersion": "1.8.0_292",
                "bridgeWinDLLVersion": "1.8.0_292",
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        info = AccessBridgeVersionInfo()
        ok = self._wab.getVersionInfo(self._vmID, byref(info))
        if not ok:
            raise APIException("Failed to get version info")
        return info

    def get_accessible_hypertext(self, context: JavaObject) -> AccessibleHypertextInfo:
        """
        Get hypertext information.

        Args:
            None.

        Returns:
            The AccessibleHypertextInfo object. For example:

            {
                "linkCount": 1,
                "links": [
                    {
                        "text": "random",
                        "startIndex": 0,
                        "endIndex": 6,
                        "accessibleHyperlink": JavaObject
                    }
                ],
                "accessibleHypertext", JavaObject
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        hypertext_info = AccessibleHypertextInfo()
        ok = self._wab.getAccessibleHypertext(self._vmID, context, byref(hypertext_info))
        if not ok:
            raise APIException("Failed to get accessible hypertext info")
        return hypertext_info

    def activate_accessible_hyperlink(self, context: JavaObject, hyperlink: JavaObject) -> None:
        """
        Activate hyperlink.

        Args:
            context: the element context handle.
            hyperlink: hyperlink JavaObject found in the AccessibleHypertextInfo object.

        Returns:
            None

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        ok = self._wab.activateAccessibleHyperlink(self._vmID, context, hyperlink)
        if not ok:
            raise APIException("Failed to activate accessible hypertext link")

    def get_accessible_hyperlink_count(self, context: JavaObject) -> int:
        """
        Get hyperlink count in element.

        Args:
            context: the element context handle.

        Returns:
            int: the hyperlink count.
        """
        return self._wab.getAccessibleHyperlinkCount(self._vmID, context)

    def get_accessible_hypertext_ext(self, context: JavaObject, index: int) -> AccessibleHypertextInfo:
        """
        Get the hypertext info for element containing hyperlinks starting from the index.

        Args:
            context: the element context handle.
            index: the start index to add the hyperlinks.

        Returns:
            The AccessibleHypertextInfo object. For example:

            {
                "linkCount": 1,
                "links": [
                    {
                        "text": "random",
                        "startIndex": 0,
                        "endIndex": 6,
                        "accessibleHyperlink": JavaObject
                    }
                ],
                "accessibleHypertext", JavaObject
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        hypertext_info = AccessibleHypertextInfo()
        ok = self._wab.getAccessibleHypertextExt(self._vmID, context, index, byref(hypertext_info))
        if not ok:
            raise APIException(f"Failed to get accessible hypertext info starting from index={index}")
        return hypertext_info

    def get_accessible_hypertext_link_index(self, hypertext: JavaObject, char_index: int) -> int:
        """
        Get the index into an array of hyperlinks that is associated with a character index in element.

        Args:
            hypertext: hypertext JavaObject found in the AccessibleHypertextInfo object.

        Returns:
            int: index of hyperlink in element.
        """
        return self._wab.getAccessibleHypertextLinkIndex(self._vmID, hypertext, char_index)

    def get_accessible_hyperlink(self, hypertext: JavaObject, index: int) -> AccessibleHyperlinkInfo:
        """
        Get hyperlink of hypertext object.

        Args:
            hypertext: hypertext JavaObject found in the AccessibleHypertextInfo object.

        Returns:
            The AccessibleHyperlinkInfo object. For example:

            {
                "text": "link text",
                "startIndex": 0,
                "endIndex": 10,
                "accessibleHyperlink": JavaObject
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        hyperlink_info = AccessibleHyperlinkInfo()
        ok = self._wab.getAccessibleHyperlink(self._vmID, hypertext, index, byref(hyperlink_info))
        if not ok:
            raise APIException(f"Failed to get accessible hypertext link info at index={index}")
        return hyperlink_info

    def get_context_text_info(self, context: JavaObject, x: int, y: int) -> AccessibleTextInfo:
        """
        Get text info object at coordinates.

        Args:
            context: the element context handle.
            x: the x coordinate.
            y: The y coordinate.

        Returns:
            The AccessibleTextInfo object. For example:

            {
                "charCount": 5,
                "caretIndex": 2,
                "indexAtPoint": 2
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        info = AccessibleTextInfo()
        ok = self._wab.getAccessibleTextInfo(self._vmID, context, byref(info), x, y)
        if not ok:
            raise APIException("Failed to get accessible text info")
        return info

    def get_accessible_text_items(self, context: JavaObject, index: int) -> AccessibleTextItemsInfo:
        """
        Get text items object at index.

        Args:
            context: the element context handle.
            index: the character index at text element.

        Returns:
            The AccessibleTextItemsInfo object. For example:

            {
                "letter": "w",
                "word": "random word",
                "sentence": "random word in a sentence"
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        info = AccessibleTextItemsInfo()
        ok = self._wab.getAccessibleTextItems(self._vmID, context, byref(info), index)
        if not ok:
            raise APIException("Failed to get accessible text context")
        return info

    def get_accessible_text_selection_info(self, context: JavaObject) -> AccessibleTextSelectionInfo:
        """
        Get text selection info object.

        Args:
            context: the element context handle.

        Returns:
            The AccessibleTextSelectionInfo object. For example:

            {
                "selectionStartIndex": 0,
                "selectionEndIndex": 6,
                "selectedText": "random"
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        info = AccessibleTextSelectionInfo()
        ok = self._wab.getAccessibleTextSelectionInfo(self._vmID, context, byref(info))
        if not ok:
            raise APIException("Failed to get accessible text selection info")
        return info

    def get_accessible_text_attributes(self, context: JavaObject, index: int) -> AccessibleTextAttributesInfo:
        """
        Get text attributes object at index.

        Args:
            context: the element context handle.
            index: the character index at text element.

        Returns:
            The AccessibleTextAttributesInfo object. For example:

            {
                "bold". False,
                "italic": False,
                "underline": False,
                "strikethrough": False,
                "superscript": False,
                "subscript": False,

                "backgroundColor": "red",
                "foregroundColor": "white",
                "fontFamily": ""font",
                "fontSize": 12,

                "alignment": 0,
                "bidiLevel": 0,

                "firstLineIndent": 10.0,
                "leftIndent": 10.0,
                "rightIndent": 10.0,
                "lineSpacing": 10.0,
                "spaceAbove": 10.0,
                "spaceBelow": 10.0,

                "fullAttributesString": "attrs",
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        attributes_info = AccessibleTextAttributesInfo()
        ok = self._wab.getAccessibleTextAttributes(self._vmID, context, index, attributes_info)
        if not ok:
            raise APIException("Failed to get accessible text attributes info")
        return attributes_info

    def get_accessible_text_rect(self, context: JavaObject, index: int) -> AccessibleTextRectInfo:
        """
        Get text rectangle object at index.

        Args:
            context: the element context handle.
            index: the character index at text element.

        Returns:
            The AccessibleTextRectInfo object. For example:

            {
                "x": 100,
                "y": 100,
                "width": 100,
                "height": 100
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        rect_info = AccessibleTextRectInfo()
        ok = self._wab.getAccessibleTextRect(self._vmID, context, byref(rect_info), index)
        if not ok:
            raise APIException("Failed to get accessible text rect info")
        return rect_info

    def get_accessible_text_line_bounds(self, context, index) -> Tuple[int, int]:
        """
        Get text line bound.

        Args:
            context: the element context handle.
            index: the character index at text element.

        Returns:
            [int, int]: Tuple of start and end index.

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        start_index = c_int()
        end_index = c_int()
        ok = self._wab.getAccessibleTextLineBounds(self._vmID, context, index, byref(start_index), byref(end_index))
        if not ok:
            raise APIException(f"Failed to get accessible text line bounds at={index}")
        return start_index, end_index

    def get_accessible_text_range(self, context: JavaObject, start_index: int, end_index: int, length: c_short) -> str:
        """
        Get text at range.

        Args:
            context: the element context handle.
            start_index: start index for text.
            end_index: end index of the text.
            length: text length.

        Returns:
            str: text at range.

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        buf = create_unicode_buffer(length)
        ok = self._wab.getAccessibleTextRange(self._vmID, context, start_index, end_index, buf, length)
        if not ok:
            raise APIException("Failed to get accessible range")
        return buf.value

    def get_current_accessible_value_from_context(self, context: JavaObject) -> str:
        """
        Get value of element.

        Args:
            context: the element context handle.

        Returns:
            str: value.

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        buf = create_unicode_buffer(SHORT_STRING_SIZE)
        ok = self._wab.getCurrentAccessibleValueFromContext(self._vmID, context, buf, SHORT_STRING_SIZE)
        if not ok:
            raise APIException("Failed to get current accessible value from context")
        return buf.value

    def get_maximum_accessible_value_from_context(self, context: JavaObject) -> str:
        """
        Get max value of element.

        Args:
            context: the element context handle.

        Returns:
            str: max value.

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        buf = create_unicode_buffer(SHORT_STRING_SIZE)
        ok = self._wab.getMaximumAccessibleValueFromContext(self._vmID, context, buf, SHORT_STRING_SIZE)
        if not ok:
            raise APIException("Failed to get maximum accessible value from context")
        return buf.value

    def get_minimum_accessible_value_from_context(self, context: JavaObject) -> str:
        """
        Get min value of element.

        Args:
            context: the element context handle.

        Returns:
            str: min value.

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        buf = create_unicode_buffer(SHORT_STRING_SIZE)
        ok = self._wab.getMinimumAccessibleValueFromContext(self._vmID, context, buf, SHORT_STRING_SIZE)
        if not ok:
            raise APIException("Failed to get minimum accessible value from context")
        return buf.value

    def add_accessible_selection_from_context(self, context: JavaObject, index: int) -> None:
        """
        Select value in selectable context.

        Args:
            context: the element context handle.
            index: the index of the selection.

        Returns:
            None
        """
        self._wab.addAccessibleSelectionFromContext(self._vmID, context, index)

    def clear_accessible_selection_from_context(self, context: JavaObject) -> None:
        """
        Clear selection in selectable context.

        Args:
            context: the element context handle.

        Returns:
            None
        """
        self._wab.clearAccessibleSelectionFromContext(self._vmID, context)

    def get_accessible_selection_from_context(self, context: JavaObject, index: int) -> JavaObject:
        """
        Get selectable context.

        Args:
            context: the element context handle.
            index: the index of the selectable context in element.

        Returns:
            JavaObject: selectable object in element.
        """
        return self._wab.getAccessibleSelectionFromContext(self._vmID, context, index)

    def get_accessible_selection_count_from_context(self, context: JavaObject) -> int:
        """
        Get selectable object count in element.

        Args:
            context: the element context handle.

        Returns:
            int: the count of selectable objects in element.
        """
        return self._wab.getAccessibleSelectionCountFromContext(self._vmID, context)

    def is_accessible_child_selected_from_context(self, context: JavaObject, index: JavaObject) -> bool:
        """
        Check if selectable object is selected in element.

        Args:
            context: the element context handle.
            index: the index of the selectable object in element.

        Returns:
            bool: True if selected else False.
        """
        return bool(self._wab.isAccessibleChildSelectedFromContext(self._vmID, context, index))

    def remove_accessible_selection_from_context(self, context: JavaObject, index: int) -> None:
        """
        Remove active selection from selectable element.

        Args:
            context: the element context handle.
            index: the index of the selectable object in element.

        Returns:
            None
        """
        self._wab.removeAccessibleSelectionFromContext(self._vmID, context, index)

    def select_all_accessible_selection_from_context(self, context: JavaObject) -> None:
        """
        Select all selections in element.

        Args:
            context: the element context handle.

        Returns:
            None
        """
        self._wab.selectAllAccessibleSelectionFromContext(self._vmID, context)

    def get_accessible_actions(self, context: JavaObject) -> AccessibleActions:
        """
        Get all possible action of the element.

        Args:
            context: the element context handle.

        Returns:
            The AccessibleActions object. For example:

            {
                "actionsCount": 1,
                "actionInfo": [
                    {
                        "name": "click"
                    }
                ]
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        actions = AccessibleActions()
        ok = self._wab.getAccessibleActions(self._vmID, context, byref(actions))
        if not ok:
            raise APIException("Failed to get accessible actions")
        return actions

    def do_accessible_actions(self, context: JavaObject, actions: AccessibleActionsToDo) -> None:
        """
        Do actions for element context.

        Args:
            context: the element context handle.
            actions: the AccessibleActionsToDo object. For example:

            {
                "actionsCount": 1,
                "actionInfo": [
                    {
                        "name": "click"
                    }
                ]
            }

        Returns:
            None

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        index = c_int()
        ok = self._wab.doAccessibleActions(self._vmID, context, actions, byref(index))
        if not ok:
            raise APIException("Action failed at index={}".format(index))

    def set_text_contents(self, context: JavaObject, text: str) -> None:
        """
        Set element text content.

        Args:
            context: the element context handle.
            text: text string to be written to element.

        Returns:
            None

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        buf = create_unicode_buffer(text, MAX_STRING_SIZE)
        ok = self._wab.setTextContents(self._vmID, context, buf)
        if not ok:
            raise APIException("Failed to set field contents")

    def request_focus(self, context: JavaObject) -> None:
        """
        Request focus for the element.

        Args:
            context: the element context handle.

        Returns:
            None

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        ok = self._wab.requestFocus(self._vmID, context)
        if not ok:
            raise APIException("Failed to request focus")

    def get_accessible_key_bindings(self, context: JavaObject) -> AccessibleKeyBindings:
        """
        Get keybindings for the element.

        Args:
            context: the element context handle.

        Returns:
            The AccessibleKeyBindings object. For example:

            {
                "keyBindingsCount": 1,
                "AccessibleKeyBindingInfo": [
                    {
                        "character": "random",
                        "modifiers": 0
                    }
                ]
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        key_bindings = AccessibleKeyBindings()
        ok = self._wab.getAccessibleKeyBindings(self._vmID, context, byref(key_bindings))
        if not ok:
            raise APIException("Failed to get accessible key bindings")
        return key_bindings

    def get_accessible_icons(self, context: JavaObject) -> AccessibleIcons:
        """
        Get the element icons.

        Args:
            context: the element context handle.

        Returns:
            The AccessibleIcons object. For example:

            {
                "AccessibleIcons": 1,
                "iconInfo": [
                    {
                        "description": "element_icon.png",
                        "height": 10,
                        "width": 10
                    }
                ]
            }

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        icons = AccessibleIcons()
        ok = self._wab.getAccessibleIcons(self._vmID, context, byref(icons))
        if not ok:
            raise APIException("Failed to get accessible icons")
        return icons

    def is_same_object(self, context_from: JavaObject, context_to: JavaObject) -> bool:
        return self._wab.isSameObject(self._vmID, context_from, context_to)

    def get_virtual_accessible_name(self, context: JavaObject) -> str:
        """
        Get the virtual accessible name of the element.

        Args:
            context: the element context handle.

        Returns:
            str.

        Raises:
            APIException: failed to call the java access bridge API with attributes.
        """
        buf = create_unicode_buffer(MAX_STRING_SIZE)
        ok = self._wab.getVirtualAccessibleName(self._vmID, context, buf, MAX_STRING_SIZE)
        if not ok:
            raise APIException("Failed to get virtual accessible name")
        return buf.value

    def get_visible_children_count(self, context: JavaObject) -> int:
        return self._wab.getVisibleChildrenCount(self._vmID, context)

    def get_visible_children(self, context: JavaObject, start_index: int) -> VisibleChildrenInfo:
        visible_children = VisibleChildrenInfo()
        ok = self._wab.getVisibleChildren(self._vmID, context, start_index, byref(visible_children))
        if not ok:
            raise APIException("Failed to get visible children info")
        return visible_children

    def register_callback(self, name: str, callback: Callable[[JavaObject], None]) -> None:
        """
        Register a callback handler for GUI events.

        Args:
            name: the of the callback.
            callback: callback function.

        Returns:
            None

        Possible callbacks:
            * property_change
            * property_name_change
            * property_description_change
            * property_state_change
            * property_value_change
            * property_selection_change
            * property_text_change
            * property_caret_change
            * property_visible_data_change
            * property_child_change
            * property_active_descendent_change
            * property_table_model_change

            * menu_selected
            * menu_deselected
            * menu_calceled

            * focus_gained
            * focus_lost

            * caret_update

            * mouse_clicked
            * mouse_entered
            * mouse_exited
            * mouse_pressed
            * mouse_released

            * popup_menu_canceled
            * popup_menu_will_become_invisible
            * popup_menu_will_become_visible
        """
        logging.debug(f"Registering callback={name}")
        self._context_callbacks.setdefault(name, []).append(callback)

    def clear_callbacks(self):
        self._context_callbacks.clear()

    """
    Define the callback handlers
    """

    def _get_callback_func(self, name, wrapper, callback):
        def func(*args):
            callback(*args)

        runner = wrapper(func)
        setattr(self, name, runner)
        return runner

    def _property_change(self, vmID: c_long, event: JavaObject, source: JavaObject, property, old_value, new_value):
        with ReleaseEvent(self, vmID, "property_change", event, source):
            if "property_change" in self._context_callbacks:
                for cp in self._context_callbacks["property_change"]:
                    cp(source, property, old_value, new_value)

    def _property_name_change(
        self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str
    ):
        with ReleaseEvent(self, vmID, "property_name_change", event, source):
            if "property_name_change" in self._context_callbacks:
                for cp in self._context_callbacks["property_name_change"]:
                    cp(source, old_value, new_value)

    def _property_description_change(
        self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str
    ):
        with ReleaseEvent(self, vmID, "property_description_change", event, source):
            if "property_description_change" in self._context_callbacks:
                for cp in self._context_callbacks["property_description_change"]:
                    cp(source, old_value, new_value)

    def _property_state_change(
        self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str
    ):
        with ReleaseEvent(self, vmID, "property_state_change", event, source):
            if "property_state_change" in self._context_callbacks:
                for cp in self._context_callbacks["property_state_change"]:
                    cp(source, old_value, new_value)

    def _property_value_change(
        self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str
    ):
        with ReleaseEvent(self, vmID, "property_value_change", event, source):
            if "property_value_change" in self._context_callbacks:
                for cp in self._context_callbacks["property_value_change"]:
                    cp(source, old_value, new_value)

    def _property_selection_change(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "property_selection_change", event, source):
            if "property_selection_change" in self._context_callbacks:
                for cp in self._context_callbacks["property_selection_change"]:
                    cp(source)

    def _property_text_change(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "property_text_change", event, source):
            if "property_text_change" in self._context_callbacks:
                for cp in self._context_callbacks["property_text_change"]:
                    cp(source)

    def _property_caret_change(self, vmID: c_long, event: JavaObject, source: JavaObject, old_pos: int, new_pos: int):
        with ReleaseEvent(self, vmID, "set_property_caret_change", event, source):
            if "set_property_caret_change" in self._context_callbacks:
                for cp in self._context_callbacks["set_property_caret_change"]:
                    cp(source, old_pos, new_pos)

    def _property_visible_data_change(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "property_visible_data_change", event, source):
            if "property_visible_data_change" in self._context_callbacks:
                for cp in self._context_callbacks["property_visible_data_change"]:
                    cp(source)

    def _property_child_change(
        self, vmID: c_long, event: JavaObject, source: JavaObject, old_child: JavaObject, new_child: JavaObject
    ):
        with ReleaseEvent(self, vmID, "property_child_change", event, source):
            if "property_child_change" in self._context_callbacks:
                for cp in self._context_callbacks["property_child_change"]:
                    cp(source, old_child, new_child)

    def _property_active_descendent_change(
        self, vmID: c_long, event: JavaObject, source: JavaObject, old_child: JavaObject, new_child: JavaObject
    ):
        with ReleaseEvent(self, vmID, "property_active_descendent_change", event, source):
            if "property active descendent change" in self._context_callbacks:
                for cp in self._context_callbacks["property_active_descendent_change"]:
                    cp(source, old_child, new_child)

    def _property_table_model_change(
        self, vmID: c_long, event: JavaObject, source: JavaObject, old_value: str, new_value: str
    ):
        with ReleaseEvent(self, vmID, "property_table_model_change", event, source):
            if "property_table_model_change" in self._context_callbacks:
                for cp in self._context_callbacks["property_table_model_change"]:
                    cp(source, old_value, new_value)

    def _menu_selected(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "menu_selected", event, source):
            if "menu_selected" in self._context_callbacks:
                for cp in self._context_callbacks["menu_selected"]:
                    cp(source)

    def _menu_deselected(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "menu_deselected", event, source):
            if "menu_deselected" in self._context_callbacks:
                for cp in self._context_callbacks["menu_deselected"]:
                    cp(source)

    def _menu_canceled(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "menu_canceled", event, source):
            if "menu_canceled" in self._context_callbacks:
                for cp in self._context_callbacks["menu_canceled"]:
                    cp(source)

    def _focus_gained(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "focus_gained", event, source):
            if "focus_gained" in self._context_callbacks:
                for cp in self._context_callbacks["focus_gained"]:
                    cp(source)

    def _focus_lost(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "focus_lost", event, source):
            if "focus_lost" in self._context_callbacks:
                for cp in self._context_callbacks["focus_lost"]:
                    cp(source)

    def _caret_update(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "caret_update", event, source):
            if "caret_update" in self._context_callbacks:
                for cp in self._context_callbacks["caret_update"]:
                    cp(source)

    def _mouse_clicked(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "mouse_clicked", event, source):
            if "mouse_clicked" in self._context_callbacks:
                for cp in self._context_callbacks["mouse_clicked"]:
                    cp(source)

    def _mouse_entered(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "mouse_entered", event, source):
            if "mouse_entered" in self._context_callbacks:
                for cp in self._context_callbacks["mouse_entered"]:
                    cp(source)

    def _mouse_exited(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "mouse_exited", event, source):
            if "mouse_exited" in self._context_callbacks:
                for cp in self._context_callbacks["mouse_exited"]:
                    cp(source)

    def _mouse_pressed(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "mouse_pressed", event, source):
            if "mouse_pressed" in self._context_callbacks:
                for cp in self._context_callbacks["mouse_pressed"]:
                    cp(source)

    def _mouse_released(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "mouse_released", event, source):
            if "mouse_released" in self._context_callbacks:
                for cp in self._context_callbacks["mouse_released"]:
                    cp(source)

    def _popup_menu_canceled(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "popup_menu_canceled", event, source):
            if "popup_menu_canceled" in self._context_callbacks:
                for cp in self._context_callbacks["popup_menu_canceled"]:
                    cp(source)

    def _popup_menu_will_become_invisible(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "popup_menu_will_become_invisible", event, source):
            if "popup_menu_will_become_invisible" in self._context_callbacks:
                for cp in self._context_callbacks["popup_menu_will_become_invisible"]:
                    cp(source)

    def _popup_menu_will_become_visible(self, vmID: c_long, event: JavaObject, source: JavaObject):
        with ReleaseEvent(self, vmID, "popup_menu_will_become_visible", event, source):
            if "popup_menu_will_become_visible" in self._context_callbacks:
                for cp in self._context_callbacks["popup_menu_will_become_visible"]:
                    cp(source)
