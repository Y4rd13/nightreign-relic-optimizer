"""My Relics tab — personal inventory of saved single relics.

Each card renders the relic as it would appear in-game: vessel-colour dot,
slot-tier badge, attrs in sort_index order, optional debuff, plus Edit /
Delete actions. Relics that reference character-tagged effects for a
different Nightfarer are greyed out (can't be applied to the current
character) but still listed — the inventory is global."""

from __future__ import annotations

import reflex as rx

from ..state import State
from ..theme import COLOR_SLOT, PAL


def _empty_state() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon(tag="package_open", size=48, color=PAL["overlay0"]),
            rx.heading("No relics saved yet", size="5", color=PAL["subtext"]),
            rx.text(
                "Open the Validator tab, build a relic you've rolled in-game, "
                "pick Common or Deep tier, and hit 'Save relic'. Saved relics "
                "appear here and in the Named Relic picker on every slot.",
                color=PAL["overlay1"], font_size="0.92rem",
                text_align="center", max_width="520px",
                line_height="1.5",
            ),
            spacing="3", align="center",
        ),
        padding="80px 20px",
        width="100%",
    )


def _color_dot(color_code) -> rx.Component:
    fill = rx.match(
        color_code,
        ("R", COLOR_SLOT["R"][1]),
        ("G", COLOR_SLOT["G"][1]),
        ("B", COLOR_SLOT["B"][1]),
        ("Y", COLOR_SLOT["Y"][1]),
        ("U", COLOR_SLOT["U"][1]),
        PAL["overlay0"],
    )
    return rx.box(
        width="10px", height="10px", border_radius="50%",
        background=fill, flex_shrink="0",
        box_shadow=f"0 0 6px {fill}",
    )


def _tier_pill(slot_tier) -> rx.Component:
    color = rx.cond(slot_tier == "deep", PAL["mauve"], PAL["teal"])
    label = rx.cond(slot_tier == "deep", "Deep", "Common")
    return rx.box(
        label,
        color=color,
        background="rgba(255,255,255,0.03)",
        border="1px solid",
        border_color=color,
        padding="1px 8px",
        border_radius="4px",
        font_size="0.68rem",
        font_weight="700",
        letter_spacing="0.04em",
    )


def _attr_line(aid, aname) -> rx.Component:
    return rx.hstack(
        rx.text(aid.to_string(),
                color=PAL["sky"], font_size="0.74rem", font_weight="700",
                font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                min_width="62px"),
        rx.text(aname,
                color=PAL["subtext"], font_size="0.8rem",
                overflow="hidden", text_overflow="ellipsis",
                white_space="nowrap", flex="1"),
        spacing="2", align="center", width="100%",
    )


def _relic_card(r) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                _color_dot(r.color),
                rx.text(r.name,
                        color=PAL["text"], font_weight="800",
                        font_size="1rem", flex="1",
                        overflow="hidden", text_overflow="ellipsis",
                        white_space="nowrap"),
                _tier_pill(r.slot_tier),
                spacing="2", align="center", width="100%",
            ),
            rx.cond(
                ~r.usable_on_current_character,
                rx.box(
                    rx.hstack(
                        rx.icon(tag="circle_alert", size=12, color=PAL["yellow"]),
                        rx.text(
                            "Has effects tagged for another Nightfarer — can't apply here.",
                            color=PAL["yellow"], font_size="0.72rem",
                        ),
                        spacing="1", align="center",
                    ),
                    padding="4px 8px", border_radius="6px",
                    background="rgba(249,226,175,0.08)",
                    border="1px solid rgba(249,226,175,0.25)",
                    width="100%",
                ),
                rx.box(),
            ),
            rx.vstack(
                rx.foreach(
                    r.attr_ids,
                    lambda aid, i: _attr_line(aid, r.attr_names[i]),
                ),
                rx.cond(
                    r.debuff_id > 0,
                    rx.hstack(
                        rx.text(r.debuff_id.to_string(),
                                color=PAL["red"], font_size="0.72rem",
                                font_weight="700",
                                font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                                min_width="62px"),
                        rx.text(r.debuff_name,
                                color="rgba(243,139,168,0.75)",
                                font_size="0.76rem", font_style="italic",
                                overflow="hidden", text_overflow="ellipsis",
                                white_space="nowrap", flex="1"),
                        spacing="2", align="center", width="100%",
                    ),
                    rx.box(),
                ),
                spacing="1", align="start", width="100%",
                padding="8px 10px",
                background=PAL["crust"],
                border="1px solid",
                border_color=PAL["surface0"],
                border_radius="6px",
            ),
            rx.hstack(
                rx.el.button(
                    rx.hstack(
                        rx.icon(tag="pencil", size=12),
                        rx.text("Edit", font_weight="700", font_size="0.78rem"),
                        spacing="1", align="center",
                    ),
                    on_click=State.edit_my_relic(r.id),
                    title="Load into Validator to edit",
                    style={
                        "background": "transparent",
                        "border": f"1px solid {PAL['surface1']}",
                        "color": PAL["lavender"],
                        "padding": "6px 12px",
                        "border_radius": "6px",
                        "cursor": "pointer",
                        "flex": "1",
                    },
                    _hover={"border_color": PAL["lavender"]},
                ),
                rx.el.button(
                    rx.icon(tag="trash_2", size=12),
                    on_click=State.delete_my_relic(r.id),
                    title="Delete relic",
                    style={
                        "background": "transparent",
                        "border": f"1px solid {PAL['surface1']}",
                        "color": PAL["red"],
                        "padding": "6px 10px",
                        "border_radius": "6px",
                        "cursor": "pointer",
                    },
                    _hover={
                        "background": "rgba(243,139,168,0.08)",
                        "border_color": PAL["red"],
                    },
                ),
                spacing="2", width="100%", padding_top="4px",
            ),
            rx.text(
                "Saved " + r.updated_at,
                color=PAL["overlay0"], font_size="0.68rem",
                font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
            ),
            spacing="2", align="start", width="100%",
        ),
        background=PAL["mantle"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_radius="12px",
        padding="12px 14px",
        opacity=rx.cond(r.usable_on_current_character, "1", "0.75"),
        transition="all 0.12s",
        _hover={"border_color": PAL["mauve"]},
    )


def my_relics_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon(tag="package", size=22, color=PAL["mauve"]),
            rx.heading("My relics", size="5", color=PAL["text"]),
            rx.cond(
                State.my_relics_list.length() > 0,
                rx.box(
                    State.my_relics_list.length(),
                    color=PAL["mauve"],
                    background="rgba(203,166,247,0.12)",
                    border="1px solid rgba(203,166,247,0.3)",
                    padding="1px 10px",
                    border_radius="99px",
                    font_size="0.78rem",
                    font_weight="700",
                ),
                rx.box(),
            ),
            spacing="2", align="center",
        ),
        rx.text(
            "Single relics you've saved from the Validator. Pickable from "
            "the Named Relic dialog on every slot — stored globally across "
            "all characters at user_data/my_relics.json.",
            color=PAL["overlay1"], font_size="0.86rem",
            margin_bottom="14px",
        ),
        rx.cond(
            State.my_relics_list.length() == 0,
            _empty_state(),
            rx.grid(
                rx.foreach(State.my_relics_list, _relic_card),
                columns="repeat(auto-fit, minmax(340px, 1fr))",
                gap="14px",
                width="100%",
            ),
        ),
        width="100%",
        align="start",
        spacing="2",
    )
