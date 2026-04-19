"""Small reusable components: badges, pills, rows."""

from __future__ import annotations

import reflex as rx

from .theme import COLOR_SLOT, GROUP_COLOR, PAL, TIER_COLOR


def tier_badge(tier) -> rx.Component:
    bg = rx.match(
        tier,
        ("STD", TIER_COLOR["STD"][0]),
        ("BTH", TIER_COLOR["BTH"][0]),
        ("DoN", TIER_COLOR["DoN"][0]),
        TIER_COLOR["STD"][0],
    )
    fg = rx.match(
        tier,
        ("STD", TIER_COLOR["STD"][1]),
        ("BTH", TIER_COLOR["BTH"][1]),
        ("DoN", TIER_COLOR["DoN"][1]),
        TIER_COLOR["STD"][1],
    )
    return rx.box(
        tier,
        bg=bg, color=fg,
        padding="2px 8px",
        border_radius="4px",
        font_size="0.72rem",
        font_weight="700",
        letter_spacing="0.03em",
        font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
        display="inline-flex",
        align_items="center",
        justify_content="center",
        min_width="38px",
        height="20px",
    )


def group_badge(group) -> rx.Component:
    color = rx.match(
        group,
        *[(k, v) for k, v in GROUP_COLOR.items()],
        PAL["overlay0"],
    )
    return rx.box(
        group,
        color=color,
        background="rgba(49,50,68,0.6)",
        border="1px solid",
        border_color=rx.match(
            group,
            *[(k, f"{v}55") for k, v in GROUP_COLOR.items()],
            f"{PAL['overlay0']}55",
        ),
        padding="2px 8px",
        border_radius="4px",
        font_size="0.68rem",
        font_weight="700",
        font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
        display="inline-flex",
        align_items="center",
        height="20px",
    )


def flag_badge(flag) -> rx.Component:
    return rx.cond(
        flag == "Y",
        rx.box("Y", bg=PAL["red"], color=PAL["crust"],
               padding="2px 8px", border_radius="4px",
               font_size="0.72rem", font_weight="700",
               font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
               display="inline-flex", align_items="center",
               justify_content="center", min_width="22px", height="20px",
               title="requires debuff"),
        rx.box("N", bg="transparent", color=PAL["overlay0"],
               border="1px solid", border_color=PAL["surface0"],
               padding="2px 8px", border_radius="4px",
               font_size="0.72rem", font_weight="700",
               font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
               display="inline-flex", align_items="center",
               justify_content="center", min_width="22px", height="20px",
               title="no debuff needed"),
    )


def color_pill(color_code) -> rx.Component:
    name = rx.match(
        color_code,
        ("R", "Red"), ("G", "Green"), ("B", "Blue"),
        ("Y", "Yellow"), ("U", "Universal"),
        "—",
    )
    col = rx.match(
        color_code,
        ("R", COLOR_SLOT["R"][1]),
        ("G", COLOR_SLOT["G"][1]),
        ("B", COLOR_SLOT["B"][1]),
        ("Y", COLOR_SLOT["Y"][1]),
        ("U", COLOR_SLOT["U"][1]),
        PAL["overlay0"],
    )
    return rx.box(
        name,
        color=col,
        background=f"transparent",
        border="1px solid",
        border_color=col,
        padding="3px 9px",
        border_radius="99px",
        font_size="0.7rem",
        font_weight="700",
        display="inline-flex",
        align_items="center",
        font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
    )


def attr_id_box(val) -> rx.Component:
    return rx.text(
        val.to_string(),
        color=PAL["sky"],
        font_weight="700",
        font_size="0.88rem",
        font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
    )


def attr_sort(val) -> rx.Component:
    return rx.text(
        val.to_string(),
        color=PAL["overlay1"],
        font_size="0.76rem",
        font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
    )


def build_type_pill(build_type, small: bool = False) -> rx.Component:
    """Colored pill tagging a build's dominant goal axis.

    Values match the strings produced by State.dominant_goal_label and
    PresetRow.build_type: "DPS build" / "Tank build" / "Utility build" /
    "Support build". Re-used in hero, compare tab, and My Builds cards."""
    color = rx.match(
        build_type,
        ("Tank build", PAL["green"]),
        ("Utility build", PAL["yellow"]),
        ("Support build", PAL["mauve"]),
        PAL["peach"],
    )
    return rx.box(
        rx.text(
            build_type,
            font_size="0.66rem" if not small else "0.64rem",
            letter_spacing="0.08em",
            font_weight="700",
            color=color,
        ),
        padding="2px 8px",
        border_radius="999px",
        border=f"1px solid {PAL['surface0']}",
        background=PAL["mantle"] if not small else PAL["crust"],
        display="inline-block",
    )


def small_button(text: str, on_click, color: str = None, title: str = "") -> rx.Component:
    color = color or PAL["subtext"]
    return rx.el.button(
        text,
        on_click=on_click,
        title=title,
        style={
            "background": "transparent",
            "border": f"1px solid {PAL['surface1']}",
            "color": color,
            "padding": "4px 10px",
            "border_radius": "6px",
            "font_size": "0.78rem",
            "font_weight": "600",
            "cursor": "pointer",
            "transition": "all 0.12s",
        },
        _hover={
            "background": "rgba(203,166,247,0.08)",
            "border_color": PAL["mauve"],
            "color": PAL["mauve"],
        },
    )
