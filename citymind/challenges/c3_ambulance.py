"""Challenge 3: Ambulance placement via Simulated Annealing (minimax)."""
import math
import random
import networkx as nx
from core.city_graph import graph
from core.event_bus import bus, ROAD_BLOCKED, ROAD_UNBLOCKED, RISK_UPDATED, AMBULANCE_MOVED

T_INIT = 100.0
T_MIN = 0.01
COOLING = 0.995

_positions = []
_dist = {}
_initialized = False
_recompute_pending = False


def _compute_distance_matrix():
    global _dist
    G = graph.get_traversable_graph()
    # use effective_cost as weight
    for u, v, d in graph.g.edges(data=True):
        if G.has_edge(u, v):
            G.edges[u, v]["w"] = d.get("effective_cost", d.get("base_cost", 1.0))
    _dist = dict(nx.all_pairs_dijkstra_path_length(G, weight="w"))


UNREACHABLE_PENALTY = 1000.0


RISK_WEIGHT = {"High": 2.0, "Medium": 1.2, "Low": 1.0}


def _energy(positions):
    """Risk-weighted worst-case distance.

    For each residential, compute min distance to any ambulance and multiply
    by its risk weight. The objective is the max over all residentials —
    so SA pulls ambulances toward HIGH-risk residentials when risk changes.
    """
    residentials = graph.nodes_by_type("Residential")
    worst = 0.0
    for r in residentials:
        best = float("inf")
        for a in positions:
            d = _dist.get(r, {}).get(a, float("inf"))
            if d < best:
                best = d
        if best == float("inf"):
            best = UNREACHABLE_PENALTY
        risk = graph.get_node(r).get("predicted_risk", "Low")
        weighted = best * RISK_WEIGHT.get(risk, 1.0)
        if weighted > worst:
            worst = weighted
    return worst


def _neighbor(positions):
    new_pos = list(positions)
    idx = random.randrange(len(new_pos))
    cur = new_pos[idx]
    neighbors = list(graph.g.neighbors(cur))
    if not neighbors:
        return new_pos
    nxt = random.choice(neighbors)
    if nxt in new_pos:
        return new_pos
    new_pos[idx] = nxt
    return new_pos


def _sa_search(initial):
    cur = list(initial)
    cur_e = _energy(cur)
    best = list(cur)
    best_e = cur_e
    T = T_INIT
    while T > T_MIN:
        new_pos = _neighbor(cur)
        new_e = _energy(new_pos)
        dE = new_e - cur_e
        if dE < 0 or random.random() < math.exp(-dE / max(T, 1e-9)):
            cur = new_pos
            cur_e = new_e
            if cur_e < best_e:
                best = list(cur)
                best_e = cur_e
        T *= COOLING
    return best, best_e


def _on_change(_data):
    global _recompute_pending
    _recompute_pending = True
    # Eagerly reposition
    run()


def run():
    """Run SA placement; uses current positions as starting point if available."""
    global _positions, _initialized
    _compute_distance_matrix()
    depots = graph.nodes_by_type("AmbulanceDepot")
    all_nodes = graph.all_nodes()

    if not _positions:
        # Seed: start from depots, then a residential center
        seed = list(depots[:2])
        # add one extra position from random residential
        residentials = graph.nodes_by_type("Residential")
        if residentials:
            seed.append(random.choice(residentials))
        while len(seed) < 3:
            seed.append(random.choice(all_nodes))
        _positions = seed[:3]

    new_positions, energy = _sa_search(_positions)
    moved = new_positions != _positions
    _positions = new_positions
    if not _initialized:
        _initialized = True
        bus.subscribe(ROAD_BLOCKED, _on_change)
        bus.subscribe(ROAD_UNBLOCKED, _on_change)
        bus.subscribe(RISK_UPDATED, _on_change)
    if moved:
        bus.publish(AMBULANCE_MOVED, {"positions": list(_positions), "worst_dist": energy})
    print(f"[C3] Ambulance positions: {_positions}, worst-case dist={energy:.3f}")
    return list(_positions)


def get_positions():
    return list(_positions)


def get_worst_distance():
    if not _dist:
        return 0.0
    return _energy(_positions)
