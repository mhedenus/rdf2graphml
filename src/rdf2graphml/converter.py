import logging
import xml.etree.ElementTree as ET
from typing import Set, Dict, List, Tuple, Any, Optional

from rdflib import Graph, Literal, BNode, URIRef
from rdflib.term import Node
from rdflib.namespace import RDFS, RDF

from .icon_loader import load_icon_as_base64
from .hierarchy import GraphHierarchy

logger = logging.getLogger(__name__)

# --- Constants for RDF List processing ---
LIST_NS_BASE: str = "https://www.hedenus.de/rdf2graphml/"
LIST_NS_INDEX: str = f"{LIST_NS_BASE}index#"
LIST_TYPE_URI: URIRef = URIRef(f"{LIST_NS_BASE}List")


class RDFToYedConverter:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.root: ET.Element = ET.Element("graphml", {"xmlns": "http://graphml.graphdrawing.org/xmlns"})
        self.graph_element: ET.Element = ET.SubElement(self.root, "graph", id="G", edgedefault="directed")

        self.nodes_to_draw: Set[Node] = set()
        self.node_attributes: Dict[Node, Dict[str, List[str]]] = {}
        self.all_attribute_keys: Set[str] = set()
        self.edge_counter: int = 0

        self.node_display_labels_raw: Dict[Node, List[Tuple[str, Optional[str]]]] = {}
        self.node_comments: Dict[Node, str] = {}
        self.node_icons: Dict[Node, Dict[str, Any]] = {}
        self.image_resources: Dict[str, Dict[str, Any]] = {}
        self.node_types: Dict[Node, List[Node]] = {}

        self.hierarchy: GraphHierarchy = GraphHierarchy()

    def _generate_unique_attr_names(self, uris: Set[str]) -> Dict[str, str]:
        used_names: Dict[str, int] = {}
        mapping: Dict[str, str] = {}
        for uri in sorted(uris):
            base_name = str(uri).split("/")[-1].split("#")[-1] or "attr"
            if base_name not in used_names:
                used_names[base_name] = 1
                mapping[uri] = base_name
            else:
                mapping[uri] = f"{base_name} ({used_names[base_name]})"
                used_names[base_name] += 1
        return mapping

    def _preprocess_lists(self, rdf_graph: Graph) -> None:
        """
        Finds RDF lists, aggregates them into a single list node, and creates
        numbered edges to the list items.

        WARNING: This method modifies the provided rdflib.Graph in-place by
        removing the original rdf:first/rdf:rest triples and adding new ones.
        """
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

                current = rest_val

            triples_to_add.append((head, RDF.type, LIST_TYPE_URI))
            triples_to_add.append((head, RDFS.label, Literal("List")))

        for t in triples_to_remove:
            rdf_graph.remove(t)
        for t in triples_to_add:
            rdf_graph.add(t)

    def _pass_1_collect_data(self, rdf_graph: Graph) -> None:
        self.nodes_forced_as_attributes: Set[Node] = set()
        allowed_triples: List[Tuple[Node, Node, Node]] = []

        for s, p, o in rdf_graph:
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
                             p == self.config.group_contains)

            if not is_structural and not self.config.is_predicate_allowed(p):
                continue

            if p == RDF.type and not self.config.is_type_allowed(o):
                continue

            allowed_triples.append((s, p, o))

        for s, p, o in allowed_triples:
            if p in self.config.node_properties or p in self.config.icon_locators or (
                    p == RDF.type and not self.config.type_as_edge):
                self.nodes_forced_as_attributes.add(o)

            if p == RDFS.label and isinstance(o, Literal):
                if s not in self.node_display_labels_raw:
                    self.node_display_labels_raw[s] = []
                lang = o.language if hasattr(o, 'language') else None
                self.node_display_labels_raw[s].append((str(o), lang))
            elif p == RDFS.comment:
                self.node_comments[s] = str(o)
            elif p in self.config.icon_locators:
                new_icon = {"source": str(o), "is_local": isinstance(o, Literal)}
                if s not in self.node_icons or new_icon["source"] < self.node_icons[s]["source"]:
                    self.node_icons[s] = new_icon
            elif p == RDF.type:
                if s not in self.node_types: self.node_types[s] = []
                self.node_types[s].append(o)

        for s, p, o in allowed_triples:
            if s not in self.nodes_forced_as_attributes:
                self.nodes_to_draw.add(s)

            if p == RDFS.comment or p in self.config.icon_locators or p == self.config.group_contains:
                continue

            if isinstance(o, Literal) or p in self.config.node_properties or (
                    p == RDF.type and not self.config.type_as_edge):
                if s not in self.node_attributes:
                    self.node_attributes[s] = {}
                p_str = str(p)
                self.all_attribute_keys.add(p_str)
                if p_str not in self.node_attributes[s]:
                    self.node_attributes[s][p_str] = []

                val_str = f"{o} (@{o.language})" if getattr(o, "language", None) else str(o)
                self.node_attributes[s][p_str].append(val_str)
            elif o not in self.nodes_forced_as_attributes:
                self.nodes_to_draw.add(o)

    def _get_display_label(self, node: Node, rdf_graph: Graph) -> str:
        labels = self.node_display_labels_raw.get(node, [])
        if not labels:
            if isinstance(node, BNode):
                return ""
            else:
                # NEU: QNames (Präfixe) aus dem Namespace-Manager als Fallback nutzen
                try:
                    prefix, namespace, name = rdf_graph.namespace_manager.compute_qname(node)
                    if prefix:
                        return f"{prefix}:{name}"
                    return name
                except Exception:
                    # Fallback zum kompletten URI, falls kein Namespace passt
                    return f"<{str(node)}>"

        pref_lang = self.config.preferred_language
        pref_labels = [text for text, lang in labels if lang == pref_lang]
        if pref_labels:
            return sorted(pref_labels)[0]

        no_lang_labels = [text for text, lang in labels if not lang]
        if no_lang_labels:
            return sorted(no_lang_labels)[0]

        return sorted([text for text, lang in labels])[0]

    def _fetch_images(self) -> None:
        resource_id = 1
        seen_sources: Dict[str, Dict[str, Any]] = {}
        for icon_data in self.node_icons.values():
            src = icon_data["source"]
            if src not in seen_sources:
                logger.debug(f"Processing image: {src}")
                result = load_icon_as_base64(
                    src,
                    icon_data["is_local"],
                    self.config.icon_height,
                    self.config.image_base_dir
                )
                if result and isinstance(result, tuple) and len(result) == 2:
                    b64, width = result
                    if b64 and width:
                        seen_sources[src] = {"id": resource_id, "base64": b64, "width": width}
                        resource_id += 1
                else:
                    logger.warning(f"Image could not be loaded and will be skipped: {src}")
        self.image_resources = seen_sources

    def _setup_graphml_keys(self) -> Dict[str, str]:
        ET.SubElement(self.root, "key", id="d_ng", **{"for": "node", "yfiles.type": "nodegraphics"})
        ET.SubElement(self.root, "key", id="d_eg", **{"for": "edge", "yfiles.type": "edgegraphics"})
        ET.SubElement(self.root, "key", id="d_url", **{"attr.name": "url", "attr.type": "string", "for": "node"})
        ET.SubElement(self.root, "key", id="d_desc",
                      **{"attr.name": "description", "attr.type": "string", "for": "node"})
        ET.SubElement(self.root, "key", id="d_res", **{"for": "graphml", "yfiles.type": "resources"})

        name_map = self._generate_unique_attr_names(self.all_attribute_keys)
        mapping: Dict[str, str] = {}
        for i, uri in enumerate(sorted(self.all_attribute_keys)):
            k_id = f"d_a{i}"
            name = name_map[uri]
            if name.lower() in ["url", "description"]: name += "_rdf"
            ET.SubElement(self.root, "key", id=k_id, **{"attr.name": name, "attr.type": "string", "for": "node"})
            mapping[uri] = k_id
        return mapping

    def _apply_group_styling(self, data_g: ET.Element, disp_label: str) -> None:
        proxy = ET.SubElement(data_g, "{http://www.yworks.com/xml/graphml}ProxyAutoBoundsNode")
        realizers = ET.SubElement(proxy, "{http://www.yworks.com/xml/graphml}Realizers", active="0")
        group_node = ET.SubElement(realizers, "{http://www.yworks.com/xml/graphml}GroupNode")

        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}NodeLabel",
                      alignment="right", autoSizePolicy="node_width", backgroundColor="#EBEBEB",
                      borderDistance="0.0", fontFamily="Dialog", fontSize="15", fontStyle="plain",
                      hasLineColor="false", modelName="internal", modelPosition="t",
                      textColor="#000000", visible="true").text = disp_label

        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}Fill", color="#F5F5F5", transparent="false")
        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}BorderStyle", color="#000000", type="dashed",
                      width="1.0")
        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}Shape", type="roundrectangle")
        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}State", closed="false", closedHeight="50.0",
                      closedWidth="50.0", innerGraphDisplayEnabled="false")
        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}Insets", bottom="15", bottomF="15.0", left="15",
                      leftF="15.0", right="15", rightF="15.0", top="15", topF="15.0")
        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}BorderInsets", bottom="0", bottomF="0.0",
                      left="0", leftF="0.0", right="0", rightF="0.0", top="0", topF="0.0")

    def _apply_standard_styling(self, data_g: ET.Element, node: Node, disp_label: str) -> None:
        icon_src = self.node_icons.get(node, {}).get("source")
        if icon_src in self.image_resources:
            img_data = self.image_resources[icon_src]
            img_node = ET.SubElement(data_g, "{http://www.yworks.com/xml/graphml}ImageNode")
            ET.SubElement(img_node, "{http://www.yworks.com/xml/graphml}Geometry",
                          height=str(self.config.icon_height), width=str(img_data["width"]))
            ET.SubElement(img_node, "{http://www.yworks.com/xml/graphml}NodeLabel",
                          modelName="sandwich", modelPosition="s").text = disp_label
            ET.SubElement(img_node, "{http://www.yworks.com/xml/graphml}Image", refid=str(img_data["id"]))
        else:
            shape_n = ET.SubElement(data_g, "{http://www.yworks.com/xml/graphml}ShapeNode")

            if isinstance(node, BNode):
                default_style = self.config.default_node_style.get("blank_nodes", {})
            else:
                default_style = self.config.default_node_style.get("uri_nodes", {})

            color = default_style.get("color", "#E8EEF7")
            shape = default_style.get("shape", "roundrectangle")

            available_types = sorted(self.node_types.get(node, []), key=str)
            best_style = None
            best_priority = -1

            for t in available_types:
                if t in self.config.type_styles:
                    style = self.config.type_styles[t]
                    priority = style.get("priority", 0)
                    if best_style is None or priority > best_priority:
                        best_style = style
                        best_priority = priority

            if best_style:
                color = best_style.get("color", color)
                shape = best_style.get("shape", shape)

            ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}NodeLabel").text = disp_label
            width = str(max(50, len(disp_label) * 8 + 20)) if disp_label else "30"
            ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}Geometry", width=width, height="30")
            ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}Fill", color=color, transparent="false")
            ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}Shape", type=shape)

    def _build_node_recursive(self, node: Node, parent_xml_element: ET.Element, attr_map: Dict[str, str],
                              rdf_graph: Graph) -> None:
        n_id = str(node)
        node_elem = ET.SubElement(parent_xml_element, "node", id=n_id)
        ET.SubElement(node_elem, "data", key="d_url").text = n_id

        if node in self.node_comments:
            comment_text = self.node_comments[node]
            html_tooltip = f"<html><body style='width: 250px;'>{comment_text}</body></html>"
            ET.SubElement(node_elem, "data", key="d_desc").text = html_tooltip

        if node in self.node_attributes:
            for p_uri in sorted(self.node_attributes[node].keys()):
                vals = self.node_attributes[node][p_uri]
                ET.SubElement(node_elem, "data", key=attr_map[p_uri]).text = ", ".join(sorted(vals))

        data_g = ET.SubElement(node_elem, "data", key="d_ng")

        # NEU: rdf_graph wird an _get_display_label übergeben
        raw_label = self._get_display_label(node, rdf_graph)
        max_len = 60
        disp_label = (raw_label[:(max_len - 3)] + "...") if len(raw_label) > max_len else raw_label

        if node in self.hierarchy.groups:
            self._apply_group_styling(data_g, disp_label)
            inner_graph = ET.SubElement(node_elem, "graph", id=f"{n_id}:", edgedefault="directed")

            children = self.hierarchy.children_of.get(node, set())
            for child in sorted(children):
                self._build_node_recursive(child, inner_graph, attr_map, rdf_graph)
        else:
            self._apply_standard_styling(data_g, node, disp_label)

    def _pass_2_build_graph(self, rdf_graph: Graph, attr_map: Dict[str, str]) -> None:
        root_nodes = self.hierarchy.get_roots(self.nodes_to_draw)
        for root_node in sorted(root_nodes):
            self._build_node_recursive(root_node, self.graph_element, attr_map, rdf_graph)

        # NEU: Dictionary nutzen, um bidirektionale Kanten zu erkennen (Wert = is_bidirectional)
        edges_to_draw: Dict[Tuple[str, str, str], bool] = {}

        for s, p, o in rdf_graph:
            if p == self.config.group_contains:
                continue

            is_valid_edge_pred = True
            if p == RDFS.comment: is_valid_edge_pred = False
            if p == RDF.type and not self.config.type_as_edge: is_valid_edge_pred = False
            if p in self.config.node_properties: is_valid_edge_pred = False
            if p in self.config.icon_locators: is_valid_edge_pred = False

            if s in self.nodes_to_draw and o in self.nodes_to_draw and not isinstance(o,
                                                                                      Literal) and is_valid_edge_pred:
                is_list_generated = str(p).startswith(LIST_NS_BASE)
                if is_list_generated or self.config.is_predicate_allowed(p):

                    s_str, p_str, o_str = str(s), str(p), str(o)
                    forward_edge = (s_str, p_str, o_str)
                    backward_edge = (o_str, p_str, s_str)

                    if backward_edge in edges_to_draw:
                        # Gegenrichtung existiert bereits -> markiere bestehende als bidirektional
                        edges_to_draw[backward_edge] = True
                    else:
                        # Neue Kante, standardmäßig nicht bidirektional
                        edges_to_draw[forward_edge] = False

        # Iteriere über das generierte Dictionary
        for (s_str, p_str, o_str), is_bidi in sorted(edges_to_draw.items()):
            edge = ET.SubElement(self.graph_element, "edge", id=f"e{self.edge_counter}", source=s_str, target=o_str)
            self.edge_counter += 1
            poly = ET.SubElement(ET.SubElement(edge, "data", key="d_eg"),
                                 "{http://www.yworks.com/xml/graphml}PolyLineEdge")

            p_uri = URIRef(p_str)
            edge_style = self.config.edge_styles.get(p_uri, {})
            color = edge_style.get("color", "#000000")
            line_type = edge_style.get("line_type", "line")
            target_arrow = edge_style.get("target_arrow", "standard")

            # NEU: Bidirektionale Pfeile setzen, falls nötig
            source_arrow = target_arrow if is_bidi and target_arrow != "none" else "none"

            ET.SubElement(poly, "{http://www.yworks.com/xml/graphml}LineStyle",
                          color=color, type=line_type, width="1.0")
            ET.SubElement(poly, "{http://www.yworks.com/xml/graphml}Arrows",
                          source=source_arrow, target=target_arrow)

            if p_str.startswith(LIST_NS_INDEX):
                edge_label = "#" + p_str.split("#")[-1]
            else:
                edge_label = p_str.split("/")[-1].split("#")[-1] or "link"

            ET.SubElement(poly, "{http://www.yworks.com/xml/graphml}EdgeLabel").text = edge_label

    def convert(self, rdf_graph: Graph) -> None:
        """
        Converts the provided RDF graph to GraphML.

        WARNING: This method modifies the provided rdflib.Graph in-place
        (e.g., when resolving RDF lists during preprocessing). If you need
        to preserve the original state of the graph, pass a copy instead.
        """
        self._preprocess_lists(rdf_graph)
        self._pass_1_collect_data(rdf_graph)
        self._fetch_images()
        attr_map = self._setup_graphml_keys()
        self._pass_2_build_graph(rdf_graph, attr_map)

        if self.image_resources:
            res_data = ET.SubElement(self.root, "data", key="d_res")
            y_res = ET.SubElement(res_data, "{http://www.yworks.com/xml/graphml}Resources")
            for res in self.image_resources.values():
                r = ET.SubElement(y_res, "{http://www.yworks.com/xml/graphml}Resource", id=str(res["id"]),
                                  type="java.awt.image.BufferedImage")
                r.text = res["base64"]

    def save(self, path: str) -> None:
        tree = ET.ElementTree(self.root)
        ET.register_namespace('y', 'http://www.yworks.com/xml/graphml')
        if hasattr(ET, "indent"):
            ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)