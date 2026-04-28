import argparse
import logging
import sys
from importlib import metadata
from pathlib import Path

from graffl.parser import parse
from rdflib import Graph, Dataset
from rdflib.util import guess_format

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
        "-m", "--model",
        required=False,
        help="Path to a model, schema or ontology file (.ttl)"
    )
    parser.add_argument(
        "-c", "--config",
        required=False,
        help="Path to the configuration file (.json)"
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

        if args.model:
            model_graph = Dataset()
            load_graph(model_graph, Path(args.model), logger)
            ConfigFromModel(config, model_graph).load_model()

        if args.type_as_edge:
            config.type_as_edge = True

        data_graph = Dataset()
        for input_file in args.inputs:
            load_graph(data_graph, Path(input_file), logger)

        logger.debug(f"Starting conversion of {len(data_graph)} triples...")
        converter = RDFToYedConverter(config)
        converter.convert(data_graph)
        converter.save(args.output)

        logger.debug(f"Saved to: {args.output}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        logger.debug("Traceback:", exc_info=True)
        sys.exit(1)


_EXTRA_SUFFIX_MAP = {
    ".jsonld": "json-ld",
}

def load_graph(rdf_graph: Dataset, path: Path, logger: logging.Logger, fmt: str = None) -> None:
    if not path.exists():
        logger.error(f"File not found: {path}")
        sys.exit(1)

    logger.debug(f"Reading {path}...")

    if path.suffix == ".graffl":
        parse(path, rdf_graph)
        return

    if fmt:
        logger.debug(f"Using explicitly specified format: {fmt}")
        rdf_graph.parse(str(path), format=fmt)
        return

    detected = guess_format(str(path)) or _EXTRA_SUFFIX_MAP.get(path.suffix.lower())

    if detected:
        logger.debug(f"Auto-detected format '{detected}' for {path.name}")
        rdf_graph.parse(str(path), format=detected)
    else:
        logger.error(
            f"Could not determine RDF format for '{path.name}'. "
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
