from JABWrapper.jab_types import (
    MAX_HYPERLINKS,
    AccessibleContextInfo,
    AccessibleHypertextInfo,
    JavaObject,
)
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.parsers.parser_if import Parser


class AccessibleHypertextParser(Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self._info = AccessibleHypertextInfo()

    def __str__(self) -> str:
        if not self._aci.accessibleText or self._info.linkCount > MAX_HYPERLINKS or self._info.linkCount < 0:
            return ""
        txt = f" links={self._info.linkCount}"
        for i in range(self._info.linkCount):
            txt += f", link={self._info.links[i].text}"
        return txt

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        """
        TODO: Identify which elements may contain hypertext.

        From java documentation (https://docs.oracle.com/javase/6/docs/api/javax/accessibility/AccessibleHypertext.html),
        the AccessibleText element may implement the AccessibleHypertext object, but not all AccessibleText elements do.

        The element JEditorPane.JEditorPaneAccessibleHypertextSupport does implement it, but is identifiable from the AccessibleContextInfo?
        """
        if self._aci.accessibleText:
            self._info = jab_wrapper.get_accessible_hypertext(context)

    @property
    def info(self) -> AccessibleHypertextInfo:
        """
        Property:
            The AccessibleHypertextInfo object. For Example:

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
        """
        return self._info

    @info.setter
    def info(self, info: AccessibleHypertextInfo) -> None:
        self._info = info
