import logging
import re
import threading
from dataclasses import dataclass
from typing import List, Optional

from JABWrapper.jab_types import AccessibleContextInfo, JavaObject
from JABWrapper.jab_wrapper import JavaAccessBridgeWrapper
from JABWrapper.parsers.actions_parser import AccessibleActionsParser
from JABWrapper.parsers.hypertext_parser import AccessibleHypertextParser
from JABWrapper.parsers.icon_parser import AccessibleIconParser
from JABWrapper.parsers.keybind_parser import AccessibleKeyBindingsParser
from JABWrapper.parsers.parser_if import Parser
from JABWrapper.parsers.selection_parser import AccessibleSelectionParser
from JABWrapper.parsers.table_parser import AccessibleTableParser
from JABWrapper.parsers.text_parser import AccessibleTextParser
from JABWrapper.parsers.value_parser import AccessibleValueParser
from JABWrapper.utils import SearchElement, log_exec_time, retry_callback


@dataclass
class NodeLocator:
    name: str
    description: str
    role: str
    states: str
    indexInParent: int
    childrenCount: int
    x: int
    y: int
    width: int
    height: int
    ancestry: int


class ContextNode:
    def __init__(
        self,
        jab_wrapper: JavaAccessBridgeWrapper,
        context: JavaObject,
        lock: threading.RLock,
        ancestry: int = 0,
        parse_children: bool = True,
        max_depth: Optional[int] = None,
        parent: Optional["ContextNode"] = None,
    ) -> None:
        self._jab_wrapper = jab_wrapper
        self._lock = lock
        self.ancestry = ancestry
        self.context: JavaObject = context
        self._should_parse_children = parse_children
        self._max_depth = max_depth

        self.state = None
        self.visible_children_count = 0
        self.virtual_accessible_name = None
        self._children: list[ContextNode] = []

        self.parent: Optional[ContextNode] = parent

        # Populate the element with data and its children if enabled.
        self.refresh()

    @property
    def children(self):
        with self._lock:
            return self._children

    def parse_context(self) -> None:
        logging.debug(f"Parsing element={self.context}")
        self._aci: AccessibleContextInfo = self._jab_wrapper.get_context_info(self.context)
        logging.debug(f"Parsed element info={self._aci}")
        self.virtual_accessible_name = self._jab_wrapper.get_virtual_accessible_name(self.context)
        self.visible_children_count = self._jab_wrapper.get_visible_children_count(self.context)
        self.text = AccessibleTextParser(self._aci)
        self.value = AccessibleValueParser(self._aci)
        self.actions = AccessibleActionsParser(self._aci)
        self.keybinds = AccessibleKeyBindingsParser(self._aci)
        self.hypertext = AccessibleHypertextParser(self._aci)
        self.table = AccessibleTableParser(self._aci)
        self.icons = AccessibleIconParser(self._aci)
        self.selections = AccessibleSelectionParser(self._aci)
        self._parsers: List[Parser] = [
            self.text,
            self.value,
            self.actions,
            self.keybinds,
            self.hypertext,
            self.table,
            self.icons,
            self.selections,
        ]
        [parser.parse(self._jab_wrapper, self.context) for parser in self._parsers]

    @property
    def context_info(self) -> AccessibleContextInfo:
        """
        Property:
            The AccessibleContextInfo object. For example:

            {
                "name": "Button",
                "description": "Click button",
                "role": "push button",
                "role_en_US": "push button",
                "states": "enabled,clicked",
                "states_en_US": "enabled,clicked",
                "indexInParent": 1,
                "childrenCount": 10,
                "x": 150,
                "y": 150,
                "width": 800,
                "height": 600,
                "accessibleComponent": True,
                "accessibleAction": True,
                "accessibleSelection": False,
                "accessibleText": False,
                "accessibleValue", False
            }
        """
        return self._aci

    @context_info.setter
    def context_info(self, context_info: AccessibleContextInfo) -> None:
        self._aci = context_info

    def _parse_children(self) -> None:
        if self._max_depth is not None and self.ancestry >= self._max_depth:
            return

        for i in range(0, self._aci.childrenCount):
            child_context = self._jab_wrapper.get_child_context(self.context, i)
            child_node = ContextNode(
                self._jab_wrapper,
                child_context,
                self._lock,
                self.ancestry + 1,
                parse_children=self._should_parse_children,
                max_depth=self._max_depth,
                parent=self,
            )
            self._children.append(child_node)

    def refresh(self):
        """Refresh the current element and its children only.

        Useful when you want to refresh just a subtree of elements starting from the
        current one as root, instead of the entire app.
        """
        with self._lock:
            self.state = None
            self._children.clear()
            self.parse_context()
            if self._should_parse_children:
                self._parse_children()

    def __repr__(self) -> str:
        """
        Returns:
            A string that represents the object tree with detailed Node values.
        """
        string = (
            f"{'| ' * self.ancestry}"
            f"role:{self.context_info.role}; "
            f"name:{self.context_info.name}; "
            f"virtual_accessible_name:{self.virtual_accessible_name}; "
            f"description:{self.context_info.description}; "
            f"ancestry:{self.ancestry}; "
            f"state:{self.state}; "
            f"states:{self.context_info.states}; "
            f"at x:{self.context_info.x} y:{self.context_info.y}; "
            f"width:{self.context_info.width}; "
            f"height:{self.context_info.height}; "
            f"indexInParent:{self.context_info.indexInParent}; "
            f"childrenCount:{self.context_info.childrenCount}; "
            f"visible_children_count:{self.visible_children_count}"
        )
        for parser in self._parsers:
            string += f"{parser}"
        for child in self.children:
            string += f"\n{repr(child)}"
        return string

    def __str__(self) -> str:
        """
        Returns:
            A string of Node values.
        """
        string = (
            f"role:{self.context_info.role}; "
            f"name:{self.context_info.name}; "
            f"virtual_accessible_name:{self.virtual_accessible_name}; "
            f"description:{self.context_info.description}; "
            f"ancestry:{self.ancestry}; "
            f"state:{self.state}; "
            f"states:{self.context_info.states}; "
            f"at x:{self.context_info.x} y:{self.context_info.y}; "
            f"width:{self.context_info.width}; "
            f"height:{self.context_info.height}; "
            f"indexInParent:{self.context_info.indexInParent}; "
            f"childrenCount:{self.context_info.childrenCount}; "
            f"visible_children_count:{self.visible_children_count}"
        )
        for parser in self._parsers:
            string += "{}".format(parser)
        return string

    def get_search_element_tree(self) -> List[NodeLocator]:
        """
        Returns node info for all searchable elements.
        """
        nodes = []
        nodes.append(
            NodeLocator(
                self.context_info.name,
                self.context_info.description,
                self.context_info.role,
                self.context_info.states,
                self.context_info.indexInParent,
                self.context_info.childrenCount,
                self.context_info.x,
                self.context_info.y,
                self.context_info.width,
                self.context_info.height,
                self.ancestry,
            )
        )
        for child in self.children:
            nodes.extend(child.get_search_element_tree())
        return nodes

    def traverse(self):
        yield self
        for child in self.children:
            yield from child.traverse()

    def __iter__(self):
        return self.traverse()

    def _get_node_by_context(self, context: JavaObject):
        if self._jab_wrapper.is_same_object(self.context, context):
            return self
        else:
            for child in self._children:
                node = child._get_node_by_context(context)
                if node:
                    return node

    def _match_attrs(self, search_elements: List[SearchElement]) -> bool:
        for search_element in search_elements:
            attr = getattr(self._aci, search_element.name)
            if isinstance(attr, str) and not search_element.strict:
                if not re.match(search_element.value, attr):
                    return False
            else:
                if not attr == search_element.value:
                    return False
        return True

    def get_by_attrs(self, search_elements: List[SearchElement]) -> List:
        """
        Get element with given search attributes.

        The SearchElement object takes a name of the field and the field value. For example:

        element = context_tree.get_by_attrs([SearchElement("role", "text")])

        Returns:
            An array of matching elements.
        """
        with self._lock:
            elements = list()
            found = self._match_attrs(search_elements)
            if found:
                elements.append(self)
            for child in self._children:
                child_elements = child.get_by_attrs(search_elements)
                elements.extend(child_elements)
            return elements

    def request_focus(self) -> None:
        """
        Request focus for element
        """
        with self._lock:
            self._jab_wrapper.request_focus(self.context)

    def get_actions(self) -> List[str]:
        """
        Get all actions available for element
        """
        with self._lock:
            return self.actions.list_actions()

    def do_action(self, action: str) -> None:
        """
        Do any action found with the get_actions interface

        Will raise APIException if action is not available
        """
        with self._lock:
            self.actions.do_action(self._jab_wrapper, self.context, action)

    def click(self) -> None:
        """
        Do click action for element
        """
        with self._lock:
            self.actions.click(self._jab_wrapper, self.context)

    def insert_text(self, text: str) -> None:
        """
        Do insert content action for element
        """
        with self._lock:
            self.actions.insert_content(self._jab_wrapper, self.context, text)

    def get_visible_children(self) -> List:
        """
        Get visible children nodes for the ContextNode.

        Will only get the immediate children for this node, not the whole ContextTree.

        Returns:
            List of ContextNode objects

        Raises:
            APIException: Failed to get visible children info
        """
        visible_children = []
        logging.debug(f"Expected visible children count={self.visible_children_count}")
        if self.visible_children_count > 0:
            visible_children_info = self._jab_wrapper.get_visible_children(self.context, 0)
            logging.debug(f"Found visible children count={self.visible_children_count}")
            for i in range(0, visible_children_info.returnedChildrenCount):
                visible_child = ContextNode(
                    self._jab_wrapper,
                    visible_children_info.children[i],
                    self._lock,
                    self.ancestry + 1,
                    parse_children=False,
                    parent=self,
                )
                visible_children.append(visible_child)
        return visible_children


