"""Compendium — browsable reference DB (Effects / Relics / Characters / Bosses).

Loads from the same data files the optimizer uses, so it stays in sync without
duplicating content. Everything is read-only; no mutations flow from here.
"""

from __future__ import annotations

import reflex as rx

from ..state import (
    CompendiumBossRow,
    CompendiumCharacterRow,
    CompendiumEffectRow,
    CompendiumRelicRow,
    State,
)
from ..theme import COLOR_SLOT, PAL, bp
from ..widgets import group_badge, tier_badge


# ═════════════════════════════════════════════════════════════
# Shared helpers
# ═════════════════════════════════════════════════════════════
def _section_header(icon: str, title: str, count_var=None) -> rx.Component:
    children = [
        rx.icon(tag=icon, size=20, color=PAL["mauve"]),
        rx.heading(title, size="5", color=PAL["text"]),
    ]
    if count_var is not None:
        children.append(
            rx.box(
                count_var,
                color=PAL["mauve"],
                background="rgba(203,166,247,0.12)",
                border="1px solid rgba(203,166,247,0.3)",
                padding="1px 10px",
                border_radius="99px",
                font_size="0.78rem",
                font_weight="700",
            )
        )
    return rx.hstack(*children, spacing="2", align="center", margin_bottom="12px")


def _filter_pill(
    label: str, value: str, active_var, on_click, small: bool = True
) -> rx.Component:
    active = active_var == value
    return rx.el.button(
        label,
        on_click=lambda: on_click(value),
        style={
            "background": rx.cond(active, PAL["mauve"], "transparent"),
            "color": rx.cond(active, PAL["crust"], PAL["subtext"]),
            "border": rx.cond(
                active, "1px solid transparent", f"1px solid {PAL['surface1']}"
            ),
            "padding": "4px 12px" if small else "6px 14px",
            "border_radius": "99px",
            "font_size": "0.76rem" if small else "0.82rem",
            "font_weight": "600",
            "cursor": "pointer",
            "transition": "all 0.12s",
        },
        _hover={"border_color": PAL["mauve"], "color": PAL["text"]},
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
        box_shadow=rx.cond(color_code != "", f"0 0 6px {fill}66", "none"),
    )


# ═════════════════════════════════════════════════════════════
# Effects sub-tab
# ═════════════════════════════════════════════════════════════
def _effect_row(e: CompendiumEffectRow) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(
                    "#" + e.effect_id.to_string(),
                    color=PAL["overlay1"],
                    font_size="0.7rem",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                    min_width="70px",
                ),
                tier_badge(e.tier),
                group_badge(e.group),
                rx.cond(
                    e.character_tag != "",
                    rx.box(
                        e.character_tag,
                        color=PAL["lavender"],
                        font_size="0.66rem",
                        font_weight="700",
                        padding="2px 8px",
                        border_radius="4px",
                        background="rgba(180,190,254,0.12)",
                        border="1px solid rgba(180,190,254,0.25)",
                    ),
                    rx.box(),
                ),
                rx.cond(
                    e.category != "",
                    rx.box(
                        e.category,
                        color=PAL["subtext"],
                        font_size="0.7rem",
                        font_style="italic",
                    ),
                    rx.box(),
                ),
                rx.spacer(),
                rx.cond(
                    e.stackable,
                    rx.box(
                        "stackable",
                        color=PAL["green"],
                        font_size="0.66rem",
                        font_weight="700",
                        padding="2px 7px",
                        border_radius="4px",
                        background="rgba(166,227,161,0.10)",
                    ),
                    rx.box(),
                ),
                spacing="2", align="center", width="100%",
            ),
            rx.text(
                e.name,
                color=PAL["text"], font_weight="700", font_size="0.92rem",
            ),
            rx.cond(
                e.effect_text != "",
                rx.text(
                    e.effect_text,
                    color=PAL["overlay1"], font_size="0.8rem",
                    line_height="1.45",
                ),
                rx.box(),
            ),
            spacing="1", align="start", width="100%",
        ),
        background=PAL["mantle"],
        border=f"1px solid {PAL['surface0']}",
        border_radius="8px",
        padding="10px 14px",
        width="100%",
    )


