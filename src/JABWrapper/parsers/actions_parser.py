from typing import List

from JABWrapper.jab_types import (
    AccessibleActionsToDo,
    AccessibleContextInfo,
    JavaObject,
)
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.parsers.parser_if import Parser


class AccessibleActionsParser(Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self._actions = dict()

    def __str__(self) -> str:
        if not self._aci.accessibleAction:
            return ""
        return " actions={}".format(", ".join([action for action in self._actions]))

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        self._actions.clear()
        if self._aci.accessibleAction:
            actions = jab_wrapper.get_accessible_actions(context)
            for index in range(actions.actionsCount):
                actionInfo = actions.actionInfo[index]
                self._actions[actionInfo.name.lower()] = actionInfo

    def list_actions(self) -> List[str]:
        return list(self._actions)

    def do_action(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject, action: str) -> None:
        if not action.lower() in self._actions:
            raise NotImplementedError("Does not implement the {} action".format(action))
        actions = AccessibleActionsToDo(actionsCount=1, actions=(self._actions[action],))
        jab_wrapper.do_accessible_actions(context, actions)

    def click(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        self.do_action(jab_wrapper, context, "click")

    def insert_content(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject, text: str) -> None:
        jab_wrapper.set_text_contents(context, text)
