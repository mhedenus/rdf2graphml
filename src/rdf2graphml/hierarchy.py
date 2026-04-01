import logging

logger = logging.getLogger(__name__)


class GraphHierarchy:
    def __init__(self):
        self.parent_of = {}  # child_node -> parent_node
        self.children_of = {}  # parent_node -> set(child_nodes)
        self.groups = set()  # nodes that are explicitly groups

    def add_group(self, group_node):
        self.groups.add(group_node)
        if group_node not in self.children_of:
            self.children_of[group_node] = set()

    def add_relation(self, parent, child):
        # yEd unterstützt keine multiplen Parents. Erster gewinnt.
        if child in self.parent_of and self.parent_of[child] != parent:
            logger.warning(f"Knoten {child} ist bereits in einer Gruppe. Ignoriere Zuordnung zu {parent}.")
            return

        # Zyklenvermeidung (Check, ob child ein Vorfahre von parent ist)
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

        # Sicherstellen, dass parent als Gruppe markiert ist
        self.groups.add(parent)

    def get_roots(self, all_nodes):
        """Gibt alle Knoten zurück, die keine Eltern haben (oberste Ebene)."""
        return [n for n in all_nodes if n not in self.parent_of]