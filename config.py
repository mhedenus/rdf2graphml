import json
import logging
from rdflib import URIRef

logger = logging.getLogger(__name__)


class ConverterConfig:
    def __init__(self, entity_property_uris=None, icon_property_uris=None, type_styles=None,
                 icon_target_height=64, preferred_language="de"):
        self.entity_property_uris = set(entity_property_uris) if entity_property_uris else set()
        self.icon_property_uris = set(icon_property_uris) if icon_property_uris else set()
        self.type_styles = type_styles if type_styles else {}
        self.icon_target_height = icon_target_height
        self.preferred_language = preferred_language  # NEU

    @classmethod
    def from_json(cls, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return cls(
                entity_property_uris={URIRef(u) for u in data.get("entity_property_uris", [])},
                icon_property_uris={URIRef(u) for u in data.get("icon_property_uris", [])},
                type_styles={URIRef(k): v for k, v in data.get("type_styles", {}).items()},
                icon_target_height=data.get("icon_target_height", 64),
                preferred_language=data.get("preferred_language", "de")  # NEU (Standard: "de")
            )
        except Exception as e:
            logger.error(f"Fehler beim Laden der Konfigurationsdatei: {e}")
            raise