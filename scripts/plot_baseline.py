import csv, collections, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

SRC = "results/baseline/summary.csv"
OUT = "results/baseline/figs"
os.makedirs(OUT, exist_ok=True)
CORES = [2, 4, 8]
COLOR = {"gap": "tab:blue", "splash4": "tab:orange"}

d = collections.defaultdict(dict)  # d[(suite, bench)][cores] = row
for r in csv.DictReader(open(SRC)):
    d[(r["suite"], r["benchmark"])][int(r["cores"])] = r
apps = sorted(d)

def f(r, k):
    return float(r[k]) if r[k] != "" else float("nan")

# 1) speedup vs 2 cores (simulated time), one panel per suite
fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
for ax, suite in zip(axes, ["gap", "splash4"]):
    for s, b in apps:
        c = d[(s, b)]
        if s == suite and all(k in c for k in CORES):
            ax.plot(CORES, [f(c[2], "simSeconds") / f(c[k], "simSeconds") for k in CORES], marker="o", label=b)
    ax.plot(CORES, [k / 2 for k in CORES], "k--", label="ideal")
    ax.set_title(suite); ax.set_xticks(CORES); ax.set_xlabel("cores"); ax.legend(fontsize=7, ncol=2)
axes[0].set_ylabel("speedup vs 2 cores (simSeconds)")
plt.tight_layout(); plt.savefig(f"{OUT}/1_speedup.png", dpi=160); plt.close()

# 2) heatmaps: app x cores
def heat(key, scale, title, fname, cmap):
    m = np.array([[f(d[a][k], key) * scale if k in d[a] else np.nan for k in CORES] for a in apps])
    fig, ax = plt.subplots(figsize=(5.5, 9))
    im = ax.imshow(m, aspect="auto", cmap=cmap)
    ax.set_xticks(range(len(CORES))); ax.set_xticklabels(CORES); ax.set_xlabel("cores")
    ax.set_yticks(range(len(apps))); ax.set_yticklabels([f"{s}/{b}" for s, b in apps], fontsize=8)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            if not np.isnan(m[i, j]):
                ax.text(j, i, f"{m[i, j]:.1f}", ha="center", va="center", fontsize=7)
    ax.set_title(title); fig.colorbar(im, ax=ax)
    plt.tight_layout(); plt.savefig(f"{OUT}/{fname}", dpi=160); plt.close()

heat("L1D_miss_rate", 100, "L1D miss rate (%)", "2_l1d_miss_rate.png", "YlOrRd")
heat("L1D_imbalance", 1, "L1D access imbalance (max/min core)", "3_imbalance.png", "YlGnBu")

# 3) per-app bars at 4 cores: L1D MPKI and L2 miss rate
def bars(ax, key, scale, ylabel, cores=4):
    items = sorted(((f(d[a][cores], key) * scale, a) for a in apps if cores in d[a]), reverse=True)
    ax.bar([a[1] for _, a in items], [v for v, _ in items], color=[COLOR[a[0]] for _, a in items])
    ax.set_ylabel(ylabel); ax.tick_params(axis="x", rotation=75)

fig, axes = plt.subplots(1, 2, figsize=(15, 5))
bars(axes[0], "L1D_MPKI", 1, "L1D misses per 1000 instructions (4 cores)")
bars(axes[1], "L2_miss_rate", 100, "L2 miss rate % (4 cores)")
axes[0].legend(handles=[Patch(color=v, label=k) for k, v in COLOR.items()])
plt.tight_layout(); plt.savefig(f"{OUT}/4_mpki_l2.png", dpi=160); plt.close()
print("wrote", OUT)
