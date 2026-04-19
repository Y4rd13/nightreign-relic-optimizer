"""Dormant Powers (permanent buffs) picker — compact list for the sidebar.

Each row cycles 0 → tier 1 → tier 2 → 0 on click. Damage-affecting buffs
are visually emphasised with a mauve left border so the user sees which
ones move the optimiser's total.
"""

from __future__ import annotations

import reflex as rx

from ..state import State
from ..theme import PAL


def _tier_pip(pip_idx, current_tier) -> rx.Component:
    active = pip_idx <= current_tier
    return rx.box(
        width="6px", height="6px",
        border_radius="50%",
        background=rx.cond(active, PAL["mauve"], PAL["surface1"]),
        transition="background 0.12s",
    )


def _row(r) -> rx.Component:
    return rx.el.button(
        rx.hstack(
            rx.box(
                rx.vstack(
                    _tier_pip(1, r.tier),
                    _tier_pip(2, r.tier),
                    spacing="0",
                    gap="2px",
                    align="center",
                ),
                padding_right="4px",
            ),
            rx.vstack(
                rx.text(r.description,
                        color=rx.cond(r.tier > 0, PAL["text"], PAL["subtext"]),
                        font_size="0.78rem",
                        font_weight=rx.cond(r.tier > 0, "700", "500"),
                        text_align="left",
                        line_height="1.3"),
                rx.cond(
                    r.tier > 0,
                    rx.text(r.formatted,
                            color=PAL["mauve"],
                            font_size="0.7rem",
                            font_style="italic",
                            text_align="left",
                            line_height="1.3"),
                    rx.box(),
                ),
                spacing="0",
                align="start",
                flex="1",
            ),
            rx.cond(
                r.is_damage,
                rx.icon(tag="flame", size=11, color=PAL["peach"]),
                rx.box(),
            ),
            spacing="2",
            width="100%",
            align="center",
        ),
        on_click=State.cycle_dormant(r.id),
        title="Click to cycle tier 1 → 2 → off",
        style={
            "background": rx.cond(r.tier > 0, "rgba(203,166,247,0.06)", PAL["crust"]),
            "border": "1px solid",
            "border_color": rx.cond(r.tier > 0, "rgba(203,166,247,0.35)", PAL["surface0"]),
            "border_left": rx.cond(
                r.is_damage,
                f"3px solid {PAL['peach']}",
                rx.cond(
                    r.tier > 0,
                    f"3px solid {PAL['mauve']}",
                    f"3px solid transparent",
                ),
            ),
            "padding": "6px 8px 6px 10px",
            "border_radius": "6px",
            "cursor": "pointer",
            "width": "100%",
            "text_align": "left",
            "transition": "all 0.12s",
        },
        _hover={
            "border_color": PAL["mauve"],
            "background": "rgba(203,166,247,0.04)",
        },
    )


def dormant_powers_list() -> rx.Component:
    """Full buff list for the sidebar accordion."""
    return rx.vstack(
        rx.hstack(
            rx.text("click rows to cycle tier",
                    color=PAL["overlay0"], font_size="0.68rem",
                    font_style="italic"),
            rx.spacer(),
            rx.cond(
                State.dormant_active_count > 0,
                rx.el.button(
                    rx.hstack(
                        rx.icon(tag="x", size=11),
                        rx.text(f"clear"),
                        spacing="1", align="center",
                    ),
                    on_click=State.clear_dormant,
                    style={
                        "background": "transparent",
                        "border": f"1px solid {PAL['surface1']}",
                        "color": PAL["subtext"],
                        "padding": "2px 8px",
                        "border_radius": "99px",
                        "font_size": "0.68rem",
                        "cursor": "pointer",
                    },
                ),
                rx.box(),
            ),
            width="100%",
            align="center",
        ),
        rx.box(
            rx.vstack(
                rx.foreach(State.dormant_power_rows, _row),
                spacing="1",
                width="100%",
            ),
            max_height="300px",
            overflow_y="auto",
            width="100%",
            padding_right="4px",
        ),
        width="100%",
        spacing="2",
        align="start",
    )


def dormant_summary_pill() -> rx.Component:
    """Small pill for the hero showing active count + damage mult."""
    return rx.cond(
        State.dormant_active_count > 0,
        rx.hstack(
            rx.icon(tag="sparkles", size=12, color=PAL["mauve"]),
            rx.text(State.dormant_summary_text,
                    color=PAL["mauve"],
                    font_size="0.72rem",
                    font_weight="700"),
            spacing="1", align="center",
            background="rgba(203,166,247,0.10)",
            border="1px solid rgba(203,166,247,0.3)",
            padding="2px 9px",
            border_radius="99px",
        ),
        rx.box(),
    )
