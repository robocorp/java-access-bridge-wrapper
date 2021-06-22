from ctypes import (
    Structure,
    c_float,
    c_int,
    c_int64,
    wintypes
)

MAX_STRING_SIZE = 1024
SHORT_STRING_SIZE = 256

MAX_ACTION_INFO = 256
MAX_ACTIONS_TO_DO = 32

MAX_RELATION_TARGETS = 250
MAX_RELATIONS = 50

MAX_KEY_BINDINGS = 50


class JavaObject(c_int64):
    pass


class AccessibleContextInfo(Structure):
    _fields_ = [
        ('name', wintypes.WCHAR * MAX_STRING_SIZE),
        ('description', wintypes.WCHAR * MAX_STRING_SIZE),
        ('role', wintypes.WCHAR * SHORT_STRING_SIZE),
        ('role_en_US', wintypes.WCHAR * SHORT_STRING_SIZE),
        ('states', wintypes.WCHAR * SHORT_STRING_SIZE),
        ('states_en_US', wintypes.WCHAR * SHORT_STRING_SIZE),
        ('indexInParent', c_int),
        ('childrenCount', c_int),
        ('x', c_int),
        ('y', c_int),
        ('width', c_int),
        ('height', c_int),
        ('accessibleComponent', wintypes.BOOL),
        ('accessibleAction', wintypes.BOOL),
        ('accessibleSelection', wintypes.BOOL),
        ('accessibleText', wintypes.BOOL),
        ('accessibleValue', wintypes.BOOL)
    ]


class AccessBridgeVersionInfo(Structure):
    _fields_ = [
        ('VMversion', wintypes.WCHAR * SHORT_STRING_SIZE),
        ('bridgeJavaClassVersion', wintypes.WCHAR * SHORT_STRING_SIZE),
        ('bridgeJavaDLLVersion', wintypes.WCHAR * SHORT_STRING_SIZE),
        ('bridgeWinDLLVersion', wintypes.WCHAR * SHORT_STRING_SIZE)
    ]


class AccessibleTextInfo(Structure):
    _fields_ = [
        ('charCount', c_int),
        ('caretIndex', c_int),
        ('indexAtPoint', c_int)
    ]


class AccessibleTextItemsInfo(Structure):
    _fields_ = [
        ('letter', wintypes.WCHAR),
        ('word', wintypes.WCHAR * SHORT_STRING_SIZE),
        ('sentence', wintypes.WCHAR * MAX_STRING_SIZE)
    ]


class AccessibleTextSelectionInfo(Structure):
    _fields_ = [
        ('selectionStartIndex', c_int),
        ('selectionEndIndex', c_int),
        ('selectedText', wintypes.WCHAR * MAX_STRING_SIZE)
    ]


class AccessibleTextAttributesInfo (Structure):
    _fields_ = [
        ("bold", wintypes.BOOL),
        ("italic", wintypes.BOOL),
        ("underline", wintypes.BOOL),
        ("strikethrough", wintypes.BOOL),
        ("superscript", wintypes.BOOL),
        ("subscript", wintypes.BOOL),

        ("backgroundColor", wintypes.WCHAR * SHORT_STRING_SIZE),
        ("foregroundColor", wintypes.WCHAR * SHORT_STRING_SIZE),
        ("fontFamily", wintypes.WCHAR * SHORT_STRING_SIZE),
        ("fontSize", c_int),

        ("alignment", c_int),
        ("bidiLevel", c_int),

        ("firstLineIndent", c_float),
        ("leftIndent", c_float),
        ("rightIndent", c_float),
        ("lineSpacing", c_float),
        ("spaceAbove", c_float),
        ("spaceBelow", c_float),

        ("fullAttributesString", wintypes.WCHAR * MAX_STRING_SIZE),
    ]


class AccessibleTextRectInfo(Structure):
    _fields_ = [
        ("x", c_int),
        ("y", c_int),
        ("width", c_int),
        ("height", c_int)
    ]


class AccessibleActionInfo(Structure):
    _fields_ = [
        ("name", wintypes.WCHAR * SHORT_STRING_SIZE)
    ]


class AccessibleActions(Structure):
    _fields_ = [
        ("actionsCount", c_int),
        ("actionInfo", AccessibleActionInfo * MAX_ACTION_INFO)
    ]


class AccessibleActionsToDo(Structure):
    _fields_ = [
        ("actionsCount", c_int),
        ("actions", AccessibleActionInfo * MAX_ACTION_INFO)
    ]


class AccessibleRelationInfo(Structure):
    _fields_ = [
        ("key", wintypes.WCHAR * SHORT_STRING_SIZE),
        ("targetCount", c_int),
        ("targets", JavaObject * MAX_RELATION_TARGETS)
    ]


class AccessibleRelationSetInfo(Structure):
    _fields = [
        ("relationCount", c_int),
        ("AccessibleRelationInfo", AccessibleRelationInfo * MAX_RELATIONS)
    ]


class AccessibleKeyBindingInfo(Structure):
    _fields_ = [
        ("character", wintypes.WCHAR),
        ("modifiers", c_int)
    ]


class AccessibleKeyBindings(Structure):
    _fields_ = [
        ("keyBindingsCount", c_int),
        ("AccessibleKeyBindingInfo", AccessibleKeyBindingInfo * MAX_KEY_BINDINGS)
    ]
