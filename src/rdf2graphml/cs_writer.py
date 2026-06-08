import json
import logging
from pathlib import Path
from typing import Union, Dict, List, Any

from .writer import GraphWriter
from .ir_model import GraphModel, NodeModel, EdgeModel

logger = logging.getLogger(__name__)


class CytoscapeWriter(GraphWriter):
    """
    Kapselt die Serialisierung des agnostischen GraphModels in eine
    interaktive, eigenständige HTML-Datei unter Verwendung von Cytoscape.js.
    """

    def write(self, graph: GraphModel, filepath: Union[str, Path]) -> None:
        """Setzt das abstrakte Interface um und erzeugt die HTML-Datei."""

        # 1. Elemente (Knoten und Kanten) für Cytoscape vorbereiten
        elements = self._build_elements(graph)
        
        # 2. Stylesheet (CSS-Äquivalent für Cytoscape) definieren
        stylesheet = self._get_stylesheet()

        # 3. HTML Template mit eingebettetem JS aufbauen
        html_content = self._get_html_template()

        # 4. JSON-Daten in das HTML-Template injizieren
        html_content = html_content.replace("/*ELEMENTS_JSON*/", json.dumps(elements, indent=2))
        html_content = html_content.replace("/*STYLE_JSON*/", json.dumps(stylesheet, indent=2))

        # 5. HTML Datei schreiben
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

            # Verschachtelung (Compound Nodes) auflösen
            if node.parent_id:
                node_data["parent"] = node.parent_id

            # Styles in die Node-Daten packen (wird im Stylesheet über 'data(...)' referenziert)
            node_data["color"] = node.style.get("color", "#E8EEF7")
            
            # yEd Shapes in Cytoscape Shapes mappen
            shape = node.style.get("shape", "roundrectangle")
            shape_mapping = {
                "roundrectangle": "round-rectangle",
                "rectangle": "rectangle",
                "ellipse": "ellipse",
                "octagon": "octagon",
                "parallelogram": "rhomboid" # Cytoscape nutzt rhomboid für Parallelogramme
            }
            node_data["shape"] = shape_mapping.get(shape, "rectangle")

            # Icon/Bild Verarbeitung
            icon_src = node.style.get("icon")
            if icon_src and icon_src in graph.image_resources:
                b64_data = graph.image_resources[icon_src]["base64"]
                # Cytoscape benötigt den Data-URI Header
                node_data["bg_image"] = f"data:image/png;base64,{b64_data}"

            # Klasse zuweisen, falls es eine Gruppe ist (für spezielles CSS)
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
            # Standard Knoten
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
                    # Zeilenumbrüche erlauben
                    "text-wrap": "wrap",
                    "text-max-width": "120px",
                    "font-size": "12px",
                    "font-family": "sans-serif"
                }
            },
            # Knoten mit Icons
            {
                "selector": "node[bg_image]",
                "style": {
                    "background-image": "data(bg_image)",
                    "background-fit": "contain",
                    "background-clip": "none",
                    "background-opacity": 0, # Mache den Hintergrund transparent, zeige nur das Bild
                    "border-width": 0
                }
            },
            # Gruppen / Verschachtelte Knoten (Compound)
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
            # Kanten
            {
                "selector": "edge",
                "style": {
                    "label": "data(label)",
                    "curve-style": "taxi", # Taxi eignet sich extrem gut für ELK/Orthogonal
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
            # Kantenspezifische Linienstile (dashed)
            {
                "selector": "edge[line_style = 'dashed']",
                "style": {
                    "line-style": "dashed"
                }
            }
        ]

    def _get_html_template(self) -> str:
        """Liefert das HTML-Grundgerüst mit Cytoscape, ELK und Cola."""
        return """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RDF2GraphML - Cytoscape Export</title>
    <style>
        body { font-family: sans-serif; margin: 0; padding: 0; overflow: hidden; background-color: #fafafa; }
        #cy { width: 100vw; height: 100vh; position: absolute; top: 0; left: 0; }
        #controls { position: absolute; top: 10px; left: 10px; z-index: 10; background: white; padding: 10px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
    </style>

    <script src="https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"></script>
    
    <script src="https://unpkg.com/elkjs@0.8.2/lib/elk.bundled.js"></script>
    <script src="https://unpkg.com/cytoscape-elk@2.1.0/dist/cytoscape-elk.js"></script>
    
    <script src="https://unpkg.com/webcola@3.4.0/WebCola/cola.min.js"></script>
    <script src="https://unpkg.com/cytoscape-cola@2.5.1/cytoscape-cola.js"></script>
</head>
<body>
    <div id="controls">
        <strong>Layout:</strong>
        <select id="layout-selector">
            <option value="elk">ELK (Hierarchisch/Orthogonal)</option>
            <option value="cola">Cola (Kräftebasiert)</option>
        </select>
    </div>
    <div id="cy"></div>

    <script>
        // 1. Graphen-Daten und Styles (werden von Python injiziert)
        const graphElements = /*ELEMENTS_JSON*/;
        const graphStyle = /*STYLE_JSON*/;

        // 2. Layout Konfigurationen vorbereiten
        
        // ELK: Perfekt für verschachtelte (Compound) Graphen mit klaren Richtungen
        const layoutElk = {
            name: 'elk',
            elk: {
                algorithm: 'layered',
                'elk.direction': 'DOWN',
                'elk.edgeRouting': 'ORTHOGONAL',
                'elk.spacing.nodeNode': 40,
                'elk.layered.spacing.nodeNodeBetweenLayers': 40
            }
        };

        // COLA: Perfekt für organische, physik-basierte Anordnungen, respektiert auch Compound-Nodes
        const layoutCola = {
            name: 'cola',
            animate: true,
            randomize: false,
            maxSimulationTime: 2000,
            nodeSpacing: 20,
            edgeLengthVal: 45
        };

        // 3. Cytoscape initialisieren
        document.addEventListener('DOMContentLoaded', function() {
            var cy = cytoscape({
                container: document.getElementById('cy'),
                elements: graphElements,
                style: graphStyle,
                layout: layoutElk // Standard-Start-Layout
            });

            // Tooltips einfaches Fallback (Titel-Attribut auf Canvas setzen)
            cy.on('mouseover', 'node', function(e){
                var node = e.target;
                if(node.data('tooltip')) {
                    document.getElementById('cy').setAttribute('title', node.data('tooltip'));
                }
            });
            cy.on('mouseout', 'node', function(e){
                document.getElementById('cy').removeAttribute('title');
            });

            // UI Logik zum dynamischen Wechseln des Layouts (ELK <-> Cola)
            document.getElementById('layout-selector').addEventListener('change', function(e) {
                var selected = e.target.value;
                var layoutConfig = (selected === 'cola') ? layoutCola : layoutElk;
                
                // Edge Style anpassen für schöneres Rendering
                if(selected === 'cola') {
                    cy.style().selector('edge').style({'curve-style': 'bezier'}).update();
                } else {
                    cy.style().selector('edge').style({'curve-style': 'taxi'}).update();
                }

                var layout = cy.layout(layoutConfig);
                layout.run();
            });
        });
    </script>
</body>
</html>
"""