class ContextTree:
    @log_exec_time("Init context tree")
    def __init__(self, jab_wrapper: JavaAccessBridgeWrapper, max_depth: Optional[int] = None) -> None:
        self._lock = threading.RLock()
        self._jab_wrapper = jab_wrapper
        self.root = ContextNode(jab_wrapper, jab_wrapper.context, self._lock, parse_children=True, max_depth=max_depth)
        self._register_callbacks()

    def __iter__(self):
        return self.root.traverse()

    def __repr__(self) -> str:
        return f"{repr(self.root)}"

    def __str__(self):
        return f"{self.root}"

    def get_search_element_tree(self):
        return self.root.get_search_element_tree()

    @retry_callback
    def _property_change_cp(self, source: JavaObject, property: str, old_value: str, new_value: str) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                setattr(node.context_info, property, new_value)
                logging.debug(f"Property={property} changed from={old_value} to={new_value} for node={node}")

    @retry_callback
    def _property_name_change_cp(self, source: JavaObject, old_value: str, new_value: str) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                setattr(node.context_info, "name", new_value)
                logging.debug(f"Name changed from={old_value} to={new_value} for node={node}")

    @retry_callback
    def _property_description_change_cp(self, source: JavaObject, old_value: str, new_value: str) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                setattr(node.context_info, "description", new_value)
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
                node.value.value = new_value
                logging.debug(f"Value changed from={old_value} to={new_value} for node={node}")

    @retry_callback
    def _property_selection_change_cp(self, source: JavaObject) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                node.parse_context()
                logging.debug(f"Selected text changed for node={node}")

    @retry_callback
    def _property_text_change_cp(self, source: JavaObject) -> None:
        with self._lock:
            node: ContextNode = self.root._get_node_by_context(source)
            if node:
                node.parse_context()
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
                node.refresh()
                logging.debug(f"Visible data changed for node tree={repr(node)}")

    @retry_callback
    def _property_child_change_cp(self, source: JavaObject, old_child: JavaObject, new_child: JavaObject) -> None:
        # Not needed to track as the visibility change event handles the coordinate update
        logging.debug("Property child change event ignored")

    @retry_callback
    def _property_active_descendent_change_cp(
        self, source: JavaObject, old_child: JavaObject, new_child: JavaObject
    ) -> None:
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
        if self._jab_wrapper.ignore_callbacks:
            logging.debug("Ignoring callback registering for Context Node")
            return

        self._jab_wrapper.clear_callbacks()

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
        self._jab_wrapper.register_callback(
            "property_active_descendent_change", self._property_active_descendent_change_cp
        )
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
        self._jab_wrapper.register_callback(
            "popup_menu_will_become_invisible", self._popup_menu_will_become_invisible_cp
        )
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
