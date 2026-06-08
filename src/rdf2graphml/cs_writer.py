import json
import logging
from pathlib import Path
from typing import Union, Dict, List, Any

from .writer import GraphWriter
from .ir_model import GraphModel

logger = logging.getLogger(__name__)


class CytoscapeWriter(GraphWriter):
    """
    Kapselt die Serialisierung des agnostischen GraphModels in eine
    interaktive HTML-Datei unter Verwendung von Cytoscape.js.
    """

    # Übersetzungs-Wörterbuch (i18n)
    TRANSLATIONS = {
        "en": {
            "layout": "Layout Configuration:",
            "elk": "ELK (Hierarchical/Orthogonal)",
            "cola": "Cola (Force-directed)",
            "elk_spacing": "Node & Layer Spacing (ELK):",
            "cola_spacing": "Minimum Node Spacing (Cola):"
        },
        "de": {
            "layout": "Layout-Ansicht:",
            "elk": "ELK (Hierarchisch/Orthogonal)",
            "cola": "Cola (Kräftebasiert & Organisch)",
            "elk_spacing": "Knoten- & Schichtabstand (ELK):",
            "cola_spacing": "Mindestabstand der Knoten (Cola):"
        }
    }

    def write(self, graph: GraphModel, filepath: Union[str, Path]) -> None:
        """Setzt das abstrakte Interface um und erzeugt die HTML-Datei."""

        elements = self._build_elements(graph)
        stylesheet = self._get_stylesheet()

        # Sprache aus der Konfiguration ermitteln (Fallback: Englisch)
        lang_code = getattr(self.config, 'preferred_language', 'en').lower()
        if lang_code not in self.TRANSLATIONS:
            lang_code = 'en'
        
        i18n_dict = self.TRANSLATIONS[lang_code]

        # HTML Template von der Festplatte laden
        template_path = Path(__file__).parent / "cytoscape-template.html"
        if not template_path.exists():
            raise FileNotFoundError(f"Das HTML-Template wurde nicht gefunden: {template_path}")

        with open(template_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # JSON-Daten in das HTML-Template injizieren
        html_content = html_content.replace("/*LANG*/", lang_code)
        html_content = html_content.replace("/*ELEMENTS_JSON*/", json.dumps(elements, indent=2))
        html_content = html_content.replace("/*STYLE_JSON*/", json.dumps(stylesheet, indent=2))
        html_content = html_content.replace("/*I18N_JSON*/", json.dumps(i18n_dict, indent=2))

        # HTML Datei speichern
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        logger.debug(f"Cytoscape HTML erfolgreich nach {filepath} geschrieben.")

    def _build_elements(self, graph: GraphModel) -> List[Dict[str, Any]]:
        """Konvertiert die Graphendaten in das Cytoscape Element-Array."""
        elements = []

        # Knoten verarbeiten
        for node in graph.nodes.values():
            node_data = {
                "id": node.id,
                "label": node.label,
                "tooltip": node.tooltip or "",
            }

            if node.parent_id:
                node_data["parent"] = node.parent_id

            node_data["color"] = node.style.get("color", "#E8EEF7")
            
            shape = node.style.get("shape", "roundrectangle")
            shape_mapping = {
                "roundrectangle": "round-rectangle",
                "rectangle": "rectangle",
                "ellipse": "ellipse",
                "octagon": "octagon",
                "parallelogram": "rhomboid" 
            }
            node_data["shape"] = shape_mapping.get(shape, "rectangle")

            icon_src = node.style.get("icon")
            if icon_src and icon_src in graph.image_resources:
                b64_data = graph.image_resources[icon_src]["base64"]
                node_data["bg_image"] = f"data:image/png;base64,{b64_data}"

            classes = "group-node" if node.is_group else "standard-node"

            elements.append({
                "group": "nodes",
                "data": node_data,
                "classes": classes
            })

        # Kanten verarbeiten
        for edge in graph.edges:
            edge_data = {
                "id": edge.id,
                "source": edge.source_id,
                "target": edge.target_id,
                "label": edge.label,
                "color": edge.style.get("color", "#000000"),
                "line_style": "dashed" if edge.style.get("line_type") == "dashed" else "solid",
            }

            elements.append({
                "group": "edges",
                "data": edge_data
            })

        return elements

    def _get_stylesheet(self) -> List[Dict[str, Any]]:
        """Definiert die visuellen Regeln für den Cytoscape Graphen."""
        return [
            {
                "selector": "node.standard-node",
                "style": {
                    "label": "data(label)",
                    "text-valign": "bottom",
                    "text-halign": "center",
                    "text-margin-y": 5,
                    "shape": "data(shape)",
                    "background-color": "data(color)",
                    "border-width": 1,
                    "border-color": "#666",
                    "width": "60px",
                    "height": "60px",
                    "text-wrap": "wrap",
                    "text-max-width": "120px",
                    "font-size": "12px",
                    "font-family": "sans-serif"
                }
            },
            {
                "selector": "node[bg_image]",
                "style": {
                    "background-image": "data(bg_image)",
                    "background-fit": "contain",
                    "background-clip": "none",
                    "background-opacity": 0, 
                    "border-width": 0
                }
            },
            {
                "selector": "node.group-node",
                "style": {
                    "label": "data(label)",
                    "text-valign": "top",
                    "text-halign": "center",
                    "background-color": "data(color)",
                    "background-opacity": 0.33,
                    "border-width": 2,
                    "border-style": "dashed",
                    "border-color": "#333",
                    "padding": "20px",
                    "font-weight": "bold",
                    "font-size": "14px"
                }
            },
            {
                "selector": "edge",
                "style": {
                    "label": "data(label)",
                    "curve-style": "taxi", 
                    "taxi-direction": "downward",
                    "line-color": "data(color)",
                    "width": 2,
                    "target-arrow-shape": "triangle",
                    "target-arrow-color": "data(color)",
                    "font-size": "10px",
                    "text-rotation": "autorotate",
                    "text-margin-y": -10,
                    "text-background-opacity": 1,
                    "text-background-color": "#ffffff",
                    "text-background-padding": "2px"
                }
            },
            {
                "selector": "edge[line_style = 'dashed']",
                "style": {
                    "line-style": "dashed"
                }
            }
        ]