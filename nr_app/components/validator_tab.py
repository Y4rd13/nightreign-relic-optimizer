"""Validator tab — interactive single-relic builder with live rule checking."""

from __future__ import annotations

import reflex as rx

from ..state import State
from ..theme import PAL
from ..widgets import (
    attr_id_box,
    attr_sort,
    flag_badge,
    group_badge,
    tier_badge,
)


def _save_button() -> rx.Component:
    """Save-relic CTA. Visually affirmative when enabled, visibly greyed
    when blocked — tooltip spells out what's missing so the user doesn't
    have to hunt through the rule list."""
    enabled = State.v_can_save
    label = rx.cond(State.my_relic_editing_id != "", "Update relic", "Save relic")
    return rx.el.button(
        rx.hstack(
            rx.icon(tag="save", size=14),
            rx.text(label, font_weight="700"),
            spacing="1", align="center",
        ),
        on_click=rx.cond(enabled, State.open_save_relic_dialog, rx.noop()),
        title=rx.cond(enabled, "Save to My Relics", State.v_save_disabled_reason),
        disabled=~enabled,
        style={
            "background": rx.cond(enabled, PAL["green"], PAL["surface0"]),
            "border": "1px solid transparent",
            "color": rx.cond(enabled, PAL["crust"], PAL["overlay0"]),
            "padding": "8px 16px",
            "border_radius": "8px",
            "font_size": "0.84rem",
            "cursor": rx.cond(enabled, "pointer", "not-allowed"),
            "opacity": rx.cond(enabled, "1", "0.6"),
            "transition": "all 0.12s",
        },
        _hover={"background": rx.cond(enabled, PAL["teal"], PAL["surface0"])},
    )


def _tier_radio() -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.icon(tag="filter", size=16, color=PAL["overlay1"]),
            rx.text("Slot type (tier gate)",
                    color=PAL["overlay1"], font_size="0.78rem",
                    font_weight="600", letter_spacing="0.05em",
                    text_transform="uppercase"),
            spacing="2", align="center",
        ),
        rx.radio_group(
            ["common", "deep", "none"],
            value=State.v_slot_tier,
            on_change=State.set_v_tier,
            direction="row",
        ),
        rx.text(
            rx.cond(
                State.v_slot_tier == "common",
                "Common slot — only STD / BTH effects allowed.",
                rx.cond(
                    State.v_slot_tier == "deep",
                    "Deep of Night slot — only DoN / BTH effects allowed.",
                    "Tier gate disabled — any tier accepted.",
                ),
            ),
            color=PAL["overlay1"], font_size="0.78rem", margin_top="6px",
        ),
        padding="14px 16px",
        background=PAL["mantle"],
        margin_bottom="14px",
    )


def _attr_picker(idx: int, candidates) -> rx.Component:
    cur_eid = State.v_attr_ids[idx]
    return rx.card(
        rx.hstack(
            rx.text(f"Attr {idx + 1}",
                    color=PAL["lavender"], font_weight="700",
                    font_size="0.86rem"),
            rx.spacer(),
            rx.cond(
                cur_eid > 0,
                rx.el.button(
                    rx.icon(tag="x", size=14),
                    on_click=State.clear_v_attr(idx),
                    title="Clear",
                    style={
                        "background": "transparent",
                        "border": f"1px solid {PAL['surface1']}",
                        "color": PAL["red"],
                        "padding": "4px 8px",
                        "border_radius": "6px",
                        "cursor": "pointer",
                    },
                ),
                rx.box(),
            ),
            width="100%",
        ),
        rx.input(
            placeholder="id · tier · group · keyword",
            value=State.v_search[idx],
            on_change=lambda s: State.set_v_search(idx, s),
            width="100%",
            margin_top="8px",
        ),
        rx.box(
            rx.foreach(
                candidates,
                lambda opt: rx.el.button(
                    rx.hstack(
                        attr_id_box(opt.id),
                        attr_sort(opt.sort),
                        flag_badge(opt.flag),
                        tier_badge(opt.tier),
                        group_badge(opt.group),
                        rx.text(opt.name, color=PAL["text"],
                                font_size="0.84rem", flex="1",
                                text_align="left",
                                overflow="hidden",
                                text_overflow="ellipsis",
                                white_space="nowrap"),
                        spacing="2", align="center", width="100%",
                    ),
                    on_click=State.set_v_attr(idx, opt.id),
                    style={
                        "background": rx.cond(
                            opt.id == cur_eid,
                            "rgba(203,166,247,0.12)",
                            PAL["crust"],
                        ),
                        "border": f"1px solid {PAL['surface0']}",
                        "padding": "8px 12px",
                        "margin_bottom": "4px",
                        "border_radius": "6px",
                        "cursor": "pointer",
                        "width": "100%",
                        "text_align": "left",
                    },
                    _hover={"border_color": PAL["mauve"]},
                ),
            ),
            max_height="300px",
            overflow_y="auto",
            margin_top="8px",
            padding_right="4px",
        ),
        padding="12px 14px",
        background=PAL["mantle"],
        min_width="0",
    )


