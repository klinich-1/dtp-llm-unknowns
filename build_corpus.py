# -*- coding: utf-8 -*-
"""Собирает corpus.json: 36 синтетических историй ДТП с эталоном.

Эталон — ЧЕРНОВОЙ. Его должны независимо проверить два человека
(таблица annotation.xlsx) до запуска моделей.

Метка у каждого значения:
  e — факт сказан прямо (explicit)
  i — факт нужно вывести из сказанного (inferred)
  u — по рассказу установить нельзя, верный ответ "unknown"
"""
import json, pathlib

FIELDS = ["a_state", "a_stop", "a_man", "a_contact",
          "b_state", "b_stop", "b_man", "b_contact",
          "direction", "place", "priority"]

# Группы полей для анализа
GROUPS = {
    "a_state": "движение", "a_stop": "движение", "a_man": "движение",
    "b_state": "движение", "b_stop": "движение", "b_man": "движение",
    "a_contact": "пространство", "b_contact": "пространство", "direction": "пространство",
    "place": "место",
    "priority": "приоритет",
}

VALUES = {
    "state": ["moving", "stopped", "parked", "unknown"],
    "stop": ["traffic_light", "traffic", "yield", "parking", "none", "unknown"],
    "man": ["straight", "left_turn", "right_turn", "u_turn", "lane_change", "overtaking",
            "reversing", "starting", "none", "unknown"],
    "contact": ["front", "rear", "left", "right", "front_left", "front_right",
                "rear_left", "rear_right", "unknown"],
    "direction": ["same", "opposite", "perpendicular", "unknown"],
    "place": ["intersection", "road", "parking", "yard", "unknown"],
    "priority": ["A", "B", "none", "unknown"],
}

CATEGORIES = {
    "E": "Простые: почти всё сказано прямо",
    "U": "Мало сведений: много неизвестного",
    "S": "Пространственные: стороны, углы, направления",
    "P": "Приоритет: нужен вывод по ПДД",
    "C": "Разговорная речь и самоисправления",
    "N": "Отрицания, сомнения и спорные утверждения",
}

