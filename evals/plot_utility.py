"""Privacy vs utility chart for the README.

python -m evals.plot_utility evals/results/utility docs/img/privacy-utility.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
ACCENT = "#2a78d6"  # the gateway (emphasis)
MUTED = "#9b9a95"  # every other condition

LABELS = {
    "plaintext": "No protection",
    "sovgate": "This gateway",
    "redact": "[REDACTED], same detection",
    "presidio": "Presidio defaults",
    "llm-guard": "LLM Guard defaults",
}


def main(src: str, dst: str) -> None:
    data = json.loads((Path(src) / "summary.json").read_text())
    summary, meta = data["summary"], data["meta"]

    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    for name, s in summary.items():
        x, y = 100 * (1 - s["outbound_leak_rate"]), 100 * s["accuracy"]
        main_point = name == "sovgate"
        ax.scatter(
            x,
            y,
            s=110 if main_point else 70,
            color=ACCENT if main_point else MUTED,
            edgecolor=SURFACE,
            linewidth=2,
            zorder=3,
        )
        ha = "right" if x > 80 else "left"
        dx = -2.2 if ha == "right" else 2.2
        dy = -5 if name == "redact" else 0  # keep clear of the Presidio label
        ax.annotate(
            f"{LABELS.get(name, name)}  {y:.0f}%",
            (x, y),
            xytext=(x + dx, y + dy),
            ha=ha,
            va="center",
            fontsize=9,
            color=INK if main_point else INK_2,
            fontweight="bold" if main_point else "normal",
        )

    ax.set_xlim(-5, 105)
    ax.set_ylim(-5, 105)
    ax.set_xlabel(
        "Personal data hidden from the model provider (%)  \u2192 more private", color=INK_2, fontsize=9
    )
    ax.set_ylabel("Questions answered correctly (%)  \u2192 more useful", color=INK_2, fontsize=9)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=8)
    ax.set_title(
        f"Privacy vs answer quality, {meta['questions']} RAG questions (EN/FR/DE), model {meta['model']}",
        fontsize=9.5,
        color=INK,
        loc="left",
    )
    fig.tight_layout()
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dst, facecolor=SURFACE)
    print(f"written {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
