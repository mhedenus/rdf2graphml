import pytest
from pathlib import Path
from rdflib import Graph

from rdf2graphml.config import ConverterConfig
from rdf2graphml.converter import RDFToYedConverter

# Wir ermitteln dynamisch den Pfad zum 'testdata'-Ordner relativ zu dieser Testdatei
TEST_DATA_DIR = Path(__file__).parent / "testdata"


def get_test_pairs():
    """
    Sucht im 'testdata'-Ordner nach allen .ttl Dateien und prüft,
    ob es eine namensgleiche .json Datei gibt.
    Gibt eine Liste von Tuplen zurück: [(Pfad_zur_ttl, Pfad_zur_json), ...]
    """
    if not TEST_DATA_DIR.exists():
        return []

    test_pairs = []
    # Suche alle .ttl Dateien
    for ttl_file in TEST_DATA_DIR.glob("*.ttl"):
        # Ersetze die Endung .ttl durch .json
        json_file = ttl_file.with_suffix(".json")

        # Nur hinzufügen, wenn die passende Config auch existiert
        if json_file.exists():
            test_pairs.append((ttl_file, json_file))

    return test_pairs


# parametrize nimmt unsere Liste und führt die Test-Funktion für jedes Tupel einmal aus.
# ids=... sorgt dafür, dass die Tests in PyCharm schöne Namen bekommen (z.B. "test_batch[test1]")
@pytest.mark.parametrize(
    "ttl_file, json_file",
    get_test_pairs(),
    ids=lambda path: path.stem if isinstance(path, Path) else ""
)
def test_batch_conversion(ttl_file: Path, json_file: Path):
    """
    Dieser Test wird für jedes gefundene Datei-Paar in 'testdata' einmal ausgeführt.
    """
    # 1. Target-Verzeichnis vorbereiten
    target_dir = Path("target")
    target_dir.mkdir(exist_ok=True)

    # Dateinamen für das Output generieren (z.B. test1.graphml)
    output_file = target_dir / f"{ttl_file.stem}.graphml"

    # Alte Datei löschen, falls vorhanden
    if output_file.exists():
        output_file.unlink()

    # 2. Config und Graphen laden
    config = ConverterConfig.from_json(str(json_file))

    g = Graph()
    g.parse(str(ttl_file), format="turtle")

    # 3. Konvertieren und speichern
    converter = RDFToYedConverter(config)
    converter.convert(g)
    converter.save(str(output_file))

    # 4. Assertions (Überprüfen, ob es geklappt hat)
    assert output_file.exists(), f"Die Datei {output_file.name} wurde nicht erstellt!"
    assert output_file.stat().st_size > 0, f"Die Datei {output_file.name} ist leer!"

    # Optionaler Inhalts-Check
    content = output_file.read_text(encoding="utf-8")
    assert "graphml" in content, "Das GraphML-Wurzelelement fehlt."