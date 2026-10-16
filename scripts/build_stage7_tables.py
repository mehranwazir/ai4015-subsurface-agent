"""Regenerate factual bibliography/results tables from checked source artifacts; no API calls."""
from __future__ import annotations

import html
import json
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "stage7"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, text: str):
    path.write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n", encoding="utf-8", newline="\n")


def bib_escape(value: str) -> str:
    return html.unescape(value).replace("&", r"\&").replace("%", r"\%")


def bibliography():
    records = read(PACK / "source_metadata.json")["records"]
    assert len(records) == 13 and all("metadata" in r for r in records)
    cards = ["# Checked bibliography: research records, not final IEEE formatting", "",
             "Generated from publisher-deposited Crossref metadata checked on 16 October 2026. "
             "See source_metadata.json for dates and raw records. Select at least ten after reading. "
             "Full author lists are retained; choose IEEE style in your reference manager and check its output. "
             "Crossref metadata alone does not establish peer review or ranking.", ""]
    entries = []
    for record in records:
        ident, m = record["id"], record["metadata"]
        authors = []
        for item in m["author"]:
            given, family = item.get("given", ""), item["family"]
            if family.isupper():
                family = family.title()
            if ident == "P06" and family == "Xu":
                given = "Hao-Ruo"  # Published corrigendum overrides stale registration spelling.
            authors.append((given, family))
        title = html.unescape(m["title"][0])
        journal = html.unescape(m["container-title"][0])
        year = m["published"]["date-parts"][0][0]
        assert year in (2025, 2026)
        doi = m["DOI"]
        line = f"{'; '.join(f'{g} {f}' for g, f in authors)}. **{title}.** *{journal}*, {year}."
        location = [f"vol. {m['volume']}" for _ in [0] if m.get("volume")]
        if m.get("issue"):
            location.append(f"no. {m['issue']}")
        if m.get("article-number"):
            location.append(f"article {m['article-number']}")
        elif m.get("page"):
            location.append(f"page/article identifier {m['page']}")
        cards.extend([f"## {ident}" + (" — BASE" if ident == "P01" else ""), "", line, "",
                      (", ".join(location) + ". ") if location else "Volume/pages absent from checked metadata. ",
                      f"[DOI](<https://doi.org/{doi}>). Metadata publisher: {m['publisher']}. "
                      f"[Crossref record](<{record['metadata_url']}>).", ""])
        fields = {"author": " and ".join(f"{f}, {g}" for g, f in authors), "title": title,
                  "journal": journal, "year": str(year), "doi": doi, "url": "https://doi.org/" + doi}
        for source, target in [("volume", "volume"), ("issue", "number"), ("page", "pages")]:
            if m.get(source):
                fields[target] = str(m[source]).replace("-", "--") if source == "page" else str(m[source])
        if ident == "P06":
            fields["note"] = "First author corrected to Hao-Ruo Xu; corrigendum DOI 10.1016/j.autcon.2025.106421"
            cards.extend(["Name correction applied from the published corrigendum; the raw Crossref spelling is preserved in the source JSON.", ""])
        entries.append("@article{" + ident + ",\n" + "\n".join(
            f"  {key} = {{{bib_escape(value)}}}," for key, value in fields.items()) + "\n}")
    cards.extend(["## Reference-manager checks", "",
                  "Use the required IEEE numbered style, order references by first citation, preserve author corrections, "
                  "and distinguish article numbers from page ranges. Do not invent P01 volume/pages. "
                  "P08 uses the 2026 issue year. The data-background paper from 2024 is additional and is not counted here."])
    write(PACK / "BIBLIOGRAPHY.md", "\n".join(cards))
    write(PACK / "references.bib", "% Checked metadata; final IEEE rendering requires reference-manager review.\n\n" + "\n\n".join(entries))