def _effects_filters() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.input(
                placeholder="Search effects by name…",
                value=State.cmp_effects_search,
                on_change=State.set_cmp_effects_search,
                style={
                    "background": PAL["crust"],
                    "border": f"1px solid {PAL['surface0']}",
                    "color": PAL["text"],
                    "padding": "8px 12px",
                    "border_radius": "6px",
                    "width": "100%",
                    "font_size": "0.88rem",
                },
            ),
            width="100%",
        ),
        rx.hstack(
            rx.text("Category:", color=PAL["overlay1"],
                    font_size="0.78rem", font_weight="600", margin_right="4px"),
            rx.foreach(
                State.cmp_effects_categories,
                lambda c: _filter_pill(
                    c, c, State.cmp_effects_category,
                    State.set_cmp_effects_category,
                ),
            ),
            spacing="1", align="center", flex_wrap="wrap", width="100%",
        ),
        spacing="2", width="100%", margin_bottom="10px",
    )


def _effects_pager() -> rx.Component:
    return rx.hstack(
        rx.text(State.cmp_effects_page_info,
                color=PAL["overlay1"], font_size="0.78rem"),
        rx.spacer(),
        rx.el.button(
            rx.icon(tag="chevron_left", size=14),
            on_click=State.cmp_effects_prev_page,
            disabled=State.cmp_effects_page == 0,
            style={
                "background": "transparent",
                "border": f"1px solid {PAL['surface1']}",
                "color": PAL["subtext"],
                "padding": "6px 10px",
                "border_radius": "6px",
                "cursor": rx.cond(State.cmp_effects_page == 0, "not-allowed", "pointer"),
                "opacity": rx.cond(State.cmp_effects_page == 0, "0.4", "1"),
            },
        ),
        rx.el.button(
            rx.icon(tag="chevron_right", size=14),
            on_click=State.cmp_effects_next_page,
            disabled=~State.cmp_effects_has_next,
            style={
                "background": "transparent",
                "border": f"1px solid {PAL['surface1']}",
                "color": PAL["subtext"],
                "padding": "6px 10px",
                "border_radius": "6px",
                "cursor": rx.cond(State.cmp_effects_has_next, "pointer", "not-allowed"),
                "opacity": rx.cond(State.cmp_effects_has_next, "1", "0.4"),
            },
        ),
        align="center", width="100%", padding="8px 0",
    )


def _effects_subtab() -> rx.Component:
    return rx.vstack(
        _section_header("zap", "Effects", State.cmp_effects_total_count),
        rx.text(
            "Every relic effect in the Cheat Engine registry. Search by name, "
            "filter by category, paginate. Rich descriptions (where available) "
            "come from the community compendium.",
            color=PAL["overlay1"], font_size="0.85rem",
            margin_bottom="12px",
        ),
        _effects_filters(),
        _effects_pager(),
        rx.vstack(
            rx.foreach(State.cmp_effects_filtered, _effect_row),
            spacing="2", width="100%",
        ),
        _effects_pager(),
        width="100%", spacing="2", align="start",
    )


# ═════════════════════════════════════════════════════════════
# Relics sub-tab
# ═════════════════════════════════════════════════════════════
_SOURCE_LABEL = {
    "all": "All",
    "shop": "Shop",
    "remembrance": "Remembrance",
    "boss_everdark": "Everdark boss",
    "other": "Other",
}

_COLOR_LABEL = {
    "all": "All",
    "R": "Red",
    "G": "Green",
    "B": "Blue",
    "Y": "Yellow",
    "U": "Any",
}


def _relic_card(r: CompendiumRelicRow) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                _color_dot(r.color),
                rx.text(r.name,
                        color=PAL["text"], font_weight="700", font_size="0.94rem",
                        flex="1"),
                rx.box(
                    r.source_type,
                    color=PAL["mauve"],
                    font_size="0.64rem",
                    font_weight="700",
                    letter_spacing="0.05em",
                    padding="2px 8px",
                    border_radius="4px",
                    background="rgba(203,166,247,0.12)",
                    border="1px solid rgba(203,166,247,0.3)",
                ),
                spacing="2", align="center", width="100%",
            ),
            rx.cond(
                r.description != "",
                rx.text(r.description, color=PAL["subtext"],
                        font_size="0.78rem", font_style="italic"),
                rx.box(),
            ),
            rx.vstack(
                rx.foreach(
                    r.attr_names,
                    lambda n, i: rx.hstack(
                        rx.text("#" + r.attr_ids[i].to_string(),
                                color=PAL["sky"], font_size="0.7rem",
                                font_weight="700",
                                font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                                min_width="60px"),
                        rx.text(n, color=PAL["subtext"], font_size="0.78rem"),
                        spacing="2", align="center", width="100%",
                    ),
                ),
                spacing="0", align="start", width="100%",
                padding="6px 10px",
                background=PAL["crust"],
                border_radius="6px",
                border=f"1px solid {PAL['surface0']}",
            ),
            rx.cond(
                r.source_detail != "",
                rx.text(r.source_detail,
                        color=PAL["overlay1"], font_size="0.72rem"),
                rx.box(),
            ),
            spacing="2", align="start", width="100%",
        ),
        background=PAL["mantle"],
        border=f"1px solid {PAL['surface0']}",
        border_radius="10px",
        padding="12px 14px",
        transition="border-color 0.12s",
        _hover={"border_color": PAL["mauve"]},
    )


