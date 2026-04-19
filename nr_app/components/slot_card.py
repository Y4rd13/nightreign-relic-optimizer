"""Slot card with inline edit buttons per attribute + named-relic button in header."""

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


def _vessel_pill(vessel_color) -> rx.Component:
    return rx.cond(
        vessel_color != "",
        rx.hstack(
            rx.text("vessel:", color=PAL["overlay1"], font_size="0.7rem"),
            color_pill(vessel_color),
            spacing="1",
            align="center",
        ),
        rx.box(),
    )


def _accent_for_slot(slot) -> rx.Var:
    """Return the border-left accent color: vessel colour if set, else default."""
    return rx.match(
        slot.vessel_color,
        ("R", COLOR_SLOT["R"][1]),
        ("G", COLOR_SLOT["G"][1]),
        ("B", COLOR_SLOT["B"][1]),
        ("Y", COLOR_SLOT["Y"][1]),
        ("U", rx.match(
            slot.color_hint,
            ("green", PAL["green"]), ("yellow", PAL["yellow"]),
            ("blue", PAL["blue"]), ("red", PAL["red"]),
            ("any", PAL["lavender"]),
            PAL["lavender"],
        )),
        rx.match(
            slot.color_hint,
            ("green", PAL["green"]), ("yellow", PAL["yellow"]),
            ("blue", PAL["blue"]), ("red", PAL["red"]),
            ("any", PAL["lavender"]),
            PAL["lavender"],
        ),
    )


