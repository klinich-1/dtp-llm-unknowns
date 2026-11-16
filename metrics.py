# -*- coding: utf-8 -*-
"""Метрики по results/raw.jsonl -> results/report.md, таблицы CSV и графики PNG.

  python metrics.py                       # реальные ответы
  python metrics.py --raw results/mock_raw.jsonl --tag mock

Все доли считаются по значениям полей. Доверительные интервалы — кластерный
бутстрэп по историям (значения внутри одной истории зависимы).
"""
import argparse, csv, json, pathlib, random, re, statistics
from collections import defaultdict

HERE = pathlib.Path(__file__).parent
EV_NAME = {"e": "явные", "i": "выводимые", "u": "неизвестные"}


def parse(text, fields, values):
    """-> (pred dict | None, format_ok)."""
    if not text:
        return (None, None), False
    t = re.sub(r"```(?:json)?", "", text)
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return (None, None), False
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return (None, None), False
    if not isinstance(obj, dict):
        return (None, None), False
    pred, ok = {}, True
    for f in fields:
        kind = f.split("_", 1)[-1] if f.startswith(("a_", "b_")) else f
        v = obj.get(f)
        if isinstance(v, dict):
            v = v.get("value")
        v = str(v).strip() if v is not None else "missing"
        if v not in values[kind]:
            ok = False
            v = v if v == "missing" else "invalid"
        pred[f] = v
    quotes = {f: (obj[f].get("quote") if isinstance(obj.get(f), dict) else None) for f in fields}
    return (pred, quotes), ok


def load(raw_path, corpus):
    F, V = corpus["fields"], corpus["values"]
    recs = []
    for line in pathlib.Path(raw_path).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        (pred, quotes), ok = parse(r.get("text"), F, V)
        r["pred"], r["quotes"], r["format_ok"] = pred, quotes, ok
        recs.append(r)
    return recs


def cells(recs, stories):
    """Плоский список (config, story, repeat, field, gold, ev, pred)."""
    out = []
    for r in recs:
        if r["pred"] is None:
            continue
        s = stories[r["story"]]
        for f, g in s["gold"].items():
            out.append((r["config"], r["story"], r["repeat"], f, g, s["evidence"][f], r["pred"][f]))
    return out


