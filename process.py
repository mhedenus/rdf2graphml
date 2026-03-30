
import sys
from pathlib import Path


from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF


if __name__ == "__main__":

    print(sys.argv)


#    fileIn = Path("test1.json").resolve()
#    fileOut = fileIn.with_suffix(".ttl")
#    graph = Graph()
#    graph.parse(fileIn, format="json-ld")
#    graph.serialize(fileOut, format="turtle")

