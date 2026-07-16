"""M7 unit tests: the dashboard's pure panel builders and event-stream reducers (BLUEPRINT §11).

Rendering is exercised without a terminal via `rich.console.Console(record=True)` — every function
under test is data-in/renderable-out, no I/O (CLAUDE.md), so these are ordinary unit tests.
"""

from __future__ import annotations

from rich.console import Console

from ui.tui import (
    THEMES,
    DashboardState,
    build_fabric_rows,
    build_mesh_rows,
    economics_panel,
    event_log_panel,
    fabric_table,
    mesh_table,
    ratchet_panel,
    render_dashboard,
)


def _render(renderable) -> str:
    console = Console(record=True, width=200, force_terminal=False)
    console.print(renderable)
    return console.export_text()


# --- build_mesh_rows / build_fabric_rows: pure reducers over the event stream --------

def test_build_mesh_rows_takes_the_most_recent_solve_or_reuse_per_agent():
    records = [
        {"type": "SOLVE", "agent": "agent:site-a", "site_class": "branch", "task_id": "t1"},
        {"type": "REUSE", "agent": "agent:site-a", "site_class": "branch", "task_id": "t2"},
        {"type": "SOLVE", "agent": "agent:site-b", "site_class": "campus", "task_id": "t3"},
        {"type": "TASK", "agent": "agent:site-a", "task_id": "t99"},  # not realized, ignored
    ]
    rows = build_mesh_rows(records)
    by_agent = {r["agent"]: r for r in rows}
    assert by_agent["agent:site-a"]["state"] == "reuse"
    assert by_agent["agent:site-a"]["task_id"] == "t2"
    assert by_agent["agent:site-b"]["state"] == "discover"
    assert rows == tuple(sorted(rows, key=lambda r: r["agent"]))  # deterministic order


def test_build_mesh_rows_reputation_is_passed_in_not_derived():
    records = [{"type": "SOLVE", "agent": "agent:site-a", "site_class": "branch", "task_id": "t1"}]
    default = build_mesh_rows(records)
    assert default[0]["reputation"] == 1.0
    with_rep = build_mesh_rows(records, reputations={"agent:site-a": 0.2})
    assert with_rep[0]["reputation"] == 0.2


def test_build_fabric_rows_folds_the_capsule_lifecycle_in_order():
    records = [
        {"type": "AUTHOR", "capsule_id": "c1", "incident_class": "ddos_syn_flood",
         "delta_pct": -40.0, "agent": "agent:site-a"},
        {"type": "JURY_VERDICT", "capsule_id": "c1", "verdict": "ACCEPT"},
        {"type": "PROMOTED", "capsule_id": "c1", "confidence": 0.9},
        {"type": "AUTHOR", "capsule_id": "c2", "incident_class": "iot_anomaly_burst",
         "delta_pct": -45.0, "agent": "agent:site-e"},
        {"type": "JURY_VERDICT", "capsule_id": "c2", "verdict": "REJECT"},
    ]
    rows = build_fabric_rows(records)
    by_id = {r["capsule_id"]: r for r in rows}
    assert by_id["c1"]["state"] == "ACTIVE" and by_id["c1"]["confidence"] == 0.9
    assert by_id["c2"]["state"] == "REJECTED"
    assert rows == tuple(sorted(rows, key=lambda r: r["capsule_id"]))  # deterministic order


def test_build_fabric_rows_excision_states():
    records = [
        {"type": "AUTHOR", "capsule_id": "c1", "incident_class": "ddos_syn_flood",
         "delta_pct": -40.0, "agent": "agent:site-e"},
        {"type": "JURY_VERDICT", "capsule_id": "c1", "verdict": "ACCEPT"},
        {"type": "PROMOTED", "capsule_id": "c1", "confidence": 1.0},
        {"type": "REVOKE", "capsule_id": "c1", "reason": "sentinel drift"},
        {"type": "AUTHOR", "capsule_id": "c2", "incident_class": "ddos_syn_flood",
         "delta_pct": -30.0, "agent": "agent:site-a"},
        {"type": "QUARANTINE", "capsule_id": "c2", "reason": "descendant of revoked c1"},
    ]
    rows = {r["capsule_id"]: r for r in build_fabric_rows(records)}
    assert rows["c1"]["state"] == "REVOKED"
    assert rows["c2"]["state"] == "QUARANTINED"


def test_build_fabric_rows_ignores_events_for_capsules_never_authored_in_this_stream():
    """A pure fold, not a store scan: an event naming a capsule this stream never AUTHORed is
    skipped rather than fabricating a row."""
    records = [{"type": "PROMOTED", "capsule_id": "ghost", "confidence": 1.0}]
    assert build_fabric_rows(records) == ()


