import logging
from dataclasses import dataclass, field
from typing import Set, Dict, List, Tuple, Any, Optional

from rdflib import Literal, BNode, URIRef, Dataset
from rdflib.namespace import RDFS, RDF, Namespace
from rdflib.term import Node

from .config import ConverterConfig
from .hierarchy import GraphHierarchy
from .icon_loader import IconLoader
from .model import RDF2GRAPHML_NS_BASE, RDF2GRAPHML_COLOR, RDF2GRAPHML_SHAPE, RDF2GRAPHML_LINK
from .ir_model import GraphModel, NodeModel, EdgeModel
from .graphml_writer import GraphMLWriter

logger = logging.getLogger(__name__)

# --- Konstanten ---
LIST_NS_BASE: str = RDF2GRAPHML_NS_BASE
LIST_NS_INDEX: str = f"{LIST_NS_BASE}index#"
LIST_TYPE_URI: URIRef = URIRef(f"{LIST_NS_BASE}List")
RDF_CONTAINER_MEMBER = "http://www.w3.org/1999/02/22-rdf-syntax-ns#_"


@dataclass
class InternalNodeData:
    """Temporärer Datenspeicher für die RDF-Eigenschaften während der Analysephase."""
    rdf_node: Node
    types: List[Node] = field(default_factory=list)
    attributes: Dict[str, List[str]] = field(default_factory=dict)
    display_labels_raw: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    value: Optional[str] = None
    comment: Optional[str] = None
    effective_style: Dict[str, Any] = field(default_factory=dict)


