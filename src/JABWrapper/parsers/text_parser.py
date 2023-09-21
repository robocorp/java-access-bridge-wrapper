from JABWrapper.jab_types import (
    AccessibleContextInfo,
    AccessibleTextAttributesInfo,
    AccessibleTextInfo,
    AccessibleTextItemsInfo,
    AccessibleTextRectInfo,
    AccessibleTextSelectionInfo,
    JavaObject,
)
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.parsers.parser_if import Parser


class AccessibleTextParser(Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self._info = AccessibleTextInfo()
        self._items = AccessibleTextItemsInfo()
        self._selection = AccessibleTextSelectionInfo()
        self._attributes_info = AccessibleTextAttributesInfo()
        self._rect_info = AccessibleTextRectInfo()

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        if self._aci.accessibleText:
            self._info = jab_wrapper.get_context_text_info(context, self._aci.x, self._aci.y)
            self._items = jab_wrapper.get_accessible_text_items(context, 0)
            self._selection = jab_wrapper.get_accessible_text_selection_info(context)
            self._attributes_info = jab_wrapper.get_accessible_text_attributes(context, 0)
            self._rect_info = jab_wrapper.get_accessible_text_rect(context, 0)

    def __str__(self) -> str:
        if not self._aci.accessibleText:
            return ""
        return " tc={} w={} s={} st={};".format(
            self._info.charCount, self._items.word, self._items.sentence, self._selection.selectedText
        )

    @property
    def info(self) -> AccessibleTextInfo:
        """
        Property:
            The AccessibleTextInfo object. For example:

            {
                "charCount": 5,
                "caretIndex": 2,
                "indexAtPoint": 2
            }
        """
        return self._info

    @info.setter
    def info(self, info: AccessibleTextInfo) -> None:
        self._info = info

    @property
    def items(self) -> AccessibleTextItemsInfo:
        """
        Property:
            the AccessibleTextItemsInfo object. For example:

            {
                "letter": "w",
                "word": "random word",
                "sentence": "random word in a sentence"
            }
        """
        return self._items

    @items.setter
    def items(self, items: AccessibleTextItemsInfo) -> None:
        self._items = items

    @property
    def selection(self) -> AccessibleTextSelectionInfo:
        """
        Property:
            the AccessibleTextSelectionInfo object. For example:

            {
                "selectionStartIndex": 0,
                "selectionEndIndex": 6,
                "selectedText": "random"
            }
        """
        return self._selection

    @selection.setter
    def selection(self, selection: AccessibleTextSelectionInfo) -> None:
        self._selection = selection

    @property
    def attributes_info(self) -> AccessibleTextAttributesInfo:
        """
        Property:
            the AccessibleTextAttributesInfo object. For example:

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
        """
        return self._attributes_info

    @attributes_info.setter
    def attributes_info(self, attributes_info: AccessibleTextAttributesInfo) -> None:
        self._attributes_info = attributes_info

    @property
    def rect_info(self) -> AccessibleTextRectInfo:
        """
        Property:
            the AccessibleTextRectInfo object. For example:

            {
                "x": 100,
                "y": 100,
                "width": 100,
                "height": 100
            }
        """
        return self._rect_info

    @rect_info.setter
    def rect_info(self, rect_info: AccessibleTextRectInfo) -> None:
        self._rect_info = rect_info
