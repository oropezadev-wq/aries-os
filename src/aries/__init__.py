"""Aries OS: Sistema Operativo IA Personal.

Este paquete principal expone los metadatos básicos y los componentes centrales
que permiten inicializar el kernel del sistema.
"""

__version__ = "0.1.0"
__author__ = "Aries OS"
__license__ = "MIT"

from .core import Kernel
from .config import Settings

__all__ = ["__version__", "__author__", "__license__", "Kernel", "Settings"]
