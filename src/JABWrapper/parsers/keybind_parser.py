from JABWrapper.jab_types import (
    AccessibleContextInfo,
    AccessibleKeyBindings,
    JavaObject,
)
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.parsers.parser_if import Parser


class AccessibleKeyBindingsParser(Parser):
    """
    Attribute keybinds contains
    """

    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self._keybinds = AccessibleKeyBindings()

    def __str__(self) -> str:
        string = f" kbs={self.keybinds.keyBindingsCount}"
        if self.keybinds.keyBindingsCount > 0:
            for index in range(self.keybinds.keyBindingsCount):
                info = self.keybinds.AccessibleKeyBindingInfo[index]
                string += f" c={info.character} m={info.modifiers}"
        return string

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        self.keybinds = jab_wrapper.get_accessible_key_bindings(context)

    @property
    def keybinds(self) -> AccessibleKeyBindings:
        """
        Property:
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
        """
        return self._keybinds

    @keybinds.setter
    def keybinds(self, keybinds: AccessibleKeyBindings) -> None:
        self._keybinds = keybinds
