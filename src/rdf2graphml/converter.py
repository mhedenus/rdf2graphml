import logging
import xml.etree.ElementTree as ET

from rdflib import Literal, BNode
from rdflib.namespace import RDFS, RDF

from .image_loader import load_image_as_base64

logger = logging.getLogger(__name__)


class RDFToYedConverter:
    def __init__(self, config):
        self.config = config
        self.root = ET.Element("graphml", {"xmlns": "http://graphml.graphdrawing.org/xmlns"})
        self.graph_element = ET.SubElement(self.root, "graph", id="G", edgedefault="directed")

        self.nodes_to_draw = set()
        self.node_attributes = {}
        self.all_attribute_keys = set()
        self.edge_counter = 0

        self.node_display_labels_raw = {}
        self.node_comments = {}
        self.node_icons = {}
        self.image_resources = {}
        self.node_types = {}

    def _generate_unique_attr_names(self, uris):
        used_names = {}
        mapping = {}
        for uri in sorted(uris):
            base_name = str(uri).split("/")[-1].split("#")[-1] or "attr"
            if base_name not in used_names:
                used_names[base_name] = 1
                mapping[uri] = base_name
            else:
                mapping[uri] = f"{base_name} ({used_names[base_name]})"
                used_names[base_name] += 1
        return mapping

    def _pass_1_collect_data(self, rdf_graph):
        self.nodes_forced_as_attributes = set()

        # 1. Filter anwenden: Nur erlaubte Tripel in die Verarbeitung aufnehmen
        allowed_triples = []
        for s, p, o in rdf_graph:
            is_structural = (p == RDF.type or p == RDFS.label or p == RDFS.comment or
                             p in self.config.icon_property_uris)

            # Prädikate filtern
            if not is_structural and not self.config.is_predicate_allowed(p):
                continue

            # Typen filtern
            if p == RDF.type and not self.config.is_type_allowed(o):
                continue

            allowed_triples.append((s, p, o))

        # 2. Strukturelle Daten aus den gefilterten Tripeln sammeln
        for s, p, o in allowed_triples:
            if p in self.config.entity_property_uris or p in self.config.icon_property_uris or p == RDF.type:
                self.nodes_forced_as_attributes.add(o)

            if p == RDFS.label and isinstance(o, Literal):
                if s not in self.node_display_labels_raw:
                    self.node_display_labels_raw[s] = []
                self.node_display_labels_raw[s].append((str(o), o.language))
            elif p == RDFS.comment:
                self.node_comments[s] = str(o)
            elif p in self.config.icon_property_uris:
                new_icon = {"source": str(o), "is_local": isinstance(o, Literal)}
                if s not in self.node_icons or new_icon["source"] < self.node_icons[s]["source"]:
                    self.node_icons[s] = new_icon
            elif p == RDF.type:
                if s not in self.node_types: self.node_types[s] = []
                self.node_types[s].append(o)

        # 3. Attribute und Knoten zum Zeichnen ermitteln
        for s, p, o in allowed_triples:
            if s not in self.nodes_forced_as_attributes:
                self.nodes_to_draw.add(s)

            if p == RDFS.comment or p in self.config.icon_property_uris:
                continue

            if isinstance(o, Literal) or p in self.config.entity_property_uris or p == RDF.type:
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

    def _get_display_label(self, node):
        """Ermittelt das deterministische Anzeigelabel basierend auf Sprache."""
        labels = self.node_display_labels_raw.get(node, [])
        if not labels:
            if isinstance(node, BNode):
                return ""
            else:
                return "<" + str(node) + ">"

        pref_lang = self.config.preferred_language

        pref_labels = [text for text, lang in labels if lang == pref_lang]
        if pref_labels:
            return sorted(pref_labels)[0]

        no_lang_labels = [text for text, lang in labels if not lang]
        if no_lang_labels:
            return sorted(no_lang_labels)[0]

        return sorted([text for text, lang in labels])[0]

    def _fetch_images(self):
        resource_id = 1
        seen_sources = {}
        for icon_data in self.node_icons.values():
            src = icon_data["source"]
            if src not in seen_sources:
                logger.info(f"Verarbeite Bild: {src}")

                # Defensives Entpacken inklusive Config-Base-Dir
                result = load_image_as_base64(
                    src,
                    icon_data["is_local"],
                    self.config.icon_target_height,
                    self.config.image_base_dir
                )

                if result and isinstance(result, tuple) and len(result) == 2:
                    b64, width = result
                    if b64 and width:
                        seen_sources[src] = {"id": resource_id, "base64": b64, "width": width}
                        resource_id += 1
                else:
                    logger.warning(f"Bild konnte nicht geladen werden und wird übersprungen: {src}")

        self.image_resources = seen_sources

    def _setup_graphml_keys(self):
        ET.SubElement(self.root, "key", id="d_ng", **{"for": "node", "yfiles.type": "nodegraphics"})
        ET.SubElement(self.root, "key", id="d_eg", **{"for": "edge", "yfiles.type": "edgegraphics"})
        ET.SubElement(self.root, "key", id="d_url", **{"attr.name": "url", "attr.type": "string", "for": "node"})
        ET.SubElement(self.root, "key", id="d_desc",
                      **{"attr.name": "description", "attr.type": "string", "for": "node"})
        ET.SubElement(self.root, "key", id="d_res", **{"for": "graphml", "yfiles.type": "resources"})

        name_map = self._generate_unique_attr_names(self.all_attribute_keys)
        mapping = {}
        for i, uri in enumerate(sorted(self.all_attribute_keys)):
            k_id = f"d_a{i}"
            name = name_map[uri]
            if name.lower() in ["url", "description"]: name += "_rdf"
            ET.SubElement(self.root, "key", id=k_id, **{"attr.name": name, "attr.type": "string", "for": "node"})
            mapping[uri] = k_id
        return mapping

    def _pass_2_build_graph(self, rdf_graph, attr_map):
        # 1. KNOTEN DETERMINISTISCH ZEICHNEN
        for node in sorted(self.nodes_to_draw):
            n_id = str(node)
            node_elem = ET.SubElement(self.graph_element, "node", id=n_id)
            ET.SubElement(node_elem, "data", key="d_url").text = n_id

            # HTML Tooltip für Kommentare
            if node in self.node_comments:
                comment_text = self.node_comments[node]
                html_tooltip = f"<html><body style='width: 250px;'>{comment_text}</body></html>"
                ET.SubElement(node_elem, "data", key="d_desc").text = html_tooltip

            if node in self.node_attributes:
                # Determinismus für Attribute
                for p_uri in sorted(self.node_attributes[node].keys()):
                    vals = self.node_attributes[node][p_uri]
                    ET.SubElement(node_elem, "data", key=attr_map[p_uri]).text = ", ".join(sorted(vals))

            data_g = ET.SubElement(node_elem, "data", key="d_ng")

            raw_label = self._get_display_label(node)
            max_len = 60
            disp_label = (raw_label[:(max_len - 3)] + "...") if len(raw_label) > max_len else raw_label

            icon_src = self.node_icons.get(node, {}).get("source")
            if icon_src in self.image_resources:
                img_data = self.image_resources[icon_src]
                img_node = ET.SubElement(data_g, "{http://www.yworks.com/xml/graphml}ImageNode")

                ET.SubElement(img_node, "{http://www.yworks.com/xml/graphml}Geometry",
                              height=str(self.config.icon_target_height),
                              width=str(img_data["width"]))

                ET.SubElement(img_node, "{http://www.yworks.com/xml/graphml}NodeLabel",
                              modelName="sandwich", modelPosition="s").text = disp_label
                ET.SubElement(img_node, "{http://www.yworks.com/xml/graphml}Image", refid=str(img_data["id"]))
            else:
                shape_n = ET.SubElement(data_g, "{http://www.yworks.com/xml/graphml}ShapeNode")
                color, shape = "#E8EEF7", "roundrectangle"
                if isinstance(node, BNode):
                    color, shape = "#C0C0C0", "ellipse"

                # Multi-Type Prioritäten deterministisch verarbeiten
                available_types = sorted(self.node_types.get(node, []), key=str)
                best_style, best_priority = None, -1

                for t in available_types:
                    if t in self.config.type_styles:
                        style = self.config.type_styles[t]
                        priority = style.get("priority", 0)
                        if best_style is None or priority > best_priority:
                            best_style, best_priority = style, priority

                if best_style:
                    color = best_style.get("color", color)
                    shape = best_style.get("shape", shape)

                ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}NodeLabel").text = disp_label
                width = str(max(50, len(disp_label) * 8 + 20)) if disp_label else "30"
                ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}Geometry", width=width, height="30")
                ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}Fill", color=color, transparent="false")
                ET.SubElement(shape_n, "{http://www.yworks.com/xml/graphml}Shape", type=shape)

        # 2. KANTEN SAMMELN UND DETERMINISTISCH ZEICHNEN
        edges_to_draw = []
        for s, p, o in rdf_graph:
            if s in self.nodes_to_draw and o in self.nodes_to_draw and not isinstance(o, Literal) \
                    and p not in (RDFS.comment, RDF.type) and p not in self.config.entity_property_uris \
                    and p not in self.config.icon_property_uris:

                # Kanten durch den Filter jagen
                if self.config.is_predicate_allowed(p):
                    edges_to_draw.append((str(s), str(p), str(o)))

        # Kanten deterministisch nach String-Wert sortieren
        for s_str, p_str, o_str in sorted(edges_to_draw):
            edge = ET.SubElement(self.graph_element, "edge", id=f"e{self.edge_counter}", source=s_str, target=o_str)
            self.edge_counter += 1
            poly = ET.SubElement(ET.SubElement(edge, "data", key="d_eg"),
                                 "{http://www.yworks.com/xml/graphml}PolyLineEdge")

            edge_label = p_str.split("/")[-1].split("#")[-1] or "link"
            ET.SubElement(poly, "{http://www.yworks.com/xml/graphml}EdgeLabel").text = edge_label
            ET.SubElement(poly, "{http://www.yworks.com/xml/graphml}Arrows", source="none", target="standard")

    def convert(self, rdf_graph):
        self._pass_1_collect_data(rdf_graph)
        self._fetch_images()
        attr_map = self._setup_graphml_keys()
        self._pass_2_build_graph(rdf_graph, attr_map)

        # Base64 Ressourcen einbetten
        if self.image_resources:
            res_data = ET.SubElement(self.root, "data", key="d_res")
            y_res = ET.SubElement(res_data, "{http://www.yworks.com/xml/graphml}Resources")
            for res in self.image_resources.values():
                r = ET.SubElement(y_res, "{http://www.yworks.com/xml/graphml}Resource", id=str(res["id"]),
                                  type="java.awt.image.BufferedImage")
                r.text = res["base64"]

    def save(self, path):
        tree = ET.ElementTree(self.root)
        ET.register_namespace('y', 'http://www.yworks.com/xml/graphml')
        if hasattr(ET, "indent"):
            ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)
