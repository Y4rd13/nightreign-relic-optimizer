"""Dialogs: edit attribute, pick named relic, save preset, exclusions list."""

from __future__ import annotations

import reflex as rx

from ..state import State
from ..theme import COLOR_SLOT, PAL
from ..widgets import (
    attr_id_box,
    attr_sort,
    color_pill,
    flag_badge,
    group_badge,
    tier_badge,
)


def _option_row(o) -> rx.Component:
    is_current = o.id == State.edit_current_id
    return rx.el.button(
        rx.vstack(
            rx.hstack(
                attr_id_box(o.id),
                attr_sort(o.sort),
                flag_badge(o.flag),
                tier_badge(o.tier),
                group_badge(o.group),
                rx.text(o.name, color=PAL["text"], font_size="0.88rem",
                        flex="1", text_align="left"),
                rx.cond(
                    is_current,
                    rx.box("current",
                           color=PAL["lavender"],
                           font_size="0.66rem", font_weight="700",
                           padding="1px 6px",
                           border_radius="3px",
                           background="rgba(180,190,254,0.12)",
                           border="1px solid rgba(180,190,254,0.3)"),
                    rx.box(),
                ),
                spacing="2", align="center", width="100%",
            ),
            rx.cond(
                o.effect_text != "",
                rx.text(o.effect_text,
                        color=PAL["overlay1"],
                        font_size="0.75rem",
                        font_style="italic",
                        text_align="left",
                        padding_left="4px"),
                rx.box(),
            ),
            spacing="1",
            width="100%",
            align="start",
        ),
        on_click=State.apply_edit(o.id),
        style={
            "background": rx.cond(
                is_current,
                "rgba(180,190,254,0.06)",
                PAL["crust"],
            ),
            "border": "1px solid",
            "border_color": rx.cond(is_current, PAL["lavender"], "transparent"),
            "padding": "10px 14px",
            "border_radius": "8px",
            "cursor": "pointer",
            "width": "100%",
            "text_align": "left",
            "transition": "all 0.12s",
        },
        _hover={
            "border_color": PAL["mauve"],
            "background": "rgba(203,166,247,0.08)",
        },
    )


def edit_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(State.edit_dialog_title, color=PAL["text"]),
            rx.dialog.description(
                "Search by id, tier, group, or any keyword. "
                "Click a row to replace — the rest of the build re-optimises around it.",
                color=PAL["overlay1"],
                font_size="0.82rem",
            ),
            rx.cond(
                State.edit_current_id > 0,
                rx.box(
                    rx.hstack(
                        rx.icon(tag="arrow_right", size=14, color=PAL["lavender"]),
                        rx.text("Currently in this attribute:",
                                color=PAL["overlay1"], font_size="0.76rem"),
                        rx.text(State.edit_current_name,
                                color=PAL["lavender"], font_size="0.8rem",
                                font_weight="600",
                                font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                                overflow="hidden",
                                text_overflow="ellipsis",
                                white_space="nowrap"),
                        spacing="2", align="center", width="100%",
                    ),
                    padding="6px 10px",
                    margin_top="8px",
                    background="rgba(180,190,254,0.06)",
                    border="1px solid rgba(180,190,254,0.22)",
                    border_radius="6px",
                ),
                rx.box(),
            ),
            rx.hstack(
                rx.input(
                    placeholder="id · tier · group · keyword…",
                    value=State.edit_search,
                    on_change=State.set_edit_search,
                    flex="1",
                ),
                rx.select(
                    State.edit_groups_available,
                    value=State.edit_group_filter,
                    on_change=State.set_edit_group,
                    width="180px",
                ),
                spacing="2",
                width="100%",
                margin_top="12px",
            ),
            rx.box(
                rx.foreach(State.edit_options, _option_row),
                margin_top="10px",
                max_height="55vh",
                overflow_y="auto",
                padding_right="4px",
                width="100%",
            ),
            rx.hstack(
                rx.dialog.close(
                    rx.el.button(
                        "Cancel",
                        on_click=State.close_edit,
                        style={
                            "background": "transparent",
                            "border": f"1px solid {PAL['surface1']}",
                            "color": PAL["subtext"],
                            "padding": "8px 16px",
                            "border_radius": "6px",
                            "cursor": "pointer",
                        },
                    ),
                ),
                rx.spacer(),
                justify="end",
                margin_top="12px",
                width="100%",
            ),
            max_width="720px",
            background=PAL["mantle"],
            color=PAL["text"],
        ),
        open=State.edit_dialog_open,
        on_open_change=State.on_edit_open_change,
    )


