import logging
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union, Dict, Set, Tuple, Any

from .writer import GraphWriter
from .ir_model import GraphModel, NodeModel, EdgeModel

logger = logging.getLogger(__name__)

# yEd XML-Namespace Konstante
YED_NS = "{http://www.yworks.com/xml/graphml}"


class GraphMLWriter(GraphWriter):
    """
    Kapselt die Serialisierung des agnostischen GraphModels in das
    yEd-konforme GraphML-Format (XML).
    """

    def __init__(self, config):
        super().__init__(config)
        self.root: Union[ET.Element, None] = None
        self.graph_element: Union[ET.Element, None] = None

    def write(self, graph: GraphModel, filepath: Union[str, Path]) -> None:
        """
        Setzt das abstrakte Interface um und erzeugt die GraphML-Datei.
        """
        # 1. XML-Grundgerüst aufbauen
        self.root = ET.Element("graphml", {"xmlns": "http://graphml.graphdrawing.org/xmlns"})
        self.graph_element = ET.SubElement(self.root, "graph", id="G", edgedefault="directed")

        # 2. GraphML Keys (Konfigurationstabellen) für yEd initialisieren
        attr_map = self._setup_graphml_keys(graph)

        # 3. Knoten rekursiv (wegen Verschachtelung/Gruppen) in XML überführen
        root_nodes = graph.get_roots()
        for root_node in sorted(root_nodes, key=lambda n: n.id):
            self._build_node_recursive(root_node, self.graph_element, attr_map, graph)

        # 4. Kanten (Edges) verarbeiten und eintragen
        self._build_edges(graph)

        # 5. Eingebettete Base64-Bildressourcen (Icons) hinzufügen, falls vorhanden
        if graph.image_resources:
            res_data = ET.SubElement(self.root, "data", key="d_res")
            y_res = ET.SubElement(res_data, f"{YED_NS}Resources")
            for res in sorted(graph.image_resources.values(), key=lambda r: r["id"]):
                r = ET.SubElement(y_res, f"{YED_NS}Resource", id=str(res["id"]),
                                  type="java.awt.image.BufferedImage")
                r.text = res["base64"]

        # 6. XML-Datei formatiert abspeichern
        tree = ET.ElementTree(self.root)
        ET.register_namespace('y', 'http://www.yworks.com/xml/graphml')
        if hasattr(ET, "indent"):
            ET.indent(tree, space="  ")

        tree.write(str(filepath), encoding="utf-8", xml_declaration=True)
        logger.debug(f"GraphML erfolgreich nach {filepath} geschrieben.")

    def _setup_graphml_keys(self, graph: GraphModel) -> Dict[str, str]:
        """Erzeugt die yEd-spezifischen Metadaten-Keys im XML-Header."""
        ET.SubElement(self.root, "key", id="d_ng", **{"for": "node", "yfiles.type": "nodegraphics"})
        ET.SubElement(self.root, "key", id="d_eg", **{"for": "edge", "yfiles.type": "edgegraphics"})
        ET.SubElement(self.root, "key", id="d_url", **{"attr.name": "url", "attr.type": "string", "for": "node"})
        ET.SubElement(self.root, "key", id="d_desc",
                      **{"attr.name": "description", "attr.type": "string", "for": "node"})
        ET.SubElement(self.root, "key", id="d_res", **{"for": "graphml", "yfiles.type": "resources"})
        ET.SubElement(self.root, "key", id="d_e_url", **{"attr.name": "url", "attr.type": "string", "for": "edge"})

        # Dynamisch alle vorkommenden Attribut-Keys aus den Knoten sammeln
        all_attribute_keys = set()
        for node in graph.nodes.values():
            all_attribute_keys.update(node.attributes.keys())

        name_map = self._generate_unique_attr_names(all_attribute_keys)
        mapping: Dict[str, str] = {}
        for i, uri in enumerate(sorted(all_attribute_keys)):
            k_id = f"d_a{i}"
            name = name_map[uri]
            if name.lower() in ["url", "description"]:
                name += "_rdf"
            ET.SubElement(self.root, "key", id=k_id, **{"attr.name": name, "attr.type": "string", "for": "node"})
            mapping[uri] = k_id
        return mapping

    def _generate_unique_attr_names(self, uris: Set[str]) -> Dict[str, str]:
        """Erzeugt lesbare, eindeutige Namen für XML-Attribute aus URIs."""
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

    def _build_node_recursive(self, node: NodeModel, parent_xml_element: ET.Element,
                              attr_map: Dict[str, str], graph: GraphModel) -> None:
        """Baut die XML-Knotenelemente inklusive Hierarchien rekursiv auf."""
        n_id = node.id
        url = node.url or n_id

        node_elem = ET.SubElement(parent_xml_element, "node", id=n_id)
        ET.SubElement(node_elem, "data", key="d_url").text = url

        # Tooltip / Beschreibung (falls vorhanden) als HTML-Struktur einbetten
        if node.tooltip:
            html_tooltip = f"<html><body>{node.tooltip}</body></html>"
            ET.SubElement(node_elem, "data", key="d_desc").text = html_tooltip

        # Benutzerdefinierte RDF-Attribute wegschreiben
        for p_uri in sorted(node.attributes.keys()):
            vals = node.attributes[p_uri]
            ET.SubElement(node_elem, "data", key=attr_map[p_uri]).text = ", ".join(sorted(vals))

        data_g = ET.SubElement(node_elem, "data", key="d_ng")
        disp_label = node.label

        # Style-Sonderfall: Prüfen, ob der Knoten ein "Link" ist (für Unterstreichung)
        is_link = "https://www.hedenus.de/rdf2graphml/Link" in node.types

        if node.is_group:
            self._apply_group_styling(node, data_g, disp_label)
            inner_graph = ET.SubElement(node_elem, "graph", id=f"{n_id}:", edgedefault="directed")

            # Kinder dieser Gruppe ermitteln und rekursiv einfügen
            children = graph.get_children(node.id)
            for child in sorted(children, key=lambda n: n.id):
                self._build_node_recursive(child, inner_graph, attr_map, graph)
        else:
            self._apply_node_styling(data_g, node, disp_label, is_link, graph)

    def _apply_group_styling(self, node: NodeModel, data_g: ET.Element, disp_label: str) -> None:
        """Erzeugt das yEd-spezifische XML-Layout für Gruppen-Container."""
        proxy = ET.SubElement(data_g, f"{YED_NS}ProxyAutoBoundsNode")
        realizers = ET.SubElement(proxy, f"{YED_NS}Realizers", active="0")
        group_node = ET.SubElement(realizers, f"{YED_NS}GroupNode")

        color = node.style.get("color", "#EEEEEE")

        ET.SubElement(group_node, f"{YED_NS}NodeLabel",
                      alignment="right", autoSizePolicy="node_size", backgroundColor=f"{color}",
                      borderDistance="0.0", fontFamily="Dialog", fontSize="15", fontStyle="plain",
                      hasLineColor="false", modelName="internal", modelPosition="t",
                      textColor="#000000", visible="true").text = disp_label

        ET.SubElement(group_node, f"{YED_NS}Fill", color="#F5F5F5", transparent="false")
        ET.SubElement(group_node, f"{YED_NS}BorderStyle", color="#000000", type="dashed", width="1.0")
        ET.SubElement(group_node, f"{YED_NS}Shape", type="roundrectangle")
        ET.SubElement(group_node, f"{YED_NS}State", closed="false", closedHeight="50.0",
                      closedWidth="50.0", innerGraphDisplayEnabled="false")
        ET.SubElement(group_node, f"{YED_NS}Insets", bottom="15", bottomF="30.0", left="30",
                      leftF="30.0", right="30", rightF="30.0", top="30", topF="30.0")
        ET.SubElement(group_node, f"{YED_NS}BorderInsets", bottom="0", bottomF="0.0",
                      left="0", leftF="0.0", right="0", rightF="0.0", top="0", topF="0.0")

    def _apply_node_styling(self, data_g: ET.Element, node: NodeModel,
                            disp_label: str, is_link: bool, graph: GraphModel) -> None:
        """Entscheidet, ob ein Knoten als Bild (Icon) oder geometrische Form gerendert wird."""
        icon_src = node.style.get("icon")

        if icon_src and icon_src in graph.image_resources:
            self._build_image_node(data_g, disp_label, icon_src, graph)
        else:
            self._build_shape_node(data_g, disp_label, node.style, is_link)

    def _build_image_node(self, data_g: ET.Element, disp_label: str, icon_src: str, graph: GraphModel) -> None:
        """Erzeugt XML für einen yEd-Knoten, der ein Icon/Bild darstellt."""
        img_data = graph.image_resources[icon_src]
        img_node = ET.SubElement(data_g, f"{YED_NS}ImageNode")
        ET.SubElement(img_node, f"{YED_NS}Geometry",
                      height=str(self.config.icon_height), width=str(img_data["width"]))
        ET.SubElement(img_node, f"{YED_NS}NodeLabel",
                      modelName="sandwich", modelPosition="s").text = disp_label
        ET.SubElement(img_node, f"{YED_NS}Image", refid=str(img_data["id"]))

    def _build_shape_node(self, data_g: ET.Element, disp_label: str, style: Dict[str, Any], is_link: bool) -> None:
        """Erzeugt XML für Standard-Formen (Rechteck, Kreis etc.) inklusive Text-Vermessung."""
        shape_n = ET.SubElement(data_g, f"{YED_NS}ShapeNode")

        color = style.get("color", "#E8EEF7")
        shape = style.get("shape", "roundrectangle")

        # Dynamische Textumbrucherkennung und Kasten-Größenberechnung
        formatted_label, width, height = self._format_and_measure_label(disp_label)

        node_label = ET.SubElement(shape_n, f"{YED_NS}NodeLabel")
        node_label.text = formatted_label
        node_label.set("alignment", "center")
        if is_link:
            node_label.set("underlinedText", "true")

        ET.SubElement(shape_n, f"{YED_NS}Geometry", width=width, height=height)
        ET.SubElement(shape_n, f"{YED_NS}Fill", color=color, transparent="false")
        ET.SubElement(shape_n, f"{YED_NS}Shape", type=shape)

    def _format_and_measure_label(self, label: str) -> Tuple[str, str, str]:
        """Berechnet basierend auf der Konfiguration die Kasten-Dimensionen für den Text."""
        layout = self.config.label_layout
        max_width_chars = layout.get("max_width_chars", 32)
        char_width = layout.get("char_width", 8)
        line_height = layout.get("line_height", 16)
        padding_x = layout.get("padding_x", 8)
        padding_y = layout.get("padding_y", 8)

        min_width = 1 * char_width + padding_x
        min_height = line_height + padding_y

        if not label:
            return "", f"{min_width}", f"{min_height}"

        normalized_label = " ".join(label.split())
        lines = textwrap.wrap(normalized_label, width=max_width_chars)
        formatted_label = "\n".join(lines)

        num_lines = len(lines)
        max_line_length = max((len(line) for line in lines), default=0)

        width = max(min_width, (max_line_length * char_width) + padding_x)
        height = max(min_height, (num_lines * line_height) + padding_y)

        return formatted_label, str(width), str(height)

    def _build_edges(self, graph: GraphModel) -> None:
        """Erstellt die Kanten im XML und führt bidirektionale Kanten zusammen."""
        edge_counter = 0
        edges_map: Dict[Tuple[str, str, str], EdgeModel] = {}
        bidi_flags: Dict[Tuple[str, str, str], bool] = {}

        # Bidirektionale Identifikation (Zusammenführen von Hin- und Rückweg mit gleichem Prädikat)
        for edge in graph.edges:
            p_str = edge.url or ""  # Speichert die Prädikats-URI
            s_str = edge.source_id
            o_str = edge.target_id

            forward = (s_str, p_str, o_str)
            backward = (o_str, p_str, s_str)

            if backward in edges_map:
                bidi_flags[backward] = True
            else:
                edges_map[forward] = edge
                bidi_flags[forward] = False

        # XML Generierung für sortierte Kanten
        for (s_str, p_str, o_str), edge_model in sorted(edges_map.items()):
            is_bidi = bidi_flags[(s_str, p_str, o_str)]

            edge_xml = ET.SubElement(self.graph_element, "edge", id=f"e{edge_counter}", source=s_str, target=o_str)
            edge_counter += 1

            ET.SubElement(edge_xml, "data", key="d_e_url").text = p_str
            poly = ET.SubElement(ET.SubElement(edge_xml, "data", key="d_eg"), f"{YED_NS}PolyLineEdge")

            style = edge_model.style
            color = style.get("color", "#000000")
            line_type = style.get("line_type", "line")
            target_arrow = style.get("target_arrow", "standard")
            line_width = str(style.get("line_width", "1.0"))

            source_arrow = target_arrow if is_bidi and target_arrow != "none" else "none"

            ET.SubElement(poly, f"{YED_NS}LineStyle", color=color, type=line_type, width=line_width)
            ET.SubElement(poly, f"{YED_NS}Arrows", source=source_arrow, target=target_arrow)
            ET.SubElement(poly, f"{YED_NS}EdgeLabel").text = edge_model.label