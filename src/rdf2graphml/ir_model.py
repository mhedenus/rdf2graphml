from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class NodeModel:
    """Repräsentiert einen agnostischen Graphen-Knoten."""
    id: str
    label: str = ""
    types: List[str] = field(default_factory=list)
    attributes: Dict[str, List[str]] = field(default_factory=dict)
    style: Dict[str, Any] = field(default_factory=dict)
    url: Optional[str] = None
    tooltip: Optional[str] = None
    parent_id: Optional[str] = None  # Setzt die Hierarchie (Gruppenzugehörigkeit)
    is_group: bool = False


@dataclass
class EdgeModel:
    """Repräsentiert eine agnostische gerichtete Kante."""
    id: str
    source_id: str
    target_id: str
    label: str = ""
    style: Dict[str, Any] = field(default_factory=dict)
    url: Optional[str] = None


@dataclass
class GraphModel:
    """Der vollständige, strukturierte Graph, bereit für den Export."""
    nodes: Dict[str, NodeModel] = field(default_factory=dict)
    edges: List[EdgeModel] = field(default_factory=list)
    image_resources: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def add_node(self, node: NodeModel) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: EdgeModel) -> None:
        self.edges.append(edge)

    def get_roots(self) -> List[NodeModel]:
        """Gibt alle Knoten zurück, die keine Eltern haben (oberste Ebene)."""
        return [n for n in self.nodes.values() if n.parent_id is None]

    def get_children(self, parent_id: str) -> List[NodeModel]:
        """Gibt alle direkten Kind-Knoten einer Gruppe zurück."""
        return [n for n in self.nodes.values() if n.parent_id == parent_id]