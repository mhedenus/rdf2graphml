import argparse
import logging
import sys
from importlib import metadata
from pathlib import Path

from graffl.parser import GrafflParser
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
    try:
        __version__ = metadata.version("rdf2graphml")
    except metadata.PackageNotFoundError:
        __version__ = "unknown (not installed)"

    parser = argparse.ArgumentParser(
        description="Converts RDF files to the yEd GraphML format."
    )

    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Print the program version and exit."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--type_as_edge",
        action="store_true",
        required=False,
        help="Enable rendering rdf:type as edge"
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
        "-o", "--output",
        required=True,
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

        if args.type_as_edge:
            config.type_as_edge = True

        if args.model:
            model_graph = Graph()
            load_graph(model_graph, Path(args.model), logger)
            ConfigFromModel(config, model_graph).load_model()

        g = Graph()
        for input_file in args.inputs:
            load_graph(g, Path(input_file), logger)

        logger.debug(f"Starting conversion of {len(g)} triples...")
        converter = RDFToYedConverter(config)
        converter.convert(g)
        converter.save(args.output)

        logger.debug(f"Saved to: {args.output}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        logger.debug("Traceback:", exc_info=True)
        sys.exit(1)


def load_graph(g: Graph, path: Path, logger: logging.Logger):
    if not path.exists():
        logger.error(f"File not found: {path}")
        sys.exit(1)

    logger.debug(f"Reading {path}...")

    if path.suffix in [".graffl", ".txt"]:
        with open(path, 'r', encoding='utf-8') as f:
            data = f.read()
        g.parse(data=data, format="graffl", plugin_parsers={"graffl": GrafflParser})
    else:
        g.parse(str(path), format="turtle")


if __name__ == "__main__":
    main()