def _attr_row(slot_idx, attr_idx, attr, is_locked_pinned, is_locked_exact, is_fixed,
              is_named_relic) -> rx.Component:
    """Render one attribute row.

    LOCKED badge = the slot belongs to a known Named Relic (Glass Necklace,
    boss drop, shop item). For those, the 3 attrs are game-fixed as a trio,
    and the whole slot gets replaced via the Named Relic dialog, not
    attr-by-attr.

    For regular Common/Deep slots, attrs show the Edit button and an
    individual lock toggle. The lock toggle persists the user's preference
    for that single attr — useful when you want 1-2 of the 3 fixed and let
    the solver re-roll the rest.
    """
    # For fixed Remembrance slots (slot 1 legacy), never show Edit/Lock.
    actions = rx.cond(
        is_fixed,
        rx.box(
            rx.text("fixed", color=PAL["overlay0"],
                    font_size="0.7rem", font_style="italic"),
            padding="3px 8px",
        ),
        rx.hstack(
            rx.el.button(
                rx.hstack(
                    rx.icon(tag="pencil", size=12),
                    rx.text("Edit", font_weight="600"),
                    spacing="1", align="center",
                ),
                on_click=State.open_edit(slot_idx, attr_idx),
                style={
                    "background": "transparent",
                    "border": f"1px solid {PAL['surface1']}",
                    "color": PAL["subtext"],
                    "padding": "3px 10px",
                    "border_radius": "5px",
                    "font_size": "0.74rem",
                    "font_weight": "600",
                    "cursor": "pointer",
                },
                _hover={
                    "background": "rgba(203,166,247,0.08)",
                    "border_color": PAL["mauve"],
                    "color": PAL["mauve"],
                },
            ),
            rx.tooltip(
                rx.el.button(
                    rx.icon(
                        tag=rx.cond(is_locked_exact, "lock", "lock_open"),
                        size=12,
                    ),
                    on_click=State.toggle_attr_lock(slot_idx, attr_idx),
                    style={
                        "background": rx.cond(
                            is_locked_exact,
                            "rgba(249,226,175,0.15)",
                            "transparent",
                        ),
                        "border": rx.cond(
                            is_locked_exact,
                            "1px solid rgba(249,226,175,0.35)",
                            f"1px solid {PAL['surface1']}",
                        ),
                        "color": rx.cond(
                            is_locked_exact,
                            PAL["yellow"],
                            PAL["overlay1"],
                        ),
                        "padding": "3px 8px",
                        "border_radius": "5px",
                        "cursor": "pointer",
                    },
                    _hover={"color": PAL["mauve"], "border_color": PAL["mauve"]},
                ),
                content=rx.cond(
                    is_locked_exact,
                    "Unlock this attr — solver is free to swap it",
                    "Lock this attr — solver will keep it as-is",
                ),
            ),
            spacing="1",
        ),
    )

    return rx.box(
        # meta row
        rx.hstack(
            rx.box(
                rx.text("Attr ", display="inline", opacity=0.7),
                rx.text(attr_idx + 1, display="inline", font_weight="700"),
                background=PAL["surface0"], color=PAL["subtext"],
                padding="2px 8px", border_radius="4px",
                font_size="0.72rem",
                min_width="52px",
                display="inline-flex",
                align_items="center",
                justify_content="center",
                height="20px",
            ),
            attr_id_box(attr.id),
            attr_sort(attr.sort),
            flag_badge(attr.flag),
            tier_badge(attr.tier),
            group_badge(attr.group),
            rx.cond(
                is_named_relic,
                rx.box(
                    rx.hstack(
                        rx.icon(tag="lock", size=10),
                        rx.text("LOCKED", font_weight="700"),
                        spacing="1", align="center",
                    ),
                    background="rgba(249,226,175,0.18)",
                    color=PAL["yellow"],
                    border="1px solid",
                    border_color="rgba(249,226,175,0.35)",
                    padding="2px 8px", border_radius="4px",
                    font_size="0.66rem",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                    display="inline-flex", align_items="center", height="20px",
                    title="Named Relic trio — use the Named relic button to replace as a whole",
                ),
                rx.cond(
                    is_locked_pinned,
                    rx.box(
                        rx.text("edited", font_weight="600"),
                        color=PAL["overlay1"],
                        padding="2px 8px", border_radius="4px",
                        font_size="0.64rem",
                        font_style="italic",
                        font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                        display="inline-flex", align_items="center", height="20px",
                        title="Manually edited — solver respects this pick. Use the revert icon to restore solver's choice.",
                    ),
                    rx.box(),
                ),
            ),
            # Contribution pill: non-zero weighted delta wins regardless of
            # status (textual-fallback effects still score via the text-parsed
            # value proxy). Only when contribution is exactly zero do we fall
            # back to the status icon:
            #   · modeled  + zero → small grey "0" (bucket dominated / gated)
            #   · textual  + zero → grey ⓘ (value in text, weight=0 for this build)
            #   · flat           → nothing (flavour / informational)
            rx.cond(
                attr.contribution != 0.0,
                rx.tooltip(
                    rx.box(
                        rx.hstack(
                            rx.text(
                                rx.cond(attr.contribution > 0, "+", ""),
                                font_size="0.62rem",
                                font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                            ),
                            rx.text(
                                attr.contribution.to_string(),
                                font_size="0.62rem",
                                font_weight="700",
                                font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                            ),
                            spacing="0",
                            align="center",
                        ),
                        background=rx.match(
                            attr.contrib_axis,
                            ("survival", "rgba(166,227,161,0.15)"),
                            ("utility", "rgba(249,226,175,0.15)"),
                            ("team", "rgba(203,166,247,0.15)"),
                            "rgba(250,179,135,0.15)",   # damage (peach)
                        ),
                        color=rx.match(
                            attr.contrib_axis,
                            ("survival", PAL["green"]),
                            ("utility", PAL["yellow"]),
                            ("team", PAL["mauve"]),
                            PAL["peach"],
                        ),
                        border="1px solid",
                        border_color=rx.match(
                            attr.contrib_axis,
                            ("survival", "rgba(166,227,161,0.35)"),
                            ("utility", "rgba(249,226,175,0.35)"),
                            ("team", "rgba(203,166,247,0.35)"),
                            "rgba(250,179,135,0.35)",
                        ),
                        padding="2px 7px",
                        border_radius="4px",
                        display="inline-flex",
                        align_items="center",
                        height="20px",
                        cursor="help",
                    ),
                    content=(
                        "Weighted score delta if removed.  "
                        "Breakdown (pre-weight): "
                        "damage=" + attr.contrib_damage.to_string()
                        + "  survival=" + attr.contrib_survival.to_string()
                        + "  utility=" + attr.contrib_utility.to_string()
                        + "  team=" + attr.contrib_team.to_string()
                        + ".  Each axis × its goal weight = shown total. "
                        "Defensive effects appear here via survival weight."
                    ),
                ),
                rx.match(
                    attr.contrib_status,
                    (
                        "modeled",
                        rx.tooltip(
                            rx.box(
                                rx.text(
                                    "0",
                                    font_size="0.62rem",
                                    font_weight="700",
                                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                                ),
                                background=PAL["surface0"],
                                color=PAL["overlay1"],
                                border=f"1px solid {PAL['surface1']}",
                                padding="2px 7px",
                                border_radius="4px",
                                display="inline-flex",
                                align_items="center",
                                height="20px",
                                cursor="help",
                            ),
                            content=(
                                "Modeled effect, but no marginal contribution in this build: "
                                "either another effect dominates its bucket, "
                                "or its condition (uptime slider) is inactive."
                            ),
                        ),
                    ),
                    (
                        "textual",
                        rx.tooltip(
                            rx.box(
                                rx.icon(tag="info", size=11),
                                background=PAL["surface0"],
                                color=PAL["overlay1"],
                                border=f"1px solid {PAL['surface1']}",
                                padding="2px 6px",
                                border_radius="4px",
                                display="inline-flex",
                                align_items="center",
                                height="20px",
                                cursor="help",
                            ),
                            content=(
                                "Effect value lives only in its description "
                                "(e.g. '…by 20%'). With the current goal "
                                "weights it scores zero here — either its axis "
                                "weight is 0 (team w=0 for solo, etc.) or the "
                                "text-parsed estimate cancels out."
                            ),
                        ),
                    ),
                    rx.box(),
                ),
            ),
            rx.spacer(),
            actions,
            spacing="2",
            align="center",
            width="100%",
            flex_wrap="wrap",
        ),
        rx.box(
            attr.name,
            color=PAL["text"],
            font_size="0.94rem",
            line_height="1.45",
            word_break="break-word",
            margin_top="6px",
        ),
        rx.cond(
            attr.effect_text != "",
            rx.box(
                rx.icon(tag="equal", size=11, color=PAL["mauve"],
                        display="inline-block", vertical_align="middle",
                        margin_right="4px"),
                rx.text(attr.effect_text,
                        display="inline",
                        color=PAL["subtext"],
                        font_size="0.78rem",
                        font_style="italic",
                        line_height="1.4"),
                margin_top="3px",
            ),
            rx.box(),
        ),
        background=PAL["crust"],
        border="1px solid transparent",
        border_radius="8px",
        padding="10px 14px",
        margin_bottom="6px",
        _hover={"border_color": PAL["surface1"], "background": "#1c1c2a"},
    )