def _relics_filters() -> rx.Component:
    return rx.vstack(
        rx.input(
            placeholder="Search relics by name or effect…",
            value=State.cmp_relics_search,
            on_change=State.set_cmp_relics_search,
            style={
                "background": PAL["crust"],
                "border": f"1px solid {PAL['surface0']}",
                "color": PAL["text"],
                "padding": "8px 12px",
                "border_radius": "6px",
                "width": "100%",
                "font_size": "0.88rem",
            },
        ),
        rx.hstack(
            rx.text("Source:", color=PAL["overlay1"],
                    font_size="0.78rem", font_weight="600"),
            *[
                _filter_pill(
                    label, key, State.cmp_relics_source,
                    State.set_cmp_relics_source,
                )
                for key, label in _SOURCE_LABEL.items()
            ],
            spacing="1", align="center", flex_wrap="wrap", width="100%",
        ),
        rx.hstack(
            rx.text("Color:", color=PAL["overlay1"],
                    font_size="0.78rem", font_weight="600"),
            *[
                _filter_pill(
                    label, key, State.cmp_relics_color,
                    State.set_cmp_relics_color,
                )
                for key, label in _COLOR_LABEL.items()
            ],
            spacing="1", align="center", flex_wrap="wrap", width="100%",
        ),
        spacing="2", width="100%", margin_bottom="10px",
    )


def _relics_subtab() -> rx.Component:
    return rx.vstack(
        _section_header("gem", "Named Relics", State.cmp_relics_filtered.length()),
        rx.text(
            "Hand-crafted relics from the game — Remembrance rewards, Small Jar "
            "Bazaar shops, and Everdark boss drops. Random/procedural relics "
            "rolled during expeditions are NOT in this list.",
            color=PAL["overlay1"], font_size="0.85rem",
            margin_bottom="12px",
        ),
        _relics_filters(),
        rx.grid(
            rx.foreach(State.cmp_relics_filtered, _relic_card),
            columns=bp("1", "repeat(auto-fit, minmax(360px, 1fr))"),
            gap="12px",
            width="100%",
        ),
        width="100%", spacing="2", align="start",
    )


# ═════════════════════════════════════════════════════════════
# Characters sub-tab
# ═════════════════════════════════════════════════════════════
def _ability_block(label: str, name, desc, color: str) -> rx.Component:
    return rx.vstack(
        rx.text(label.upper(),
                color=PAL["overlay1"], font_size="0.62rem",
                letter_spacing="0.1em", font_weight="700"),
        rx.text(name, color=color, font_weight="700", font_size="0.88rem"),
        rx.text(desc, color=PAL["subtext"], font_size="0.76rem",
                line_height="1.4"),
        spacing="1", align="start", width="100%",
    )


