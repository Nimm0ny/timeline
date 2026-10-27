import json
from pathlib import Path
import re

from pydantic import ValidationError

from backend.app.schemas.ui_contracts import UiContractMap


ROOT_DIR = Path(__file__).resolve().parents[1]
UI_CONTRACTS_PATH = ROOT_DIR / "ui" / "contracts.json"


def load_ui_contracts() -> tuple[UiContractMap | None, dict | None]:
    try:
        payload = json.loads(UI_CONTRACTS_PATH.read_text(encoding="utf-8"))
        return UiContractMap.model_validate(payload), None
    except FileNotFoundError:
        return None, {
            "code": "ui_contracts_missing",
            "message": "UI contract registry was not found.",
            "nextAction": "Create ui/contracts.json from the UI contract schema, then run ui check.",
            "details": {"path": str(UI_CONTRACTS_PATH)},
        }
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        return None, {
            "code": "ui_contract_invalid",
            "message": "UI contract registry is unreadable or does not match its schema.",
            "nextAction": "Fix the reported registry error and rerun ui check.",
            "details": {"reason": str(exc), "path": str(UI_CONTRACTS_PATH)},
        }


def validate_ui_contracts(feature_map: dict, *, feature_id: str | None = None) -> dict:
    catalog, error = load_ui_contracts()
    if error:
        return {"status": "failed", "problems": [error], "coverageGaps": []}

    features = {feature["id"]: feature for feature in feature_map.get("features", [])}
    contracts = catalog.model_dump(by_alias=True)["contracts"]
    contracts_by_id = {contract["id"]: contract for contract in contracts}
    problems: list[dict] = []
    coverage_gaps: list[dict] = []
    scenario_gaps: list[dict] = []

    if len(contracts_by_id) != len(contracts):
        problems.append({"code": "duplicate_ui_contract_id"})

    selected_features = (
        {feature_id: features.get(feature_id)} if feature_id else features
    )
    if feature_id and selected_features.get(feature_id) is not None:
        selected_ui = selected_features[feature_id].get("ui", {})
        if selected_ui.get("hasWebEntry", True) is False and not selected_ui.get("contractIds", []):
            return {
                "status": "not_applicable",
                "contractsChecked": 0,
                "contractIds": [],
                "problems": [],
                "coverageGaps": [],
            }
    for current_id, feature in selected_features.items():
        if feature is None:
            problems.append({"code": "unknown_feature", "featureId": current_id})
            continue
        registered_ids = feature.get("ui", {}).get("contractIds", [])
        has_web_entry = feature.get("ui", {}).get("hasWebEntry", True)
        if not has_web_entry and registered_ids:
            problems.append({"code": "api_only_feature_has_ui_contract", "featureId": current_id})
        if has_web_entry and not registered_ids:
            coverage_gaps.append({"code": "feature_has_no_ui_contract", "featureId": current_id})
        for contract_id in registered_ids:
            contract = contracts_by_id.get(contract_id)
            if contract is None:
                problems.append({
                    "code": "feature_contract_missing",
                    "featureId": current_id,
                    "contractId": contract_id,
                })
            elif contract["featureId"] != current_id:
                problems.append({
                    "code": "feature_contract_owner_mismatch",
                    "featureId": current_id,
                    "contractId": contract_id,
                    "contractFeatureId": contract["featureId"],
                })

    selected_contracts = [
        contract for contract in contracts
        if feature_id is None or contract["featureId"] == feature_id
    ]
    scenario_ids: set[str] = set()
    for contract in selected_contracts:
        feature = features.get(contract["featureId"])
        if feature is None:
            problems.append({"code": "contract_feature_missing", "contractId": contract["id"]})
            continue
        if not feature.get("ui", {}).get("hasWebEntry", True):
            problems.append({"code": "contract_feature_has_no_web_entry", "contractId": contract["id"], "featureId": contract["featureId"]})
        if contract["id"] not in feature.get("ui", {}).get("contractIds", []):
            problems.append({
                "code": "contract_not_bound_to_feature",
                "contractId": contract["id"],
                "featureId": contract["featureId"],
            })
        if not contract["route"].startswith("/") or ".." in contract["route"].split("/"):
            problems.append({"code": "invalid_ui_contract_route", "contractId": contract["id"], "route": contract["route"]})

        operations = {
            operation["operationId"]: operation
            for operation in feature.get("api", [])
        }
        for operation_id in contract["operationIds"]:
            operation = operations.get(operation_id)
            if operation is None:
                problems.append({
                    "code": "contract_operation_missing",
                    "contractId": contract["id"],
                    "operationId": operation_id,
                })

        variants = contract["variants"]
        for variant in variants:
            if variant["maxWidth"] is not None and variant["maxWidth"] < variant["minWidth"]:
                problems.append({
                    "code": "invalid_ui_variant_range",
                    "contractId": contract["id"],
                    "variantId": variant["id"],
                })
        for index, variant in enumerate(variants):
            upper = variant["maxWidth"] if variant["maxWidth"] is not None else 3840
            for other in variants[index + 1:]:
                other_upper = other["maxWidth"] if other["maxWidth"] is not None else 3840
                if max(variant["minWidth"], other["minWidth"]) <= min(upper, other_upper):
                    problems.append({
                        "code": "overlapping_ui_variants",
                        "contractId": contract["id"],
                        "variantIds": [variant["id"], other["id"]],
                    })

        for source_path in contract["sourcePaths"]:
            if source_path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", source_path):
                problems.append({"code": "ui_source_path_not_relative", "contractId": contract["id"], "path": source_path})
                continue
            resolved = (ROOT_DIR / source_path).resolve()
            try:
                resolved.relative_to(ROOT_DIR.resolve())
            except ValueError:
                problems.append({"code": "ui_source_path_outside_repository", "contractId": contract["id"], "path": source_path})
                continue
            if not resolved.is_file():
                problems.append({"code": "ui_source_path_missing", "contractId": contract["id"], "path": source_path})

        for scenario in contract["scenarios"]:
            if scenario["id"] in scenario_ids:
                problems.append({"code": "duplicate_ui_scenario_id", "scenarioId": scenario["id"]})
            scenario_ids.add(scenario["id"])
            if scenario["targetState"] not in contract["states"]:
                problems.append({
                    "code": "scenario_state_not_declared",
                    "contractId": contract["id"],
                    "scenarioId": scenario["id"],
                    "state": scenario["targetState"],
                })
            operation_ids = set(contract["operationIds"])
            if scenario["readback"]["operationId"] not in operation_ids:
                problems.append({
                    "code": "readback_operation_not_declared",
                    "contractId": contract["id"],
                    "scenarioId": scenario["id"],
                    "operationId": scenario["readback"]["operationId"],
                })
            readback_operation = operations.get(scenario["readback"]["operationId"])
            if readback_operation and (readback_operation.get("readOnly") is not True or readback_operation.get("method") != "GET"):
                problems.append({
                    "code": "ui_readback_must_be_read_only_get",
                    "contractId": contract["id"],
                    "scenarioId": scenario["id"],
                    "operationId": scenario["readback"]["operationId"],
                })
            for assertion in scenario["assertions"]:
                if assertion["kind"] == "operation-observed" and assertion["operationId"] not in operation_ids:
                    problems.append({
                        "code": "assertion_operation_not_declared",
                        "contractId": contract["id"],
                        "scenarioId": scenario["id"],
                        "operationId": assertion["operationId"],
                    })
                elif assertion["kind"] == "operation-observed":
                    operation = operations.get(assertion["operationId"])
                    if operation and (operation.get("readOnly") is not True or operation.get("method") != "GET"):
                        problems.append({
                            "code": "observed_ui_operation_must_be_read_only_get",
                            "contractId": contract["id"],
                            "scenarioId": scenario["id"],
                            "operationId": assertion["operationId"],
                        })
            for action in scenario["actions"]:
                if action["action"] == "expect-visible" and not (action.get("name") or action.get("textFrom")):
                    problems.append({
                        "code": "ui_action_missing_target",
                        "contractId": contract["id"],
                        "scenarioId": scenario["id"],
                    })

        if not contract["scenarios"]:
            scenario_gaps.append({
                "code": "feature_has_no_executable_ui_scenario",
                "featureId": contract["featureId"],
                "contractId": contract["id"],
            })

    status = "failed" if problems else "partial" if coverage_gaps else "passed"
    return {
        "status": status,
        "contractsChecked": len(selected_contracts),
        "contractIds": [contract["id"] for contract in selected_contracts],
        "problems": problems,
        "coverageGaps": coverage_gaps,
        "scenarioCoverage": "partial" if scenario_gaps else "complete",
        "scenarioGaps": scenario_gaps,
    }


def find_ui_scenario(catalog: UiContractMap, scenario_id: str) -> tuple[dict | None, dict | None]:
    for contract in catalog.model_dump(by_alias=True)["contracts"]:
        for scenario in contract["scenarios"]:
            if scenario["id"] == scenario_id:
                return contract, scenario
    return None, None
