"""Catppuccin Mocha palette + utility helpers for the Reflex UI."""

from __future__ import annotations

PAL = {
    "base":     "#11111b",
    "crust":    "#181825",
    "mantle":   "#1e1e2e",
    "surface0": "#313244",
    "surface1": "#45475a",
    "overlay0": "#6c7086",
    "overlay1": "#9399b2",
    "subtext":  "#bac2de",
    "text":     "#cdd6f4",
    "mauve":    "#cba6f7",
    "pink":     "#f5c2e7",
    "red":      "#f38ba8",
    "maroon":   "#eba0ac",
    "peach":    "#fab387",
    "yellow":   "#f9e2af",
    "green":    "#a6e3a1",
    "teal":     "#94e2d5",
    "sky":      "#89dceb",
    "sapphire": "#74c7ec",
    "blue":     "#89b4fa",
    "lavender": "#b4befe",
}

TIER_COLOR: dict[str, tuple[str, str]] = {
    "STD":     ("#45475a", "#bac2de"),
    "BTH":     ("#94e2d5", "#1e1e2e"),
    "DoN":     ("#cba6f7", "#11111b"),
    "ILLEGAL": ("#f38ba8", "#11111b"),
    "N/A":     ("#45475a", "#bac2de"),
}

GROUP_COLOR = {
    "CHARACTER": "#b4befe",
    "ATTACK":    "#eba0ac",
    "NONE":      "#94e2d5",
    "CURSE":     "#f38ba8",
    "HP_REST":   "#a6e3a1",
    "FP_REST":   "#89b4fa",
    "MAGIC_UP":  "#cba6f7",
    "POISON_UP": "#a6e3a1",
    "FROST_UP":  "#89dceb",
    "CRYSTAL":   "#f5c2e7",
    "PURFUME":   "#fab387",
    "SKILL":     "#f9e2af",
    "SPELL":     "#cba6f7",
    "ST_AFFINITY": "#89dceb",
    "DISCOVERY": "#74c7ec",
}

COLOR_SLOT = {
    "R": ("Red",       "#f38ba8"),
    "G": ("Green",     "#a6e3a1"),
    "B": ("Blue",      "#89b4fa"),
    "Y": ("Yellow",    "#f9e2af"),
    "U": ("Universal", "#cdd6f4"),
}


GLOBAL_STYLE = f"""
html, body, #__next {{
  background: {PAL["base"]} !important;
  color: {PAL["text"]} !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Ubuntu, sans-serif;
  margin: 0;
  min-height: 100vh;
}}
* {{ box-sizing: border-box; }}
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-track {{ background: {PAL["crust"]}; }}
::-webkit-scrollbar-thumb {{ background: {PAL["surface1"]}; border-radius: 5px; }}
::-webkit-scrollbar-thumb:hover {{ background: {PAL["overlay0"]}; }}

/* Radix / Reflex overrides to match our palette */
.rx-Root, .radix-themes {{
  --accent-9: {PAL["mauve"]};
  --accent-10: {PAL["pink"]};
  background: {PAL["base"]} !important;
}}

/* small helper classes */
.nr-mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
"""
