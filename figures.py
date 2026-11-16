# -*- coding: utf-8 -*-
"""Рис. 2 статьи v6: (а) известные верно vs неизвестность сохранена, 12 конфигураций с 95% ДИ;
(б) сохранение неизвестности по полям: GigaChat Pro+Max vs три внешние модели."""
import csv, json, re, sys, collections
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

EXP, OUT = sys.argv[1], sys.argv[2]
A = list(csv.DictReader(open(f"{EXP}/results/all/A_main.csv", encoding="utf-8-sig"), delimiter=";"))
E = list(csv.DictReader(open(f"{EXP}/results/all/errors.csv", encoding="utf-8-sig"), delimiter=";"))
corp = json.load(open(f"{EXP}/corpus.json", encoding="utf-8"))


def ci(s):
    v = [float(x) for x in re.findall(r"[\d.]+", s)]
    return v[0], v[1], v[2]


FAM = [("Lite", "GigaChat-2 Lite", "#9aa5b1"), ("Pro", "GigaChat-2 Pro", "#5b7fa6"), ("Max", "GigaChat-2 Max", "#1f4e79"),
       ("Claude", "Claude Sonnet 5.5", "#c26a2e"), ("GPT", "GPT-6 Sol", "#2e8b57"), ("DeepSeek", "DeepSeek V4 Pro", "#7b4ea3")]
plt.rcParams.update({"font.family": "Times New Roman", "font.size": 11})
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5.6), gridspec_kw={"width_ratios": [1.1, 1]})

for pre, name, col in FAM:
    for r in A:
        if not r["config"].startswith(pre):
            continue
        strict = r["config"].endswith("строгий")
        k, klo, khi = ci(r["известные верно"]); u, ulo, uhi = ci(r["неизвестность сохранена"])
        a1.errorbar(k, u, xerr=[[k - klo], [khi - k]], yerr=[[u - ulo], [uhi - u]], fmt="o" if strict else "s",
                    ms=8, color=col, mfc=col if strict else "white", mew=1.8, elinewidth=0.8, alpha=0.9, capsize=0,
                    label=name if strict else None)
a1.set_xlabel("Известные значения верно, %"); a1.set_ylabel("Неизвестность сохранена, %")
a1.set_xlim(64, 100); a1.set_ylim(0, 100)
h1 = a1.legend(frameon=False, loc="upper left", fontsize=9.5)
a1.add_artist(h1)
from matplotlib.lines import Line2D
a1.legend([Line2D([], [], marker="o", ls="", color="k"), Line2D([], [], marker="s", ls="", color="k", mfc="white")],
          ["строгий промпт", "базовый промпт"], frameon=False, loc="lower right", fontsize=9.5)
a1.set_title("(а) Перенос известного и сохранение неизвестного")

unk = collections.Counter(f for s in corp["stories"] for f in corp["fields"] if s["evidence"][f] == "u")
grp = [("GigaChat Pro+Max", ("Pro", "Max"), 4, "#1f4e79"), ("Claude Sonnet 5.5", ("Claude",), 2, "#c26a2e"),
       ("GPT-6 Sol", ("GPT",), 2, "#2e8b57"), ("DeepSeek V4 Pro", ("DeepSeek",), 2, "#7b4ea3")]
# знаменатель — фактически разобранные ответы (как в metrics.py)
raw = [json.loads(l) for fn in ("raw.jsonl", "raw_ext.jsonl") for l in open(f"{EXP}/results/{fn}", encoding="utf-8")]
sys.path.insert(0, EXP)
import metrics
nparsed = collections.Counter()
for r in raw:
    (p, _), _ = metrics.parse(r.get("text"), corp["fields"], corp["values"])
    if p is not None:
        nparsed[(r["config"], r["story"])] += 1
fields = sorted(unk, key=lambda f: -unk[f])
vals = {}
for g, pres, _, _ in grp:
    for f in fields:
        den = sum(nparsed[(c, s["id"])] for s in corp["stories"] if s["evidence"][f] == "u"
                  for c in {k for k, _ in nparsed if k.startswith(pres)})
        err = sum(1 for r in E if r["config"].startswith(pres) and r["type"] == "неизвестные" and r["field"] == f)
        vals[(g, f)] = 100 * (1 - err / den)
h = 0.2
for i, (g, _, _, col) in enumerate(grp):
    a2.barh([j + (i - 1.5) * h for j in range(len(fields))], [vals[(g, f)] for f in fields], h, color=col, label=g)
a2.set_yticks(range(len(fields)), [f"{f} (n={unk[f]})" for f in fields]); a2.invert_yaxis()
a2.set_xlim(0, 100); a2.set_xlabel("Неизвестность сохранена, %")
a2.legend(frameon=False, fontsize=9.5, loc="upper center", bbox_to_anchor=(0.45, -0.13), ncol=2)
a2.set_title("(б) По полям")
for a in (a1, a2):
    a.spines[["top", "right"]].set_visible(False)
fig.tight_layout(); fig.savefig(OUT, dpi=200)
print({k: round(v) for k, v in vals.items() if k[1] in ("place", "priority", "b_man")})
