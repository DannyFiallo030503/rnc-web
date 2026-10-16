"""Funciones estadísticas puras para evaluación académica.

Estos cálculos no están aprobados ni contrastados con resultados del RNC. El
llamador debe proporcionar denominadores, estratos y pesos compatibles y
conservar la versión del método junto a cualquier resultado de evaluación.
"""

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from math import isfinite, log, sqrt
from statistics import NormalDist

from . import METHODS_VERSION

RATE_SCALE = 100_000


@dataclass(frozen=True)
class ConfidenceInterval:
    lower: float
    upper: float
    confidence_level: float
    method: str
    method_version: str = METHODS_VERSION


def poisson_rate_interval(
    cases: int,
    population: int | float,
    confidence_level: float = 0.95,
    scale: int = RATE_SCALE,
) -> ConfidenceInterval:
    """IC candidato para tasa cruda/específica: Byar; límite superior exacto si y=0.

    La aproximación Byar se usa para conteos positivos; con cero casos, el
    límite superior usa el cuantil exacto Poisson. No es una política RNC.
    """
    absolute_frequency(cases)
    _positive_finite(population, "La población")
    _positive_finite(scale, "La escala")
    z = _confidence_z(confidence_level)
    if cases == 0:
        lower_count = 0.0
        upper_count = -log((1 - confidence_level) / 2)
    else:
        lower_count = max(0.0, cases * (1 - 1 / (9 * cases) - z / (3 * sqrt(cases))) ** 3)
        next_count = cases + 1
        upper_count = next_count * (1 - 1 / (9 * next_count) + z / (3 * sqrt(next_count))) ** 3
    factor = float(scale) / float(population)
    return ConfidenceInterval(lower_count * factor, upper_count * factor, confidence_level,
                              "Poisson Byar aproximado; límite superior exacto si cero")


def direct_standardized_rate_interval(
    cases_by_stratum: Mapping[Hashable, int],
    population_by_stratum: Mapping[Hashable, int | float],
    standard_weights: Mapping[Hashable, int | float],
    confidence_level: float = 0.95,
    scale: int = RATE_SCALE,
) -> ConfidenceInterval:
    """IC Wald normal candidato para ASR; provisional, frágil con conteos bajos/ceros."""
    rate = direct_standardized_rate(cases_by_stratum, population_by_stratum, standard_weights, scale)
    _confidence_z(confidence_level)
    _positive_finite(scale, "La escala")
    total_weight = sum(float(weight) for weight in standard_weights.values())
    variance = 0.0
    for group, cases in cases_by_stratum.items():
        absolute_frequency(cases)
        population = float(population_by_stratum[group])
        weight = float(standard_weights[group]) / total_weight
        variance += cases * (weight / population * float(scale)) ** 2
    margin = _confidence_z(confidence_level) * sqrt(variance)
    return ConfidenceInterval(max(0.0, rate - margin), rate + margin, confidence_level,
                              "Wald normal con varianza Poisson CI5; candidato")


def _confidence_z(confidence_level: float) -> float:
    if isinstance(confidence_level, bool) or not isinstance(confidence_level, (int, float)) or not isfinite(confidence_level) or not 0 < confidence_level < 1:
        raise ValueError("El nivel de confianza debe estar entre cero y uno.")
    return NormalDist().inv_cdf((1 + float(confidence_level)) / 2)


def absolute_frequency(count: int) -> int:
    """Devuelve un conteo ya agregado, sin cambiar su unidad epidemiológica."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("El conteo debe ser un entero no negativo.")
    return count


def relative_frequency(part: int, universe: int) -> float:
    """Porcentaje del numerador sobre un universo explícito y compatible."""
    absolute_frequency(part)
    absolute_frequency(universe)
    if universe == 0:
        raise ValueError("El universo debe ser mayor que cero.")
    if part > universe:
        raise ValueError("El numerador no puede exceder el universo declarado.")
    return part / universe * 100


def incidence_rate(cases: int, population: int | float, scale: int = RATE_SCALE) -> float:
    """Tasa cruda o específica por la escala indicada (100 000 por defecto)."""
    absolute_frequency(cases)
    _positive_finite(population, "La población")
    _positive_finite(scale, "La escala")
    return cases / population * scale


def direct_standardized_rate(
    cases_by_stratum: Mapping[Hashable, int],
    population_by_stratum: Mapping[Hashable, int | float],
    standard_weights: Mapping[Hashable, int | float],
    scale: int = RATE_SCALE,
) -> float:
    """Tasa ajustada directa ponderada con pesos estándar suministrados.

    Requiere coincidencia exacta de estratos para impedir omisiones silenciosas.
    Los pesos pueden sumar cualquier total positivo: se normalizan en el cálculo.
    """
    case_groups = set(cases_by_stratum)
    if not case_groups or case_groups != set(population_by_stratum) or case_groups != set(standard_weights):
        raise ValueError("Casos, poblaciones y pesos deben cubrir los mismos estratos no vacíos.")

    _positive_finite(scale, "La escala")
    total_weight = 0.0
    weighted_rate = 0.0
    for group in cases_by_stratum:
        cases = absolute_frequency(cases_by_stratum[group])
        population = population_by_stratum[group]
        weight = standard_weights[group]
        _positive_finite(population, f"La población del estrato {group!r}")
        _nonnegative_finite(weight, f"El peso del estrato {group!r}")
        total_weight += float(weight)
        weighted_rate += cases / float(population) * float(weight)

    if total_weight <= 0:
        raise ValueError("La suma de los pesos estándar debe ser mayor que cero.")
    return weighted_rate / total_weight * float(scale)


def _positive_finite(value: int | float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError(f"{label} debe ser un número finito mayor que cero.")


def _nonnegative_finite(value: int | float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError(f"{label} debe ser un número finito no negativo.")
