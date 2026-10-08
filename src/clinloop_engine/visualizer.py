"""
visualizer.py — ClinLoop AI Figure Generator

Creates publication-quality plots from benchmark results.
Generates ROC/PR curves, comparison charts, and alert fatigue analysis.
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
import seaborn as plt_sns
import networkx as nx
from typing import Dict, List

# Setup matplotlib styling
plt.style.use('seaborn-v0_8-whitegrid')
COLORS = {
    "ClinLoop AI": "#0288d1",      # Blue
    "EMR Baseline": "#757575",     # Gray
    "LLM Baseline": "#f57c00",     # Orange
    "Light Blue": "#e1f5fe",
    "Light Orange": "#ffe0b2",
    "Light Gray": "#eeeeee"
}

class Visualizer:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
    def plot_roc_curves(self, results: Dict):
        """Plot ROC curves for all methods."""
        plt.figure(figsize=(8, 6), dpi=300)
        
        for name, metrics in results["overall"].items():
            fpr = metrics["fpr"]
            tpr = metrics["tpr"]
            auc = metrics["roc_auc"]
            plt.plot(fpr, tpr, lw=2, color=COLORS[name], 
                     label=f"{name} (AUC = {auc:.3f})")
            
        plt.plot([0, 1], [0, 1], 'k--', lw=1.5, alpha=0.5)
        plt.xlim([-0.02, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel("False Positive Rate (1 - Specificity)", fontsize=12)
        plt.ylabel("True Positive Rate (Sensitivity)", fontsize=12)
        plt.title("Receiver Operating Characteristic (ROC)", fontsize=14, pad=15)
        plt.legend(loc="lower right", fontsize=11)
        plt.tight_layout()
        
        path = os.path.join(self.output_dir, "fig1_roc_curves.png")
        plt.savefig(path)
        plt.close()
        print(f"  ✓ Saved {path}")
        
    def plot_pr_curves(self, results: Dict):
        """Plot Precision-Recall curves."""
        plt.figure(figsize=(8, 6), dpi=300)
        
        for name, metrics in results["overall"].items():
            prec = metrics["pr_prec"]
            rec = metrics["pr_rec"]
            auc = metrics["pr_auc"]
            plt.plot(rec, prec, lw=2, color=COLORS[name], 
                     label=f"{name} (AUC = {auc:.3f})")
            
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel("Recall (Sensitivity)", fontsize=12)
        plt.ylabel("Precision (PPV)", fontsize=12)
        plt.title("Precision-Recall Curve", fontsize=14, pad=15)
        plt.legend(loc="lower left", fontsize=11)
        plt.tight_layout()
        
        path = os.path.join(self.output_dir, "fig2_pr_curves.png")
        plt.savefig(path)
        plt.close()
        print(f"  ✓ Saved {path}")
        
    def plot_comparison_bars(self, results: Dict):
        """Side-by-side comparison of key metrics."""
        metrics_to_plot = ["sensitivity", "specificity", "f1_score"]
        labels = ["Sensitivity (Recall)", "Specificity", "F1 Score"]
        
        models = list(results["overall"].keys())
        n_models = len(models)
        
        plt.figure(figsize=(10, 6), dpi=300)
        x = np.arange(len(metrics_to_plot))
        width = 0.25
        
        for i, model in enumerate(models):
            values = [results["overall"][model][m] for m in metrics_to_plot]
            pos = x - width + (i * width)
            bars = plt.bar(pos, values, width, label=model, color=COLORS[model])
            
            # Add text labels on bars
            for bar in bars:
                height = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                         f'{height:.2f}', ha='center', va='bottom', fontsize=10)
                
        plt.ylabel('Score', fontsize=12)
        plt.title('Performance Comparison: ClinLoop vs Baselines', fontsize=14, pad=15)
        plt.xticks(x, labels, fontsize=12)
        plt.ylim(0, 1.1)
        plt.legend(loc='lower center', bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=11)
        plt.tight_layout()
        
        path = os.path.join(self.output_dir, "fig3_comparison_bars.png")
        plt.savefig(path)
        plt.close()
        print(f"  ✓ Saved {path}")
        
    def plot_alert_fatigue(self, results: Dict):
        """Plot alert fatigue (false positives per 100 cases)."""
        models = list(results["overall"].keys())
        fatigue_values = [results["overall"][m]["alert_fatigue"] for m in models]
        
        plt.figure(figsize=(8, 5), dpi=300)
        x = np.arange(len(models))
        
        colors = [COLORS[m] for m in models]
        bars = plt.bar(x, fatigue_values, 0.5, color=colors)
        
        # Add values on top
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                     f'{height:.1f}', ha='center', va='bottom', fontsize=11)
            
        plt.ylabel('False Alerts / 100 Patients', fontsize=12)
        plt.title('Alert Fatigue Analysis (Lower is Better)', fontsize=14, pad=15)
        plt.xticks(x, models, fontsize=12)
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        path = os.path.join(self.output_dir, "fig4_alert_fatigue.png")
        plt.savefig(path)
        plt.close()
        print(f"  ✓ Saved {path}")
        
    def generate_all(self, results: Dict):
        """Generate all figures."""
        print("Generating visualization figures...")
        self.plot_roc_curves(results)
        self.plot_pr_curves(results)
        self.plot_comparison_bars(results)
        self.plot_alert_fatigue(results)