def _character_card(c: CompendiumCharacterRow) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(c.icon, font_size="1.8rem"),
                rx.vstack(
                    rx.text(c.name,
                            color=PAL["text"], font_weight="800", font_size="1.1rem"),
                    rx.text(c.tagline, color=PAL["subtext"],
                            font_size="0.78rem", font_style="italic"),
                    spacing="0", align="start", flex="1",
                ),
                rx.cond(
                    c.data_quality == "full",
                    rx.box("tuned", color=PAL["green"], font_size="0.64rem",
                           font_weight="700", letter_spacing="0.05em",
                           padding="2px 7px", border_radius="4px",
                           background="rgba(166,227,161,0.10)"),
                    rx.box("skeleton", color=PAL["yellow"], font_size="0.64rem",
                           font_weight="700", letter_spacing="0.05em",
                           padding="2px 7px", border_radius="4px",
                           background="rgba(249,226,175,0.10)"),
                ),
                spacing="3", align="center", width="100%",
            ),
            rx.divider(border_color=PAL["surface0"]),
            _ability_block("Skill", c.skill_name, c.skill_desc, PAL["mauve"]),
            _ability_block("Ultimate", c.ultimate_name, c.ultimate_desc, PAL["peach"]),
            _ability_block("Passive", c.passive_name, c.passive_desc, PAL["teal"]),
            rx.divider(border_color=PAL["surface0"]),
            rx.hstack(
                rx.text("WEAPONS",
                        color=PAL["overlay1"], font_size="0.62rem",
                        letter_spacing="0.1em", font_weight="700"),
                rx.cond(
                    c.dual_wield,
                    rx.box("dual-wield", color=PAL["sky"], font_size="0.64rem",
                           font_weight="700", padding="2px 7px",
                           border_radius="4px",
                           background="rgba(137,220,235,0.10)"),
                    rx.box(),
                ),
                spacing="2", align="center",
            ),
            rx.hstack(
                rx.foreach(
                    c.weapon_types,
                    lambda w: rx.box(
                        w.replace("_", " "),
                        color=PAL["subtext"], font_size="0.74rem",
                        padding="2px 8px", border_radius="4px",
                        background=PAL["surface0"],
                    ),
                ),
                spacing="1", align="center", flex_wrap="wrap",
            ),
            rx.cond(
                c.remembrance_name != "",
                rx.vstack(
                    rx.text("REMEMBRANCE",
                            color=PAL["overlay1"], font_size="0.62rem",
                            letter_spacing="0.1em", font_weight="700"),
                    rx.text(c.remembrance_name,
                            color=PAL["lavender"], font_size="0.82rem",
                            font_weight="700"),
                    spacing="1", align="start",
                ),
                rx.box(),
            ),
            spacing="3", align="start", width="100%",
        ),
        background=PAL["mantle"],
        border=f"1px solid {PAL['surface0']}",
        border_radius="12px",
        padding="16px 18px",
        transition="border-color 0.12s",
        _hover={"border_color": PAL["mauve"]},
    )


def _characters_subtab() -> rx.Component:
    return rx.vstack(
        _section_header("users", "Nightfarers", State.cmp_characters.length()),
        rx.text(
            "The 10 playable Nightfarers with their Character Skill, Ultimate "
            "Art, Passive, and allowed weapon categories. '[tuned]' characters "
            "have fully modeled damage profiles in the solver; 'skeleton' ones "
            "use baseline metadata only.",
            color=PAL["overlay1"], font_size="0.85rem",
            margin_bottom="12px",
        ),
        rx.grid(
            rx.foreach(State.cmp_characters, _character_card),
            columns=bp("1", "repeat(auto-fit, minmax(380px, 1fr))"),
            gap="14px",
            width="100%",
        ),
        width="100%", spacing="2", align="start",
    )


# ═════════════════════════════════════════════════════════════
# Bosses sub-tab
# ═════════════════════════════════════════════════════════════
def _boss_row(b: CompendiumBossRow) -> rx.Component:
    threat_color = rx.match(
        b.threat,
        ("Small", PAL["green"]),
        ("Medium", PAL["yellow"]),
        ("Large", PAL["peach"]),
        ("Night", PAL["red"]),
        PAL["overlay0"],
    )
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(b.name,
                        color=PAL["text"], font_weight="700", font_size="0.92rem"),
                rx.cond(
                    (b.type != "") | (b.threat != ""),
                    rx.hstack(
                        rx.text(b.type, color=PAL["mauve"], font_size="0.72rem",
                                font_weight="600"),
                        rx.cond(
                            (b.type != "") & (b.threat != ""),
                            rx.text("·", color=PAL["overlay0"]),
                            rx.box(),
                        ),
                        rx.text(b.threat, color=threat_color, font_size="0.72rem",
                                font_weight="600"),
                        spacing="1", align="center",
                    ),
                    rx.box(),
                ),
                rx.cond(
                    b.notes != "",
                    rx.text(b.notes, color=PAL["overlay1"],
                            font_size="0.74rem", font_style="italic"),
                    rx.box(),
                ),
                spacing="1", align="start", flex="1",
            ),
            rx.vstack(
                rx.text("ID", color=PAL["overlay1"], font_size="0.58rem",
                        letter_spacing="0.08em"),
                rx.text(b.id.to_string(),
                        color=PAL["subtext"], font_size="0.72rem",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                spacing="0", align="end", min_width="90px",
            ),
            spacing="3", align="start", width="100%",
        ),
        background=PAL["mantle"],
        border=f"1px solid {PAL['surface0']}",
        border_radius="8px",
        padding="10px 14px",
        width="100%",
    )


