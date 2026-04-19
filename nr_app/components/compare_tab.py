"""Compare presets tab — current build radar + comparison bar chart across presets."""

from __future__ import annotations

import reflex as rx

from ..state import State
from ..theme import PAL
from ..widgets import build_type_pill
from .stats_chart import stats_radar


def _empty_state() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon(tag="scale", size=48, color=PAL["overlay0"]),
            rx.heading("No presets saved yet", size="4", color=PAL["subtext"]),
            rx.text(
                "Save a build from the sidebar, then return here to diff multiple builds side by side.",
                color=PAL["overlay1"], font_size="0.88rem",
                text_align="center", max_width="480px",
            ),
            spacing="2",
            align="center",
        ),
        padding="60px 20px",
        width="100%",
    )


def _metric_strip(preset) -> rx.Component:
    """Dense one-line summary of each preset's damage-model numbers."""
    return rx.hstack(
        rx.vstack(
            rx.text("DAMAGE", color=PAL["overlay1"],
                    font_size="0.6rem", letter_spacing="0.08em",
                    font_weight="700"),
            rx.text(preset.score,
                    color=PAL["mauve"], font_size="1.3rem",
                    font_weight="800",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                    line_height="1"),
            spacing="0", align="start", min_width="88px",
        ),
        rx.vstack(
            rx.text("HAMMER", color=PAL["overlay1"],
                    font_size="0.6rem", letter_spacing="0.08em",
                    font_weight="700"),
            rx.text(preset.hammer_mult.to_string() + "×",
                    color=PAL["peach"], font_size="0.96rem",
                    font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
            spacing="0", align="start", min_width="72px",
        ),
        rx.vstack(
            rx.text("HEX", color=PAL["overlay1"],
                    font_size="0.6rem", letter_spacing="0.08em",
                    font_weight="700"),
            rx.text(preset.hex_mult.to_string() + "×",
                    color=PAL["sky"], font_size="0.96rem",
                    font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
            spacing="0", align="start", min_width="64px",
        ),
        rx.vstack(
            rx.text("ADD.PHYS", color=PAL["overlay1"],
                    font_size="0.6rem", letter_spacing="0.08em",
                    font_weight="700"),
            rx.text("+" + preset.additive_phys_pct.to_string() + "%",
                    color=PAL["teal"], font_size="0.96rem",
                    font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
            spacing="0", align="start", min_width="80px",
        ),
        rx.vstack(
            rx.text("UTILITY", color=PAL["overlay1"],
                    font_size="0.6rem", letter_spacing="0.08em",
                    font_weight="700"),
            rx.text(preset.utility_mult.to_string() + "×",
                    color=PAL["lavender"], font_size="0.96rem",
                    font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
            spacing="0", align="start", min_width="72px",
        ),
        rx.vstack(
            rx.text("UPTIME", color=PAL["overlay1"],
                    font_size="0.6rem", letter_spacing="0.08em",
                    font_weight="700"),
            rx.text(preset.trance_uptime_pct.to_string() + "%",
                    color=PAL["yellow"], font_size="0.96rem",
                    font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
            spacing="0", align="start", min_width="68px",
        ),
        spacing="4", align="start", width="100%",
        flex_wrap="wrap",
        padding="10px 12px",
        background=PAL["crust"],
        border=f"1px solid {PAL['surface0']}",
        border_radius="8px",
    )


def _preset_row_card(preset) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.hstack(
                rx.text(preset.character_icon, font_size="1.05rem"),
                rx.vstack(
                    rx.hstack(
                        rx.text(preset.name,
                                color=PAL["text"], font_weight="800",
                                font_size="1rem"),
                        build_type_pill(preset.build_type),
                        spacing="2", align="center",
                    ),
                    rx.hstack(
                        rx.text(preset.vessel_name,
                                color=PAL["teal"], font_size="0.72rem"),
                        rx.text("·", color=PAL["overlay0"], font_size="0.72rem"),
                        rx.text(preset.mode,
                                color=PAL["overlay1"], font_size="0.72rem",
                                font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                        rx.text("·", color=PAL["overlay0"], font_size="0.72rem"),
                        rx.text(preset.date,
                                color=PAL["overlay0"], font_size="0.72rem"),
                        spacing="1", align="center",
                    ),
                    spacing="0", align="start",
                ),
                spacing="3", align="start", flex="1",
            ),
            rx.el.button(
                rx.hstack(
                    rx.icon(tag="rotate_cw", size=12),
                    rx.text("Load", font_weight="700"),
                    spacing="1", align="center",
                ),
                on_click=State.load_preset(preset.name),
                title="Load this preset to see its radar overlay current build",
                style={
                    "background": "transparent",
                    "border": f"1px solid {PAL['surface1']}",
                    "color": PAL["mauve"],
                    "padding": "6px 14px",
                    "border_radius": "6px",
                    "font_size": "0.78rem",
                    "cursor": "pointer",
                },
                _hover={
                    "background": "rgba(203,166,247,0.10)",
                    "border_color": PAL["mauve"],
                },
            ),
            width="100%", align="center",
            margin_bottom="8px",
        ),
        _metric_strip(preset),
        background=PAL["mantle"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_radius="10px",
        padding="12px 14px",
        _hover={"border_color": PAL["surface1"]},
    )


def _goals_bar_chart() -> rx.Component:
    """Grouped bar chart of the 4 build-goal axes per preset. Makes it
    obvious at a glance which presets are DPS / tank / caster / support —
    bar heights map directly to damage/survival/utility/team scores."""
    return rx.box(
        rx.hstack(
            rx.icon(tag="target", size=18, color=PAL["mauve"]),
            rx.heading("Goal axes", size="4", color=PAL["text"]),
            rx.text("· damage vs survival vs utility vs team per preset",
                    color=PAL["overlay1"], font_size="0.82rem"),
            spacing="2", align="center", margin_bottom="12px",
        ),
        rx.recharts.bar_chart(
            rx.recharts.cartesian_grid(stroke=PAL["surface0"],
                                        stroke_dasharray="2 4"),
            rx.recharts.x_axis(
                data_key="name",
                stroke=PAL["surface1"],
                tick_line=False,
                interval=0,
                tick={"fontSize": 11, "fill": PAL["subtext"]},
            ),
            rx.recharts.y_axis(
                stroke=PAL["surface1"],
                tick_line=False,
                axis_line=False,
                tick={"fontSize": 11, "fill": PAL["overlay1"]},
            ),
            rx.recharts.graphing_tooltip(
                content_style={
                    "backgroundColor": PAL["crust"],
                    "border": f"1px solid {PAL['surface1']}",
                    "borderRadius": "6px",
                    "fontSize": "12px",
                },
                cursor={"fill": "rgba(203,166,247,0.08)"},
            ),
            rx.recharts.legend(wrapper_style={"fontSize": "11px"}),
            rx.recharts.bar(
                data_key="damage", fill=PAL["peach"],
                name="Damage", radius=[3, 3, 0, 0],
            ),
            rx.recharts.bar(
                data_key="survival", fill=PAL["green"],
                name="Survival", radius=[3, 3, 0, 0],
            ),
            rx.recharts.bar(
                data_key="utility", fill=PAL["yellow"],
                name="Utility", radius=[3, 3, 0, 0],
            ),
            rx.recharts.bar(
                data_key="team", fill=PAL["mauve"],
                name="Team", radius=[3, 3, 0, 0],
            ),
            data=State.preset_compare_chart_data,
            height=300,
            margin={"top": 10, "right": 20, "left": 0, "bottom": 10},
        ),
        background=PAL["mantle"],
        border=f"1px solid {PAL['surface0']}",
        border_radius="12px",
        padding="14px 18px 16px",
        width="100%",
    )


def _comparison_bar_chart() -> rx.Component:
    """Grouped bar chart: each preset on X, 4 grouped bars per preset."""
    return rx.box(
        rx.hstack(
            rx.icon(tag="chart_bar", size=18, color=PAL["mauve"]),
            rx.heading("Comparison chart", size="4", color=PAL["text"]),
            rx.text("· damage & multipliers across saved presets",
                    color=PAL["overlay1"], font_size="0.82rem"),
            spacing="2", align="center", margin_bottom="12px",
        ),
        rx.recharts.bar_chart(
            rx.recharts.cartesian_grid(stroke=PAL["surface0"],
                                        stroke_dasharray="2 4"),
            rx.recharts.x_axis(
                data_key="name",
                stroke=PAL["surface1"],
                tick_line=False,
                interval=0,
                tick={"fontSize": 11, "fill": PAL["subtext"]},
            ),
            rx.recharts.y_axis(
                stroke=PAL["surface1"],
                tick_line=False,
                axis_line=False,
                tick={"fontSize": 11, "fill": PAL["overlay1"]},
            ),
            rx.recharts.graphing_tooltip(
                content_style={
                    "backgroundColor": PAL["crust"],
                    "border": f"1px solid {PAL['surface1']}",
                    "borderRadius": "6px",
                    "fontSize": "12px",
                },
                cursor={"fill": "rgba(203,166,247,0.08)"},
            ),
            rx.recharts.legend(wrapper_style={"fontSize": "11px"}),
            rx.recharts.bar(
                data_key="damage",
                fill=PAL["mauve"],
                name="Damage (30s)",
                radius=[3, 3, 0, 0],
            ),
            rx.recharts.bar(
                data_key="additive_phys_pct",
                fill=PAL["teal"],
                name="Additive phys %",
                radius=[3, 3, 0, 0],
            ),
            rx.recharts.bar(
                data_key="hammer_mult_pct",
                fill=PAL["peach"],
                name="Hammer mult +%",
                radius=[3, 3, 0, 0],
            ),
            rx.recharts.bar(
                data_key="utility_mult_pct",
                fill=PAL["lavender"],
                name="Utility mult +%",
                radius=[3, 3, 0, 0],
            ),
            rx.recharts.bar(
                data_key="trance_uptime_pct",
                fill=PAL["yellow"],
                name="Skill uptime %",
                radius=[3, 3, 0, 0],
            ),
            data=State.preset_compare_chart_data,
            height=320,
            margin={"top": 10, "right": 20, "left": 0, "bottom": 10},
        ),
        background=PAL["mantle"],
        border=f"1px solid {PAL['surface0']}",
        border_radius="12px",
        padding="14px 18px 16px",
        width="100%",
    )


def _current_build_radar_panel() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.icon(tag="radar", size=18, color=PAL["mauve"]),
            rx.heading("Current build stats", size="4", color=PAL["text"]),
            rx.text("· radar shows effective grades with active relics",
                    color=PAL["overlay1"], font_size="0.82rem"),
            spacing="2", align="center", margin_bottom="12px",
        ),
        rx.box(
            stats_radar(height=320, show_legend=True),
            max_width="520px",
        ),
        background=PAL["mantle"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_radius="12px",
        padding="14px 18px 16px",
    )


def compare_tab() -> rx.Component:
    return rx.cond(
        State.saved_presets.length() == 0,
        rx.vstack(
            _current_build_radar_panel(),
            _empty_state(),
            width="100%",
            spacing="3",
            align="start",
        ),
        rx.vstack(
            rx.grid(
                _current_build_radar_panel(),
                _goals_bar_chart(),
                columns=rx.breakpoints(initial="1", md="2"),
                gap="14px",
                width="100%",
            ),
            _comparison_bar_chart(),
            rx.hstack(
                rx.icon(tag="scale", size=22, color=PAL["mauve"]),
                rx.heading("Compare saved builds", size="5", color=PAL["text"]),
                spacing="2", align="center",
                margin_top="6px",
            ),
            rx.text(
                "Detailed metrics per preset. Click Load to overlay that "
                "preset's radar on top — use the chart above for high-level "
                "differences at a glance.",
                color=PAL["overlay1"], font_size="0.86rem",
                margin_bottom="6px",
            ),
            rx.vstack(
                rx.foreach(State.saved_presets, _preset_row_card),
                width="100%",
                spacing="2",
                align="stretch",
            ),
            rx.callout(
                rx.text(
                    "Tip: the bar chart displays damage in absolute dmg/30s "
                    "and multipliers as % over baseline (+10% = 1.10×). "
                    "Skill uptime is shown directly as % of boss window.",
                    font_size="0.82rem",
                ),
                icon="info",
                color_scheme="gray",
                margin_top="16px",
                width="100%",
            ),
            width="100%",
            align="start",
            spacing="3",
        ),
    )
