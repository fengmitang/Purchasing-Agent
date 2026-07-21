from decimal import Decimal

from scripts.seed_development_data import (
    CURATED_COUNT,
    PRODUCTS,
    REQUIREMENT_COUNT,
    build_employees,
    build_requirement_specs,
    generation_summary,
)


def test_generation_summary_has_expected_dataset_size() -> None:
    summary = generation_summary()

    assert summary["requirements"] == 500
    assert summary["curated_requirements"] == 240
    assert summary["simulated_requirements"] == 260
    assert summary["employees"] == 80
    assert summary["orders"] == 355


def test_generated_requirements_are_complete_and_financially_consistent() -> None:
    requirements = build_requirement_specs()

    assert len(requirements) == REQUIREMENT_COUNT
    assert sum(row["source_kind"] == "curated" for row in requirements) == CURATED_COUNT
    assert len({row["source_reference"] for row in requirements}) == REQUIREMENT_COUNT
    for row in requirements:
        assert row["reason"]
        assert row["location"]
        assert isinstance(row["quantity"], Decimal) and row["quantity"] > 0
        assert isinstance(row["unit_price"], Decimal) and row["unit_price"] > 0
        assert row["total_amount"] == row["quantity"] * row["unit_price"]


def test_revision_links_and_synthetic_markers_are_valid() -> None:
    requirements = build_requirement_specs()
    employees = build_employees()

    assert all(product[4].startswith("DEV-") for product in PRODUCTS)
    assert all(str(employee["employee_no"]).startswith("DEV-") for employee in employees)
    assert all(str(employee["name"]).endswith("（测试）") for employee in employees)

    revised = [row for row in requirements if row["revision_no"] == 2]
    assert len(revised) == 30
    for row in revised:
        previous = requirements[int(row["previous_index"])]
        assert previous["status"] == "REJECTED"
        assert row["requester_index"] == previous["requester_index"]
        assert row["template_index"] == previous["template_index"]
