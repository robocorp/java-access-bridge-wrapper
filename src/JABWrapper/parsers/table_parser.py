from JABWrapper.jab_types import AccessibleContextInfo, AccessibleTableInfo, JavaObject
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.parsers.parser_if import Parser


class AccessibleTableParser(Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self._table = AccessibleTableInfo()

    def __str__(self) -> str:
        if self._aci.role == "table":
            return f" table={self._table.rowCount},{self._table.columnCount}"
        return ""

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        if self._aci.role == "table":
            self._table = jab_wrapper.get_accessible_table_info(context)

    @property
    def table(self) -> AccessibleTableInfo:
        """
        Property:
            The AccessibleTableInfo object. For example:

            {
                "caption": JavaObject,
                "summary": JavaObject,
                "rowCount": 1,
                "columnCount": 2,
                "accessibleContext": JavaObject,
                "accessibleTable": JavaObject
            }
        """
        return self._table

    @table.setter
    def table(self, table: AccessibleTableInfo) -> None:
        self._table = table
