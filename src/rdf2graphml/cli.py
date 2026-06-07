import argparse
import logging
import sys
from importlib import metadata
from pathlib import Path

from graffl.parser import parse
from rdflib import Graph, Dataset
from rdflib.util import guess_format

from .config import ConverterConfig
from .converter import RDFToGraphModelConverter
from .model_loader import ConfigFromModel

# Import der neuen Writer-Klassen
from .graphml_writer import GraphMLWriter
from .drawio_writer import DrawIOWriter


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
        description="Converts RDF files to GraphML (yEd) or Draw.io XML format."
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
    # NEU: Das Format-Argument
    parser.add_argument(
        "-f", "--format",
        choices=["graphml", "drawio"],
        default="graphml",
        help="Output format: 'graphml' (yEd) or 'drawio' (default: graphml)"
    )
    parser.add_argument(
        "--base_dir",
        required=False,
        help="Base dir for resolving relative resource paths"
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
        help="Path to the output file (e.g. output.graphml or output.drawio)"
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="The RDF files to read"
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

        if args.base_dir:
            config.base_dir = Path(args.base_dir)

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

        # 1. Konverter erzeugt NUR NOCH das Intermediate Representation (IR) Modell
        converter = RDFToGraphModelConverter(config)
        converter.convert(data_graph)

        if not converter.graph_model:
            logger.error("Konvertierung fehlgeschlagen: Es wurde kein Graph-Modell erzeugt.")
            sys.exit(1)

        # 2. Den passenden Writer anhand des CLI-Arguments wählen
        if args.format == "drawio":
            writer = DrawIOWriter(config)
            logger.debug("Nutze DrawIOWriter für die Ausgabe.")
        else:
            writer = GraphMLWriter(config)
            logger.debug("Nutze GraphMLWriter für die Ausgabe.")

        # 3. Das fertig aufgebaute IR-Modell übergeben und in Datei speichern
        writer.write(converter.graph_model, args.output)

        logger.info(f"Erfolgreich gespeichert unter: {args.output} (Format: {args.format})")

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