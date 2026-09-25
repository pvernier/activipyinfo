"""The original object API, kept working while the new one is built.

``Database`` and ``Folder`` are replaced by :mod:`activipyinfo.models`
(``client.databases``); ``Form``, ``Field`` and ``Record`` will be replaced
in later phases (see docs/DEVELOPMENT_PLAN.md).
"""

from .database import Database
from .field import Field
from .folder import Folder
from .form import Form
from .manager import Manager
from .record import Record

__all__ = ["Database", "Field", "Folder", "Form", "Manager", "Record"]
