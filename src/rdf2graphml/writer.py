from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

from .ir_model import GraphModel
from .config import ConverterConfig


class GraphWriter(ABC):
    """Abstrakte Basisklasse für alle Graphen-Exporter."""

    def __init__(self, config: ConverterConfig):
        # Der Writer braucht ggf. noch Zugriff auf globale Einstellungen
        # wie Base-Verzeichnisse oder Icon-Größen.
        self.config = config

    @abstractmethod
    def write(self, graph: GraphModel, filepath: Union[str, Path]) -> None:
        """
        Nimmt das fertig aufgebaute, agnostische GraphModel und exportiert es
        in das zielspezifische Dateiformat (z.B. XML).

        :param graph: Das agnostische Zwischenmodell.
        :param filepath: Der Pfad zur Ausgabedatei.
        """
        pass