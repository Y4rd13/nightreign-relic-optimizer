"""Hero banner — compact flex-wrap layout with damage number + key stats + buckets."""

from __future__ import annotations

import reflex as rx

from ..state import State
from ..theme import PAL
from ..widgets import build_type_pill
from .dormant_powers import dormant_summary_pill


STAT_CARD_STYLE = {
    "padding": "8px 12px",
    "background": PAL["mantle"],
    "border": f"1px solid {PAL['surface0']}",
    "border_radius": "8px",
    "min_width": "132px",
    "transition": "border-color 0.12s",
}

BUCKET_CARD_STYLE = {
    "padding": "8px 12px",
    "background": "rgba(148,226,213,0.08)",
    "border": "1px solid rgba(148,226,213,0.22)",
    "border_radius": "8px",
    "min_width": "110px",
    "transition": "border-color 0.12s",
}


_HERO_TOOLTIPS = {
    "Primary":      "Aggregate damage multiplier for this character's primary attack lane — product of bucket × utility × skill uptime.",
    "Secondary":    "Aggregate damage multiplier for the character's secondary damage lane (e.g. Undertaker's hex casts).",
    "Additive":     "Sum of additive damage effects (+N% phys / +N% all). Adds after multipliers: damage × (1 + additive%).",
    "Utility":      "Utility multiplier — folds in skill-uptime loops and other non-bucket effects.",
    "Skill uptime": "Percentage of the boss window with the character's skill buff active. A 'skill loop' relic pushes this toward 99%.",
}


_GOAL_CARD_BASE = {
    "padding": "6px 10px",
    "border_radius": "7px",
    "min_width": "90px",
    "cursor": "help",
    "border": "1px solid",
}


