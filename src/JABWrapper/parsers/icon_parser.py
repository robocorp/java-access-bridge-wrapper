from JABWrapper.jab_types import AccessibleContextInfo, AccessibleIcons, JavaObject
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.parsers.parser_if import Parser


class AccessibleIconParser(Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self._icons = AccessibleIcons()

    def __str__(self) -> str:
        string = f" icons={self._icons.iconsCount}"
        if self._icons.iconsCount > 0:
            for index in range(self._icons.iconsCount):
                info = self._icons.iconInfo[index]
                string += f" d={info.description} h={info.height} w={info.width}"
        return string

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        self._icons = jab_wrapper.get_accessible_icons(context)

    @property
    def icons(self) -> AccessibleIcons:
        """
        Property:
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
        """
        return self._icons

    @icons.setter
    def icons(self, icons: AccessibleIcons) -> None:
        self._icons = icons
