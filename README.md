🏙️ CityMind — Urban Intelligence System
An AI-powered city simulation that integrates 6 classical AI techniques on a shared 10×10 grid graph, visualised in real time with a PyQt6 dark-themed UI.

📌 Project Overview
CityMind is a multi-agent urban simulation built as an AI course final project. It models a smart city where six independent AI modules — each solving a distinct urban challenge — operate simultaneously on a shared graph. Every module communicates exclusively through a publish/subscribe EventBus, making the system loosely coupled and live-modification-ready.

The simulation covers city layout planning, road network optimization, ambulance deployment, emergency routing, crime risk assessment, and police dispatch — all running in real time across 30 configurable steps.

🤖 AI Techniques Demonstrated
#	Challenge	AI Technique	Module
C1	City Layout Planning	CSP — Backtracking + AC-3 + Min-Conflicts	challenges/c1_layout.py
C2	Road Network Design	Genetic Algorithm	challenges/c2_roads.py
C3	Ambulance Placement	Simulated Annealing	challenges/c3_ambulance.py
C4	Emergency Routing	A* with admissible heuristic + dynamic replanning	challenges/c4_routing.py
C5	Crime Risk Assessment	K-Means + Decision Tree	challenges/c5_crime.py
C6	Police Dispatch	K-Means zone-spread	challenges/c_police.py
🗂️ Project Structure
citymind/
├── core/
│   ├── city_graph.py        # Singleton networkx graph (single source of truth)
│   └── event_bus.py         # Singleton publish/subscribe event system
├── challenges/
│   ├── c1_layout.py         # CSP: city layout with building type constraints
│   ├── c2_roads.py          # Genetic Algorithm: optimal road placement
│   ├── c3_ambulance.py      # Simulated Annealing: ambulance depot positioning
│   ├── c4_routing.py        # A*: dynamic emergency vehicle routing
│   ├── c5_crime.py          # K-Means + Decision Tree: crime risk heatmap
│   └── c_police.py          # K-Means: police zone coverage
├── simulation/
│   └── runner.py            # 30-step simulation orchestrator
├── ui/
│   └── display.py           # PyQt6 dark-themed real-time UI
├── main.py                  # Application entry point
├── smoketest.py             # Headless integration test
└── requirements.txt
All modules read from the same shared graph object and communicate through typed bus.publish / bus.subscribe events (ROAD_BLOCKED, RISK_UPDATED, AMBULANCE_MOVED, etc.).

⚙️ Installation
Prerequisites
Python 3.10+
pip
Steps
git clone https://github.com/your-username/citymind.git
cd citymind
pip install -r requirements.txt
Requirements:

PyQt6>=6.5
networkx>=3.0
scikit-learn>=1.3
numpy>=1.24
▶️ Running the Simulation
python main.py
Note: First launch takes 5–15 seconds while the CSP solver, Genetic Algorithm road builder, and ML models initialise in a background thread. The UI displays a status message during this time.

🎮 Controls
Key	Action
Space	Play / Pause simulation
→	Step forward one tick
R	Toggle road overlay
A	Toggle ambulance coverage
C	Toggle crime heatmap
P	Toggle police zones
F	Toggle A* path display
D	Toggle population-density opacity
Ctrl+R	Reset simulation (keeps layout)
Ctrl+I	Re-initialise full new city
Ctrl+S	Save event log
🔁 Simulation Loop
Default 30 steps (configurable 5–100 via the Max steps slider).

Each step:

20% chance to flood a random road → fires ROAD_BLOCKED
Medical team advances one A* hop (replans dynamically on block)
Every 5 steps: ambulance SA repositioning
Every 10 steps: K-Means + Decision Tree risk refresh → police redistribute
A summary dialog appears at completion showing rescued count, repositions, worst-case distance, and final risk distribution.

🏗️ Architecture Highlights
Single source of truth: All AI modules share one networkx graph object via core/city_graph.py.
Event-driven communication: Modules never call each other directly — all state changes propagate through EventBus, making the system extensible and testable.
Live-modification ready: Calling graph.update_risk(node, "High") at runtime instantly triggers ambulance SA + police K-Means + A* edge-cost refresh across all subscribed modules.
📄 Output
citymind_log.txt — Full simulation event log, auto-saved on exit.
