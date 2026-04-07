import logging
import re
from pathlib import Path

import owlrl
from rdflib import Graph, Namespace, OWL, RDFS, RDF

from .config import ConverterConfig
from .model import RDF2GRAPHML_NS_BASE

logger = logging.getLogger(__name__)

CONF = Namespace(RDF2GRAPHML_NS_BASE)


def camel_to_snake(name: str) -> str:
    """Converts camelCase to snake_case."""
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()


class ConfigFromModel:
    def __init__(
            self,
            config: ConverterConfig):
        self.config = config
        self.model = Graph()

    def load_model(self, model_path: Path):
        self.model.parse(str(model_path), format="turtle")

        # 1. Add base subsumptions to simplify queries
        self.model.add((OWL.ObjectProperty, RDFS.subClassOf, RDF.Property))
        self.model.add((OWL.DatatypeProperty, RDFS.subClassOf, RDF.Property))
        self.model.add((OWL.Class, RDFS.subClassOf, RDFS.Class))

        # Run reasoner
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(self.model)

        # 2. Extract global settings from owl:Ontology
        # We do this FIRST because preferredLanguage affects label resolution later
        ontology_node = next(self.model.subjects(RDF.type, OWL.Ontology), None)
        if ontology_node:
            for p, o in self.model.predicate_objects(subject=ontology_node):
                if str(p).startswith(RDF2GRAPHML_NS_BASE):
                    attr_name = camel_to_snake(str(p).replace(RDF2GRAPHML_NS_BASE, ""))

                    # Update global config attributes with proper type conversion
                    if attr_name == "preferred_language":
                        self.config.preferred_language = str(o)
                    elif attr_name == "icon_height":
                        try:
                            self.config.icon_height = int(o)
                        except ValueError:
                            logger.warning(f"Invalid iconHeight value for ontology: {o}")
                    elif attr_name == "type_as_edge":
                        self.config.type_as_edge = (str(o).lower() == "true")

                    logger.debug(f"Global setting updated from model: {attr_name} = {o}")

        # 3. Extract structural configurations (Roles / Classes)

        # Node Properties (rendered as node attributes, not edges)
        for prop in self.model.subjects(RDF.type, CONF.NodeProperty):
            self.config.node_properties.add(prop)
            logger.debug(f"Added node property from model: {prop}")

        # Icon Locators (properties pointing to image URLs/paths)
        for prop in self.model.subjects(RDF.type, CONF.IconLocatorProperty):
            self.config.icon_locators.add(prop)
            logger.debug(f"Added icon locator from model: {prop}")

        # Group Type (classes that should be rendered as yEd groups)
        for cls in self.model.subjects(RDF.type, CONF.GroupClass):
            self.config.group_type = cls
            logger.debug(f"Set group type from model: {cls}")

        # Group Contains Property (property defining the parent-child relationship)
        for prop in self.model.subjects(RDF.type, CONF.GroupContainsProperty):
            self.config.group_contains = prop
            logger.debug(f"Set group contains property from model: {prop}")

        # Ignored Properties (will be completely excluded from the graph)
        for prop in self.model.subjects(RDF.type, CONF.IgnoredProperty):
            self.config.exclude_predicates.append(str(prop))
            logger.debug(f"Added ignored property from model: {prop}")

        # Ignored Classes (instances of these classes will be excluded)
        for cls in self.model.subjects(RDF.type, CONF.IgnoredClass):
            self.config.exclude_types.append(str(cls))
            logger.debug(f"Added ignored class from model: {cls}")

        # 4. Extract visual styles and labels (Values / Properties)

        # --- Extract type styles (nodes) ---
        for node_class in self.model.subjects(RDF.type, RDFS.Class):
            style_dict = {}
            for p, o in self.model.predicate_objects(subject=node_class):
                if str(p).startswith(RDF2GRAPHML_NS_BASE):
                    # Extract attribute name and convert from camelCase to snake_case
                    attr_name_camel = str(p).replace(RDF2GRAPHML_NS_BASE, "")
                    attr_name = camel_to_snake(attr_name_camel)

                    if attr_name == "priority":
                        try:
                            style_dict[attr_name] = int(o)
                        except ValueError:
                            logger.warning(f"Could not convert priority for {node_class} to int: {o}")
                    else:
                        style_dict[attr_name] = str(o)

            if style_dict:
                if node_class not in self.config.type_styles:
                    self.config.type_styles[node_class] = {}
                self.config.type_styles[node_class].update(style_dict)
                logger.debug(f"Loaded type style from model for {node_class}: {style_dict}")

        # --- Extract edge styles (properties) ---
        for edge_prop in self.model.subjects(RDF.type, RDF.Property):
            style_dict = {}
            labels_raw = []

            for p, o in self.model.predicate_objects(subject=edge_prop):
                if str(p).startswith(RDF2GRAPHML_NS_BASE):
                    # Extract attribute name and convert from camelCase to snake_case
                    attr_name_camel = str(p).replace(RDF2GRAPHML_NS_BASE, "")
                    attr_name = camel_to_snake(attr_name_camel)
                    style_dict[attr_name] = str(o)

                # Collect rdfs:label for edges
                elif p == RDFS.label:
                    lang = getattr(o, 'language', None)
                    labels_raw.append((str(o), lang))

            # Resolve the best label based on preferred_language
            if labels_raw:
                pref_lang = self.config.preferred_language
                pref_labels = [text for text, lang in labels_raw if lang == pref_lang]

                if pref_labels:
                    style_dict["label"] = sorted(pref_labels)[0]
                else:
                    no_lang_labels = [text for text, lang in labels_raw if not lang]
                    if no_lang_labels:
                        style_dict["label"] = sorted(no_lang_labels)[0]
                    else:
                        style_dict["label"] = sorted([text for text, lang in labels_raw])[0]

            if style_dict:
                if edge_prop not in self.config.edge_styles:
                    self.config.edge_styles[edge_prop] = {}
                self.config.edge_styles[edge_prop].update(style_dict)
                logger.debug(f"Loaded edge style from model for {edge_prop}: {style_dict}")