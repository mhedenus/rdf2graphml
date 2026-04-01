import json
import logging
import fnmatch
from rdflib import URIRef
from pathlib import Path

logger = logging.getLogger(__name__)


class ConverterConfig:
    def __init__(self, node_properties=None, icon_locators=None, type_styles=None,
                 icon_height=64, preferred_language="de", base_dir=None,
                 include_predicates=None, exclude_predicates=None,
                 include_types=None, exclude_types=None):

        self.node_properties = set(node_properties) if node_properties else set()
        self.icon_locators = set(icon_locators) if icon_locators else set()
        self.type_styles = type_styles if type_styles else {}
        self.icon_target_height = icon_height
        self.preferred_language = preferred_language
        self.image_base_dir = Path(base_dir) if base_dir else Path.cwd()

        self.include_predicates = include_predicates if include_predicates else []
        self.exclude_predicates = exclude_predicates if exclude_predicates else []

        # WICHTIG: Hier müssen die Typ-Listen gespeichert werden
        self.include_types = include_types if include_types else []
        self.exclude_types = exclude_types if exclude_types else []

    def _is_uri_allowed(self, uri, includes, excludes):
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

    def is_predicate_allowed(self, predicate_uri):
        return self._is_uri_allowed(predicate_uri, self.include_predicates, self.exclude_predicates)

    def is_type_allowed(self, type_uri):
        return self._is_uri_allowed(type_uri, self.include_types, self.exclude_types)

    @classmethod
    def from_json(cls, file_path):
        config_path = Path(file_path).resolve()
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        base_dir = config_path.parent
        if "base_dir" in data:
            base_dir = (config_path.parent / data["base_dir"]).resolve()

        return cls(
            node_properties={URIRef(u) for u in data.get("node_properties", [])},
            icon_locators={URIRef(u) for u in data.get("icon_locators", [])},
            type_styles={URIRef(k): v for k, v in data.get("type_styles", {}).items()},
            icon_height=data.get("icon_height", 64),
            preferred_language=data.get("preferred_language", "de"),
            base_dir=base_dir,
            include_predicates=data.get("include_predicates", []),
            exclude_predicates=data.get("exclude_predicates", []),
            # WICHTIG: Diese beiden Zeilen müssen existieren, sonst greift der Filter nie!
            include_types=data.get("include_types", []),
            exclude_types=data.get("exclude_types", [])
        )