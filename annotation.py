# -*- coding: utf-8 -*-
"""Проверка эталона двумя экспертами.

  python annotation.py make                 -> annotation/эксперт_1.xlsx, эксперт_2.xlsx (без эталона)
  python annotation.py score A.xlsx B.xlsx  -> annotation/agreement.md: каппа Коэна,
                                               расхождения экспертов и расхождения с черновым эталоном

Порядок работы: эксперты размечают независимо, не видя эталона и друг друга.
Затем расхождения обсуждаются, и финальный эталон вносится в corpus.json ДО прогона моделей.
"""
import json, pathlib, sys
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).parent
DESC = {
    "a_state": "Состояние машины A (рассказчик) перед ДТП", "b_state": "Состояние машины B перед ДТП",
    "a_stop": "Причина остановки A", "b_stop": "Причина остановки B",
    "a_man": "Манёвр A", "b_man": "Манёвр B",
    "a_contact": "Место первого контакта на машине A", "b_contact": "Место первого контакта на машине B",
    "direction": "Взаимное направление движения", "place": "Место ДТП",
    "priority": "Кто по ПДД должен был уступить / не создавать помех",
}


def kind(f):
    return f.split("_", 1)[-1] if f.startswith(("a_", "b_")) else f


def make(corpus):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    od = HERE / "annotation"; od.mkdir(exist_ok=True)
    for n in (1, 2):
        wb = Workbook(); ws = wb.active; ws.title = "Разметка"
        hdr = ["id", "Рассказ", "Поле", "Что отмечаем", "Значение", "Тип (e/i/u)", "Комментарий"]
        ws.append(hdr)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="0B5C9E")
        dvs = {}
        for k, vals in corpus["values"].items():
            dv = DataValidation(type="list", formula1='"' + ",".join(vals) + '"', allow_blank=True)
            ws.add_data_validation(dv); dvs[k] = dv
        dvt = DataValidation(type="list", formula1='"e,i,u"', allow_blank=True); ws.add_data_validation(dvt)
        r = 2
        for s in corpus["stories"]:
            for i, f in enumerate(corpus["fields"]):
                ws.append([s["id"], s["text"] if i == 0 else "", f, DESC[f], "", "", ""])
                dvs[kind(f)].add(f"E{r}"); dvt.add(f"F{r}")
                r += 1
        for col, w in zip("ABCDEFG", [6, 60, 11, 40, 15, 11, 30]):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2):
            row[1].alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        g = wb.create_sheet("Правила")
        for line in [
            "Размечайте независимо. Не смотрите эталон и разметку второго эксперта.",
            "A — машина рассказчика («я»), B — другая машина. Левая сторона — сторона водителя.",
            "Значение: выберите из списка. unknown — если по рассказу установить нельзя уверенно.",
            "Тип: e — сказано прямо; i — нужно вывести из сказанного; u — неизвестно (значение unknown).",
            "Утверждения второго водителя, с которыми рассказчик спорит, фактом не считаются.",
            "priority: A/B — кто по ПДД должен был уступить или не создавать помех; none — вопрос не возникал.",
        ]:
            g.append([line])
        g.column_dimensions["A"].width = 110
        wb.save(od / f"эксперт_{n}.xlsx")
    print(f"Созданы файлы в {od}")


def read(path):
    from openpyxl import load_workbook
    ws = load_workbook(path, data_only=True)["Разметка"]
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        sid, _, f, _, v, t, _ = row[:7]
        if sid and f:
            out[(sid, f)] = ((str(v).strip() if v else ""), (str(t).strip() if t else ""))
    return out


def kappa(pairs):
    pairs = [(a, b) for a, b in pairs if a and b]
    if not pairs:
        return float("nan"), 0
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n / n
    return ((po - pe) / (1 - pe) if pe < 1 else 1.0), n


def score(corpus, pa, pb):
    A, B = read(pa), read(pb)
    gold = {(s["id"], f): (s["gold"][f], s["evidence"][f]) for s in corpus["stories"] for f in corpus["fields"]}
    lines = ["# Согласие экспертов", "", "| Поле | n | Каппа (значение) | Согласие с эталоном, эксперт 1 | эксперт 2 |", "|---|---|---|---|---|"]
    allp = []
    for f in corpus["fields"]:
        keys = [k for k in gold if k[1] == f]
        p = [(A.get(k, ("", ""))[0], B.get(k, ("", ""))[0]) for k in keys]
        allp += p
        kv, n = kappa(p)
        ga = sum(A.get(k, ("",))[0] == gold[k][0] for k in keys) / len(keys)
        gb = sum(B.get(k, ("",))[0] == gold[k][0] for k in keys) / len(keys)
        lines.append(f"| {f} | {n} | {kv:.2f} | {100*ga:.0f}% | {100*gb:.0f}% |")
    kv, n = kappa(allp)
    kt, nt = kappa([(A.get(k, ("", ""))[1], B.get(k, ("", ""))[1]) for k in gold])
    lines += ["", f"**Все поля:** каппа по значению {kv:.2f} (n={n}), по типу факта {kt:.2f} (n={nt}).",
              "Ориентир: >0,8 — почти полное согласие, 0,6–0,8 — существенное.", "", "## Расхождения", "",
              "| id | поле | эксперт 1 | эксперт 2 | черновой эталон |", "|---|---|---|---|---|"]
    for k in gold:
        a, b = A.get(k, ("", ""))[0], B.get(k, ("", ""))[0]
        if a != b or a != gold[k][0]:
            lines.append(f"| {k[0]} | {k[1]} | {a or '—'} | {b or '—'} | {gold[k][0]} ({gold[k][1]}) |")
    out = HERE / "annotation" / "agreement.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Готово: {out}")


if __name__ == "__main__":
    c = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    if sys.argv[1:2] == ["make"]:
        make(c)
    elif sys.argv[1:2] == ["score"] and len(sys.argv) == 4:
        score(c, sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
