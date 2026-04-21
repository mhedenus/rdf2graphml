import fnmatch
import json
import logging
from pathlib import Path
from typing import Set, List, Dict, Optional, Any

from rdflib import URIRef
from .model import RDF2GRAPHML_ICON

logger = logging.getLogger(__name__)


class ConverterConfig:
    def __init__(self, **kwargs) -> None:
        """
        Initialisiert die Konfiguration.
        Lädt zuerst die 'default-config.json' und überschreibt diese
        mit den übergebenen Argumenten (**kwargs).
        """
        # 1. Defaults laden
        default_path = Path(__file__).parent / "default-config.json"
        with open(default_path, 'r', encoding='utf-8') as f:
            self._raw_data = json.load(f)

        # 2. Standard-Verzeichnis setzen
        self.image_base_dir: Path = Path.cwd()

        # 3. Mit übergebenen Argumenten aktualisieren
        if kwargs:
            self.update(**kwargs)
        else:
            self._apply_config()

    def update(self, **kwargs) -> None:
        """
        Aktualisiert die Konfiguration programmatisch.
        Beispiel: config.update(type_as_edge=True, icon_height=128)
        """
        # Falls ein Pfad für base_dir übergeben wurde, diesen separat behandeln
        if "base_dir" in kwargs:
            self.image_base_dir = Path(kwargs.pop("base_dir")).resolve()

        # Deep Merge für Dicts (z.B. type_styles), sonst einfaches Überschreiben
        for key, value in kwargs.items():
            if isinstance(value, dict) and key in self._raw_data and isinstance(self._raw_data[key], dict):
                self._raw_data[key].update(value)
            else:
                self._raw_data[key] = value

        self._apply_config()

    def _apply_config(self) -> None:
        """
        Interne Methode: Überträgt die Rohdaten (Dict) in die typisierten
        Instanzattribute (alphabetisch sortiert).
        """
        d = self._raw_data

        self.default_node_style: Dict[str, Dict[str, str]] = d.get("default_node_style", {})

        self.edge_styles: Dict[URIRef, Dict[str, Any]] = {
            URIRef(k): v for k, v in d.get("edge_styles", {}).items()
        }

        self.exclude_predicates: List[str] = d.get("exclude_predicates", [])
        self.exclude_types: List[str] = d.get("exclude_types", [])

        self.group_contains = URIRef(d["group_contains"]) if d.get("group_contains") else None
        self.group_type = URIRef(d["group_type"]) if d.get("group_type") else None

        self.icon_height: int = d.get("icon_height", 64)

        locators = d.get("icon_locators") or [RDF2GRAPHML_ICON]
        self.icon_locators: Set[URIRef] = {URIRef(u) for u in locators}

        self.include_predicates: List[str] = d.get("include_predicates", [])
        self.include_types: List[str] = d.get("include_types", [])

        self.namespaces: Dict[str, str] = d.get("namespaces", {})

        self.node_properties: Set[URIRef] = {
            URIRef(u) for u in d.get("node_properties", [])
        }

        self.preferred_language: str = d.get("preferred_language", "de")
        self.type_as_edge: bool = d.get("type_as_edge", False)

        self.type_styles: Dict[URIRef, Dict[str, Any]] = {
            URIRef(k): v for k, v in d.get("type_styles", {}).items()
        }

    @classmethod
    def from_json(cls, file_path: str) -> 'ConverterConfig':
        """Lädt Konfiguration aus einer JSON-Datei."""
        path = Path(file_path).resolve()
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Falls base_dir nicht in JSON steht, ist es relativ zur JSON-Datei
        if "base_dir" in data:
            data["base_dir"] = (path.parent / data["base_dir"]).resolve()
        else:
            data["base_dir"] = path.parent

        return cls(**data)

    def is_predicate_allowed(self, predicate_uri: URIRef) -> bool:
        return self._is_uri_allowed(predicate_uri, self.include_predicates, self.exclude_predicates)

    def is_type_allowed(self, type_uri: URIRef) -> bool:
        return self._is_uri_allowed(type_uri, self.include_types, self.exclude_types)

    def _is_uri_allowed(self, uri: URIRef, includes: List[str], excludes: List[str]) -> bool:
        uri_str = str(uri)
        for pattern in excludes:
            if fnmatch.fnmatch(uri_str, pattern): return False
        return True if not includes else any(fnmatch.fnmatch(uri_str, p) for p in includes)