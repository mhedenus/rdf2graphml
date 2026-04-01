# rdf2graphml

Python library for easy converting any __RDF__ to __GraphML__ (http://graphml.graphdrawing.org/specification/xsd.html)
compatible with __yEd__ (https://www.yworks.com/products/yed).

## Configuration

### Styles

Following styles are known by __yEd__:

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

### Special Handling of RDF Lists

Lists are contracted to single nodes.

    "type_styles": {
      "http://yed.rdf.list/List": {
        "color": "#FFD700",
        "shape": "hexagon",
        "priority": 100
      }
    }


