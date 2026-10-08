"""
run_benchmark.py — Main Entry Script for ClinLoop AI

Executes the full pipeline:
1. Generates 300 synthetic patient trajectories
2. Runs the ClinLoop AI engine (Hypergraph + Safety Clock + Risk Scorer)
3. Runs EMR and LLM baselines
4. Calculates metrics and generates benchmark figures
"""

import os
import sys

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.clinloop_engine.data_generator import generate_all_scenarios, save_scenarios
from src.clinloop_engine.benchmark import BenchmarkSuite
from src.clinloop_engine.visualizer import Visualizer

def main():
    print("=" * 60)
    print(" ClinLoop AI: Neuro-Symbolic Open-Loop Detection Engine")
    print(" ClinLoop AI - Benchmark Suite")
    print("=" * 60)
    
    # 1. Setup paths
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    data_dir = os.path.join(base_dir, "data", "synthetic")
    results_dir = os.path.join(base_dir, "results")
    
    # 2. Generate Synthetic Data
    print("\n[1/4] Generating synthetic clinical trajectories...")
    scenarios = generate_all_scenarios(n_total=300)
    save_scenarios(scenarios, data_dir)
    
    # 3. Run Benchmarks
    print("\n[2/4] Executing baseline algorithms and ClinLoop AI...")
    suite = BenchmarkSuite(scenarios)
    results = suite.run()
    
    print("\n[3/4] Calculating metrics and saving results...")
    suite.save_results(results_dir)
    
    # Print summary table
    print("\n" + "-"*55)
    print(f"{'Model':<20} | {'Sens':<6} | {'Spec':<6} | {'F1':<6} | {'F.Alerts':<8}")
    print("-" * 55)
    for model, metrics in results["overall"].items():
        sens = metrics["sensitivity"]
        spec = metrics["specificity"]
        f1 = metrics["f1_score"]
        fa = metrics["alert_fatigue"]
        print(f"{model:<20} | {sens:.3f}  | {spec:.3f}  | {f1:.3f}  | {fa:5.1f}/100")
    print("-" * 55)
    
    # 4. Generate Visualizations
    print("\n[4/4] Generating publication-quality figures...")
    vis = Visualizer(results_dir)
    vis.generate_all(results)
    
    print("\n" + "=" * 60)
    print("✓ Complete! All benchmark results and figures are saved.")
    print(f"Results JSON: {os.path.join(results_dir, 'benchmark_results.json')}")
    print(f"Figures Dir:  {results_dir}/")
    print("=" * 60)

if __name__ == "__main__":
    main()
