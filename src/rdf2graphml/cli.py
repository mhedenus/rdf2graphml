import argparse
import logging
import sys
from pathlib import Path

from rdflib import Graph

from .config import ConverterConfig
from .converter import RDFToYedConverter
from .model_loader import ConfigFromModel


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
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "-c", "--config",
        required=False,
        help="Path to the configuration file (.json)"
    )
    parser.add_argument(
        "-m", "--model",
        required=False,
        help="Path to a model, schema or ontology file (.ttl)"
    )
    parser.add_argument(
        "output",
        help="Path to the output file (e.g. output.graphml)"
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more RDF files to read"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:

        if args.config:
            config_path = Path(args.config)
            if not config_path.exists():
                logger.error(f"Config file not found: {config_path}")
                sys.exit(1)
            logger.debug(f"Loading configuration as JSON: {config_path}")
            config = ConverterConfig.from_json(str(config_path))
        else:
            config = ConverterConfig()

        if args.model:
            model_path = Path(args.model)
            if not model_path.exists():
                logger.error(f"Model file not found: {model_path}")
                sys.exit(1)
            logger.debug(f"Loading model: {model_path}")
            ConfigFromModel(config).load_model(model_path)


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