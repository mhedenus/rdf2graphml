import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Union

from .writer import GraphWriter
from .ir_model import GraphModel, NodeModel, EdgeModel


class DrawIOWriter(GraphWriter):
    """
    Kapselt die Serialisierung des agnostischen GraphModels in das
    Draw.io (mxGraph) XML-Format.
    """

    def write(self, graph: GraphModel, filepath: Union[str, Path]) -> None:
        """Setzt das abstrakte Interface um und erzeugt die Draw.io-Datei."""

        # 1. XML-Grundgerüst für Draw.io aufbauen
        mxfile = ET.Element("mxfile")
        diagram = ET.SubElement(mxfile, "diagram", id="diagram_1", name="Exported Graph")
        mx_graph_model = ET.SubElement(
            diagram, "mxGraphModel",
            dx="1000", dy="1000", grid="1", gridSize="10", guides="1",
            tooltips="1", connect="1", arrows="1", fold="1", page="1",
            pageScale="1", pageWidth="827", pageHeight="1169", math="0", shadow="0"
        )
        self.root = ET.SubElement(mx_graph_model, "root")

        # Draw.io benötigt diese beiden unsichtbaren Basis-Zellen für das Canvas
        ET.SubElement(self.root, "mxCell", id="0")
        ET.SubElement(self.root, "mxCell", id="1", parent="0")

        # 2. Alle Knoten schreiben
        for node in graph.nodes.values():
            self._build_node(node, graph)

        # 3. Alle Kanten schreiben
        for edge in graph.edges:
            self._build_edge(edge)

        # 4. XML-Datei formatieren und abspeichern
        tree = ET.ElementTree(mxfile)
        if hasattr(ET, "indent"):
            ET.indent(tree, space="  ")

        tree.write(str(filepath), encoding="utf-8", xml_declaration=True)

    def _build_node(self, node: NodeModel, graph: GraphModel) -> None:
        """Übersetzt ein NodeModel in eine Draw.io mxCell."""
        # Standard-Parent ist 1, es sei denn, der Knoten liegt in einer Gruppe
        parent_id = node.parent_id if node.parent_id else "1"

        # Basis-Stile
        color = node.style.get("color", "#E8EEF7")
        style_parts = ["whiteSpace=wrap", "html=1", f"fillColor={color}"]

        # Typ-/Form-Zuweisung
        if node.is_group:
            style_parts.insert(0, "swimlane")
            width, height = "300", "300"
        else:
            shape = node.style.get("shape", "roundrectangle")
            if shape == "roundrectangle":
                style_parts.insert(0, "rounded=1")
            else:
                style_parts.insert(0, f"shape={shape}")
            width, height = "120", "60"  # Fallback-Größe für Standard-Knoten

        # Icon-Zuweisung (Draw.io bettet Base64 direkt in den Style-String ein)
        icon_src = node.style.get("icon")
        if icon_src and icon_src in graph.image_resources:
            b64_data = graph.image_resources[icon_src]["base64"]
            img_width = graph.image_resources[icon_src]["width"]
            style_parts.insert(0, "shape=image")

            # WICHTIGER FIX: Komma statt ";base64," verwenden, damit
            # der mxGraph-Style-Parser nicht aus dem Tritt gerät!
            style_parts.append(f"image=data:image/png,{b64_data}")

            style_parts.append("verticalLabelPosition=bottom")
            style_parts.append("verticalAlign=top")
            width = str(img_width)
            height = str(self.config.icon_height)

        style_str = ";".join(style_parts) + ";"

        # Label zusammenbauen
        label_html = self._format_label(node)

        # Zelle in den XML-Baum einfügen
        cell = ET.SubElement(
            self.root, "mxCell",
            id=node.id, value=label_html, style=style_str,
            vertex="1", parent=parent_id
        )

        ET.SubElement(cell, "mxGeometry", width=width, height=height, **{"as": "geometry"})

    def _format_label(self, node: NodeModel) -> str:
        """Formatiert das Label und fügt Metadaten/Attribute hinzu."""
        label = node.label
        # Optional: Hier könnte man die Attribute aus node.attributes als HTML-Tabelle anhängen
        # Draw.io unterstützt rudimentäres HTML in Labels, wenn 'html=1' im Style gesetzt ist.
        return label

    def _build_edge(self, edge: EdgeModel) -> None:
        """Übersetzt ein EdgeModel in eine verbindende mxCell."""
        color = edge.style.get("color", "#000000")
        target_arrow = edge.style.get("target_arrow", "classic")

        # Draw.io Edge Styles
        style_str = (
            f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
            f"jettySize=auto;html=1;strokeColor={color};"
        )

        # Zelle erzeugen (Kanten liegen normalerweise im Root-Parent "1")
        cell = ET.SubElement(
            self.root, "mxCell",
            id=edge.id, value=edge.label, style=style_str,
            edge="1", parent="1", source=edge.source_id, target=edge.target_id
        )
        ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})