_SOURCE_COLORS = {
    "remembrance": "mauve",
    "shop": "peach",
    "boss_standard": "red",
    "boss_everdark": "lavender",
    "boss_dlc": "sky",
    "other": "overlay1",
}


def _source_badge(source_type) -> rx.Component:
    """Colored pill showing the relic's source category."""
    color = rx.match(
        source_type,
        ("remembrance", PAL["mauve"]),
        ("shop", PAL["peach"]),
        ("boss_standard", PAL["red"]),
        ("boss_everdark", PAL["lavender"]),
        ("boss_dlc", PAL["sky"]),
        ("other", PAL["overlay1"]),
        PAL["overlay0"],
    )
    label = rx.match(
        source_type,
        ("remembrance", "Remembrance"),
        ("shop", "Shop"),
        ("boss_standard", "Boss · Std"),
        ("boss_everdark", "Boss · Everdark"),
        ("boss_dlc", "Boss · DLC"),
        ("other", "Other"),
        "",
    )
    return rx.cond(
        source_type != "",
        rx.box(
            label,
            color=color,
            background="rgba(255,255,255,0.04)",
            border="1px solid",
            border_color=color,
            padding="1px 8px",
            border_radius="4px",
            font_size="0.66rem",
            font_weight="700",
            letter_spacing="0.04em",
        ),
        rx.box(),
    )


