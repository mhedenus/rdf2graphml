import time
import pytest
from pathlib import Path
from rdflib import Graph, URIRef, Namespace, Literal
from rdflib.namespace import RDF, RDFS

from rdf2graphml.config import ConverterConfig
from rdf2graphml.converter import RDFToYedConverter

EX = Namespace("http://example.org/collatz/")


def generate_collatz_graph(max_start_number: int) -> Graph:
    """
    Generiert einen RDF-Graphen basierend auf den Collatz-Sequenzen
    für alle Zahlen von 1 bis max_start_number.
    """
    g = Graph()
    g.bind("ex", EX)

    processed = set()

    for n in range(1, max_start_number + 1):
        current = n
        while current != 1 and current not in processed:
            processed.add(current)

            # Collatz-Regel anwenden
            if current % 2 == 0:
                next_val = current // 2
            else:
                next_val = 3 * current + 1

            # RDF Knoten erstellen
            subject_node = EX[f"Node_{current}"]
            object_node = EX[f"Node_{next_val}"]

            # Triples hinzufügen
            g.add((subject_node, EX.next, object_node))
            g.add((subject_node, RDF.type, EX.Number))
            g.add((subject_node, RDFS.label, Literal(str(current))))

            current = next_val

    # Den Zielknoten "1" abschließend noch benennen und typisieren
    g.add((EX["Node_1"], RDF.type, EX.Number))
    g.add((EX["Node_1"], RDFS.label, Literal("1")))

    return g


# Wir überspringen diesen Test im normalen CI-Lauf, damit er die
# schnelle Feedback-Schleife nicht blockiert.
# (Zum manuellen Ausführen den Kommentar in der nächsten Zeile entfernen oder pytest -m umstellen)
#@pytest.mark.skip(reason="Belastungstest - läuft zu lange für reguläre CI-Durchläufe")
def test_collatz_load():
    """
    Belastungstest mit einem großen Graphen.
    """
    N = 1000  # Erzeugt je nach N zehntausende bis hunderttausende Triples

    print(f"\n--- BELASTUNGSTEST: COLLATZ N={N} ---")

    # 1. Graphen erzeugen
    start_time = time.time()
    g = generate_collatz_graph(N)
    gen_time = time.time() - start_time
    print(f"Graph generiert in {gen_time:.3f} Sekunden. (Größe: {len(g)} Triples)")

    # 2. Konfiguration
    config = ConverterConfig(
        namespaces={"ex": str(EX)},
        include_predicates=["*"],
        type_as_edge=False,
        default_node_style={
            "uri_nodes": {"color": "#FFA500", "shape": "ellipse"}
        }
    )
    converter = RDFToYedConverter(config)

    # 3. Konvertierung
    print("Starte Konvertierung nach GraphML...")
    start_time = time.time()
    converter.convert(g)
    conv_time = time.time() - start_time
    print(f"Konvertierung abgeschlossen in {conv_time:.3f} Sekunden.")

    # 4. Speichern
    target_dir = Path("target")
    target_dir.mkdir(exist_ok=True)
    output_file = target_dir / f"collatz_load_{N}.graphml"

    start_time = time.time()
    converter.save(str(output_file))
    save_time = time.time() - start_time

    mb_size = output_file.stat().st_size / (1024 * 1024)
    print(f"Datei gespeichert in {save_time:.3f} Sekunden. (Dateigröße: {mb_size:.2f} MB)")
    print("---------------------------------------")

    assert output_file.exists()
    assert output_file.stat().st_size > 0