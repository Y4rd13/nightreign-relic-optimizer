"""Radar chart of character effective stats.

Renders the 8 Nightreign attributes (VGR MND END STR DEX INT FAI ARC) as a
radar, where the axis value is the numeric grade (D=1 … S=5). Two series
are overlaid:
  - base (character's default grade) — dashed lavender
  - effective (after the active build's stat-modifying relics) — solid mauve

The delta between the two makes stat-shifting builds visible at a glance.
"""

from __future__ import annotations

import reflex as rx

from ..state import State
from ..theme import PAL


def _legend_chip(color: str, label: str, dashed: bool = False) -> rx.Component:
    border_style = "dashed" if dashed else "solid"
    return rx.hstack(
        rx.box(
            width="16px", height="3px",
            background=color,
            border=f"1px {border_style} {color}",
            border_radius="2px",
        ),
        rx.text(label, color=PAL["subtext"], font_size="0.72rem",
                font_weight="600"),
        spacing="1", align="center",
    )


def _grade_scale() -> rx.Component:
    """Tiny legend of the D/C/B/A/S rings (1-5 on the axis)."""
    grades = [("D", PAL["overlay0"]), ("C", PAL["teal"]),
              ("B", PAL["blue"]), ("A", PAL["mauve"]), ("S", PAL["peach"])]
    return rx.hstack(
        *[rx.text(g, color=c, font_size="0.65rem", font_weight="700",
                  font_family="ui-monospace, SFMono-Regular, Menlo, monospace")
          for g, c in grades],
        spacing="2",
        align="center",
        opacity=0.7,
    )


def stats_radar(height: int = 260, show_legend: bool = True) -> rx.Component:
    chart = rx.recharts.radar_chart(
        rx.recharts.polar_grid(
            stroke=PAL["surface1"],
            stroke_dasharray="2 3",
        ),
        rx.recharts.polar_angle_axis(
            data_key="abbr",
            tick={"fill": PAL["subtext"], "fontSize": 11, "fontWeight": 700},
        ),
        rx.recharts.polar_radius_axis(
            angle=90,
            domain=[0, 5],
            tick=False,
            axis_line=False,
        ),
        rx.recharts.radar(
            data_key="base_value",
            stroke=PAL["lavender"],
            fill=PAL["lavender"],
            fill_opacity=0.12,
            stroke_dasharray="4 3",
        ),
        rx.recharts.radar(
            data_key="value",
            stroke=PAL["mauve"],
            fill=PAL["mauve"],
            fill_opacity=0.35,
        ),
        rx.recharts.graphing_tooltip(
            cursor=False,
            content_style={
                "background": PAL["mantle"],
                "border": f"1px solid {PAL['surface1']}",
                "border_radius": "8px",
                "font_size": "0.78rem",
                "color": PAL["text"],
            },
        ),
        data=State.effective_stats_chart_data,
        width="100%",
        height=height,
    )

    if show_legend:
        return rx.vstack(
            chart,
            rx.hstack(
                _legend_chip(PAL["mauve"], "Effective (with relics)"),
                _legend_chip(PAL["lavender"], "Base", dashed=True),
                rx.spacer(),
                _grade_scale(),
                width="100%",
                align="center",
                spacing="3",
                flex_wrap="wrap",
            ),
            width="100%",
            spacing="2",
        )
    return chart


def _stat_delta_row(r) -> rx.Component:
    """One row showing a stat's base→effective grade if the build shifted it."""
    shifted = r.grade != r.base_grade
    return rx.cond(
        shifted,
        rx.hstack(
            rx.text(r.abbr, color=PAL["subtext"], font_size="0.72rem",
                    font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                    min_width="32px"),
            rx.text(r.base_grade, color=PAL["overlay1"], font_size="0.72rem"),
            rx.icon(tag="arrow_right", size=10, color=PAL["overlay0"]),
            rx.text(r.grade, color=PAL["mauve"], font_size="0.78rem",
                    font_weight="700"),
            rx.text(
                " (",
                rx.cond(r.delta > 0, rx.text("+", display="inline"), rx.text("", display="inline")),
                r.delta,
                ")",
                color=PAL["overlay0"], font_size="0.7rem", display="inline-flex",
            ),
            spacing="1", align="center",
        ),
        rx.box(),
    )


def stats_delta_list() -> rx.Component:
    """Short list of stats that actually shifted grades thanks to relics.
    Hidden when no shifts — so the sidebar stays clean for default builds."""
    return rx.box(
        rx.text("stat shifts from relics",
                color=PAL["overlay0"], font_size="0.68rem",
                font_weight="700",
                letter_spacing="0.08em",
                text_transform="uppercase",
                margin_bottom="4px"),
        rx.vstack(
            rx.foreach(State.effective_stats, _stat_delta_row),
            spacing="1",
            align="start",
            width="100%",
        ),
    )


