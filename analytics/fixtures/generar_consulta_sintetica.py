"""Regenera un escenario ficticio con etiquetas y contexto demográfico cubanos."""

import csv
from pathlib import Path
import sys

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from analytics.catalogs import id_for

AGES = [
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
    "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74",
    "75-79", "80-84", "85+",
]
YEARS = [2021, 2022, 2023, 2024]
ANNUAL_CASE_TARGETS = {2021: 40500, 2022: 41400, 2023: 42300, 2024: 43200}

# Población media por provincia, tabla 1.2 del Anuario Demográfico de Cuba 2024.
PROVINCE_POPULATIONS = {
    "Pinar del Río": [577024, 558749, 537741, 515208],
    "Artemisa": [508359, 491741, 473195, 452430],
    "La Habana": [2086844, 1984455, 1870806, 1749964],
    "Mayabeque": [379122, 364162, 348018, 330260],
    "Matanzas": [705753, 679098, 650369, 619159],
    "Villa Clara": [763873, 733814, 700350, 665447],
    "Cienfuegos": [399602, 382767, 364607, 342709],
    "Sancti Spíritus": [457946, 442231, 424064, 404037],
    "Ciego de Ávila": [427959, 411784, 396448, 376919],
    "Camagüey": [752938, 724121, 692922, 653203],
    "Las Tunas": [528166, 513604, 497042, 475343],
    "Holguín": [1011393, 982799, 951574, 911674],
    "Granma": [811049, 793962, 775906, 749289],
    "Santiago de Cuba": [1038663, 1020459, 998939, 963915],
    "Guantánamo": [501949, 492909, 482927, 465429],
    "Isla de la Juventud": [82832, 80388, 77446, 73021],
}

# Sexo por provincia: población efectiva 2024, tabla 1.7 de ONEI.
PROVINCE_SEX = {
    "Pinar del Río": (258717, 256491), "Artemisa": (225649, 226781),
    "La Habana": (825923, 924041), "Mayabeque": (165666, 164594),
    "Matanzas": (306122, 313037), "Villa Clara": (328068, 337379),
    "Cienfuegos": (170642, 172067), "Sancti Spíritus": (201199, 202838),
    "Ciego de Ávila": (188429, 188490), "Camagüey": (322711, 330492),
    "Las Tunas": (239097, 236246), "Holguín": (454822, 456852),
    "Granma": (376251, 373038), "Santiago de Cuba": (477131, 486784),
    "Guantánamo": (231868, 233561), "Isla de la Juventud": (36614, 36407),
}

# Distribución efectiva de Cuba por sexo y grupo quinquenal, tabla 1.10 de ONEI.
NATIONAL_AGE_SEX = {
    "Hombres": [226801, 277179, 292519, 265726, 294293, 277224, 296485, 307198, 265520, 299395, 423166, 429008, 376390, 241247, 207368, 150179, 98465, 80746],
    "Mujeres": [213473, 256821, 275212, 251788, 267815, 259171, 289800, 309751, 269765, 306477, 434612, 452320, 404997, 270355, 239476, 187665, 131994, 117606],
}

SITES = [
    "Tráquea, bronquios y pulmón", "Próstata", "Mama", "Colon y recto",
    "Estómago", "Cuello del útero", "Cuerpo del útero", "Tiroides",
    "Páncreas", "Vejiga urinaria", "Riñón", "Hígado y vías biliares",
    "Ovario", "Laringe y faringe",
]
SITE_SHARES = {
    "Hombres": {
        "Tráquea, bronquios y pulmón": .19, "Próstata": .30, "Mama": .003,
        "Colon y recto": .15, "Estómago": .08, "Cuello del útero": 0,
        "Cuerpo del útero": 0, "Tiroides": .025, "Páncreas": .05,
        "Vejiga urinaria": .07, "Riñón": .04, "Hígado y vías biliares": .05,
        "Ovario": 0, "Laringe y faringe": .042,
    },
    "Mujeres": {
        "Tráquea, bronquios y pulmón": .12, "Próstata": 0, "Mama": .29,
        "Colon y recto": .12, "Estómago": .07, "Cuello del útero": .10,
        "Cuerpo del útero": .07, "Tiroides": .08, "Páncreas": .04,
        "Vejiga urinaria": .025, "Riñón": .025, "Hígado y vías biliares": .025,
        "Ovario": .05, "Laringe y faringe": 0,
    },
}

