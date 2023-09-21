from JABWrapper.jab_types import AccessibleContextInfo, JavaObject
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.parsers.parser_if import Parser


class AccessibleValueParser(Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self.value = ""
        self.min = ""
        self.max = ""

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        if self._aci.accessibleValue:
            self.current = jab_wrapper.get_current_accessible_value_from_context(context)
            self.min = jab_wrapper.get_minimum_accessible_value_from_context(context)
            self.max = jab_wrapper.get_maximum_accessible_value_from_context(context)

    def __str__(self) -> str:
        if not self._aci.accessibleValue:
            return ""
        return " v={};".format(self.value)
