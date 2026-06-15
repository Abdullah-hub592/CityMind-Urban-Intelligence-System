"""Police dispatch via K-Means zone-spread."""
import numpy as np
from sklearn.cluster import KMeans
from core.city_graph import graph
from core.event_bus import bus, RISK_UPDATED, POLICE_MOVED

NUM_OFFICERS = 10
_positions = []
_initialized = False


def _on_risk_update(_data):
    run()


def run():
    global _positions, _initialized
    if not _initialized:
        _initialized = True
        bus.subscribe(RISK_UPDATED, _on_risk_update)

    # Clear previous assignments
    for n in graph.all_nodes():
        graph.get_node(n)["police_assigned"] = False

    # Eligible nodes: anything except Empty land (no patrols on unbuilt land)
    eligible = [n for n in graph.all_nodes()
                if graph.get_node(n)["location_type"] != "Empty"]

    # Direct allocation by risk:
    #   High-risk cells get an officer first (1 each, up to NUM_OFFICERS)
    #   Then medium-risk cells get the remaining via weighted K-Means clusters
    high = [n for n in eligible if graph.get_node(n)["predicted_risk"] == "High"]
    med  = [n for n in eligible if graph.get_node(n)["predicted_risk"] == "Medium"]
    low  = [n for n in eligible if graph.get_node(n)["predicted_risk"] == "Low"]

    positions = []
    used = set()

    # Step 1: cover every High-risk node directly (priority placement).
    for n in high:
        if len(positions) >= NUM_OFFICERS:
            break
        positions.append(n); used.add(n)

    # Step 2: spread remaining officers across Medium-risk clusters using
    #         risk-weighted K-Means.
    remaining = NUM_OFFICERS - len(positions)
    if remaining > 0 and med:
        coords = np.array([graph.get_node(n)["grid_pos"] for n in med], dtype=float)
        weights = np.array([graph.get_node(n)["risk_index"] for n in med])
        k = min(remaining, len(med))
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(coords, sample_weight=weights)
        for ctr in km.cluster_centers_:
            best, best_d = None, float("inf")
            for n in med:
                if n in used:
                    continue
                p = graph.get_node(n)["grid_pos"]
                d = (p[0] - ctr[0]) ** 2 + (p[1] - ctr[1]) ** 2
                if d < best_d:
                    best_d, best = d, n
            if best is not None:
                positions.append(best); used.add(best)

    # Step 3: top-up from low-risk only if officers remain
    if len(positions) < NUM_OFFICERS:
        low.sort(key=lambda n: graph.get_node(n)["population_density"], reverse=True)
        for n in low:
            if len(positions) >= NUM_OFFICERS:
                break
            if n not in used:
                positions.append(n); used.add(n)

    for n in positions:
        graph.get_node(n)["police_assigned"] = True

    if positions != _positions:
        _positions = positions
        bus.publish(POLICE_MOVED, {"positions": list(_positions)})
    print(f"[Police] {len(_positions)} officers deployed.")
    return list(_positions)


def get_positions():
    return list(_positions)
