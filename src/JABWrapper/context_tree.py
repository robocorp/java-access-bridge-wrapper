import logging
import threading
from typing import Dict, List

from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.jab_types import (
    AccessibleActionsToDo,
    AccessibleKeyBindings,
    AccessibleTextAttributesInfo,
    AccessibleTextItemsInfo,
    AccessibleTextRectInfo,
    JavaObject,
    AccessibleContextInfo,
    AccessibleTextInfo,
    AccessibleTextSelectionInfo
)
from JABWrapper.utils import log_exec_time, retry_callback


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
        self.min = u''
        self.max = u''

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        if self._aci.accessibleValue:
            self.value = jab_wrapper.get_current_accessible_value_from_context(context)
            self.min = jab_wrapper.get_minimum_accessible_value_from_context(context)
            self.max = jab_wrapper.get_maximum_accessible_value_from_context(context)

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
        self.attributes_info = AccessibleTextAttributesInfo()
        self.rect_info = AccessibleTextRectInfo()

    def parse(self, jab_wrapper: JavaAccessBridgeWrapper, context: JavaObject) -> None:
        if self._aci.accessibleText:
            self.info = jab_wrapper.get_context_text_info(context, self._aci.x, self._aci.y)
            self.items = jab_wrapper.get_accessible_text_items(context, 0)
            self.selection = jab_wrapper.get_accessible_text_selection_info(context)
            self.attributes_info = jab_wrapper.get_accessible_text_attributes(context, 0)
            self.rect_info = jab_wrapper.get_accessible_text_rect(context, 0)

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
        self.state = None
        self.virtual_accessible_name = None
        self._parse_context()
        self.children: list[ContextNode] = []
        self._parse_children()

    def _parse_context(self) -> None:
        self.aci: AccessibleContextInfo = self._jab_wrapper.get_context_info(self._context)
        self.virtual_accessible_name = self._jab_wrapper.get_virtual_accessible_name(self._context)
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
        string = "{}C={}, Role={}, Name={}, VAN={}, Desc={}, St={}, Sts={}, at x={}:y={} w={} h={}; cc={};".format(
            '  ' * self.ancestry,
            self._context,
            repr(self.aci.role),
            repr(self.aci.name),
            repr(self.virtual_accessible_name),
            repr(self.aci.description),
            repr(self.state),
            repr(self.aci.states),
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
        string = "Role={}, Name={}, VAN={}, Desc={}, St={}, Sts={}, at x={}:y={} w={} h={}; cc={};".format(
            repr(self.aci.role),
            repr(self.aci.name),
            repr(self.virtual_accessible_name),
            repr(self.aci.description),
            repr(self.state),
            repr(self.aci.states),
            self.aci.x,
            self.aci.y,
            self.aci.width,
            self.aci.height,
            self.aci.childrenCount
        )
        for parser in self._parsers:
            string += "{}".format(parser)
        return string

    def _get_node_by_context(self, context: JavaObject):
        if self._jab_wrapper.is_same_object(self._context, context):
            return self
        else:
            for child in self.children:
                node = child._get_node_by_context(context)
                if node:
                    return node

    def _update_node(self) -> None:
        self.children = []
        self._parse_context()
        self._parse_children()

    def _van_match(self, search_elements: List[SearchElement]) -> bool:
        for search_element in search_elements:
            if search_element.name == "VAN":
                if search_element.value != self.virtual_accessible_name:
                    return False
        return True

    def get_by_attrs(self, search_elements: List[SearchElement]) -> List:
        """
        Get element with given seach attributes.

        The SearchElement object takes a name of the field and the field value:
        element = context_tree.get_by_attrs([SearchElement("role", "text")])

        Returns an array of matching elements.
        """
        with self._lock:
            elements = list()
            van_match = self._van_match(search_elements)
            found = all([getattr(self.aci, search_element.name).startswith(search_element.value) for search_element in search_elements])
            if found and van_match:
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

    @retry_callback
    def _property_change_cp(self, source: JavaObject, property: str, old_value: str, new_value: str) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                setattr(node.aci, property, new_value)
                logging.debug(f"Property={property} changed from={old_value} to={new_value} for node={node}")

    @retry_callback
    def _property_name_change_cp(self, source: JavaObject, old_value: str, new_value: str) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                setattr(node.aci, "name", new_value)
                logging.debug(f"Name changed from={old_value} to={new_value} for node={node}")

    @retry_callback
    def _property_description_change_cp(self, source: JavaObject, old_value: str, new_value: str) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                setattr(node.aci, "description", new_value)
                logging.debug(f"Description changed from={old_value} to={new_value} for node={node}")

    @retry_callback
    def _property_state_change_cp(self, source: JavaObject, old_value: str, new_value: str) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                node.state = new_value
                logging.debug(f"State changed from={old_value} to={new_value} for node={node}")

    @retry_callback
    def _property_value_change_cp(self, source: JavaObject, old_value: str, new_value: str) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                node.avp.value = new_value
                logging.debug(f"Value changed from={old_value} to={new_value} for node={node}")

    @retry_callback
    def _property_selection_change_cp(self, source: JavaObject) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                node._parse_context()
                logging.debug(f"Selected text changed for node={node}")

    @retry_callback
    def _property_text_change_cp(self, source: JavaObject) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                node._parse_context()
                logging.debug(f"Text changed for node={node}")

    @retry_callback
    def _property_caret_change_cp(self, source: JavaObject, old_pos: int, new_pos: int) -> None:
        # Caret information is not stored in the node component
        logging.debug("Property caret change event ignored")

    @retry_callback
    def _visible_data_change_cp(self, source: JavaObject) -> None:
        with self._lock:
            node = self.root._get_node_by_context(source)
            if node:
                node._update_node()
                logging.debug(f"Visible data changed for node tree={repr(node)}")

    @retry_callback
    def _property_child_change_cp(self, source: JavaObject, old_child: JavaObject, new_child: JavaObject) -> None:
        # Not needed to track as the visibility change event handles the coordinate update
        logging.debug("Property child change event ignored")

    @retry_callback
    def _property_active_descendent_change_cp(self, source: JavaObject, old_child: JavaObject, new_child: JavaObject) -> None:
        # The activity status is not stored inside the tree model
        logging.debug("Property active descendent change event ignored")

    @retry_callback
    def _property_table_model_change_cp(self, source: JavaObject, old_value: str, new_value: str) -> None:
        # TODO: Add table model parsing
        logging.debug("Property table model change event ignored")

    @retry_callback
    def _menu_selected_cp(self, source: JavaObject) -> None:
        # All menu events can be ignored as the visibility change event already gives needed information update to the context tree
        logging.debug("Menu selected event ignored")

    @retry_callback
    def _menu_deselected_cp(self, source: JavaObject) -> None:
        # All menu events can be ignored as the visibility change event already gives needed information update to the context tree
        logging.debug("Menu deselected event ignored")

    @retry_callback
    def _menu_canceled_cp(self, source: JavaObject) -> None:
        # All menu events can be ignored as the visibility change event already gives needed information update to the context tree
        logging.debug("Menu canceled event ignored")

    @retry_callback
    def _focus_gained_cp(self, source: JavaObject) -> None:
        # State information is not stored in the context tree
        logging.debug("Focus gained event ignored")

    @retry_callback
    def _focus_lost_cp(self, source: JavaObject) -> None:
        # State information is not stored in the context tree
        logging.debug("Focus lost event ignored")

    @retry_callback
    def _caret_update_cp(self, source: JavaObject) -> None:
        # Caret information is not stored in the context tree
        logging.debug("Caret update event ignored")

    @retry_callback
    def _mouse_clicked_cp(self, source: JavaObject) -> None:
        # Ignore the mouse events, as the change events will update the context tree
        logging.debug("mouse clicked event ignored")

    @retry_callback
    def _mouse_entered_cp(self, source: JavaObject) -> None:
        # Ignore the mouse events, as the change events will update the context tree
        logging.debug("mouse entered event ignored")

    @retry_callback
    def _mouse_exited_cp(self, source: JavaObject) -> None:
        # Ignore the mouse events, as the change events will update the context tree
        logging.debug("mouse exited event ignored")

    @retry_callback
    def _mouse_pressed_cp(self, source: JavaObject) -> None:
        # Ignore the mouse events, as the change events will update the context tree
        logging.debug("mouse pressed event ignored")

    @retry_callback
    def _mouse_released_cp(self, source: JavaObject) -> None:
        # Ignore the mouse events, as the change events will update the context tree
        logging.debug("mouse released event ignored")

    @retry_callback
    def _popup_menu_canceled_cp(self, source: JavaObject) -> None:
        # Ignore the popup events
        logging.debug("popup menu canceled event ignored")

    @retry_callback
    def _popup_menu_will_become_invisible_cp(self, source: JavaObject) -> None:
        # Ignore the popup events
        logging.debug("popup menu will become invisible event ignored")

    @retry_callback
    def _popup_menu_will_become_visible_cp(self, source: JavaObject) -> None:
        # Ignore the popup events
        logging.debug("popup menu will become visible event ignored")

    def _register_callbacks(self) -> None:
        """
        Register callbacks to the jab wrapper when context updated events
        are generated from the Access Bridge
        """
        # Property change event handlers
        self._jab_wrapper.register_callback("property_change", self._property_change_cp)
        self._jab_wrapper.register_callback("property_name_change", self._property_name_change_cp)
        self._jab_wrapper.register_callback("property_description_change", self._property_description_change_cp)
        self._jab_wrapper.register_callback("property_state_change", self._property_state_change_cp)
        self._jab_wrapper.register_callback("property_value_change", self._property_value_change_cp)
        self._jab_wrapper.register_callback("property_selection_change", self._property_selection_change_cp)
        self._jab_wrapper.register_callback("property_text_change", self._property_text_change_cp)
        self._jab_wrapper.register_callback("property_caret_change", self._property_caret_change_cp)
        self._jab_wrapper.register_callback("property_visible_data_change", self._visible_data_change_cp)
        self._jab_wrapper.register_callback("property_child_change", self._property_child_change_cp)
        self._jab_wrapper.register_callback("property_active_descendent_change", self._property_active_descendent_change_cp)
        self._jab_wrapper.register_callback("property_table_model_change", self._property_table_model_change_cp)
        # Menu event handlers
        self._jab_wrapper.register_callback("menu_selected", self._menu_selected_cp)
        self._jab_wrapper.register_callback("menu_deselected", self._menu_deselected_cp)
        self._jab_wrapper.register_callback("menu_calceled", self._menu_canceled_cp)
        # Focus event handlers
        self._jab_wrapper.register_callback("focus_gained", self._focus_gained_cp)
        self._jab_wrapper.register_callback("focus_lost", self._focus_lost_cp)
        # Caret update event handler
        self._jab_wrapper.register_callback("caret_update", self._caret_update_cp)
        # Mouse events
        self._jab_wrapper.register_callback("mouse_clicked", self._mouse_clicked_cp)
        self._jab_wrapper.register_callback("mouse_entered", self._mouse_entered_cp)
        self._jab_wrapper.register_callback("mouse_exited", self._mouse_exited_cp)
        self._jab_wrapper.register_callback("mouse_pressed", self._mouse_pressed_cp)
        self._jab_wrapper.register_callback("mouse_released", self._mouse_released_cp)
        # Popup menu events
        self._jab_wrapper.register_callback("popup_menu_canceled", self._popup_menu_canceled_cp)
        self._jab_wrapper.register_callback("popup_menu_will_become_invisible", self._popup_menu_will_become_invisible_cp)
        self._jab_wrapper.register_callback("popup_menu_will_become_visible", self._popup_menu_will_become_visible_cp)

    def get_by_attrs(self, search_elements: List[SearchElement]) -> List[ContextNode]:
        """
        Find an element from the context tree.

        The root node has the same API as each child node inside the tree.

        The SearchElement object takes a name of the field and the field value:
        element = context_tree.get_by_attrs([SearchElement("role", "text")])

        Returns an array of matching elements.
        """
        return self.root.get_by_attrs(search_elements)
