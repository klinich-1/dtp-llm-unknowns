# Do Large Language Models Preserve the Unknown? Extracting Road-Accident Facts from Driver Accounts

Data and code accompanying the paper *“Do Large Language Models Preserve the Unknown? Extracting Road-Accident Circumstances from Driver Accounts with GigaChat, Claude, GPT and DeepSeek”* by K. V. Bagin, A. Yu. Fedorovich, T. V. Novikov, D. E. Anisimov, D. Yu. Fedorovich and A. A. Belenko (Institute of Radioelectronics and Information Technologies, Ural Federal University, Yekaterinburg, Russia).

The study measures, separately, how well LLMs (1) transfer facts a driver states explicitly, (2) infer facts that follow from the account, and (3) answer `unknown` when the account contains no information, instead of filling the field with a plausible guess. The accounts are in Russian.

## Contents

| File | Description |
|---|---|
| `corpus.json` | 36 synthetic driver accounts × 11 fields: a gold standard of 396 values, each labelled `e` (explicit), `i` (inferred) or `u` (unknown). Version v1, SHA-256 `0fb35925b897bf3c9c551ff89a3330eb27a117f4e2d04613ed0d5a8adcd0ab41` |
| `build_corpus.py` | source of the corpus and gold standard; generates `corpus.json` |
| `prompt.txt`, `prompt_base.txt` | strict prompt (with an explicit “do not guess” rule) and base prompt (the same text without that paragraph) |
| `configs.json` | 12 configurations: 6 models × 2 prompts |
| `run_gigachat.py` | queries the models and appends responses to a JSONL file |
| `metrics.py` | computes all metrics and bootstrap confidence intervals |
| `figures.py` | Figure 2 of the paper |
| `annotation.py`, `annotation/` | tool for independent double annotation of the gold standard and Cohen's kappa |
| `results/raw.jsonl` | 1,080 responses of GigaChat-2 Lite, Pro and Max (6 Nov 2026) |
| `results/raw_ext.jsonl` | 1,080 responses of Claude Sonnet 5.5, GPT-6 Sol and DeepSeek V4 Pro (11–12 Nov 2026) |
| `results/all/` | final tables (`report.md`, CSV), per-error file (`errors.csv`) and the figure |

Each record in `raw*.jsonl` holds the configuration, account id, repeat index, full response text, finish reason, model identifier returned by the API, token usage and latency.

## Models

| Model | Access | Parameters |
|---|---|---|
| GigaChat-2, GigaChat-2-Pro, GigaChat-2-Max (version 2.0.28.2) | GigaChat REST API | temperature 0.1 |
| claude-sonnet-5-5 | commercial API aggregator, Anthropic Messages protocol | default temperature, effort `low` |
| gpt-6-sol | commercial API aggregator, OpenAI Chat Completions protocol | temperature 0.1, reasoning_effort `low` |
| deepseek-v4-pro-0813 | commercial API aggregator, OpenAI Chat Completions protocol | temperature 0.1 |

Every account was queried five times independently: 2,160 responses in total.

## Reproducing the metrics

Requires Python 3.10+ and `matplotlib`. No API access is needed: everything is computed from the stored responses.

```bash
cat results/raw.jsonl results/raw_ext.jsonl > results/raw_all.jsonl
python metrics.py --raw results/raw_all.jsonl --tag all
python figures.py . results/all/fig_main.png
```

Tables are written to `results/all/report.md`. Table and column labels in the generated report are in Russian; the glossary below maps them to the metrics in the paper.

## Re-running the models

API keys are not included. For GigaChat, put the authorization key in `gigachat_key.txt` (line 1: key, line 2: scope) and the Russian Trusted Root CA certificate `russian_trusted_root_ca.pem` next to the script. For the other models, put the key (line 1) and the base URL of an OpenAI-compatible API (line 2, e.g. `https://.../v1`) in `star_key.txt`.

```bash
python run_gigachat.py --only "Lite,Pro,Max" --out results/raw.jsonl
python run_gigachat.py --only "Claude,GPT-6 Sol,DeepSeek" --workers 4 --out results/raw_ext.jsonl
```

An interrupted run resumes where it stopped. To test the pipeline without any API, use `python run_gigachat.py --mock`.

## Metrics

| Metric (report label) | Meaning |
|---|---|
| Object obtained (`объект получен`) | the response parses as a JSON object |
| Full format (`полный формат`) | all 11 fields are present with valid values |
| Accuracy (`точность (все)`) | share of values matching the gold standard, over obtained responses |
| Known correct (`известные верно`) | accuracy on explicit and inferred values |
| Unknown preserved (`неизвестность сохранена`) | the model answered `unknown` where the account gives no information |
| Fabricated (`додумано`) | complement of the above: the field was filled with a guess |
| False unknown (`ложное unknown`) | the model answered `unknown` although the value is known |
| Exact set (`точный набор`) | all 11 fields correct in one response |
| Stability (`устойчивость`) | the same answer in all five repeats |

95% confidence intervals use a cluster bootstrap over accounts (2,000 resamples); differences between configurations use a paired bootstrap on the same accounts.

## Limitations

The corpus is synthetic. The gold standard was checked by a single expert. The non-GigaChat models were accessed through a commercial aggregator rather than the developers' own APIs. See the Limitations section of the paper for details.

## Citation

If you use these data, please cite the paper (citation details will be added after publication).