class RDFToGraphModelConverter:
    """
    Analysiert RDF-Graphen und überführt sie in ein agnostisches Zwischenmodell (GraphModel).
    Bietet über save() eine abwärtskompatible Brücke zum GraphMLWriter.
    """

    def __init__(self, config: ConverterConfig) -> None:
        self.config = config
        self.icon_loader = IconLoader()

        self.nodes_to_draw: Set[Node] = set()
        self.internal_nodes: Dict[Node, InternalNodeData] = {}
        self.nodes_forced_as_attributes: Set[Node] = set()

        self.hierarchy: GraphHierarchy = GraphHierarchy()
        self.graph_model: Optional[GraphModel] = None

    def _get_internal_node(self, node: Node) -> InternalNodeData:
        """Zentrale Lazy-Initialisierung für temporäre Knotendaten."""
        if node not in self.internal_nodes:
            self.internal_nodes[node] = InternalNodeData(rdf_node=node)
        return self.internal_nodes[node]

    def _preprocess_lists(self, rdf_graph: Dataset) -> None:
        """Überführt RDF-Listen (rdf:first/rdf:rest) in indizierte Repräsentationen."""
        rest_objects = set(rdf_graph.objects(predicate=RDF.rest))
        list_heads = set(rdf_graph.subjects(predicate=RDF.first)) - rest_objects

        triples_to_remove: List[Tuple[Node, Node, Node]] = []
        triples_to_add: List[Tuple[Node, Node, Node]] = []

        for head in list_heads:
            current = head
            index = 1

            while current and current != RDF.nil:
                first_val = next(rdf_graph.objects(subject=current, predicate=RDF.first), None)
                rest_val = next(rdf_graph.objects(subject=current, predicate=RDF.rest), None)

                if first_val is not None:
                    triples_to_add.append((head, URIRef(f"{LIST_NS_INDEX}{index}"), first_val))
                    index += 1

                for p in (RDF.first, RDF.rest):
                    for o in rdf_graph.objects(subject=current, predicate=p):
                        triples_to_remove.append((current, p, o))

                if rest_val != RDF.nil:
                    for s in rdf_graph.subjects(object=rest_val, predicate=self.config.group_contains):
                        triples_to_remove.append((s, self.config.group_contains, rest_val))

                current = rest_val

            triples_to_add.append((head, RDF.type, LIST_TYPE_URI))
            triples_to_add.append((head, RDFS.label, Literal("0..n")))

        for t in triples_to_remove:
            rdf_graph.remove(t)
        for t in triples_to_add:
            rdf_graph.add(t)

    def _pass_1_collect_data(self, rdf_graph: Dataset) -> None:
        """Sammelt alle strukturellen Daten, Attribute und berechnet die Stile."""
        allowed_triples = self._collect_structural_data(rdf_graph)
        self._extract_node_properties(allowed_triples)
        self._resolve_effective_styles()

    def _collect_structural_data(self, rdf_graph: Dataset) -> List[Tuple[Node, Node, Node]]:
        """Filtert Triples anhand der Konfiguration und baut die Gruppenhierarchie auf."""
        allowed_triples: List[Tuple[Node, Node, Node]] = []

        for s, p, o, _ in rdf_graph:
            if self.config.group_type and p == RDF.type and o == self.config.group_type:
                self.hierarchy.add_group(s)
                self.nodes_to_draw.add(s)

            if self.config.group_contains and p == self.config.group_contains:
                self.hierarchy.add_relation(parent=s, child=o)
                self.nodes_to_draw.add(s)
                self.nodes_to_draw.add(o)

            is_list_generated = str(p).startswith(LIST_NS_BASE)
            is_structural = (p == RDF.type or p == RDFS.label or p == RDFS.comment or
                             p in self.config.icon_locators or is_list_generated or
                             p == self.config.group_contains or p == RDF2GRAPHML_COLOR or
                             p == RDF2GRAPHML_SHAPE)

            if not is_structural and not self.config.is_predicate_allowed(p):
                continue

            if p == RDF.type and not self.config.is_type_allowed(o):
                continue

            allowed_triples.append((s, p, o))
        return allowed_triples

    def _extract_node_properties(self, allowed_triples: List[Tuple[Node, Node, Node]]) -> None:
        """Extrahiert Labels, Werte, Kommentare und packt Literal-Eigenschaften in Attribute."""
        for s, p, o in allowed_triples:
            s_node = self._get_internal_node(s)

            if p in self.config.node_properties or p in self.config.icon_locators or (
                    p == RDF.type and not self.config.type_as_edge) or p == RDF2GRAPHML_COLOR or p == RDF2GRAPHML_SHAPE:
                self.nodes_forced_as_attributes.add(o)

            if p == RDFS.label and isinstance(o, Literal):
                lang = o.language if hasattr(o, 'language') else None
                s_node.display_labels_raw.append((str(o), lang))
            elif p == RDF.value:
                s_node.value = str(o)
            elif p == RDFS.comment:
                s_node.comment = str(o)
            elif p in self.config.icon_locators:
                s_node.effective_style["icon"] = str(o)
            elif p == RDF2GRAPHML_COLOR:
                s_node.effective_style["color"] = str(o)
            elif p == RDF2GRAPHML_SHAPE:
                s_node.effective_style["shape"] = str(o)
            elif p == RDF.type:
                s_node.types.append(o)

        for s, p, o in allowed_triples:
            if s not in self.nodes_forced_as_attributes:
                self.nodes_to_draw.add(s)

            if p == RDFS.comment or p in self.config.icon_locators or p == self.config.group_contains or p == RDF2GRAPHML_COLOR or p == RDF2GRAPHML_SHAPE:
                continue

            if isinstance(o, Literal) or p in self.config.node_properties or (
                    p == RDF.type and not self.config.type_as_edge):
                s_node = self._get_internal_node(s)
                p_str = str(p)
                if p_str not in s_node.attributes:
                    s_node.attributes[p_str] = []

                val_str = f"{o} (@{o.language})" if getattr(o, "language", None) else str(o)
                s_node.attributes[p_str].append(val_str)
            elif o not in self.nodes_forced_as_attributes:
                self.nodes_to_draw.add(o)

    def _get_best_node_style(self, node: Node) -> Optional[Dict[str, Any]]:
        """Ermittelt den passendsten Stil basierend auf der Typ-Priorität."""
        g_node = self._get_internal_node(node)
        types = sorted(g_node.types, key=str)
        best_style = None
        best_priority = -1
        for t in types:
            if t in self.config.type_styles:
                style = self.config.type_styles[t]
                priority = style.get("priority", 0)
                if best_style is None or priority > best_priority:
                    best_style = style
                    best_priority = priority
        return best_style

    def _resolve_effective_styles(self) -> None:
        """Berechnet die finalen visuellen Stile (Farbe, Form, Icon) für jeden sichtbaren Knoten."""
        for node in self.nodes_to_draw:
            g_node = self._get_internal_node(node)
            node_style = g_node.effective_style
            best_type_style = self._get_best_node_style(node) or {}

            if isinstance(node, BNode):
                default_style = self.config.default_node_style.get("blank_nodes", {})
            else:
                default_style = self.config.default_node_style.get("uri_nodes", {})

            if "icon" not in node_style and "icon" in best_type_style:
                node_style["icon"] = best_type_style["icon"]

            if "color" not in node_style:
                node_style["color"] = best_type_style.get("color", default_style.get("color", "#E8EEF7"))

            if "shape" not in node_style:
                node_style["shape"] = best_type_style.get("shape", default_style.get("shape", "roundrectangle"))

    def _get_display_label(self, node: Node, rdf_graph: Dataset) -> str:
        """Ermittelt das optimale Anzeigen-Label unter Beachtung der bevorzugten Sprache."""
        g_node = self._get_internal_node(node)
        labels = g_node.display_labels_raw

        if labels:
            pref_lang = self.config.preferred_language
            pref_labels = [text for text, lang in labels if lang == pref_lang]
            if pref_labels:
                return sorted(pref_labels)[0]

            no_lang_labels = [text for text, lang in labels if not lang]
            if no_lang_labels:
                return sorted(no_lang_labels)[0]

            return sorted([text for text, lang in labels])[0]
        else:
            if g_node.value:
                return g_node.value
            else:
                if isinstance(node, BNode):
                    return ""
                else:
                    try:
                        prefix, namespace, name = rdf_graph.namespace_manager.compute_qname(node)
                        if prefix:
                            return f"{prefix}:{name}"
                        return name
                    except Exception:
                        return f"<{str(node)}>"

    def _fetch_images(self) -> Dict[str, Dict[str, Any]]:
        """Lädt alle benötigten Icons herunter und konvertiert sie in Base64."""
        resource_id = 1
        seen_sources: Dict[str, Dict[str, Any]] = {}
        for g_node in self.internal_nodes.values():
            style = g_node.effective_style
            if "icon" in style:
                src = style["icon"]
                is_local = not src.startswith(("http://", "https://"))
                if src not in seen_sources:
                    logger.debug(f"Processing image: {src}")
                    result = self.icon_loader.load_icon_as_base64(
                        src,
                        is_local,
                        self.config.icon_height,
                        self.config.base_dir
                    )
                    if result and isinstance(result, tuple) and len(result) == 2:
                        b64, width = result
                        if b64 and width:
                            seen_sources[src] = {"id": resource_id, "base64": b64, "width": width}
                            resource_id += 1
                    else:
                        logger.warning(f"Image could not be loaded and will be skipped: {src}")
        return seen_sources

    def _determine_edge_label(self, p_str: str, rdf_graph: Dataset) -> str:
        """Generiert ein lesbares Text-Label für eine Kante basierend auf ihrer Prädikats-URI."""
        if p_str.startswith(LIST_NS_INDEX):
            return "#" + p_str.split("#")[-1]
        elif p_str.startswith(RDF_CONTAINER_MEMBER):
            return "#" + p_str.split("_")[-1]

        try:
            prefix, namespace, name = rdf_graph.namespace_manager.compute_qname(URIRef(p_str))
            if prefix:
                return f"{prefix}:{name}"
            return name
        except Exception:
            return p_str.split("/")[-1].split("#")[-1] or "link"

    def _should_draw_edge(self, s: Node, p: Node, o: Node) -> bool:
        """Prüft, ob ein Triple als echte Kante im Graphen gerendert werden soll."""
        if p == self.config.group_contains or p == RDFS.comment or (p == RDF.type and not self.config.type_as_edge):
            return False
        if p in self.config.node_properties or p in self.config.icon_locators or p == RDF2GRAPHML_COLOR or p == RDF2GRAPHML_SHAPE:
            return False

        if s in self.nodes_to_draw and o in self.nodes_to_draw and not isinstance(o, Literal):
            is_list_generated = str(p).startswith(LIST_NS_BASE)
            if is_list_generated or self.config.is_predicate_allowed(p):
                return True
        return False

    def convert(self, rdf_graph: Dataset) -> None:
        """
        Hauptmethode: Analysiert das RDF-Modell und baut das agnostische GraphModel auf.
        """
        for prefix, uri in self.config.namespaces.items():
            rdf_graph.bind(prefix, Namespace(uri), override=True)

        # 1. Daten aggregieren und Stile auflösen
        self._preprocess_lists(rdf_graph)
        self._pass_1_collect_data(rdf_graph)
        image_resources = self._fetch_images()

        # 2. Agnostisches Datenmodell initialisieren
        self.graph_model = GraphModel()
        self.graph_model.image_resources = image_resources

        # 3. IR-Knoten (NodeModels) generieren
        for node in self.nodes_to_draw:
            g_node = self._get_internal_node(node)
            n_id = str(node)

            # URL-Logik für Links
            url = n_id
            if RDF2GRAPHML_LINK in g_node.types and isinstance(node, BNode) and g_node.value:
                url = g_node.value

            tooltip = g_node.comment if g_node.comment else g_node.value
            parent_id = str(self.hierarchy.parent_of[node]) if node in self.hierarchy.parent_of else None
            is_group = node in self.hierarchy.groups

            node_model = NodeModel(
                id=n_id,
                label=self._get_display_label(node, rdf_graph),
                types=[str(t) for t in g_node.types],
                attributes=g_node.attributes,
                style=g_node.effective_style,
                url=url,
                tooltip=tooltip,
                parent_id=parent_id,
                is_group=is_group
            )
            self.graph_model.add_node(node_model)

        # 4. IR-Kanten (EdgeModels) generieren
        edge_idx = 0
        for s, p, o, _ in rdf_graph:
            if self._should_draw_edge(s, p, o):
                p_uri = URIRef(p)
                edge_style = self.config.edge_styles.get(p_uri, {})

                custom_label = edge_style.get("label")
                edge_label = custom_label if custom_label else self._determine_edge_label(str(p), rdf_graph)

                edge_model = EdgeModel(
                    id=f"e_{edge_idx}",
                    source_id=str(s),
                    target_id=str(o),
                    label=edge_label,
                    style=edge_style,
                    url=str(p)
                )
                self.graph_model.add_edge(edge_model)
                edge_idx += 1

    def save(self, path: str) -> None:
        """
        Abwärtskompatible Methode für die cli.py.
        Nutzt den neuen GraphMLWriter zur Ausgabe.
        """
        if not self.graph_model:
            raise ValueError("Hier wurde noch kein Graph konvertiert. Rufe zuerst convert() auf.")

        writer = GraphMLWriter(self.config)
        writer.write(self.graph_model, path)