# rdf2graphml

Python library for easy converting any __RDF__ to **[GraphML](http://graphml.graphdrawing.org/specification/xsd.html)**
compatible with **[yEd](https://www.yworks.com/products/yed)**.

The RDF-to-GraphML conversion is very customizable.
The basic idea is to extend an existing model or ontology with visualization properties.
The ontology for these annotation properties is found here: `rdf2graphml.ttl`.

If you do not have a model or ontology you can specify a JSON configuration file.

## Usage

    rdf2graphml [-h] [-V] [-v] [--type_as_edge] [-m MODEL] [-c CONFIG] -o OUTPUT inputs [inputs ...] 

If you use `-m` and `-c` option, the JSON configuration will be loaded bofore the model
The properties from the model will then overwrite the JSON configuration.
In any case the command line option `--type_as_edge` takes precedence.


The converter automatically detects the format of your INPUT files based on their file extensions. The following formats are supported out of the box:

**Standard RDF Formats:**
Any format supported by rdflib (`.ttl` for Turtle, `.rdf` for RDF/XML, `.nt` for N-Triples).

**JSON-LD:** Explicit support for `.jsonld` files.

**Graffl:** Native support for parsing `.graffl` files - see
the **[graffl project](https://github.com/mhedenus/graffl)**.

## Configuration

While the annotation properties in the provided RDF ontology use camelCase
(e.g. `rdf2graphml:lineWidth`), the
corresponding keys in the JSON configuration use snake_case (e.g. `line_width`).
Your actual RDF URIs used in the configuration remain unchanged.

### Annotating a Model or Ontology

Annotating a model or ontology is simple, just add the layout properties to your types:

    @prefix rdf2graphml: <https://www.hedenus.de/rdf2graphml/> .
    
    <http://example.org#System> a owl:Class ;
      rdf2graphml:icon "icons/my_icon.png" .

    <http://example.org#note> a rdf:Property ;
      rdf2graphml:color "#FFAAAA" ;
      rdf2graphml:lineWidth "2.0" .

### Example JSON Configuration

```json
{
  "namespaces": {
    "ex": "http://example.org/ontology/",
    "schema": "http://schema.org/",
    "rdf2": "https://www.hedenus.de/rdf2graphml/"
  },
  "base_dir": "./assets/icons",
  "icon_height": 80,
  "preferred_language": "de",
  "type_as_edge": false,
  "node_properties": [
    "http://www.w3.org/2000/01/rdf-schema#comment",
    "http://example.org/ontology/internalId"
  ],
  "icon_locators": [
    "http://example.org/ontology/hasIcon",
    "https://www.hedenus.de/rdf2graphml/icon"
  ],
  "group_type": "http://example.org/ontology/SystemBoundary",
  "group_contains": "http://example.org/ontology/containsComponent",
  "default_node_style": {
    "blank_nodes": {
      "color": "#F0F0F0",
      "shape": "ellipse"
    },
    "uri_nodes": {
      "color": "#DAE8FC",
      "shape": "roundrectangle"
    }
  },
  "type_styles": {
    "http://example.org/ontology/Database": {
      "icon": "database_icon.png",
      "color": "#FFE6CC",
      "shape": "cylinder",
      "priority": 20
    },
    "http://example.org/ontology/Service": {
      "color": "#D5E8D4",
      "shape": "rectangle",
      "priority": 10
    },
    "https://www.hedenus.de/rdf2graphml/List": {
      "color": "#FFFF88",
      "shape": "hexagon",
      "priority": 100
    }
  },
  "edge_styles": {
    "http://example.org/ontology/calls": {
      "color": "#0000FF",
      "line_type": "line",
      "line_width": "2.0",
      "target_arrow": "standard",
      "label": "ruft auf"
    },
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type": {
      "color": "#888888",
      "line_type": "dashed",
      "target_arrow": "transparent_circle"
    }
  },
  "include_predicates": [
    "http://example.org/*",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
  ],
  "exclude_predicates": [
    "http://example.org/ontology/ignoredProperty"
  ],
  "include_types": [
    "*"
  ],
  "exclude_types": [
    "http://example.org/ontology/HiddenType"
  ]
}
```

### Reference

#### General Settings

* `namespaces` *(object)*: A dictionary mapping prefixes to namespace URIs. These custom namespaces are registered with
  the converter to generate shorter QName labels (e.g., `ex:Node`) for nodes and edges instead of full URIs. Overrides
  existing prefixes in the source graph.
* `base_dir` *(string)*: The base directory used to resolve local image paths specified by `icon_locators`. Defaults to
  the directory of the configuration file.
* `icon_height` *(integer)*: The target height in pixels for downloaded/loaded icons. The width is scaled proportionally
  using Lanczos resampling. Default: `64`.
* `preferred_language` *(string)*: The language tag used to pick the primary `rdfs:label` for display purposes (e.g.,
  `"en"` or `"de"`). If not found, it falls back to a label without a language tag, or an arbitrary one. Default:
  `"en"`.
* `type_as_edge` *(boolean)*: If `true`, `rdf:type` relations are drawn as explicit edges in the graph. If `false`, they
  are collected as node attributes (GraphML Data). Default: `false`.

#### RDF Mapping & Extraction

* `node_properties` *(list of strings)*: A list of URIs. Triples with these predicates are explicitly prevented from
  becoming edges. Instead, their objects are attached to the subject node as GraphML data attributes.
* `icon_locators` *(list of strings)*: A list of URIs. If a node has one of these predicates, the converter interprets
  the object as a URL or local file path to an image, downloads/reads it, converts it to Base64, and renders the node as
  a __yEd__ `ImageNode`.

#### Groups & Hierarchies (Nested Graphs)

* `group_type` *(string)*: The URI of the `rdf:type` that identifies a node as a group container.
* `group_contains` *(string)*: The URI of the predicate used to link a group node to its children. These triples
  establish the nested graph hierarchy in __yEd__ and will *not* be drawn as visible edges.

#### Styling

* `default_node_style` *(object)*: Fallback styling for nodes.
    * `blank_nodes`: Style object (`color`, `shape`) applied to RDF Blank Nodes. Default: Grey ellipse.
    * `uri_nodes`: Style object (`color`, `shape`) applied to standard URI nodes. Default: Light-blue roundrectangle.

* `type_styles` *(object)*: Maps `rdf:type` URIs to specific styles.
    * `icon` (string): URL or local path to a default image/icon for this type. Takes precedence over shape. If the
      image fails to load, the converter gracefully falls back to the configured shape.
    * `color` *(string)*: Hex color code (e.g. `"#ADD8E6"`).
    * `shape` *(string)*: Shape identifier
    * `priority` *(integer)*: If a node has multiple types, the style with the highest priority wins.

* `edge_styles` *(object)*: Maps predicate URIs to edge styles.
    * `color` *(string)*: Hex color code (e.g. `"#ADD8E6"`).
    * `line_type` *(string)*:  Line type identifier.
    * `line_width` *(string)*: Line width (e.g. `2.0`).
    * `target_arrow` *(string)*: Arrow types identifier.

#### RDF Lists

The converter automatically aggregates `rdf:first`/`rdf:rest` lists into a single node. You can style this generated
node by targeting the URI `https://www.hedenus.de/rdf2graphml/List`.

      "type_styles": {
          "https://www.hedenus.de/rdf2graphml/List": {
              "color": "#FFD700",
              "shape": "hexagon",
              "priority": 100
        }}

#### Filtering

Filters accept Unix shell-style wildcards (e.g., `*` or `http://example.org/*`). The exclusion rules are always
evaluated before the inclusion rules.

* `include_predicates` *(list of strings)*: Only predicates matching these patterns will be drawn as edges. If empty,
  all predicates (that are not structural/excluded) are allowed.
* `exclude_predicates` *(list of strings)*: Predicates matching these patterns are completely ignored.
* `include_types` *(list of strings)*: Only nodes possessing an `rdf:type` matching these patterns are drawn.
* `exclude_types` *(list of strings)*: Nodes possessing an `rdf:type` matching these patterns are explicitly ignored.

### Styles known by yEd

Also see the application's documentation.

`shape`:

- `diamond`
- `ellipse`
- `fatarrow` (pointing to right)
- `fatarrow2` (pointing to left)
- `hexagon`
- `octagon`
- `parallelogram` (skewed right)
- `parallelogram2` (skewed left)
- `rectangle3d`
- `rectangle`
- `roundrectangle`
- `star5`
- `star6`
- `star8`
- `trapezoid` (pointing up)
- `trapezoid2` (pointing down)
- `triangle` (pointing up)
- `triangle2` (pointing down)

`line_type`:

- `dashed`
- `dashed_dotted`
- `dotted`
- `line`

`target_arrow`:

- `circle`
- `delta`
- `diamond`
- `none`
- `plain`
- `short`
- `standard`
- `transparent_circle`
- `white_circle`
- `white_delta`
- `white_diamond`

## Credits

- User icon (alice.png) created by Heykiyou - [Flaticon](https://www.flaticon.com/)
- Battery icon (battery.png) created by Freepik - [Flaticon](https://www.flaticon.com/)
- User icon (user.png) created by meaicon - [Flaticon](https://www.flaticon.com/)