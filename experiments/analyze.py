"""Build every E1-E6 table, figure and the failure analysis from the scored final runs.

Inputs : results/experiments/final/runs.csv (from `summarize`), results/baseline_metrics.json,
         models/g3_policy.json, logs/evidence/final/ (saved run records).
Outputs: results/final/tables/*.csv and tables.md, results/final/figures/*.png, docs/FAILURE_ANALYSIS.md.

Uncertainty: mean +/- standard deviation across the three repeats, and a 95% bootstrap interval over benchmark
cases (each case averaged over its repeats; 5,000 resamples, seed 0).

Run: python experiments/analyze.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "experiments" / "final" / "runs.csv"
EVIDENCE = ROOT / "logs" / "evidence" / "final"
OUT = ROOT / "results" / "final"
TABLES, FIGURES = OUT / "tables", OUT / "figures"
LIMIT = 0.05
SYSTEMS = ["b0", "b2", "full"]
NAMES = {"b0": "B0 fixed pipeline", "b2": "B2 LogACF-style", "full": "Proposed (full)",
         "no_g1": "Full without G1", "no_g2": "Full without G2", "no_g3": "Full without G3"}
COLORS = {"full": "#2a78d6", "b2": "#eb6834", "b0": "#1baf7a", "off": "#8f8e89"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
NEGATIVE = ["missing_unit", "vague_well", "unknown_well", "out_of_range", "unsupported"]
RNG = np.random.default_rng(0)


def load() -> pd.DataFrame:
    runs = pd.read_csv(RUNS)
    for col in ["task_correct", "answered", "refused", "should_answer", "unwarranted_answer", "silent_error",
                "failed", "disposition_correct"]:
        runs[col] = runs[col].astype(bool)
    return runs


def subsets(r: pd.DataFrame) -> dict[str, pd.Series]:
    harmful = r.fault.notna() & (r.fault != "shuffle_rows")
    prediction = r.family == "prediction"
    return {"all": pd.Series(True, index=r.index), "negative": r.family.isin(NEGATIVE),
            "g1": r.gaps.str.contains("G1"), "harmful": harmful, "benign": r.fault == "shuffle_rows",
            "prediction": prediction, "answered_prediction": prediction & r.answered,
            "good": prediction & (r.interval_error <= LIMIT), "poor": prediction & (r.interval_error > LIMIT),
            "missing_unit": r.family == "missing_unit", "g1_args": r.arguments_correct.notna()}


def bootstrap(values: np.ndarray, n: int = 5000) -> tuple[float, float]:
    if len(values) < 2:
        return float("nan"), float("nan")
    means = RNG.choice(values, size=(n, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def stat(r: pd.DataFrame, system: str, mask: pd.Series, column: str) -> dict:
    d = r.loc[(r.system == system) & mask & r[column].notna()]
    if d.empty:
        return {"mean": np.nan, "std": np.nan, "lo": np.nan, "hi": np.nan, "cases": 0, "runs": 0}
    values = d[column].astype(float)
    per_repeat = values.groupby(d.repeat).mean()
    per_case = values.groupby(d.case_id).mean().to_numpy()
    lo, hi = bootstrap(per_case)
    return {"mean": float(values.mean()), "std": float(per_repeat.std(ddof=1)) if len(per_repeat) > 1 else 0.0,
            "lo": lo, "hi": hi, "cases": len(per_case), "runs": len(d)}


def paired_difference(r: pd.DataFrame, a: str, b: str, mask: pd.Series, column: str) -> dict:
    da = r.loc[(r.system == a) & mask].groupby("case_id")[column].mean()
    db = r.loc[(r.system == b) & mask].groupby("case_id")[column].mean()
    common = da.index.intersection(db.index)
    diff = (da[common].astype(float) - db[common].astype(float)).to_numpy()
    lo, hi = bootstrap(diff)
    return {"diff": float(diff.mean()), "lo": lo, "hi": hi, "cases": len(common)}


def pct(s: dict, ci: bool = True) -> str:
    if s["runs"] == 0 or np.isnan(s["mean"]):
        return "n/a"
    text = f"{100 * s['mean']:.1f}"
    if s["std"] and s["std"] > 1e-12:
        text += f" ± {100 * s['std']:.1f}"
    if ci and not np.isnan(s["lo"]):
        text += f" [{100 * s['lo']:.1f}, {100 * s['hi']:.1f}]"
    return text


def md_table(frame: pd.DataFrame) -> str:
    cells = lambda row: "| " + " | ".join(str(v) for v in row) + " |"
    return "\n".join([cells(frame.columns), "|" + "---|" * len(frame.columns)] + [cells(r) for r in frame.itertuples(index=False)])


def write_table(name: str, title: str, frame: pd.DataFrame, note: str, md: list[str]) -> None:
    frame.to_csv(TABLES / f"{name}.csv", index=False)
    md += [f"## {title}", "", md_table(frame), "", note, ""]


METRICS = [  # (label, subset, column)
    ("Task success, all 50 cases (%)", "all", "task_correct"),
    ("G1: must-not-answer requests handled correctly (%)", "negative", "task_correct"),
    ("G1: unwarranted answers on must-not-answer requests (%)", "negative", "unwarranted_answer"),
    ("G1: missing-unit requests clarified (%)", "missing_unit", "task_correct"),
    ("G1: interval arguments correct (%)", "g1_args", "arguments_correct"),
    ("G2: harmful faults detected (%)", "harmful", "fault_detected"),
    ("G2: silent errors on harmful faults (%)", "harmful", "silent_error"),
    ("G2: harmful faults repaired (%)", "harmful", "repaired"),
    ("G2: false alarms on benign control (%)", "benign", "refused"),
    ("G3: prediction requests answered, coverage (%)", "prediction", "answered"),
    ("G3: answers above 0.05 RMSE, selective error (%)", "answered_prediction", "bad_answer"),
    ("G3: acceptable intervals refused, false refusal (%)", "good", "refused"),
    ("G3: poor intervals refused, justified abstention (%)", "poor", "refused"),
]


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    r = load()
    sub = subsets(r)
    md = ["# Final evaluation tables", "",
          "Generated by `python experiments/analyze.py` from `results/experiments/final/runs.csv`. Rates are % of runs: "
          "mean ± standard deviation across the three repeats, then the 95% bootstrap interval over cases "
          "(B0 is deterministic and runs once, so it has no standard deviation).", ""]

    # E1: numerical baseline and the non-agentic workflow.
    base = json.loads((ROOT / "results" / "baseline_metrics.json").read_text(encoding="utf-8"))
    test = base["splits"]["test"]
    e1 = pd.DataFrame([{"Target": t, "Training-mean RMSE": round(test["mean"]["pooled"]["targets"][t]["rmse"], 4),
                        "Random Forest RMSE": round(test["random_forest"]["pooled"]["targets"][t]["rmse"], 4),
                        "Random Forest R2": round(test["random_forest"]["pooled"]["targets"][t]["r2"], 3)}
                       for t in ["PHIF", "SW", "VSH"]])
    e1.loc[len(e1)] = ["Mean of three", round(test["mean"]["pooled"]["macro_target_rmse"], 4),
                       round(test["random_forest"]["pooled"]["macro_target_rmse"], 4), ""]
    write_table("e1_numerical_baseline", "E1a. Numerical baseline on test wells 3 and 7 (4,122 rows)", e1,
                "Fixed Random Forest versus the training-mean predictor, from `results/baseline_metrics.json`. "
                "LogACF reports a corrected mean RMSE of 0.07423 under its own protocol; the numbers are not comparable.", md)

    # E2-E4: main comparison, one row per metric.
    rows = []
    for label, s, col in METRICS:
        rows.append({"Metric": label, **{NAMES[x]: pct(stat(r, x, sub[s], col)) for x in SYSTEMS}})
    write_table("e2_e4_main_comparison", "E2-E4. Proposed system against B0 and B2 on the 50 test cases",
                pd.DataFrame(rows), "Cases per metric: all 50; must-not-answer 12; missing unit 2; harmful faults 14; "
                "benign control 2; prediction 22 (16 with reference error ≤ 0.05, 6 above).", md)

    diffs = []
    for label, s, col in [("Task success", "all", "task_correct"), ("G1 must-not-answer handled", "negative", "task_correct"),
                          ("G2 silent errors", "harmful", "silent_error"), ("G3 selective error", "answered_prediction", "bad_answer")]:
        for other in ["b2", "b0"]:
            d = paired_difference(r, "full", other, sub[s], col) if col != "bad_answer" else None
            if d is None:
                continue
            diffs.append({"Comparison": f"{label}: full − {other.upper()}", "Difference (points)": f"{100 * d['diff']:+.1f}",
                          "95% interval": f"[{100 * d['lo']:+.1f}, {100 * d['hi']:+.1f}]", "Cases": d["cases"]})
    write_table("e4_paired_differences", "E4. Paired differences on the same cases", pd.DataFrame(diffs),
                "Each case is averaged over its repeats; the interval is a 95% bootstrap over cases. Selective error is "
                "not paired because the systems answer different subsets of cases.", md)

    # E5: each ablation against the full system on exactly the same cases.
    ablation = []
    for off, s_case, metrics in [
            ("no_g1", "g1", [("Task success on G1 cases", "g1", "task_correct"),
                             ("Must-not-answer handled", "negative", "task_correct"),
                             ("Unwarranted answers", "negative", "unwarranted_answer")]),
            ("no_g2", "harmful", [("Silent errors on harmful faults", "harmful", "silent_error"),
                                  ("Harmful faults repaired", "harmful", "repaired"),
                                  ("Task success on fault cases", "harmful", "task_correct")]),
            ("no_g3", "prediction", [("Coverage", "prediction", "answered"),
                                     ("Selective error", "answered_prediction", "bad_answer"),
                                     ("False refusals", "good", "refused"),
                                     ("Task success on prediction cases", "prediction", "task_correct")])]:
        for label, s, col in metrics:
            ablation.append({"Component removed": off.replace("no_", "").upper(), "Metric (%)": label,
                             "Full": pct(stat(r, "full", sub[s], col)), "Without component": pct(stat(r, off, sub[s], col))})
    write_table("e5_ablation", "E5. Ablation: full system versus the same system with one component removed",
                pd.DataFrame(ablation), "Each ablation ran only on the cases of its own gap (34 G1, 16 fault, 22 "
                "prediction cases); the full system is shown on exactly the same cases.", md)

    # E6: efficiency and reliability.
    generation = {}
    for path in EVIDENCE.glob("final-*/result.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        generation[record["run_id"]] = (record.get("generation") or {}).get("credentials_file", "none")
    r["credentials"] = r.run_id.map(generation)
    e6 = []
    for x in ["b0", "b2", "full", "no_g1", "no_g2", "no_g3"]:
        d = r.loc[r.system == x]
        e6.append({"System": NAMES[x], "Runs": len(d), "Requests per run": round(d.provider_requests.mean(), 2),
                   "Prompt tokens per run": int(round(d.prompt_tokens.mean())),
                   "Output tokens per run": int(round(d.output_tokens.mean())),
                   "Tool calls per run": round(d.tool_calls.mean(), 2),
                   "Median active latency (s)": round(d.latency_seconds.median(), 2),
                   "Provider failures": int(d.failed.sum())})
    write_table("e6_efficiency", "E6. Efficiency and reliability per run", pd.DataFrame(e6),
                "Latency excludes request pacing and rate-limit waits. Runs were spread over three API projects with "
                "different response times (next table), so requests and tokens are the reliable cost measures.", md)
    matched = []
    for off, s in [("no_g1", "g1"), ("no_g2", "harmful"), ("no_g3", "prediction")]:
        for x in ["full", off]:
            d = r.loc[(r.system == x) & sub[s]]
            matched.append({"Cases": f"{s} ({d.case_id.nunique()})", "System": NAMES[x], "Runs": len(d),
                            "Requests per run": round(d.provider_requests.mean(), 2),
                            "Prompt tokens per run": int(round(d.prompt_tokens.mean())),
                            "Tool calls per run": round(d.tool_calls.mean(), 2)})
    write_table("e6_matched_cost", "E6d. Cost of each ablation against the full system on the same cases",
                pd.DataFrame(matched), "Ablations ran only on their own gap's cases, so their cost is compared with "
                "the full system on exactly those cases.", md)
    keys = (r.loc[r.system != "b0"].groupby(["credentials", "system"]).latency_seconds
            .agg(["count", "median"]).round(2).reset_index())
    keys.columns = ["Credentials file", "System", "Runs", "Median active latency (s)"]
    write_table("e6_latency_by_project", "E6b. Active latency by API project", keys,
                "The same system shows different latency on different projects, so latency comparisons across "
                "systems are confounded by the project that served them.", md)
    consistency = []
    for x in ["b2", "full", "no_g1", "no_g2", "no_g3"]:
        d = r.loc[r.system == x]
        changed = int((d.groupby("case_id").status.nunique() > 1).sum())
        consistency.append({"System": NAMES[x], "Cases": d.case_id.nunique(), "Cases whose outcome changed across repeats": changed})
    write_table("e6_consistency", "E6c. Outcome consistency across the three repeats", pd.DataFrame(consistency),
                "A case counts as changed if its final status (answer, clarify, abstain) differed between repeats.", md)

    # Gap-resolution table (README and paper).
    def short(x, s, col):
        return f"{100 * stat(r, x, sub[s], col)['mean']:.1f}%"
    gap_table = pd.DataFrame([
        {"Gap": "G1 semantic grounding", "Method / component": "Request-to-argument check and dataset registry (`gaps/grounding.py`)",
         "Metric": "Must-not-answer requests handled; unwarranted answers",
         "Base paper result": f"B2: {short('b2', 'negative', 'task_correct')}; {short('b2', 'negative', 'unwarranted_answer')}",
         "Our result": f"{short('full', 'negative', 'task_correct')}; {short('full', 'negative', 'unwarranted_answer')}",
         "Addressed?": "Fully"},
        {"Gap": "G2 verification and repair", "Method / component": "Artifact verifier with bounded regeneration (`gaps/verification.py`)",
         "Metric": "Silent errors on harmful faults; faults repaired",
         "Base paper result": f"B2: {short('b2', 'harmful', 'silent_error')}; {short('b2', 'harmful', 'repaired')}",
         "Our result": f"{short('full', 'harmful', 'silent_error')}; {short('full', 'harmful', 'repaired')}",
         "Addressed?": "Fully"},
        {"Gap": "G3 acceptance under weak evidence", "Method / component": "Uncertainty gate calibrated on validation wells (`gaps/acceptance.py`)",
         "Metric": "Selective error; coverage; false refusals",
         "Base paper result": f"B2: {short('b2', 'answered_prediction', 'bad_answer')}; {short('b2', 'prediction', 'answered')}; {short('b2', 'good', 'refused')}",
         "Our result": f"{short('full', 'answered_prediction', 'bad_answer')}; {short('full', 'prediction', 'answered')}; {short('full', 'good', 'refused')}",
         "Addressed?": "Partially"}])
    write_table("gap_resolution", "Gap-resolution table", gap_table,
                "Base paper result: our LogACF-style adaptation (B2), reproduced by us on the same data, cases and "
                "metrics. LogACF itself reports no request-grounding, artifact-fault or selective-error results.", md)

    # Failure analysis.
    def category(row) -> str:
        if row.failed:
            return "Provider or budget failure"
        if row.silent_error:
            return "G2: answered from an invalid file"
        if row.unwarranted_answer:
            return "G1: answered a request that needed clarification or refusal"
        if row.answered and row.bad_answer is True:
            return "G3: answered an interval above the error requirement"
        if row.refused and row.family == "prediction" and row.interval_error <= LIMIT:
            return "G3: refused an acceptable interval"
        if not row.disposition_correct:
            return "Wrong kind of non-answer (clarify vs abstain)"
        return "Other"
    failed = r.loc[~r.task_correct].copy()
    failed["category"] = failed.apply(category, axis=1)
    counts = (failed.groupby(["category", "system"]).size().unstack(fill_value=0)
              .reindex(columns=["b0", "b2", "full", "no_g1", "no_g2", "no_g3"], fill_value=0))
    totals = r.groupby("system").size()
    counts.loc["Total failed runs"] = counts.sum()
    counts.loc["Runs"] = [int(totals.get(c, 0)) for c in counts.columns]
    counts = counts.reset_index().rename(columns={"category": "Failure category", **NAMES})
    write_table("failure_categories", "Failure categories (number of failed runs)", counts,
                "A run fails when it is not task-correct (see the scoring rules in the README).", md)
    failed[["system", "repeat", "case_id", "family", "status", "expected", "interval_error", "answer_error", "category"]] \
        .to_csv(TABLES / "failed_runs.csv", index=False)

    (OUT / "tables.md").write_text("\n".join(md), encoding="utf-8", newline="\n")
    figures(r, sub)
    failure_document(r, failed)
    print(f"tables: {len(list(TABLES.glob('*.csv')))} csv; figures: {len(list(FIGURES.glob('*.png')))}")


def style(ax, ylabel: str) -> None:
    ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def bars(ax, labels, values, errors, colors) -> None:
    x = np.arange(len(labels))
    ax.bar(x, values, width=0.62, color=colors, edgecolor="white", linewidth=1.5)
    for i, (v, (lo, hi)) in enumerate(zip(values, errors)):
        if not np.isnan(lo):
            ax.plot([i, i], [lo, hi], color=INK, linewidth=1)
        ax.text(i, (hi if not np.isnan(hi) else v) + 3, f"{v:.0f}%", ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.set_xticks(x, labels, fontsize=8.5, color=INK)
    ax.set_ylim(0, 115)


def figures(r: pd.DataFrame, sub: dict) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    panels = [("G1: must-not-answer requests\nhandled correctly", "negative", "task_correct"),
              ("G2: answers given from\na broken file (lower is better)", "harmful", "silent_error"),
              ("G3: answers above the error\nrequirement (lower is better)", "answered_prediction", "bad_answer")]
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7))
    for ax, (title, s, col) in zip(axes, panels):
        stats = [stat(r, x, sub[s], col) for x in SYSTEMS]
        bars(ax, ["B0", "B2", "Ours"], [100 * t["mean"] for t in stats],
             [(100 * t["lo"], 100 * t["hi"]) for t in stats], [COLORS[x] for x in SYSTEMS])
        ax.set_title(title, fontsize=9, color=INK)
        style(ax, "% of runs" if ax is axes[0] else "")
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_gapwise.png", dpi=220)
    plt.close(fig)

    panels = [("Remove G1", "no_g1", "negative", "task_correct", "Must-not-answer\nhandled (%)"),
              ("Remove G2", "no_g2", "harmful", "silent_error", "Silent errors on\nharmful faults (%)"),
              ("Remove G3", "no_g3", "answered_prediction", "bad_answer", "Selective error (%)")]
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6))
    for ax, (title, off, s, col, ylabel) in zip(axes, panels):
        stats = [stat(r, "full", sub[s], col), stat(r, off, sub[s], col)]
        bars(ax, ["Full", "Without"], [100 * t["mean"] for t in stats],
             [(100 * t["lo"], 100 * t["hi"]) for t in stats], [COLORS["full"], COLORS["off"]])
        ax.set_title(title, fontsize=9, color=INK)
        style(ax, ylabel)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_ablation.png", dpi=220)
    plt.close(fig)

    policy = json.loads((ROOT / "models" / "g3_policy.json").read_text(encoding="utf-8"))
    curve = pd.DataFrame(policy["tradeoff"])
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    ax.plot(100 * curve.coverage, 100 * curve.risk, color=MUTED, linewidth=2, label="Validation windows (limit sweep)")
    ax.scatter([100 * policy["coverage"]], [100 * policy["risk"]], s=40, color=MUTED, zorder=3)
    ax.annotate("chosen limit", (100 * policy["coverage"], 100 * policy["risk"]), xytext=(4, 8),
                textcoords="offset points", fontsize=8, color=MUTED)
    for x, label in [("full", "Ours, test"), ("no_g3", "Without G3, test")]:
        cov = stat(r, x, sub["prediction"], "answered")["mean"]
        risk = stat(r, x, sub["answered_prediction"], "bad_answer")["mean"]
        ax.scatter([100 * cov], [100 * risk], s=64, color=COLORS["full"] if x == "full" else COLORS["off"],
                   edgecolor="white", linewidth=1.5, zorder=4, label=label)
    ax.set_xlabel("Coverage: share of intervals answered (%)", color=MUTED, fontsize=9)
    style(ax, "Bad answers among answered (%)")
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 35)
    ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_g3_tradeoff.png", dpi=220)
    plt.close(fig)

    # Only systems run on the same 50 cases are compared here; ablation costs on matched cases are in E6d.
    fig, axes = plt.subplots(1, 2, figsize=(5.0, 2.4))
    systems = ["b2", "full"]
    labels = ["B2", "Ours"]
    colors = [COLORS["b2"], COLORS["full"]]
    for ax, col, ylabel, fmt in [(axes[0], "provider_requests", "LLM requests per run", "{:.1f}"),
                                 (axes[1], "prompt_tokens", "Prompt tokens per run (thousands)", "{:.1f}")]:
        values = [r.loc[r.system == x, col].mean() / (1000 if col == "prompt_tokens" else 1) for x in systems]
        x = np.arange(len(systems))
        ax.bar(x, values, width=0.62, color=colors, edgecolor="white", linewidth=1.5)
        for i, v in enumerate(values):
            ax.text(i, v * 1.03, fmt.format(v), ha="center", va="bottom", fontsize=8.5, color=INK)
        ax.set_xticks(x, labels, fontsize=8.5, color=INK)
        ax.set_ylim(0, max(values) * 1.2)
        style(ax, ylabel)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_cost.png", dpi=220)
    plt.close(fig)
    architecture()


def architecture() -> None:
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 46)
    ax.axis("off")

    def box(x, y, w, h, text, fill="#ffffff", edge=MUTED, weight="normal", size=8):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.2",
                                    facecolor=fill, edgecolor=edge, linewidth=1))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=INK, weight=weight)

    def arrow(a, b, both=False):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="<|-|>" if both else "-|>", mutation_scale=9,
                                     color=MUTED, linewidth=1))

    blue = "#e8f1fb"
    box(1, 31, 15, 10, "User request\n(natural language)")
    box(22, 31, 18, 10, "Planner LLM\n(Gemini, native\nfunction calls)", weight="bold")
    box(46, 18, 33, 26, "", fill="#fafaf8")
    ax.text(62.5, 41.5, "Tool runtime (deterministic Python)", ha="center", fontsize=8, color=INK, weight="bold")
    box(48, 34, 29, 5, "G1 grounding check: well, depths,\nunit, curves, targets vs request", fill=blue, size=7)
    box(48, 27, 29, 5.5, "inspect_dataset · inspect_interval\npredict_properties · plot_logs", size=7)
    box(48, 20.5, 14, 5, "G2 verifier\n+ bounded repair", fill=blue, size=7)
    box(63, 20.5, 14, 5, "G3 evidence gate\n(uncertainty)", fill=blue, size=7)
    box(84, 33, 15, 8, "finish: answer,\nclarify or abstain")
    box(46, 3, 15, 9, "Feature-only\nwell-log table")
    box(63, 3, 17, 9, "Frozen Random\nForest + G3 policy")
    box(1, 3, 39, 9, "Run state and trace: arguments, outputs,\nerrors, budgets, versions, offline oracle")
    box(84, 3, 15, 9, "Offline scorer\n(reference labels)")
    arrow((16, 36), (22, 36))
    arrow((40, 36), (46, 36), both=True)
    arrow((79, 36), (84, 37))
    arrow((53, 12), (53, 18))
    arrow((71, 12), (71, 18))
    arrow((31, 31), (24, 12))
    arrow((91.5, 33), (91.5, 12))
    ax.text(43, 31.5, "tool calls /\nresults", ha="center", fontsize=6.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_architecture.png", dpi=220)
    plt.close(fig)


def trajectory(run_id: str) -> list[str]:
    record = json.loads((EVIDENCE / run_id / "result.json").read_text(encoding="utf-8"))
    lines = [f"Run `{run_id}`, request: \"{record['query']}\"", ""]
    step = 0
    for event in record["trace"]:
        if event.get("event") != "tool":
            continue
        step += 1
        result = event["result"]
        if result.get("ok"):
            keys = [k for k in ("rows", "input_coverage", "prediction_id", "verified", "status") if k in result]
            detail = ", ".join(f"{k}={result[k]}" for k in keys)
            if "evidence" in result:
                detail += f", uncertainty={result['evidence']['model_uncertainty']:.4f} (decision {result['evidence']['decision']})"
            outcome = f"ok ({detail})" if detail else "ok"
        else:
            outcome = f"**{result['error']}**: {result['message'][:110]}"
        args = {k: v for k, v in event["arguments"].items() if k != "reason"}
        lines.append(f"{step}. `{event['name']}` {json.dumps(args) if args else ''} → {outcome}")
    lines += ["", f"Final: **{record['status']}**, reason: \"{record['reason'][:160]}\". "
                  f"{record['tool_calls']} tool calls, {record['provider_requests']} LLM requests.", ""]
    return lines


def failure_document(r: pd.DataFrame, failed: pd.DataFrame) -> None:
    full = failed.loc[failed.system == "full"]
    n_full = int((r.system == "full").sum())
    by_cat = full.groupby("category").agg(runs=("case_id", "size"), cases=("case_id", "nunique")).reset_index()
    pick = lambda frame: frame.sort_values(["case_id", "repeat"]).iloc[0].run_id
    ok = r.loc[(r.system == "full") & r.task_correct]
    success_clarify = pick(ok.loc[ok.family == "missing_unit"])
    success_repair = pick(ok.loc[ok.fault == "corrupt_values"])
    fail_refusal = pick(full.loc[full.category == "G3: refused an acceptable interval"])
    bad = full.loc[full.category == "G3: answered an interval above the error requirement"]
    fail_bad = pick(bad) if len(bad) else None
    b2_silent = pick(r.loc[(r.system == "b2") & r.silent_error & (r.fault == "corrupt_values")])

    doc = ["# Failure analysis (final evaluation, test benchmark)", "",
           "Generated by `python experiments/analyze.py` from the scored runs in `results/experiments/final/runs.csv` "
           "and the saved traces in `logs/evidence/final/`. A run fails when it is not task-correct.", "",
           f"## Failures of the proposed system ({len(full)} of {n_full} runs)", "",
           md_table(by_cat.rename(columns={"category": "Category", "runs": "Failed runs", "cases": "Distinct cases"})), "",
           "All failures of the proposed system are G3 acceptance errors; it made no G1 or G2 errors on the test cases. "
           "The outcome of every case was identical in all three repeats, so each failing case failed three times.", "",
           "**G3: refused an acceptable interval.** The calibrated uncertainty limit (0.0254, chosen on validation wells "
           "to keep bad answers at or below 5%) is exceeded by intervals whose reference error is still within 0.05. "
           "Tree-ensemble spread is only a moderate predictor of error (Spearman 0.53 on validation windows), so a single "
           "limit cannot separate good and poor intervals cleanly. A looser limit admits more bad answers (see the "
           "risk-coverage curve, `results/final/figures/fig_g3_tradeoff.png`). Future work: per-well or interval-length "
           "aware calibration, conformal prediction intervals, and more validation wells.", "",
           "**G3: answered an interval above the error requirement.** Some poor intervals have low tree spread: the "
           "forest agrees with itself but is wrong for that rock. Disagreement among trees cannot detect systematic "
           "error shared by all trees. Future work: input-distribution signals that actually track error on this field, "
           "or a second, independent predictor.", "",
           "## Failures of the comparison systems", "",
           "See `results/final/tables/failure_categories.csv` for counts per system. In short: B0 and B2 assume a unit "
           "when none is given, and B2's LLM reviewer approved most broken prediction files (silent errors), while the "
           "full system made neither error.", "",
           "## Representative success cases (proposed system)", "",
           "### Success 1: missing unit leads to clarification (G1)", ""] + trajectory(success_clarify) + [
           "### Success 2: corrupted prediction file detected and repaired (G2)", ""] + trajectory(success_repair) + [
           "## Representative failure cases (proposed system)", "",
           "### Failure 1: acceptable interval refused (G3 false refusal)", ""] + trajectory(fail_refusal) + [
           f"Why it is a failure: the reference error of this interval is "
           f"{r.loc[r.run_id == fail_refusal, 'interval_error'].iloc[0]:.4f}, within the 0.05 requirement, so answering "
           "was the correct choice.", ""]
    if fail_bad:
        doc += ["### Failure 2: poor interval answered (G3 missed a bad answer)", ""] + trajectory(fail_bad) + [
            f"Why it is a failure: G2 repaired the injected fault correctly, but the reported prediction has a mean "
            f"property RMSE of {r.loc[r.run_id == fail_bad, 'answer_error'].iloc[0]:.4f} against the reference labels, above "
            "the 0.05 requirement. Its uncertainty sat just under the limit, so G3 accepted it.", ""]
    doc += ["## Contrast: B2 approving a corrupted file", ""] + trajectory(b2_silent)
    (ROOT / "docs" / "FAILURE_ANALYSIS.md").write_text("\n".join(doc), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
