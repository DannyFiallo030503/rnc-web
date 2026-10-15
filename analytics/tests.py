"""Arithmetic regression cases; these do not validate institutional RNC methods."""

from django.test import SimpleTestCase

from .demo import summarize
from .metrics import (
    direct_standardized_rate,
    direct_standardized_rate_interval,
    incidence_rate,
    poisson_rate_interval,
    relative_frequency,
)


class CandidateCalculationTests(SimpleTestCase):
    def test_explicit_frequency_and_rate_units(self):
        self.assertAlmostEqual(relative_frequency(15, 60), 25)
        self.assertAlmostEqual(incidence_rate(20, 200_000), 10)
        self.assertAlmostEqual(incidence_rate(20, 200_000, scale=1_000), .1)

    def test_direct_adjustment_matches_hand_worked_example(self):
        # Rates are 100 and 300; reference weights 70%/30% give 160.
        self.assertAlmostEqual(direct_standardized_rate(
            {"A": 10, "B": 60}, {"A": 10_000, "B": 20_000}, {"A": 70, "B": 30}), 160)

    def test_adjusted_interval_matches_hand_worked_variance(self):
        # Var = 10*7² + 60*1.5² = 625; SE = 25.
        interval = direct_standardized_rate_interval(
            {"A": 10, "B": 60}, {"A": 10_000, "B": 20_000}, {"A": 70, "B": 30})
        self.assertAlmostEqual(interval.lower, 111.0009004, places=6)
        self.assertAlmostEqual(interval.upper, 208.9990996, places=6)

    def test_zero_count_poisson_upper_bound(self):
        interval = poisson_rate_interval(0, 100_000)
        self.assertEqual(interval.lower, 0)
        self.assertAlmostEqual(interval.upper, 3.688879454, places=8)
        standard = poisson_rate_interval(20, 100_000, .95)
        wider = poisson_rate_interval(20, 100_000, .99)
        self.assertLess(standard.lower, 20)
        self.assertGreater(standard.upper, 20)
        self.assertLess(wider.lower, standard.lower)
        self.assertGreater(wider.upper, standard.upper)

    def test_incompatible_or_nonfinite_inputs_are_rejected(self):
        for population in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(population=population), self.assertRaises(ValueError):
                incidence_rate(1, population)
        with self.assertRaises(ValueError):
            direct_standardized_rate({"A": 1}, {"B": 100}, {"A": 1})
        with self.assertRaises(ValueError):
            relative_frequency(11, 10)
        with self.assertRaises(ValueError):
            poisson_rate_interval(1, 100_000, 1)

    def test_combining_sites_does_not_duplicate_population(self):
        base = {"period": 2024, "territory": "Provincia de prueba", "sex": "Mujer",
                "age_group": "50-54", "population": 10_000, "standard_weight": 100}
        data = summarize([
            {**base, "site": "A", "tumor_count": 10, "person_count": 8},
            {**base, "site": "B", "tumor_count": 20, "person_count": 17},
        ])
        self.assertEqual(data["population"], 10_000)
        self.assertEqual(data["tumors"], 30)
        self.assertAlmostEqual(data["tumor_rate"], 300)