# id | текст | 11 значений в порядке FIELDS
RAW = [
("E01", "Стоял на красный на перекрёстке Ленина и Мира. Сзади въехала Гранта, ударила передом в мой задний бампер. Водитель Гранты сказал, что ехал прямо и не успел затормозить.",
 "stopped:e traffic_light:e none:i rear:e moving:i none:i straight:e front:e same:i intersection:e none:i"),
("E02", "Ехал прямо по главной дороге через перекрёсток. Справа со второстепенной прямо выехал Солярис, не уступил и ударил передом мне в правую переднюю дверь.",
 "moving:e none:i straight:e right:e moving:e none:i straight:e front:e perpendicular:i intersection:e B:e"),
("E03", "Сдавал задом на парковке у торгового центра и задним бампером задел пустую стоящую Киа. Удар пришёлся ей в левый задний угол.",
 "moving:i none:i reversing:e rear:e parked:e parking:i none:i rear_left:e unknown:u parking:e none:i"),
("E04", "Поворачивал налево на зелёный. Навстречу прямо ехала Камри, она врезалась передом мне в правый бок.",
 "moving:i none:i left_turn:e right:e moving:e none:i straight:e front:e opposite:e intersection:i A:i"),
("E05", "Ехал в правом ряду по проспекту. Машина из левого ряда начала перестраиваться в мой ряд и задела меня. У меня поцарапан левый передний угол, у неё правый задний.",
 "moving:e none:i straight:i front_left:e moving:e none:i lane_change:e rear_right:e same:i road:i B:i"),
("E06", "Стоял в пробке на мосту. Машина впереди начала откатываться назад и ударила меня задним бампером в передний.",
 "stopped:e traffic:e none:i front:e moving:i none:i reversing:i rear:e same:i road:i none:i"),

("U01", "Меня ударили во дворе. Я вышел из машины, а там уже вмятина на заднем бампере, второй водитель стоит рядом.",
 "unknown:u unknown:u unknown:u rear:e unknown:u unknown:u unknown:u unknown:u unknown:u yard:e unknown:u"),
("U02", "Столкнулись с белой Ладой на Гагарина, у меня разбита фара. Как всё случилось, толком не понял.",
 "unknown:u unknown:u unknown:u front:i unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u"),
("U03", "Ехал домой, в меня въехали. Повреждения у обеих машин несерьёзные.",
 "moving:e none:i unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u"),
("U04", "Я парковался, а другая машина в это время выезжала с парковки. Чуть задели друг друга.",
 "moving:i none:i unknown:u unknown:u moving:i none:i unknown:u unknown:u unknown:u parking:e unknown:u"),
("U05", "На светофоре стояли две машины, моя первая. Потом удар, у меня смят багажник.",
 "stopped:e traffic_light:e none:i rear:i unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u"),
("U06", "Водитель Ниссана говорит, что я его подрезал, но я считаю, что виноват он сам. Удар был в мою заднюю левую дверь.",
 "moving:i none:i unknown:u rear_left:e unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u"),

("S01", "Ехал прямо. На перекрёстке без светофора слева выскочил Форд и ударил меня в водительскую дверь своим правым передним углом.",
 "moving:e none:i straight:e left:i moving:i none:i unknown:u front_right:e perpendicular:i intersection:e unknown:u"),
("S02", "Выезжал задом с парковочного места и правым задним углом задел машину, которая проезжала сзади. Удар пришёлся ей в левый бок.",
 "moving:i none:i reversing:e rear_right:e moving:e none:i straight:i left:e perpendicular:i parking:e A:i"),
("S03", "Ехали в одну сторону по двухполосной дороге, я во втором ряду. Он справа от меня решил развернуться через мою полосу и ударил передом мне в пассажирскую сторону.",
 "moving:i none:i straight:i right:i moving:i none:i u_turn:e front:e same:e road:i B:i"),
("S04", "На повороте дороги встречная машина срезала угол и выехала на мою полосу. Лобовое столкновение, у обеих машин разбиты передние левые части.",
 "moving:i none:i straight:i front_left:e moving:i none:i straight:i front_left:e opposite:e road:e none:i"),
("S05", "Трогался от обочины, включил левый поворотник. Машина, ехавшая сзади по левой полосе, задела мой левый передний угол своим правым боком.",
 "moving:i none:i starting:e front_left:e moving:e none:i straight:i right:e same:i road:i A:i"),
("S06", "На круговом движении я ехал по внешней полосе, а машина с внутренней начала съезжать прямо передо мной. Я ударил её передом в правый задний угол.",
 "moving:i none:i straight:i front:e moving:i none:i right_turn:i rear_right:e same:i intersection:i B:i"),

("P01", "Поворачивал направо со второстепенной дороги на главную. По главной слева ехал Рено, мы столкнулись: у меня разбит левый передний угол, у него правая сторона.",
 "moving:i none:i right_turn:e front_left:e moving:e none:i straight:i right:e perpendicular:i intersection:i A:i"),
("P02", "Ехал прямо на зелёный, а слева на красный проехал внедорожник и врезался передом мне в левый бок.",
 "moving:e none:i straight:e left:e moving:e none:i straight:i front:e perpendicular:i intersection:i B:i"),
("P03", "Выезжал из двора на дорогу и поворачивал налево. Машина ехала по дороге справа и ударила меня передом в правый задний угол.",
 "moving:i none:i left_turn:e rear_right:e moving:e none:i straight:i front:e perpendicular:i road:i A:i"),
("P04", "На равнозначном перекрёстке без знаков я ехал прямо, справа от меня прямо ехал Хендай. Столкнулись: у меня правое переднее крыло, у него левое переднее.",
 "moving:e none:i straight:e front_right:e moving:e none:i straight:e front_left:e perpendicular:i intersection:e A:i"),
("P05", "Разворачивался на перекрёстке на зелёный. Встречная машина ехала прямо, удар пришёлся мне в правый задний угол.",
 "moving:i none:i u_turn:e rear_right:e moving:e none:i straight:e unknown:u opposite:e intersection:e A:i"),
("P06", "Стоял перед пешеходным переходом, пропускал людей. Сзади меня объезжал автобус, чтобы перестроиться в мой ряд, и задел мою левую сторону своим правым боком.",
 "stopped:e yield:e none:i left:e moving:i none:i lane_change:e right:e same:i road:i B:i"),

("C01", "Короче, еду я такой, ну не еду, стоял уже, на светофоре, и тут бац — в зад мне прилетает газелька.",
 "stopped:e traffic_light:e none:i rear:e moving:i none:i unknown:u front:i same:i unknown:u none:i"),
("C02", "Поворачивал направо, нет, стоп, налево, во двор. А сзади меня обгонял какой-то умник по встречке и ударил в левую дверь.",
 "moving:i none:i left_turn:e left:e moving:i none:i overtaking:e unknown:u same:i road:i unknown:u"),
("C03", "Я на своей девятке, а он на крузаке. Он мне в бочину справа влетел, когда я по главной шёл прямо.",
 "moving:e none:i straight:e right:e moving:i none:i unknown:u front:i unknown:u unknown:u unknown:u"),
("C04", "Ну там парковка у Пятёрочки, я назад сдавал, не, вперёд выезжал, а он сзади сдавал. В общем, он задом мне в переднюю правую часть.",
 "moving:i none:i straight:i front_right:e moving:i none:i reversing:e rear:e unknown:u parking:e B:i"),
("C05", "Стояла на аварийке у обочины, в меня сзади въехал таксист, у него в руке был телефон.",
 "stopped:e unknown:u none:i rear:e moving:i none:i unknown:u front:i same:i road:i none:i"),
("C06", "Значит так. Перекрёсток, у меня зелёный, я прямо. Он со встречки налево, не пропустил. Мне в морду, ему в правую сторону.",
 "moving:e none:i straight:e front:e moving:e none:i left_turn:e right:e opposite:e intersection:e B:e"),

("N01", "Я не поворачивал и не перестраивался, ехал строго в своём ряду. Машина справа начала поворачивать налево прямо передо мной, и я ударил её в левый бок.",
 "moving:e none:i straight:e front:i moving:i none:i left_turn:e left:e same:i unknown:u B:i"),
("N02", "Пострадавших нет. Я не уверен, ехал ли второй водитель или уже стоял, когда я въехал в него задним ходом.",
 "moving:i none:i reversing:e rear:i unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u unknown:u"),
("N03", "Сначала мне показалось, что удар был в заднюю дверь, но потом увидел — вмятина на заднем бампере. Я стоял в пробке.",
 "stopped:e traffic:e none:i rear:e moving:i none:i unknown:u front:i same:i unknown:u none:i"),
("N04", "Второй водитель утверждает, что стоял, но он катился вперёд и задел меня своим правым передним углом. Я ехал прямо по соседней левой полосе.",
 "moving:e none:i straight:e right:i moving:e none:i unknown:u front_right:e same:i unknown:u unknown:u"),
("N05", "Никаких поворотов, ни я, ни он. Ехали навстречу друг другу по узкому проезду во дворе и зацепились зеркалами — у меня левое, у него тоже левое.",
 "moving:e none:i straight:e left:e moving:e none:i straight:e left:e opposite:e yard:e unknown:u"),
("N06", "Это не я въехал в него, а он в меня: он сдавал назад со своего места на парковке, а я стоял и ждал, пока место освободится.",
 "stopped:e parking:i none:i unknown:u moving:i none:i reversing:e rear:i unknown:u parking:e B:i"),
]