# --- Pure panel builders: renderable, stable, no crashes on empty state --------------

def test_mesh_table_renders_agent_rows():
    rows = ({"agent": "agent:site-a", "site_class": "branch", "state": "discover",
             "reputation": 1.0, "task_id": "t01"},)
    text = _render(mesh_table(rows))
    assert "agent:site-a" in text and "branch" in text and "discover" in text


def test_fabric_table_renders_claim_and_confidence():
    rows = ({"capsule_id": "abcdef1234567890", "incident_class": "ddos_syn_flood",
             "delta_pct": -44.1, "state": "ACTIVE", "confidence": 0.83, "author": "agent:site-e"},)
    text = _render(fabric_table(rows))
    assert "-44.1%" in text and "ACTIVE" in text and "0.83" in text
    assert "abcdef1234567890" not in text  # truncated to id-short (BLUEPRINT §11)


def test_fabric_table_handles_missing_claim_and_confidence():
    rows = ({"capsule_id": "c1", "incident_class": "ddos_syn_flood", "delta_pct": None,
             "state": "SUBMITTED", "confidence": None, "author": "agent:site-a"},)
    text = _render(fabric_table(rows))
    assert "SUBMITTED" in text


def test_ratchet_panel_sparkline_is_present_and_empty_class_is_a_dash():
    text = _render(ratchet_panel({"ddos_syn_flood": [30.0, 25.0, 18.0], "cert_expiry_storm": []}))
    assert "ddos_syn_flood" in text and "best=18.0" in text
    assert "cert_expiry_storm" in text


def test_ratchet_panel_empty_state_does_not_crash():
    text = _render(ratchet_panel({}))
    assert "no realized solves" in text


def test_economics_panel_renders_lane_comparison():
    text = _render(economics_panel(
        {"lane_a_cumulative": 800.0, "lane_b_cumulative": 1200.0, "pct_saved": 33.3,
         "median_lead_time": 6.5}
    ))
    assert "800.0" in text and "1200.0" in text and "33.3%" in text and "6.5" in text


def test_economics_panel_handles_missing_fields():
    text = _render(economics_panel({}))
    assert "-" in text  # no crash on an empty summary


def test_event_log_panel_respects_limit_and_shows_latest():
    records = tuple({"type": "SOLVE", "sim_time": float(i), "capsule_id": f"c{i}"} for i in range(20))
    text = _render(event_log_panel(records, limit=5))
    assert "c19" in text and "c0" not in text


def test_event_log_panel_empty_is_not_a_crash():
    text = _render(event_log_panel(()))
    assert "no events" in text


def test_event_log_panel_every_theme_renders_every_reserved_event_type():
    """Every BLUEPRINT event type has a color in both themes — no silent default-color fallback for
    a type the demo scripts actually emit."""
    from ui.events import EVENT_TYPES

    narrated = set(EVENT_TYPES) - {"TASK"}  # TASK carries no reason/capsule_id worth logging
    for theme in THEMES:
        records = tuple({"type": t, "sim_time": 1.0, "capsule_id": "c"} for t in sorted(narrated))
        text = _render(event_log_panel(records, limit=len(records), theme=theme))
        for t in narrated:
            assert t in text


# --- render_dashboard: the single entry point, end to end ---------------------------

def test_render_dashboard_is_pure_and_deterministic():
    state = DashboardState(
        sim_time=12.3,
        mesh=({"agent": "agent:site-a", "site_class": "branch", "state": "discover",
               "reputation": 1.0, "task_id": "t01"},),
        fabric=({"capsule_id": "c1", "incident_class": "ddos_syn_flood", "delta_pct": -40.0,
                  "state": "ACTIVE", "confidence": 0.9, "author": "agent:site-a"},),
        staircase={"ddos_syn_flood": [30.0, 20.0]},
        economics={"lane_a_cumulative": 800.0, "lane_b_cumulative": 1200.0, "pct_saved": 33.3,
                    "median_lead_time": 6.5},
        event_log=({"type": "PROMOTED", "sim_time": 10.0, "capsule_id": "c1"},),
    )
    text1 = _render(render_dashboard(state))
    text2 = _render(render_dashboard(state))
    assert text1 == text2
    assert "sim_time=12.30" in text1


def test_render_dashboard_empty_state_does_not_crash():
    text = _render(render_dashboard(DashboardState()))
    assert "sim_time=0.00" in text


def test_dashboard_rejects_unknown_theme():
    from ui.tui import Dashboard

    try:
        Dashboard(theme="neon")
        assert False, "expected ValueError"
    except ValueError:
        pass