def rate(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def boot(cl, stat, n=2000, seed=7):
    """cl: {story: [cells]} -> (est, lo, hi)."""
    keys = list(cl)
    rnd = random.Random(seed)
    est = stat([c for k in keys for c in cl[k]])
    vals = []
    for _ in range(n):
        smp = [c for k in (rnd.choice(keys) for _ in keys) for c in cl[k]]
        v = stat(smp)
        if v == v:
            vals.append(v)
    vals.sort()
    return est, vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


ACC = lambda cs: rate([c[6] == c[4] for c in cs])
KNOWN = lambda cs: rate([c[6] == c[4] for c in cs if c[5] != "u"])
UNK = lambda cs: rate([c[6] == "unknown" for c in cs if c[5] == "u"])


def pct(x):
    return "—" if x != x else f"{100 * x:.1f}%"


def ci(t):
    return f"{pct(t[0])} [{pct(t[1])}; {pct(t[2])}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(HERE / "results" / "raw.jsonl"))
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    stories = {s["id"]: s for s in corpus["stories"]}
    F, G = corpus["fields"], corpus["groups"]
    recs = load(a.raw, corpus)
    is_mock = any(r.get("mock") for r in recs)
    cs = cells(recs, stories)
    _ord = [c["name"] for c in json.loads((HERE / "configs.json").read_text(encoding="utf-8"))["configs"]]
    confs = sorted(dict.fromkeys(r["config"] for r in recs), key=lambda k: _ord.index(k) if k in _ord else 99)
    od = HERE / "results" / (a.tag or ("mock" if is_mock else "real"))
    od.mkdir(parents=True, exist_ok=True)

    byc = defaultdict(list)
    for c in cs:
        byc[c[0]].append(c)
    recc = defaultdict(list)
    for r in recs:
        recc[r["config"]].append(r)

    # --- Таблица A: главные показатели
    rowsA = []
    for k in confs:
        R, C = recc[k], byc[k]
        cl = defaultdict(list)
        for c in C:
            cl[c[1]].append(c)
        known = [c for c in C if c[5] != "u"]
        unk = [c for c in C if c[5] == "u"]
        # точный набор: все 11 полей истории верны в одном ответе
        per = defaultdict(list)
        for c in C:
            per[(c[1], c[2])].append(c[6] == c[4])
        lat = [r["latency"] for r in R if r.get("latency")]
        rowsA.append({
            "config": k,
            "ответов": len(R),
            "объект получен": rate([r["pred"] is not None for r in R]),
            "полный формат": rate([r["format_ok"] for r in R]),
            "точность (все)": boot(cl, ACC) if C else (float("nan"),) * 3,
            "известные верно": boot(cl, KNOWN) if known else (float("nan"),) * 3,
            "неизвестность сохранена": boot(cl, UNK) if unk else (float("nan"),) * 3,
            "додумано": rate([c[6] not in ("unknown",) for c in unk]),
            "ложное unknown": rate([c[6] == "unknown" for c in known]),
            "точный набор": rate([all(v) for v in per.values()]),
            "медиана, с": statistics.median(lat) if lat else float("nan"),
        })

    # --- Таблица B: по типу факта и группе полей
    rowsB = []
    for k in confs:
        C = byc[k]
        row = {"config": k}
        for t in "eiu":
            row[EV_NAME[t]] = ACC([c for c in C if c[5] == t])
        for g in dict.fromkeys(G.values()):
            row[g] = KNOWN([c for c in C if G[c[3]] == g])
        rowsB.append(row)

    # --- Таблица C: по полям (только известные) и по категориям историй
    rowsC = []
    for f in F:
        row = {"поле": f}
        for k in confs:
            row[k] = KNOWN([c for c in byc[k] if c[3] == f])
        rowsC.append(row)
    rowsD = []
    for cat, name in corpus["categories"].items():
        row = {"категория": f"{cat}: {name}"}
        for k in confs:
            row[k] = ACC([c for c in byc[k] if c[1][0] == cat])
        rowsD.append(row)

    # --- Устойчивость между повторами
    rowsE = []
    for k in confs:
        g = defaultdict(set)
        for c in byc[k]:
            g[(c[1], c[3])].add(c[6])
        multi = [v for v in g.values()]
        rowsE.append({"config": k, "поля с одинаковым ответом во всех повторах": rate([len(v) == 1 for v in multi])})

    # --- Парные разности (бутстрэп по историям, одни и те же истории)
    rowsF = []
    pairs = [(f"{m} базовый", f"{m} строгий") for m in ("Lite", "Pro", "Max")]
    pairs += [("Pro строгий", "Lite строгий"), ("Max строгий", "Lite строгий"), ("Max строгий", "Pro строгий")]
    ext = ("Claude Sonnet 5.5", "GPT-6 Sol", "DeepSeek V4 Pro")
    pairs += [(f"{m} базовый", f"{m} строгий") for m in ext]
    pairs += [(f"{m} строгий", "Max строгий") for m in ext]
    pairs += [("Claude Sonnet 5.5 строгий", "GPT-6 Sol строгий"), ("Claude Sonnet 5.5 строгий", "DeepSeek V4 Pro строгий"),
              ("GPT-6 Sol строгий", "DeepSeek V4 Pro строгий")]
    pairs = [(x, y) for x, y in pairs if x in byc and y in byc] or [(k, confs[0]) for k in confs[1:]]
    ids = list(stories)
    bys = {k: defaultdict(list) for k in confs}
    for c in cs:
        bys[c[0]][c[1]].append(c)
    for k, ref in pairs:
        rnd = random.Random(11)
        def diff(smp):
            A = [c for s_ in smp for c in bys[k][s_]]
            B = [c for s_ in smp for c in bys[ref][s_]]
            return ACC(A) - ACC(B), KNOWN(A) - KNOWN(B), UNK(A) - UNK(B)
        est = diff(ids)
        samples = [diff([rnd.choice(ids) for _ in ids]) for _ in range(2000)]
        res = {"сравнение": f"{k} − {ref}"}
        for i, nm in enumerate(["Δ точность", "Δ известные", "Δ неизвестность"]):
            v = sorted(x[i] for x in samples if x[i] == x[i])
            if not v or est[i] != est[i]:
                res[nm] = "—"
                continue
            lo, hi = v[int(.025 * len(v))], v[int(.975 * len(v)) - 1]
            res[nm] = f"{100*est[i]:+.1f} п.п. [{100*lo:+.1f}; {100*hi:+.1f}]"
        rowsF.append(res)

    # --- Цитаты и токены
    norm = lambda x: re.sub(r"[^\wё]+", " ", str(x).lower().replace("ё", "е")).strip()
    rowsG = []
    for k in confs:
        q_ok, q_all, tok_in, tok_out = 0, 0, [], []
        for r in recc[k]:
            u = r.get("usage") or {}
            if u:
                tok_in.append(u.get("prompt_tokens", 0) + u.get("precached_prompt_tokens", 0) + ((u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)) if r["model"].startswith("claude") else 0)); tok_out.append(u.get("completion_tokens", 0))
            if not r.get("quotes"):
                continue
            st_text = norm(stories[r["story"]]["text"])
            for f, q in r["quotes"].items():
                if q and r["pred"][f] not in ("unknown", "missing", "invalid"):
                    q_all += 1; q_ok += norm(q) in st_text
        rowsG.append({"config": k, "цитата есть в рассказе": (q_ok / q_all) if q_all else float("nan"),
                      "токенов на запрос (вход)": f"{statistics.mean(tok_in):.0f}" if tok_in else "—",
                      "токенов на запрос (выход)": f"{statistics.mean(tok_out):.0f}" if tok_out else "—",
                      "всего токенов": str(sum(tok_in) + sum(tok_out)),
                      "ошибки API": str(sum(1 for r in recc[k] if r.get("error")))})

    # --- Ошибки для качественного разбора
    errs = [c for c in cs if c[6] != c[4]]
    with (od / "errors.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["config", "story", "repeat", "field", "gold", "type", "pred", "error_kind", "text"])
        for c in errs:
            kind = "додумано" if c[5] == "u" else ("ложное unknown" if c[6] == "unknown" else "неверное значение")
            w.writerow([*c[:5], EV_NAME[c[5]], c[6], kind, stories[c[1]]["text"]])

    # --- CSV
    def dump(name, rows):
        with (od / name).open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
            w.writeheader()
            for r in rows:
                w.writerow({k: (ci(v) if isinstance(v, tuple) else (pct(v) if isinstance(v, float) and k != "медиана, с" else v)) for k, v in r.items()})
    for n, r in [("A_main.csv", rowsA), ("B_types.csv", rowsB), ("C_fields.csv", rowsC),
                 ("D_categories.csv", rowsD), ("E_repeats.csv", rowsE), ("G_quotes_tokens.csv", rowsG)] + ([("F_paired.csv", rowsF)] if rowsF else []):
        dump(n, r)

    # --- Markdown-отчёт
    def md(rows):
        h = list(rows[0])
        out = ["| " + " | ".join(h) + " |", "|" + "---|" * len(h)]
        for r in rows:
            out.append("| " + " | ".join(ci(v) if isinstance(v, tuple) else
                       (("—" if v != v else f"{v:.2f}") if k == "медиана, с" and isinstance(v, float) else pct(v) if isinstance(v, float) else str(v))
                       for k, v in r.items()) + " |")
        return "\n".join(out)
    warn = "\n> **ВНИМАНИЕ: это имитация (--mock). Цифры не являются результатами моделей.**\n" if is_mock else ""
    rep = f"""# Отчёт по извлечению фактов ДТП{warn}
Корпус: {len(stories)} историй × {len(F)} полей, версия {corpus['version']}. Ответов: {len(recs)}.

## A. Главные показатели (95% ДИ, бутстрэп по историям)
{md(rowsA)}

## B. Точность по типу факта и группе полей
Типы: явные / выводимые / неизвестные — доля верных. Группы — только известные значения.
{md(rowsB)}

## C. Точность по полям (известные значения)
{md(rowsC)}

## D. Точность по категориям историй
{md(rowsD)}

## E. Устойчивость между повторами
{md(rowsE)}
""" + (f"\n## F. Парные разности (95% ДИ)\n{md(rowsF)}\n" if rowsF else "") + \
        f"\n## G. Цитаты и расход токенов\n{md(rowsG)}\n" + \
        f"\nОшибок для разбора: {len(errs)} → errors.csv\n"
    (od / "report.md").write_text(rep, encoding="utf-8")

    # --- Графики
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ttl = " (ИМИТАЦИЯ)" if is_mock else ""
        fig, ax = plt.subplots(figsize=(12, 4.6), dpi=150)
        w = 0.8 / 3
        cols = ["#0B5C9E", "#7CC9FF", "#E8833A"]
        for j, t in enumerate("eiu"):
            ax.bar([i + (j - 1) * w for i in range(len(confs))], [100 * r[EV_NAME[t]] for r in rowsB], w,
                   label=EV_NAME[t], color=cols[j])
        ax.set_xticks(range(len(confs)), [c.replace(" ", chr(10), 1) if len(c) > 14 else c for c in confs], fontsize=7)
        ax.set_ylabel("Доля верных, %"); ax.set_ylim(0, 100)
        ax.set_title("Точность по типу факта" + ttl); ax.legend(frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout(); fig.savefig(od / "fig_types.png"); plt.close(fig)

        fig, ax = plt.subplots(figsize=(12, 4.6), dpi=150)
        groups = list(dict.fromkeys(G.values()))
        for j, g in enumerate(groups):
            ax.plot(confs, [100 * r[g] for r in rowsB], marker="o", label=g)
        ax.set_ylabel("Известные значения верно, %"); ax.set_ylim(0, 100)
        ax.set_title("Точность по группам полей" + ttl); ax.legend(frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout(); fig.savefig(od / "fig_groups.png"); plt.close(fig)
    except ImportError:
        print("matplotlib не установлен — графики пропущены")
    print(f"Готово: {od}")


if __name__ == "__main__":
    main()
