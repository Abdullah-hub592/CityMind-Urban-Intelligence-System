"""Challenge 5: Crime risk pipeline - K-Means + Decision Tree."""
import random
import numpy as np
import networkx as nx
from sklearn.cluster import KMeans
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from core.city_graph import graph

_classifier = None  # cached after first train


def _industrial_proximity(node_id):
    """Distance from `node_id` to the NEAREST OTHER industrial cell.
    Excludes self — otherwise industrials would always get the max value
    (1.0) and dominate the risk score."""
    G = graph.get_traversable_graph()
    industrials = [i for i in graph.nodes_by_type("Industrial") if i != node_id]
    if not industrials or node_id not in G:
        return 0.0
    best = float("inf")
    for ind in industrials:
        if ind not in G:
            continue
        try:
            d = nx.shortest_path_length(G, node_id, ind)
            if d < best:
                best = d
        except nx.NetworkXNoPath:
            continue
    if best == float("inf"):
        return 0.0
    return 1.0 / (1.0 + best)


def _build_features():
    # Every non-Empty cell is a candidate for crime classification.
    # Industrials, hospitals, schools, etc. all get risk labels — but the
    # feature set avoids the trivial bias that made industries always High.
    nodes = [n for n in graph.all_nodes()
             if graph.get_node(n)["location_type"] != "Empty"]
    feats = []
    for n in nodes:
        d = graph.get_node(n)
        feats.append([d["population_density"], _industrial_proximity(n)])
    return nodes, np.array(feats)


def run(_=None):
    global _classifier
    print("[C5] Running crime risk pipeline...")
    nodes, X = _build_features()

    # K-Means with elbow analysis
    inertias = []
    for k in range(1, 9):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        km.fit(X)
        inertias.append(km.inertia_)
    print(f"[C5] K-Means elbow inertias K=1..8: {[round(i,2) for i in inertias]}")

    km = KMeans(n_clusters=3, random_state=42, n_init=10)
    cluster_ids = km.fit_predict(X)
    for n, cid in zip(nodes, cluster_ids):
        graph.get_node(n)["cluster_id"] = int(cid)

    # Synthetic labels (percentile-based so we always get a realistic
    # High/Medium/Low spread regardless of feature scale).
    pd = X[:, 0]
    ip = X[:, 1]
    norm_pd = (pd - pd.min()) / (pd.max() - pd.min() + 1e-9)
    norm_ip = (ip - ip.min()) / (ip.max() - ip.min() + 1e-9)
    rng = np.random.RandomState()  # different jitter each run
    # 35% density + 35% industrial-proximity + 30% random noise — noise is
    # large enough that no cell type is systematically High or Low.
    score = 0.35 * norm_pd + 0.35 * norm_ip + 0.30 * rng.uniform(0, 1, size=len(X))
    # Top ~20% High, next ~50% Medium, bottom ~30% Low
    p_high = np.quantile(score, 0.80)
    p_med  = np.quantile(score, 0.30)
    labels = np.where(score >= p_high, "High",
              np.where(score >= p_med, "Medium", "Low"))

    # Decision Tree
    X_full = np.column_stack([X, cluster_ids])
    X_train, X_test, y_train, y_test = train_test_split(
        X_full, labels, test_size=0.2, random_state=42, stratify=labels if len(set(labels)) > 1 else None
    )
    clf = DecisionTreeClassifier(max_depth=5, random_state=42)
    clf.fit(X_train, y_train)
    acc = accuracy_score(y_test, clf.predict(X_test))
    print(f"[C5] Decision Tree accuracy={acc:.3f} importances={clf.feature_importances_.round(3).tolist()}")
    _classifier = clf

    predictions = clf.predict(X_full)
    mapping = {n: lbl for n, lbl in zip(nodes, predictions)}
    graph.update_risks_bulk(mapping)

    counts = {"High": 0, "Medium": 0, "Low": 0}
    for v in mapping.values():
        counts[v] += 1
    print(f"[C5] Risk distribution: {counts}")
    return mapping
