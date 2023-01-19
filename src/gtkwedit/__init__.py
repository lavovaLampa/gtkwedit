from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, Final, Generic, Literal, Optional, TypeAlias, TypedDict, TypeVar

from typing_extensions import NotRequired, Unpack
from vcd.gtkw import GTKWColor as Color, GTKWFlag, GTKWSave

T = TypeVar("T", bound="Trace | NestedTrace")


class DataFmt(Enum):
    HEX = "hex"
    DEC = "dec"
    BIN = "bin"
    OCT = "oct"
    ASCII = "ascii"
    REAL = "real"
    SIGNED = "signed"


class RootStyle(TypedDict):
    color: NotRequired[Optional[Color]]
    datafmt: DataFmt
    rjustify: bool
    extraflags: NotRequired[Optional[GTKWFlag]]


class Style(TypedDict, total=False):
    color: Optional[Color]
    datafmt: DataFmt
    rjustify: bool
    extraflags: Optional[GTKWFlag]


@dataclass(frozen=True)
class Styled(Generic[T]):
    children: Sequence[T] | T
    style: Style


@dataclass(frozen=True)
class Signal:
    name: str
    alias: Optional[str] = None
    highlight: bool = False
    style: Optional[Style] = None
    translate_filter_file: Optional[str] = None
    translate_filter_process: Optional[str] = None


@dataclass(frozen=True)
class Submodule(Generic[T]):
    name: str
    children: Sequence[T] | T
    style: Optional[Style] = None


@dataclass(frozen=True)
class Group:
    name: str
    # Groups cannot be nested
    children: "Sequence[NestedTrace] | NestedTrace"
    closed: bool = False
    highlight: bool = False
    style: Optional[Style] = None


@dataclass(frozen=True)
class Blank:
    analog_extend: bool = False
    highlight: bool = False


@dataclass(frozen=True)
class Comment:
    comment: str
    analog_extend: bool = False
    highlight: bool = False


NestedTrace: TypeAlias = (
    str | Signal | Submodule["NestedTrace"] | Comment | Blank | Styled["NestedTrace"]
)
Trace: TypeAlias = (
    str | Signal | Submodule["Trace"] | Group | Comment | Blank | Styled["Trace"]
)

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
    dom: Sequence[T] | T,
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
    """

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