def _goal_card(label: str, value, accent: str, weight, tooltip_text: str) -> rx.Component:
    """Compact card showing one goal axis: label, raw score, weight applied.

    The border + accent colour match the sidebar slider so the user can
    eyeball which goal weight drives which card."""
    return rx.tooltip(
        rx.box(
            rx.hstack(
                rx.text(label.upper(), color=accent,
                        font_size="0.62rem", letter_spacing="0.08em",
                        font_weight="700"),
                rx.spacer(),
                rx.text("w=", color=PAL["overlay1"], font_size="0.62rem",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                rx.text(weight.to_string(), color=PAL["overlay1"],
                        font_size="0.62rem", font_weight="700",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                spacing="1",
                width="100%",
                align="center",
            ),
            rx.text(value, color=PAL["text"],
                    font_size="1rem", font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                    margin_top="2px"),
            style={
                **_GOAL_CARD_BASE,
                "border_color": accent,
                "background": "rgba(0,0,0,0.18)",
            },
        ),
        content=tooltip_text,
    )


def _build_type_badge() -> rx.Component:
    """Wrapper around the shared widget with a top margin to fit the hero layout."""
    return rx.box(build_type_pill(State.dominant_goal_label), margin_top="4px")


def _mult(label, value, tooltip_key: str | None = None) -> rx.Component:
    """Generic multiplier card. `label` may be a Python str or a Reflex Var;
    `tooltip_key` selects the tooltip text (defaults to the label string)."""
    up = label.upper() if hasattr(label, "upper") else label
    tooltip_text = _HERO_TOOLTIPS.get(tooltip_key or label, "")
    return rx.tooltip(
        rx.box(
            rx.text(up, color=PAL["overlay1"],
                    font_size="0.64rem", letter_spacing="0.08em",
                    font_weight="700"),
            rx.hstack(
                rx.text("×", color=PAL["overlay1"], font_size="0.86rem",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                rx.text(value, color=PAL["text"],
                        font_size="1.1rem", font_weight="700",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                spacing="0",
                align="baseline",
                margin_top="2px",
            ),
            style={**STAT_CARD_STYLE, "cursor": "help"},
        ),
        content=tooltip_text,
    )


def _pct(label: str, value, prefix: str = "+") -> rx.Component:
    return rx.tooltip(
        rx.box(
            rx.text(label.upper(), color=PAL["overlay1"],
                    font_size="0.64rem", letter_spacing="0.08em",
                    font_weight="700"),
            rx.hstack(
                rx.text(prefix, color=PAL["overlay1"], font_size="0.86rem",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                rx.text(value, color=PAL["text"],
                        font_size="1.1rem", font_weight="700",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                rx.text("%", color=PAL["overlay1"], font_size="0.86rem",
                        margin_left="1px"),
                spacing="0",
                align="baseline",
                margin_top="2px",
            ),
            style={**STAT_CARD_STYLE, "cursor": "help"},
        ),
        content=_HERO_TOOLTIPS.get(label, label),
    )


def _raw(label: str, value, suffix: str = "") -> rx.Component:
    return rx.tooltip(
        rx.box(
            rx.text(label.upper(), color=PAL["overlay1"],
                    font_size="0.64rem", letter_spacing="0.08em",
                    font_weight="700"),
            rx.hstack(
                rx.text(value, color=PAL["text"],
                        font_size="1.1rem", font_weight="700",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                rx.cond(
                    suffix != "",
                    rx.text(suffix, color=PAL["overlay1"], font_size="0.86rem",
                            margin_left="2px"),
                    rx.box(),
                ),
                spacing="0",
                align="baseline",
                margin_top="2px",
            ),
            style={**STAT_CARD_STYLE, "cursor": "help"},
        ),
        content=_HERO_TOOLTIPS.get(label, label),
    )


def _bucket(b) -> rx.Component:
    return rx.tooltip(
        rx.box(
            rx.text(b.name, color=PAL["overlay1"],
                    font_size="0.6rem", letter_spacing="0.06em",
                    font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
            rx.hstack(
                rx.text("×", color=PAL["teal"], font_size="0.76rem",
                        margin_right="1px", opacity="0.7"),
                rx.text(b.value, color=PAL["teal"],
                        font_size="1rem", font_weight="700",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                spacing="0",
                align="baseline",
                margin_top="2px",
            ),
            style={**BUCKET_CARD_STYLE, "cursor": "help"},
        ),
        content=rx.cond(
            State.bucket_label_map.contains(b.name),
            State.bucket_label_map[b.name],
            b.name,
        ),
    )


def _weapon_pill(w) -> rx.Component:
    """One weapon chip: name + how many effects in the pool key off this class.
    The damage model can't split damage per weapon, but the pool count tells
    the user which weapons actually unlock new effect surfaces for them."""
    return rx.tooltip(
        rx.hstack(
            rx.icon(tag="sword", size=10, color=PAL["teal"]),
            rx.text(w["label"], color=PAL["subtext"],
                    font_size="0.72rem", font_weight="600"),
            rx.box(
                w["effect_count"].to_string(),
                background="rgba(148,226,213,0.16)",
                color=PAL["teal"],
                padding="0 5px", border_radius="99px",
                font_size="0.62rem", font_weight="700",
                font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                margin_left="2px",
            ),
            spacing="1", align="center",
            padding="3px 8px",
            border="1px solid rgba(148,226,213,0.22)",
            border_radius="6px",
            background="rgba(148,226,213,0.06)",
        ),
        content=("Effects in your character pool that reference this "
                 "weapon class. Swap weapons in the sidebar to change "
                 "which effects are eligible."),
    )


def _weapons_strip() -> rx.Component:
    return rx.cond(
        State.weapon_display_rows.length() > 0,
        rx.vstack(
            rx.text("Weapons active",
                    color=PAL["overlay1"], font_size="0.58rem",
                    letter_spacing="0.08em", font_weight="700",
                    margin_top="2px"),
            rx.flex(
                rx.foreach(State.weapon_display_rows, _weapon_pill),
                direction="row", wrap="wrap", gap="4px",
            ),
            spacing="1", align="start",
            margin_top="4px",
        ),
        rx.box(),
    )


def hero() -> rx.Component:
    return rx.box(
        rx.flex(
            # Damage score block (fixed width)
            rx.vstack(
                rx.tooltip(
                    rx.text(State.damage_total,
                            font_size="2.6rem", font_weight="800",
                            color=PAL["mauve"],
                            line_height="1",
                            letter_spacing="-0.02em",
                            cursor="help",
                            font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                    content=(
                        "Relative damage score over a 30-second boss window. "
                        "It's the number of 'naked-hit equivalents' the build "
                        "produces — not raw HP damage. Use it to compare "
                        "builds against each other. A build scoring 84 with "
                        "baseline 29 hits ~2.87× harder than a naked weapon."
                    ),
                ),
                rx.hstack(
                    rx.icon(tag="timer", size=11, color=PAL["overlay1"]),
                    rx.text("DAMAGE SCORE · 30s",
                            color=PAL["overlay1"],
                            font_size="0.64rem",
                            letter_spacing="0.08em",
                            font_weight="700"),
                    spacing="1",
                    align="center",
                    margin_top="4px",
                ),
                rx.tooltip(
                    rx.hstack(
                        rx.text("≈", color=PAL["overlay0"],
                                font_size="0.78rem"),
                        rx.text(State.damage_baseline_mult,
                                color=PAL["teal"],
                                font_size="0.88rem", font_weight="700",
                                font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                        rx.text("×", color=PAL["teal"],
                                font_size="0.78rem", font_weight="700"),
                        rx.text("naked baseline",
                                color=PAL["overlay1"], font_size="0.72rem",
                                margin_left="3px"),
                        spacing="1", align="baseline",
                        margin_top="2px",
                    ),
                    content=(
                        f"Current build / naked (0 relics) = damage multiplier. "
                        f"Naked baseline = {State.naked_baseline_score}."
                    ),
                ),
                _build_type_badge(),
                dormant_summary_pill(),
                _weapons_strip(),
                spacing="1",
                align="start",
                min_width="180px",
                padding_right="20px",
                border_right=f"1px solid {PAL['surface0']}",
            ),
            # Stats + goal-axis breakdown — flex-wrap for natural flow.
            rx.flex(
                _goal_card("Damage", State.damage_total, PAL["peach"],
                           State.effective_build_goal_weights["damage"],
                           "Boss-window damage score (the big number). "
                           "Weighted by 'Damage' goal slider. Higher = more "
                           "30-second DPS."),
                _goal_card("Survival", State.survival_score, PAL["green"],
                           State.effective_build_goal_weights["survival"],
                           "Defensive value: max HP + damage negation + "
                           "poise + HP restoration. Weighted by 'Survival' "
                           "goal slider. Guardian-tank default = 1.0."),
                _goal_card("Utility", State.utility_score, PAL["yellow"],
                           State.effective_build_goal_weights["utility"],
                           "Non-damage utility: skill CD, ult gauge, "
                           "stamina/FP recovery. Weighted by 'Utility' "
                           "slider. Scholar default = 0.8."),
                _goal_card("Team", State.team_score, PAL["mauve"],
                           State.effective_build_goal_weights["team"],
                           "Ally-oriented effects: team heals, party buffs, "
                           "summon/retinue. Weighted by 'Team' slider. "
                           "Revenant default = 0.8."),
                _mult(State.primary_damage_label, State.hammer_mult,
                      tooltip_key="Primary"),
                rx.cond(
                    State.has_secondary_damage,
                    _mult(State.secondary_damage_label, State.hex_mult,
                          tooltip_key="Secondary"),
                    rx.box(),
                ),
                _pct ("Additive",    State.additive_phys_pct),
                _mult("Utility",     State.utility_mult),
                _raw ("Skill uptime", State.skill_uptime_pct, suffix="%"),
                rx.foreach(State.bucket_report, _bucket),
                direction="row",
                wrap="wrap",
                gap="10px",
                flex="1",
                padding_left="20px",
            ),
            direction="row",
            wrap="wrap",
            align="center",
            width="100%",
            gap="12px",
        ),
        background="linear-gradient(135deg, rgba(203,166,247,0.10) 0%, rgba(137,180,250,0.06) 50%, rgba(148,226,213,0.04) 100%)",
        border="1px solid rgba(203,166,247,0.22)",
        border_radius="14px",
        padding="16px 20px",
        margin_bottom="18px",
        box_shadow="0 4px 20px rgba(0,0,0,0.15)",
    )
