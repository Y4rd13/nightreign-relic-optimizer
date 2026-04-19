"""Main entry — sidebar + tabbed main area + dialogs."""

from __future__ import annotations

import reflex as rx

from .components.compare_tab import compare_tab
from .components.dialogs import debuff_dialog, edit_dialog, named_dialog, preset_dialog
from .components.hero import hero
from .components.my_builds_tab import my_builds_tab
from .components.sidebar import sidebar
from .components.slot_card import slot_card
from .components.stats_chart import character_stats_panel
from .components.validator_tab import validator_tab
from .state import State
from .theme import PAL


def _title_bar() -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.heading(
                "Nightreign · Relic Optimizer",
                size="7",
                background_image=f"linear-gradient(90deg, {PAL['mauve']}, {PAL['lavender']} 50%, {PAL['sky']})",
                background_clip="text",
                color="transparent",
                letter_spacing="-0.02em",
                font_weight="800",
            ),
            rx.hstack(
                rx.text(State.character_icon, font_size="1rem"),
                rx.text(State.character_name, color=PAL["mauve"],
                        font_weight="700", font_size="0.92rem"),
                rx.box(width="4px", height="4px", border_radius="50%",
                       background=PAL["overlay0"]),
                rx.text(State.character_tagline, color=PAL["subtext"],
                        font_size="0.86rem"),
                rx.box(width="4px", height="4px", border_radius="50%",
                       background=PAL["overlay0"]),
                rx.box(
                    State.mode_label,
                    color=PAL["mauve"],
                    font_size="0.78rem",
                    padding="2px 9px",
                    border_radius="99px",
                    background="rgba(203,166,247,0.12)",
                    border=f"1px solid rgba(203,166,247,0.3)",
                ),
                spacing="2", align="center",
            ),
            spacing="1",
            align="start",
            flex="1",
        ),
        rx.box(),  # placeholder for future right-side controls
        width="100%",
        align="center",
        margin_bottom="18px",
    )


def _tab_trigger(value: str, icon: str, label: str) -> rx.Component:
    # Flat children (no hstack) so Radix's aria tracking doesn't duplicate the
    # accessible name. Using flex on the trigger itself keeps icon + text
    # visually aligned.
    return rx.tabs.trigger(
        rx.icon(tag=icon, size=16, style={"margin_right": "8px",
                                           "display": "inline-block",
                                           "vertical_align": "middle"}),
        label,
        value=value,
        style={
            "padding": "10px 18px",
            "border_radius": "8px 8px 0 0",
            "cursor": "pointer",
            "transition": "all 0.12s",
            "display": "inline-flex",
            "align_items": "center",
            "font_weight": "600",
        },
    )


def _optimizer_content() -> rx.Component:
    return rx.vstack(
        hero(),
        character_stats_panel(),
        rx.cond(
            State.mode == "standard",
            rx.vstack(
                rx.hstack(
                    rx.icon(tag="circle_dot", size=18, color=PAL["mauve"]),
                    rx.heading("Common slots · 1-3", size="5", color=PAL["text"]),
                    spacing="2", align="center",
                    margin_bottom="10px",
                ),
                rx.grid(
                    rx.foreach(State.build_slots, slot_card),
                    columns="repeat(auto-fit, minmax(460px, 1fr))",
                    gap="14px",
                    width="100%",
                ),
                width="100%",
                align="start",
                spacing="2",
            ),
            rx.grid(
                rx.vstack(
                    rx.hstack(
                        rx.icon(tag="circle_dot", size=16, color=PAL["mauve"]),
                        rx.heading("Common slots · 1-3", size="5", color=PAL["text"]),
                        spacing="2", align="center",
                        margin_bottom="10px",
                    ),
                    rx.foreach(State.build_slots[0:3], slot_card),
                    width="100%",
                    spacing="2",
                    align="stretch",
                ),
                rx.vstack(
                    rx.hstack(
                        rx.icon(tag="moon", size=16, color=PAL["lavender"]),
                        rx.heading("Deep slots · 4-6", size="5", color=PAL["text"]),
                        spacing="2", align="center",
                        margin_bottom="10px",
                    ),
                    rx.foreach(State.build_slots[3:6], slot_card),
                    width="100%",
                    spacing="2",
                    align="stretch",
                ),
                columns="2",
                gap="20px",
                width="100%",
            ),
        ),
        width="100%",
        spacing="3",
        align="start",
    )


def _tabs() -> rx.Component:
    return rx.tabs.root(
        rx.tabs.list(
            _tab_trigger("optimizer", "wrench", "Optimizer"),
            _tab_trigger("validator", "check-circle", "Validator"),
            _tab_trigger("builds", "bookmark", "My builds"),
            _tab_trigger("compare", "scale", "Compare presets"),
            style={
                "gap": "8px",
                "border_bottom": f"1px solid {PAL['surface0']}",
                "margin_bottom": "18px",
                "padding_bottom": "2px",
            },
        ),
        rx.tabs.content(_optimizer_content(), value="optimizer",
                        padding_top="4px"),
        rx.tabs.content(validator_tab(), value="validator",
                        padding_top="4px"),
        rx.tabs.content(my_builds_tab(), value="builds",
                        padding_top="4px"),
        rx.tabs.content(compare_tab(), value="compare",
                        padding_top="4px"),
        value=State.active_tab,
        on_change=State.set_tab,
        default_value="optimizer",
    )


def index() -> rx.Component:
    return rx.hstack(
        sidebar(),
        rx.box(
            _title_bar(),
            _tabs(),
            padding="22px 28px",
            flex="1",
            overflow_y="auto",
            height="100vh",
        ),
        edit_dialog(),
        named_dialog(),
        debuff_dialog(),
        preset_dialog(),
        rx.toast.provider(
            position="bottom-right",
            close_button=True,
            rich_colors=True,
        ),
        spacing="0",
        align="start",
        width="100vw",
        min_height="100vh",
        background=PAL["base"],
    )


app = rx.App(
    style={
        "background": PAL["base"],
        "color": PAL["text"],
        "font_family": '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Ubuntu, sans-serif',
    },
    stylesheets=["/global.css"],
    theme=rx.theme(
        appearance="dark",
        accent_color="purple",
        gray_color="mauve",
        scaling="95%",
        panel_background="solid",
    ),
)

# Toast provider for save/load/delete notifications.
app.add_custom_reflex_cloud_config = None  # ignore unused


@rx.page(route="/", title="Nightreign · Relic Optimizer", on_load=State.recompute)
def root() -> rx.Component:
    return index()
