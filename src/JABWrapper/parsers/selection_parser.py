from JABWrapper.jab_types import AccessibleContextInfo, JavaObject
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.parsers.parser_if import Parser


class AccessibleSelectionParser(Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self.selection_count = 0

    def __str__(self) -> str:
        if self._aci.accessibleSelection:
            return f" sel_count={self.selection_count}"
        return ""

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        self.selection_count = jab_wrapper.get_accessible_selection_count_from_context(context)
