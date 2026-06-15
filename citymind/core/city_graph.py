"""Singleton CityGraph - the only source of truth for city state."""
import networkx as nx
from core.event_bus import bus, ROAD_BLOCKED, ROAD_UNBLOCKED, RISK_UPDATED


RISK_LEVELS = {"High": 1.5, "Medium": 1.2, "Low": 1.0}


class CityGraph:
    def __init__(self):
        self.g = nx.Graph()

    # ---------------- Nodes ----------------
    def add_node(self, node_id, **attrs):
        defaults = {
            "location_type": "Residential",
            "population_density": 0.5,
            "risk_index": 1.0,
            "accessible": True,
            "grid_pos": (0, 0),
            "cluster_id": -1,
            "predicted_risk": "Low",
            "police_assigned": False,
        }
        defaults.update(attrs)
        self.g.add_node(node_id, **defaults)

    def get_node(self, node_id):
        return self.g.nodes[node_id]

    def all_nodes(self):
        return list(self.g.nodes())

    def nodes_by_type(self, location_type):
        return [n for n, d in self.g.nodes(data=True) if d.get("location_type") == location_type]

    # ---------------- Edges ----------------
    def add_edge(self, u, v, base_cost=1.0):
        self.g.add_edge(u, v, base_cost=base_cost, is_blocked=False)
        self._recompute_edge(u, v)

    def get_edge(self, u, v):
        return self.g.edges[u, v]

    def _recompute_edge(self, u, v):
        if not self.g.has_edge(u, v):
            return
        d = self.g.edges[u, v]
        if d.get("is_blocked", False):
            d["effective_cost"] = float("inf")
        else:
            ru = self.g.nodes[u].get("risk_index", 1.0)
            rv = self.g.nodes[v].get("risk_index", 1.0)
            d["effective_cost"] = d["base_cost"] * ((ru + rv) / 2.0)

    def block_edge(self, u, v):
        if not self.g.has_edge(u, v):
            return
        d = self.g.edges[u, v]
        if d.get("is_blocked"):
            return
        d["is_blocked"] = True
        d["effective_cost"] = float("inf")
        bus.publish(ROAD_BLOCKED, {"u": u, "v": v})

    def unblock_edge(self, u, v):
        if not self.g.has_edge(u, v):
            return
        d = self.g.edges[u, v]
        if not d.get("is_blocked"):
            return
        d["is_blocked"] = False
        self._recompute_edge(u, v)
        bus.publish(ROAD_UNBLOCKED, {"u": u, "v": v})

    def update_risk(self, node_id, level):
        if level not in RISK_LEVELS:
            level = "Low"
        self.g.nodes[node_id]["predicted_risk"] = level
        self.g.nodes[node_id]["risk_index"] = RISK_LEVELS[level]
        for v in self.g.neighbors(node_id):
            self._recompute_edge(node_id, v)
        bus.publish(RISK_UPDATED, {"node": node_id, "level": level})

    def update_risks_bulk(self, mapping: dict):
        """Apply many risk updates, then publish ONE RISK_UPDATED event."""
        for node_id, level in mapping.items():
            if level not in RISK_LEVELS:
                level = "Low"
            self.g.nodes[node_id]["predicted_risk"] = level
            self.g.nodes[node_id]["risk_index"] = RISK_LEVELS[level]
        for u, v in self.g.edges():
            self._recompute_edge(u, v)
        bus.publish(RISK_UPDATED, {"bulk": True, "count": len(mapping)})

    def unblock_all(self):
        changed = []
        for u, v, d in self.g.edges(data=True):
            if d.get("is_blocked"):
                d["is_blocked"] = False
                changed.append((u, v))
                self._recompute_edge(u, v)
        for u, v in changed:
            bus.publish(ROAD_UNBLOCKED, {"u": u, "v": v})

    def get_traversable_graph(self):
        """Return a view subgraph containing only non-blocked edges."""
        return self.g.edge_subgraph(
            [(u, v) for u, v, d in self.g.edges(data=True) if not d.get("is_blocked", False)]
        ).copy()

    def edges_data(self):
        return list(self.g.edges(data=True))

    def reset(self):
        self.g.clear()


graph = CityGraph()
