# CityMind — Urban Intelligence System

An intelligent city simulation that integrates **6 AI techniques** on a shared
10×10 grid graph, visualised in real time with PyQt6.

## AI Techniques Demonstrated

| # | Technique | Module | Challenge |
|---|-----------|--------|-----------|
| 1 | **CSP** — Backtracking + AC-3 + Min-Conflicts | `challenges/c1_layout.py` | C1 City Layout |
| 2 | **Genetic Algorithm** | `challenges/c2_roads.py` | C2 Road Network |
| 3 | **K-Means + Decision Tree** | `challenges/c5_crime.py` | C5 Crime Risk |
| 4 | **Simulated Annealing** | `challenges/c3_ambulance.py` | C3 Ambulance Placement |
| 5 | **K-Means zone-spread** | `challenges/c_police.py` | Police Dispatch |
| 6 | **A\*** with admissible heuristic + dynamic replanning | `challenges/c4_routing.py` | C4 Emergency Routing |

## Architecture

```
citymind/
├── core/
│   ├── city_graph.py     # Singleton networkx graph (single source of truth)
│   └── event_bus.py      # Singleton publish/subscribe system
├── challenges/           # 6 AI modules
├── simulation/runner.py  # 30-step orchestrator
├── ui/display.py         # PyQt6 dark-themed UI
└── main.py               # Entry point
```

All modules read from the same `graph` object and communicate exclusively
through `bus.publish` / `bus.subscribe` events
(`ROAD_BLOCKED`, `RISK_UPDATED`, `AMBULANCE_MOVED`, etc.).

## Installation

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

Initialisation (CSP solve + GA road build + ML training) takes ~5–15 s on
first launch; the UI shows a status message while it runs in a background
thread.

## Controls

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `→` | Step forward one tick |
| `R` | Toggle road overlay |
| `A` | Toggle ambulance coverage |
| `C` | Toggle crime heatmap |
| `P` | Toggle police zones |
| `F` | Toggle A\* path |
| `D` | Toggle population-density opacity |
| `Ctrl+R` | Reset simulation (keeps layout) |
| `Ctrl+I` | Re-initialise full new city |
| `Ctrl+S` | Save event log |

## Simulation

Default 30 steps, configurable 5–100 via the *Max steps* slider.

Each step:
1. 20% chance to flood a random road → `ROAD_BLOCKED`.
2. Medical team advances one A\* hop (replans on block).
3. Every 5 steps: ambulance SA repositioning.
4. Every 10 steps: K-Means+DT risk refresh → police redistribute.

A summary dialog appears at completion with rescued count, repositions,
worst-case distance, and final risk distribution.

## Live-modification readiness

Because every change is propagated through the `EventBus`, a constraint can be
edited at runtime — e.g. `graph.update_risk(node, "High")` instantly forces
ambulance SA + police K-Means + A\* edge-cost refresh.

## Files produced

`citymind_log.txt` — full event log auto-saved on exit.
