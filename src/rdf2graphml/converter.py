import logging
import textwrap
import xml.etree.ElementTree as ET
from typing import Set, Dict, List, Tuple, Any, Optional

from rdflib import Literal, BNode, URIRef, Dataset
from rdflib.namespace import RDFS, RDF, Namespace
from rdflib.term import Node

from .hierarchy import GraphHierarchy
from .icon_loader import load_icon_as_base64
from .model import RDF2GRAPHML_NS_BASE, RDF2GRAPHML_COLOR, RDF2GRAPHML_SHAPE, RDF2GRAPHML_LINK

logger = logging.getLogger(__name__)

# --- Constants for RDF List processing ---
LIST_NS_BASE: str = RDF2GRAPHML_NS_BASE
LIST_NS_INDEX: str = f"{LIST_NS_BASE}index#"
LIST_TYPE_URI: URIRef = URIRef(f"{LIST_NS_BASE}List")

RDF_CONTAINER_MEMBER = "http://www.w3.org/1999/02/22-rdf-syntax-ns#_"


class RDFToYedConverter:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.root: ET.Element = ET.Element("graphml", {"xmlns": "http://graphml.graphdrawing.org/xmlns"})
        self.graph_element: ET.Element = ET.SubElement(self.root, "graph", id="G", edgedefault="directed")

        self.nodes_to_draw: Set[Node] = set()
        self.node_types: Dict[Node, List[Node]] = {}
        self.node_attributes: Dict[Node, Dict[str, List[str]]] = {}
        self.node_display_labels_raw: Dict[Node, List[Tuple[str, Optional[str]]]] = {}
        self.node_values: Dict[Node, str] = {}
        self.node_comments: Dict[Node, str] = {}
        self.node_effective_style: Dict[Node, Dict[str, Any]] = {}
        self.image_resources: Dict[str, Dict[str, Any]] = {}
        self.all_attribute_keys: Set[str] = set()
        self.edge_counter: int = 0
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

    def _preprocess_lists(self, rdf_graph: Dataset) -> None:
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

                # if the list is in a Group, then the following bnodes of the list must be removed
                # from the group, otherwise they will appear as separate nodes
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
        allowed_triples = self._collect_structural_data(rdf_graph)
        self._extract_node_properties(allowed_triples)
        self._resolve_effective_styles()

    def _collect_structural_data(self, rdf_graph: Dataset) -> List[Tuple[Node, Node, Node]]:
        self.nodes_forced_as_attributes: Set[Node] = set()
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
        for s, p, o in allowed_triples:
            if p in self.config.node_properties or p in self.config.icon_locators or (
                    p == RDF.type and not self.config.type_as_edge) or p == RDF2GRAPHML_COLOR or p == RDF2GRAPHML_SHAPE:
                self.nodes_forced_as_attributes.add(o)

            if p == RDFS.label and isinstance(o, Literal):
                if s not in self.node_display_labels_raw:
                    self.node_display_labels_raw[s] = []
                lang = o.language if hasattr(o, 'language') else None
                self.node_display_labels_raw[s].append((str(o), lang))
            elif p == RDF.value:
                self.node_values[s] = str(o)
            elif p == RDFS.comment:
                self.node_comments[s] = str(o)
            elif p in self.config.icon_locators:
                if s not in self.node_effective_style:
                    self.node_effective_style[s] = {}
                self.node_effective_style[s]["icon"] = str(o)
            elif p == RDF2GRAPHML_COLOR:
                if s not in self.node_effective_style:
                    self.node_effective_style[s] = {}
                self.node_effective_style[s]["color"] = str(o)
            elif p == RDF2GRAPHML_SHAPE:
                if s not in self.node_effective_style:
                    self.node_effective_style[s] = {}
                self.node_effective_style[s]["shape"] = str(o)
            elif p == RDF.type:
                if s not in self.node_types: self.node_types[s] = []
                self.node_types[s].append(o)

        for s, p, o in allowed_triples:
            if s not in self.nodes_forced_as_attributes:
                self.nodes_to_draw.add(s)

            if p == RDFS.comment or p in self.config.icon_locators or p == self.config.group_contains or p == RDF2GRAPHML_COLOR or p == RDF2GRAPHML_SHAPE:
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

    def _get_best_node_style(self, node: Node) -> Optional[Dict[str, Any]]:
        types = sorted(self.node_types.get(node, []), key=str)
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
        """
        Resolves the final effective style for each node drawn in the graph.
        Priority:
        1. Custom properties defined directly on the node (icon_locator, shape, color)
        2. Style from the RDF type (type_styles)
        3. Default style
        """
        for node in self.nodes_to_draw:
            if node not in self.node_effective_style:
                self.node_effective_style[node] = {}

            node_style = self.node_effective_style[node]
            best_type_style = self._get_best_node_style(node) or {}

            if isinstance(node, BNode):
                default_style = self.config.default_node_style.get("blank_nodes", {})
            else:
                default_style = self.config.default_node_style.get("uri_nodes", {})

            if "icon" not in node_style:
                if "icon" in best_type_style:
                    node_style["icon"] = best_type_style["icon"]

            if "color" not in node_style:
                if "color" in best_type_style:
                    node_style["color"] = best_type_style["color"]
                else:
                    node_style["color"] = default_style.get("color", "#E8EEF7")

            if "shape" not in node_style:
                if "shape" in best_type_style:
                    node_style["shape"] = best_type_style["shape"]
                else:
                    node_style["shape"] = default_style.get("shape", "roundrectangle")

    def _get_display_label(self, node: Node, rdf_graph: Dataset) -> str:
        labels = self.node_display_labels_raw.get(node, [])
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
            value = self.node_values.get(node)
            if value:
                return value
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

    def _fetch_images(self) -> None:
        resource_id = 1
        seen_sources: Dict[str, Dict[str, Any]] = {}
        for style in self.node_effective_style.values():
            if "icon" in style:
                src = style["icon"]
                is_local = not src.startswith(("http://", "https://"))
                if src not in seen_sources:
                    logger.debug(f"Processing image: {src}")
                    result = load_icon_as_base64(
                        src,
                        is_local,
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
        ET.SubElement(self.root, "key", id="d_e_url", **{"attr.name": "url", "attr.type": "string", "for": "edge"})

        name_map = self._generate_unique_attr_names(self.all_attribute_keys)
        mapping: Dict[str, str] = {}
        for i, uri in enumerate(sorted(self.all_attribute_keys)):
            k_id = f"d_a{i}"
            name = name_map[uri]
            if name.lower() in ["url", "description"]: name += "_rdf"
            ET.SubElement(self.root, "key", id=k_id, **{"attr.name": name, "attr.type": "string", "for": "node"})
            mapping[uri] = k_id
        return mapping

    def _apply_group_styling(self, node: Node, data_g: ET.Element, disp_label: str) -> None:
        proxy = ET.SubElement(data_g, "{http://www.yworks.com/xml/graphml}ProxyAutoBoundsNode")
        realizers = ET.SubElement(proxy, "{http://www.yworks.com/xml/graphml}Realizers", active="0")
        group_node = ET.SubElement(realizers, "{http://www.yworks.com/xml/graphml}GroupNode")

        style = self.node_effective_style.get(node, {})
        color = style.get("color", "#EEEEEE")

        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}NodeLabel",
                      alignment="right", autoSizePolicy="node_size", backgroundColor=f"{color}",
                      borderDistance="0.0", fontFamily="Dialog", fontSize="15", fontStyle="plain",
                      hasLineColor="false", modelName="internal", modelPosition="t",
                      textColor="#000000", visible="true").text = disp_label

        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}Fill", color="#F5F5F5", transparent="false")
        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}BorderStyle", color="#000000", type="dashed",
                      width="1.0")
        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}Shape", type="roundrectangle")
        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}State", closed="false", closedHeight="50.0",
                      closedWidth="50.0", innerGraphDisplayEnabled="false")
        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}Insets", bottom="15", bottomF="30.0", left="30",
                      leftF="30.0", right="30", rightF="30.0", top="30", topF="30.0")
        ET.SubElement(group_node, "{http://www.yworks.com/xml/graphml}BorderInsets", bottom="0", bottomF="0.0",
                      left="0", leftF="0.0", right="0", rightF="0.0", top="0", topF="0.0")

    def _format_and_measure_label(self, label: str, max_width_chars: int = 40) -> Tuple[str, str, str]:
        if not label:
            return "", "30", "30"

        normalized_label = " ".join(label.split())

        lines = textwrap.wrap(normalized_label, width=max_width_chars)
        formatted_label = "\n".join(lines)

        num_lines = len(lines)
        max_line_length = max((len(line) for line in lines), default=0)

        char_width = 8
        line_height = 16
        padding_x = 24
        padding_y = 16

        width = max(50, (max_line_length * char_width) + padding_x)
        height = max(30, (num_lines * line_height) + padding_y)

        return formatted_label, str(width), str(height)

    def _build_node_recursive(self, node: Node, parent_xml_element: ET.Element, attr_map: Dict[str, str],
                              rdf_graph: Dataset) -> None:
        n_id = str(node)
        url = n_id
        is_link = False

        # special handling for Link-Nodes: use rdf:value as URL
        types = self.node_types.get(node, [])
        if types and RDF2GRAPHML_LINK in types:
            is_link = True
            if isinstance(node, BNode):
                href = self.node_values.get(node, None)
                if href:
                    url = href

        node_elem = ET.SubElement(parent_xml_element, "node", id=n_id)
        ET.SubElement(node_elem, "data", key="d_url").text = url

        self._add_node_tooltip(node, node_elem)
        self._add_node_attributes(node, node_elem, attr_map)

        data_g = ET.SubElement(node_elem, "data", key="d_ng")
        raw_label = self._get_display_label(node, rdf_graph)
        disp_label = raw_label

        if node in self.hierarchy.groups:
            self._apply_group_styling(node, data_g, disp_label)
            inner_graph = ET.SubElement(node_elem, "graph", id=f"{n_id}:", edgedefault="directed")

            children = self.hierarchy.children_of.get(node, set())
            for child in sorted(children):
                self._build_node_recursive(child, inner_graph, attr_map, rdf_graph)
        else:
            self._apply_node_styling(data_g, node, disp_label, is_link)

    def _add_node_tooltip(self, node: Node, node_elem: ET.Element) -> None:
        if node in self.node_comments:
            comment_text = self.node_comments[node]
            html_tooltip = f"<html><body>{comment_text}</body></html>"
            ET.SubElement(node_elem, "data", key="d_desc").text = html_tooltip

    def _add_node_attributes(self, node: Node, node_elem: ET.Element, attr_map: Dict[str, str]) -> None:
        if node in self.node_attributes:
            for p_uri in sorted(self.node_attributes[node].keys()):
                vals = self.node_attributes[node][p_uri]
                ET.SubElement(node_elem, "data", key=attr_map[p_uri]).text = ", ".join(sorted(vals))

    def _apply_node_styling(self, data_g: ET.Element, node: Node, disp_label: str, is_link: bool) -> None:
        """
        Delegates styling to specific builders based on node type.
        Can be extended in the future to register custom builders for specific RDF types.
        """
        if self._apply_custom_type_styling(data_g, node, disp_label, is_link):
            return

        self._apply_standard_styling(data_g, node, disp_label, is_link)

    def _apply_custom_type_styling(self, data_g: ET.Element, node: Node, disp_label: str, is_link: bool) -> bool:
        # types = self.node_types.get(node, [])
        # if RDF2GRAPHML_LINK in types:
        # return True
        return False

    def _apply_standard_styling(self, data_g: ET.Element, node: Node, disp_label: str, is_link: bool) -> None:
        style = self.node_effective_style.get(node, {})
        icon_src = style.get("icon")

        if icon_src and icon_src in self.image_resources:
            self._build_image_node(data_g, disp_label, icon_src, is_link)
        else:
            self._build_shape_node(data_g, node, disp_label, style, is_link)

    def _build_image_node(self, data_g: ET.Element, disp_label: str, icon_src: str, is_link: bool) -> None:
        img_data = self.image_resources[icon_src]
        img_node = ET.SubElement(data_g, "{http://www.yworks.com/xml/graphml}ImageNode")
        ET.SubElement(img_node, "{http://www.yworks.com/xml/graphml}Geometry",
                      height=str(self.config.icon_height), width=str(img_data["width"]))
        ET.SubElement(img_node, "{http://www.yworks.com/xml/graphml}NodeLabel",
                      modelName="sandwich", modelPosition="s").text = disp_label
        ET.SubElement(img_node, "{http://www.yworks.com/xml/graphml}Image", refid=str(img_data["id"]))

    def _build_shape_node(self, data_g: ET.Element, node: Node, disp_label: str, style: Dict[str, Any],
                          is_link: bool) -> None:
        shape_n = ET.SubElement(data_g, "{http://www.yworks.com/xml/graphml}ShapeNode")

        color = style.get("color", "#E8EEF7")
        shape = style.get("shape", "roundrectangle")

        formatted_label, width, height = self._format_and_measure_label(disp_label)

        node_label = ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}NodeLabel")
        node_label.text = formatted_label
        node_label.set("alignment", "center")
        if is_link:
            node_label.set("underlinedText", "true")

        ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}Geometry", width=width, height=height)
        ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}Fill", color=color, transparent="false")
        ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}Shape", type=shape)

    def _pass_2_build_graph(self, rdf_graph: Dataset, attr_map: Dict[str, str]) -> None:
        self._build_nodes(rdf_graph, attr_map)
        self._build_edges(rdf_graph)

    def _build_nodes(self, rdf_graph: Dataset, attr_map: Dict[str, str]) -> None:
        root_nodes = self.hierarchy.get_roots(self.nodes_to_draw)
        for root_node in sorted(root_nodes):
            self._build_node_recursive(root_node, self.graph_element, attr_map, rdf_graph)

    def _build_edges(self, rdf_graph: Dataset) -> None:
        edges_to_draw: Dict[Tuple[str, str, str], bool] = {}
        for s, p, o, _ in rdf_graph:
            if self._should_draw_edge(s, p, o):
                self._register_edge(s, p, o, edges_to_draw)

        for (s_str, p_str, o_str), is_bidi in sorted(edges_to_draw.items()):
            self._create_edge_xml(s_str, p_str, o_str, is_bidi, rdf_graph)

    def _should_draw_edge(self, s: Node, p: Node, o: Node) -> bool:
        if p == self.config.group_contains:
            return False
        if p == RDFS.comment:
            return False
        if p == RDF.type and not self.config.type_as_edge:
            return False
        if p in self.config.node_properties:
            return False
        if p in self.config.icon_locators:
            return False
        if p == RDF2GRAPHML_COLOR or p == RDF2GRAPHML_SHAPE:
            return False

        if s in self.nodes_to_draw and o in self.nodes_to_draw and not isinstance(o, Literal):
            is_list_generated = str(p).startswith(LIST_NS_BASE)
            if is_list_generated or self.config.is_predicate_allowed(p):
                return True
        return False

    def _register_edge(self, s: Node, p: Node, o: Node, edges_to_draw: Dict[Tuple[str, str, str], bool]) -> None:
        s_str, p_str, o_str = str(s), str(p), str(o)
        forward_edge = (s_str, p_str, o_str)
        backward_edge = (o_str, p_str, s_str)

        if backward_edge in edges_to_draw:
            edges_to_draw[backward_edge] = True
        else:
            edges_to_draw[forward_edge] = False

    def _create_edge_xml(self, s_str: str, p_str: str, o_str: str, is_bidi: bool, rdf_graph: Dataset) -> None:
        edge = ET.SubElement(self.graph_element, "edge", id=f"e{self.edge_counter}", source=s_str, target=o_str)
        self.edge_counter += 1
        ET.SubElement(edge, "data", key="d_e_url").text = p_str
        poly = ET.SubElement(ET.SubElement(edge, "data", key="d_eg"),
                             "{http://www.yworks.com/xml/graphml}PolyLineEdge")

        p_uri = URIRef(p_str)
        edge_style = self.config.edge_styles.get(p_uri, {})
        color = edge_style.get("color", "#000000")
        line_type = edge_style.get("line_type", "line")
        target_arrow = edge_style.get("target_arrow", "standard")
        line_width = str(edge_style.get("line_width", "1.0"))

        source_arrow = target_arrow if is_bidi and target_arrow != "none" else "none"

        ET.SubElement(poly, "{http://www.yworks.com/xml/graphml}LineStyle",
                      color=color, type=line_type, width=line_width)
        ET.SubElement(poly, "{http://www.yworks.com/xml/graphml}Arrows",
                      source=source_arrow, target=target_arrow)

        custom_label = edge_style.get("label")
        if custom_label:
            edge_label = custom_label
        else:
            edge_label = self._determine_edge_label(p_str, rdf_graph)

        ET.SubElement(poly, "{http://www.yworks.com/xml/graphml}EdgeLabel").text = edge_label

    def _determine_edge_label(self, p_str: str, rdf_graph: Dataset) -> str:
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

    def convert(self, rdf_graph: Dataset) -> None:
        """
        Converts the provided RDF graph to GraphML.

        WARNING: This method modifies the provided rdflib.Dataset in-place
        (e.rdf_graph., when resolving RDF lists during preprocessing). If you need
        to preserve the original state of the graph, pass a copy instead.
        """

        for prefix, uri in self.config.namespaces.items():
            rdf_graph.bind(prefix, Namespace(uri), override=True)

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