def damage_contribution_bar(height: int = 260) -> rx.Component:
    """Horizontal bars: each multiplier bucket's % contribution above baseline.
    Labels are human-readable ('3+ Hammers Equipped') via bucket_label_map."""
    return rx.recharts.bar_chart(
        rx.recharts.cartesian_grid(
            stroke=PAL["surface0"],
            stroke_dasharray="2 3",
            horizontal=False,
        ),
        rx.recharts.x_axis(
            type_="number",
            tick={"fill": PAL["overlay1"], "fontSize": 10},
            stroke=PAL["surface1"],
            unit="%",
        ),
        rx.recharts.y_axis(
            data_key="name",
            type_="category",
            width=160,
            tick={"fill": PAL["subtext"], "fontSize": 11, "fontWeight": 600},
            axis_line=False,
        ),
        rx.recharts.bar(
            rx.recharts.label_list(
                data_key="value",
                position="right",
                fill=PAL["text"],
                offset=6,
            ),
            data_key="value",
            fill=PAL["mauve"],
            radius=4,
        ),
        rx.recharts.graphing_tooltip(
            cursor={"fill": "rgba(203,166,247,0.05)"},
            content_style={
                "background": PAL["mantle"],
                "border": f"1px solid {PAL['surface1']}",
                "border_radius": "8px",
                "font_size": "0.78rem",
                "color": PAL["text"],
                "padding": "6px 10px",
            },
        ),
        data=State.mult_stack_data,
        layout="vertical",
        width="100%",
        height=height,
        margin={"left": 4, "right": 40, "top": 4, "bottom": 8},
    )


def damage_sources_pie(height: int = 240) -> rx.Component:
    """Pie chart: hammer vs hex damage share of the 30s boss window."""
    return rx.recharts.pie_chart(
        rx.recharts.pie(
            rx.foreach(
                State.damage_sources_with_colors,
                lambda row: rx.recharts.cell(fill=row["fill"], stroke=PAL["mantle"]),
            ),
            data=State.damage_sources_with_colors,
            data_key="value",
            name_key="name",
            cx="50%", cy="48%",
            inner_radius=45,
            outer_radius=85,
            padding_angle=3,
            label={"fill": PAL["text"], "fontSize": 12, "fontWeight": 700},
            label_line=False,
            stroke=PAL["mantle"],
        ),
        rx.recharts.graphing_tooltip(
            content_style={
                "background": PAL["mantle"],
                "border": f"1px solid {PAL['surface1']}",
                "border_radius": "8px",
                "font_size": "0.8rem",
                "color": PAL["text"],
                "padding": "6px 10px",
            },
        ),
        rx.recharts.legend(
            vertical_align="bottom",
            icon_size=12,
            wrapper_style={
                "fontSize": "0.78rem",
                "color": PAL["subtext"],
                "paddingTop": "6px",
            },
        ),
        data=State.damage_sources_with_colors,
        width="100%",
        height=height,
    )


_DEFENSIVE_GROUP_COLORS = {
    "body": PAL["green"],
    "elemental": PAL["teal"],
    "status": PAL["yellow"],
}


