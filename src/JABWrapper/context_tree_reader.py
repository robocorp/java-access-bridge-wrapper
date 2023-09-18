import re
import sys
from typing import List

from JABWrapper.context_tree import ContextTree, SearchElement
from JABWrapper.jab_types import (
    AccessibleContextInfo,
    AccessibleIcons,
    AccessibleKeyBindings,
    AccessibleTableInfo,
)

MATCH = re.compile(r"^(\s+)?Role=(.*?), Name=(.*?), VAN=(.*?), Desc=?(.*?)")

MATCH_OPTION = re.compile(
    r"^[\|\s]*?role:(.*?); name:(.*?); virtual_accessible_name:(.*?); description:?(.*?); ancestry:(\d+)*"
)

IntegerLocatorTypes = ["x", "y", "width", "height", "indexInParent", "childrentCount"]


class Row:
    def __init__(self, line: str):
        match = re.search(MATCH, line)
        if match:
            groups = match.groups()
            self.ancestry = int(len(groups[0]) / 2) if groups[0] else 0
            self.role = groups[1][1:-1]  # strip first first and last char
            self.name = groups[2][1:-1]  # strip first first and last char
            self.van = groups[3][1:-1]  # strip first first and last char
            self.desc = groups[4][1:-1]  # strip first first and last char
        else:
            match = re.search(MATCH_OPTION, line)
            groups = match.groups()
            self.role = groups[0]
            self.name = groups[1]
            self.van = groups[2]
            self.desc = groups[3]
            self.ancestry = int(groups[4])

    def __str__(self):
        return f"{self.ancestry} role='{self.role}' name='{self.name}' van='{self.van}' desc='{self.desc}'"


class Node:
    def __init__(self, row):
        self.info = row
        self.parent = None
        self.children = []

    def find_grandparent(self, ancestry):
        if self.info.ancestry == ancestry:
            return self
        if self.parent:
            return self.parent.find_grandparent(ancestry)

    def __str__(self):
        string = str(self.info)
        for child in self.children:
            string += f"\n{child}"
        return string


class Tree:
    def __init__(self, rows):
        self._rows = rows
        self.root = None
        self._current_node = None
        self._parse()

    def _parse(self):
        for row in self._rows:
            if row.ancestry == 0:
                self.root = self._current_node = Node(row)
            # childs child
            if self._current_node.info.ancestry < (row.ancestry - 1):
                self._current_node = self._current_node.children[-1]
            # not child of this node
            if self._current_node.info.ancestry > row.ancestry or self._current_node.info.ancestry == row.ancestry:
                parent = self._current_node.find_grandparent(row.ancestry - 1)
                if parent:
                    self._current_node = parent
            # next child
            if self._current_node.info.ancestry == (row.ancestry - 1):
                child = Node(row)
                self._current_node.children.append(child)
                child.parent = self._current_node
                self._current_node = child

    def __str__(self):
        return str(self.root)


def read_output_file(output_file) -> List[str]:
    with open(output_file) as f:
        return f.readlines()


def parse_output(output: List[str]):
    rows = [Row(item) for item in output if item]
    tree = Tree(rows)
    return tree


class FakeJabWrapper:
    def __init__(self, tree):
        self.ignore_callbacks = True
        self.context: Node = tree.root

    def get_context_info(self, context) -> AccessibleContextInfo:
        return AccessibleContextInfo(
            context.info.name,
            context.info.desc,
            context.info.role,
            "",
            "",
            "",
            0,
            len(context.children),
            0,
            0,
            False,
            False,
            False,
            False,
            False,
        )

    def get_virtual_accessible_name(self, context):
        return context.info.van

    def get_visible_children_count(self, context):
        return len(context.children)

    def get_accessible_key_bindings(self, context):
        return AccessibleKeyBindings(0)

    def get_accessible_icons(self, context):
        return AccessibleIcons(0)

    def get_accessible_selection_count_from_context(self, context):
        return 0

    def get_child_context(self, context, index):
        return context.children[index]

    def get_accessible_table_info(self, context):
        return AccessibleTableInfo(0, 0, 0, 0, 0, 0)


class ContextTreeFaker:
    def __init__(self, tree):
        self._jab_wrapper = FakeJabWrapper(tree)
        self.context_tree = ContextTree(self._jab_wrapper)


class LocatorSimulator:
    def __init__(self, locator_filename: str = "", locator: str = ""):
        self._locator_filename = locator_filename
        self.faker = None

    def _parse_locator(self, locator, strict_default=False) -> List[SearchElement]:
        levels = locator.split(">")
        levels = [lvl.strip() for lvl in levels]
        searches = []
        for lvl in levels:
            conditions = lvl.split(" and ")
            lvl_search = []
            strict_mode = strict_default
            for cond in conditions:
                parts = cond.split(":", 1)
                if len(parts) == 1:
                    parts = ["name", parts[0]]
                elif parts[0].lower() == "strict":
                    strict_mode = bool(parts[1])
                    continue
                elif parts[0] in IntegerLocatorTypes:
                    try:
                        parts[1] = int(parts[1])
                    except ValueError as err:
                        raise Exception("Locator '%s' needs to be of 'integer' type" % parts[0]) from err
                lvl_search.append(SearchElement(parts[0], parts[1], strict=strict_mode))
            searches.append(lvl_search)
        return searches

    def _find_elements(self, locator: str, index: int = None, strict: bool = False):
        searches = self._parse_locator(locator, strict)
        elements = []
        for lvl, search_elements in enumerate(searches):
            if lvl == 0:
                elements = self.faker.context_tree.get_by_attrs(search_elements)
            else:
                sub_matches = []
                for elem in elements:
                    matches = elem.get_by_attrs(search_elements)
                    sub_matches.extend(matches)
                elements = sub_matches
        if index and len(elements) > (index + 1):
            raise AttributeError(
                "Locator '%s' returned only %s elements (can't index element at %s)" % (locator, len(elements), index)
            )
        return elements[index] if index else elements

    def parse_element_tree(self, locator_filename=""):
        if not locator_filename and not self._locator_filename:
            raise Exception("Please provide locator file path")
        if locator_filename:
            self._locator_filename = locator_filename
        output = read_output_file(self._locator_filename)
        tree = parse_output(output)
        self.faker = ContextTreeFaker(tree)

    def find_element(self, locator):
        if not self.faker:
            raise Exception("Please parse element tree first")
        return self._find_elements(locator)


def main():
    output_file = sys.argv[1]
    locator = " ".join(sys.argv[2:])
    simulator = LocatorSimulator(output_file)
    simulator.parse_element_tree()
    for element in simulator.find_element(locator):
        print(str(element))


if __name__ == "__main__":
    main()