def _named_row(r) -> rx.Component:
    return rx.el.button(
        rx.hstack(
            color_pill(r.color),
            rx.vstack(
                rx.hstack(
                    rx.text(r.name, color=PAL["text"], font_weight="700",
                            font_size="0.92rem"),
                    _source_badge(r.source_type),
                    rx.cond(
                        r.verified,
                        rx.box("✓ attrs verified · locks",
                               color=PAL["green"], font_size="0.68rem",
                               font_weight="700", padding="1px 6px",
                               background="rgba(166,227,161,0.1)",
                               border_radius="3px"),
                        rx.box("⚠ unverified · info-only",
                               color=PAL["yellow"], font_size="0.68rem",
                               font_weight="700", padding="1px 6px",
                               background="rgba(249,226,175,0.08)",
                               border_radius="3px"),
                    ),
                    spacing="2", align="center", flex_wrap="wrap",
                ),
                rx.cond(
                    r.source_detail != "",
                    rx.text(r.source_detail,
                            color=PAL["overlay1"], font_size="0.72rem",
                            font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                            font_style="italic"),
                    rx.box(),
                ),
                rx.text(r.description, color=PAL["subtext"],
                        font_size="0.78rem", line_height="1.4"),
                spacing="1",
                align="start",
                flex="1",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        on_click=State.apply_named(r.id),
        style={
            "background": PAL["crust"],
            "border": "1px solid transparent",
            "padding": "10px 14px",
            "border_radius": "8px",
            "cursor": "pointer",
            "width": "100%",
            "text_align": "left",
            "transition": "all 0.12s",
        },
        _hover={
            "border_color": PAL["lavender"],
            "background": "rgba(180,190,254,0.06)",
        },
    )


_FILTER_LABELS = {
    "all": "All",
    "remembrance": "Remembrance",
    "shop": "Shop",
    "boss_standard": "Boss · Std",
    "boss_everdark": "Boss · Everdark",
    "boss_dlc": "Boss · DLC",
    "other": "Other",
}


def _filter_chip(f) -> rx.Component:
    active = f == State.named_source_filter
    label = rx.match(
        f,
        ("all", "All"),
        ("remembrance", "Remembrance"),
        ("shop", "Shop"),
        ("boss_standard", "Boss · Std"),
        ("boss_everdark", "Boss · Everdark"),
        ("boss_dlc", "Boss · DLC"),
        ("other", "Other"),
        "",
    )
    return rx.el.button(
        label,
        on_click=State.set_named_source_filter(f),
        style={
            "background": rx.cond(active, PAL["mauve"], "transparent"),
            "border": "1px solid",
            "border_color": rx.cond(active, PAL["mauve"], PAL["surface1"]),
            "color": rx.cond(active, PAL["crust"], PAL["subtext"]),
            "padding": "4px 12px",
            "border_radius": "99px",
            "font_size": "0.74rem",
            "font_weight": "700",
            "cursor": "pointer",
            "transition": "all 0.12s",
        },
    )


def named_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.text("Named Relic · Slot ", State.named_slot_idx + 1),
                color=PAL["text"],
            ),
            rx.dialog.description(
                "Pick a Remembrance quest reward, Jar Bazaar purchase, or Nightlord boss drop. "
                "Verified relics auto-lock their fixed attributes into this slot.",
                color=PAL["overlay1"],
                font_size="0.82rem",
            ),
            rx.el.button(
                "↺ Unlock this slot (let the solver pick freely)",
                on_click=State.apply_named("__unlock__"),
                style={
                    "background": "transparent",
                    "border": f"1px solid {PAL['surface1']}",
                    "color": PAL["subtext"],
                    "padding": "7px 12px",
                    "border_radius": "6px",
                    "font_size": "0.8rem",
                    "margin_top": "12px",
                    "cursor": "pointer",
                    "width": "100%",
                },
                _hover={"border_color": PAL["yellow"], "color": PAL["yellow"]},
            ),
            rx.box(
                rx.text("filter by source",
                        color=PAL["overlay0"], font_size="0.68rem",
                        font_weight="700",
                        letter_spacing="0.08em",
                        text_transform="uppercase",
                        margin_bottom="6px"),
                rx.flex(
                    rx.foreach(State.named_source_buckets, _filter_chip),
                    direction="row", wrap="wrap", gap="6px",
                ),
                margin_top="14px",
            ),
            rx.box(
                rx.vstack(
                    rx.foreach(State.named_relics_list, _named_row),
                    spacing="2",
                    width="100%",
                ),
                margin_top="10px",
                max_height="52vh",
                overflow_y="auto",
                padding_right="4px",
                width="100%",
            ),
            rx.hstack(
                rx.dialog.close(
                    rx.el.button(
                        "Close",
                        on_click=State.close_named,
                        style={
                            "background": "transparent",
                            "border": f"1px solid {PAL['surface1']}",
                            "color": PAL["subtext"],
                            "padding": "8px 16px",
                            "border_radius": "6px",
                            "cursor": "pointer",
                        },
                    ),
                ),
                rx.spacer(),
                justify="end",
                margin_top="12px",
                width="100%",
            ),
            max_width="720px",
            background=PAL["mantle"],
            color=PAL["text"],
        ),
        open=State.named_dialog_open,
        on_open_change=State.on_named_open_change,
    )


def _debuff_option_row(o) -> rx.Component:
    is_current = o.id == State.debuff_current_id
    return rx.el.button(
        rx.vstack(
            rx.hstack(
                attr_id_box(o.id),
                attr_sort(o.sort),
                tier_badge(o.tier),
                group_badge(o.group),
                rx.text(o.name, color=PAL["text"], font_size="0.88rem",
                        flex="1", text_align="left"),
                rx.cond(
                    is_current,
                    rx.box("current",
                           color=PAL["red"], font_size="0.66rem",
                           font_weight="700", padding="1px 6px",
                           border_radius="3px",
                           background="rgba(243,139,168,0.14)",
                           border="1px solid rgba(243,139,168,0.35)"),
                    rx.box(),
                ),
                spacing="2", align="center", width="100%",
            ),
            rx.cond(
                o.effect_text != "",
                rx.text(o.effect_text,
                        color=PAL["overlay1"], font_size="0.74rem",
                        font_style="italic",
                        text_align="left", padding_left="4px"),
                rx.box(),
            ),
            spacing="1", width="100%", align="start",
        ),
        on_click=State.apply_debuff(o.id),
        style={
            "background": rx.cond(is_current, "rgba(243,139,168,0.06)",
                                  PAL["crust"]),
            "border": "1px solid",
            "border_color": rx.cond(is_current, PAL["red"], "transparent"),
            "padding": "10px 14px",
            "border_radius": "8px",
            "cursor": "pointer",
            "width": "100%",
            "text_align": "left",
            "transition": "all 0.12s",
        },
        _hover={
            "border_color": PAL["red"],
            "background": "rgba(243,139,168,0.06)",
        },
    )


