# 🏙️ CityMind — Urban Intelligence System

An AI-powered smart city simulation that integrates 6 classical AI techniques on a shared 10×10 grid graph, visualized in real time using a PyQt6 dark-themed interface.

---

## 📌 Project Overview

CityMind is a multi-agent urban simulation built as an AI course final project. It models a smart city where six independent AI modules operate simultaneously on a shared graph structure.

Each module solves a different urban challenge:

- City layout planning
- Road network optimization
- Ambulance positioning
- Emergency routing
- Crime risk prediction
- Police dispatch

All modules communicate through a publish/subscribe EventBus, ensuring a loosely coupled and fully event-driven system.

The simulation runs across 30 configurable steps with real-time updates affecting all modules.

---

## 🤖 AI Techniques Demonstrated

### 🧠 C1: City Layout Planning
- CSP (Constraint Satisfaction Problem)
- Backtracking + AC-3 + Min-Conflicts
- `challenges/c1_layout.py`

### 🚧 C2: Road Network Design
- Genetic Algorithm optimization
- `challenges/c2_roads.py`

### 🚑 C3: Ambulance Placement
- Simulated Annealing
- Optimal ambulance positioning
- `challenges/c3_ambulance.py`

### 🚨 C4: Emergency Routing
- A* Search algorithm
- Admissible heuristic + dynamic replanning
- `challenges/c4_routing.py`

### 📊 C5: Crime Risk Assessment
- K-Means clustering
- Decision Tree classification
- `challenges/c5_crime.py`

### 👮 C6: Police Dispatch
- K-Means zone clustering
- Dynamic police allocation
- challenges/c_police.py

---

## 🗂️ Project Structure

```text
citymind/
├── core/
│   ├── city_graph.py        # Shared NetworkX graph (single source of truth)
│   └── event_bus.py         # Publish/subscribe event system
│
├── challenges/
│   ├── c1_layout.py         # CSP city layout
│   ├── c2_roads.py          # Genetic algorithm road optimization
│   ├── c3_ambulance.py      # Simulated annealing placement
│   ├── c4_routing.py        # A* emergency routing
│   ├── c5_crime.py          # Crime prediction system
│   └── c_police.py          # Police zone clustering
│
├── simulation/
│   └── runner.py            # 30-step simulation engine
│
├── ui/
│   └── display.py           # PyQt6 real-time UI (dark theme)
│
├── main.py                  # Application entry point
├── smoketest.py             # Headless integration test
└── requirements.txt
```
▶️ Running the Simulation
```text
python main.py
```
Notes
First run may take 5–15 seconds
Initializes:
CSP solver
Genetic algorithm
ML models
UI shows loading status during startup
🎮 Controls
Space → Play / Pause simulation
Right Arrow → Step forward one tick
R → Toggle road overlay
A → Toggle ambulance coverage
C → Toggle crime heatmap
P → Toggle police zones
F → Toggle A* path visualization
D → Toggle population density view
Ctrl + R → Reset simulation (keep layout)
Ctrl + I → Rebuild entire city
Ctrl + S → Save event log
🔁 Simulation Workflow

The simulation runs for 30 steps (configurable 5–100).

Each Step
20% chance road flooding → triggers ROAD_BLOCKED event
Ambulances move using A*
Dynamic replanning if path is blocked
Every 5 Steps
Simulated Annealing optimizes ambulance placement
Every 10 Steps
K-Means + Decision Tree updates crime prediction
Police zones are redistributed
🧠 System Behavior
All modules react dynamically to graph changes
EventBus propagates updates instantly
Example flow:
Road blocked → rerouting → ambulance shift → police update
🏗️ Key Design Highlights
Single shared NetworkX graph
Event-driven architecture
Fully decoupled AI modules
Real-time system updates
Scalable multi-agent design
📄 Output
citymind_log.txt
Complete simulation event log
Auto-saved on exit
