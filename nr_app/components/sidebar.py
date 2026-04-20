"""Sidebar: character / mode / vessel / playstyle / controls / presets."""

from __future__ import annotations

import reflex as rx

from ..state import CUSTOM_VESSEL, PLAYSTYLE_DEFAULTS, State
from ..theme import COLOR_SLOT, PAL
from ..widgets import color_pill
from .dormant_powers import dormant_powers_list


def _fmt_default(v) -> str:
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


STAT_RANK_COLOR = {
    "S": PAL["peach"], "A": PAL["mauve"], "B": PAL["blue"],
    "C": PAL["teal"], "D": PAL["overlay0"],
}


def _section(icon_name: str, title: str, *children, start_open: bool = True) -> rx.Component:
    return rx.accordion.item(
        rx.accordion.header(
            rx.accordion.trigger(
                rx.hstack(
                    rx.icon(tag=icon_name, size=14, color=PAL["mauve"]),
                    rx.text(title.upper(),
                            color=PAL["mauve"],
                            font_size="0.74rem",
                            font_weight="700",
                            letter_spacing="0.08em"),
                    rx.spacer(),
                    rx.accordion.icon(color=PAL["overlay0"]),
                    width="100%",
                    align="center",
                    spacing="2",
                ),
                style={
                    "padding": "8px 4px",
                    "background": "transparent",
                    "cursor": "pointer",
                    "border": "none",
                },
            ),
        ),
        rx.accordion.content(
            rx.vstack(
                *children,
                spacing="2",
                width="100%",
                padding="4px 4px 12px",
            ),
        ),
        value=title,
        background="transparent",
        border_bottom=f"1px solid {PAL['surface0']}",
    )


