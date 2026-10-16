# Literature evidence and reading queue

These are factual research notes, not the required critical summaries or assessed comparison table. Full references are in [BIBLIOGRAPHY.md](BIBLIOGRAPHY.md); the 13 raw Crossref records were rechecked on 16 October 2026. **No ten-paper student critical review is claimed complete.**

## Recommended ten core readings

Use **P01/P02/P03/P04/P05/P06/P07/P08/P09/P13** as the initial ten-paper reading queue. P01/P02 directly address well-log agents; P05 is another subsurface tool workflow. The others support particular reasoning, schema, review or evaluation components. Geotechnical/GIS/NER relevance must be argued explicitly. P10–P12 are alternatives/comparators; they are not equally direct reservoir-agent studies.

If a chosen paper cannot support critical analysis after full-text reading, replace it with a sufficiently relevant alternative. Do not count a verified title as a completed reading, or pad the count with loosely related references. The older 2024 SPWLA background citation is additional and does not count toward ten.

## Evidence notes

| ID | Task / data / mechanism | Reported evidence and location | What to check before writing |
|---|---|---|---|
| **P01 BASE** | LogACF; SPWLA and tight-sandstone case; role/memory/planning/execution with scientific scripts | Section 3.3.1 reports intermediate corrected average RMSE **0.07423**. It is not a verified final best score. | Read final result figures/supplement, split definitions and validation procedure. Avoid comparing our different split directly. [Article](https://doi.org/10.1016/j.petsci.2026.05.031) |
| P02 | Well-log agents, human review, formulas/ML/MCP; 100 field wells | Table 3 includes XGBoost porosity MAE **1.34 ± 0.04**; earlier audit identifies percentage units. | Read the table header/units and formula comparator before quoting. Component ML accuracy does not isolate an agent benefit. [Journal](https://ped.cpedm.com/CN/10.1016/S1876-3804%2826%2960734-3) |
| P03 | OpenMindat workflow; QLoRA Llama 3.1 8B, 63 human cases, 2,009 training examples, 152 evaluation cases | Table 5, six-example setting: weighted wFP **41.45% → 9.21%**, wFN **0.66% → 5.92%** from untuned to tuned model. | These are the paper's weighted outcome percentages, not conditional false-positive/false-negative rates. Check definitions and the termination tradeoff. Training used A100 40 GB. [Article](https://doi.org/10.1016/j.acags.2025.100311) |
| P04 | AGeoKE; USGS Mineral Deposit Models/NASA Lunar Sample Compendium; schema-adaptive extraction and multi-version QC | Expert validation described; exact numerical QC effect **not retrieved**. | Obtain result tables; distinguish schema extraction from numerical tool correctness. Do not invent accuracy. [Article](https://doi.org/10.1016/j.acags.2026.100362) |
| P05 | GAGAW; petrophysical conversion, time-lapse inversion and data fusion | Three demonstrated workflows; an aggregate success/error statistic was **not extracted**. | Read numerical example results, data sources, tool validation and failure discussion; demonstration count is not reliability. [Article](https://doi.org/10.1016/j.bdes.2026.100042) |
| P06 | multi-GeoLLM; engineering calculation/review; 60 multimodal and 100 text cases | Publisher preview reports text precision **0.999**, recall **1.0**. | Obtain metric/task definitions and full critique; footing design differs from well logs. First-author name was corrected. [Article](https://doi.org/10.1016/j.autcon.2025.106257) |
| P07 | Geotechnical site planning/geological characterization; multihop retrieval and human collaboration | Publisher preview reports **88% retrieval accuracy**, **50% efficiency enhancement**. | Check denominators, timing comparison, evaluation set and public artifacts. These are not reservoir-property errors. [Article](https://doi.org/10.1016/j.autcon.2025.106103) |
| P08 | Geological description standardization; stratified RAG; 100 boreholes, 21 projects, 908 samples | Classification/uncertainty studied; exact previously claimed **84%/82%** values were not re-established. | Inspect classification/uncertainty tables and regional transfer limits. Keep those old percentages out of the submission until checked. [Article](https://doi.org/10.1016/j.geoai.2025.100047) |
| P09 | Geological rock/mineral NER; domain prompts plus feedback; four regional reports | Publisher highlights report **17%/11%** improvements. | Resolve relative-percent versus percentage-point interpretation and metric names before quoting; extraction is component-related. [Article](https://doi.org/10.1016/j.cageo.2025.105944) |
| P13 | GeoAgentic-RAG; Nanjing/Guangzhou geospatial tasks, planning/tools/reflection | Table 2: Nanjing PR **85.3%**, AC **88.3%**, HS **75.3%**. Table 3: without reflection HS **61.2%**, a **14.1-point** difference. | Read PR/AC/HS definitions. Urban GIS results motivate an experiment; they do not demonstrate our well-log mechanism. [Article](https://doi.org/10.1016/j.jag.2026.105195) |
| P10 alternative | GeoGPT/LightRAG geological QA; geology-specific prompting | Table 1 entity F1 **0.7680 → 0.8353** | Model/prompt/retrieval effects may be mixed; not a numerical agent workflow. [Article](https://doi.org/10.3390/geosciences15100382) |
| P11 alternative | GeoFactory; factual/inferential geoscience tasks, 14 enhancement algorithms | Paper reports **21.07%/7.37%** score gains and **0.28%** average advantage over GPT-4 | Verify score conventions and cost; heavier training differs from our small fixed-tool system. [Article](https://doi.org/10.1080/20964471.2025.2506291) |
| P12 alternative | Dutch borehole lithology classification; GEOBERTje domain adaptation | Table 4 base-setting accuracy **0.944/0.838/0.775** for primary/secondary/tertiary lithology | Regional/language limits; not itself an agent. A100 training is outside this baseline. [Article](https://doi.org/10.1016/j.acags.2025.100229) |

Paper values are author-reported observations from the research audit, with P01/P03/P13 key passages rechecked during Stage 7. They are not locally reproduced paper results. Do not average or rank these unlike metrics together. P03's earlier summarized decision accuracy can differ slightly from sums of rounded table cells; use the original table and metric definition.

## Peer review and access ledger

| Paper(s) | Evidence level | Remaining access limitation |
|---|---|---|
| P01 | Publisher identifies original paper and peer-review responsibility; online 25 May 2026 | Indexed sections accessed; full supplement not retrieved/run. |
| P02 | Journal article and [PolyU peer-reviewed record](https://research.polyu.edu.hk/en/publications/a-multi-agent-collaborative-framework-with-human-in-the-loop-for-/) | Journal text is indexed, but direct page sometimes shows unresolved templates; field release not established. |
| P03 / P04 | Idaho explicitly labels [P03](https://verso.uidaho.edu/esploro/outputs/journalArticle/Fine-tuning-small-and-open-LLMs-to/996867365701851) / [P04](https://verso.uidaho.edu/esploro/outputs/journalArticle/An-LLM-based-multi-agent-system-for-geoscience/996973292301851) peer reviewed | P04 quantitative tables remain missing. |
| P05 | Published research; [journal author guide](https://www.keaipublishing.com/en/journals/big-data-and-earth-system/guide-for-authors/) describes external peer review | Direct publisher fetch returned 403; indexed abstract/method and author demo available. |
| P06 / P07 / P08 / P09 / P13 | Publisher journal research records, not preprint-only records | Several direct fetches returned 403; previews/indexed sections are not complete manuscripts. |
| P10 / P11 | Published research with article histories; accessible full text during initial audit | Still requires student reading and critique. |
| P12 | Published journal research; [institution-hosted manuscript](https://pub.vito.be/openaccess/1-s2.0-S2590197425000114-main.pdf) | Full reproduction was not attempted. |

Crossref's `journal-article` type alone does not certify peer review. Publisher/institutional evidence is separate. If full text is unavailable here, use university access or an author/institution-hosted copy; do not silently fill missing evidence.

## Artifact/reproduction ledger

| ID | Located artifact | Status |
|---|---|---|
| P01 | [Pinned LogACF source](https://github.com/DangDang-LG/LogACF/tree/78e2fd011cb8401a959fc060a2f968078638d992) | Inspected, not executed/copied; no license/dependency manifest observed in inspected tree. |
| P03 | [Llama Mindat workflow](https://github.com/ChuBL/Llama_MindatWorkflow) | Code/data link established; exact retraining not attempted. |
| P04 | [Adaptive Geo Knowledge Extraction](https://github.com/ChuBL/Adaptive_Geo_Knowledge_Extraction) | Author release linked; dependencies/data/reproduction completeness not established. |
| P05 | [GAGAW demo](https://github.com/geohang/GAGAW_Hydrogeophysics) | Demo located; publication status follows publisher, not older repository citation text. |
| P09 | [LLM-RocMin-NER](https://github.com/fairy1234567/LLM-RocMin-NER) | Source located; data/instructions not fully verified. |
| P02 / P06 / P07 / P08 | No complete runnable public package verified | Do not claim none exists; mark artifact access pending. |
| P10 / P11 / P12 / P13 | Paper/manuscript artifact references vary | Inspect exact linked data/model/code before describing as reproducible. |

## Per-paper note form for the students

For each selected paper, record: reader; full-text location; research-article/peer-review evidence; exact section/table/figure for each number; task and data/split; method; strongest baseline; author-stated limitation; your own critique; specific connection to one project gap; artifact/license/access; unresolved questions. Then write the 150–250-word critique yourselves.

Citation corrections: P06's first author is **Hao-Ruo Xu**, per [corrigendum](https://doi.org/10.1016/j.autcon.2025.106421); Crossref still records Hao-Rao. The raw metadata is preserved and the corrected name is used in BibTeX with a note. P01 has no volume/pages in the checked DOI metadata; no values were invented. P08 uses the 2026 issue year, while its DOI contains 2025; both dates fall within the allowed window.