def _locked_row(attr_idx_offset, locked_label) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.box(
                rx.text("Attr ", display="inline", opacity=0.7),
                rx.text(attr_idx_offset + 1, display="inline", font_weight="700"),
                background=PAL["surface0"], color=PAL["subtext"],
                padding="2px 8px", border_radius="4px", font_size="0.72rem",
                min_width="52px", display="inline-flex", align_items="center",
                justify_content="center", height="20px",
            ),
            rx.text("LOCKED", color=PAL["overlay1"], font_weight="700",
                    font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                    font_size="0.82rem"),
            rx.text("—", color=PAL["overlay1"]),
            flag_badge("N"),
            tier_badge("STD"),
            group_badge("FIXED"),
            spacing="2", align="center", width="100%", flex_wrap="wrap",
        ),
        rx.box(locked_label, color=PAL["text"], font_size="0.94rem",
               line_height="1.45", margin_top="6px"),
        background=PAL["crust"],
        border_radius="8px",
        padding="10px 14px",
        margin_bottom="6px",
        opacity="0.7",
    )


def _debuff_edit_btn(slot_idx) -> rx.Component:
    return rx.el.button(
        rx.hstack(
            rx.icon(tag="pencil", size=11),
            rx.text("Change", font_weight="600"),
            spacing="1", align="center",
        ),
        on_click=State.open_debuff(slot_idx),
        title="Pick a different curse for this slot",
        style={
            "background": "transparent",
            "border": f"1px solid rgba(243,139,168,0.35)",
            "color": PAL["red"],
            "padding": "3px 10px",
            "border_radius": "5px",
            "font_size": "0.72rem",
            "cursor": "pointer",
        },
        _hover={
            "background": "rgba(243,139,168,0.12)",
            "border_color": PAL["red"],
        },
    )


def _debuff_add_btn(slot_idx) -> rx.Component:
    return rx.el.button(
        rx.hstack(
            rx.icon(tag="plus", size=11),
            rx.text("Pick curse", font_weight="600"),
            spacing="1", align="center",
        ),
        on_click=State.open_debuff(slot_idx),
        title="Add a curse to this slot anyway",
        style={
            "background": "transparent",
            "border": f"1px solid {PAL['surface1']}",
            "color": PAL["overlay1"],
            "padding": "3px 10px",
            "border_radius": "5px",
            "font_size": "0.72rem",
            "cursor": "pointer",
        },
        _hover={
            "background": "rgba(243,139,168,0.08)",
            "border_color": PAL["red"],
            "color": PAL["red"],
        },
    )


