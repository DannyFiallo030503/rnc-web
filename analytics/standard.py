"""Candidate standard population used by the synthetic prototype only."""

# Candidate Segi–Doll weights. Keep one source for validation, calculations and
# release metadata. This is not an institutionally validated RNC method.
AGE_STANDARD_WEIGHTS = dict(
    zip(
        [f"{n}-{n + 4}" for n in range(0, 85, 5)] + ["85+"],
        [
            12000,
            10000,
            9000,
            9000,
            8000,
            8000,
            6000,
            6000,
            6000,
            6000,
            5000,
            4000,
            4000,
            3000,
            2000,
            1000,
            500,
            500,
        ],
    )
)
AGE_STANDARD_ID = "segi-doll-candidate-v1"
