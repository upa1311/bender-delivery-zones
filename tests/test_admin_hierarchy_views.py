"""User-facing hierarchy: Липканы is nested under Бендеры, never a peer."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP = (REPO / "docs/app.js").read_text("utf-8")
CSS = (REPO / "docs/styles.css").read_text("utf-8")
AUDIT = (REPO / "scripts/build_demand_audit.py").read_text("utf-8")

TOP_LEVEL = ("bender_core", "parkany", "giska", "protyagailovka")


def _block(name: str) -> str:
    m = re.search(rf"const {name} = \{{(.*?)\}};", APP, re.S)
    assert m, name
    return m.group(1)


# --- 1. top-level list holds only the four settlements ----------------------

def test_top_level_territories_are_only_the_four_settlements():
    m = re.search(r"const TOP_LEVEL_TERRITORIES = \[(.*?)\];", APP, re.S)
    assert m
    keys = re.findall(r'"([a-z_]+)"', m.group(1))
    assert keys == list(TOP_LEVEL)
    assert "bender_lipcani" not in keys


def test_lipcani_is_declared_a_district_of_bender():
    assert re.search(r"const DISTRICT_OF = \{[^}]*bender_lipcani:\s*\"bender_core\"", APP)
    assert re.search(r"const DISTRICT_LABEL = \{[^}]*bender_lipcani:\s*\"Липканы\"", APP)


# --- 2. no peer label / no peer colour --------------------------------------

def test_lipcani_is_not_a_peer_in_the_label_map():
    assert "bender_lipcani" not in _block("TERRITORY_LABEL")


def test_lipcani_has_no_separate_territory_colour():
    assert "bender_lipcani" not in _block("TERRITORY_COLOR")


def test_the_old_peer_caption_is_gone_everywhere():
    assert "Бендеры, район Липканы" not in APP


def test_district_colour_follows_the_parent_settlement():
    assert "TERRITORY_COLOR[isDistrictKey(key) ? DISTRICT_OF[key] : key]" in APP


def test_map_labels_render_a_district_in_a_subordinate_style():
    assert "area-label-district" in APP
    assert "area-label-district" in CSS


def test_polygons_use_the_parent_colour_helper():
    assert "territoryColor(f.properties.key)" in APP
    assert "TERRITORY_COLOR[f.properties.key]" not in APP


# --- 3. filters read settlement = Бендеры, district = Липканы ---------------

def test_settlement_of_maps_lipcani_to_bender():
    assert re.search(r'bender_lipcani:\s*"Бендеры"', _block("SETTLEMENT_OF"))


def test_popups_show_the_hierarchy_path_not_a_peer_name():
    assert "territoryPath(" in APP
    assert "TERRITORY_LABEL[p.territory]" not in APP
    assert "TERRITORY_LABEL[p.settlement]" not in APP


def test_territory_path_builds_parent_arrow_child():
    assert "→ ${DISTRICT_LABEL[key]}" in APP


# --- 4. statistics: districts only inside the "Районы Бендер" section --------

def test_statistics_table_excludes_districts_from_top_level_rows():
    assert "if key in district_of:" in AUDIT
    assert "continue" in AUDIT


def test_statistics_has_a_bender_districts_subsection():
    assert "### Районы Бендер" in AUDIT
    assert "Не отдельные населённые пункты" in AUDIT


# --- 5. the technical key survives for internal attribution -----------------

def test_the_technical_key_is_kept_for_attribution():
    assert "bender_lipcani" in APP           # still known internally
    assert "DISTRICT_OF" in APP              # but only via the district mapping