def _debuff_row_explicit(slot) -> rx.Component:
    slot_idx = slot.index
    return rx.cond(
        slot.debuff,
        rx.box(
            rx.hstack(
                rx.box("Debuff",
                       background="rgba(243,139,168,0.2)",
                       color=PAL["red"],
                       padding="2px 8px", border_radius="4px",
                       font_size="0.72rem", font_weight="700",
                       display="inline-flex", align_items="center", height="20px"),
                attr_id_box(slot.debuff.id),
                tier_badge(slot.debuff.tier),
                group_badge(slot.debuff.group),
                rx.spacer(),
                _debuff_edit_btn(slot_idx),
                spacing="2", align="center", width="100%",
            ),
            rx.text(slot.debuff.name, color=PAL["subtext"], font_size="0.82rem",
                    margin_top="4px"),
            rx.cond(
                slot.debuff.effect_text != "",
                rx.hstack(
                    rx.icon(tag="equal", size=11, color=PAL["red"]),
                    rx.text(slot.debuff.effect_text,
                            color=PAL["subtext"], font_size="0.76rem",
                            font_style="italic"),
                    spacing="1", align="center", margin_top="2px",
                ),
                rx.box(),
            ),
            background="rgba(243,139,168,0.08)",
            border="1px dashed rgba(243,139,168,0.35)",
            border_radius="6px",
            padding="6px 12px",
            margin_top="6px",
        ),
        rx.cond(
            slot.needs_debuff,
            rx.hstack(
                rx.text("⚠  Debuff required but not assigned",
                        color=PAL["red"], font_size="0.82rem"),
                rx.spacer(),
                _debuff_edit_btn(slot_idx),
                align="center",
                width="100%",
                padding="6px 12px", border_radius="6px",
                border="1px dashed", border_color=PAL["red"],
                margin_top="6px",
            ),
            rx.hstack(
                rx.text("— no debuff needed",
                        color=PAL["overlay0"], font_style="italic",
                        font_size="0.82rem"),
                rx.spacer(),
                _debuff_add_btn(slot_idx),
                align="center",
                width="100%",
                padding="6px 12px", border_radius="6px",
                border="1px solid", border_color=PAL["surface0"],
                margin_top="6px",
            ),
        ),
    )




def _slot_lock_btn(slot_idx, lock_state) -> rx.Component:
    """Whole-slot lock toggle. Smart click:
      · none    → lock all 3 (pins the current composition)
      · partial → lock the remaining attrs
      · full    → unlock all 3
    Colours match the per-attr toggle palette: yellow for locked, mauve hover."""
    is_locked = lock_state == "full"
    is_partial = lock_state == "partial"
    return rx.tooltip(
        rx.el.button(
            rx.hstack(
                rx.icon(
                    tag=rx.cond(is_locked, "lock", "lock_open"),
                    size=13,
                ),
                rx.text(
                    rx.cond(
                        is_locked, "Locked",
                        rx.cond(is_partial, "Lock slot (partial)", "Lock slot"),
                    ),
                    font_weight="600",
                ),
                spacing="1", align="center",
            ),
            on_click=State.toggle_slot_lock(slot_idx),
            style={
                "background": rx.cond(
                    is_locked, "rgba(249,226,175,0.15)",
                    rx.cond(is_partial, "rgba(249,226,175,0.08)", "transparent"),
                ),
                "border": rx.cond(
                    is_locked, "1px solid rgba(249,226,175,0.45)",
                    rx.cond(is_partial, "1px solid rgba(249,226,175,0.30)",
                            f"1px solid {PAL['surface1']}"),
                ),
                "color": rx.cond(
                    is_locked, PAL["yellow"],
                    rx.cond(is_partial, PAL["yellow"], PAL["subtext"]),
                ),
                "padding": "5px 12px",
                "border_radius": "6px",
                "font_size": "0.78rem",
                "cursor": "pointer",
                "transition": "all 0.12s",
            },
            _hover={
                "background": "rgba(203,166,247,0.10)",
                "border_color": PAL["mauve"],
                "color": PAL["mauve"],
            },
        ),
        content=rx.cond(
            is_locked,
            "Unlock this slot — solver is free to re-roll all 3 attrs",
            rx.cond(
                is_partial,
                "Some attrs already locked — click to lock the rest",
                "Freeze this slot's 3 attrs so the solver won't touch them",
            ),
        ),
    )


