"""Battery pipeline: prices, a price forecast and an exact battery optimiser for the GB Battery Watch Power BI report.

Run with ``python -m pipeline.battery.run``. It is independent of the dbt warehouse: every input is
re-fetchable from public APIs, and its state lives in the published ``powerbi-data`` branch.
"""
