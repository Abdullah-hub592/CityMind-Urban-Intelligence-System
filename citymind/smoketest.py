"""Headless smoke test - runs init + 30 sim steps without GUI."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulation import runner

if __name__ == "__main__":
    print("=== INIT ===")
    runner.initialize()
    print("=== STEP LOOP ===")
    for i in range(30):
        runner.step()
    s = runner.get_stats()
    print("=== FINAL STATS ===")
    for k, v in s.items():
        print(f"  {k}: {v}")
    print("OK")