def _slider(label: str, value, on_change, on_commit=None,
            min_=0.0, max_=1.0, step=0.05,
            help_text: str = "", is_int: bool = False,
            field_name: str = "",
            effective_value=None, gated_count=None,
            has_source=None, full_delta=None) -> rx.Component:
    """Playstyle slider.

    `on_change` fires continuously while dragging — we use it to keep the
    displayed value synced without doing expensive work.
    `on_commit` (optional) fires once on mouse-release — use it to trigger
    recompute. If omitted, falls back to `on_change` (legacy behaviour).

    `effective_value` (rx.Var or None): the uptime AFTER folding in relic
    uptime_boosts from the current build. When different from `value`, the
    slider shows a "→ Y" arrow next to the number so the user sees what
    their build stacks on top of their playstyle floor.

    `gated_count` (rx.Var or None): how many effects in the current build
    depend on this slider being > 0. Renders a small "×N" pill that
    previews how much the slider influences scoring.
    """
    default = PLAYSTYLE_DEFAULTS.get(field_name)
    default_str = _fmt_default(default) if default is not None else ""
    tooltip_txt = help_text or label
    if default_str:
        tooltip_txt = f"{tooltip_txt}  ·  default: {default_str}"
    slider_kwargs = {
        "default_value": [value],
        "min": min_,
        "max": max_,
        "step": step,
        "on_change": on_change,
        "width": "100%",
        "color_scheme": "purple",
        "size": "1",
    }
    if on_commit is not None:
        slider_kwargs["on_value_commit"] = on_commit
    effective_pill = rx.box()
    if effective_value is not None:
        effective_pill = rx.cond(
            effective_value > value,
            rx.tooltip(
                rx.hstack(
                    rx.text("→", color=PAL["green"],
                            font_size="0.7rem", font_weight="700",
                            font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                    rx.text(effective_value, color=PAL["green"],
                            font_size="0.78rem", font_weight="700",
                            font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
                    spacing="1", align="center",
                ),
                content=(
                    "Effective uptime — relics in your current build add boosts "
                    "on top of your baseline. The solver scores against this "
                    "higher value."
                ),
            ),
            rx.box(),
        )
    full_delta_pill = rx.box()
    if full_delta is not None:
        # Only render the pill when there's meaningful potential gain — a
        # delta of 0 means either the slider is already at 1.0 or no effect
        # in the build is gated by it (so nothing would change).
        full_delta_pill = rx.cond(
            full_delta > 0.0,
            rx.tooltip(
                rx.text(
                    "+" + full_delta.to_string() + " at full",
                    color=PAL["overlay1"],
                    font_size="0.64rem",
                    font_weight="600",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                    font_style="italic",
                    margin_top="2px",
                ),
                content=(
                    "Weighted-score increase if you pushed this slider to "
                    "1.0 (everything else fixed). Low number → the slider "
                    "doesn't meaningfully gate your current build; high "
                    "number → cycling this buff better in-game is worth "
                    "effort."
                ),
            ),
            rx.box(),
        )
    no_source_pill = rx.box()
    if has_source is not None:
        # Render the ⚠ only when the user has actually raised the slider above
        # zero — a 0 slider can't mislead the solver, so the warning would be
        # pure noise.
        no_source_pill = rx.cond(
            (value > 0.0) & ~has_source,
            rx.tooltip(
                rx.icon(
                    tag="triangle_alert",
                    size=12,
                    color=PAL["yellow"],
                    style={"cursor": "help"},
                ),
                content=(
                    "No plausible in-game source for this status on your "
                    "current weapon loadout / playstyle. The solver will "
                    "credit damage bonuses you can't trigger. Override "
                    "your weapons or playstyle tags if this is wrong."
                ),
            ),
            rx.box(),
        )
    gated_pill = rx.box()
    if gated_count is not None:
        gated_pill = rx.cond(
            gated_count > 0,
            rx.tooltip(
                rx.text(
                    "×" + gated_count.to_string(),
                    background=PAL["surface0"],
                    color=PAL["overlay1"],
                    border=f"1px solid {PAL['surface1']}",
                    padding="1px 6px",
                    border_radius="3px",
                    font_size="0.64rem",
                    font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                ),
                content=(
                    "Effects in your current build gated by this slider. "
                    "Raising it above zero unlocks their scoring contribution."
                ),
            ),
            rx.box(),
        )
    return rx.box(
        rx.hstack(
            rx.tooltip(
                rx.text(label, color=PAL["subtext"], font_size="0.78rem",
                        cursor="help"),
                content=tooltip_txt,
            ),
            no_source_pill,
            gated_pill,
            rx.spacer(),
            rx.text(value, color=PAL["text"],
                    font_size="0.78rem", font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
            effective_pill,
            rx.cond(
                (default is not None) & (value != default),
                rx.tooltip(
                    rx.el.button(
                        rx.icon(tag="rotate_ccw", size=10),
                        on_click=State.reset_playstyle_field(field_name),
                        style={
                            "background": "transparent",
                            "border": f"1px solid {PAL['surface1']}",
                            "color": PAL["overlay1"],
                            "padding": "2px 5px",
                            "border_radius": "4px",
                            "cursor": "pointer",
                            "display": "inline-flex",
                            "align_items": "center",
                        },
                        _hover={"color": PAL["mauve"], "border_color": PAL["mauve"]},
                    ),
                    content=f"reset to default ({default_str})",
                ),
                rx.box(),
            ),
            width="100%",
            align="center",
            spacing="1",
        ),
        rx.slider(**slider_kwargs),
        full_delta_pill,
        width="100%",
        spacing="1",
    )


def _goal_slider_row(key: str, icon: str, label: str, accent: str,
                     weight, on_change, on_commit) -> rx.Component:
    """Single row for the Build Goal accordion: icon + label + slider + value.

    The accent colour matches the axis (damage = peach, survival = green,
    utility = yellow, team = mauve) so the user can eyeball which knob does
    what without reading the label."""
    return rx.box(
        rx.hstack(
            rx.text(icon, font_size="0.96rem", min_width="22px"),
            rx.text(label, color=PAL["subtext"], font_size="0.78rem",
                    font_weight="600"),
            rx.spacer(),
            rx.text(weight.to_string(),
                    color=accent, font_weight="700", font_size="0.78rem",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                    min_width="36px", text_align="right"),
            width="100%",
            align="center",
            spacing="1",
        ),
        rx.slider(
            default_value=[weight],
            min=0.0, max=1.0, step=0.05,
            on_change=on_change,
            on_value_commit=on_commit,
            color_scheme="purple",
            size="1",
            width="100%",
        ),
        width="100%",
    )


def _stat_chip(s) -> rx.Component:
    color = rx.match(
        s.val,
        ("S", STAT_RANK_COLOR["S"]),
        ("A", STAT_RANK_COLOR["A"]),
        ("B", STAT_RANK_COLOR["B"]),
        ("C", STAT_RANK_COLOR["C"]),
        ("D", STAT_RANK_COLOR["D"]),
        PAL["overlay0"],
    )
    return rx.box(
        rx.hstack(
            rx.text(s.abbr, color=color,
                    font_weight="700", font_size="0.64rem",
                    letter_spacing="0.06em"),
            rx.text(s.val, color=PAL["text"],
                    font_weight="800", font_size="0.76rem"),
            spacing="1", align="center",
        ),
        background=PAL["crust"],
        border="1px solid",
        border_color=PAL["surface0"],
        padding="3px 8px",
        border_radius="5px",
    )


def _character_card() -> rx.Component:
    return rx.box(
        rx.text(State.character_tagline,
                color=PAL["subtext"], font_style="italic",
                font_size="0.78rem", line_height="1.4",
                margin_bottom="8px"),
        rx.flex(
            rx.foreach(State.character_stats_flat, _stat_chip),
            direction="row", wrap="wrap", gap="4px",
            margin_bottom="10px",
        ),
        rx.hstack(
            rx.icon(tag="zap", size=12, color=PAL["mauve"]),
            rx.text(State.character_abilities_text,
                    color=PAL["overlay1"], font_size="0.72rem",
                    line_height="1.4"),
            spacing="1",
            align="start",
        ),
        rx.tooltip(
            rx.hstack(
                rx.icon(tag="filter", size=11, color=PAL["overlay0"]),
                rx.text(State.pool_stats_text,
                        color=PAL["overlay1"], font_size="0.7rem",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                        cursor="help"),
                spacing="1",
                align="center",
                margin_top="6px",
            ),
            content=(
                "The solver already filters out effects that can't apply to "
                "your character (wrong weapon class, foreign character tag, "
                "non-rollable tier, etc.). Changing weapons, playstyle tags, "
                "party composition, or build-goal weights updates this count."
            ),
        ),
        rx.cond(
            ~State.character_is_full,
            rx.box(
                rx.hstack(
                    rx.icon(tag="triangle_alert", size=12, color=PAL["yellow"]),
                    rx.text(
                        "Baseline model — generic effects work, class-specific buckets need tuning.",
                        color=PAL["yellow"], font_size="0.7rem",
                        line_height="1.4",
                    ),
                    spacing="1",
                    align="start",
                ),
                margin_top="8px",
                padding="6px 8px",
                border_radius="6px",
                background="rgba(249,226,175,0.06)",
                border="1px solid rgba(249,226,175,0.22)",
            ),
            rx.box(),
        ),
        background=PAL["mantle"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_radius="10px",
        padding="10px 12px",
        margin_top="6px",
    )


def _custom_vessel_editor() -> rx.Component:
    colors = ["R", "G", "B", "Y", "U"]

    def slot_picker(i: int) -> rx.Component:
        return rx.hstack(
            rx.text(f"Slot {i+1}", color=PAL["subtext"],
                    font_size="0.76rem", min_width="50px"),
            rx.select.root(
                rx.select.trigger(width="100%"),
                rx.select.content(
                    *[rx.select.item(c, value=c) for c in colors],
                ),
                value=State.custom_vessel_colors[i],
                on_change=lambda v: State.set_custom_color(i, v),
                size="1",
            ),
            width="100%",
            align="center",
        )

    return rx.vstack(
        slot_picker(0), slot_picker(1), slot_picker(2),
        rx.cond(
            State.mode == "don",
            rx.vstack(slot_picker(3), slot_picker(4), slot_picker(5),
                      spacing="2", width="100%"),
            rx.box(),
        ),
        rx.flex(
            rx.foreach(
                State.custom_vessel_colors[0:State.num_slots],
                lambda c: color_pill(c),
            ),
            gap="4px", wrap="wrap",
            margin_top="6px",
            padding="8px",
            background=PAL["crust"],
            border_radius="6px",
            width="100%",
        ),
        spacing="2",
        width="100%",
        padding="10px 12px",
        background=PAL["mantle"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_radius="10px",
        margin_top="6px",
    )


def _preset_row(p) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(p.name, color=PAL["text"],
                        font_weight="700", font_size="0.84rem",
                        overflow="hidden",
                        text_overflow="ellipsis",
                        white_space="nowrap"),
                rx.hstack(
                    rx.text(p.score, color=PAL["mauve"],
                            font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                            font_size="0.78rem", font_weight="700"),
                    rx.text(p.mode, color=PAL["overlay1"],
                            font_size="0.68rem",
                            padding="1px 6px",
                            border_radius="3px",
                            background=PAL["surface0"]),
                    spacing="2",
                    align="center",
                ),
                rx.text(p.date, color=PAL["overlay0"], font_size="0.64rem"),
                spacing="0",
                flex="1",
                align="start",
            ),
            rx.vstack(
                rx.el.button(
                    rx.icon(tag="rotate_cw", size=14),
                    on_click=State.load_preset(p.name),
                    title="Load this preset",
                    style={
                        "background": "transparent",
                        "border": f"1px solid {PAL['surface1']}",
                        "color": PAL["subtext"],
                        "padding": "5px 8px",
                        "border_radius": "5px",
                        "cursor": "pointer",
                    },
                    _hover={"border_color": PAL["mauve"], "color": PAL["mauve"]},
                ),
                rx.el.button(
                    rx.icon(tag="trash_2", size=14),
                    on_click=State.delete_preset(p.name),
                    title="Delete",
                    style={
                        "background": "transparent",
                        "border": f"1px solid {PAL['surface1']}",
                        "color": PAL["red"],
                        "padding": "5px 8px",
                        "border_radius": "5px",
                        "cursor": "pointer",
                    },
                ),
                spacing="1",
                align="end",
            ),
            width="100%",
            spacing="2",
            align="start",
        ),
        padding="8px 10px",
        margin_bottom="4px",
        background=PAL["mantle"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_radius="8px",
        transition="border-color 0.12s",
        _hover={"border_color": PAL["mauve"]},
    )


def _controls_row() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.tooltip(
                rx.el.button(
                    rx.hstack(
                        rx.icon(tag="dices", size=14),
                        rx.text("Try variant", font_weight="600"),
                        spacing="1",
                        align="center",
                    ),
                    on_click=State.explore_variant,
                    style={
                        "background": PAL["surface0"],
                        "border": f"1px solid {PAL['surface1']}",
                        "color": PAL["text"],
                        "padding": "8px 10px",
                        "border_radius": "6px",
                        "font_size": "0.82rem",
                        "cursor": "pointer",
                        "flex": "1",
                    },
                    _hover={"border_color": PAL["mauve"], "color": PAL["mauve"]},
                ),
                content=(
                    "Re-rolls the solver seed to explore near-optimal "
                    "alternatives. Builds auto-recompute on slider/lock "
                    "changes — use this button only when you want to see "
                    "a different high-scoring composition for the same inputs."
                ),
            ),
            rx.el.button(
                rx.hstack(
                    rx.icon(tag="circle_x", size=14),
                    rx.text("Reset excl.", font_weight="600"),
                    spacing="1",
                    align="center",
                ),
                on_click=State.reset_excluded,
                title="Clear all excluded effects",
                style={
                    "background": PAL["surface0"],
                    "border": f"1px solid {PAL['surface1']}",
                    "color": PAL["text"],
                    "padding": "8px 10px",
                    "border_radius": "6px",
                    "font_size": "0.82rem",
                    "cursor": "pointer",
                    "flex": "1",
                },
            ),
            width="100%",
            spacing="2",
        ),
        rx.cond(
            State.explore_seed != 0,
            rx.tooltip(
                rx.el.button(
                    rx.hstack(
                        rx.icon(tag="rotate_ccw", size=12),
                        rx.text("Back to default seed", font_weight="600"),
                        rx.box(State.explore_seed,
                               font_size="0.66rem",
                               color=PAL["overlay1"],
                               font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                               padding="0px 6px",
                               background=PAL["surface0"],
                               border_radius="3px"),
                        spacing="1", align="center",
                    ),
                    on_click=State.reset_explore_seed,
                    style={
                        "background": "transparent",
                        "border": f"1px solid {PAL['surface1']}",
                        "color": PAL["overlay1"],
                        "padding": "5px 10px",
                        "border_radius": "5px",
                        "font_size": "0.7rem",
                        "cursor": "pointer",
                        "width": "100%",
                    },
                    _hover={"border_color": PAL["mauve"], "color": PAL["mauve"]},
                ),
                content="Returns to the deterministic solver result.",
            ),
            rx.box(),
        ),
        rx.tooltip(
            rx.el.button(
                rx.hstack(
                    rx.icon(tag="rotate_ccw", size=14),
                    rx.text("Reset sliders to defaults", font_weight="600"),
                    spacing="1",
                    align="center",
                ),
                on_click=State.reset_playstyle_all,
                style={
                    "background": "transparent",
                    "border": f"1px solid {PAL['surface1']}",
                    "color": PAL["subtext"],
                    "padding": "8px 12px",
                    "border_radius": "6px",
                    "font_size": "0.78rem",
                    "cursor": "pointer",
                    "width": "100%",
                },
                _hover={"border_color": PAL["mauve"], "color": PAL["mauve"]},
            ),
            content="Restores Boss routing · Buff uptime · Combat patterns to their starting values.",
        ),
        rx.cond(
            State.locked_picks.length() > 0,
            rx.el.button(
                rx.hstack(
                    rx.icon(tag="lock_open", size=14),
                    rx.text("Unlock all", font_weight="600"),
                    rx.box(State.locked_picks.length(),
                           background=PAL["yellow"],
                           color=PAL["crust"],
                           padding="1px 7px",
                           border_radius="99px",
                           font_size="0.7rem",
                           font_weight="700"),
                    spacing="2",
                    align="center",
                ),
                on_click=State.unlock_all,
                style={
                    "background": PAL["surface0"],
                    "border": f"1px solid {PAL['surface1']}",
                    "color": PAL["yellow"],
                    "padding": "8px 12px",
                    "border_radius": "6px",
                    "font_size": "0.82rem",
                    "cursor": "pointer",
                    "width": "100%",
                },
            ),
            rx.box(),
        ),
        width="100%",
        spacing="2",
    )


def sidebar() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.icon(tag="swords", size=22, color=PAL["mauve"]),
            rx.text("Nightreign",
                    color=PAL["mauve"], font_weight="800",
                    font_size="1rem", letter_spacing="-0.01em"),
            rx.text("Optimizer",
                    color=PAL["overlay1"], font_weight="600",
                    font_size="0.86rem"),
            spacing="2",
            align="center",
            margin_bottom="12px",
            padding="4px 4px",
        ),
        rx.accordion.root(
            _section(
                "user",
                "Character",
                rx.select.root(
                    rx.select.trigger(placeholder="Select Nightfarer", width="100%"),
                    rx.select.content(
                        rx.foreach(
                            State.character_option_ids,
                            lambda cid, i: rx.select.item(
                                State.character_option_labels[i],
                                value=cid,
                            ),
                        ),
                    ),
                    value=State.character_id,
                    on_change=State.set_character,
                    size="2",
                ),
                _character_card(),
            ),

            _section(
                "gamepad-2",
                "Mode",
                rx.radio_group(
                    ["standard", "don"],
                    value=State.mode,
                    on_change=State.set_mode,
                    direction="column",
                ),
                rx.cond(
                    State.mode == "standard",
                    rx.hstack(
                        rx.icon(tag="info", size=12, color=PAL["overlay1"]),
                        rx.text("3 relics · STD / BTH",
                                color=PAL["overlay1"], font_size="0.72rem"),
                        spacing="1",
                    ),
                    rx.hstack(
                        rx.icon(tag="info", size=12, color=PAL["overlay1"]),
                        rx.text("6 relics · 1-3 STD/BTH, 4-6 DoN/BTH",
                                color=PAL["overlay1"], font_size="0.72rem"),
                        spacing="1",
                    ),
                ),
            ),

            _section(
                "wine",
                "Vessel",
                rx.select.root(
                    rx.select.trigger(placeholder="Select a vessel or Custom", width="100%"),
                    rx.select.content(
                        rx.foreach(
                            State.vessel_option_ids,
                            lambda vid, i: rx.select.item(
                                State.vessel_option_labels[i],
                                value=rx.cond(vid == "", "__none__", vid),
                            ),
                        ),
                    ),
                    value=rx.cond(State.vessel_id == "", "__none__", State.vessel_id),
                    on_change=State.set_vessel,
                    size="2",
                ),
                rx.cond(
                    State.is_custom_vessel,
                    _custom_vessel_editor(),
                    rx.box(),
                ),
            ),

            _section(
                "target",
                "Boss routing",
                _slider("Evergaol clears", State.evergaol_clears,
                        lambda v: State.drag_slider("evergaol_clears", v),
                        lambda v: State.commit_slider("evergaol_clears", v),
                        min_=0, max_=8, step=1,
                        help_text="+5% damage per evergaol boss cleared per run.",
                        field_name="evergaol_clears"),
                _slider("Night Invader kills", State.invader_kills,
                        lambda v: State.drag_slider("invader_kills", v),
                        lambda v: State.commit_slider("invader_kills", v),
                        min_=0, max_=6, step=1,
                        help_text="+7% damage per invader killed.",
                        field_name="invader_kills"),
            ),

            _section(
                "sparkles",
                "Dormant powers",
                dormant_powers_list(),
                start_open=False,
            ),

            _section(
                "zap",
                "Buff uptime",
                rx.hstack(
                    rx.icon(tag="info", size=11, color=PAL["overlay1"]),
                    rx.text(
                        "Baseline = how often you naturally hold each buff without "
                        "relic help (your skill / playstyle). Relics with "
                        "uptime_boosts stack on top — the green '→ X' shows the "
                        "effective total in your current build.",
                        color=PAL["overlay1"], font_size="0.7rem",
                        line_height="1.4",
                    ),
                    spacing="1", align="start",
                    margin_bottom="6px",
                ),
                _slider("Grease baseline", State.grease_uptime,
                        lambda v: State.drag_slider("grease_uptime", v),
                        lambda v: State.commit_slider("grease_uptime", v),
                        help_text="Fraction of fight you keep grease applied (L50 buff bucket).",
                        field_name="grease_uptime",
                        effective_value=State.effective_uptimes["grease_uptime"],
                        gated_count=State.slider_gated_count["grease_uptime"],
                        full_delta=State.slider_full_delta["grease_uptime"]),
                _slider(State.character_skill_name + " (skill) baseline",
                        State.trance_uptime,
                        lambda v: State.drag_slider("trance_uptime", v),
                        lambda v: State.commit_slider("trance_uptime", v),
                        help_text="Time you keep your character skill active. Relics with skill-cooldown reductions (e.g. L525 Trance Loop) push this toward 99%.",
                        field_name="trance_uptime",
                        effective_value=State.effective_uptimes["trance_uptime"],
                        gated_count=State.slider_gated_count["trance_uptime"],
                        full_delta=State.slider_full_delta["trance_uptime"]),
                _slider("Ult baseline", State.ult_uptime,
                        lambda v: State.drag_slider("ult_uptime", v),
                        lambda v: State.commit_slider("ult_uptime", v),
                        help_text="Time Ultimate Art is active — depends on how fast you charge the gauge.",
                        field_name="ult_uptime",
                        effective_value=State.effective_uptimes["ult_uptime"],
                        gated_count=State.slider_gated_count["ult_uptime"],
                        full_delta=State.slider_full_delta["ult_uptime"]),
                rx.cond(
                    State.character_uses_condition["incant_buff_active"],
                    _slider("Incant buff baseline", State.incant_uptime,
                            lambda v: State.drag_slider("incant_uptime", v),
                            lambda v: State.commit_slider("incant_uptime", v),
                            help_text="Golden Vow / Flame Grant Me Strength / similar self-buff uptime. L522 effects only score when > 0.",
                            field_name="incant_uptime",
                            effective_value=State.effective_uptimes["incant_uptime"],
                            gated_count=State.slider_gated_count["incant_uptime"],
                            full_delta=State.slider_full_delta["incant_uptime"]),
                    rx.box(),
                ),
                _slider("Taking-attacks baseline", State.took_damage_uptime,
                        lambda v: State.drag_slider("took_damage_uptime", v),
                        lambda v: State.commit_slider("took_damage_uptime", v),
                        help_text="Fraction of boss window you've been hit recently — gates L49 'recently took damage' buffs.",
                        field_name="took_damage_uptime",
                        effective_value=State.effective_uptimes["took_damage_uptime"],
                        gated_count=State.slider_gated_count["took_damage_uptime"],
                        full_delta=State.slider_full_delta["took_damage_uptime"]),
                start_open=False,
            ),

            _section(
                "biohazard",
                "Enemy afflictions",
                rx.hstack(
                    rx.icon(tag="info", size=11, color=PAL["overlay1"]),
                    rx.text(
                        "How reliably your weapon/incantations actually apply "
                        "each status. Leave at 0 if you don't inflict it — "
                        "\"damage vs X-afflicted\" relics will score 0 and be "
                        "ignored. The ×N badge shows effects in your current "
                        "build gated by each status.",
                        color=PAL["overlay1"], font_size="0.7rem",
                        line_height="1.4",
                    ),
                    spacing="1", align="start",
                    margin_bottom="4px",
                ),
                _slider("Poison", State.enemy_poisoned_uptime,
                        lambda v: State.drag_slider("enemy_poisoned_uptime", v),
                        lambda v: State.commit_slider("enemy_poisoned_uptime", v),
                        help_text="Fraction of fight the enemy is poisoned (weapon coat / poison incant).",
                        field_name="enemy_poisoned_uptime",
                        gated_count=State.slider_gated_count["enemy_poisoned_uptime"],
                        has_source=State.affliction_has_source["enemy_poisoned_uptime"],
                        full_delta=State.slider_full_delta["enemy_poisoned_uptime"]),
                _slider("Scarlet rot", State.enemy_scarlet_rot_uptime,
                        lambda v: State.drag_slider("enemy_scarlet_rot_uptime", v),
                        lambda v: State.commit_slider("enemy_scarlet_rot_uptime", v),
                        help_text="Fraction of fight enemy has scarlet rot applied.",
                        field_name="enemy_scarlet_rot_uptime",
                        gated_count=State.slider_gated_count["enemy_scarlet_rot_uptime"],
                        has_source=State.affliction_has_source["enemy_scarlet_rot_uptime"],
                        full_delta=State.slider_full_delta["enemy_scarlet_rot_uptime"]),
                _slider("Frostbite", State.enemy_frostbite_uptime,
                        lambda v: State.drag_slider("enemy_frostbite_uptime", v),
                        lambda v: State.commit_slider("enemy_frostbite_uptime", v),
                        help_text="Fraction of fight enemy is frostbitten (cold weapon / frost incant).",
                        field_name="enemy_frostbite_uptime",
                        gated_count=State.slider_gated_count["enemy_frostbite_uptime"],
                        has_source=State.affliction_has_source["enemy_frostbite_uptime"],
                        full_delta=State.slider_full_delta["enemy_frostbite_uptime"]),
                _slider("Bleed", State.enemy_bleed_uptime,
                        lambda v: State.drag_slider("enemy_bleed_uptime", v),
                        lambda v: State.commit_slider("enemy_bleed_uptime", v),
                        help_text="Fraction of fight enemy is bleeding (hemorrhage).",
                        field_name="enemy_bleed_uptime",
                        gated_count=State.slider_gated_count["enemy_bleed_uptime"],
                        has_source=State.affliction_has_source["enemy_bleed_uptime"],
                        full_delta=State.slider_full_delta["enemy_bleed_uptime"]),
                _slider("Asleep", State.enemy_asleep_uptime,
                        lambda v: State.drag_slider("enemy_asleep_uptime", v),
                        lambda v: State.commit_slider("enemy_asleep_uptime", v),
                        help_text="Fraction of fight enemy is asleep.",
                        field_name="enemy_asleep_uptime",
                        gated_count=State.slider_gated_count["enemy_asleep_uptime"],
                        has_source=State.affliction_has_source["enemy_asleep_uptime"],
                        full_delta=State.slider_full_delta["enemy_asleep_uptime"]),
                _slider("Madness", State.enemy_madness_uptime,
                        lambda v: State.drag_slider("enemy_madness_uptime", v),
                        lambda v: State.commit_slider("enemy_madness_uptime", v),
                        help_text="Fraction of fight enemy has madness.",
                        field_name="enemy_madness_uptime",
                        gated_count=State.slider_gated_count["enemy_madness_uptime"],
                        has_source=State.affliction_has_source["enemy_madness_uptime"],
                        full_delta=State.slider_full_delta["enemy_madness_uptime"]),
                _slider("Death Blight", State.enemy_deathblight_uptime,
                        lambda v: State.drag_slider("enemy_deathblight_uptime", v),
                        lambda v: State.commit_slider("enemy_deathblight_uptime", v),
                        help_text="Fraction of fight enemy is afflicted by death blight.",
                        field_name="enemy_deathblight_uptime",
                        gated_count=State.slider_gated_count["enemy_deathblight_uptime"],
                        has_source=State.affliction_has_source["enemy_deathblight_uptime"],
                        full_delta=State.slider_full_delta["enemy_deathblight_uptime"]),
                start_open=False,
            ),

            _section(
                "sword",
                "Combat patterns",
                rx.hstack(
                    rx.icon(tag="info", size=11, color=PAL["overlay1"]),
                    rx.text(
                        "Fraction of your attacks that match each pattern — "
                        "reflects your playstyle (long combos vs R1 spam). "
                        "Gates effects keyed on combo position. The ×N badge "
                        "shows effects in your build that use each.",
                        color=PAL["overlay1"], font_size="0.7rem",
                        line_height="1.4",
                    ),
                    spacing="1", align="start",
                    margin_bottom="4px",
                ),
                rx.cond(
                    State.character_uses_condition["chain_last_hit"],
                    _slider("Chain last-hit", State.chain_last_hit,
                            lambda v: State.drag_slider("chain_last_hit", v),
                            lambda v: State.commit_slider("chain_last_hit", v),
                            help_text="Fraction of hits that are the final blow of a chain / combo (L521 Chain-Final-Blow).",
                            field_name="chain_last_hit",
                            gated_count=State.slider_gated_count["chain_last_hit"],
                            full_delta=State.slider_full_delta["chain_last_hit"]),
                    rx.box(),
                ),
                rx.cond(
                    State.character_uses_condition["first_combo_hit"],
                    _slider("First-hit", State.first_combo_hit,
                            lambda v: State.drag_slider("first_combo_hit", v),
                            lambda v: State.commit_slider("first_combo_hit", v),
                            help_text="Fraction of hits that are combo starters (first attack of a string).",
                            field_name="first_combo_hit",
                            gated_count=State.slider_gated_count["first_combo_hit"],
                            full_delta=State.slider_full_delta["first_combo_hit"]),
                    rx.box(),
                ),
                rx.hstack(
                    rx.cond(
                        State.character_uses_condition["three_hammers_equipped"],
                        rx.hstack(
                            rx.checkbox(checked=State.three_hammers, on_change=State.toggle_hammers),
                            rx.tooltip(
                                rx.text("3+ " + State.primary_weapon_label,
                                        color=PAL["subtext"], font_size="0.78rem"),
                                content="Unlocks the +20% 'Improved Attack Power with 3+ X Equipped' bucket for your primary weapon class.",
                            ),
                            spacing="1", align="center",
                        ),
                        rx.box(),
                    ),
                    rx.cond(
                        State.character_uses_condition["dual_wielding"],
                        rx.hstack(
                            rx.checkbox(checked=State.dual_wielding, on_change=State.toggle_dual),
                            rx.tooltip(
                                rx.text("Dual-wield", color=PAL["subtext"], font_size="0.78rem"),
                                content="Some stance-break effects key off this.",
                            ),
                            spacing="1", align="center",
                        ),
                        rx.box(),
                    ),
                    spacing="3",
                    width="100%",
                ),
                start_open=False,
            ),

            _section(
                "swords",
                "Playstyle & weapons",
                rx.hstack(
                    rx.icon(tag="info", size=11, color=PAL["overlay1"]),
                    rx.text(
                        "Override the character's default kit. Solver filters "
                        "relic effects to match only the weapon classes and "
                        "playstyles you actually use.",
                        color=PAL["overlay1"], font_size="0.7rem",
                        line_height="1.4",
                    ),
                    spacing="1", align="start",
                    margin_bottom="6px",
                ),
                rx.text("Weapons", color=PAL["subtext"],
                        font_size="0.72rem", font_weight="700",
                        letter_spacing="0.04em", margin_bottom="2px"),
                rx.flex(
                    rx.foreach(
                        State.all_weapon_slugs,
                        lambda w: rx.el.button(
                            w.replace("_", " "),
                            on_click=State.toggle_weapon(w),
                            style={
                                "background": rx.cond(
                                    State.effective_weapon_types.contains(w),
                                    "rgba(203,166,247,0.20)",
                                    "transparent",
                                ),
                                "border": rx.cond(
                                    State.effective_weapon_types.contains(w),
                                    f"1px solid {PAL['mauve']}",
                                    f"1px solid {PAL['surface0']}",
                                ),
                                "color": rx.cond(
                                    State.effective_weapon_types.contains(w),
                                    PAL["mauve"],
                                    PAL["overlay1"],
                                ),
                                "padding": "2px 8px",
                                "border_radius": "4px",
                                "font_size": "0.68rem",
                                "cursor": "pointer",
                                "font_weight": "600",
                            },
                        ),
                    ),
                    wrap="wrap", gap="3px",
                    margin_bottom="10px",
                ),
                rx.text("Playstyle", color=PAL["subtext"],
                        font_size="0.72rem", font_weight="700",
                        letter_spacing="0.04em", margin_bottom="2px"),
                rx.flex(
                    rx.foreach(
                        State.all_playstyle_tags,
                        lambda t: rx.el.button(
                            t,
                            on_click=State.toggle_playstyle_tag(t),
                            style={
                                "background": rx.cond(
                                    State.effective_playstyle_tags.contains(t),
                                    "rgba(148,226,213,0.20)",
                                    "transparent",
                                ),
                                "border": rx.cond(
                                    State.effective_playstyle_tags.contains(t),
                                    f"1px solid {PAL['teal']}",
                                    f"1px solid {PAL['surface0']}",
                                ),
                                "color": rx.cond(
                                    State.effective_playstyle_tags.contains(t),
                                    PAL["teal"],
                                    PAL["overlay1"],
                                ),
                                "padding": "2px 9px",
                                "border_radius": "4px",
                                "font_size": "0.7rem",
                                "cursor": "pointer",
                                "font_weight": "600",
                            },
                        ),
                    ),
                    wrap="wrap", gap="3px",
                    margin_bottom="8px",
                ),
                rx.text("Stat scaling (damage weight)",
                        color=PAL["subtext"],
                        font_size="0.72rem", font_weight="700",
                        letter_spacing="0.04em", margin_bottom="2px",
                        margin_top="6px"),
                rx.hstack(
                    rx.icon(tag="info", size=10, color=PAL["overlay1"]),
                    rx.text(
                        "Weight 0 = stat doesn't scale damage. Higher = more "
                        "damage per +stat point. Swap relics (+STR/-DEX etc.) "
                        "are valued based on these.",
                        color=PAL["overlay1"], font_size="0.64rem",
                        line_height="1.4",
                    ),
                    spacing="1", align="start",
                    margin_bottom="4px",
                ),
                rx.vstack(
                    rx.foreach(
                        State.stat_scaling_rows,
                        lambda row: rx.hstack(
                            rx.text(row["abbr"],
                                    color=PAL["subtext"],
                                    font_size="0.72rem",
                                    font_weight="700",
                                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                                    min_width="34px"),
                            rx.slider(
                                default_value=[row["weight"]],
                                min=0.0, max=1.0, step=0.05,
                                on_change=lambda v: State.set_stat_scaling(row["stat"], v),
                                on_value_commit=lambda v: State.set_stat_scaling_commit(row["stat"], v),
                                color_scheme="purple",
                                size="1",
                                width="100%",
                            ),
                            rx.text(row["weight"].to_string(),
                                    color=PAL["text"],
                                    font_size="0.7rem",
                                    font_weight="700",
                                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                                    min_width="32px",
                                    text_align="right"),
                            spacing="1", align="center", width="100%",
                        ),
                    ),
                    spacing="1", width="100%",
                    margin_bottom="6px",
                ),
                rx.cond(
                    State.playstyle_is_customized,
                    rx.el.button(
                        rx.hstack(
                            rx.icon(tag="rotate_ccw", size=11),
                            rx.text("Reset to character defaults",
                                    font_weight="600"),
                            spacing="1", align="center",
                        ),
                        on_click=State.reset_playstyle_weapons,
                        style={
                            "background": "transparent",
                            "border": f"1px solid {PAL['surface1']}",
                            "color": PAL["overlay1"],
                            "padding": "5px 10px",
                            "border_radius": "5px",
                            "font_size": "0.72rem",
                            "cursor": "pointer",
                            "width": "100%",
                        },
                        _hover={"border_color": PAL["mauve"], "color": PAL["mauve"]},
                    ),
                    rx.box(),
                ),
                start_open=False,
            ),

            _section(
                "users",
                "Team composition",
                rx.hstack(
                    rx.icon(tag="info", size=11, color=PAL["overlay1"]),
                    rx.text(
                        "Expedition size + team-mates. Unlocks synergy effects "
                        "tied to another character's kit (e.g. 'near Totem "
                        "Stela' needs Raider in the party).",
                        color=PAL["overlay1"], font_size="0.7rem",
                        line_height="1.4",
                    ),
                    spacing="1", align="start",
                    margin_bottom="6px",
                ),
                rx.text("Party size", color=PAL["subtext"],
                        font_size="0.72rem", font_weight="700",
                        letter_spacing="0.04em", margin_bottom="4px"),
                rx.hstack(
                    rx.foreach(
                        ["1", "2", "3"],
                        lambda n: rx.el.button(
                            rx.cond(n == "1", "Solo",
                                    rx.cond(n == "2", "Duo", "Trio")),
                            on_click=State.set_party_size(n.to(int)),
                            style={
                                "background": rx.cond(
                                    State.party_size == n.to(int),
                                    "rgba(203,166,247,0.20)",
                                    "transparent",
                                ),
                                "border": rx.cond(
                                    State.party_size == n.to(int),
                                    f"1px solid {PAL['mauve']}",
                                    f"1px solid {PAL['surface0']}",
                                ),
                                "color": rx.cond(
                                    State.party_size == n.to(int),
                                    PAL["mauve"], PAL["overlay1"],
                                ),
                                "padding": "5px 14px",
                                "border_radius": "6px",
                                "font_size": "0.78rem",
                                "font_weight": "600",
                                "cursor": "pointer",
                                "flex": "1",
                            },
                        ),
                    ),
                    spacing="2", width="100%", margin_bottom="8px",
                ),
                rx.cond(
                    State.party_size > 1,
                    rx.vstack(
                        rx.text("Team-mate 2", color=PAL["subtext"],
                                font_size="0.72rem", font_weight="700",
                                letter_spacing="0.04em", margin_bottom="2px"),
                        rx.select.root(
                            rx.select.trigger(
                                placeholder="Select a character",
                                width="100%"),
                            rx.select.content(
                                rx.foreach(
                                    State.character_option_ids,
                                    lambda cid, i: rx.cond(
                                        cid != State.character_id,
                                        rx.select.item(
                                            State.character_option_labels[i],
                                            value=cid,
                                        ),
                                        rx.fragment(),
                                    ),
                                ),
                            ),
                            value=State.party_slot_ids[0],
                            on_change=lambda v: State.set_party_member(0, v),
                            size="1",
                        ),
                        spacing="1", width="100%",
                    ),
                    rx.box(),
                ),
                rx.cond(
                    State.party_size > 2,
                    rx.vstack(
                        rx.text("Team-mate 3", color=PAL["subtext"],
                                font_size="0.72rem", font_weight="700",
                                letter_spacing="0.04em",
                                margin_top="6px", margin_bottom="2px"),
                        rx.select.root(
                            rx.select.trigger(
                                placeholder="Select a character",
                                width="100%"),
                            rx.select.content(
                                rx.foreach(
                                    State.character_option_ids,
                                    lambda cid, i: rx.cond(
                                        cid != State.character_id,
                                        rx.select.item(
                                            State.character_option_labels[i],
                                            value=cid,
                                        ),
                                        rx.fragment(),
                                    ),
                                ),
                            ),
                            value=State.party_slot_ids[1],
                            on_change=lambda v: State.set_party_member(1, v),
                            size="1",
                        ),
                        spacing="1", width="100%",
                    ),
                    rx.box(),
                ),
                rx.cond(
                    State.party_members_override.length() > 0,
                    rx.el.button(
                        rx.hstack(
                            rx.icon(tag="rotate_ccw", size=11),
                            rx.text("Reset to solo", font_weight="600"),
                            spacing="1", align="center",
                        ),
                        on_click=State.reset_party,
                        style={
                            "background": "transparent",
                            "border": f"1px solid {PAL['surface1']}",
                            "color": PAL["overlay1"],
                            "padding": "5px 10px",
                            "border_radius": "5px",
                            "font_size": "0.72rem",
                            "cursor": "pointer",
                            "width": "100%",
                            "margin_top": "8px",
                        },
                        _hover={"border_color": PAL["mauve"], "color": PAL["mauve"]},
                    ),
                    rx.box(),
                ),
                start_open=False,
            ),

            _section(
                "target",
                "Build goal",
                rx.hstack(
                    rx.icon(tag="info", size=11, color=PAL["overlay1"]),
                    rx.text(
                        "Tell the solver what kind of build you want. "
                        "Undertaker defaults to pure damage; Guardian to tank; "
                        "Scholar to utility support. Adjust to taste.",
                        color=PAL["overlay1"], font_size="0.7rem",
                        line_height="1.4",
                    ),
                    spacing="1", align="start",
                    margin_bottom="6px",
                ),
                rx.vstack(
                    _goal_slider_row(
                        "damage", "⚔️", "Damage", PAL["peach"],
                        State.effective_build_goal_weights["damage"],
                        State.set_goal_damage, State.set_goal_damage_commit,
                    ),
                    _goal_slider_row(
                        "survival", "🛡️", "Survival", PAL["green"],
                        State.effective_build_goal_weights["survival"],
                        State.set_goal_survival, State.set_goal_survival_commit,
                    ),
                    _goal_slider_row(
                        "utility", "⚡", "Utility", PAL["yellow"],
                        State.effective_build_goal_weights["utility"],
                        State.set_goal_utility, State.set_goal_utility_commit,
                    ),
                    _goal_slider_row(
                        "team", "🤝", "Team support", PAL["mauve"],
                        State.effective_build_goal_weights["team"],
                        State.set_goal_team, State.set_goal_team_commit,
                    ),
                    spacing="2", width="100%",
                ),
                rx.cond(
                    State.build_goal_is_customized,
                    rx.el.button(
                        rx.hstack(
                            rx.icon(tag="rotate_ccw", size=11),
                            rx.text("Reset to character defaults",
                                    font_weight="600"),
                            spacing="1", align="center",
                        ),
                        on_click=State.reset_build_goals,
                        style={
                            "background": "transparent",
                            "border": f"1px solid {PAL['surface1']}",
                            "color": PAL["overlay1"],
                            "padding": "5px 10px",
                            "border_radius": "5px",
                            "font_size": "0.72rem",
                            "cursor": "pointer",
                            "width": "100%",
                            "margin_top": "6px",
                        },
                        _hover={"border_color": PAL["mauve"], "color": PAL["mauve"]},
                    ),
                    rx.box(),
                ),
                start_open=False,
            ),

            _section(
                "sliders-horizontal",
                "Controls",
                _controls_row(),
            ),

            _section(
                "bookmark",
                "Presets",
                rx.el.button(
                    rx.hstack(
                        rx.icon(tag="save", size=14),
                        rx.text("Save current build", font_weight="600"),
                        spacing="1",
                        align="center",
                    ),
                    on_click=State.open_preset,
                    style={
                        "background": PAL["mauve"],
                        "border": "1px solid transparent",
                        "color": PAL["crust"],
                        "padding": "8px 12px",
                        "border_radius": "6px",
                        "font_size": "0.82rem",
                        "cursor": "pointer",
                        "width": "100%",
                    },
                ),
                rx.cond(
                    State.saved_presets.length() == 0,
                    rx.box(
                        rx.text("No presets saved for this character.",
                                color=PAL["overlay0"], font_size="0.74rem",
                                font_style="italic"),
                        padding="8px 4px",
                    ),
                    rx.vstack(
                        rx.foreach(State.saved_presets, _preset_row),
                        spacing="1",
                        width="100%",
                        margin_top="4px",
                    ),
                ),
            ),

            type="multiple",
            default_value=State.sidebar_open_sections,
            variant="ghost",
            width="100%",
        ),

        padding="14px 16px",
        background=PAL["crust"],
        border_right=f"1px solid {PAL['surface0']}",
        width="320px",
        min_width="320px",
        height="100vh",
        overflow_y="auto",
        position="sticky",
        top="0",
    )
