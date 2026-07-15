from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import yaml


DEFAULT_MATRIX = Path(__file__).with_name("sources.yaml")
DEFAULT_REGISTRY = Path(__file__).with_name("sources.json")
EXPECTED_DIRECTORIES = {
    "central_departments": "https://www.gov.cn/home/2023-03/29/content_5748953.htm",
    "local_governments": "https://www.gov.cn/home/2023-03/29/content_5748954.htm",
}
EXPECTED_CENTRAL_IDS = {
    "central_ccdi_nsc_documents", "central_cpc_rules", "central_cppcc_documents",
    "central_national_law_database", "central_npc_reports", "central_qstheory",
    "central_state_council_documents", "central_state_council_gazette",
    "central_supreme_court_documents", "central_supreme_procuratorate_documents",
}
EXPECTED_CENTRAL_PORTALS = {
    "central_state_council_documents": "https://www.gov.cn/",
    "central_state_council_gazette": "https://www.gov.cn/",
    "central_cpc_rules": "https://www.12371.cn/",
    "central_npc_reports": "http://www.npc.gov.cn/",
    "central_national_law_database": "https://flk.npc.gov.cn/",
    "central_cppcc_documents": "https://www.cppcc.gov.cn/",
    "central_ccdi_nsc_documents": "https://www.ccdi.gov.cn/",
    "central_supreme_court_documents": "https://www.court.gov.cn/",
    "central_supreme_procuratorate_documents": "https://www.spp.gov.cn/",
    "central_qstheory": "https://www.qstheory.cn/",
}
EXPECTED_PROVINCIAL_PORTALS = {
    "CN-BJ": "http://www.beijing.gov.cn/", "CN-TJ": "https://www.tj.gov.cn/",
    "CN-HE": "http://www.hebei.gov.cn/", "CN-SX": "http://www.shanxi.gov.cn/",
    "CN-NM": "https://www.nmg.gov.cn/", "CN-LN": "http://www.ln.gov.cn/",
    "CN-JL": "http://www.jl.gov.cn/", "CN-HL": "https://www.hlj.gov.cn/",
    "CN-SH": "https://www.shanghai.gov.cn/", "CN-JS": "http://www.jiangsu.gov.cn/",
    "CN-ZJ": "https://www.zj.gov.cn/", "CN-AH": "https://www.ah.gov.cn/",
    "CN-FJ": "http://www.fujian.gov.cn/", "CN-JX": "http://www.jiangxi.gov.cn/",
    "CN-SD": "http://www.shandong.gov.cn/", "CN-HA": "https://www.henan.gov.cn/",
    "CN-HB": "http://www.hubei.gov.cn/", "CN-HN": "http://www.hunan.gov.cn/",
    "CN-GD": "http://www.gd.gov.cn/", "CN-GX": "http://www.gxzf.gov.cn/",
    "CN-HI": "https://www.hainan.gov.cn/", "CN-CQ": "http://www.cq.gov.cn/",
    "CN-SC": "https://www.sc.gov.cn/", "CN-GZ": "http://www.guizhou.gov.cn/",
    "CN-YN": "https://www.yn.gov.cn/", "CN-XZ": "http://www.xizang.gov.cn/",
    "CN-SN": "http://www.shaanxi.gov.cn/", "CN-GS": "http://www.gansu.gov.cn/",
    "CN-QH": "http://www.qinghai.gov.cn/", "CN-NX": "https://www.nx.gov.cn/",
    "CN-XJ": "http://www.xinjiang.gov.cn/", "CN-XJ-BT": "http://www.xjbt.gov.cn/",
}
EXPECTED_PROVINCIAL_CODES = set(EXPECTED_PROVINCIAL_PORTALS)
LIFECYCLE_STATES = {"planned", "production", "external"}
FACET_STATES = {"pending", "partial", "verified", "not_applicable"}
EXPECTED_RUNTIME_CONTENT_COVERAGE = {
    "gov_cn_department_docs": ["policy_document"],
    "party_rules": ["party_rule"],
    "npc_reports": ["work_report"],
    "national_law_database": ["law_regulation"],
    "beijing_government_docs": ["policy_document"],
    "guangdong_government_docs": ["policy_document"],
    "jiangsu_government_docs": ["policy_document"],
}
COLLECTION_FACETS = ("list", "article", "attachments", "pagination")


def _is_url(value: object) -> bool:
    return isinstance(value, str) and urlsplit(value).scheme in {"http", "https"} and bool(urlsplit(value).netloc)


