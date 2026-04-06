import fnmatch
import json
import logging
from pathlib import Path
from typing import Set, List, Dict, Optional, Any

from rdflib import URIRef, Graph, Namespace
from rdflib.namespace import RDF

logger = logging.getLogger(__name__)

# Namespace für die Konfiguration
CONF = Namespace("https://www.hedenus.de/rdf2graphml/")


class ConverterConfig:
    def __init__(
            self,
            node_properties: Optional[List[str]] = None,
            icon_locators: Optional[List[str]] = None,
            type_styles: Optional[Dict[str, Dict[str, Any]]] = None,
            edge_styles: Optional[Dict[str, Dict[str, Any]]] = None,
            type_as_edge: bool = False,
            icon_height: int = 64,
            preferred_language: str = "de",
            base_dir: Optional[Path] = None,
            include_predicates: Optional[List[str]] = None,
            exclude_predicates: Optional[List[str]] = None,
            include_types: Optional[List[str]] = None,
            exclude_types: Optional[List[str]] = None,
            group_type: Optional[str] = None,
            group_contains: Optional[str] = None,
            namespaces: Optional[Dict[str, str]] = None,  # NEU
            default_node_style: Optional[Dict[str, Dict[str, str]]] = None
    ) -> None:

        self.namespaces: Dict[str, str] = namespaces or {}  # NEU
        self.type_as_edge: bool = type_as_edge
        self.node_properties: Set[URIRef] = {URIRef(u) for u in node_properties} if node_properties else set()
        self.icon_locators: Set[URIRef] = {URIRef(u) for u in icon_locators} if icon_locators else set()
        self.type_styles: Dict[URIRef, Dict[str, Any]] = {URIRef(k): v for k, v in
                                                          type_styles.items()} if type_styles else {}
        self.edge_styles: Dict[URIRef, Dict[str, Any]] = {URIRef(k): v for k, v in
                                                          edge_styles.items()} if edge_styles else {}
        self.icon_height: int = icon_height
        self.preferred_language: str = preferred_language
        self.image_base_dir: Path = base_dir if base_dir else Path.cwd()

        self.include_predicates: List[str] = include_predicates if include_predicates else []
        self.exclude_predicates: List[str] = exclude_predicates if exclude_predicates else []
        self.include_types: List[str] = include_types if include_types else []
        self.exclude_types: List[str] = exclude_types if exclude_types else []

        self.group_type: Optional[URIRef] = URIRef(group_type) if group_type else None
        self.group_contains: Optional[URIRef] = URIRef(group_contains) if group_contains else None

        self.default_node_style: Dict[str, Dict[str, str]] = default_node_style or {
            "blank_nodes": {"color": "#C0C0C0", "shape": "ellipse"},
            "uri_nodes": {"color": "#E8EEF7", "shape": "roundrectangle"}
        }

    def _is_uri_allowed(self, uri: URIRef, includes: List[str], excludes: List[str]) -> bool:
        uri_str = str(uri)
        for pattern in excludes:
            if fnmatch.fnmatch(uri_str, pattern):
                return False
        if not includes:
            return True
        for pattern in includes:
            if fnmatch.fnmatch(uri_str, pattern):
                return True
        return False

    def is_predicate_allowed(self, predicate_uri: URIRef) -> bool:
        return self._is_uri_allowed(predicate_uri, self.include_predicates, self.exclude_predicates)

    def is_type_allowed(self, type_uri: URIRef) -> bool:
        return self._is_uri_allowed(type_uri, self.include_types, self.exclude_types)

    @classmethod
    def from_json(cls, file_path: str) -> 'ConverterConfig':
        config_path = Path(file_path).resolve()
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        base_dir = config_path.parent
        if "base_dir" in data:
            base_dir = (config_path.parent / data["base_dir"]).resolve()

        return cls(
            node_properties=data.get("node_properties", []),
            icon_locators=data.get("icon_locators", []),
            type_styles=data.get("type_styles", {}),
            edge_styles=data.get("edge_styles", {}),
            type_as_edge=data.get("type_as_edge", False),
            icon_height=data.get("icon_height", 64),
            preferred_language=data.get("preferred_language", "de"),
            base_dir=base_dir,
            include_predicates=data.get("include_predicates", []),
            exclude_predicates=data.get("exclude_predicates", []),
            include_types=data.get("include_types", []),
            exclude_types=data.get("exclude_types", []),
            group_type=data.get("group_type"),
            group_contains=data.get("group_contains"),
            namespaces=data.get("namespaces", {}),  # NEU
            default_node_style=data.get("default_node_style")
        )

    @classmethod
    def from_rdf(cls, graph: Graph, file_path: Optional[str] = None) -> 'ConverterConfig':
        config_nodes = list(graph.subjects(RDF.type, CONF.Configuration))
        if not config_nodes:
            raise ValueError(f"No configuration node found (Expected type: {CONF.Configuration})")

        c_node = config_nodes[0]

        def get_str(pred: URIRef, default: Any = None) -> Any:
            val = graph.value(c_node, pred)
            return str(val) if val is not None else default

        def get_int(pred: URIRef, default: int) -> int:
            val = graph.value(c_node, pred)
            return int(val) if val is not None else default

        def get_bool(pred: URIRef, default: bool) -> bool:
            val = graph.value(c_node, pred)
            if val is not None:
                return str(val).lower() == "true"
            return default

        def get_list(pred: URIRef) -> List[str]:
            return [str(o) for o in graph.objects(c_node, pred)]

        type_as_edge = get_bool(CONF.type_as_edge, False)
        icon_height = get_int(CONF.icon_height, 64)
        preferred_language = get_str(CONF.preferred_language, "de")
        group_type = get_str(CONF.group_type)
        group_contains = get_str(CONF.group_contains)

        node_properties = get_list(CONF.node_properties)
        icon_locators = get_list(CONF.icon_locators)
        include_predicates = get_list(CONF.include_predicates)
        exclude_predicates = get_list(CONF.exclude_predicates)
        include_types = get_list(CONF.include_types)
        exclude_types = get_list(CONF.exclude_types)

        type_styles = {}
        for style_node in graph.objects(c_node, CONF.type_styles):
            target = graph.value(style_node, CONF.target)
            if target:
                s_dict = {}
                color = graph.value(style_node, CONF.color)
                shape = graph.value(style_node, CONF.shape)
                priority = graph.value(style_node, CONF.priority)
                icon = graph.value(style_node, CONF.icon)  # NEU: Icon extrahieren

                if color: s_dict["color"] = str(color)
                if shape: s_dict["shape"] = str(shape)
                if priority: s_dict["priority"] = int(priority)
                if icon: s_dict["icon"] = str(icon)
                type_styles[str(target)] = s_dict

        edge_styles = {}
        for style_node in graph.objects(c_node, CONF.edge_styles):
            target = graph.value(style_node, CONF.target)
            if target:
                s_dict = {}
                color = graph.value(style_node, CONF.color)
                line_type = graph.value(style_node, CONF.line_type)
                target_arrow = graph.value(style_node, CONF.target_arrow)
                if color: s_dict["color"] = str(color)
                if line_type: s_dict["line_type"] = str(line_type)
                if target_arrow: s_dict["target_arrow"] = str(target_arrow)
                edge_styles[str(target)] = s_dict

        default_node_style = None
        dns_node = graph.value(c_node, CONF.default_node_style)
        if dns_node:
            default_node_style = {}
            for key in ["blank_nodes", "uri_nodes"]:
                key_node = graph.value(dns_node, CONF[key])
                if key_node:
                    s_dict = {}
                    color = graph.value(key_node, CONF.color)
                    shape = graph.value(key_node, CONF.shape)
                    if color: s_dict["color"] = str(color)
                    if shape: s_dict["shape"] = str(shape)
                    default_node_style[key] = s_dict

        base_dir_str = get_str(CONF.base_dir)
        base_dir = None
        if file_path:
            config_path = Path(file_path).resolve()
            base_dir = config_path.parent
            if base_dir_str:
                base_dir = (config_path.parent / base_dir_str).resolve()

                # NEU: Namespaces auslesen
        namespaces = {}
        for ns_node in graph.objects(c_node, CONF.namespace):
            prefix = graph.value(ns_node, CONF.prefix)
            uri = graph.value(ns_node, CONF.uri)
            if prefix and uri:
                namespaces[str(prefix)] = str(uri)

        return cls(
            node_properties=node_properties,
            icon_locators=icon_locators,
            type_styles=type_styles,
            edge_styles=edge_styles,
            type_as_edge=type_as_edge,
            icon_height=icon_height,
            preferred_language=preferred_language,
            base_dir=base_dir,
            include_predicates=include_predicates,
            exclude_predicates=exclude_predicates,
            include_types=include_types,
            exclude_types=exclude_types,
            group_type=group_type,
            group_contains=group_contains,
            namespaces=namespaces,  # NEU
            default_node_style=default_node_style
        )

    @classmethod
    def from_turtle(cls, file_path: str) -> 'ConverterConfig':
        g = Graph()
        g.parse(file_path, format="turtle")
        return cls.from_rdf(g, file_path=file_path)