def executed_results():
    metrics = read(ROOT / "results/baseline_metrics.json")
    data = read(ROOT / "results/data_manifest.json")
    evaluation = read(ROOT / "results/agent_evaluation.json")
    run = read(ROOT / "results/evidence/gemini-e2e-002/result.json")
    replay = read(ROOT / "results/evidence/replay.json")
    counts = read(ROOT / "results/evidence/request_accounting.json")
    requests_by_run = {r["run_id"]: r["requests_this_run"] for r in counts["runs"]}
    suite = ET.parse(ROOT / "results/tests.xml").find(".//testsuite")
    assert suite is not None and suite.attrib["errors"] == suite.attrib["failures"] == "0"
    rf, mean = metrics["splits"]["test"]["random_forest"], metrics["splits"]["test"]["mean"]
    lines = ["# Executed results: factual evidence tables", "",
             "Generated by `python scripts/build_stage7_tables.py` from the tracked JSON/XML artifacts. "
             "This command reads evidence and formats tables; it does not train, evaluate a model, or call an API. "
             "Values below are existing actual executions, not newly run experiments or assessed prose.", "",
             "## Data and numerical setup", "",
             f"Source commit: `{data['source_commit']}`. Eligible cohort: **{data['cohort_rows']:,} rows**. "
             f"Excluded out-of-range complete target rows: **{data['complete_target_rows_outside_0_1']}**. "
             "Source labels are interpreted reference estimates.", "",
             "| Split | Wells | Rows |", "|---|---|---:|"]
    for split, info in data["splits"].items():
        lines.append(f"| {split} | {', '.join(map(str,info['wells']))} | {info['rows']:,} |")
    lines.extend(["", "Fixed RF: 80 trees, depth 10, minimum leaf 3, seed 42, one CPU worker; training-only median "
                  "imputation plus missingness indicators. No search/test-guided selection. "
                  f"Recorded fit time: **{metrics['model']['fit_seconds']:.3f} s**. "
                  f"Python **{metrics['python']}**. No GPU training.", "",
                  "## Held-out property prediction", "",
                  "| Target | Mean RMSE | RF RMSE | RF MAE | RF R² |", "|---|---:|---:|---:|---:|"])
    for target, values in rf["pooled"]["targets"].items():
        baseline = mean["pooled"]["targets"][target]
        lines.append(f"| {target} | {baseline['rmse']:.6f} | {values['rmse']:.6f} | {values['mae']:.6f} | {values['r2']:.6f} |")
    lines.extend([f"| Mean of three property RMSEs | **{mean['pooled']['macro_target_rmse']:.6f}** | **{rf['pooled']['macro_target_rmse']:.6f}** | — | — |", "",
                  f"Pooled test rows: **{rf['pooled']['rows']:,}**. RF equal-well mean RMSE: **{rf['macro_well_rmse']:.6f}**. "
                  "This differs from averaging target RMSE after pooling all rows.", "",
                  "| Well | Rows | Mean property RMSE | SW RMSE | SW R² |", "|---|---:|---:|---:|---:|"])
    for well, values in rf["per_well"].items():
        sw = values["targets"]["SW"]
        lines.append(f"| {well} | {values['rows']:,} | {values['macro_target_rmse']:.6f} | {sw['rmse']:.6f} | {sw['r2']:.6f} |")
    lines.extend(["", "Retain the weaker well 7 SW performance. Only one field/two held-out IDs are scored. "
                  "These numbers are neither an official competition score nor a fair direct comparison to LogACF. "
                  "The agent uses this same frozen predictor; no agent-driven RMSE improvement is demonstrated.", "",
                  "[Full metrics](../../results/baseline_metrics.json), [data manifest](../../results/data_manifest.json), "
                  "[well 3 plot](../../results/figures/test_well_3.png), [well 7 plot](../../results/figures/test_well_7.png).", "",
                  "## Real developer cases", "",
                  "| Case | Status | Checks passed | Tool calls | HTTP attempts | Latency s |",
                  "|---|---|---|---:|---:|---:|"])
    for case in evaluation["cases"]:
        lines.append(f"| {case['case_id']} | {case['status']} | {case['passed']} | {case['tool_calls']} | "
                     f"{requests_by_run[case['run_id']]} | {case['latency_seconds']:.3f} |")
    latencies = [c["latency_seconds"] for c in evaluation["cases"]]
    lines.extend(["", f"**{evaluation['passed']}/{evaluation['executed_case_count']}** selected cases passed once each. "
                  "Ten additional defined cases were not run live. "
                  f"Mean/median recorded loop latency: **{statistics.mean(latencies):.3f}/{statistics.median(latencies):.3f} s**. "
                  "HTTP attempts use corrected per-run deltas, including retries; original cumulative fields remain preserved.", "",
                  "These manually authored convenience cases include hints and deliberate fault injection. "
                  "They are development evidence, not a held-out reliability estimate or gap-ablation result. "
                  "No invoice was queried; API cost is unknown. "
                  "[Evaluation summary](../../results/agent_evaluation.json), "
                  "[request accounting](../../results/evidence/request_accounting.json).", "",
                  "## Complete real workflow, replay and software tests", "",
                  f"Real run `{run['run_id']}`: **{run['tool_calls']} tool calls**, **{run['tool_errors']} tool errors**, "
                  f"**{run['latency_seconds']:.3f} s**, model `{run['model_version']}`. "
                  "It inspected the requested interval, predicted 1,220 rows, verified and plotted the artifact. "
                  "[Run](../../results/evidence/gemini-e2e-002/result.json), "
                  "[plot](../../results/evidence/gemini-e2e-002/pred-d1b99cbd57e60bde.png).", "",
                  f"Replay: **{len(replay['checks'])} structured outputs checked**, all match = `{replay['all_match']}`, "
                  f"LLM called = `{replay['llm_called']}`. [Replay record](../../results/evidence/replay.json).", "",
                  f"Offline software verification: **{suite.attrib['tests']} tests**, "
                  f"**{suite.attrib['failures']} failures**, **{suite.attrib['errors']} errors**. "
                  "[Final XML](../../results/tests.xml). Test doubles are not live model evidence. "
                  "The earlier sandbox-temp setup failure and initial provider 404 remain in the evidence folder.", "",
                  "Verification demonstrates artifact/execution consistency, not geological truth or calibrated uncertainty. "
                  "Action replay is not a fresh stochastic agent run. "
                  "Broader fault tests, controlled ablations, repeated runs and independent-field validation remain planned."])
    write(PACK / "05_EXECUTED_RESULTS.md", "\n".join(lines))


if __name__ == "__main__":
    bibliography()
    executed_results()
    print("Regenerated bibliography, BibTeX and actual-results tables from local evidence.")