GENERAL_AGE_RISK = [.01, .01, .012, .02, .035, .055, .085, .13, .21, .34, .53, .76, 1.0, 1.23, 1.42, 1.5, 1.42, 1.2]
SITE_AGE_RISK = {
    "Tráquea, bronquios y pulmón": [.005, .005, .006, .01, .018, .03, .05, .08, .14, .24, .42, .68, .98, 1.25, 1.45, 1.5, 1.38, 1.2],
    "Próstata": [0, 0, 0, 0, .001, .003, .008, .02, .06, .18, .42, .72, 1.0, 1.2, 1.4, 1.55, 1.65, 1.55],
    "Mama": [.005, .005, .008, .015, .03, .06, .11, .2, .38, .58, .78, .92, 1.0, .98, .9, .82, .7, .6],
    "Colon y recto": [.006, .006, .008, .015, .025, .04, .07, .12, .21, .35, .56, .8, 1.05, 1.25, 1.4, 1.45, 1.4, 1.25],
    "Estómago": [.008, .008, .01, .018, .03, .05, .08, .13, .22, .35, .54, .75, .95, 1.15, 1.3, 1.35, 1.3, 1.18],
    "Cuello del útero": [0, .001, .003, .015, .05, .12, .25, .45, .65, .8, .9, .9, .75, .65, .55, .45, .35, .25],
    "Cuerpo del útero": [0, 0, .001, .003, .01, .025, .06, .13, .27, .46, .68, .86, 1.0, 1.12, 1.2, 1.2, 1.1, .95],
    "Tiroides": [.01, .01, .02, .05, .15, .25, .38, .5, .6, .72, .75, .6, .5, .42, .35, .28, .22, .16],
    "Páncreas": [.004, .004, .006, .01, .018, .03, .05, .08, .14, .23, .38, .62, .9, 1.18, 1.42, 1.5, 1.42, 1.2],
    "Vejiga urinaria": [.002, .002, .003, .006, .01, .018, .03, .06, .12, .22, .38, .62, .9, 1.2, 1.45, 1.55, 1.5, 1.35],
    "Riñón": [.01, .01, .015, .025, .045, .07, .12, .19, .28, .4, .55, .72, .9, 1.05, 1.18, 1.2, 1.12, .95],
    "Hígado y vías biliares": [.008, .008, .01, .015, .025, .04, .07, .12, .2, .34, .54, .8, 1.08, 1.3, 1.42, 1.4, 1.28, 1.1],
    "Ovario": [0, .001, .002, .01, .025, .05, .1, .18, .3, .43, .55, .62, .67, .65, .58, .48, .36, .25],
    "Laringe y faringe": [.002, .002, .003, .006, .012, .02, .035, .06, .11, .2, .36, .62, .98, 1.3, 1.5, 1.5, 1.38, 1.18],
}


def age_sex_population(province, year, sex, age_index):
    total = PROVINCE_POPULATIONS[province][YEARS.index(year)]
    male, female = PROVINCE_SEX[province]
    sex_share = male / (male + female) if sex == "Hombres" else female / (male + female)
    national_sex_total = sum(NATIONAL_AGE_SEX[sex])
    return total * sex_share * NATIONAL_AGE_SEX[sex][age_index] / national_sex_total


def apportion(weights, target):
    exact = [weight / sum(weights) * target for weight in weights]
    counts = [int(value) for value in exact]
    remainder = target - sum(counts)
    order = sorted(range(len(exact)), key=lambda index: exact[index] - counts[index], reverse=True)
    for index in order[:remainder]:
        counts[index] += 1
    return counts


def main():
    standard_source = HERE / "tasas_sinteticas.csv"
    with standard_source.open(encoding="utf-8", newline="") as source:
        standard_weights = {row["age_group"]: int(row["standard_weight"]) for row in csv.DictReader(source)}

    records = []
    for year in YEARS:
        cells = []
        cell_weights = []
        for province in PROVINCE_POPULATIONS:
            for sex in ("Mujeres", "Hombres"):
                for age_index, age in enumerate(AGES):
                    population = max(1, round(age_sex_population(province, year, sex, age_index)))
                    for site in SITES:
                        weight = SITE_SHARES[sex][site] * SITE_AGE_RISK[site][age_index]
                        cells.append((province, sex, age, site, population))
                        cell_weights.append(population * weight)
        tumor_counts = apportion(cell_weights, ANNUAL_CASE_TARGETS[year])
        for (province, sex, age, site, population), tumors in zip(cells, tumor_counts):
            multiple_primary_share = .055 if sex == "Hombres" else .045
            persons = tumors - round(tumors * multiple_primary_share)
            records.append({
                "period": year,
                "territory_id": id_for("territory_id", province),
                "sex_id": id_for("sex_id", sex),
                "age_group_id": id_for("age_group_id", age),
                "site_id": id_for("site_id", site),
                "tumor_count": tumors,
                "person_count": persons,
                "population": population,
                "standard_weight": standard_weights[age],
                "source_is_synthetic": "TRUE",
                "population_basis": "ONEI 2024 province totals; modeled age-sex allocation",
            })

    target = HERE / "consulta_demo_sintetica.csv"
    with target.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    print(f"Regenerated {target.name}: {len(records)} aggregate cells over {len(YEARS)} synthetic case periods.")


if __name__ == "__main__":
    main()
