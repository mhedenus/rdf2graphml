# rdf2graphml

Python library for easy converting any __RDF__ to __GraphML__ (http://graphml.graphdrawing.org/specification/xsd.html)
compatible with __yEd__ (https://www.yworks.com/products/yed).

## Usage

    rdf2graphml [-h] [-v] -c CONFIG.json OUTPUT.graphml INPUT [INPUT..] 



## Configuration

The RDF-to-GraphML conversion is highly customizable via a JSON configuration file. This allows you to control exactly which triples are drawn as nodes, edges, or data attributes, and how they are visually styled in __yEd__.

### Example Configuration

```json
{
  "base_dir": "./images",
  "icon_height": 64,
  "preferred_language": "en",
  "type_as_edge": false,
  "node_properties": ["http://www.w3.org/2000/01/rdf-schema#label"],
  "icon_locators": ["http://example.org/ontology/iconUrl"],
  "group_type": "http://example.org/ontology/Group",
  "group_contains": "http://example.org/ontology/contains",
  "default_node_style": {
    "blank_nodes": { "color": "#DDDDDD", "shape": "ellipse" },
    "uri_nodes": { "color": "#E8EEF7", "shape": "roundrectangle" }
  },
  "type_styles": {
    "http://example.org/ontology/System": { "color": "#ADD8E6", "shape": "roundrectangle", "priority": 10 }
  },
  "edge_styles": {
    "http://example.org/ontology/dependsOn": { "color": "#FF0000", "line_type": "dashed", "target_arrow": "standard" }
  },
  "include_predicates": ["*"],
  "exclude_predicates": []
}
```

### Reference

#### General Settings
* `base_dir` *(string)*: The base directory used to resolve local image paths specified by `icon_locators`. Defaults to the directory of the configuration file.
* `icon_height` *(integer)*: The target height in pixels for downloaded/loaded icons. The width is scaled proportionally using Lanczos resampling. Default: `64`.
* `preferred_language` *(string)*: The language tag used to pick the primary `rdfs:label` for display purposes (e.g., `"en"` or `"de"`). If not found, it falls back to a label without a language tag, or an arbitrary one. Default: `"de"`.
* `type_as_edge` *(boolean)*: If `true`, `rdf:type` relations are drawn as explicit edges in the graph. If `false`, they are collected as node attributes (GraphML Data). Default: `false`.

#### RDF Mapping & Extraction
* `node_properties` *(list of strings)*: A list of URIs. Triples with these predicates are explicitly prevented from becoming edges. Instead, their objects are attached to the subject node as GraphML data attributes.
* `icon_locators` *(list of strings)*: A list of URIs. If a node has one of these predicates, the converter interprets the object as a URL or local file path to an image, downloads/reads it, converts it to Base64, and renders the node as a __yEd__ `ImageNode`.

#### Groups & Hierarchies (Nested Graphs)
* `group_type` *(string)*: The URI of the `rdf:type` that identifies a node as a group container.
* `group_contains` *(string)*: The URI of the predicate used to link a group node to its children. These triples establish the nested graph hierarchy in __yEd__ and will *not* be drawn as visible edges.

#### Styling
* `default_node_style` *(object)*: Fallback styling for nodes.
    * `blank_nodes`: Style object (`color`, `shape`) applied to RDF Blank Nodes. Default: Grey ellipse.
    * `uri_nodes`: Style object (`color`, `shape`) applied to standard URI nodes. Default: Light-blue roundrectangle.
* `type_styles` *(object)*: Maps `rdf:type` URIs to specific styles.
    * `color` *(string)*: Hex color code (e.g., `"#ADD8E6"`).
    * `shape` *(string)*: __yEd__ shape identifier (e.g., `"roundrectangle"`, `"ellipse"`, `"hexagon"`, `"diamond"`).
    * `priority` *(integer)*: If a node has multiple types, the style with the highest priority wins.
    
* `edge_styles` *(object)*: Maps predicate URIs to edge styles.
    * `color` *(string)*: Hex color code.
    * `line_type` *(string)*: Supported __yEd__ line types (e.g., `"line"`, `"dashed"`, `"dotted"`).
    * `target_arrow` *(string)*: Supported __yEd__ arrow types (e.g., `"standard"`, `"white_delta"`, `"none"`).

#### RDF Lists

The converter automatically aggregates `rdf:first`/`rdf:rest` lists into a single node. You can style this generated node by targeting the URI `https://www.hedenus.de/rdf2graphml/List`.
      
      "type_styles": {
          "https://www.hedenus.de/rdf2graphml/List": {
              "color": "#FFD700",
              "shape": "hexagon",
              "priority": 100
        }}


#### Filtering
Filters accept **Unix shell-style wildcards** (e.g., `*` or `http://example.org/*`). The exclusion rules are always evaluated before the inclusion rules.

* `include_predicates` *(list of strings)*: Only predicates matching these patterns will be drawn as edges. If empty, all predicates (that are not structural/excluded) are allowed.
* `exclude_predicates` *(list of strings)*: Predicates matching these patterns are completely ignored.
* `include_types` *(list of strings)*: Only nodes possessing an `rdf:type` matching these patterns are drawn.
* `exclude_types` *(list of strings)*: Nodes possessing an `rdf:type` matching these patterns are explicitly ignored.



### Styles known by yEd

`shape`:

- `diamond`
- `ellipse`
- `hexagon`
- `octagon`
- `parallelogram`
- `rectangle`
- `rectangle3d`
- `roundrectangle`
- `trapezoid`
- `trapezoid2`
- `triangle`

`line_type`:

- `dashed`
- `dashed_dotted`
- `dotted`
- `line`

`target_arrow`:

- `diamond`
- `none`
- `standard`
- `transparent_circle`
- `white_delta`

