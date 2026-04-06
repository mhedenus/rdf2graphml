from rdflib import URIRef
from rdf2graphml.config import ConverterConfig


def test_predicate_filtering():
    """Testet die include/exclude Logik für Predicates mit Wildcards."""
    # Konfiguration: Alles zulassen, was "allow" enthält, aber "secret" blockieren
    config = ConverterConfig(
        include_predicates=["*allow*"],
        exclude_predicates=["*secret*"]
    )

    uri_allowed = URIRef("http://example.org/allow_this_property")
    uri_secret = URIRef("http://example.org/allow_but_is_secret")
    uri_other = URIRef("http://example.org/something_else")

    # Sollte erlaubt sein (Matcht include, nicht exclude)
    assert config.is_predicate_allowed(uri_allowed) is True

    # Sollte blockiert werden (Matcht zwar include, aber exclude hat Vorrang)
    assert config.is_predicate_allowed(uri_secret) is False

    # Sollte blockiert werden (Matcht nicht das include pattern)
    assert config.is_predicate_allowed(uri_other) is False