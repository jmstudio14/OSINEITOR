"""Capa no visual de la aplicación de escritorio de OSINEITOR.

Todo aquí es Python puro (sin Qt) para poder probarlo sin pantalla. Las vistas viven en
`osineitor_gui.ui` y solo presentan lo que esta capa calcula. La aplicación habla con la CLI por
el contrato de docs/CLI_CONTRACT.md: del motor importa únicamente `detect_type` y `__version__`.
"""

from osineitor import __version__

__all__ = ["__version__"]
