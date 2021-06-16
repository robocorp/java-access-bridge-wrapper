import logging
import ctypes
import threading
from typing import Dict, List

from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.jab_types import (
    AccessibleActionsToDo,
    AccessibleKeyBindings,
    AccessibleTextItemsInfo,
    JavaObject,
    AccessibleContextInfo,
    AccessibleTextInfo,
    AccessibleTextSelectionInfo
)
from JABWrapper.utils import log_exec_time


class SearchElement:
    def __init__(self, name, value) -> None:
        self.name = name
        self.value = value


class _Parser:
    def parse() -> None:
        raise NotImplementedError()


class _AccessibleKeyBindingsParser(_Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self.key_bindings = AccessibleKeyBindings()

    def __str__(self) -> str:
        string = f" kbs={self.key_bindings.keyBindingsCount}"
        if self.key_bindings.keyBindingsCount > 0:
            for index in range(self.key_bindings.keyBindingsCount):
                info = self.key_bindings.AccessibleKeyBindingInfo[index]
                string += f" c={info.character} m={info.modifiers}"
        return string

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        self.key_bindings = jab_wrapper.get_accessible_key_bindings(context)


class _AccessibleActionsParser(_Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self.actions = dict()

    def __str__(self) -> str:
        if not self._aci.accessibleAction:
            return ""
        return " actions={}".format(", ".join([action for action in self.actions]))

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        self.actions.clear()
        if self._aci.accessibleAction:
            actions = jab_wrapper.get_accessible_actions(context)
            for index in range(actions.actionsCount):
                actionInfo = actions.actionInfo[index]
                self.actions[actionInfo.name.lower()] = actionInfo

    def do_action(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject, action: str) -> None:
        if not action.lower() in self.actions:
            raise NotImplementedError("Does not implement the {} action".format(action))
        actions = AccessibleActionsToDo(actionsCount=1, actions=(self.actions[action],))
        jab_wrapper.do_accessible_actions(context, actions)

    def click(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        self.do_action(jab_wrapper, context, "click")

    def insert_content(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject, text: str) -> None:
        jab_wrapper.set_text_contents(context, text)


class _AccessibleValueParser(_Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self.value = u''

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        if self._aci.accessibleValue:
            self.value = jab_wrapper.get_current_accessible_value_from_context(context)

    def __str__(self) -> str:
        if not self._aci.accessibleValue:
            return ""
        return " v={};".format(self.value)


class _AccessibleTextParser(_Parser):
    def __init__(self, aci: AccessibleContextInfo) -> None:
        self._aci = aci
        self.info = AccessibleTextInfo()
        self.items = AccessibleTextItemsInfo()
        self.selection = AccessibleTextSelectionInfo()

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        if self._aci.accessibleText:
            self.info = jab_wrapper.get_context_text_info(context, self._aci.x, self._aci.y)
            self.items = jab_wrapper.get_accessible_text_items(context, 0)
            self.selection = jab_wrapper.get_accessible_text_selection_info(context)

    def __str__(self) -> str:
        if not self._aci.accessibleText:
            return ""
        return " tc={} w={} s={} st={};".format(
            self.info.charCount,
            self.items.word,
            self.items.sentence,
            self.selection.selectedText
        )


class ContextNode:
    def __init__(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject, lock, ancestry: int = 0) -> None:
        self._jab_wrapper = jab_wrapper
        self._lock = lock
        self.ancestry = ancestry
        self._context: JavaObject = context
        self._parse_context()
        self.children: list[ContextNode] = []
        self._parse_children()

    def _parse_context(self) -> None:
        self.aci: AccessibleContextInfo = self._jab_wrapper.get_context_info(self._context)
        self.atp = _AccessibleTextParser(self.aci)
        self.avp = _AccessibleValueParser(self.aci)
        self._aap = _AccessibleActionsParser(self.aci)
        self.akbs = _AccessibleKeyBindingsParser(self.aci)
        self._parsers: List[_Parser] = [self.atp, self.avp, self._aap, self.akbs]
        [parser.parse(self._jab_wrapper, self._context) for parser in self._parsers]

    def _parse_children(self) -> None:
        for i in range(0, self.aci.childrenCount):
            child_context = self._jab_wrapper.get_child_context(self._context, i)
            child_node = ContextNode(self._jab_wrapper, child_context, self._lock, self.ancestry + 1)
            self.children.append(child_node)

    def __repr__(self) -> str:
        """
        Returns a string that represents the object tree with detailed Node values
        """
        string = "{}C={}, Role={}, Name={}, Desc={}, at x={}:y={} w={} h={}; cc={};".format(
            '  ' * self.ancestry,
            self._context,
            repr(self.aci.role),
            repr(self.aci.name),
            repr(self.aci.description),
            self.aci.x,
            self.aci.y,
            self.aci.width,
            self.aci.height,
            self.aci.childrenCount
        )
        for parser in self._parsers:
            string += f"{parser}"
        for child in self.children:
            string += f"\n{repr(child)}"
        return string

    def __str__(self) -> str:
        """
        Returns a string of Node values
        """
        string = "Role={}, Name={}, Desc={}, at x={}:y={} w={} h={}; cc={};".format(
            repr(self.aci.role),
            repr(self.aci.name),
            repr(self.aci.description),
            self.aci.x,
            self.aci.y,
            self.aci.width,
            self.aci.height,
            self.aci.childrenCount
        )
        for parser in self._parsers:
            string += "{}".format(parser)
        return string

    def refresh(self) -> None:
        with self._lock:
            self._parse_context()
            for child in self.children:
                child.refresh()

    def update(self, context: JavaObject) -> bool:
        """
        Find the matching node with context object from bottom up.

        If match is found, update the context of the node.
        """
        with self._lock:
            # Start from bottom up
            for child in self.children:
                updated = child.update(context)
                if updated:
                    return True

            # If matching object found, update context
            try:
                if self._jab_wrapper.is_same_object(self._context, context):
                    self._context = context
                    self._parse_context()
                    return True
            except ctypes.ArgumentError as e:
                # TODO: Should the object be dropped from the tree?
                # Find out why the object query fails in Java Access Bridge depending on timings
                logging.error(f"JAB object match error={e}")

            return False

    def get_by_attrs(self, search_elements: List[SearchElement]) -> List:
        """
        Get element with given seach attributes.

        The SearchElement object takes a name of the field and the field value:
        element = context_tree.get_by_attrs([SearchElement("role", "text")])

        Returns an array of matching elements.
        """
        with self._lock:
            elements = list()
            found = all([getattr(self.aci, search_element.name).startswith(search_element.value) for search_element in search_elements])
            if found:
                elements.append(self)
            for child in self.children:
                child_elements = child.get_by_attrs(search_elements)
                elements.extend(child_elements)
            return elements

    def request_focus(self) -> None:
        """
        Request focus for element
        """
        with self._lock:
            self._jab_wrapper.request_focus(self._context)

    def get_actions(self) -> Dict:
        """
        Get all actions available for element
        """
        with self._lock:
            return self._aap.actions

    def do_action(self, action: str) -> None:
        """
        Do any action found with the get_actions interface

        Will raise APIException is action is not available
        """
        with self._lock:
            self._aap.do_action(self._jab_wrapper, self._context, action)

    def click(self) -> None:
        """
        Do click action for element
        """
        with self._lock:
            self._aap.click(self._jab_wrapper, self._context)

    def insert_text(self, text: str) -> None:
        """
        Do insert content action for element
        """
        with self._lock:
            self._aap.insert_content(self._jab_wrapper, self._context, text)


class ContextTree:
    @log_exec_time("Init context tree")
    def __init__(self, jab_wrapper: JavaAccessBridgeWrapper) -> None:
        self._lock = threading.RLock()
        self._jab_wrapper = jab_wrapper
        self.root = ContextNode(jab_wrapper, jab_wrapper.context, self._lock)
        self._register_callbacks()

    def __repr__(self) -> str:
        return f"{repr(self.root)}"

    def __str__(self):
        return f"{self.root}"

    def _update_node_cp(self, source: JavaObject) -> None:
        self.root.update(source)

    def _property_changed_cp(self, source: JavaObject, property: str, old_value: str, new_value: str) -> None:
        logging.debug(f"Property name change={source} p={property} ov={old_value} nv={new_value}")
        self._update_node_cp(source)

    def _property_name_change_cp(self, source: JavaObject, old_value: str, new_value: str) -> None:
        logging.debug(f"Property name change={source} ov={old_value} nv={new_value}")
        self._update_node_cp(source)

    def _property_description_change_cp(self, source: JavaObject, old_value: str, new_value: str) -> None:
        logging.debug(f"Property description change={source} ov={old_value} nv={new_value}")
        self._update_node_cp(source)

    def _property_state_change_cp(self, source: JavaObject, old_value: str, new_value: str) -> None:
        logging.debug(f"Property state change={source} ov={old_value} nv={new_value}")
        self._update_node_cp(source)

    def _register_callbacks(self) -> None:
        """
        Register callbacks to the jab wrapper when context updated events
        are generated from the Access Bridge
        """
        self._jab_wrapper.register_callback("property_changed", self._property_changed_cp)
        self._jab_wrapper.register_callback("property_text_changed", self._update_node_cp)
        self._jab_wrapper.register_callback("property_name_change", self._property_name_change_cp)
        self._jab_wrapper.register_callback("property_description_change", self._property_description_change_cp)
        self._jab_wrapper.register_callback("property_state_change", self._property_state_change_cp)
        self._jab_wrapper.register_callback("menu_selected", self._update_node_cp)
        self._jab_wrapper.register_callback("menu_deselected", self._update_node_cp)
        self._jab_wrapper.register_callback("menu_calceled", self._update_node_cp)
        self._jab_wrapper.register_callback("focus_gained", self._update_node_cp)
        self._jab_wrapper.register_callback("focus_lost", self._update_node_cp)
        self._jab_wrapper.register_callback("mouse_clicked", self._update_node_cp)
        self._jab_wrapper.register_callback("mouse_entered", self._update_node_cp)
        self._jab_wrapper.register_callback("mouse_exited", self._update_node_cp)
        self._jab_wrapper.register_callback("mouse_pressed", self._update_node_cp)
        self._jab_wrapper.register_callback("mouse_released", self._update_node_cp)
        self._jab_wrapper.register_callback("popup_menu_canceled", self._update_node_cp)
        self._jab_wrapper.register_callback("popup_menu_will_become_invisible", self._update_node_cp)
        self._jab_wrapper.register_callback("popup_menu_will_become_visible", self._update_node_cp)

    @log_exec_time
    def refresh(self) -> None:
        """
        Refresh the context tree
        """
        self.root.refresh()

    def get_by_attrs(self, search_elements: List[SearchElement]) -> List[ContextNode]:
        """
        Find an element from the context tree.

        The root node has the same API as each child node inside the tree.

        The SearchElement object takes a name of the field and the field value:
        element = context_tree.get_by_attrs([SearchElement("role", "text")])

        Returns an array of matching elements.
        """
        return self.root.get_by_attrs(search_elements)
