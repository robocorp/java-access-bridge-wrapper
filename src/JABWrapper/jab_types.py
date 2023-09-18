from ctypes import Structure, c_bool, c_float, c_int, c_int64, c_wchar, wintypes

MAX_STRING_SIZE = 1024
SHORT_STRING_SIZE = 256

MAX_ACTION_INFO = 256
MAX_ACTIONS_TO_DO = 32

MAX_RELATION_TARGETS = 25
MAX_RELATIONS = 5

MAX_HYPERLINKS = 64

MAX_TABLE_SELECTIONS = 64

MAX_KEY_BINDINGS = 10

MAX_ICON_INFO = 10

MAX_VISIBLE_CHILDREN_COUNT = 256


class JavaObject(c_int64):
    pass


class AccessibleContextInfo(Structure):
    _fields_ = [
        ("name", c_wchar * MAX_STRING_SIZE),
        ("description", c_wchar * MAX_STRING_SIZE),
        ("role", c_wchar * SHORT_STRING_SIZE),
        ("role_en_US", c_wchar * SHORT_STRING_SIZE),
        ("states", c_wchar * SHORT_STRING_SIZE),
        ("states_en_US", c_wchar * SHORT_STRING_SIZE),
        ("indexInParent", c_int),
        ("childrenCount", c_int),
        ("x", c_int),
        ("y", c_int),
        ("width", c_int),
        ("height", c_int),
        ("accessibleComponent", wintypes.BOOL),
        ("accessibleAction", wintypes.BOOL),
        ("accessibleSelection", wintypes.BOOL),
        ("accessibleText", wintypes.BOOL),
        ("accessibleValue", wintypes.BOOL),
    ]


class AccessBridgeVersionInfo(Structure):
    _fields_ = [
        ("VMversion", c_wchar * SHORT_STRING_SIZE),
        ("bridgeJavaClassVersion", c_wchar * SHORT_STRING_SIZE),
        ("bridgeJavaDLLVersion", c_wchar * SHORT_STRING_SIZE),
        ("bridgeWinDLLVersion", c_wchar * SHORT_STRING_SIZE),
    ]


class AccessibleTextInfo(Structure):
    _fields_ = [("charCount", c_int), ("caretIndex", c_int), ("indexAtPoint", c_int)]


class AccessibleTextItemsInfo(Structure):
    _fields_ = [("letter", c_wchar), ("word", c_wchar * SHORT_STRING_SIZE), ("sentence", c_wchar * MAX_STRING_SIZE)]


class AccessibleTextSelectionInfo(Structure):
    _fields_ = [
        ("selectionStartIndex", c_int),
        ("selectionEndIndex", c_int),
        ("selectedText", c_wchar * MAX_STRING_SIZE),
    ]


class AccessibleTextAttributesInfo(Structure):
    _fields_ = [
        ("bold", wintypes.BOOL),
        ("italic", wintypes.BOOL),
        ("underline", wintypes.BOOL),
        ("strikethrough", wintypes.BOOL),
        ("superscript", wintypes.BOOL),
        ("subscript", wintypes.BOOL),
        ("backgroundColor", c_wchar * SHORT_STRING_SIZE),
        ("foregroundColor", c_wchar * SHORT_STRING_SIZE),
        ("fontFamily", c_wchar * SHORT_STRING_SIZE),
        ("fontSize", c_int),
        ("alignment", c_int),
        ("bidiLevel", c_int),
        ("firstLineIndent", c_float),
        ("leftIndent", c_float),
        ("rightIndent", c_float),
        ("lineSpacing", c_float),
        ("spaceAbove", c_float),
        ("spaceBelow", c_float),
        ("fullAttributesString", c_wchar * MAX_STRING_SIZE),
    ]


class AccessibleTextRectInfo(Structure):
    _fields_ = [("x", c_int), ("y", c_int), ("width", c_int), ("height", c_int)]


class AccessibleActionInfo(Structure):
    _fields_ = [("name", c_wchar * SHORT_STRING_SIZE)]


class AccessibleActions(Structure):
    _fields_ = [("actionsCount", c_int), ("actionInfo", AccessibleActionInfo * MAX_ACTION_INFO)]


class AccessibleActionsToDo(Structure):
    _fields_ = [("actionsCount", c_int), ("actions", AccessibleActionInfo * MAX_ACTION_INFO)]


class AccessibleRelationInfo(Structure):
    _fields_ = [
        ("key", c_wchar * SHORT_STRING_SIZE),
        ("targetCount", c_int),
        ("targets", JavaObject * MAX_RELATION_TARGETS),
    ]


class AccessibleRelationSetInfo(Structure):
    _fields = [("relationCount", c_int), ("AccessibleRelationInfo", AccessibleRelationInfo * MAX_RELATIONS)]


class AccessibleHyperlinkInfo(Structure):
    _fields_ = [
        ("text", c_wchar * SHORT_STRING_SIZE),
        ("startIndex", c_int),
        ("endIndex", c_int),
        ("accessibleHyperlink", JavaObject),
    ]


class AccessibleHypertextInfo(Structure):
    _fields_ = [
        ("linkCount", c_int),
        ("links", AccessibleHyperlinkInfo * MAX_HYPERLINKS),
        ("accessibleHypertext", JavaObject),
    ]


class AccessibleKeyBindingInfo(Structure):
    _fields_ = [("character", c_wchar), ("modifiers", c_int)]


class AccessibleKeyBindings(Structure):
    _fields_ = [("keyBindingsCount", c_int), ("AccessibleKeyBindingInfo", AccessibleKeyBindingInfo * MAX_KEY_BINDINGS)]


class AccessibleIconInfo(Structure):
    _fields_ = [("description", c_wchar * SHORT_STRING_SIZE), ("height", c_int), ("width", c_int)]


class AccessibleIcons(Structure):
    _fields_ = [("iconsCount", c_int), ("iconInfo", AccessibleIconInfo * MAX_ICON_INFO)]


class AccessibleTableInfo(Structure):
    _fields_ = [
        ("caption", JavaObject),
        ("summary", JavaObject),
        ("rowCount", c_int),
        ("columnCount", c_int),
        ("accessibleContext", JavaObject),
        ("accessibleTable", JavaObject),
    ]


class AccessibleTableCellInfo(Structure):
    _fields_ = [
        ("accessibleContext", JavaObject),
        ("index", c_int),
        ("row", c_int),
        ("column", c_int),
        ("rowExtent", c_int),
        ("columnExtent", c_int),
        ("isSelected", c_bool),
    ]


class VisibleChildrenInfo(Structure):
    _fields_ = [("returnedChildrenCount", c_int), ("children", JavaObject * MAX_VISIBLE_CHILDREN_COUNT)]