def _curse_picker() -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.icon(tag="shield_alert", size=16, color=PAL["red"]),
            rx.text("Debuff (CURSE)",
                    color=PAL["red"], font_weight="700",
                    font_size="0.86rem"),
            spacing="2", align="center",
        ),
        rx.select.root(
            rx.select.trigger(placeholder="— none —", width="100%"),
            rx.select.content(
                rx.foreach(
                    State.v_curse_options,
                    lambda c: rx.select.item(
                        rx.cond(c.id == 0, "— none —",
                                c.id.to_string() + " · " + c.name),
                        value=c.id.to_string(),
                    ),
                ),
            ),
            value=State.v_debuff_id.to_string(),
            on_change=lambda v: State.set_v_debuff(v),
            margin_top="8px",
        ),
        padding="12px 14px",
        background=PAL["mantle"],
    )


def _rule_row(r) -> rx.Component:
    icon = rx.cond(
        r.ok,
        rx.icon(tag="check", size=18, color=PAL["green"]),
        rx.cond(
            r.severity == "warning",
            rx.icon(tag="triangle_alert", size=18, color=PAL["yellow"]),
            rx.icon(tag="x", size=18, color=PAL["red"]),
        ),
    )
    border = rx.cond(
        r.ok,
        PAL["green"],
        rx.cond(r.severity == "warning", PAL["yellow"], PAL["red"]),
    )
    return rx.box(
        rx.hstack(
            icon,
            rx.text(r.rule, color=PAL["lavender"],
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                    font_size="0.76rem", font_weight="600",
                    min_width="140px"),
            rx.text(r.message, color=PAL["subtext"],
                    font_size="0.84rem", flex="1",
                    line_height="1.5"),
            spacing="2", align="start", width="100%",
        ),
        padding="8px 12px",
        margin_bottom="4px",
        background=PAL["crust"],
        border_radius="6px",
        border_left=f"3px solid {border}",
    )


def _summary_banner() -> rx.Component:
    return rx.box(
        rx.cond(
            State.v_is_valid,
            rx.hstack(
                rx.icon(tag="circle_check_big", size=24, color=PAL["green"]),
                rx.text("All hard rules pass — this relic is legal.",
                        color=PAL["green"], font_weight="700",
                        font_size="0.96rem"),
                spacing="2", align="center",
            ),
            rx.hstack(
                rx.icon(tag="circle_x", size=24, color=PAL["red"]),
                rx.text("One or more rules failed — see below.",
                        color=PAL["red"], font_weight="700",
                        font_size="0.96rem"),
                spacing="2", align="center",
            ),
        ),
        padding="12px 16px",
        border_radius="10px",
        background=rx.cond(
            State.v_is_valid,
            "rgba(166,227,161,0.08)",
            "rgba(243,139,168,0.08)",
        ),
        border="1px solid",
        border_color=rx.cond(
            State.v_is_valid,
            "rgba(166,227,161,0.4)",
            "rgba(243,139,168,0.4)",
        ),
        margin_bottom="12px",
    )


def validator_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Relic Validator", size="5", color=PAL["text"]),
                rx.text(
                    "Build a single relic and check every Nightreign rule — "
                    "sort order, roll groups, debuff linkage, tier gate, character tagging.",
                    color=PAL["overlay1"], font_size="0.86rem",
                ),
                spacing="1", align="start", flex="1",
            ),
            rx.hstack(
                rx.el.button(
                    rx.hstack(
                        rx.icon(tag="arrow_up_down", size=14),
                        rx.text("Auto-sort attrs", font_weight="600"),
                        spacing="1", align="center",
                    ),
                    on_click=State.v_auto_sort,
                    title="Reorder attrs to ascending sort_index (game's display rule)",
                    style={
                        "background": "transparent",
                        "border": f"1px solid {PAL['surface1']}",
                        "color": PAL["mauve"],
                        "padding": "8px 14px",
                        "border_radius": "8px",
                        "font_size": "0.84rem",
                        "cursor": "pointer",
                    },
                    _hover={"background": "rgba(203,166,247,0.08)"},
                ),
                rx.cond(
                    State.my_relic_editing_id != "",
                    rx.el.button(
                        rx.hstack(
                            rx.icon(tag="x", size=14),
                            rx.text("Cancel edit", font_weight="600"),
                            spacing="1", align="center",
                        ),
                        on_click=State.cancel_edit_my_relic,
                        title="Discard edits and clear validator",
                        style={
                            "background": "transparent",
                            "border": f"1px solid {PAL['surface1']}",
                            "color": PAL["subtext"],
                            "padding": "8px 14px",
                            "border_radius": "8px",
                            "font_size": "0.84rem",
                            "cursor": "pointer",
                        },
                    ),
                    rx.box(),
                ),
                _save_button(),
                spacing="2",
                align="center",
            ),
            width="100%",
            align="center",
            margin_bottom="16px",
        ),
        _tier_radio(),
        rx.heading("Attributes", size="4", color=PAL["text"],
                   margin_bottom="8px"),
        rx.grid(
            _attr_picker(0, State.v_candidate_options_0),
            _attr_picker(1, State.v_candidate_options_1),
            _attr_picker(2, State.v_candidate_options_2),
            columns="repeat(auto-fit, minmax(280px, 1fr))",
            gap="12px",
            width="100%",
            margin_bottom="16px",
        ),
        _curse_picker(),
        rx.divider(margin_y="16px"),
        _summary_banner(),
        rx.vstack(
            rx.foreach(State.v_results, _rule_row),
            width="100%",
            spacing="0",
        ),
        width="100%",
        align="start",
        spacing="2",
    )
