from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Union

from dissect.target.exceptions import ContainerError
from dissect.target.helpers.lazy import import_lazy
from dissect.target.helpers.utils import readinto

if TYPE_CHECKING:
    from dissect.target.volume import VolumeSystem

raw = import_lazy("dissect.target.containers.raw")
"""A lazy import of :mod:`dissect.target.containers.raw`"""
ewf = import_lazy("dissect.target.containers.ewf")
"""A lazy import of :mod:`dissect.target.containers.ewf`"""
vmdk = import_lazy("dissect.target.containers.vmdk")
"""A lazy import of :mod:`dissect.target.containers.vmdk`"""
vhdx = import_lazy("dissect.target.containers.vhdx")
"""A lazy import of :mod:`dissect.target.containers.vhdx`"""
vhd = import_lazy("dissect.target.containers.vhd")
"""A lazy import of :mod:`dissect.target.containers.vhd`"""
qcow2 = import_lazy("dissect.target.containers.qcow2")
"""A lazy import of :mod:`dissect.target.containers.qcow2`"""
split = import_lazy("dissect.target.containers.split")
"""A lazy import of :mod:`dissect.target.containers.split`"""
vdi = import_lazy("dissect.target.containers.vdi")
"""A lazy import of :mod:`dissect.target.containers.vdi`"""

log = logging.getLogger(__name__)


class Container(io.IOBase):
    """Base class that acts as a file-like object wrapper around anything that can behave like a "raw disk".

    Containers are anything from raw disk images and virtual disks, to evidence containers and made-up binary formats.
    Consumers of the ``Container`` class only need to implement ``seek``, ``tell`` and ``read``.
    Override ``__init__`` for any opening that you may need to do, but don't forget to initialize the super class.

    Args:
        fh: The source file-like object of the container or a ``Path`` object to the file.
        size: The size of the container.
        vs: An optional shorthand to set the underlying volume system, usually set later.
    """

    def __init__(self, fh: Union[BinaryIO, Path], size: int, vs: VolumeSystem = None):
        self.fh = fh
        self.size = size

        # Shorthand access to vs
        self.vs = vs

    def __repr__(self):
        return f"<{self.__class__.__name__} size={self.size} vs={self.vs}>"

    @classmethod
    def detect(cls, item: Union[list, BinaryIO, Path]) -> bool:
        """Detect if this ``Container`` can handle this file format.

        Args:
            item: The object we want to see if it can be handled by this ``Container``.

        Returns:
            ``True`` if this ``Container`` can be used, ``False`` otherwise.
        """
        i = item[0] if isinstance(item, list) else item
        if hasattr(i, "read"):
            return cls.detect_fh(i, item)
        else:
            return cls.detect_path(i, item)

    @staticmethod
    def detect_fh(fh: BinaryIO, original: Union[list, BinaryIO]) -> bool:
        """Detect if this ``Container`` can be used to open the file-like object ``fh``.

        The function checks wether the raw data contains any magic information that corresponds to this
        specific container.

        Args:
            fh: A file-like object that we want to open a ``Container`` on.
            original: The original argument passed to ``detect()``.

        Returns:
            ``True`` if this ``Container`` can be used for this file-like object, ``False`` otherwise.
        """
        raise NotImplementedError()

    @staticmethod
    def detect_path(path: Path, original: Union[list, Path]) -> bool:
        """Detect if this ``Container`` can be used to open ``path``.

        The function checks wether file inside ``path`` is formatted in such a way that
        this ``Container`` can be used to read it. For example, it validates against the
        file extension.

        Args:
            path: A location to a file.
            original: The original argument passed to ``detect()``.

        Returns:
            ``True`` if this ``Container`` can be used for this path, ``False`` otherwise.
        """
        raise NotImplementedError()

    def read(self, length: int) -> bytes:
        """Read a ``length`` of bytes from this ``Container``."""
        raise NotImplementedError()

    def readinto(self, b: bytearray) -> int:
        """Uses :func:`dissect.target.helpers.utils.readinto`."""
        return readinto(buffer=b, fh=self)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        """Change the stream position to ``offset``.

        ``whence`` determines where to seek from:

        * ``io.SEEK_SET`` (``0``):: absolute offset in the stream.
        * ``io.SEEK_CUR`` (``1``):: current position in the stream.
        * ``io.SEEK_END`` (``2``):: end of stream.

        Args:
            offset: The offset relative to the position indicated by ``whence``.
            whence: Where to start the seek from.
        """
        raise NotImplementedError()

    def seekable(self) -> bool:
        """Returns whether ``seek`` can be used by this ``Container``. Always ``True``."""
        return True

    def tell(self) -> int:
        """Returns the current seek position of the ``Container``."""
        raise NotImplementedError()

    def close(self) -> None:
        """Close the container.

        Override this if you need to clean-up anything.
        """
        raise NotImplementedError()


def open(item: Union[list, str, BinaryIO, Path], *args, **kwargs):
    """Open a :class:`Container` from the given object.

    All currently supported containers are checked to find a compatible one.
    :class:`RawContainer <dissect.target.containers.raw.RawContainer>` must always be checked last
    since it always succeeds!

    Args:
        item: The object we want to open a :class`Container` from.

    Raises:
        ContainerError: When a compatible :class`Container` was found but it failed to open.
        ContainerError: When no compatible :class`Container` implementations were found.
    """
    containers = [
        ewf.EwfContainer,
        vmdk.VmdkContainer,
        vhdx.VhdxContainer,
        vhd.VhdContainer,
        qcow2.QCow2Container,
        vdi.VdiContainer,
        split.SplitContainer,
        raw.RawContainer,
    ]
    if isinstance(item, list):
        item = [Path(entry) if isinstance(entry, str) else entry for entry in item]
    elif isinstance(item, str):
        item = Path(item)

    for container in containers:
        try:
            if container.detect(item):
                return container(item, *args, **kwargs)
        except ImportError as e:
            log.warning("Failed to import %s", container, exc_info=e)
        except Exception as e:
            raise ContainerError(f"Failed to open container {item}", cause=e)

    raise ContainerError(f"Failed to detect container for {item}")