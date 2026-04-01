import logging
from typing import Dict, Set, List
from rdflib.term import Node

logger = logging.getLogger(__name__)


class GraphHierarchy:
    def __init__(self) -> None:
        self.parent_of: Dict[Node, Node] = {}
        self.children_of: Dict[Node, Set[Node]] = {}
        self.groups: Set[Node] = set()

    def add_group(self, group_node: Node) -> None:
        self.groups.add(group_node)
        if group_node not in self.children_of:
            self.children_of[group_node] = set()

    def add_relation(self, parent: Node, child: Node) -> None:
        if child in self.parent_of and self.parent_of[child] != parent:
            logger.warning(f"Knoten {child} ist bereits in einer Gruppe. Ignoriere Zuordnung zu {parent}.")
            return

        current = parent
        while current in self.parent_of:
            current = self.parent_of[current]
            if current == child:
                logger.warning(f"Zyklus erkannt! {parent} -> {child} übersprungen.")
                return

        self.parent_of[child] = parent
        if parent not in self.children_of:
            self.children_of[parent] = set()
        self.children_of[parent].add(child)

        self.groups.add(parent)

    def get_roots(self, all_nodes: Set[Node]) -> List[Node]:
        """Gibt alle Knoten zurück, die keine Eltern haben (oberste Ebene)."""
        return [n for n in all_nodes if n not in self.parent_of]