def slot_card(slot) -> rx.Component:
    slot_idx = slot.index
    accent = _accent_for_slot(slot)

    named_btn = rx.el.button(
        rx.hstack(
            rx.icon(tag="tag", size=13),
            rx.text("Named relic", font_weight="600"),
            spacing="1", align="center",
        ),
        on_click=State.open_named(slot_idx),
        title="Pick a Remembrance / shop / boss relic with fixed attrs",
        style={
            "background": "transparent",
            "border": f"1px solid {PAL['surface1']}",
            "color": PAL["subtext"],
            "padding": "5px 12px",
            "border_radius": "6px",
            "font_size": "0.78rem",
            "cursor": "pointer",
            "transition": "all 0.12s",
        },
        _hover={
            "background": "rgba(180,190,254,0.10)",
            "border_color": PAL["lavender"],
            "color": PAL["lavender"],
        },
    )

    # Solver now decides for itself whether a named relic (Remembrance / shop /
    # boss) beats a free roll in each slot, so the Unfix/Restore buttons from
    # the previous design are gone. Manual override still available via the
    # "Named relic" picker to the right.
    remembrance_btn = rx.box()

    lock_state = State.slot_lock_state[slot_idx]
    lock_btn = rx.cond(slot.is_fixed, rx.box(), _slot_lock_btn(slot_idx, lock_state))

    # ⚠ badge surfaces validation rule failures (duplicate ids, roll-group
    # collision, missing debuff, tier mismatch, foreign character tag). Never
    # shows for Remembrance fixed slots or named-relic-locked trios.
    invalid_badge = rx.cond(
        slot.validation_errors.length() > 0,
        rx.tooltip(
            rx.box(
                rx.hstack(
                    rx.icon(tag="triangle-alert", size=12),
                    rx.text("Invalid", font_weight="700"),
                    spacing="1", align="center",
                ),
                background="rgba(243,139,168,0.18)",
                color=PAL["red"],
                border="1px solid rgba(243,139,168,0.45)",
                padding="2px 8px",
                border_radius="4px",
                font_size="0.68rem",
                font_family="ui-monospace, SFMono-Regular, Menlo, monospace",
                display="inline-flex",
                align_items="center",
                height="20px",
                cursor="help",
            ),
            content=slot.validation_tooltip,
        ),
        rx.box(),
    )

    header = rx.hstack(
        rx.hstack(
            rx.box(width="10px", height="10px", border_radius="50%",
                   background=accent,
                   box_shadow=f"0 0 10px {accent}"),
            rx.text(slot.name, font_weight="600", font_size="1rem",
                    color=PAL["text"]),
            _vessel_pill(slot.vessel_color),
            invalid_badge,
            spacing="2", align="center", flex_wrap="wrap",
        ),
        rx.spacer(),
        rx.hstack(
            remembrance_btn,
            lock_btn,
            named_btn,
            rx.text("tier:", color=PAL["overlay0"], font_size="0.76rem"),
            rx.foreach(
                slot.tiers,
                lambda t: rx.text(t, color=PAL["subtext"], font_size="0.76rem",
                                  margin_right="4px",
                                  font_family="ui-monospace, SFMono-Regular, Menlo, monospace"),
            ),
            rx.cond(slot.is_fixed,
                    rx.text("· 🔒 fixed", color=PAL["overlay0"], font_size="0.76rem"),
                    rx.box()),
            spacing="2", align="center",
        ),
        width="100%",
        align="center",
        margin_bottom="10px",
        flex_wrap="wrap",
    )

    attr_rows = rx.foreach(
        slot.attrs,
        lambda a, i: _attr_row(
            slot_idx, i, a,
            # "pinned" = effect_id appears among this slot's locked set.
            # Drives the "edited" badge (informational, not exact-position).
            State.locked_effects_per_slot[slot_idx].contains(a.id),
            # "locked_exact" = the exact (slot, attr_idx) key is locked.
            # Drives the lock icon (toggle feedback) — survives duplicates
            # because it's position-keyed, not effect-id keyed.
            State.locked_keys_by_slot[slot_idx].contains(i),
            slot.is_fixed,
            # "named relic" = the slot as a whole matches a verified Named
            # Relic (Glass Necklace, boss drop, etc.). LOCKED badge only
            # shows for these.
            slot.named_relic_id != "",
        ),
    )

    locked_rows = rx.foreach(
        slot.locked_labels,
        lambda lk, j: _locked_row(slot.attrs.length() + j, lk),
    )

    return rx.box(
        header,
        attr_rows,
        locked_rows,
        _debuff_row_explicit(slot),
        background=PAL["mantle"],
        border="1px solid",
        border_color=PAL["surface0"],
        border_left=f"4px solid {accent}",
        border_radius="12px",
        padding="14px 18px 12px",
        margin_bottom="14px",
        width="100%",
    )
