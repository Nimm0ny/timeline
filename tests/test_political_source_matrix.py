from copy import deepcopy
import json

import pytest

from tools.political_ingestion import source_matrix


def runtime_registry():
    return json.loads(source_matrix.DEFAULT_REGISTRY.read_text(encoding="utf-8"))


def test_default_matrix_has_complete_s0_inventory():
    matrix = source_matrix.load_matrix()

    assert source_matrix.matrix_summary(matrix) == {
        "total": 42,
        "central": 10,
        "provincial": 32,
        "production": 7,
        "planned": 34,
        "external": 1,
    }
    assert {
        source["region_code"] for source in matrix["sources"] if source["level"] == "provincial"
    } == source_matrix.EXPECTED_PROVINCIAL_CODES


def test_production_sources_exactly_match_runtime_registry():
    matrix = source_matrix.load_matrix()
    mapped = {
        source["runtime_registry_id"]
        for source in matrix["sources"]
        if source["lifecycle"] == "production"
    }

    assert mapped == {source["id"] for source in runtime_registry()["sources"]}
    qstheory = next(source for source in matrix["sources"] if source["id"] == "central_qstheory")
    assert qstheory["owner"] == "qstheory"
    assert qstheory["lifecycle"] == "external"
    assert matrix["content_targets"]["provincial_default"] == [
        "policy_document", "work_report", "announcement", "public_consultation", "policy_interpretation",
    ]
    assert set(matrix["runtime_content_coverage"]) == mapped


def test_matrix_rejects_missing_province():
    matrix = deepcopy(source_matrix.load_matrix())
    matrix["sources"] = [source for source in matrix["sources"] if source.get("region_code") != "CN-XJ-BT"]

    with pytest.raises(ValueError, match="required 32 region codes"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_runtime_drift():
    matrix = deepcopy(source_matrix.load_matrix())
    source = next(item for item in matrix["sources"] if item["lifecycle"] == "production")
    source["runtime_registry_id"] = "missing_runtime_source"

    with pytest.raises(ValueError, match="exactly match sources.json"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_runtime_url_drift():
    matrix = deepcopy(source_matrix.load_matrix())
    registry = runtime_registry()
    registry["sources"][0]["list_url"] = "https://example.gov.cn/drifted"

    with pytest.raises(ValueError, match="production list_url has drifted"):
        source_matrix.validate_matrix(matrix, registry)


def test_matrix_rejects_swapped_official_portals_and_missing_directory():
    matrix = deepcopy(source_matrix.load_matrix())
    beijing = next(source for source in matrix["sources"] if source.get("region_code") == "CN-BJ")
    tianjin = next(source for source in matrix["sources"] if source.get("region_code") == "CN-TJ")
    beijing["portal_url"], tianjin["portal_url"] = tianjin["portal_url"], beijing["portal_url"]
    matrix["authoritative_directories"].pop("local_governments")

    with pytest.raises(ValueError, match="region-to-portal mapping") as exc_info:
        source_matrix.validate_matrix(matrix, runtime_registry())
    assert "authoritative_directories" in str(exc_info.value)


def test_matrix_rejects_unknown_collection_state():
    matrix = deepcopy(source_matrix.load_matrix())
    matrix["sources"][0]["collection"]["pagination"] = "assumed"

    with pytest.raises(ValueError, match="invalid collection.pagination state"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_self_extended_state_vocabulary():
    matrix = deepcopy(source_matrix.load_matrix())
    matrix["states"]["facet"].append("assumed")
    matrix["sources"][0]["collection"]["pagination"] = "assumed"

    with pytest.raises(ValueError, match="fixed facet vocabulary"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_unverified_production_facets():
    matrix = deepcopy(source_matrix.load_matrix())
    matrix["sources"][0]["collection"]["article"] = "pending"

    with pytest.raises(ValueError, match="must be verified or partial"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_runtime_content_outside_target():
    matrix = deepcopy(source_matrix.load_matrix())
    matrix["runtime_content_coverage"]["npc_reports"] = ["announcement"]

    with pytest.raises(ValueError, match="runtime content exceeds its source target"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_runtime_content_inflated_within_target():
    matrix = deepcopy(source_matrix.load_matrix())
    matrix["runtime_content_coverage"]["beijing_government_docs"] = [
        "policy_document", "work_report", "announcement", "public_consultation", "policy_interpretation",
    ]

    with pytest.raises(ValueError, match="verified adapter baseline"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_non_object_source_with_diagnostic_error():
    matrix = deepcopy(source_matrix.load_matrix())
    matrix["sources"].append("invalid")

    with pytest.raises(ValueError, match="every source must be an object"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_missing_required_source_fields():
    matrix = deepcopy(source_matrix.load_matrix())
    matrix["sources"][0].pop("id")

    with pytest.raises(ValueError, match="id is required"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_invalid_external_contract():
    matrix = deepcopy(source_matrix.load_matrix())
    qstheory = next(source for source in matrix["sources"] if source["id"] == "central_qstheory")
    qstheory["owner"] = "political_ingestion"
    qstheory["collection"]["article"] = "verified"

    with pytest.raises(ValueError, match="external source must use qstheory ownership"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_malformed_top_level_objects():
    matrix = deepcopy(source_matrix.load_matrix())
    matrix["states"] = []

    with pytest.raises(ValueError, match="states must be an object"):
        source_matrix.validate_matrix(matrix, runtime_registry())


def test_matrix_rejects_duplicate_runtime_registry_ids():
    matrix = deepcopy(source_matrix.load_matrix())
    registry = runtime_registry()
    registry["sources"].append(deepcopy(registry["sources"][0]))

    with pytest.raises(ValueError, match="sources.json source ids must be present and unique"):
        source_matrix.validate_matrix(matrix, registry)
