import argparse
import sys
import logging
from pathlib import Path
from rdflib import Graph
from converter import RDFToYedConverter
from config import ConverterConfig

# Logger für dieses Modul initialisieren
logger = logging.getLogger(__name__)


def get_rdf_format(file_path):
    """Ermittelt das rdflib-Format anhand der Dateiendung."""
    suffix = Path(file_path).suffix.lower()
    format_map = {
        '.ttl': 'turtle',
        '.rdf': 'xml',
        '.owl': 'xml',
        '.xml': 'xml',
        '.nt': 'nt',
        '.n3': 'n3',
        '.jsonld': 'json-ld'
    }
    return format_map.get(suffix, 'turtle')


def main():
    # Logging Basis-Konfiguration (Format: LEVEL: Nachricht)
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )

    parser = argparse.ArgumentParser(
        description="Konvertiert und mergt RDF-Dateien in ein yEd-kompatibles GraphML-Format."
    )
    parser.add_argument("output_file", help="Pfad zur Ausgabe-GraphML-Datei (z.B. output.graphml)")
    parser.add_argument("config_file", help="Pfad zur JSON-Konfigurationsdatei (z.B. config.json)")
    parser.add_argument("input_files", nargs="+", help="Eine oder mehrere RDF-Eingabedateien (.ttl, .rdf, .nt, etc.)")

    args = parser.parse_args()

    logger.info("Lade und merge die RDF-Dateien...")
    merged_graph = Graph()

    for file_path in args.input_files:
        if not Path(file_path).exists():
            logger.error(f"Datei '{file_path}' nicht gefunden.")
            sys.exit(1)

        rdf_format = get_rdf_format(file_path)
        logger.info(f"Parse '{file_path}' als {rdf_format}...")

        try:
            merged_graph.parse(file_path, format=rdf_format)
        except Exception as e:
            logger.error(f"Fehler beim Parsen von '{file_path}': {e}")
            sys.exit(1)

    logger.info(f"Erfolgreich geladen: {len(merged_graph)} Triples insgesamt.")

    logger.info(f"Lade Konfiguration aus '{args.config_file}'...")
    try:
        config = ConverterConfig.from_json(args.config_file)
    except Exception as e:
        logger.error(f"Fehler beim Laden der Konfiguration: {e}")
        sys.exit(1)

    logger.info("Starte Konvertierung nach GraphML...")
    try:
        converter = RDFToYedConverter(config=config)
        converter.convert(merged_graph)
        converter.save(args.output_file)
        logger.info(f"Fertig! GraphML gespeichert unter: {args.output_file}")
    except Exception as e:
        logger.error(f"Fehler während der Konvertierung oder beim Speichern: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()