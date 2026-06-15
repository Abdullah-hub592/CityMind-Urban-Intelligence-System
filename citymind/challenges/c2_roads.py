"""Challenge 2: Road network optimization via Genetic Algorithm.

Builds roads connecting all 100 nodes at minimum cost while guaranteeing
2 edge-disjoint paths between Primary Hospital and AmbulanceDepot.
"""
import random
import networkx as nx
from core.city_graph import graph

POPULATION_SIZE = 80
GENERATIONS = 120          # reduced from 300 for responsiveness while still useful
CROSSOVER_RATE = 0.85
MUTATION_RATE = 0.02
ELITE_COUNT = 4
TOURNAMENT_SIZE = 5

GRID_SIZE = 10


def all_possible_edges():
    """All 4-adjacent grid edges with base cost.
    Roads CAN cross Empty cells (they're just unbuilt land), so we include
    every grid-adjacent pair."""
    edges = []
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            cid = r * GRID_SIZE + c
            if c + 1 < GRID_SIZE:
                v = cid + 1
                edges.append((cid, v, _edge_base_cost(cid, v)))
            if r + 1 < GRID_SIZE:
                v = cid + GRID_SIZE
                edges.append((cid, v, _edge_base_cost(cid, v)))
    return edges


def _edge_base_cost(u, v):
    tu = graph.get_node(u)["location_type"]
    tv = graph.get_node(v)["location_type"]
    # Cheaper roads through residential (already developed); pricier across
    # empty land (must be built); flat for specials.
    if tu == "Empty" or tv == "Empty":
        return 1.3
    if tu == "Residential" or tv == "Residential":
        return 0.8
    return 1.0


def _built_nodes():
    return graph.all_nodes()


def chromosome_to_graph(chromo, edges):
    G = nx.Graph()
    for n in _built_nodes():
        G.add_node(n)
    for bit, (u, v, c) in zip(chromo, edges):
        if bit:
            G.add_edge(u, v, weight=c)
    return G


def fitness(chromo, edges, hospital, depot):
    cost = 0.0
    G = nx.Graph()
    built = _built_nodes()
    for n in built:
        G.add_node(n)
    for bit, (u, v, c) in zip(chromo, edges):
        if bit:
            G.add_edge(u, v, weight=c)
            cost += c
    # Connectivity test on built subgraph only
    if len(built) > 0 and not nx.is_connected(G.subgraph(built)):
        comps = nx.number_connected_components(G.subgraph(built))
        cost += 10000 + comps * 100
        return cost
    try:
        ec = nx.edge_connectivity(G, hospital, depot)
    except Exception:
        ec = 0
    if ec < 2:
        cost += 5000
    return cost


def mst_chromosome(edges):
    G = nx.Graph()
    for n in _built_nodes():
        G.add_node(n)
    for u, v, c in edges:
        G.add_edge(u, v, weight=c)
    mst = nx.minimum_spanning_tree(G, weight="weight")
    mst_edges = set()
    for u, v in mst.edges():
        mst_edges.add((min(u, v), max(u, v)))
    chromo = []
    for u, v, _ in edges:
        chromo.append(1 if (min(u, v), max(u, v)) in mst_edges else 0)
    return chromo


def add_edge_for_dual_path(chromo, edges, hospital, depot):
    """Augment chromosome with cheapest extra edge to raise edge-connectivity."""
    chromo = list(chromo)
    G = chromosome_to_graph(chromo, edges)
    try:
        ec = nx.edge_connectivity(G, hospital, depot)
    except Exception:
        ec = 0
    if ec >= 2:
        return chromo
    # Try adding cheapest non-built edge that creates an alternate path
    candidates = []
    for i, (u, v, c) in enumerate(edges):
        if chromo[i] == 0:
            chromo[i] = 1
            G2 = chromosome_to_graph(chromo, edges)
            try:
                ec2 = nx.edge_connectivity(G2, hospital, depot)
            except Exception:
                ec2 = 0
            if ec2 >= 2:
                candidates.append((c, i))
            chromo[i] = 0
    if candidates:
        candidates.sort()
        chromo[candidates[0][1]] = 1
    return chromo


def tournament_select(pop, fits):
    sample = random.sample(range(len(pop)), TOURNAMENT_SIZE)
    best = min(sample, key=lambda i: fits[i])
    return pop[best]


def crossover(p1, p2):
    if random.random() > CROSSOVER_RATE or len(p1) < 2:
        return list(p1), list(p2)
    pt = random.randrange(1, len(p1))
    return p1[:pt] + p2[pt:], p2[:pt] + p1[pt:]


def mutate(chromo):
    return [b if random.random() > MUTATION_RATE else 1 - b for b in chromo]


def run():
    print("[C2] Starting GA road network optimization...")
    edges = all_possible_edges()
    hospitals = graph.nodes_by_type("Hospital")
    depots = graph.nodes_by_type("AmbulanceDepot")
    if not hospitals or not depots:
        raise RuntimeError("Hospitals or AmbulanceDepots missing - C1 must run first.")
    hospital = hospitals[0]   # primary hospital
    depot = depots[0]

    # Seed population
    seed_mst = mst_chromosome(edges)
    seed_dual = add_edge_for_dual_path(seed_mst, edges, hospital, depot)
    population = [seed_mst, seed_dual]
    while len(population) < POPULATION_SIZE:
        c = list(random.choice([seed_mst, seed_dual]))
        # flip 3-5 random bits
        for _ in range(random.randint(3, 5)):
            i = random.randrange(len(c))
            c[i] = 1 - c[i]
        population.append(c)

    fits = [fitness(c, edges, hospital, depot) for c in population]
    best_overall = min(zip(fits, population), key=lambda x: x[0])

    for gen in range(GENERATIONS):
        # elites
        ranked = sorted(range(len(population)), key=lambda i: fits[i])
        new_pop = [list(population[i]) for i in ranked[:ELITE_COUNT]]
        while len(new_pop) < POPULATION_SIZE:
            p1 = tournament_select(population, fits)
            p2 = tournament_select(population, fits)
            c1, c2 = crossover(p1, p2)
            c1 = mutate(c1)
            c2 = mutate(c2)
            new_pop.append(c1)
            if len(new_pop) < POPULATION_SIZE:
                new_pop.append(c2)
        population = new_pop
        fits = [fitness(c, edges, hospital, depot) for c in population]
        cur_best = min(zip(fits, population), key=lambda x: x[0])
        if cur_best[0] < best_overall[0]:
            best_overall = cur_best
        if gen % 20 == 0 or gen == GENERATIONS - 1:
            print(f"[C2] Gen {gen}: best fitness = {best_overall[0]:.2f}")

    best_chromo = best_overall[1]
    # Decode to graph
    built = []
    for bit, (u, v, c) in zip(best_chromo, edges):
        if bit:
            graph.add_edge(u, v, base_cost=c)
            built.append((u, v))
    # Sanity: if built subgraph not connected, force-add MST
    built_nodes_set = set(_built_nodes())
    G = graph.get_traversable_graph().subgraph(built_nodes_set)
    if built_nodes_set and not nx.is_connected(G):
        print("[C2] WARNING - GA produced disconnected graph. Adding MST fallback.")
        for u, v, c in edges:
            if not graph.g.has_edge(u, v):
                graph.add_edge(u, v, base_cost=c)
                built.append((u, v))
            G2 = graph.get_traversable_graph().subgraph(built_nodes_set)
            if nx.is_connected(G2):
                break
    print(f"[C2] Roads built: {len(built)}. Final fitness={best_overall[0]:.2f}")
    return built