def debuff_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(State.debuff_dialog_title, color=PAL["text"]),
            rx.dialog.description(
                "Pick a curse to assign to this slot. Debuffs are only required "
                "when the slot contains at least one Y-flag effect, but you can "
                "still pin one explicitly — the solver keeps it through recompute.",
                color=PAL["overlay1"],
                font_size="0.82rem",
            ),
            rx.el.button(
                "↺ Clear user-pinned debuff (let the solver auto-pick)",
                on_click=State.apply_debuff(0),
                style={
                    "background": "transparent",
                    "border": f"1px solid {PAL['surface1']}",
                    "color": PAL["subtext"],
                    "padding": "7px 12px",
                    "border_radius": "6px",
                    "font_size": "0.8rem",
                    "margin_top": "12px",
                    "cursor": "pointer",
                    "width": "100%",
                },
                _hover={"border_color": PAL["yellow"], "color": PAL["yellow"]},
            ),
            rx.box(
                rx.vstack(
                    rx.foreach(State.debuff_options, _debuff_option_row),
                    spacing="2",
                    width="100%",
                ),
                margin_top="10px",
                max_height="55vh",
                overflow_y="auto",
                padding_right="4px",
                width="100%",
            ),
            rx.hstack(
                rx.dialog.close(
                    rx.el.button(
                        "Close",
                        on_click=State.close_debuff,
                        style={"background": "transparent",
                               "border": f"1px solid {PAL['surface1']}",
                               "color": PAL["subtext"],
                               "padding": "8px 16px",
                               "border_radius": "6px",
                               "cursor": "pointer"},
                    ),
                ),
                rx.spacer(),
                justify="end",
                margin_top="12px",
                width="100%",
            ),
            max_width="680px",
            background=PAL["mantle"],
            color=PAL["text"],
        ),
        open=State.debuff_dialog_open,
        on_open_change=State.on_debuff_open_change,
    )


def preset_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Save current build as preset",
                            color=PAL["text"]),
            rx.dialog.description(
                "Stored per-character in presets/presets.json. "
                "Use the Compare Presets tab to diff multiple saves.",
                color=PAL["overlay1"],
                font_size="0.82rem",
            ),
            rx.input(
                placeholder="e.g. evergaol-heavy",
                value=State.preset_name_input,
                on_change=State.set_preset_name,
                width="100%",
                margin_top="14px",
            ),
            rx.hstack(
                rx.dialog.close(
                    rx.el.button(
                        "Cancel",
                        on_click=State.close_preset,
                        style={"background": "transparent",
                               "border": f"1px solid {PAL['surface1']}",
                               "color": PAL["subtext"],
                               "padding": "8px 16px",
                               "border_radius": "6px",
                               "cursor": "pointer"},
                    ),
                ),
                rx.spacer(),
                rx.el.button(
                    "Save",
                    on_click=State.save_preset,
                    style={"background": PAL["mauve"],
                           "border": "1px solid transparent",
                           "color": PAL["crust"],
                           "padding": "8px 20px",
                           "border_radius": "6px",
                           "font_weight": "700",
                           "cursor": "pointer"},
                ),
                margin_top="14px",
                width="100%",
            ),
            max_width="480px",
            background=PAL["mantle"],
            color=PAL["text"],
        ),
        open=State.preset_dialog_open,
        on_open_change=State.on_preset_open_change,
    )
