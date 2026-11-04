"""Pruebas sin conexión a internet. Ejecutar: python -m unittest discover tests"""
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from radar import advisor, indicators as ind, news, plan, sec, signals, stats  # noqa: E402
import update  # noqa: E402


class IndicatorTests(unittest.TestCase):
    def test_sma_ema(self):
        self.assertEqual(ind.sma([1, 2, 3, 4, 5], 3)[2:], [2, 3, 4])
        self.assertAlmostEqual(ind.ema([1.0, 2.0, 3.0, 4.0], 3)[3], 3.0)

    def test_rsi(self):
        ref = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
        self.assertAlmostEqual(ind.rsi(ref)[14], 70.46, delta=0.2)
        self.assertEqual(ind.rsi([float(i) for i in range(40)])[-1], 100.0)
        self.assertEqual(ind.rsi([5.0] * 40)[-1], 50.0)


class SignalTests(unittest.TestCase):
    def test_sign_change(self):
        self.assertEqual(signals.recent_sign_change([-1, -0.5, 0.2], 2), 1)
        self.assertEqual(signals.recent_sign_change([1, 0.5, -0.2], 2), -1)
        self.assertEqual(signals.recent_sign_change([-1, 1, 2, 3, 4], 2), 0)

    def test_crosses(self):
        def find(series, step, prefix):
            for _ in range(60):
                series.append(series[-1] + step)
                if any(m.startswith(prefix) for m in signals.evaluate(series)["motivos"]):
                    return True
            return False
        self.assertTrue(find([100 - i * 0.5 for i in range(80)], 1.2, "Cruce alcista"))
        self.assertTrue(find([50 + i * 0.5 for i in range(80)], -1.2, "Cruce bajista"))
        self.assertEqual(signals.evaluate([10.0] * 30)["accion"], signals.HOLD)


class StatsTests(unittest.TestCase):
    def test_stats(self):
        weekly = [100 * 1.10 ** (i / 52) for i in range(261)]
        self.assertAlmostEqual(stats.cagr(weekly, 52), 0.10, places=9)
        self.assertAlmostEqual(stats.max_drawdown([100, 120, 90, 130, 117]), -0.25)


SLEEVES = plan.normalize_sleeves([
    {"grupo": "Núcleo", "nombre": "S&P 500", "peso": 45, "candidatos": ["SPY"]},
    {"grupo": "Núcleo", "nombre": "Nasdaq", "peso": 15, "candidatos": ["QQQ"]},
    {"grupo": "Núcleo", "nombre": "Desarrollados", "peso": 7, "candidatos": ["EFA"]},
    {"grupo": "Núcleo", "nombre": "Emergentes", "peso": 8, "candidatos": ["EEM"]},
    {"grupo": "Temática", "nombre": "Tecno", "peso": 10, "candidatos": [{"ticker": "MSFT", "nombre": "Microsoft"}, "NVDA", "GOOGL"]},
    {"grupo": "Temática", "nombre": "Salud", "peso": 7, "candidatos": ["LLY", "VRTX"]},
    {"grupo": "Temática", "nombre": "Argentina", "peso": 8, "candidatos": ["VIST", "YPF", "GGAL"]},
])