def kind(field):
    return field.split("_", 1)[-1] if field.startswith(("a_", "b_")) else field


def build():
    stories = []
    for sid, text, labels in RAW:
        parts = labels.split()
        assert len(parts) == len(FIELDS), sid
        gold, ev = {}, {}
        for f, p in zip(FIELDS, parts):
            v, t = p.split(":")
            assert v in VALUES[kind(f)], (sid, f, v)
            assert t in "eiu", (sid, f, t)
            assert (v == "unknown") == (t == "u"), (sid, f, p)
            gold[f], ev[f] = v, t
        stories.append({"id": sid, "category": sid[0], "text": text, "gold": gold, "evidence": ev})
    return {"version": "v1-2026-11-06-expert-approved", "fields": FIELDS, "groups": GROUPS,
            "values": VALUES, "categories": CATEGORIES, "stories": stories}


if __name__ == "__main__":
    c = build()
    out = pathlib.Path(__file__).with_name("corpus.json")
    out.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(c["stories"]) * len(FIELDS)
    cnt = {t: sum(s["evidence"][f] == t for s in c["stories"] for f in FIELDS) for t in "eiu"}
    print(f"{len(c['stories'])} историй, {n} значений: явных {cnt['e']}, выводимых {cnt['i']}, неизвестных {cnt['u']}")
