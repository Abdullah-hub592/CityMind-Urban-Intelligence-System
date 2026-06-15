"""Challenge 4: A* dynamic routing for medical team."""
import heapq
import math
import random
from core.city_graph import graph
from core.event_bus import bus, ROAD_BLOCKED, REROUTE, CIVILIAN_RESCUED

_state = {
    "team_pos": None,
    "depot": None,
    "civilians": [],          # unrescued civilian node IDs
    "rescued": [],
    "current_target": None,
    "current_path": [],       # full node-list path including team_pos
    "initialized": False,
    "complete": False,
}


def _euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _heuristic(n, goal):
    pa = graph.get_node(n)["grid_pos"]
    pb = graph.get_node(goal)["grid_pos"]
    return 0.8 * _euclid(pa, pb)


def a_star(start, goal):
    if start == goal:
        return [start]
    open_set = []
    counter = 0
    heapq.heappush(open_set, (0 + _heuristic(start, goal), counter, start))
    came_from = {}
    g_score = {start: 0.0}
    closed = set()
    while open_set:
        f, _, cur = heapq.heappop(open_set)
        if cur == goal:
            # reconstruct
            path = [cur]
            while cur in came_from:
                cur = came_from[cur]
                path.append(cur)
            return list(reversed(path))
        if cur in closed:
            continue
        closed.add(cur)
        for nb in graph.g.neighbors(cur):
            edata = graph.get_edge(cur, nb)
            if edata.get("is_blocked"):
                continue
            cost = edata.get("effective_cost", 1.0)
            tentative = g_score[cur] + cost
            if tentative < g_score.get(nb, float("inf")):
                g_score[nb] = tentative
                came_from[nb] = cur
                counter += 1
                heapq.heappush(open_set, (tentative + _heuristic(nb, goal), counter, nb))
    return None


def _pick_nearest(targets, from_node):
    best = None
    best_path = None
    best_cost = float("inf")
    for t in targets:
        path = a_star(from_node, t)
        if path is None:
            continue
        cost = 0.0
        for i in range(len(path) - 1):
            cost += graph.get_edge(path[i], path[i + 1])["effective_cost"]
        if cost < best_cost:
            best_cost = cost
            best = t
            best_path = path
    return best, best_path


def _on_road_blocked(_data):
    if _state["complete"] or not _state["initialized"]:
        return
    if _state["current_target"] is None:
        return
    new_path = a_star(_state["team_pos"], _state["current_target"])
    if new_path is None:
        # current target unreachable - pick another
        targets = [c for c in _state["civilians"] if c not in _state["rescued"]]
        targets = [t for t in targets if t != _state["current_target"]]
        if not targets:
            _state["complete"] = True
            return
        nxt, path = _pick_nearest(targets, _state["team_pos"])
        if nxt is None:
            _state["complete"] = True
            return
        _state["current_target"] = nxt
        _state["current_path"] = path
        bus.publish(REROUTE, {"from": _state["team_pos"], "to": nxt, "len": len(path)})
    else:
        _state["current_path"] = new_path
        bus.publish(REROUTE, {"from": _state["team_pos"], "to": _state["current_target"], "len": len(new_path)})


def run():
    """Initialize: pick depot, 4 random civilian targets, compute first path."""
    depots = graph.nodes_by_type("AmbulanceDepot")
    residentials = graph.nodes_by_type("Residential")
    if not depots or len(residentials) < 4:
        raise RuntimeError("Need depot + at least 4 residential nodes.")
    depot = depots[0]
    civilians = random.sample(residentials, 4)
    _state.update({
        "team_pos": depot,
        "depot": depot,
        "civilians": list(civilians),
        "rescued": [],
        "current_target": None,
        "current_path": [],
        "complete": False,
    })
    if not _state["initialized"]:
        _state["initialized"] = True
        bus.subscribe(ROAD_BLOCKED, _on_road_blocked)

    nxt, path = _pick_nearest(civilians, depot)
    _state["current_target"] = nxt
    _state["current_path"] = path or [depot]
    print(f"[C4] Team at {depot}, civilians={civilians}, first target={nxt}")
    return civilians


def advance_one_step():
    if _state["complete"]:
        return None
    path = _state["current_path"]
    if not path or len(path) < 2:
        # already at target
        if _state["team_pos"] == _state["current_target"]:
            return _arrive()
        # try replanning
        if _state["current_target"] is not None:
            new_path = a_star(_state["team_pos"], _state["current_target"])
            if new_path and len(new_path) >= 2:
                _state["current_path"] = new_path
                path = new_path
            else:
                return None
        else:
            return None
    # move to next node
    next_node = path[1]
    _state["team_pos"] = next_node
    _state["current_path"] = path[1:]
    if next_node == _state["current_target"]:
        return _arrive()
    return {"moved_to": next_node}


def _arrive():
    target = _state["current_target"]
    if target is None:
        return None
    if target not in _state["rescued"]:
        _state["rescued"].append(target)
        bus.publish(CIVILIAN_RESCUED, {"node": target, "rescued": list(_state["rescued"])})
    remaining = [c for c in _state["civilians"] if c not in _state["rescued"]]
    if not remaining:
        _state["complete"] = True
        _state["current_target"] = None
        _state["current_path"] = [_state["team_pos"]]
        return {"rescued": target, "complete": True}
    nxt, path = _pick_nearest(remaining, _state["team_pos"])
    if nxt is None:
        _state["complete"] = True
        return {"rescued": target, "complete": True}
    _state["current_target"] = nxt
    _state["current_path"] = path
    return {"rescued": target, "next_target": nxt}


def get_current_path():
    return list(_state["current_path"])


def get_team_position():
    return _state["team_pos"]


def get_civilians():
    return list(_state["civilians"])


def get_rescued():
    return list(_state["rescued"])


def get_current_target():
    return _state["current_target"]


def is_complete():
    return _state["complete"]