def _validate_source(source: dict) -> list[str]:
    source_id = str(source.get("id") or "<missing-id>")
    errors = []
    if source.get("tier") != "S0" or source.get("level") not in {"central", "provincial"}:
        errors.append(f"{source_id}: tier must be S0 and level must be central or provincial")
    if source.get("lifecycle") not in LIFECYCLE_STATES:
        errors.append(f"{source_id}: invalid lifecycle")
    for key in ("portal_url", "provenance_url"):
        if not _is_url(source.get(key)):
            errors.append(f"{source_id}: {key} must be an absolute HTTP(S) URL")
    collection = source.get("collection")
    if not isinstance(collection, dict):
        return errors + [f"{source_id}: collection must be an object"]
    if collection.get("list_url") is not None and not _is_url(collection.get("list_url")):
        errors.append(f"{source_id}: collection.list_url must be null or an absolute HTTP(S) URL")
    for facet in COLLECTION_FACETS:
        if collection.get(facet) not in FACET_STATES:
            errors.append(f"{source_id}: invalid collection.{facet} state")
    runtime_id = source.get("runtime_registry_id")
    lifecycle = source.get("lifecycle")
    if lifecycle == "production" and not runtime_id:
        errors.append(f"{source_id}: production source requires runtime_registry_id")
    if lifecycle == "production" and source.get("owner") != "political_ingestion":
        errors.append(f"{source_id}: production source must be owned by political_ingestion")
    if lifecycle == "production" and any(collection.get(facet) in {"pending", "not_applicable"} for facet in COLLECTION_FACETS):
        errors.append(f"{source_id}: production collection facets must be verified or partial")
    if source.get("lifecycle") != "production" and runtime_id:
        errors.append(f"{source_id}: non-production source cannot have runtime_registry_id")
    if lifecycle == "external" and (
        source.get("owner") != "qstheory"
        or any(collection.get(facet) != "not_applicable" for facet in COLLECTION_FACETS)
    ):
        errors.append(f"{source_id}: external source must use qstheory ownership and not_applicable facets")
    return errors


def _validate_inventory(matrix: dict, sources: list[dict]) -> list[str]:
    errors = []
    ids = [source.get("id") for source in sources]
    if any(not source_id for source_id in ids) or len(ids) != len(set(ids)):
        errors.append("matrix source ids must be present and unique")
    central_ids = {source.get("id") for source in sources if source.get("level") == "central"}
    provincial_codes = [source.get("region_code") for source in sources if source.get("level") == "provincial"]
    if central_ids != EXPECTED_CENTRAL_IDS:
        errors.append("central S0 inventory does not match the required source set")
    if set(provincial_codes) != EXPECTED_PROVINCIAL_CODES or len(provincial_codes) != len(set(provincial_codes)):
        errors.append("provincial inventory must contain each of the required 32 region codes exactly once")
    central_portals = {source.get("id"): source.get("portal_url") for source in sources if source.get("level") == "central"}
    provincial_portals = {source.get("region_code"): source.get("portal_url") for source in sources if source.get("level") == "provincial"}
    if central_portals != EXPECTED_CENTRAL_PORTALS:
        errors.append("central source portals do not match the verified baseline")
    if provincial_portals != EXPECTED_PROVINCIAL_PORTALS:
        errors.append("provincial region-to-portal mapping does not match the State Council directory baseline")
    if len(set(provincial_portals.values())) != len(provincial_portals):
        errors.append("provincial portal URLs must be unique")
    if matrix.get("authoritative_directories") != EXPECTED_DIRECTORIES:
        errors.append("authoritative_directories do not match the verified baseline")
    scope = matrix.get("scope", {})
    if scope.get("central_s0_expected") != len(EXPECTED_CENTRAL_IDS):
        errors.append("scope.central_s0_expected is inconsistent")
    if scope.get("provincial_expected") != len(EXPECTED_PROVINCIAL_CODES):
        errors.append("scope.provincial_expected is inconsistent")
    return errors


def _validate_registry(sources: list[dict], registry: dict) -> list[str]:
    matrix_runtime_ids = [source.get("runtime_registry_id") for source in sources if source.get("lifecycle") == "production"]
    registry_ids = [source.get("id") for source in registry.get("sources", [])]
    errors = []
    if any(not runtime_id for runtime_id in registry_ids) or len(registry_ids) != len(set(registry_ids)):
        errors.append("sources.json source ids must be present and unique")
    if len(matrix_runtime_ids) != len(set(matrix_runtime_ids)):
        errors.append("production runtime_registry_id values must be unique")
    if set(matrix_runtime_ids) != set(registry_ids):
        errors.append("production matrix mappings must exactly match sources.json")
    if any(not source.get("enabled") for source in registry.get("sources", [])):
        errors.append("all sources.json entries represented as production must be enabled")
    registry_by_id = {source.get("id"): source for source in registry.get("sources", [])}
    for source in sources:
        runtime_id = source.get("runtime_registry_id")
        if runtime_id and source["collection"].get("list_url") != registry_by_id.get(runtime_id, {}).get("list_url"):
            errors.append(f"{source['id']}: production list_url has drifted from sources.json")
    return errors


