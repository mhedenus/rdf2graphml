import json
import logging
from rdflib import URIRef
from pathlib import Path

logger = logging.getLogger(__name__)


class ConverterConfig:
    def __init__(self, entity_property_uris=None, icon_property_uris=None, type_styles=None,
                 icon_target_height=64, preferred_language="de", image_base_dir=None):
        self.entity_property_uris = set(entity_property_uris) if entity_property_uris else set()
        self.icon_property_uris = set(icon_property_uris) if icon_property_uris else set()
        self.type_styles = type_styles if type_styles else {}
        self.icon_target_height = icon_target_height
        self.preferred_language = preferred_language
        # NEU: Der Basis-Pfad für lokale Bilder
        self.image_base_dir = Path(image_base_dir) if image_base_dir else Path.cwd()

    @classmethod
    def from_json(cls, file_path):
        try:
            config_path = Path(file_path).resolve()
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # NEU: Berechne den Basis-Pfad.
            # Standardmäßig ist das der Ordner, in dem die config.json liegt.
            # Wenn der User in der JSON "image_base_dir": "pfad/zu/bildern" angibt,
            # wird dieser relativ zur config.json aufgelöst.
            base_dir = config_path.parent
            if "image_base_dir" in data:
                base_dir = (config_path.parent / data["image_base_dir"]).resolve()

            return cls(
                entity_property_uris={URIRef(u) for u in data.get("entity_property_uris", [])},
                icon_property_uris={URIRef(u) for u in data.get("icon_property_uris", [])},
                type_styles={URIRef(k): v for k, v in data.get("type_styles", {}).items()},
                icon_target_height=data.get("icon_target_height", 64),
                preferred_language=data.get("preferred_language", "de"),
                image_base_dir=base_dir  # Übergebe den berechneten Pfad
            )
        except Exception as e:
            logger.error(f"Fehler beim Laden der Konfigurationsdatei: {e}")
            raise