def _bosses_filters() -> rx.Component:
    return rx.vstack(
        rx.input(
            placeholder="Search bosses by name…",
            value=State.cmp_bosses_search,
            on_change=State.set_cmp_bosses_search,
            style={
                "background": PAL["crust"],
                "border": f"1px solid {PAL['surface0']}",
                "color": PAL["text"],
                "padding": "8px 12px",
                "border_radius": "6px",
                "width": "100%",
                "font_size": "0.88rem",
            },
        ),
        rx.hstack(
            rx.text("Type:", color=PAL["overlay1"],
                    font_size="0.78rem", font_weight="600"),
            rx.foreach(
                State.cmp_boss_types,
                lambda t: _filter_pill(
                    t, t, State.cmp_bosses_type, State.set_cmp_bosses_type,
                ),
            ),
            spacing="1", align="center", flex_wrap="wrap", width="100%",
        ),
        spacing="2", width="100%", margin_bottom="10px",
    )


def _bosses_subtab() -> rx.Component:
    return rx.vstack(
        _section_header("skull", "Bosses", State.cmp_bosses_filtered.length()),
        rx.callout(
            rx.text(
                "HP tiers, elemental resistances / weaknesses, and Deep-of-Night "
                "scaling are NOT yet in our data. Names, types, and threat "
                "levels only for now. Coming soon.",
                font_size="0.8rem",
            ),
            icon="info", color_scheme="gray", width="100%",
            margin_bottom="12px",
        ),
        _bosses_filters(),
        rx.vstack(
            rx.foreach(State.cmp_bosses_filtered, _boss_row),
            spacing="2", width="100%",
        ),
        width="100%", spacing="2", align="start",
    )


# ═════════════════════════════════════════════════════════════
# Shell
# ═════════════════════════════════════════════════════════════
def _sub_tab_trigger(value: str, icon: str, label: str) -> rx.Component:
    return rx.tabs.trigger(
        rx.icon(tag=icon, size=14, style={"margin_right": "6px",
                                           "display": "inline-block",
                                           "vertical_align": "middle"}),
        label,
        value=value,
        style={
            "padding": "8px 14px",
            "border_radius": "6px 6px 0 0",
            "cursor": "pointer",
            "font_size": "0.84rem",
            "font_weight": "600",
            "display": "inline-flex",
            "align_items": "center",
        },
    )


def compendium_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon(tag="book_open", size=22, color=PAL["mauve"]),
            rx.heading("Compendium", size="5", color=PAL["text"]),
            spacing="2", align="center",
        ),
        rx.text(
            "Browsable reference database for effects, named relics, "
            "Nightfarers, and bosses. All data read-only — for theorycrafting "
            "and lookup.",
            color=PAL["overlay1"], font_size="0.86rem",
            margin_bottom="14px",
        ),
        rx.tabs.root(
            rx.tabs.list(
                _sub_tab_trigger("effects", "zap", "Effects"),
                _sub_tab_trigger("relics", "gem", "Relics"),
                _sub_tab_trigger("characters", "users", "Nightfarers"),
                _sub_tab_trigger("bosses", "skull", "Bosses"),
                style={
                    "gap": "6px",
                    "flex_wrap": "wrap",
                    "border_bottom": f"1px solid {PAL['surface0']}",
                    "margin_bottom": "14px",
                    "padding_bottom": "2px",
                },
            ),
            rx.tabs.content(_effects_subtab(), value="effects"),
            rx.tabs.content(_relics_subtab(), value="relics"),
            rx.tabs.content(_characters_subtab(), value="characters"),
            rx.tabs.content(_bosses_subtab(), value="bosses"),
            value=State.compendium_sub_tab,
            on_change=State.set_compendium_sub_tab,
            default_value="effects",
        ),
        width="100%", align="start", spacing="2",
    )