class PlanTests(unittest.TestCase):
    def test_holdings(self):
        h = plan.holdings_from_movements([
            {"fecha": "2026-01-02", "ticker": "spy", "monto_usd": 100, "precio_usd": 500},
            {"fecha": "2026-02-02", "ticker": "SPY", "monto_usd": 100, "precio_usd": 400},
            {"fecha": "2026-03-02", "ticker": "QQQ", "monto_usd": 50, "precio_usd": 0},  # inválido
            {"fecha": "2026-04-02", "ticker": "SPY", "tipo": "venta", "monto_usd": 90, "precio_usd": 600},
        ])
        self.assertEqual(list(h), ["SPY"])
        self.assertAlmostEqual(h["SPY"]["cantidad"], 0.2 + 0.25 - 0.15)
        self.assertAlmostEqual(h["SPY"]["invertido_usd"], 200 * (1 - 0.15 / 0.45))
        v = plan.value_holdings(h, {"SPY": 700})
        self.assertAlmostEqual(v[0]["valor_usd"], 0.3 * 700)

    def test_first_month_goes_to_biggest_sleeve(self):
        s = plan.suggest(SLEEVES, {}, 100, {}, {})
        self.assertEqual([(x["ticker"], x["monto_usd"]) for x in s], [("SPY", 100)])

    def test_rotation_over_months(self):
        values, bought = {}, []
        ranking = {"MSFT": 70, "NVDA": 80, "GOOGL": 60, "LLY": 75, "VRTX": 50, "VIST": 65, "YPF": 55, "GGAL": 60}
        for _ in range(24):
            for x in plan.suggest(SLEEVES, values, 100, ranking, {}):
                values[x["ticker"]] = values.get(x["ticker"], 0) + x["monto_usd"]
                bought.append(x["ticker"])
        self.assertEqual(sum(values.values()), 2400)
        per, _ = plan.sleeve_values(SLEEVES, values)
        for s, v in zip(SLEEVES, per):
            self.assertLess(abs(v / 2400 * 100 - s["peso"]), 4.5, s["nombre"])
        self.assertIn("NVDA", bought)
        self.assertIn("LLY", bought)

    def test_bigger_amount_splits(self):
        s = plan.suggest(SLEEVES, {}, 1500, {}, {})
        self.assertEqual(len(s), 3)
        self.assertEqual(sum(x["monto_usd"] for x in s), 1500)

    def test_sell_signal_skips_thematic_pick(self):
        values = {"SPY": 450, "QQQ": 150, "EFA": 70, "EEM": 80, "LLY": 70, "VIST": 80}
        s = plan.suggest(SLEEVES, values, 100, {"NVDA": 90, "MSFT": 70}, {"NVDA": "VENTA"})
        self.assertEqual(s[0]["ticker"], "MSFT")

    def test_prefers_held_when_close(self):
        sleeve = SLEEVES[4]
        self.assertEqual(plan.pick_ticker(sleeve, {"NVDA": 80, "MSFT": 78}, {}, {"MSFT": 10}), "MSFT")
        self.assertEqual(plan.pick_ticker(sleeve, {"NVDA": 80, "MSFT": 70}, {}, {"MSFT": 10}), "NVDA")

    def test_scores(self):
        sc = plan.composite_scores({
            "A": {"momentum": 0.3, "tecnico_puntaje": 3, "crecimiento": 20, "margen": 25, "moneda": "USD", "sentimiento": 70},
            "B": {"momentum": 0.1, "tecnico_puntaje": -1, "crecimiento": 5, "margen": 10, "moneda": "USD", "sentimiento": 50},
            "C": {"momentum": None, "tecnico_puntaje": None, "crecimiento": 90, "margen": None, "moneda": "ARS", "sentimiento": None},
        })
        self.assertGreater(sc["A"]["puntaje"], sc["B"]["puntaje"])
        self.assertIsNone(sc["C"]["puntaje"])  # crecimiento en pesos no se compara

    def test_momentum(self):
        closes = [100.0] * 231 + [120.0] * 21
        self.assertAlmostEqual(plan.momentum_12_1(closes), 0.0)
        self.assertIsNone(plan.momentum_12_1([1.0] * 100))


RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Nvidia beats estimates as AI demand surges - Reuters</title><link>https://a</link><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate><source url="x">Reuters</source></item>
<item><title>Nvidia faces antitrust probe in Europe - Bloomberg</title><link>https://b</link><source url="x">Bloomberg</source></item>
<item><title>Nvidia in talks to buy chip startup - CNBC</title><link>https://c</link><source url="x">CNBC</source></item>
<item><title>What to watch this week - WSJ</title><link>https://d</link><source url="x">WSJ</source></item>
</channel></rss>"""


class NewsTests(unittest.TestCase):
    def test_parse_and_score(self):
        items = news.parse_rss(RSS)
        self.assertEqual(items[0]["titulo"], "Nvidia beats estimates as AI demand surges")
        self.assertEqual(items[0]["fecha"], "2026-11-02")
        self.assertEqual([i["tono"] for i in items], [1, -1, 0, 0])
        self.assertEqual([i["fusion"] for i in items], [False, False, True, False])
        s = news.summarize(items)
        self.assertEqual(s["puntaje"], 50.0)
        self.assertEqual(len(s["fusiones"]), 1)

    def test_no_false_merger(self):
        self.assertFalse(news.mentions_merger("Is it time to buy Nvidia stock?"))
        self.assertTrue(news.mentions_merger("AbbVie agrees to buy biotech for $10 billion"))

    def test_clean_name(self):
        self.assertEqual(news.clean_company_name("NVIDIA Corporation"), "NVIDIA")
        self.assertEqual(news.clean_company_name("Eli Lilly and Company"), "Eli Lilly and")
        self.assertEqual(news.clean_company_name("MercadoLibre, Inc."), "MercadoLibre")


def facts(rows, taxonomy="us-gaap", unit="USD"):
    out = {}
    for name, entries in rows.items():
        out[name] = {"units": {unit if "PerShare" not in name else "USD/shares": entries}}
    return {"entityName": "Ejemplo Corp", "facts": {taxonomy: out}}


class SecTests(unittest.TestCase):
    def test_extract(self):
        def e(start, end, val, form="10-K", filed="2025-02-01"):
            return {"start": start, "end": end, "val": val, "form": form, "filed": filed}
        cf = facts({
            "Revenues": [e("2023-01-01", "2023-12-31", 100), e("2024-01-01", "2024-12-31", 120),
                         e("2024-10-01", "2024-12-31", 35, form="10-Q")],
            "NetIncomeLoss": [e("2024-01-01", "2024-12-31", 24)],
            "EarningsPerShareDiluted": [e("2024-01-01", "2024-12-31", 2.0)],
        })
        f = sec.extract(cf, price=50)
        self.assertEqual(f["crecimiento_ingresos_pct"], 20.0)
        self.assertEqual(f["margen_neto_pct"], 20.0)
        self.assertEqual(f["precio_ganancia"], 25.0)
        self.assertIsNone(sec.extract({"facts": {}}, 10))


class AdvisorTests(unittest.TestCase):
    def test_parse_review(self):
        text = "Comentario.\n```json\n" + json.dumps({
            "resumen": "ok", "aporte": {"de_acuerdo": True, "comentario": "bien"},
            "tesis": [{"ticker": "nvda", "veredicto": "Vigilar"}, {"ticker": "x", "veredicto": "comprar ya"}, "basura"],
        }) + "\n```"
        r = advisor.parse_review(text)
        self.assertEqual([(t["ticker"], t["veredicto"]) for t in r["tesis"]], [("NVDA", "vigilar"), ("X", "mantener")])
        self.assertEqual(advisor.explanation(text), "Comentario.")
        self.assertIsNone(advisor.parse_review("nada"))


class RotationParityTests(unittest.TestCase):
    """La web (docs/rotation.js) tiene que sugerir exactamente lo mismo que Python."""

    def test_parity(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js no está instalado")
        rnd = random.Random(7)
        tickers = [t for s in SLEEVES for t in s["candidatos"]] + ["OTRO"]
        cases = []
        for _ in range(300):
            values = {t: round(rnd.uniform(0, 900), 2) for t in tickers if rnd.random() < 0.5}
            ranking = {t: round(rnd.uniform(0, 100), 1) for t in tickers if rnd.random() < 0.8}
            sigs = {t: rnd.choice(["COMPRA", "VENTA", "MANTENER"]) for t in tickers if rnd.random() < 0.6}
            amount = rnd.choice([50, 100, 100, 150, 250, 333, 999, 1000, 2500, 7777])
            cases.append({"values": values, "ranking": ranking, "signals": sigs, "amount": amount,
                          "expected": plan.suggest(SLEEVES, values, amount, ranking, sigs)})
        tmp = Path(tempfile.mkdtemp())
        (tmp / "cases.json").write_text(json.dumps({"sleeves": SLEEVES, "cases": cases}))
        script = tmp / "check.mjs"
        script.write_text(
            "import { readFileSync } from 'fs';\n"
            f"import {{ suggest }} from '{(ROOT / 'docs' / 'rotation.js').as_uri()}';\n"
            f"const d = JSON.parse(readFileSync('{(tmp / 'cases.json').as_posix()}', 'utf8'));\n"
            "let bad = 0;\n"
            "d.cases.forEach((c, i) => {\n"
            "  const got = suggest(d.sleeves, c.values, c.amount, c.ranking, c.signals);\n"
            "  const a = JSON.stringify(got.map(x => [x.ticker, x.monto_usd, x.grupo_id, x.actual_pct, x.objetivo_pct]));\n"
            "  const b = JSON.stringify(c.expected.map(x => [x.ticker, x.monto_usd, x.grupo_id, x.actual_pct, x.objetivo_pct]));\n"
            "  if (a !== b) { bad++; if (bad < 4) console.log(i, a, b); }\n"
            "});\n"
            "console.log('diferencias', bad);\n"
            "process.exit(bad ? 1 : 0);\n"
        )
        res = subprocess.run([node, str(script)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


# ---------- corrida completa simulada ----------

def fake_fetch(symbol, range_, interval):
    if symbol in ("NOEXISTE",):
        return None
    n = {"1mo": 22, "1y": 252, "5y": 261}.get(range_, 30)
    seed = sum(ord(c) for c in symbol)
    closes = [100 + seed % 50 + i * 0.05 + 3 * math.sin((i + seed) / 7) for i in range(n)]
    return {"symbol": symbol, "name": f"{symbol} Inc.", "currency": "USD", "price": closes[-1],
            "previous_close": closes[-2], "change_pct": (closes[-1] / closes[-2] - 1) * 100,
            "closes": closes, "adj_closes": closes, "timestamps": list(range(n))}


def fake_news(company):
    return news.parse_rss(RSS.replace("Nvidia", company))


class FakeSec:
    def __init__(self, contact):
        self.contact = contact

    def fundamentals(self, ticker, price):
        return {"crecimiento_ingresos_pct": len(ticker) * 5.0, "margen_neto_pct": 10.0, "moneda": "USD", "precio_ganancia": 20.0}


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old = (update.DATA, update.CONFIG_PATH, update.STATE_PATH, update.PORTFOLIO_PATH)
        update.DATA = self.tmp / "docs" / "data"
        update.CONFIG_PATH = self.tmp / "config.json"
        update.STATE_PATH = self.tmp / "estado.json"
        update.PORTFOLIO_PATH = self.tmp / "cartera.json"
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        cfg["lista"] = ["NOEXISTE", "GLD"]
        update.CONFIG_PATH.write_text(json.dumps(cfg), encoding="utf-8")
        update.PORTFOLIO_PATH.write_text(json.dumps({"movimientos": [
            {"fecha": "2026-10-01", "ticker": "SPY", "monto_usd": 100, "precio_usd": 100},
            {"fecha": "2026-10-01", "ticker": "NVDA", "monto_usd": 50, "precio_usd": 100},
        ]}), encoding="utf-8")
        self.sent, self.asked = [], []
        self.env = dict(os.environ)

    def tearDown(self):
        update.DATA, update.CONFIG_PATH, update.STATE_PATH, update.PORTFOLIO_PATH = self.old
        os.environ.clear()
        os.environ.update(self.env)

    def send(self, title, message, url="", tags=None, priority=3):
        self.sent.append(title)
        return []

    def ask(self, key, system, user, model, max_searches):
        self.asked.append(user)
        review = {"resumen": "ok", "aporte": {"de_acuerdo": True, "comentario": "Tiene sentido."},
                  "tesis": [{"ticker": "NVDA", "veredicto": "vigilar", "tesis": "t", "riesgos": "r"}]}
        return {"text": "```json\n" + json.dumps(review) + "\n```", "sources": []}

    def run_on(self, when):
        return update.run(fetch=fake_fetch, ask=self.ask, send=self.send, news_fetch=fake_news,
                          sec_factory=FakeSec, patents_fn=lambda k, org: {"ultimos_12_meses": 10},
                          today=when)

    def test_free_mode(self):
        meta = self.run_on(datetime(2026, 11, 3, 18, 30))  # martes, después del día 1
        self.assertEqual(meta["errores"], [])
        self.assertEqual(self.asked, [])
        self.assertIn("Modo gratuito", meta["ia"])
        p = json.loads((update.DATA / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(p["sugerencia"][0]["monto_usd"], 100)
        self.assertEqual({r["ticker"] for r in p["cartera"]}, {"SPY", "NVDA"})
        self.assertIn("Aporte de noviembre", self.sent)
        ideas = json.loads((update.DATA / "ideas.json").read_text(encoding="utf-8"))
        self.assertTrue(all(i.get("puntaje") is not None for i in ideas if not i.get("sin_datos")))
        self.assertTrue(any(i["sentimiento"]["fusiones"] for i in ideas))
        sig = json.loads((update.DATA / "signals.json").read_text(encoding="utf-8"))
        self.assertTrue(next(r for r in sig if r["symbol"] == "NOEXISTE")["sin_datos"])

        # Al día siguiente: sin recordatorio repetido ni avisos de fusiones ya vistas.
        self.sent.clear()
        self.run_on(datetime(2026, 11, 4, 18, 30))
        self.assertNotIn("Aporte de noviembre", self.sent)
        self.assertFalse(any(t.startswith("Posible fusión") for t in self.sent))

    def test_monthly_ai(self):
        os.environ["ANTHROPIC_API_KEY"] = "x"
        os.environ["SEC_CONTACTO"] = "a@b.c"
        os.environ["PATENTSVIEW_API_KEY"] = "k"
        meta = self.run_on(datetime(2026, 11, 2, 18, 30))
        self.assertEqual(len(self.asked), 1)
        self.assertTrue(meta["fuentes"]["sec"] and meta["fuentes"]["patentes"])
        self.assertIn("La IA sugiere vigilar: NVDA", self.sent)
        ai = json.loads((update.DATA / "ai.json").read_text(encoding="utf-8"))
        self.assertEqual(ai["revision"]["tesis"][0]["ticker"], "NVDA")
        ideas = json.loads((update.DATA / "ideas.json").read_text(encoding="utf-8"))
        self.assertTrue(any(i.get("patentes") for i in ideas))
        # Mismo mes: no vuelve a consultar.
        self.run_on(datetime(2026, 11, 3, 18, 30))
        self.assertEqual(len(self.asked), 1)
        # Mes siguiente: sí.
        self.run_on(datetime(2026, 12, 1, 18, 30))
        self.assertEqual(len(self.asked), 2)

    def test_weekly_summary_on_friday(self):
        self.run_on(datetime(2026, 11, 6, 18, 30))  # viernes
        self.assertIn("Resumen de tu plan", self.sent)


if __name__ == "__main__":
    unittest.main()
