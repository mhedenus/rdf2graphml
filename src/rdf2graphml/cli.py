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
        description="Converts RDF files to the yEd GraphML format."
    )

    parser.add_argument(
        "output",
        help="Path to the output file (e.g., output.graphml)"
    )
    parser.add_argument(
        "-c", "--config",
        required=True,
        help="Path to the JSON configuration file"
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more RDF files (TTL, XML, etc.) to read"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # 1. Load configuration
        config = ConverterConfig.from_json(args.config)

        # 2. Build RDF graph
        g = Graph()
        for input_file in args.inputs:
            path = Path(input_file)
            if not path.exists():
                logger.error(f"Input file not found: {path}")
                sys.exit(1)

            logger.debug(f"Reading {path}...")
            # Guess format from suffix, fallback to turtle
            fmt = "xml" if path.suffix in [".rdf", ".owl"] else "turtle"
            g.parse(str(path), format=fmt)

        # 3. Convert and save
        logger.debug(f"Starting conversion of {len(g)} triples...")
        converter = RDFToYedConverter(config)
        converter.convert(g)
        converter.save(args.output)

        logger.debug(f"Saved to: {args.output}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()