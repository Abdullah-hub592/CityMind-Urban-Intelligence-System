"""Simulation runner - orchestrates 30-step CityMind scenario."""
import random
from datetime import datetime

from core.city_graph import graph
from core.event_bus import (
    bus, ROAD_BLOCKED, ROAD_UNBLOCKED, RISK_UPDATED, AMBULANCE_MOVED,
    POLICE_MOVED, CIVILIAN_RESCUED, SIMULATION_STEP, REROUTE,
)
from challenges import c1_layout, c2_roads, c5_crime, c3_ambulance, c_police, c4_routing


_state = {
    "step": 0,
    "max_steps": 30,
    "log": [],
    "stats": {
        "roads_blocked": 0,
        "roads_unblocked": 0,
        "ambulance_repositions": 0,
        "police_repositions": 0,
        "rescued": 0,
        "crime_refreshes": 0,
        "reroutes": 0,
    },
    "initialized": False,
    "subs_attached": False,
}

MAX_LOG = 500


def _log(step, etype, detail):
    entry = {
        "step": step,
        "type": etype,
        "detail": detail,
        "timestamp": datetime.now(),
    }
    _state["log"].append(entry)
    if len(_state["log"]) > MAX_LOG:
        del _state["log"][0]
    return entry


def _on_road_blocked(d):
    _state["stats"]["roads_blocked"] += 1
    _log(_state["step"], ROAD_BLOCKED, f"Road ({d.get('u')},{d.get('v')}) blocked.")


def _on_road_unblocked(d):
    _state["stats"]["roads_unblocked"] += 1
    _log(_state["step"], ROAD_UNBLOCKED, f"Road ({d.get('u')},{d.get('v')}) cleared.")


def _on_risk(d):
    if d.get("bulk"):
        _log(_state["step"], RISK_UPDATED, f"Crime risk refresh ({d.get('count', 0)} nodes).")


def _on_amb(d):
    _state["stats"]["ambulance_repositions"] += 1
    _log(_state["step"], AMBULANCE_MOVED, f"Ambulances at {d.get('positions')}, worst={d.get('worst_dist',0):.2f}")


def _on_police(d):
    _state["stats"]["police_repositions"] += 1
    _log(_state["step"], POLICE_MOVED, f"Police redistributed ({len(d.get('positions',[]))} officers).")


def _on_rescue(d):
    _state["stats"]["rescued"] = len(d.get("rescued", []))
    _log(_state["step"], CIVILIAN_RESCUED, f"Civilian {d.get('node')} rescued. {_state['stats']['rescued']}/4")


def _on_reroute(d):
    _state["stats"]["reroutes"] += 1
    _log(_state["step"], REROUTE, f"A* replanned {d.get('from')}→{d.get('to')} (len={d.get('len')}).")


def _attach_subs():
    if _state["subs_attached"]:
        return
    bus.subscribe(ROAD_BLOCKED, _on_road_blocked)
    bus.subscribe(ROAD_UNBLOCKED, _on_road_unblocked)
    bus.subscribe(RISK_UPDATED, _on_risk)
    bus.subscribe(AMBULANCE_MOVED, _on_amb)
    bus.subscribe(POLICE_MOVED, _on_police)
    bus.subscribe(CIVILIAN_RESCUED, _on_rescue)
    bus.subscribe(REROUTE, _on_reroute)
    _state["subs_attached"] = True


def initialize():
    """Run full initialisation pipeline (C1 → C2 → C5 → C3 → Police → C4)."""
    _attach_subs()
    _state["step"] = 0
    _state["log"].clear()
    for k in _state["stats"]:
        _state["stats"][k] = 0
    _log(0, "INIT", "Initialising city...")
    c1_layout.run()
    c2_roads.run()
    c5_crime.run()
    c3_ambulance.run()
    c_police.run()
    c4_routing.run()
    _state["initialized"] = True
    _log(0, "INIT", "City ready. Starting simulation.")


def reset():
    """Reset to step 0 but keep layout."""
    _state["step"] = 0
    for k in _state["stats"]:
        _state["stats"][k] = 0
    graph.unblock_all()
    c4_routing.run()       # reset team to depot, choose new civilians? keep targets simple - reset
    _log(0, "RESET", "Simulation reset to step 0.")


def step():
    if _state["step"] >= _state["max_steps"]:
        return None
    _state["step"] += 1
    s = _state["step"]
    bus.publish(SIMULATION_STEP, {"step": s})

    # a) flood event 20%
    if random.random() < 0.20:
        edges = [(u, v) for u, v, d in graph.g.edges(data=True) if not d.get("is_blocked")]
        if edges:
            u, v = random.choice(edges)
            graph.block_edge(u, v)

    # b) advance team
    if not c4_routing.is_complete():
        c4_routing.advance_one_step()

    # c) every 3 steps perturb population density of a few residentials
    if s % 3 == 0:
        residentials = graph.nodes_by_type("Residential")
        if residentials:
            for n in random.sample(residentials, min(8, len(residentials))):
                d = graph.get_node(n)
                # gaussian-ish jitter, clamped to [0.2, 1.0]
                new_d = d["population_density"] + random.uniform(-0.15, 0.15)
                d["population_density"] = max(0.2, min(1.0, new_d))

    # d) every 5 steps re-run SA
    if s % 5 == 0:
        c3_ambulance.run()

    # e) every 10 steps re-run crime  (this fires RISK_UPDATED which
    #     auto-triggers ambulance + police via event subscriptions)
    if s % 10 == 0:
        _state["stats"]["crime_refreshes"] += 1
        c5_crime.run()

    _log(s, SIMULATION_STEP, f"Step {s} complete.")

    if s >= _state["max_steps"]:
        _log(s, "COMPLETE", "Simulation finished.")
    return _state["log"][-1]


def set_max_steps(n):
    _state["max_steps"] = max(1, int(n))


def get_max_steps():
    return _state["max_steps"]


def get_step():
    return _state["step"]


def get_log():
    return list(_state["log"])


def get_stats():
    s = dict(_state["stats"])
    # risk distribution (exclude Empty land — no risk classification there)
    counts = {"High": 0, "Medium": 0, "Low": 0}
    for n in graph.all_nodes():
        nd = graph.get_node(n)
        if nd["location_type"] == "Empty":
            continue
        counts[nd["predicted_risk"]] = counts.get(nd["predicted_risk"], 0) + 1
    s["risk"] = counts
    s["step"] = _state["step"]
    s["max_steps"] = _state["max_steps"]
    s["police_count"] = len(c_police.get_positions())
    s["civilians_total"] = len(c4_routing.get_civilians())
    return s


def is_complete():
    return _state["step"] >= _state["max_steps"]
