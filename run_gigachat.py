# -*- coding: utf-8 -*-
"""Прогон историй corpus.json через модели GigaChat.

Ответы дописываются в results/raw.jsonl, повторный запуск продолжает с места остановки.

Переменные окружения:
  GIGACHAT_AUTH_KEY   — ключ авторизации (Base64 из личного кабинета), НЕ коммитить
  GIGACHAT_SCOPE      — GIGACHAT_API_PERS | GIGACHAT_API_B2B | GIGACHAT_API_CORP (по умолчанию PERS)
  GIGACHAT_CA_BUNDLE  — путь к сертификату НУЦ Минцифры (russian_trusted_root_ca.pem)

Примеры:
  python run_gigachat.py --list-models
  python run_gigachat.py                 # все конфигурации из configs.json
  python run_gigachat.py --only "Pro 3"  # одна конфигурация
  python run_gigachat.py --mock          # без API: имитация ответов для проверки конвейера
"""
import argparse, json, os, pathlib, random, sys, time, uuid

HERE = pathlib.Path(__file__).parent
OAUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API = "https://gigachat.devices.sberbank.ru/api/v1"


class Client:
    def __init__(self):
        import requests
        self.rq = requests
        self.key = os.environ.get("GIGACHAT_AUTH_KEY")
        kf = HERE / "gigachat_key.txt"  # альтернатива переменной окружения; не коммитить
        if not self.key and kf.exists():
            lines = [l.strip() for l in kf.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.key = lines[0]
            if len(lines) > 1:  # вторая строка — scope
                os.environ.setdefault("GIGACHAT_SCOPE", lines[1])
        if not self.key:
            sys.exit("Нет ключа: задайте GIGACHAT_AUTH_KEY или положите его в gigachat_key.txt")
        cf = HERE / "russian_trusted_root_ca.pem"
        if "GIGACHAT_CA_BUNDLE" not in os.environ and cf.exists():
            os.environ["GIGACHAT_CA_BUNDLE"] = str(cf)
        self.scope = os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.verify = os.environ.get("GIGACHAT_CA_BUNDLE", True)
        self.token, self.exp = None, 0

    def auth(self):
        if self.token and time.time() < self.exp - 60:
            return
        r = self.rq.post(OAUTH, data={"scope": self.scope}, verify=self.verify, timeout=30,
                         headers={"Authorization": f"Basic {self.key}", "RqUID": str(uuid.uuid4()),
                                  "Content-Type": "application/x-www-form-urlencoded"})
        r.raise_for_status()
        j = r.json()
        self.token, self.exp = j["access_token"], j["expires_at"] / 1000

    def models(self):
        self.auth()
        r = self.rq.get(f"{API}/models", headers={"Authorization": f"Bearer {self.token}"},
                        verify=self.verify, timeout=30)
        r.raise_for_status()
        return [m["id"] for m in r.json()["data"]]

    def chat(self, model, system, user, temperature, effort):
        self.auth()
        body = {"model": model, "temperature": temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if effort:
            body["reasoning_effort"] = effort
        for wait in (2, 5, 10, 20, 40, 60, None):  # 429 — лимит частоты, это не исход эксперимента
            t0 = time.time()
            r = self.rq.post(f"{API}/chat/completions", json=body, verify=self.verify, timeout=300,
                             headers={"Authorization": f"Bearer {self.token}"})
            dt = time.time() - t0
            if r.status_code != 429 or wait is None:
                break
            time.sleep(wait)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}", "latency": dt}
        j = r.json()
        ch = j["choices"][0]
        return {"text": ch["message"].get("content", ""), "finish": ch.get("finish_reason"),
                "model_version": j.get("model"), "usage": j.get("usage"), "latency": dt}


class Star:
    """Модели других разработчиков через агрегатор (star_key.txt: строка 1 — ключ, строка 2 — base URL .../v1).

    Claude вызывается через Anthropic SDK (/v1/messages), остальные — через /v1/chat/completions.
    Ключ не коммитить.
    """

    def __init__(self):
        import requests
        self.rq = requests
        lines = [l.strip() for l in (HERE / "star_key.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
        self.key, self.base = lines[0], lines[1].rstrip("/")
        self._anth = None

    def anth(self):
        if self._anth is None:
            import anthropic
            self._anth = anthropic.Anthropic(api_key=self.key, base_url=self.base[:-3] if self.base.endswith("/v1") else self.base,
                                             max_retries=4, timeout=600)
        return self._anth

    def chat(self, model, system, user, temperature, effort):
        t0 = time.time()
        if model.startswith("claude"):
            import anthropic
            kw = {}
            if effort:
                kw["output_config"] = {"effort": effort}
            try:
                m = self.anth().messages.create(model=model, max_tokens=4000, system=system,
                                                messages=[{"role": "user", "content": user}], **kw)
            except anthropic.APIStatusError as e:
                return {"error": f"HTTP {e.status_code}: {str(e.message)[:300]}", "latency": time.time() - t0}
            except anthropic.APIConnectionError as e:
                return {"error": f"connection: {e!r}"[:300], "latency": time.time() - t0}
            text = "".join(b.text for b in m.content if b.type == "text")
            u = m.usage
            return {"text": text, "finish": m.stop_reason, "model_version": m.model, "latency": time.time() - t0,
                    "usage": {"prompt_tokens": u.input_tokens, "completion_tokens": u.output_tokens,
                              "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
                              "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0}}
        body = {"model": model, "temperature": temperature, "max_tokens": 4000,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if effort:
            body["reasoning_effort"] = effort
        for wait in (5, 15, 30, 60, None):
            t0 = time.time()
            try:
                r = self.rq.post(f"{self.base}/chat/completions", json=body, timeout=600,
                                 headers={"Authorization": f"Bearer {self.key}"})
            except Exception as e:
                r = None; err = repr(e)[:300]
            dt = time.time() - t0
            if r is not None and r.status_code not in (429, 500, 502, 503, 504):
                break
            if wait is None:
                break
            time.sleep(wait)
        if r is None:
            return {"error": err, "latency": dt}
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}", "latency": dt}
        j = r.json()
        ch = j["choices"][0]
        return {"text": ch["message"].get("content") or "", "finish": ch.get("finish_reason"),
                "model_version": j.get("model"), "usage": j.get("usage"), "latency": dt}


class Mock:
    """Имитация: портит эталон с разной вероятностью. Только для проверки кода метрик."""
    LEVEL = {"Lite": 0.30, "Pro": 0.22, "Max": 0.15, "Pro 3": 0.18, "Pro 3 low": 0.12}

    def __init__(self, corpus):
        self.c = corpus
        self.by_text = {s["text"]: s for s in corpus["stories"]}

    def chat(self, model, system, user, temperature, effort, name=""):
        s = self.by_text[user]
        p = self.LEVEL.get(name, 0.2)
        rnd = random.Random(hash((name, s["id"], time.time_ns())))
        if rnd.random() < 0.03:
            return {"text": "Извините, не могу ответить.", "finish": "stop", "latency": 0.0}
        out = {}
        for f in self.c["fields"]:
            v = s["gold"][f]
            kind = f.split("_", 1)[-1] if f.startswith(("a_", "b_")) else f
            vals = self.c["values"][kind]
            ev = s["evidence"][f]
            q = p * (1.6 if ev == "u" else 1.2 if ev == "i" else 0.5)
            if rnd.random() < q:
                v = rnd.choice([x for x in vals if x != v])
            out[f] = {"value": v, "quote": None}
        return {"text": json.dumps(out, ensure_ascii=False), "finish": "stop", "latency": 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--stories", default=None, help="id историй через запятую (для пробного прогона)")
    ap.add_argument("--repeats", type=int, default=None)
    ap.add_argument("--workers", type=int, default=1, help="параллельных запросов (GigaChat с личным ключом — только 1)")
    a = ap.parse_args()

    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    cfg = json.loads((HERE / "configs.json").read_text(encoding="utf-8"))
    prompts = {}
    def system_for(c):
        f = c.get("prompt", "prompt.txt")
        if f not in prompts:
            prompts[f] = (HERE / f).read_text(encoding="utf-8")
        return prompts[f]

    if a.list_models:
        print("\n".join(Client().models()))
        return

    out = pathlib.Path(a.out) if a.out else HERE / "results" / ("mock_raw.jsonl" if a.mock else "raw.jsonl")
    out.parent.mkdir(exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add((r["config"], r["story"], r["repeat"]))

    clients = {}
    def client_for(c):
        p = "mock" if a.mock else c.get("provider", "gigachat")
        if p not in clients:
            clients[p] = Mock(corpus) if p == "mock" else Star() if p == "star" else Client()
        return clients[p]
    stories = corpus["stories"]
    if a.stories:
        stories = [s for s in stories if s["id"] in a.stories.split(",")]
    reps = a.repeats if a.repeats is not None else cfg["repeats"]
    jobs = [(c, s, k) for c in cfg["configs"] for k in range(reps) for s in stories
            if not a.only or any(c["name"].startswith(o) for o in a.only.split(","))]
    todo = [j for j in jobs if (j[0]["name"], j[1]["id"], j[2]) not in done]
    print(f"Заданий: {len(jobs)}, осталось: {len(todo)} -> {out}")
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lock = threading.Lock(); cnt = [0]
    for c in cfg["configs"]:  # клиенты создаём заранее, до потоков
        if any(j[0] is c for j in todo):
            client_for(c)

    def work(job, fh):
        c, s, k = job
        kw = {"name": c["name"]} if a.mock else {}
        try:
            r = client_for(c).chat(c["model"], system_for(c), s["text"], c.get("temperature", cfg["temperature"]), c["reasoning_effort"], **kw)
        except Exception as e:  # сеть, таймаут — фиксируем как отдельный исход
            r = {"error": repr(e)[:300]}
        rec = {"config": c["name"], "model": c["model"], "effort": c["reasoning_effort"], "prompt": c.get("prompt", "prompt.txt"),
               "story": s["id"], "repeat": k, "mock": a.mock, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **r}
        with lock:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
            cnt[0] += 1
            if cnt[0] % 20 == 0 or cnt[0] == len(todo):
                print(f"  {cnt[0]}/{len(todo)}", flush=True)

    with out.open("a", encoding="utf-8") as fh:
        if a.workers <= 1:
            for job in todo:
                work(job, fh)
        else:
            with ThreadPoolExecutor(a.workers) as ex:
                list(ex.map(lambda j: work(j, fh), todo))


if __name__ == "__main__":
    main()
