"""python -m unittest discover engine  — reglas de fusión entre la Mac y GitHub Actions."""
import unittest

from exportar import fusionar

CFG = {"origen": "PBC", "ida_centro": "2026-12-22", "vuelta_centro": "2026-12-29", "flex_dias": 2,
       "excluir_ida": ["2026-12-24"], "excluir_vuelta": ["2026-12-31"], "aeropuertos_alternos": {"MEX": 480},
       "grupo_cdmx": {"adultos": 1, "aeropuertos": ["MEX"]}}


def snap(latest=None, hist=None, salud=None, **extra):
    return {"config": CFG, "latest": latest or {}, "historial": hist or {}, "mejor_total_diario_3p": {},
            "salud": salud or {"ultima_corrida": "2026-10-22T10:00", "corridas": {"mac": 1}}, **extra}


class Fusion(unittest.TestCase):
    def test_historial_toma_el_minimo_por_dia(self):
        r = snap(hist={"ida|PBC|2026-12-22": {"2026-10-20": 9000, "2026-10-21": 8000}})
        l = snap(hist={"ida|PBC|2026-12-22": {"2026-10-21": 7000, "2026-10-22": 7500}})
        h = fusionar(r, l)["historial"]["ida|PBC|2026-12-22"]
        self.assertEqual(h, {"2026-10-20": 9000, "2026-10-21": 7000, "2026-10-22": 7500})

    def test_latest_gana_el_mas_reciente(self):
        r = snap(latest={"ida|PBC|2026-12-22": {"precio_total": 1, "cuando": "2026-10-22T11:00"}})
        l = snap(latest={"ida|PBC|2026-12-22": {"precio_total": 2, "cuando": "2026-10-22T10:00"}})
        self.assertEqual(fusionar(r, l)["latest"]["ida|PBC|2026-12-22"]["precio_total"], 1)

    def test_sin_vuelo_posterior_borra_el_precio(self):
        r = snap(latest={"ida|PBC|2026-12-22": {"precio_total": 1, "cuando": "2026-10-22T09:00"}})
        l = snap(sin_vuelo={"ida|PBC|2026-12-22": "2026-10-22T10:00"})
        self.assertNotIn("ida|PBC|2026-12-22", fusionar(r, l)["latest"])

    def test_descarta_fechas_y_aeropuertos_fuera_de_reglas(self):
        r = snap(latest={"ida|PBC|2026-12-24": {"cuando": "x"}, "ida|NLU|2026-12-22": {"cuando": "x"},
                         "ida_cdmx|NLU|2026-12-22": {"cuando": "x"}, "vuelta|MEX|2026-12-29": {"cuando": "x"}})
        self.assertEqual(list(fusionar(r, snap())["latest"]), ["vuelta|MEX|2026-12-29"])

    def test_salud_suma_corridas_y_respeta_la_ultima(self):
        r = snap(salud={"ultima_corrida": "2026-10-22T09:00", "corridas_total": 557, "fuente": "Mac (fast-flights)",
                        "desde": "2026-09-26T00:47"})
        l = snap(salud={"ultima_corrida": "2026-10-22T12:00", "ultima_ci": "2026-10-22T12:00",
                        "corridas": {"ci": 3}, "fuente": "GitHub Actions (SerpApi)", "fallidas_seguidas": 0,
                        "serpapi_mes": {"mes": "2026-10", "ci": 12}})
        s = fusionar(r, l)["salud"]
        self.assertEqual(s["corridas_total"], 560)
        self.assertEqual(s["ultima_mac"], "2026-10-22T09:00")
        self.assertEqual(s["fuente"], "GitHub Actions (SerpApi)")
        self.assertEqual(s["serpapi_mes"]["usadas"], 12)

    def test_intento_fallido_no_refresca_los_datos(self):
        r = snap(salud={"ultima_corrida": "2026-10-23T00:07", "fallidas_seguidas": 0, "fuente": "Mac (fast-flights)"})
        l = snap(salud={"ultima_corrida": None, "ultimo_intento": "2026-10-23T00:08", "fallidas_seguidas": 1,
                        "fuente": "GitHub Actions (sin fuente)", "corridas": {"ci": 0}})
        s = fusionar(r, l)["salud"]
        self.assertEqual(s["ultima_corrida"], "2026-10-23T00:07")
        self.assertEqual(s["ultimo_intento"], "2026-10-23T00:08")
        self.assertEqual(s["fallidas_seguidas"], 1)

    def test_minimo_y_alerta(self):
        r = snap(minimo_historico={"total": 100, "cuando": "a"}, ultima_alerta={"total": 5, "cuando": "2026-10-01"})
        l = snap(minimo_historico={"total": 90, "cuando": "b"}, ultima_alerta={"total": 9, "cuando": "2026-09-01"})
        f = fusionar(r, l)
        self.assertEqual(f["minimo_historico"]["total"], 90)
        self.assertEqual(f["ultima_alerta"]["cuando"], "2026-10-01")


if __name__ == "__main__":
    unittest.main()
