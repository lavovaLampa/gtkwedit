from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final, Generic, Optional, TypeAlias, TypedDict, TypeVar

from typing_extensions import NotRequired, Unpack
from vcd.gtkw import GTKWColor as Color, GTKWFlag, GTKWSave

T = TypeVar("T", bound="Trace | NestedTrace")


class DataFmt(Enum):
    """Trace display data format"""
    HEX = "hex"
    DEC = "dec"
    BIN = "bin"
    OCT = "oct"
    ASCII = "ascii"
    REAL = "real"
    SIGNED = "signed"


class RootStyle(TypedDict):
    """Root/top trace style (must specify data format and right justification state)"""
    color: NotRequired[Optional[Color]]
    """Trace color"""
    datafmt: DataFmt
    """Trace data format"""
    rjustify: bool
    """Right justify displayed trace data?"""
    extraflags: NotRequired[Optional[GTKWFlag]]
    """Extra flags (can be ORed)"""


class Style(TypedDict, total=False):
    """Trace style"""
    color: Optional[Color]
    """Trace color"""
    datafmt: DataFmt
    """Trace data format"""
    rjustify: bool
    """Right justify displayed trace data?"""
    extraflags: Optional[GTKWFlag]
    """Extra flags (can be ORed)"""


@dataclass(frozen=True)
class Styled(Generic[T]):
    """Childrent inherit specified style"""
    children: Sequence[T] | T
    """Sequence of childrent that will inherit specified style"""
    style: Style
    """Trace style"""


@dataclass(frozen=True)
class Signal:
    """Signal trace"""
    name: str
    """Signal name"""
    alias: Optional[str] = None
    """Display alias (if any)"""
    highlight: bool = False
    """Highlight signal by default?"""
    style: Optional[Style] = None
    """Signal style"""
    translate_filter_file: Optional[str] = None
    """Translate filter file to use (if any)"""
    translate_filter_process: Optional[str] = None
    """Translate filter process to use (if any)"""


@dataclass(frozen=True)
class Submodule(Generic[T]):
    name: str
    children: Sequence[T] | T
    style: Optional[Style] = None


@dataclass(frozen=True)
class Group:
    """Trace group"""
    name: str
    """Group name"""
    # Groups cannot be nested
    children: "Sequence[NestedTrace] | NestedTrace"
    """Group children (groups cannot be nested)"""
    closed: bool = False
    """Closed group by default?"""
    highlight: bool = False
    """Higlight group by default?"""
    style: Optional[Style] = None
    """Group trace style"""


@dataclass(frozen=True)
class Blank:
    """Blank trace"""
    analog_extend: bool = False
    """Analog extend previous defined trace?"""
    highlight: bool = False
    """Highlight blank by default?"""


@dataclass(frozen=True)
class Comment:
    """Comment trace"""
    comment: str
    """Comment string"""
    analog_extend: bool = False
    """Analog extend previous defined trace?"""
    highlight: bool = False
    """Highlight blank by default?"""


NestedTrace: TypeAlias = (
    str | Signal | Submodule["NestedTrace"] | Comment | Blank | Styled["NestedTrace"]
)
Trace: TypeAlias = (
    str | Signal | Submodule["Trace"] | Group | Comment | Blank | Styled["Trace"]
)
AnyTrace: TypeAlias = NestedTrace | Trace

_ROOT_STYLE: Final[RootStyle] = RootStyle(datafmt=DataFmt.HEX, rjustify=True)


def _merge_path(parent: Optional[str], own: str) -> str:
    if parent is not None:
        return f"{parent}.{own}"
    else:
        return own


def _merge_style(parent: RootStyle, own: Optional[Style]) -> RootStyle:
    if own is not None:
        return parent | own  # type: ignore
    else:
        return parent


def _traverse_dom(
    save: GTKWSave,
    dom: Sequence[AnyTrace] | AnyTrace,
    parent_style: RootStyle,
    parent_path: Optional[str],
) -> None:
    if not isinstance(dom, Sequence):
        dom = [dom]

    for item in dom:
        match item:
            case Comment(comment, analog_extend, highlight):
                save.blank(comment, analog_extend, highlight)

            case Blank(analog_extend, highlight):
                save.blank(analog_extend=analog_extend, highlight=highlight)

            case Group(name, children, closed, highlight, style):
                style = _merge_style(parent_style, style)
                with save.group(name, closed, highlight):
                    _traverse_dom(save, children, style, parent_path)

            case Submodule(name, children, style):
                style = _merge_style(parent_style, style)
                _traverse_dom(save, children, style, _merge_path(parent_path, name))

            case Signal(
                name,
                alias,
                highlight,
                style,
                translate_filter_file,
                translate_filter_process,
            ):
                style = _merge_style(parent_style, style)
                save.trace(
                    _merge_path(parent_path, name),
                    alias,
                    style.get("color"),
                    style.get("datafmt").value,
                    highlight,
                    style.get("rjustify"),
                    style.get("extraflags"),
                    translate_filter_file,
                    translate_filter_process,
                )

            case Styled(children, style):
                style = _merge_style(parent_style, style)
                _traverse_dom(save, children, style, parent_path)

            # Implicit signal name
            case str():
                save.trace(
                    _merge_path(parent_path, item),
                    color=parent_style.get("color"),
                    datafmt=parent_style.get("datafmt").value,
                    rjustify=parent_style.get("rjustify"),
                    extraflags=parent_style.get("extraflags"),
                )


class Options(TypedDict, total=False):
    add_vcd_mtime: bool
    """Store VCD modification time?"""
    vcd_abs: bool
    """Use absolute path to VCD file?"""
    named_markers: dict[str, int]
    """Named marker positions ('a' - 'z')"""
    timestart: int
    """Simulation start time"""


def write_gtkw_file(
    file_name: str | Path,
    vcd_file: str | Path,
    traces: Sequence[Trace] | Trace,
    *,
    source_file: Optional[str | Path] = None,
    zoom: float = 0,
    marker: int = -1,
    root_style: RootStyle = _ROOT_STYLE,
    root_module: Optional[str] = None,
    **kwargs: Unpack[Options],
) -> None:
    """Create a new gtkw save file.

    Args:
        file_name:      `.gtkw` file path
        vcd_file:       `.vcd` file path
        traces:         List/sequence of traces
        source_file:    Source file path
        zoom:           Zoom amount
        marker:         Primary marker position
        root_style:     Root style to use
        root_module:    Root module name to use
        kwargs:         Various options (see `Options`)
    """
    with open(file_name, "wt", encoding="utf-8") as fjel:
        gtkw = GTKWSave(fjel)

        if source_file is not None:
            gtkw.comment(f"Auto-generated from {source_file}")
        gtkw.dumpfile(str(vcd_file), kwargs.get("vcd_abs", True))
        gtkw.zoom_markers(zoom, marker, kwargs=kwargs.get("named_markers", dict()))

        _traverse_dom(gtkw, traces, root_style, root_module)
