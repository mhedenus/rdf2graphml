import argparse
import logging
import sys
from rdflib import Graph
from pathlib import Path

from .config import ConverterConfig
from .converter import RDFToYedConverter


def setup_logging(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s'
    )


def main():
    parser = argparse.ArgumentParser(
        description="Konvertiert RDF-Dateien deterministisch in das yEd GraphML-Format."
    )

    parser.add_argument(
        "output",
        help="Pfad zur Ausgabe-Datei (z.B. output.graphml)"
    )
    parser.add_argument(
        "-c", "--config",
        required=True,
        help="Pfad zur JSON-Konfigurationsdatei"
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Eine oder mehrere RDF-Dateien (TTL, XML, etc.) zum Einlesen"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Aktiviert detailliertes Logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # 1. Konfiguration laden
        config = ConverterConfig.from_json(args.config)

        # 2. RDF-Graph aufbauen
        g = Graph()
        for input_file in args.inputs:
            path = Path(input_file)
            if not path.exists():
                logger.error(f"Eingabedatei nicht gefunden: {path}")
                sys.exit(1)

            logger.info(f"Lese {path} ein...")
            # Format anhand der Endung raten, Fallback auf turtle
            fmt = "xml" if path.suffix in [".rdf", ".owl"] else "turtle"
            g.parse(str(path), format=fmt)

        # 3. Konvertieren und speichern
        logger.info(f"Starte Konvertierung von {len(g)} Tripeln...")
        converter = RDFToYedConverter(config)
        converter.convert(g)
        converter.save(args.output)

        logger.info(f"Erfolgreich gespeichert unter: {args.output}")

    except Exception as e:
        logger.error(f"Ein Fehler ist aufgetreten: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()