def _defensive_row(row) -> rx.Component:
    """One line 'Label ......... +N%'. Greyed when value==0."""
    non_zero = row.value > 0
    return rx.hstack(
        rx.box(
            width="3px", height="12px",
            background=rx.match(
                row.group,
                ("body", _DEFENSIVE_GROUP_COLORS["body"]),
                ("elemental", _DEFENSIVE_GROUP_COLORS["elemental"]),
                ("status", _DEFENSIVE_GROUP_COLORS["status"]),
                PAL["overlay0"],
            ),
            border_radius="2px",
            opacity=rx.cond(non_zero, "1", "0.25"),
        ),
        rx.text(row.label,
                color=rx.cond(non_zero, PAL["subtext"], PAL["overlay0"]),
                font_size="0.74rem"),
        rx.spacer(),
        rx.hstack(
            rx.text(rx.cond(non_zero, "+", ""),
                    font_size="0.74rem",
                    color=rx.cond(non_zero, PAL["text"], PAL["overlay0"])),
            rx.text(row.value.to_string(),
                    font_weight="700",
                    font_size="0.78rem",
                    color=rx.cond(non_zero, PAL["text"], PAL["overlay0"]),
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
            rx.text(row.unit,
                    font_size="0.7rem",
                    color=PAL["overlay1"],
                    margin_left="1px"),
            spacing="0", align="baseline",
        ),
        width="100%",
        align="center",
        spacing="2",
        padding="3px 2px",
    )


def _affinity_row(row) -> rx.Component:
    non_zero = row.value > 0
    return rx.hstack(
        rx.text(row.label,
                color=rx.cond(non_zero, PAL["subtext"], PAL["overlay0"]),
                font_size="0.74rem"),
        rx.spacer(),
        rx.hstack(
            rx.text(rx.cond(non_zero, "+", ""),
                    font_size="0.74rem",
                    color=rx.cond(non_zero, PAL["peach"], PAL["overlay0"])),
            rx.text(row.value.to_string(),
                    font_weight="700",
                    font_size="0.78rem",
                    color=rx.cond(non_zero, PAL["peach"], PAL["overlay0"]),
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
            rx.text("%", font_size="0.7rem", color=PAL["overlay1"]),
            spacing="0", align="baseline",
        ),
        width="100%",
        align="center",
        spacing="2",
        padding="3px 2px",
    )


def defensive_stats_list() -> rx.Component:
    """Table: Max HP, poise, element negation, status resistance."""
    return rx.vstack(
        rx.foreach(State.defensive_rows, _defensive_row),
        spacing="0",
        width="100%",
    )


def affinity_attack_list() -> rx.Component:
    """Per-element attack-power bonus — relevant for hybrid / caster builds."""
    return rx.vstack(
        rx.foreach(State.affinity_attack_rows, _affinity_row),
        spacing="0",
        width="100%",
    )


def _chart_toggle_btn() -> rx.Component:
    return rx.el.button(
        rx.hstack(
            rx.icon(
                tag=rx.cond(State.show_charts, "eye_off", "eye"),
                size=13,
            ),
            rx.text(
                rx.cond(State.show_charts, "Hide charts", "Show charts"),
                font_weight="600",
            ),
            spacing="1", align="center",
        ),
        on_click=State.toggle_charts,
        title="Toggle the character-stats charts on / off",
        style={
            "background": "transparent",
            "border": f"1px solid {PAL['surface1']}",
            "color": PAL["subtext"],
            "padding": "4px 12px",
            "border_radius": "6px",
            "font_size": "0.76rem",
            "cursor": "pointer",
        },
        _hover={
            "border_color": PAL["mauve"],
            "color": PAL["mauve"],
        },
    )


def _chart_card(icon: str, label: str, child: rx.Component,
                min_width: str = "300px") -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.icon(tag=icon, size=13, color=PAL["overlay1"]),
            rx.text(label.upper(),
                    color=PAL["overlay1"],
                    font_size="0.66rem",
                    letter_spacing="0.08em",
                    font_weight="700"),
            spacing="1", align="center",
            margin_bottom="6px",
        ),
        child,
        flex="1",
        min_width=min_width,
        padding="8px 10px",
        background=PAL["crust"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_radius="10px",
    )


def character_stats_panel() -> rx.Component:
    """Optimizer-tab stats panel: 3-4 charts with a show/hide toggle."""
    return rx.box(
        rx.hstack(
            rx.icon(tag="chart_column", size=18, color=PAL["mauve"]),
            rx.heading("Character · build analytics", size="4", color=PAL["text"]),
            rx.text("· attributes · multiplier stack · damage sources",
                    color=PAL["overlay1"], font_size="0.82rem"),
            rx.spacer(),
            _chart_toggle_btn(),
            spacing="2", align="center", margin_bottom="12px",
            width="100%",
        ),
        rx.cond(
            State.show_charts,
            rx.flex(
                _chart_card("radar", "Attributes — base vs effective",
                            stats_radar(height=260, show_legend=True),
                            min_width="320px"),
                _chart_card("chart_bar", "Multiplier contribution %",
                            damage_contribution_bar(height=260),
                            min_width="380px"),
                _chart_card("chart_pie", "Damage sources",
                            damage_sources_pie(height=260),
                            min_width="280px"),
                rx.cond(
                    State.has_stat_shifts,
                    _chart_card("trending_up", "Stat shifts from relics",
                                stats_delta_list(),
                                min_width="240px"),
                    rx.box(),
                ),
                _chart_card("shield", "Defense & resistance",
                            defensive_stats_list(),
                            min_width="270px"),
                _chart_card("sparkles", "Affinity attack %",
                            affinity_attack_list(),
                            min_width="180px"),
                direction="row",
                wrap="wrap",
                gap="12px",
                width="100%",
                align="stretch",
            ),
            rx.hstack(
                rx.icon(tag="info", size=12, color=PAL["overlay0"]),
                rx.text("Charts hidden · click 'Show charts' to expand.",
                        color=PAL["overlay0"],
                        font_size="0.78rem",
                        font_style="italic"),
                spacing="1", align="center",
                padding="8px 4px",
            ),
        ),
        background=PAL["mantle"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_radius="12px",
        padding="14px 18px 16px",
        margin_bottom="14px",
    )
