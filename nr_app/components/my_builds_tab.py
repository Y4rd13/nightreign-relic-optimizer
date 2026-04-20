"""My builds tab — rich cards with slot/vessel/character info + Load/Delete."""

from __future__ import annotations

import reflex as rx

from ..state import State
from ..theme import COLOR_SLOT, PAL
from ..widgets import build_type_pill


def _empty_state() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.icon(tag="bookmark", size=48, color=PAL["overlay0"]),
            rx.heading("No builds saved yet", size="5", color=PAL["subtext"]),
            rx.text(
                "Tune sliders, locks, vessel, and dormant powers to your liking, "
                "then click 'Save current build' in the sidebar. Saved builds "
                "show up here and survive docker rebuilds.",
                color=PAL["overlay1"], font_size="0.92rem",
                text_align="center", max_width="520px",
                line_height="1.5",
            ),
            spacing="3",
            align="center",
        ),
        padding="80px 20px",
        width="100%",
    )


def _stat_block(label: str, value, color: str = None) -> rx.Component:
    return rx.vstack(
        rx.text(label.upper(),
                color=PAL["overlay1"], font_size="0.62rem",
                letter_spacing="0.08em", font_weight="700"),
        rx.text(value,
                color=color or PAL["text"], font_size="0.9rem",
                font_weight="700",
                font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
        spacing="0", align="start", min_width="68px",
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
        width="8px", height="8px", border_radius="50%",
        background=fill, flex_shrink="0",
        box_shadow=rx.cond(color_code != "", f"0 0 4px {fill}", "none"),
    )


def _attr_line(aid, aname) -> rx.Component:
    return rx.hstack(
        rx.text(aid.to_string(),
                color=PAL["sky"], font_size="0.72rem", font_weight="700",
                font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                min_width="58px"),
        rx.text(aname,
                color=PAL["subtext"], font_size="0.78rem",
                overflow="hidden", text_overflow="ellipsis",
                white_space="nowrap", flex="1"),
        spacing="2", align="center", width="100%",
    )


def _slot_block(slot) -> rx.Component:
    return rx.box(
        rx.hstack(
            _color_dot(slot.vessel_color),
            rx.text(f"Slot ", color=PAL["overlay1"], font_size="0.7rem",
                    display="inline"),
            rx.text(slot.index + 1,
                    color=PAL["text"], font_weight="700",
                    font_size="0.74rem", display="inline"),
            rx.text("·", color=PAL["overlay0"], font_size="0.7rem"),
            rx.text(slot.name,
                    color=PAL["overlay1"], font_size="0.72rem",
                    font_style="italic",
                    overflow="hidden", text_overflow="ellipsis",
                    white_space="nowrap", flex="1"),
            spacing="1", align="center", width="100%", margin_bottom="4px",
        ),
        rx.vstack(
            rx.foreach(
                slot.attr_ids,
                lambda aid, i: _attr_line(aid, slot.attr_names[i]),
            ),
            rx.cond(
                slot.debuff_id > 0,
                rx.hstack(
                    rx.text(slot.debuff_id.to_string(),
                            color=PAL["red"], font_size="0.7rem",
                            font_weight="700",
                            font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                            min_width="58px"),
                    rx.text(slot.debuff_name,
                            color="rgba(243,139,168,0.75)", font_size="0.74rem",
                            font_style="italic",
                            overflow="hidden", text_overflow="ellipsis",
                            white_space="nowrap", flex="1"),
                    spacing="2", align="center", width="100%",
                ),
                rx.box(),
            ),
            spacing="1", align="start", width="100%",
        ),
        background=PAL["crust"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_radius="6px",
        padding="6px 10px 8px",
    )


def _slots_grid(preset) -> rx.Component:
    return rx.grid(
        rx.foreach(preset.slots, _slot_block),
        columns="repeat(auto-fit, minmax(240px, 1fr))",
        gap="6px",
        width="100%",
    )


def _build_card(preset) -> rx.Component:
    return rx.box(
        rx.vstack(
            # Header — name + damage
            rx.hstack(
                rx.checkbox(
                    checked=State.selected_build_names.contains(preset.name),
                    on_change=lambda _v: State.toggle_build_selected(preset.name),
                    title="Select for export",
                ),
                rx.hstack(
                    rx.text(preset.character_icon, font_size="1.1rem"),
                    rx.text(preset.name,
                            color=PAL["text"], font_weight="800",
                            font_size="1.06rem",
                            overflow="hidden", text_overflow="ellipsis",
                            white_space="nowrap"),
                    build_type_pill(preset.build_type, small=True),
                    spacing="2", align="center", flex="1",
                ),
                rx.vstack(
                    rx.text(preset.score,
                            color=PAL["mauve"], font_size="1.4rem",
                            font_weight="800",
                            font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                            line_height="1"),
                    rx.text("dmg/30s",
                            color=PAL["overlay1"], font_size="0.62rem",
                            letter_spacing="0.06em"),
                    spacing="0", align="end",
                ),
                width="100%", align="start",
            ),
            # Meta row — character, vessel, mode, date
            rx.hstack(
                rx.box(
                    preset.character_name,
                    color=PAL["lavender"], font_size="0.72rem",
                    font_weight="600",
                    padding="2px 8px", border_radius="4px",
                    background="rgba(180,190,254,0.12)",
                    border="1px solid rgba(180,190,254,0.25)",
                ),
                rx.box(
                    rx.hstack(
                        rx.icon(tag="wine", size=10),
                        rx.text(preset.vessel_name, font_size="0.72rem",
                                font_weight="600"),
                        spacing="1", align="center",
                    ),
                    color=rx.cond(preset.vessel_name == "— no vessel —",
                                  PAL["overlay0"], PAL["teal"]),
                    padding="2px 8px", border_radius="4px",
                    background=rx.cond(preset.vessel_name == "— no vessel —",
                                        "rgba(108,112,134,0.12)",
                                        "rgba(148,226,213,0.10)"),
                    border=rx.cond(preset.vessel_name == "— no vessel —",
                                   f"1px solid {PAL['surface0']}",
                                   "1px solid rgba(148,226,213,0.25)"),
                ),
                rx.box(
                    preset.mode,
                    color=PAL["subtext"], font_size="0.7rem",
                    padding="2px 8px", border_radius="4px",
                    background=PAL["surface0"],
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                ),
                rx.spacer(),
                rx.text(preset.date,
                        color=PAL["overlay0"], font_size="0.72rem",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                spacing="2", align="center", width="100%",
                flex_wrap="wrap",
                padding_top="6px",
                border_top=f"1px solid {PAL['surface0']}",
            ),
            # Goal-axis scores — the 4 dimensions the solver optimises.
            rx.hstack(
                _stat_block("damage", preset.damage_score, PAL["peach"]),
                _stat_block("survival", preset.survival_score, PAL["green"]),
                _stat_block("utility", preset.utility_score, PAL["yellow"]),
                _stat_block("team", preset.team_score, PAL["mauve"]),
                spacing="3", align="start", width="100%",
                padding="6px 0",
            ),
            # Damage-internals strip (legacy, useful for debugging the build).
            rx.hstack(
                _stat_block("hammer", preset.hammer_mult.to_string() + "×",
                            PAL["peach"]),
                _stat_block("hex", preset.hex_mult.to_string() + "×",
                            PAL["sky"]),
                _stat_block("add.phys",
                            "+" + preset.additive_phys_pct.to_string() + "%",
                            PAL["teal"]),
                _stat_block("uptime",
                            preset.trance_uptime_pct.to_string() + "%",
                            PAL["yellow"]),
                spacing="3", align="start", width="100%",
                padding="6px 0",
            ),
            # Slots grid
            _slots_grid(preset),
            # Actions
            rx.hstack(
                rx.el.button(
                    rx.hstack(
                        rx.icon(tag="rotate_cw", size=14),
                        rx.text("Load build", font_weight="700"),
                        spacing="1", align="center",
                    ),
                    on_click=State.load_preset(preset.name),
                    title="Load this build's locks + exclusions + vessel into the optimizer",
                    style={
                        "background": PAL["mauve"],
                        "border": "1px solid transparent",
                        "color": PAL["crust"],
                        "padding": "9px 16px",
                        "border_radius": "8px",
                        "font_size": "0.84rem",
                        "cursor": "pointer",
                        "flex": "1",
                        "transition": "all 0.12s",
                    },
                    _hover={"background": PAL["lavender"]},
                ),
                rx.el.button(
                    rx.icon(tag="trash_2", size=14),
                    on_click=State.delete_preset(preset.name),
                    title=f"Delete '{preset.name}'",
                    style={
                        "background": "transparent",
                        "border": f"1px solid {PAL['surface1']}",
                        "color": PAL["red"],
                        "padding": "9px 12px",
                        "border_radius": "8px",
                        "cursor": "pointer",
                    },
                    _hover={
                        "background": "rgba(243,139,168,0.08)",
                        "border_color": PAL["red"],
                    },
                ),
                spacing="2", width="100%", padding_top="4px",
            ),
            spacing="3", align="start", width="100%",
        ),
        background=PAL["mantle"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_radius="12px",
        padding="14px 16px 14px",
        transition="all 0.12s",
        _hover={
            "border_color": PAL["mauve"],
            "box_shadow": f"0 0 0 1px {PAL['mauve']}",
        },
    )


def _export_btn() -> rx.Component:
    disabled = State.selected_build_names.length() == 0
    return rx.el.button(
        rx.hstack(
            rx.icon(tag="download", size=13),
            rx.text("Export selected", font_weight="700", font_size="0.8rem"),
            spacing="1", align="center",
        ),
        on_click=State.export_selected_builds,
        disabled=disabled,
        title="Download a JSON file with the selected builds",
        style={
            "background": "transparent",
            "border": f"1px solid {PAL['surface1']}",
            "color": rx.cond(disabled, PAL["overlay0"], PAL["lavender"]),
            "padding": "6px 12px",
            "border_radius": "6px",
            "cursor": rx.cond(disabled, "not-allowed", "pointer"),
            "opacity": rx.cond(disabled, "0.55", "1"),
        },
        _hover={"border_color": PAL["lavender"]},
    )


def _import_btn() -> rx.Component:
    return rx.el.button(
        rx.hstack(
            rx.icon(tag="upload", size=13),
            rx.text("Import…", font_weight="700", font_size="0.8rem"),
            spacing="1", align="center",
        ),
        on_click=State.open_import_builds_dialog,
        title="Load builds from a JSON file",
        style={
            "background": "transparent",
            "border": f"1px solid {PAL['surface1']}",
            "color": PAL["teal"],
            "padding": "6px 12px",
            "border_radius": "6px",
            "cursor": "pointer",
        },
        _hover={"border_color": PAL["teal"]},
    )


def _selection_bar() -> rx.Component:
    total = State.saved_presets.length()
    chosen = State.selected_build_names.length()
    return rx.hstack(
        rx.checkbox(
            "Select all",
            checked=(chosen > 0) & (chosen == total),
            on_change=State.set_all_builds_selected,
        ),
        rx.text(chosen.to_string() + " / " + total.to_string() + " selected",
                color=PAL["overlay1"], font_size="0.78rem"),
        rx.spacer(),
        _export_btn(),
        _import_btn(),
        align="center", width="100%",
        padding="8px 10px",
        background=PAL["surface0"],
        border_radius="8px",
        margin_bottom="10px",
    )


def _import_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Import builds"),
            rx.dialog.description(
                "Upload a JSON file exported from this tool. "
                "Duplicates (same name + character) are skipped unless "
                "'Overwrite existing' is checked.",
                color=PAL["subtext"], font_size="0.82rem",
            ),
            rx.vstack(
                rx.upload.root(
                    rx.vstack(
                        rx.icon(tag="file_json", size=28, color=PAL["lavender"]),
                        rx.text("Drop a .json file here or click to select",
                                color=PAL["subtext"], font_size="0.88rem"),
                        spacing="2", align="center",
                    ),
                    id="import_builds_upload",
                    multiple=False,
                    accept={"application/json": [".json"]},
                    on_drop=State.handle_upload_builds(
                        rx.upload_files(upload_id="import_builds_upload")
                    ),
                    style={
                        "border": f"2px dashed {PAL['surface1']}",
                        "border_radius": "8px",
                        "padding": "28px",
                        "cursor": "pointer",
                        "background": PAL["mantle"],
                    },
                    _hover={"border_color": PAL["lavender"]},
                ),
                rx.checkbox(
                    "Overwrite existing builds with the same name",
                    checked=State.import_overwrite_builds,
                    on_change=State.toggle_import_overwrite_builds,
                ),
                rx.cond(
                    State.import_report_text != "",
                    rx.callout(State.import_report_text, icon="info",
                               color_scheme="gray"),
                    rx.box(),
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.dialog.close(
                        rx.button("Close", variant="soft",
                                  on_click=State.close_import_builds_dialog),
                    ),
                    width="100%",
                ),
                spacing="3", width="100%",
            ),
            max_width="520px",
        ),
        open=State.import_builds_dialog_open,
        on_open_change=State.set_import_builds_dialog_open,
    )


def my_builds_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon(tag="bookmark", size=22, color=PAL["mauve"]),
            rx.heading("My builds", size="5", color=PAL["text"]),
            rx.cond(
                State.saved_presets.length() > 0,
                rx.box(
                    State.saved_presets.length(),
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
            "Saved relic/playstyle configurations for the current character. "
            "Each card shows the vessel, slot-by-slot effect lineup, and key "
            "damage multipliers at save time — click Load to re-apply.",
            color=PAL["overlay1"], font_size="0.86rem",
            margin_bottom="14px",
        ),
        rx.cond(
            State.saved_presets.length() > 0,
            _selection_bar(),
            rx.box(),
        ),
        _import_dialog(),
        rx.cond(
            State.saved_presets.length() == 0,
            _empty_state(),
            rx.grid(
                rx.foreach(State.saved_presets, _build_card),
                columns="repeat(auto-fit, minmax(460px, 1fr))",
                gap="14px",
                width="100%",
            ),
        ),
        rx.callout(
            rx.text(
                "Saved builds live on your host at user_data/presets.json — "
                "safe to back up or edit. The Compare presets tab overlays "
                "the current build's stat radar plus a grouped bar chart "
                "against whichever preset you Load here.",
                font_size="0.82rem",
            ),
            icon="info",
            color_scheme="gray",
            margin_top="18px",
            width="100%",
        ),
        width="100%",
        align="start",
        spacing="2",
    )