def _validate_content(matrix: dict, sources: list[dict], registry: dict) -> list[str]:
    taxonomy = set(matrix.get("content_taxonomy", []))
    targets = matrix.get("content_targets", {})
    coverage = matrix.get("runtime_content_coverage", {})
    errors = []
    central_ids = {source.get("id") for source in sources if source.get("level") == "central"}
    if set(targets) != central_ids | {"provincial_default"}:
        errors.append("content_targets must cover every central source and provincial_default")
    if set(coverage) != {source.get("id") for source in registry.get("sources", [])}:
        errors.append("runtime_content_coverage must exactly match sources.json")
    if coverage != EXPECTED_RUNTIME_CONTENT_COVERAGE:
        errors.append("runtime_content_coverage does not match the verified adapter baseline")
    for target_id, content_types in targets.items():
        if not content_types or not set(content_types) <= taxonomy:
            errors.append(f"{target_id}: invalid content target")
    source_by_runtime_id = {source.get("runtime_registry_id"): source for source in sources}
    for runtime_id, content_types in coverage.items():
        source = source_by_runtime_id.get(runtime_id, {})
        target = targets.get(source.get("id"), targets.get("provincial_default", []))
        if not content_types or not set(content_types) <= set(target):
            errors.append(f"{runtime_id}: runtime content exceeds its source target")
    return errors


def validate_matrix(matrix: dict, registry: dict) -> None:
    errors = []
    if matrix.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    for key in ("scope", "authoritative_directories", "states", "content_targets", "runtime_content_coverage"):
        if not isinstance(matrix.get(key), dict):
            errors.append(f"{key} must be an object")
    if errors:
        raise ValueError("Invalid political source matrix:\n- " + "\n- ".join(errors))
    sources = matrix.get("sources")
    if not isinstance(sources, list):
        raise ValueError("sources must be a list")
    if any(not isinstance(source, dict) for source in sources):
        raise ValueError("Invalid political source matrix:\n- every source must be an object")
    structural_errors = []
    for index, source in enumerate(sources):
        if not source.get("id"):
            structural_errors.append(f"sources[{index}]: id is required")
        if source.get("level") not in {"central", "provincial"}:
            structural_errors.append(f"sources[{index}]: valid level is required")
        if source.get("level") == "provincial" and not source.get("region_code"):
            structural_errors.append(f"sources[{index}]: provincial region_code is required")
        if not isinstance(source.get("collection"), dict):
            structural_errors.append(f"sources[{index}]: collection object is required")
    if structural_errors:
        raise ValueError("Invalid political source matrix:\n- " + "\n- ".join(structural_errors))
    states = matrix.get("states", {})
    if set(states.get("lifecycle", [])) != LIFECYCLE_STATES or len(states.get("lifecycle", [])) != len(LIFECYCLE_STATES):
        errors.append("states.lifecycle must exactly match the fixed lifecycle vocabulary")
    if set(states.get("facet", [])) != FACET_STATES or len(states.get("facet", [])) != len(FACET_STATES):
        errors.append("states.facet must exactly match the fixed facet vocabulary")
    errors.extend(_validate_inventory(matrix, sources))
    for source in sources:
        errors.extend(_validate_source(source))
    errors.extend(_validate_registry(sources, registry))
    errors.extend(_validate_content(matrix, sources, registry))
    if errors:
        raise ValueError("Invalid political source matrix:\n- " + "\n- ".join(errors))


def load_matrix(matrix_path: Path = DEFAULT_MATRIX, registry_path: Path = DEFAULT_REGISTRY) -> dict:
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(matrix, dict):
        raise ValueError("source matrix root must be an object")
    validate_matrix(matrix, registry)
    return matrix


def matrix_summary(matrix: dict) -> dict[str, int]:
    sources = matrix["sources"]
    return {
        "total": len(sources),
        "central": sum(source["level"] == "central" for source in sources),
        "provincial": sum(source["level"] == "provincial" for source in sources),
        "production": sum(source["lifecycle"] == "production" for source in sources),
        "planned": sum(source["lifecycle"] == "planned" for source in sources),
        "external": sum(source["lifecycle"] == "external" for source in sources),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the political source planning matrix")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    print(json.dumps(matrix_summary(load_matrix(args.matrix, args.registry)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
