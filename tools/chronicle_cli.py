"""Feature Map, API diagnostics, and restricted Chronicle CLI operations."""

import argparse
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.app.schemas.common import (
    ContractModel,
    EmptyInput,
    FeatureMapOut,
    FeatureOut,
    NoteListInput,
    NoteListQuery,
    NoteListScenarioInput,
    NoteOut,
    NotePageOut,
    NoteReadScenarioInput,
    NoteSearchInput,
    NoteSearchItem,
    NoteSearchScenarioInput,
    TopicOut,
    TopicReadInput,
)
import backend.app.schemas.common as api_schemas
from backend.app.features import list_features as local_feature_map
from backend.app.schemas.ui_contracts import UiSearchScenarioInput
from tools.ui_contracts import find_ui_scenario, load_ui_contracts, validate_ui_contracts

ROOT_URL_DEFAULT = "http://127.0.0.1:8000"
DEV_MANAGER_PATH = ROOT_DIR / "tools" / "chronicle_dev_manager.py"
DEBUG_ENABLED = False


class OperationCallInput(ContractModel):
    path: dict[str, object] = Field(default_factory=dict)
    query: dict[str, object] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: object | None = None
    file: str | None = None


SCHEMA_MODELS = {
    name: value
    for name, value in vars(api_schemas).items()
    if isinstance(value, type) and issubclass(value, BaseModel)
}


class JsonArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        options = []
        commands = []
        for action in self._actions:
            if isinstance(action, argparse._SubParsersAction):
                help_by_name = {choice.dest: choice.help for choice in action._choices_actions}
                commands = [
                    {"name": name, "help": help_by_name.get(name) or parser.description}
                    for name, parser in action.choices.items()
                ]
                continue
            if isinstance(action, argparse._HelpAction):
                continue
            item = {
                "name": action.dest,
                "flags": action.option_strings,
                "required": bool(getattr(action, "required", False)),
                "help": action.help,
            }
            if action.default is not argparse.SUPPRESS and action.default is not None:
                item["default"] = action.default
            if action.choices is not None:
                item["choices"] = list(action.choices)
            if action.type is not None:
                item["type"] = getattr(action.type, "__name__", str(action.type))
            options.append(item)
        return json.dumps({
            "status": "succeeded",
            "command": self.prog,
            "description": self.description,
            "usage": self.format_usage().strip(),
            "arguments": options,
            "commands": commands,
        }, ensure_ascii=False, separators=(",", ":")) + "\n"

    def error(self, message: str) -> None:
        error = {
            "code": "invalid_arguments",
            "message": "CLI 参数不符合命令 schema。",
            "nextAction": "查看 --help，并按 Feature Map 中的场景输入 schema 重试。",
            "details": message,
        }
        emit({"status": "failed", "failure": error, "nextAction": error["nextAction"]}, 2)
        raise SystemExit(2)


def emit(payload: dict, exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


def fail(error: dict, *, feature: str | None = None, scenario: str | None = None, exit_code: int = 1) -> int:
    result = {"status": "failed", "failure": error, "nextAction": error.get("nextAction")}
    if feature:
        result["feature"] = feature
    if scenario:
        result["scenario"] = scenario
    return emit(result, exit_code)


def validation_details(exc: ValidationError) -> list[dict[str, str]]:
    return [
        {
            "field": ".".join(str(part) for part in item.get("loc", ())),
            "message": item.get("msg", "Invalid value"),
            "rule": item.get("type", "value_error"),
        }
        for item in exc.errors()
    ]


def validate_input(model, values: dict) -> tuple[object | None, dict | None]:
    try:
        validator = getattr(model, "model_validate", None)
        instance = validator(values) if validator else model.parse_obj(values)
        return instance, None
    except ValidationError as exc:
        return None, {
            "code": "invalid_arguments",
            "message": "CLI 参数不符合共享请求 schema。",
            "nextAction": "修正返回的字段错误后重试。",
            "details": validation_details(exc),
        }


def validate_response(model, payload) -> tuple[object | None, dict | None]:
    try:
        validator = getattr(model, "model_validate", None)
        instance = validator(payload) if validator else model.parse_obj(payload)
        return instance, None
    except ValidationError as exc:
        return None, {
            "code": "api_contract_mismatch",
            "message": "API 响应与共享 schema 不匹配。",
            "nextAction": "停止依赖该响应，检查服务版本和 OpenAPI schema。",
            "details": validation_details(exc),
        }


def validate_array_response(model, payload) -> tuple[list[dict] | None, dict | None]:
    if not isinstance(payload, list):
        return None, {
            "code": "api_contract_mismatch",
            "message": "API 响应不是预期的数组。",
            "nextAction": "检查服务版本和 OpenAPI schema。",
        }
    values = []
    for item in payload:
        instance, error = validate_response(model, item)
        if error:
            return None, error
        values.append(model_data(instance))
    return values, None


def model_data(instance, *, exclude_none: bool = False, exclude_unset: bool = False) -> dict:
    dumper = getattr(instance, "model_dump", None)
    if dumper:
        return dumper(by_alias=True, exclude_none=exclude_none, exclude_unset=exclude_unset)
    return instance.dict(by_alias=True, exclude_none=exclude_none, exclude_unset=exclude_unset)


def trace(message: str) -> None:
    if DEBUG_ENABLED:
        sys.stderr.write(f"chronicle: {message}\n")


def dev_root() -> Path:
    project_key = hashlib.sha256(str(ROOT_DIR).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "chronicle-cli" / project_key


def load_latest_dev_manifest(run_id: str | None = None) -> tuple[Path | None, dict | None, dict | None]:
    root = dev_root()
    try:
        if run_id is None:
            pointer = root / "latest.txt"
            if not pointer.is_file():
                return None, None, None
            run_id = pointer.read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("Invalid managed session id")
        manifest_path = root / run_id / "session.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return None, None, {
            "code": "dev_manifest_invalid",
            "message": "CLI development session metadata is unreadable.",
            "nextAction": "Run dev up to create a new isolated session; existing processes will not be stopped.",
            "details": {"reason": str(exc)},
        }
    if not isinstance(manifest, dict) or manifest.get("runId") != run_id:
        return None, None, {
            "code": "dev_manifest_invalid",
            "message": "CLI development session metadata does not match its directory.",
            "nextAction": "Run dev up to create a new isolated session; existing processes will not be stopped.",
        }
    return manifest_path, manifest, None


def dev_manager_status(manifest: dict) -> tuple[dict | None, dict | None]:
    try:
        port = int(manifest["managerPort"])
        token = str(manifest["token"])
    except (KeyError, TypeError, ValueError):
        return None, {
            "code": "dev_owner_unavailable",
            "message": "The managed process owner did not publish a control endpoint.",
            "nextAction": "Inspect the session log. The CLI will not stop processes without a reachable owner.",
        }
    request = Request(
        f"http://127.0.0.1:{port}/status",
        headers={"X-Chronicle-Token": token, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, {
            "code": "dev_owner_unavailable",
            "message": "The CLI-owned development process manager is not reachable.",
            "nextAction": "Inspect the saved session logs; the CLI will not terminate a process without its owner.",
            "details": {"reason": str(exc)},
        }
    return payload, None


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def loopback_port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            candidate.bind(("127.0.0.1", int(port)))
        return True
    except OSError:
        return False


def public_dev_manifest(manifest: dict) -> dict:
    return {key: value for key, value in manifest.items() if key not in {"token", "managerPort", "managerPid"}}


def list_dev_sessions() -> list[dict]:
    root = dev_root()
    if not root.is_dir():
        return []
    sessions = []
    for manifest_path in root.glob("*/session.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict) or manifest.get("runId") != manifest_path.parent.name:
            continue
        row = public_dev_manifest(manifest)
        if manifest.get("status") in {"starting", "running", "stopping"}:
            manager, error = dev_manager_status(manifest)
            row["ownerReachable"] = error is None
            if manager:
                row["status"] = manager.get("status", row["status"])
            elif error:
                row["ownerFailure"] = error.get("code")
        sessions.append(row)
    return sorted(sessions, key=lambda item: item.get("runId", ""))


def run_dev_up(args: argparse.Namespace) -> int:
    latest_path, latest, error = load_latest_dev_manifest()
    if error:
        return fail(error)
    if latest and latest.get("status") in {"starting", "running", "stopping"}:
        manager, manager_error = dev_manager_status(latest)
        if manager_error:
            trace(f"previous dev owner unavailable for run {latest.get('runId')}; starting a new isolated session without stopping it")
        if manager and manager.get("status") in {"starting", "running", "stopping"}:
            return fail({
                "code": "dev_already_running",
                "message": "A CLI-owned development session is already running.",
                "nextAction": "Use dev status, dev logs, or dev down --run-id <runId> before starting another session.",
                "details": public_dev_manifest(manager),
            })

    api_port = args.api_port or free_loopback_port()
    ui_port = args.ui_port or free_loopback_port()
    if not (1 <= api_port <= 65535) or not (1 <= ui_port <= 65535) or api_port == ui_port:
        return fail({
            "code": "invalid_arguments",
            "message": "API and UI ports must be different ports from 1 through 65535.",
            "nextAction": "Choose two distinct loopback ports or omit both options for automatic selection.",
        }, exit_code=2)
    for label, port in (("API", api_port), ("UI", ui_port)):
        if not loopback_port_available(port):
            return fail({
                "code": "port_conflict",
                "message": f"The requested {label} port is already in use.",
                "nextAction": "Choose another port. The CLI will not take over or stop the process using this port.",
                "details": {"port": port},
            }, exit_code=2)

    run_id = uuid.uuid4().hex
    run_dir = dev_root() / run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        return fail({
            "code": "dev_workspace_unavailable",
            "message": "Could not create an isolated CLI development session directory.",
            "nextAction": "Check access to the system temporary directory and rerun dev up.",
            "details": {"reason": str(exc)},
        })

    manifest_path = run_dir / "session.json"
    data_dir = run_dir / "data"
    token = secrets.token_urlsafe(32)
    command = [
        sys.executable,
        str(DEV_MANAGER_PATH),
        "--manifest", str(manifest_path),
        "--token", token,
        "--api-port", str(api_port),
        "--ui-port", str(ui_port),
        "--data-dir", str(data_dir),
    ]
    options = {
        "cwd": ROOT_DIR,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        options["start_new_session"] = True
    try:
        manager_process = subprocess.Popen(command, **options)
    except OSError as exc:
        return fail({
            "code": "dev_manager_start_failed",
            "message": "Could not start the CLI development process manager.",
            "nextAction": "Check the Python executable and rerun dev up.",
            "details": {"reason": str(exc)},
        })

    pointer = dev_root() / "latest.txt"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(run_id, encoding="utf-8")
    deadline = time.monotonic() + 75
    manifest = None
    while time.monotonic() < deadline:
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                manifest = None
            if manifest and manifest.get("status") in {"running", "failed"}:
                break
        if manager_process.poll() is not None:
            break
        time.sleep(0.25)

    if manifest and manifest.get("status") == "running":
        live_manifest, live_error = dev_manager_status(manifest)
        if live_error:
            return fail(live_error)
        if live_manifest.get("status") != "running":
            return fail({
                "code": "dev_start_failed",
                "message": "The process manager exited before the session was reported ready.",
                "nextAction": "Read dev logs and start a new isolated session.",
                "details": public_dev_manifest(live_manifest),
            })
        return emit({
            "status": "succeeded",
            "command": "dev.up",
            "result": {
                "runId": run_id,
                "apiUrl": manifest["apiUrl"],
                "uiUrl": manifest["uiUrl"],
                "dataDir": manifest["dataDir"],
                "logs": manifest["logs"],
            },
            "nextAction": "Use dev doctor to check the live API, then dev down to stop this session. The data directory is retained.",
        })
    return fail({
        "code": "dev_start_failed",
        "message": "The isolated API and UI did not both become ready.",
        "nextAction": "Read dev logs. The manager stops only child processes it started and retains the isolated data directory.",
        "details": public_dev_manifest(manifest or {"runId": run_id, "logs": {}}),
    })


def run_dev_command(args: argparse.Namespace, feature_map: dict | None = None) -> int:
    if args.action == "up":
        return run_dev_up(args)
    if args.action == "sessions":
        return emit({"status": "succeeded", "command": "dev.sessions", "result": list_dev_sessions()})
    manifest_path, manifest, error = load_latest_dev_manifest(getattr(args, "run_id", None))
    if error:
        return fail(error)
    if manifest is None:
        if args.action == "status":
            return emit({"status": "succeeded", "command": "dev.status", "result": {"state": "stopped"}})
        return fail({
            "code": "dev_not_started",
            "message": "No CLI-owned development session is registered for this checkout.",
            "nextAction": "Run dev up to create an isolated development session.",
        }, exit_code=2)

    saved_status = manifest.get("status")
    if saved_status in {"stopped", "failed"}:
        if args.action == "status":
            return emit({"status": "succeeded", "command": "dev.status", "result": public_dev_manifest(manifest)})
        if args.action == "down":
            return emit({"status": "succeeded", "command": "dev.down", "result": {"state": saved_status, "dataDirRetained": manifest.get("dataDir")}})
        if args.action == "doctor":
            return fail({
                "code": "dev_not_running",
                "message": "The latest CLI development session is not running.",
                "nextAction": "Run dev up before dev doctor.",
            }, exit_code=2)

    if args.action == "status":
        manager, error = dev_manager_status(manifest)
        if error:
            result = public_dev_manifest(manifest)
            result["ownerReachable"] = False
            result["ownerFailure"] = error.get("code")
            return emit({"status": "succeeded", "command": "dev.status", "result": result})
        return emit({"status": "succeeded", "command": "dev.status", "result": public_dev_manifest(manager)})

    if args.action == "logs":
        services = ("api", "ui") if args.service == "all" else (args.service,)
        output = {}
        for service in services:
            log_path = Path(manifest.get("logs", {}).get(service, ""))
            try:
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as exc:
                return fail({
                    "code": "dev_log_unavailable",
                    "message": f"Could not read the {service} log.",
                    "nextAction": "Check the saved dev session directory.",
                    "details": {"reason": str(exc)},
                })
            output[service] = lines[-args.lines:]
        return emit({"status": "succeeded", "command": "dev.logs", "result": output})

    manager, error = dev_manager_status(manifest)
    if error:
        return fail(error)
    if args.action == "down":
        if manager.get("status") in {"stopped", "failed"}:
            return emit({"status": "succeeded", "command": "dev.down", "result": {"state": manager.get("status"), "dataDirRetained": manager.get("dataDir")}})
        request = Request(
            f"http://127.0.0.1:{int(manifest['managerPort'])}/shutdown",
            data=b"",
            headers={"X-Chronicle-Token": str(manifest["token"])},
            method="POST",
        )
        try:
            with urlopen(request, timeout=3) as response:
                if response.status != 202:
                    raise RuntimeError(f"unexpected owner response {response.status}")
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
            return fail({
                "code": "dev_shutdown_failed",
                "message": "The CLI-owned process manager rejected or did not receive shutdown.",
                "nextAction": "Check dev status and dev logs. The CLI will not terminate a process without its manager.",
                "details": {"reason": str(exc)},
            })
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                updated = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                updated = {}
            if updated.get("status") == "stopped":
                return emit({
                    "status": "succeeded",
                    "command": "dev.down",
                    "result": {"state": "stopped", "dataDirRetained": updated.get("dataDir")},
                })
            time.sleep(0.25)
        return fail({
            "code": "dev_shutdown_timeout",
            "message": "The process manager has not reported that its child processes stopped.",
            "nextAction": "Run dev status and inspect dev logs. Do not terminate a process by PID.",
            "details": {"runId": manifest.get("runId")},
        })
    if args.action == "doctor":
        live_map, error = feature_map_from_service(manager["apiUrl"])
        if error:
            return fail(error)
        return run_doctor(manager["apiUrl"], live_map)
    return fail({
        "code": "unknown_command",
        "message": f"Unknown dev action: {args.action}",
        "nextAction": "Use dev up, dev status, dev doctor, dev logs, or dev down.",
    }, exit_code=2)


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: object | None = None,
    request_headers: dict[str, str] | None = None,
    file_path: str | None = None,
    output_file: str | None = None,
) -> tuple[dict | list | None, dict | None]:
    headers = {"Accept": "application/json"}
    data = None
    output_path = None
    if output_file:
        output_path = Path(output_file).expanduser().resolve()
        if output_path.exists():
            return None, {
                "code": "output_file_exists",
                "message": "CLI will not overwrite an existing output file.",
                "nextAction": "Choose a new --output-file path and retry the read operation.",
                "details": {"path": str(output_path)},
            }
        if not output_path.parent.is_dir():
            return None, {
                "code": "output_directory_missing",
                "message": "The --output-file parent directory does not exist.",
                "nextAction": "Create the directory explicitly or choose a path inside an existing directory.",
                "details": {"path": str(output_path.parent)},
            }
        if payload is not None or file_path:
            return None, {
                "code": "invalid_arguments",
                "message": "Binary response output cannot share a request body or upload file.",
                "nextAction": "Use --output-file only with a registered binary read operation.",
            }
    if file_path:
        source = Path(file_path).expanduser()
        if not source.is_file():
            return None, {
                "code": "invalid_arguments",
                "message": "上传文件不存在或不是普通文件。",
                "nextAction": "检查 input.file 指向的本地文件路径。",
            }
        boundary = f"chronicle-{os.urandom(12).hex()}"
        file_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        data = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{source.name}"\r\n'
            f"Content-Type: {file_type}\r\n\r\n"
        ).encode("utf-8") + source.read_bytes() + f"\r\n--{boundary}--\r\n".encode("ascii")
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers.update(request_headers or {})
    url = f"{base_url.rstrip('/')}{path}"
    request = Request(url, data=data, headers=headers, method=method)
    started = time.monotonic()
    diagnostic_path = path.split("?", 1)[0]
    trace(f"request {method} {diagnostic_path}")
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            if output_path is not None:
                try:
                    with output_path.open("xb") as target:
                        target.write(raw)
                except OSError as exc:
                    return None, {
                        "code": "output_file_write_failed",
                        "message": "The API response was received but could not be saved to the requested file.",
                        "nextAction": "Choose a writable new --output-file path and rerun the read operation.",
                        "details": {"path": str(output_path), "reason": str(exc)},
                    }
                result = {
                    "savedTo": str(output_path),
                    "bytes": len(raw),
                    "contentType": response.headers.get("content-type", "application/octet-stream"),
                }
            else:
                result = json.loads(raw.decode("utf-8")) if raw else None
            trace(f"response {response.status} {method} {diagnostic_path} {time.monotonic() - started:.3f}s")
            return result, None
    except HTTPError as exc:
        trace(f"response {exc.code} {method} {diagnostic_path} {time.monotonic() - started:.3f}s")
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = None
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            return None, {
                "code": error.get("code", "request_failed"),
                "message": error.get("message", str(exc)),
                "nextAction": error.get("nextAction", "检查请求后重试。"),
                "details": error.get("details"),
                "httpStatus": exc.code,
            }
        return None, {
            "code": "request_failed",
            "message": str(exc),
            "nextAction": "检查服务响应并重试。",
            "details": None,
            "httpStatus": exc.code,
        }
    except (URLError, TimeoutError, OSError) as exc:
        trace(f"transport-error {method} {diagnostic_path} {type(exc).__name__}")
        is_write = method.upper() not in {"GET", "HEAD"}
        details = {"reason": str(exc)}
        key = next((value for name, value in (request_headers or {}).items() if name.lower() == "idempotency-key"), None)
        if key:
            details["idempotencyKey"] = key
        return None, {
            "code": "unknown_result" if is_write else "service_unavailable",
            "message": "连接中断，写入结果未知。" if is_write else "无法连接到编年服务。",
            "nextAction": (
                "通过 Feature Map 中的只读操作回读目标状态；确认结果前不要重放写入。"
                if is_write
                else "启动后端服务，或通过 --base-url 指向正在运行的服务。"
            ),
            "details": details,
        }
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        trace(f"invalid-json {method} {diagnostic_path}")
        return None, {
            "code": "invalid_service_response",
            "message": "服务返回的内容不是有效 JSON。",
            "nextAction": "检查服务地址是否指向编年 API。",
            "details": {"reason": str(exc)},
        }


def get_json(base_url: str, path: str) -> tuple[dict | list | None, dict | None]:
    return request_json(base_url, path)


def feature_map_from_service(base_url: str) -> tuple[dict | None, dict | None]:
    payload, error = get_json(base_url, "/api/features")
    if error:
        return None, error
    feature_map, error = validate_response(FeatureMapOut, payload)
    return (model_data(feature_map), None) if feature_map else (None, error)


def feature_map_from_source() -> tuple[dict | None, dict | None]:
    feature_map, error = validate_response(FeatureMapOut, local_feature_map())
    return (model_data(feature_map), None) if feature_map else (None, error)


def registered_operations(feature_map: dict) -> list[tuple[str, dict]]:
    return [
        (feature["id"], operation)
        for feature in feature_map.get("features", [])
        for operation in feature.get("api", [])
    ]


def operation_by_id(feature_map: dict, operation_id: str) -> tuple[str | None, dict | None]:
    for feature_id, operation in registered_operations(feature_map):
        if operation.get("operationId") == operation_id:
            return feature_id, operation
    return None, None


def openapi_from_service(base_url: str) -> tuple[dict | None, dict | None]:
    payload, error = get_json(base_url, "/openapi.json")
    if error:
        return None, error
    if not isinstance(payload, dict) or not isinstance(payload.get("paths"), dict):
        return None, {
            "code": "invalid_openapi_document",
            "message": "服務未返回可识别的 OpenAPI 路由目录。",
            "nextAction": "检查 --base-url 是否指向 Chronicle FastAPI 服务。",
        }
    return payload, None


def openapi_operations(openapi: dict) -> dict[str, tuple[str, str, dict]]:
    result = {}
    for path, path_item in openapi.get("paths", {}).items():
        if not path.startswith("/api/"):
            continue
        for method, operation in path_item.items():
            if not isinstance(operation, dict) or not operation.get("operationId"):
                continue
            result[operation["operationId"]] = (method.upper(), path, operation)
    return result


def schema_names(schema: str | None) -> list[str]:
    if not schema:
        return []
    if schema in {"Record<string,string>", "string[]", "MultipartFileIn", "Binary"}:
        return []
    value = schema.removesuffix("[]")
    return [part.strip() for part in value.split("|") if part.strip()]


def schema_model(name: str | None):
    return SCHEMA_MODELS.get(name or "")


def api_catalog_diagnostics(base_url: str, feature_map: dict) -> tuple[dict, dict | None]:
    openapi, error = openapi_from_service(base_url)
    if error:
        return {}, error

    server_operations = openapi_operations(openapi)
    feature_operations = registered_operations(feature_map)
    registered_by_id: dict[str, tuple[str, dict]] = {}
    duplicates: list[str] = []
    for feature_id, operation in feature_operations:
        operation_id = operation.get("operationId")
        if not operation_id:
            duplicates.append("<missing-operationId>")
            continue
        if operation_id in registered_by_id:
            # Shared operations such as topics_list can belong to more than one feature.
            continue
        registered_by_id[operation_id] = (feature_id, operation)

    problems: list[dict[str, str]] = []
    missing = sorted(set(server_operations) - set(registered_by_id))
    stale = sorted(set(registered_by_id) - set(server_operations))
    for operation_id in missing:
        problems.append({"code": "feature_missing_operation", "operationId": operation_id})
    for operation_id in stale:
        problems.append({"code": "feature_operation_not_in_openapi", "operationId": operation_id})

    schemas = openapi.get("components", {}).get("schemas", {})
    frontend_path = ROOT_DIR / "ui" / "src" / "composables" / "useApi.js"
    frontend_source = frontend_path.read_text(encoding="utf-8") if frontend_path.is_file() else ""
    missing_client_methods: list[str] = []
    for operation_id, (server_method, server_path, _) in server_operations.items():
        entry = registered_by_id.get(operation_id)
        if not entry:
            continue
        feature_id, operation = entry
        if operation.get("method") != server_method or operation.get("path") != server_path:
            problems.append({"code": "feature_route_mismatch", "operationId": operation_id})
        if operation.get("readOnly") and server_method not in {"GET", "POST"}:
            problems.append({"code": "unsafe_read_only_declaration", "operationId": operation_id})
        for schema_field in ("requestSchema", "responseSchema"):
            for schema_name in schema_names(operation.get(schema_field)):
                if schema_name not in schemas:
                    problems.append({
                        "code": "feature_schema_missing_in_openapi",
                        "operationId": operation_id,
                        "schema": schema_name,
                    })
        if operation.get("responseSchema") == "Binary":
            response = server_operations[operation_id][2].get("responses", {}).get("200", {})
            content = response.get("content", {})
            if not any(
                schema.get("format") == "binary" or schema.get("type") == "string"
                for media in content.values()
                for schema in [media.get("schema", {})]
            ):
                problems.append({"code": "binary_response_schema_missing", "operationId": operation_id})
        query_schema = operation.get("querySchema")
        query_model = schema_model(query_schema)
        if query_schema and query_model is None:
            problems.append({"code": "query_schema_not_supported", "operationId": operation_id, "schema": query_schema})
        elif query_model:
            query_params = {
                item["name"]: bool(item.get("required"))
                for item in server_operations[operation_id][2].get("parameters", [])
                if item.get("in") == "query"
            }
            model_schema = query_model.model_json_schema(by_alias=True) if hasattr(query_model, "model_json_schema") else query_model.schema(by_alias=True)
            model_params = {
                name: name in set(model_schema.get("required", []))
                for name in model_schema.get("properties", {})
            }
            if query_params != model_params:
                problems.append({"code": "query_schema_mismatch", "operationId": operation_id, "schema": query_schema})
        client_method = operation.get("clientMethod")
        if client_method and not re.search(rf"\b{re.escape(client_method)}\s*\(", frontend_source):
            missing_client_methods.append(f"{operation_id}:{client_method}")

    report = {
        "featureMapVersion": feature_map.get("version"),
        "apiOperationCount": len(server_operations),
        "registeredOperationCount": len(registered_by_id),
        "coveredOperationCount": len(set(server_operations) & set(registered_by_id)),
        "featureCount": len(feature_map.get("features", [])),
        "routeMismatches": [item for item in problems if item["code"] == "feature_route_mismatch"],
        "schemaMismatches": [item for item in problems if item["code"] in {"feature_schema_missing_in_openapi", "query_schema_not_supported", "query_schema_mismatch"}],
        "missingClientMethods": missing_client_methods,
        "problems": problems,
    }
    if problems or missing_client_methods:
        return report, {
            "code": "api_catalog_mismatch",
            "message": "Feature Map、OpenAPI 和前端 API 客户端目录未完全对齐。",
            "nextAction": "按 problems 和 missingClientMethods 修正目录或客户端，再重跑 doctor。",
            "details": {"problems": problems, "missingClientMethods": missing_client_methods},
        }
    return report, None


def cli_operation_diagnostics(feature_map: dict) -> tuple[dict, dict | None]:
    active: dict[str, tuple[str, dict]] = {}
    unsupported: list[dict[str, str]] = []
    special_schemas = {"Record<string,string>", "string[]", "MultipartFileIn", "Binary"}

    def supports(schema: str | None) -> bool:
        if not schema or schema in special_schemas:
            return True
        return all(schema_model(name) is not None for name in schema_names(schema))

    for feature_id, operation in registered_operations(feature_map):
        operation_id = operation.get("operationId")
        if not operation_id or operation.get("lifecycle", "active") != "active":
            continue
        active.setdefault(operation_id, (feature_id, operation))

    for operation_id, (feature_id, operation) in active.items():
        for field in ("requestSchema", "querySchema", "responseSchema"):
            schema = operation.get(field)
            if not supports(schema):
                unsupported.append({
                    "featureId": feature_id,
                    "operationId": operation_id,
                    "field": field,
                    "schema": str(schema),
                })

    report = {
        "activeOperationCount": len(active),
        "callableOperationCount": len(active) - len({item["operationId"] for item in unsupported}),
        "dispatch": "api call <operationId>",
        "unsupportedSchemas": unsupported,
    }
    if unsupported:
        return report, {
            "code": "cli_schema_coverage_incomplete",
            "message": "部分 active API operation 没有 CLI schema 验证器。",
            "nextAction": "在 FastAPI 共享 schema 中定义这些类型，再运行 doctor。",
            "details": {"unsupportedSchemas": unsupported},
        }
    return report, None


def validate_named_schema(model, values: object, *, code: str = "invalid_arguments") -> tuple[object | None, dict | None]:
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except json.JSONDecodeError as exc:
            return None, {
                "code": code,
                "message": "输入不是有效 JSON。",
                "nextAction": "提供符合 OperationCallInput 的 JSON 对象。",
                "details": {"reason": str(exc)},
            }
    return validate_input(model, values)


def validate_response_schema(schema_name: str, payload: object) -> tuple[object | None, dict | None]:
    if schema_name.endswith("[]"):
        item_schema = schema_name[:-2]
        if item_schema == "string":
            if isinstance(payload, list) and all(isinstance(value, str) for value in payload):
                return payload, None
            return None, {
                "code": "api_contract_mismatch",
                "message": "API 响应不是预期的字符串数组。",
                "nextAction": "检查服务版本和 OpenAPI schema。",
            }
        model = schema_model(item_schema)
        if model:
            return validate_array_response(model, payload)
    if schema_name == "Record<string,string>":
        if isinstance(payload, dict) and all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
            return payload, None
        return None, {
            "code": "api_contract_mismatch",
            "message": "API 响应不是预期的字符串映射。",
            "nextAction": "检查服务版本和 OpenAPI schema。",
        }
    model = schema_model(schema_name)
    if model:
        return validate_response(model, payload)
    return None, {
        "code": "unsupported_response_schema",
        "message": f"CLI 没有为响应 schema {schema_name} 注册验证器。",
        "nextAction": "先在 CLI schema registry 中加入该响应类型，再执行操作。",
    }


def validate_request_schema(schema_name: str | None, payload: object) -> tuple[object | None, dict | None]:
    if not schema_name:
        if payload is None:
            return None, None
        return None, {
            "code": "unexpected_request_body",
            "message": "此操作不接受请求正文。",
            "nextAction": "移除 input.body 后重试。",
        }
    if schema_name == "Record<string,string>":
        if isinstance(payload, dict) and all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
            return payload, None
        return None, {
            "code": "invalid_arguments",
            "message": "body 必须是字符串到字符串的映射。",
            "nextAction": "修正 body 字段后重试。",
        }
    if schema_name == "MultipartFileIn":
        if payload is None:
            return None, None
        return None, {
            "code": "invalid_arguments",
            "message": "文件操作不接受 JSON body。",
            "nextAction": "通过 input.file 指定文件路径。",
        }
    validation_errors = []
    known_models = []
    for candidate in (part.strip() for part in schema_name.split("|")):
        model = schema_model(candidate)
        if model:
            known_models.append(candidate)
            parsed, error = validate_input(model, payload if payload is not None else {})
            if not error:
                return parsed, None
            validation_errors.append(error)
    if known_models and validation_errors:
        return None, min(validation_errors, key=lambda error: len(error.get("details", [])))
    return None, {
        "code": "unsupported_request_schema",
        "message": f"CLI 没有为请求 schema {schema_name} 注册验证器。",
        "nextAction": "先在 CLI schema registry 中加入该请求类型，再执行操作。",
    }


def run_registered_operation(
    base_url: str,
    feature_map: dict,
    openapi: dict,
    operation_id: str,
    input_value: object,
    *,
    confirm_writes: bool = False,
    output_file: str | None = None,
) -> tuple[dict | None, dict | None]:
    feature_id, operation = operation_by_id(feature_map, operation_id)
    if not operation:
        return None, {
            "code": "unknown_operation",
            "message": f"Feature Map 未注册操作 {operation_id}。",
            "nextAction": "运行 api list 并选择已登记操作。",
        }
    if operation.get("lifecycle", "active") != "active":
        return None, {
            "code": "operation_out_of_scope",
            "message": f"操作 {operation_id} 的生命周期为 {operation.get('lifecycle')}，CLI 只执行 active 操作。",
            "nextAction": "运行 api list 并选择 lifecycle 为 active 的 operationId。",
        }
    if operation.get("readOnly") is not True and not confirm_writes:
        return None, {
            "code": "confirmation_required",
            "message": "此操作会更改 Chronicle 数据，必须显式确认。",
            "nextAction": f"确认变更范围后，使用 api call {operation_id} --confirm。",
        }

    call, error = validate_named_schema(OperationCallInput, input_value)
    if error:
        return None, error

    actual = openapi_operations(openapi).get(operation_id)
    if not actual:
        return None, {
            "code": "operation_not_available",
            "message": "目标服务的 OpenAPI 中没有此操作。",
            "nextAction": "确认服务版本和 Feature Map 来自同一个 Chronicle 服务。",
        }
    method, route, route_spec = actual
    if operation.get("method") != method or operation.get("path") != route:
        return None, {
            "code": "api_catalog_mismatch",
            "message": "目标服务的操作路由与 Feature Map 不一致。",
            "nextAction": "重启到匹配版本的服务，并运行 doctor 核验目录。",
        }

    parameters = route_spec.get("parameters", [])
    path_params = {item["name"]: item for item in parameters if item.get("in") == "path"}
    if set(call.path) != set(path_params):
        return None, {
            "code": "invalid_arguments",
            "message": "path 参数与操作路由要求不一致。",
            "nextAction": f"提供且只提供这些 path 参数：{', '.join(sorted(path_params)) or '无'}。",
        }
    resolved_path = route
    for name, parameter in path_params.items():
        value = call.path[name]
        schema = parameter.get("schema", {})
        if schema.get("type") == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return None, {"code": "invalid_arguments", "message": f"path.{name} 必须是 JSON 整数。", "nextAction": "使用整数类型的资源 ID，不要提供小数或字符串。"}
            if value < 1:
                return None, {"code": "invalid_arguments", "message": f"path.{name} 必须是正整数。", "nextAction": "修正 path 参数后重试。"}
        elif not isinstance(value, str) or not value:
            return None, {"code": "invalid_arguments", "message": f"path.{name} 必须是非空字符串。", "nextAction": "修正 path 参数后重试。"}
        resolved_path = resolved_path.replace("{" + name + "}", quote(str(value), safe=""))

    query_parameters = {item["name"]: item for item in parameters if item.get("in") == "query"}
    query_schema = operation.get("querySchema")
    query_model = schema_model(query_schema)
    if query_schema and query_model is None:
        return None, {"code": "unsupported_query_schema", "message": f"OpenAPI 查询 schema {query_schema} 没有共享 Pydantic 类型。", "nextAction": "为 FastAPI 路由登记 schema 后重试。"}
    if query_model:
        query_value, error = validate_input(query_model, call.query)
        if error:
            return None, error
        query_values = model_data(query_value, exclude_none=True)
    else:
        if set(call.query) - set(query_parameters):
            return None, {
                "code": "invalid_arguments",
                "message": "查询参数与 OpenAPI 路由要求不一致。",
                "nextAction": f"可用 query 参数：{', '.join(sorted(query_parameters)) or '无'}。",
            }
        missing_query = sorted(
            name for name, item in query_parameters.items()
            if item.get("required") and name not in call.query
        )
        if missing_query:
            return None, {
                "code": "invalid_arguments",
                "message": "缺少必需的 query 参数。",
                "nextAction": f"提供这些参数：{', '.join(missing_query)}。",
            }
        query_values = call.query
    if set(query_values) - set(query_parameters):
        return None, {
            "code": "api_catalog_mismatch",
            "message": "query schema 包含 OpenAPI 未登记的参数。",
            "nextAction": "同步 Feature Map 查询 schema 和 FastAPI OpenAPI。",
        }
    if query_values:
        resolved_path += "?" + urlencode(query_values, doseq=True)

    header_parameters = {item["name"].lower(): item for item in parameters if item.get("in") == "header"}
    provided_headers: dict[str, str] = {}
    for name, value in call.headers.items():
        normalized = name.lower()
        if normalized not in header_parameters:
            return None, {
                "code": "invalid_arguments",
                "message": f"header.{name} 未在 OpenAPI 中登记。",
                "nextAction": f"可用 headers：{', '.join(item['name'] for item in header_parameters.values()) or '无'}。",
            }
        if normalized in provided_headers:
            return None, {"code": "invalid_arguments", "message": f"header.{name} 重复。", "nextAction": "每个 header 只提供一个值。"}
        provided_headers[normalized] = value
    missing_headers = [
        parameter["name"]
        for name, parameter in header_parameters.items()
        if parameter.get("required") and name not in provided_headers
    ]
    if missing_headers:
        return None, {
            "code": "invalid_arguments",
            "message": "缺少必需的 header。",
            "nextAction": f"提供这些 headers：{', '.join(missing_headers)}。",
        }
    request_headers = {
        header_parameters[name]["name"]: value
        for name, value in provided_headers.items()
    }

    request_schema = operation.get("requestSchema")
    response_schema = operation.get("responseSchema")
    if response_schema == "Binary" and not output_file:
        return None, {
            "code": "output_file_required",
            "message": "This operation returns a file and requires --output-file.",
            "nextAction": f"Run api describe {operation_id}, then choose a new output path with --output-file.",
        }
    if response_schema != "Binary" and output_file:
        return None, {
            "code": "unexpected_output_file",
            "message": "This operation does not return a file.",
            "nextAction": "Remove --output-file or choose a registered binary read operation.",
        }
    if request_schema == "MultipartFileIn":
        if not call.file:
            return None, {
                "code": "invalid_arguments",
                "message": "此操作需要 input.file 文件路径。",
                "nextAction": "在 --input-json 或 --input-file 中填写 input.file。",
            }
        if call.body is not None:
            return None, {
                "code": "unexpected_request_body",
                "message": "multipart 文件操作不接受 JSON body。",
                "nextAction": "移除 input.body 并只填写 input.file。",
            }
        body = None
    else:
        if call.file:
            return None, {
                "code": "unexpected_file_input",
                "message": "此操作不接受文件输入。",
                "nextAction": "移除 input.file。",
            }
        body, error = validate_request_schema(request_schema, call.body)
        if error:
            return None, error
        if body is not None:
            body = model_data(body, exclude_unset=True) if hasattr(body, "model_dump") or hasattr(body, "dict") else body

    response, error = request_json(
        base_url,
        resolved_path,
        method=method,
        payload=body,
        request_headers=request_headers,
        file_path=call.file,
        output_file=output_file,
    )
    if error:
        return None, error
    if response_schema == "Binary":
        result = response
    else:
        parsed_response, error = validate_response_schema(response_schema, response)
        if error:
            return None, error
        result = model_data(parsed_response) if hasattr(parsed_response, "model_dump") or hasattr(parsed_response, "dict") else parsed_response
    return {"featureId": feature_id, "operationId": operation_id, "result": result}, None


def get_note(base_url: str, note_id: int) -> tuple[dict | None, dict | None]:
    payload, error = get_json(base_url, f"/api/notes/{note_id}")
    if error:
        return None, error
    note, error = validate_response(NoteOut, payload)
    return (model_data(note), None) if note else (None, error)


def list_notes(base_url: str, note_input) -> tuple[dict | None, dict | None]:
    values = model_data(note_input, exclude_none=True)
    topic_id = values.pop("topicId")
    values.pop("containsNoteId", None)
    query = urlencode(values)
    path = f"/api/topics/{topic_id}/notes?{query}" if query else f"/api/topics/{topic_id}/notes"
    payload, error = get_json(base_url, path)
    if error:
        return None, error
    page, error = validate_response(NotePageOut, payload)
    if not page:
        return None, error
    result = model_data(page)
    result["items"] = [
        {
            key: item.get(key)
            for key in (
                "id",
                "headline",
                "displayLabel",
                "preview",
                "updatedAt",
                "favorite",
                "deletedAt",
            )
        }
        for item in result["items"]
    ]
    return result, None


def search_notes(base_url: str, search_input) -> tuple[list[dict] | None, dict | None]:
    parameters = model_data(search_input)
    parameters.pop("expectedNoteId", None)
    query = urlencode(parameters)
    payload, error = get_json(base_url, f"/api/search?{query}")
    if error:
        return None, error
    return validate_array_response(NoteSearchItem, payload)


def scenario_by_id(feature_map: dict, scenario_id: str) -> tuple[dict | None, dict | None]:
    for feature in feature_map.get("features", []):
        for scenario in feature.get("scenarios", []):
            if scenario.get("id") == scenario_id:
                return feature, scenario
    return None, None


def run_note_command(args: argparse.Namespace, base_url: str) -> int:
    if args.action == "get":
        values, error = validate_input(NoteReadScenarioInput, {"noteId": args.note_id})
        if error:
            return fail(error)
        note, error = get_note(base_url, values.noteId)
        if error:
            return fail(error, feature="notes.read")
        return emit({"status": "succeeded", "command": "note.get", "featureId": "notes.read", "operationId": "notes_get", "result": note})

    if args.action == "list":
        values, error = validate_input(
            NoteListInput,
            {
                key: value
                for key, value in {
                    "topicId": args.topic_id,
                    "limit": args.limit,
                    "from": args.from_date,
                    "to": args.to_date,
                    "cursor": args.cursor,
                    "dir": args.direction,
                }.items()
                if value is not None
            },
        )
        if error:
            return fail(error)
        page, error = list_notes(base_url, values)
        if error:
            return fail(error, feature="notes.browse")
        return emit({"status": "succeeded", "command": "note.list", "featureId": "notes.browse", "operationId": "notes_list", "result": page})

    values, error = validate_input(
        NoteSearchInput,
        {key: value for key, value in {"q": args.query, "limit": args.limit}.items() if value is not None},
    )
    if error:
        return fail(error)
    results, error = search_notes(base_url, values)
    if error:
        return fail(error, feature="notes.search")
    return emit({"status": "succeeded", "command": "note.search", "featureId": "notes.search", "operationId": "notes_search", "result": results})


def run_topic_command(args: argparse.Namespace, base_url: str) -> int:
    if args.action == "list":
        payload, error = get_json(base_url, "/api/topics")
        if error:
            return fail(error, feature="topics.manage")
        topics, error = validate_array_response(TopicOut, payload)
        if error:
            return fail(error, feature="topics.manage")
        result = [
            {key: topic.get(key) for key in ("id", "name", "title", "noteCount", "minDate", "maxDate")}
            for topic in topics
        ]
        return emit({"status": "succeeded", "command": "topic.list", "featureId": "topics.manage", "operationId": "topics_list", "result": result})

    values, error = validate_input(TopicReadInput, {"topicId": args.topic_id})
    if error:
        return fail(error)
    payload, error = get_json(base_url, f"/api/topics/{values.topicId}")
    if error:
        return fail(error, feature="topics.manage")
    topic, error = validate_response(TopicOut, payload)
    if error:
        return fail(error, feature="topics.manage")
    return emit(
        {
            "status": "succeeded",
            "command": "topic.get",
            "featureId": "topics.manage",
            "operationId": "topics_get",
            "result": model_data(topic),
        }
    )


def summarize_operation_result(result: object) -> dict:
    if isinstance(result, list):
        return {"itemCount": len(result)}
    if isinstance(result, dict):
        summary = {"fields": sorted(result.keys())}
        for name in ("id", "updatedAt", "databaseIdentity", "groupBy", "hasMore"):
            if name in result:
                summary[name] = result[name]
        if isinstance(result.get("items"), list):
            summary["itemCount"] = len(result["items"])
        if isinstance(result.get("notes"), list):
            summary["noteCount"] = len(result["notes"])
        if isinstance(result.get("topics"), list):
            summary["topicCount"] = len(result["topics"])
        return summary
    return {"value": result}


def run_read_smoke(base_url: str, feature_map: dict) -> tuple[list[dict], dict | None]:
    feature, scenario = scenario_by_id(feature_map, "app.read-smoke")
    if not scenario:
        return [], {
            "code": "unknown_scenario",
            "message": "Feature Map 未注册 app.read-smoke。",
            "nextAction": "更新服务到包含完整诊断场景的版本后重试。",
        }
    openapi, error = openapi_from_service(base_url)
    if error:
        return [], error
    results = []
    for step in scenario.get("steps", []):
        operation_id = step.get("operationId")
        operation_result, error = run_registered_operation(
            base_url,
            feature_map,
            openapi,
            operation_id,
            {"path": {}, "query": {}, "body": None},
        )
        if error:
            error = dict(error)
            error["details"] = {"step": step.get("id"), "operationId": operation_id, "cause": error.get("details")}
            return results, error
        results.append({"step": step["id"], "operationId": operation_id, "status": "passed", "result": summarize_operation_result(operation_result["result"])})
    return results, None


def run_doctor(base_url: str, feature_map: dict) -> int:
    catalog, catalog_error = api_catalog_diagnostics(base_url, feature_map)
    checks = [{"id": "api-catalog", "status": "passed" if not catalog_error else "failed", "result": catalog}]
    errors = []
    if catalog_error:
        errors.append(catalog_error)

    cli_coverage, cli_coverage_error = cli_operation_diagnostics(feature_map)
    checks.append({
        "id": "cli-operation-coverage",
        "status": "passed" if not cli_coverage_error else "failed",
        "result": cli_coverage,
    })
    if cli_coverage_error:
        errors.append(cli_coverage_error)

    identity_feature, identity_operation = operation_by_id(feature_map, "runtime_identity")
    if identity_operation:
        openapi, openapi_error = openapi_from_service(base_url)
        if openapi_error:
            identity_result, identity_error = None, openapi_error
        else:
            identity_result, identity_error = run_registered_operation(
                base_url,
                feature_map,
                openapi,
                "runtime_identity",
                {"path": {}, "query": {}, "body": None},
            )
        checks.append({
            "id": "runtime-identity",
            "status": "passed" if not identity_error else "failed",
            "result": summarize_operation_result(identity_result["result"]) if identity_result else None,
        })
        if identity_error:
            errors.append(identity_error)
    else:
        errors.append({
            "code": "runtime_identity_not_registered",
            "message": "Feature Map 未登记 runtime_identity。",
            "nextAction": "补齐服务身份操作后重跑 doctor。",
        })

    status = "passed" if not errors else "failed"
    payload = {
        "status": status,
        "checks": checks,
        "failure": errors[0] if errors else None,
        "nextAction": errors[0].get("nextAction") if errors else None,
    }
    return emit(payload, 0 if not errors else 1)


def read_operation_input(args: argparse.Namespace) -> tuple[dict | None, dict | None]:
    source = getattr(args, "input_json", None)
    input_file = getattr(args, "input_file", None)
    if source is not None and input_file is not None:
        return None, {
            "code": "invalid_arguments",
            "message": "--input-json 和 --input-file 不能同时使用。",
            "nextAction": "只提供其中一种输入方式。",
        }
    try:
        if input_file:
            source = Path(input_file).read_text(encoding="utf-8")
        value = json.loads(source) if source is not None else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, {
            "code": "invalid_arguments",
            "message": "无法读取有效的 CLI JSON 输入。",
            "nextAction": "检查 --input-file 路径或修正 --input-json 内容。",
            "details": {"reason": str(exc)},
        }
    if not isinstance(value, dict):
        return None, {
            "code": "invalid_arguments",
            "message": "CLI 操作输入必须是 JSON 对象。",
            "nextAction": "使用 {\"path\":{},\"query\":{},\"headers\":{},\"body\":{},\"file\":null} 结构传入输入。",
        }
    return value, None


def run_api_command(args: argparse.Namespace, base_url: str, feature_map: dict) -> int:
    if args.action == "list":
        unique = {}
        for feature_id, operation in registered_operations(feature_map):
            unique.setdefault(operation["operationId"], {**operation, "feature": feature_id})
        return emit({"status": "succeeded", "command": "api.list", "operations": sorted(unique.values(), key=lambda item: item["operationId"])})

    feature_id, operation = operation_by_id(feature_map, args.operation_id)
    if not operation:
        return fail({
            "code": "unknown_operation",
            "message": f"Feature Map 未注册操作 {args.operation_id}。",
            "nextAction": "运行 api list 并选择已登记的 operationId。",
        }, exit_code=2)
    if args.action == "describe":
        openapi, error = openapi_from_service(base_url)
        if error:
            return fail(error, feature=feature_id)
        actual = openapi_operations(openapi).get(args.operation_id)
        if not actual:
            return fail({
                "code": "operation_not_available",
                "message": "目标服务的 OpenAPI 中没有此操作。",
                "nextAction": "确认服务版本和 Feature Map 来自同一个 Chronicle 服务。",
            }, feature=feature_id)
        _, _, route_spec = actual
        parameters = [
            {
                "name": item["name"],
                "in": item.get("in"),
                "required": bool(item.get("required")),
                "type": item.get("schema", {}).get("type", "unknown"),
                "default": item.get("schema", {}).get("default"),
                "enum": item.get("schema", {}).get("enum"),
                "description": item.get("description"),
            }
            for item in route_spec.get("parameters", [])
        ]
        request_body = route_spec.get("requestBody", {}).get("content", {})
        responses = route_spec.get("responses", {})
        component_schemas = openapi.get("components", {}).get("schemas", {})
        referenced_schemas = set()
        for field in ("requestSchema", "querySchema", "responseSchema"):
            referenced_schemas.update(schema_names(operation.get(field)))
        declared_schemas = {
            operation.get(field)
            for field in ("requestSchema", "querySchema", "responseSchema")
            if operation.get(field)
        }
        schemas = {
            name: component_schemas[name]
            for name in sorted(referenced_schemas)
            if name in component_schemas
        }
        if "Record<string,string>" in referenced_schemas:
            schemas["Record<string,string>"] = {
                "type": "object",
                "additionalProperties": {"type": "string"},
            }
        if "MultipartFileIn" in referenced_schemas:
            schemas["MultipartFileIn"] = {"type": "string", "format": "binary"}
        if "Binary" in declared_schemas:
            schemas["Binary"] = {"type": "string", "format": "binary"}
        if "string[]" in declared_schemas:
            schemas["string[]"] = {"type": "array", "items": {"type": "string"}}
        return emit({
            "status": "succeeded",
            "command": "api.describe",
            "featureId": feature_id,
            "operationId": args.operation_id,
            "operation": operation,
            "parameters": parameters,
            "requestBody": request_body,
            "responses": responses,
            "schemas": schemas,
            "writeConfirmationRequired": operation.get("readOnly") is not True,
            "outputFileRequired": operation.get("responseSchema") == "Binary",
        })

    if operation.get("readOnly") is not True and not args.confirm:
        return fail({
            "code": "confirmation_required",
            "message": "此 operation 会更改 Chronicle 数据。",
            "nextAction": f"检查 api describe {args.operation_id} 的输入、副作用和版本条件；确认后再添加 --confirm。",
        }, feature=feature_id, exit_code=2)

    input_value, error = read_operation_input(args)
    if error:
        return fail(error, feature=feature_id, exit_code=2)
    openapi, error = openapi_from_service(base_url)
    if error:
        return fail(error, feature=feature_id)
    result, error = run_registered_operation(
        base_url,
        feature_map,
        openapi,
        args.operation_id,
        input_value,
        confirm_writes=args.confirm,
        output_file=args.output_file,
    )
    if error:
        return fail(error, feature=feature_id, exit_code=2 if error.get("code") in {"confirmation_required", "operation_out_of_scope", "invalid_arguments", "unsupported_request_schema", "output_file_required", "unexpected_output_file", "output_file_exists", "output_directory_missing"} else 1)
    return emit({"status": "succeeded", "command": "api.call", **result})


def run_scenario(args: argparse.Namespace, base_url: str, feature_map: dict) -> int:
    feature, scenario = scenario_by_id(feature_map, args.scenario_id)
    if not scenario:
        error = {
            "code": "unknown_scenario",
            "message": f"Unknown scenario: {args.scenario_id}",
            "nextAction": "运行 scenario list 并使用已注册场景。",
        }
        return fail(error, exit_code=2)
    if scenario.get("readOnly") is not True:
        error = {
            "code": "scenario_requires_user_confirmation",
            "message": "该场景包含写入步骤，当前 CLI 只运行只读场景。",
            "nextAction": "先在 UI 中完成并确认写入，再运行只读回读场景。",
        }
        return fail(error, feature=feature["id"], scenario=scenario["id"], exit_code=2)

    input_schema = scenario.get("inputSchema")
    if input_schema == "EmptyInput" and scenario.get("id") == "app.read-smoke":
        _, error = validate_input(EmptyInput, {})
        if error:
            return fail(error, feature=feature["id"], scenario=scenario["id"], exit_code=2)
        results, error = run_read_smoke(base_url, feature_map)
        if error:
            return fail(error, feature=feature["id"], scenario=scenario["id"])
        return emit({
            "status": "passed",
            "feature": feature["id"],
            "scenario": scenario["id"],
            "result": {"steps": results, "passed": len(results), "failed": 0},
            "failure": None,
            "nextAction": None,
        })
    if input_schema == "NoteReadScenarioInput":
        values, error = validate_input(NoteReadScenarioInput, {"noteId": args.note_id})
        if error:
            return fail(error, feature=feature["id"], scenario=scenario["id"], exit_code=2)
        note, error = get_note(base_url, values.noteId)
        if error:
            return fail(error, feature=feature["id"], scenario=scenario["id"])
        result = {"noteId": note["id"], "version": note["updatedAt"], "headline": note["headline"]}
        passed = note["id"] == values.noteId and bool(note["updatedAt"])
    elif input_schema == "NoteListScenarioInput":
        values, error = validate_input(
            NoteListScenarioInput,
            {
                key: value
                for key, value in {
                    "topicId": args.topic_id,
                    "containsNoteId": args.contains_note_id,
                    "limit": args.limit,
                    "from": args.from_date,
                    "to": args.to_date,
                    "cursor": args.cursor,
                    "dir": args.direction,
                }.items()
                if value is not None
            },
        )
        if error:
            return fail(error, feature=feature["id"], scenario=scenario["id"], exit_code=2)
        page, error = list_notes(base_url, values)
        if error:
            return fail(error, feature=feature["id"], scenario=scenario["id"])
        ids = [item["id"] for item in page["items"]]
        result = {"topicId": values.topicId, "noteCount": len(ids), "containsNoteId": values.containsNoteId}
        passed = values.containsNoteId in ids
    elif input_schema == "NoteSearchScenarioInput":
        values, error = validate_input(
            NoteSearchScenarioInput,
            {
                key: value
                for key, value in {
                    "q": args.query,
                    "limit": args.limit,
                    "expectedNoteId": args.expected_note_id,
                }.items()
                if value is not None
            },
        )
        if error:
            return fail(error, feature=feature["id"], scenario=scenario["id"], exit_code=2)
        results, error = search_notes(base_url, values)
        if error:
            return fail(error, feature=feature["id"], scenario=scenario["id"])
        ids = [item["id"] for item in results]
        result = {"query": values.query, "resultCount": len(ids), "expectedNoteId": values.expectedNoteId}
        passed = values.expectedNoteId in ids
    else:
        error = {
            "code": "unsupported_scenario_schema",
            "message": f"No runner is registered for input schema {input_schema}.",
            "nextAction": "Use scenario describe to inspect the scenario and choose a supported operation.",
        }
        return fail(error, feature=feature["id"], scenario=scenario["id"], exit_code=2)

    if not passed:
        error = {
            "code": "scenario_assertion_failed",
            "message": "实际 API 结果未满足场景断言。",
            "nextAction": "检查笔记身份、查询范围和当前服务数据后重跑场景。",
            "details": result,
        }
        return fail(error, feature=feature["id"], scenario=scenario["id"])
    return emit(
        {
            "status": "passed",
            "feature": feature["id"],
            "scenario": scenario["id"],
            "result": result,
            "failure": None,
            "nextAction": None,
        }
    )


def validate_loopback_url(value: str, *, label: str) -> tuple[str | None, dict | None]:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        is_loopback = hostname == "localhost" or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        is_loopback = False
        parsed = None
    if parsed is None or parsed.scheme != "http" or not parsed.netloc or not is_loopback:
        return None, {
            "code": "local_ui_url_required",
            "message": f"{label} must be an HTTP URL on localhost or a loopback address.",
            "nextAction": "Start Chronicle on a loopback address and pass its local URL.",
        }
    return value.rstrip("/"), None


def validate_ui_viewport(width: int, height: int) -> dict | None:
    if not 320 <= width <= 3840 or not 320 <= height <= 4320:
        return {
            "code": "invalid_ui_viewport",
            "message": "UI viewport dimensions are outside the supported device range.",
            "nextAction": "Use a width from 320 to 3840 and a height from 320 to 4320 pixels.",
            "details": {"width": width, "height": height},
        }
    return None


def applicable_ui_variant(contract: dict, width: int) -> dict | None:
    return next((
        variant for variant in contract["variants"]
        if width >= variant["minWidth"]
        and (variant["maxWidth"] is None or width <= variant["maxWidth"])
    ), None)


def run_ui_driver(request: dict, *, timeout: int = 45) -> tuple[dict | None, dict | None]:
    node = shutil.which("node")
    if not node:
        return None, {
            "code": "ui_driver_unavailable",
            "message": "Node.js is not available to the UI browser runner.",
            "nextAction": "Install the repository's Node.js dependency runtime, then rerun the UI command.",
        }
    try:
        process = subprocess.run(
            [node, str(ROOT_DIR / "tools" / "chronicle_ui_runner.mjs")],
            input=json.dumps(request, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=ROOT_DIR,
        )
    except subprocess.TimeoutExpired:
        return None, {
            "code": "ui_driver_timeout",
            "message": "The browser command exceeded its time limit.",
            "nextAction": "Check the local service and browser runner, then rerun the registered UI scenario.",
        }
    except OSError as exc:
        return None, {
            "code": "ui_driver_unavailable",
            "message": "The browser runner could not be started.",
            "nextAction": "Install the repository's UI browser dependency and rerun the command.",
            "details": {"reason": str(exc)},
        }
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError:
        return None, {
            "code": "ui_driver_invalid_output",
            "message": "The browser runner did not return one JSON result.",
            "nextAction": "Check the Node.js and Playwright installation, then rerun the command.",
            "details": {"exitCode": process.returncode, "stderr": process.stderr[-4000:]},
        }
    if process.returncode != 0 or result.get("status") == "failed":
        return None, {
            "code": result.get("failure", {}).get("code", "ui_driver_failed"),
            "message": result.get("failure", {}).get("message", "The browser scenario failed."),
            "nextAction": "Inspect the returned UI facts and browser error, then rerun the registered scenario.",
            "details": {"result": result, "stderr": process.stderr[-4000:]},
        }
    return result, None


def ui_source_facts(contract: dict) -> dict:
    digests = {"ui/contracts.json": hashlib.sha256((ROOT_DIR / "ui" / "contracts.json").read_bytes()).hexdigest()}
    for relative in contract.get("sourcePaths", []):
        digests[relative] = hashlib.sha256((ROOT_DIR / relative).read_bytes()).hexdigest()
    tracked_paths = ["ui/contracts.json", *contract.get("sourcePaths", [])]
    status = subprocess.run(
        ["git", "status", "--short", "--", *tracked_paths],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT_DIR,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT_DIR
    )
    return {
        "gitRevision": revision.stdout.strip() if revision.returncode == 0 else None,
        "workingTreeDirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "sha256": digests,
    }


def ui_revision_facts() -> dict:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT_DIR
    )
    return {"gitRevision": revision.stdout.strip() if revision.returncode == 0 else None}


def run_ui_command(args: argparse.Namespace) -> int:
    feature_map, error = feature_map_from_source()
    if error:
        return fail(error)
    catalog, error = load_ui_contracts()
    if error:
        return fail(error)
    contracts = catalog.model_dump(by_alias=True)["contracts"]

    if args.action == "check":
        result = validate_ui_contracts(feature_map, feature_id=args.feature_id)
        payload = {"check": "ui-contracts", **result, "nextAction": None}
        if result["status"] == "failed":
            payload["failure"] = {
                "code": "ui_contract_invalid",
                "message": "The UI contract registry or a Feature Map binding is invalid.",
            }
            payload["nextAction"] = "Fix the reported problems and rerun ui check."
        elif result["status"] == "partial":
            payload["nextAction"] = "Bind each remaining Web Feature to an executable UI contract, or explicitly mark it as having no Web entry."
        exit_code = 1 if result["status"] == "failed" else 3 if result["status"] == "partial" else 4 if result["status"] == "not_applicable" else 0
        return emit(payload, exit_code)

    if args.action == "guide":
        if args.feature_id:
            feature = next((item for item in feature_map["features"] if item["id"] == args.feature_id), None)
            if feature is None:
                return fail({
                    "code": "unknown_feature",
                    "message": f"Unknown feature: {args.feature_id}",
                    "nextAction": "Run feature list and choose a registered feature id.",
                }, exit_code=2)
            selected_ids = feature.get("ui", {}).get("contractIds", [])
            selected = [item for item in contracts if item["id"] in selected_ids]
        elif args.contract_id:
            selected = [item for item in contracts if item["id"] == args.contract_id]
            feature = None
        else:
            selected = contracts
            feature = None
        if feature is not None and feature.get("ui", {}).get("hasWebEntry", True) is False:
            return emit({
                "status": "not_applicable",
                "source": "working-tree",
                "feature": args.feature_id,
                "hasWebEntry": False,
                "contracts": [],
                "compliance": "not-applicable",
            })
        if args.contract_id:
            selected = [item for item in selected if item["id"] == args.contract_id]
        if not selected:
            return fail({
                "code": "unknown_ui_contract",
                "message": "No UI contract matches the requested feature or contract id.",
                "nextAction": "Run ui guide without a filter or choose a contract id from the Feature Map.",
            }, exit_code=2)
        return emit({
            "status": "succeeded",
            "command": "ui.guide",
            "source": "working-tree",
            "feature": args.feature_id,
            "contractIds": [item["id"] for item in selected],
            "contracts": selected,
            "compliance": "not-assessed",
        })

    if args.action == "inspect":
        error = validate_ui_viewport(args.viewport_width, args.viewport_height)
        if error:
            return fail(error, exit_code=2)
        url, error = validate_loopback_url(args.url, label="UI URL")
        if error:
            return fail(error, exit_code=2)
        observed, error = run_ui_driver({
            "mode": "inspect",
            "url": url,
            "viewport": {"width": args.viewport_width, "height": args.viewport_height},
        })
        if error:
            return fail(error, feature=contract["featureId"])
        return emit({
            "status": "observed",
            "proof": False,
            "observation": observed["page"],
            "source": ui_revision_facts(),
        })

    if args.action == "measure":
        feature_map, error = feature_map_from_service(args.base_url)
        if error:
            return fail(error)
        contract, scenario = find_ui_scenario(catalog, args.scenario_id)
        if contract is None or scenario is None:
            return fail({
                "code": "unknown_scenario",
                "message": f"Unknown UI scenario: {args.scenario_id}",
                "nextAction": "Run scenario list and choose a registered UI scenario.",
            }, exit_code=2)
        return run_ui_scenario(args, args.base_url, feature_map, contract, scenario)

    return fail({
        "code": "unsupported_ui_command",
        "message": f"Unsupported UI action: {args.action}",
        "nextAction": "Use ui guide, ui check, or ui inspect.",
    }, exit_code=2)


def run_ui_scenario(args: argparse.Namespace, base_url: str, feature_map: dict, contract: dict, scenario: dict) -> int:
    measure_mode = getattr(args, "command", None) == "ui"
    contract_check = validate_ui_contracts(feature_map, feature_id=contract["featureId"])
    if contract_check["status"] != "passed":
        return fail({
            "code": "ui_contract_invalid",
            "message": "The UI contract is not applicable to the current Feature Map or has validation problems.",
            "nextAction": "Run ui check for the feature and fix its binding or coverage errors.",
            "details": contract_check,
        }, feature=contract["featureId"], scenario=scenario["id"])
    feature = next((item for item in feature_map["features"] if item["id"] == contract["featureId"]), None)
    if feature is None or contract["id"] not in feature.get("ui", {}).get("contractIds", []):
        return fail({
            "code": "ui_contract_feature_mismatch",
            "message": "The service Feature Map does not bind this UI contract to its feature.",
            "nextAction": "Restart against a service built from the current Feature Map and UI contract.",
        }, scenario=scenario["id"])
    if not args.ui_url or not args.input_json:
        return fail({
            "code": "invalid_arguments",
            "message": "UI scenarios require --ui-url and --input-json.",
            "nextAction": "Read scenario describe, then provide the local Web URL and its input object.",
        }, feature=feature["id"], scenario=scenario["id"], exit_code=2)
    error = validate_ui_viewport(args.viewport_width, args.viewport_height)
    if error:
        return fail(error, feature=feature["id"], scenario=scenario["id"], exit_code=2)
    variant = applicable_ui_variant(contract, args.viewport_width)
    if variant is None:
        return fail({
            "code": "ui_variant_not_supported",
            "message": "The UI contract has no variant for this viewport width.",
            "nextAction": "Choose a registered viewport variant or update the contract.",
            "details": {"width": args.viewport_width, "variants": contract["variants"]},
        }, feature=feature["id"], scenario=scenario["id"], exit_code=2)
    if measure_mode and (not 2 <= args.repeat <= 30 or (args.dataset_size is not None and args.dataset_size < 1)):
        return fail({
            "code": "invalid_measurement_input",
            "message": "UI measurements need 2 to 30 samples and a positive dataset size when supplied.",
            "nextAction": "Set --repeat between 2 and 30 and --dataset-size to a positive count.",
        }, feature=feature["id"], scenario=scenario["id"], exit_code=2)
    if measure_mode and not args.run_mode:
        return fail({
            "code": "measurement_run_mode_required",
            "message": "UI measurements must name the browser run mode.",
            "nextAction": "Pass --run-mode with development, preview, or production.",
        }, feature=feature["id"], scenario=scenario["id"], exit_code=2)
    url, error = validate_loopback_url(args.ui_url, label="UI URL")
    if error:
        return fail(error, feature=feature["id"], scenario=scenario["id"], exit_code=2)
    parsed_ui_url = urlsplit(url)
    if parsed_ui_url.path not in {"", "/"} or parsed_ui_url.query or parsed_ui_url.fragment:
        return fail({
            "code": "invalid_ui_base_url",
            "message": "UI scenarios expect a loopback origin; the registered contract supplies the route.",
            "nextAction": "Pass the local Web origin without a path, query, or fragment.",
        }, feature=feature["id"], scenario=scenario["id"], exit_code=2)
    url = f"{parsed_ui_url.scheme}://{parsed_ui_url.netloc}{contract['route']}"
    try:
        raw_input = json.loads(args.input_json)
    except json.JSONDecodeError as exc:
        return fail({
            "code": "invalid_arguments",
            "message": "UI scenario input is not valid JSON.",
            "nextAction": "Pass a JSON object matching the scenario input schema.",
            "details": {"reason": str(exc)},
        }, feature=feature["id"], scenario=scenario["id"], exit_code=2)
    values, error = validate_input(UiSearchScenarioInput, raw_input)
    if error:
        return fail(error, feature=feature["id"], scenario=scenario["id"], exit_code=2)
    input_data = model_data(values)
    readback = scenario["readback"]
    feature_id, operation = operation_by_id(feature_map, readback["operationId"])
    if feature_id != contract["featureId"] or not operation or operation.get("readOnly") is not True or operation.get("method") != "GET":
        return fail({
            "code": "ui_readback_operation_invalid",
            "message": "The registered UI scenario must read back through a GET operation owned by its feature.",
            "nextAction": "Correct the contract to reference a current read-only Feature Map operation.",
        }, feature=feature["id"], scenario=scenario["id"])

    source_before = ui_source_facts(contract)
    runner_request = {
        "mode": "measure" if measure_mode else "scenario",
        "url": url,
        "viewport": {"width": args.viewport_width, "height": args.viewport_height},
        "variantId": variant["id"],
        "input": input_data,
        "scenario": scenario,
        "operation": operation,
    }
    if measure_mode:
        runner_request["repeat"] = args.repeat
        runner_request["datasetSize"] = args.dataset_size
        runner_request["runMode"] = args.run_mode
    browser_result, error = run_ui_driver(runner_request, timeout=max(45, getattr(args, "repeat", 1) * 20))
    if error:
        return fail(error, feature=feature["id"], scenario=scenario["id"])

    openapi, error = openapi_from_service(base_url)
    if error:
        return fail(error, feature=feature["id"], scenario=scenario["id"])
    query = {
        "q": input_data[readback["queryFrom"]],
        "limit": readback["limit"],
    }
    readback_result, error = run_registered_operation(
        base_url,
        feature_map,
        openapi,
        readback["operationId"],
        {"path": {}, "query": query},
    )
    if error:
        return fail(error, feature=feature["id"], scenario=scenario["id"])
    matches = [
        item for item in readback_result["result"]
        if item.get("id") == input_data[readback["containsIdFrom"]]
        and item.get("headline") == input_data["expectedHeadline"]
    ]
    if not matches:
        return fail({
            "code": "ui_readback_assertion_failed",
            "message": "The registered API readback did not contain the expected note identity and headline.",
            "nextAction": "Check the scenario fixture and search operation, then rerun the UI scenario.",
            "details": {"operationId": readback["operationId"], "expectedNoteId": input_data["expectedNoteId"]},
        }, feature=feature["id"], scenario=scenario["id"])

    source_after = ui_source_facts(contract)
    if source_before != source_after:
        return fail({
            "code": "ui_source_changed_during_run",
            "message": "A UI contract source file changed while the browser scenario was running.",
            "nextAction": "Keep the source stable and rerun the registered UI scenario.",
        }, feature=feature["id"], scenario=scenario["id"])

    return emit({
        "status": "measured" if measure_mode else "scenario_passed",
        "feature": feature["id"],
        "contractId": contract["id"],
        "scenario": scenario["id"],
        "result": {
            "browser": browser_result,
            "apiReadback": {
                "operationId": readback_result["operationId"],
                "matchedNoteId": matches[0]["id"],
            },
            "input": {"expectedNoteId": input_data["expectedNoteId"], "queryLength": len(input_data["query"])},
            "source": source_after,
            "manualReviewRequired": contract.get("manualReview", []),
            "scenarioStatus": "scenario_passed",
        },
        "failure": None,
        "nextAction": None,
    })


def run(args: argparse.Namespace) -> int:
    global DEBUG_ENABLED
    DEBUG_ENABLED = bool(args.debug)

    if args.command == "ui":
        return run_ui_command(args)
    if args.command == "dev":
        return run_dev_command(args)

    feature_map, error = (
        feature_map_from_source()
        if args.local_catalog
        else feature_map_from_service(args.base_url)
    )
    if error:
        return fail(error)

    if args.command == "doctor":
        return run_doctor(args.base_url, feature_map)
    if args.command == "feature":
        if args.action == "list":
            return emit({"status": "succeeded", "command": "feature.list", "source": "local" if args.local_catalog else "service", "featureMap": feature_map})
        if args.local_catalog:
            feature = next((item for item in feature_map["features"] if item["id"] == args.feature_id), None)
            if not feature:
                return fail({
                    "code": "unknown_feature",
                    "message": f"Unknown feature: {args.feature_id}",
                    "nextAction": "运行 feature list 并选择已登记的 feature id。",
                }, exit_code=2)
            return emit({"status": "succeeded", "command": "feature.describe", "source": "local", "feature": feature})
        feature, error = get_json(args.base_url, f"/api/features/{quote(args.feature_id, safe='')}")
        if error:
            return fail(error)
        validated, error = validate_response(FeatureOut, feature)
        if error:
            return fail(error)
        return emit({"status": "succeeded", "command": "feature.describe", "source": "service", "feature": model_data(validated)})

    if args.command == "note":
        return run_note_command(args, args.base_url)
    if args.command == "topic":
        return run_topic_command(args, args.base_url)
    if args.command == "api":
        if args.local_catalog and args.action != "call":
            if args.action == "list":
                unique = {}
                for feature_id, operation in registered_operations(feature_map):
                    unique.setdefault(operation["operationId"], {**operation, "feature": feature_id})
                return emit({"status": "succeeded", "command": "api.list", "source": "local", "operations": sorted(unique.values(), key=lambda item: item["operationId"])})
            feature_id, operation = operation_by_id(feature_map, args.operation_id)
            if not operation:
                return fail({
                    "code": "unknown_operation",
                    "message": f"Feature Map 未注册操作 {args.operation_id}。",
                    "nextAction": "运行 api list 并选择已登记的 operationId。",
                }, exit_code=2)
            return emit({"status": "succeeded", "command": "api.describe", "source": "local", "featureId": feature_id, "operation": operation})
        return run_api_command(args, args.base_url, feature_map)

    if args.action == "list":
        catalog, catalog_error = load_ui_contracts()
        if catalog_error:
            return fail(catalog_error)
        ui_coverage = validate_ui_contracts(feature_map)
        if ui_coverage["status"] == "failed":
            return fail({
                "code": "ui_contract_invalid",
                "message": "UI contract registration does not match the current Feature Map.",
                "nextAction": "Run ui check and repair contract registration errors.",
                "details": ui_coverage,
            })
        scenarios = [
            {
                "feature": feature["id"],
                "id": scenario["id"],
                "title": scenario["title"],
                "summary": scenario["summary"],
                "readOnly": scenario.get("readOnly", True),
                "kind": "api",
            }
            for feature in feature_map["features"]
            for scenario in feature.get("scenarios", [])
        ]
        for contract in catalog.model_dump(by_alias=True)["contracts"]:
            scenarios.extend({
                "feature": contract["featureId"],
                "contractId": contract["id"],
                "id": scenario["id"],
                "title": scenario["title"],
                "summary": scenario["summary"],
                "readOnly": True,
                "kind": "ui",
            } for scenario in contract["scenarios"])
        return emit({
            "status": "succeeded",
            "command": "scenario.list",
            "source": "local" if args.local_catalog else "service",
            "uiContractSource": "working-tree",
            "uiCoverage": ui_coverage,
            "scenarios": scenarios,
        })

    if args.action == "describe":
        feature, scenario = scenario_by_id(feature_map, args.scenario_id)
        if scenario:
            return emit({"status": "succeeded", "command": "scenario.describe", "kind": "api", "source": "local" if args.local_catalog else "service", "featureId": feature["id"], "scenario": scenario})
        catalog, catalog_error = load_ui_contracts()
        if catalog_error:
            return fail(catalog_error)
        contract, ui_scenario = find_ui_scenario(catalog, args.scenario_id)
        if contract and ui_scenario:
            ui_coverage = validate_ui_contracts(feature_map, feature_id=contract["featureId"])
            if ui_coverage["status"] != "passed":
                return fail({
                    "code": "ui_contract_invalid",
                    "message": "The UI scenario contract is not valid for the current Feature Map.",
                    "nextAction": "Run ui check for the owning feature and repair contract registration errors.",
                    "details": ui_coverage,
                }, scenario=args.scenario_id)
            return emit({
                "status": "succeeded",
                "command": "scenario.describe",
                "kind": "ui",
                "source": "working-tree",
                "featureId": contract["featureId"],
                "contract": contract,
                "scenario": ui_scenario,
            })
        if not scenario:
            error = {
                "code": "unknown_scenario",
                "message": f"Unknown scenario: {args.scenario_id}",
                "nextAction": "运行 scenario list 并使用已注册场景。",
            }
            return fail(error, exit_code=2)

    if args.action == "run":
        catalog, catalog_error = load_ui_contracts()
        if catalog_error:
            return fail(catalog_error)
        contract, ui_scenario = find_ui_scenario(catalog, args.scenario_id)
        if contract and ui_scenario:
            return run_ui_scenario(args, args.base_url, feature_map, contract, ui_scenario)

    return run_scenario(args, args.base_url, feature_map)


def add_note_list_arguments(parser: argparse.ArgumentParser, *, scenario: bool) -> None:
    parser.add_argument("--topic-id", type=int, required=not scenario)
    if scenario:
        parser.add_argument("--contains-note-id", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--cursor")
    parser.add_argument("--direction", type=int, choices=(-1, 1), default=1)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="chronicle", description="Chronicle Feature Map CLI")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("CHRONICLE_URL", ROOT_URL_DEFAULT),
        help="Chronicle API base URL (default: CHRONICLE_URL or http://127.0.0.1:8000)",
    )
    parser.add_argument("--debug", action="store_true", help="Write HTTP diagnostics to stderr while keeping stdout JSON.")
    parser.add_argument("--local-catalog", action="store_true", help="Use the working-tree Feature Map for discovery; execution still uses the HTTP API.")
    commands = parser.add_subparsers(dest="command", required=True)

    feature = commands.add_parser("feature", help="Discover the registered Feature Map")
    feature_actions = feature.add_subparsers(dest="action", required=True)
    feature_actions.add_parser("list", help="Return the Feature Map")
    describe = feature_actions.add_parser("describe", help="Expand one feature")
    describe.add_argument("feature_id")

    note = commands.add_parser("note", help="Read notes through named API operations")
    note_actions = note.add_subparsers(dest="action", required=True)
    read = note_actions.add_parser("get", help="Read one note detail")
    read.add_argument("--note-id", type=int, required=True)
    listing = note_actions.add_parser("list", help="Read a page from one topic")
    add_note_list_arguments(listing, scenario=False)
    search = note_actions.add_parser("search", help="Search live notes")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=20)

    topic = commands.add_parser("topic", help="Read the notebook directory")
    topic_actions = topic.add_subparsers(dest="action", required=True)
    topic_actions.add_parser("list", help="List notebooks")
    topic_get = topic_actions.add_parser("get", help="Read notebook metadata")
    topic_get.add_argument("--topic-id", type=int, required=True)

    api = commands.add_parser("api", help="Discover and invoke named Feature Map API operations")
    api_actions = api.add_subparsers(dest="action", required=True)
    api_actions.add_parser("list", help="List API operations in the Feature Map")
    api_describe = api_actions.add_parser("describe", help="Expand one API operation and its schemas")
    api_describe.add_argument("operation_id")
    api_call = api_actions.add_parser("call", help="Call a registered API operation; writes require --confirm")
    api_call.add_argument("operation_id")
    api_call.add_argument("--confirm", action="store_true", help="Confirm the write described by this operation")
    api_call.add_argument("--output-file", help="Create a new local file for a registered binary response; existing files are never overwritten")
    api_inputs = api_call.add_mutually_exclusive_group()
    api_inputs.add_argument("--input-json", help="UTF-8 JSON object with path, query, headers, body, and optional file fields")
    api_inputs.add_argument("--input-file", help="Path to UTF-8 JSON input with path, query, headers, body, and optional file fields")

    commands.add_parser("doctor", help="Check live API catalog alignment and runtime identity")

    dev = commands.add_parser("dev", help="Manage CLI-owned isolated API and Vite development processes")
    dev_actions = dev.add_subparsers(dest="action", required=True)
    dev_up = dev_actions.add_parser("up", help="Start an isolated API and Vite session")
    dev_up.add_argument("--api-port", type=int, help="API loopback port; omitted selects an available port")
    dev_up.add_argument("--ui-port", type=int, help="UI loopback port; omitted selects an available port")
    dev_actions.add_parser("sessions", help="List CLI-managed development sessions")
    dev_status = dev_actions.add_parser("status", help="Inspect a managed session without stopping anything")
    dev_status.add_argument("--run-id", help="Inspect a specific session from dev up output")
    dev_doctor = dev_actions.add_parser("doctor", help="Run API catalog and runtime checks against a managed session")
    dev_doctor.add_argument("--run-id", help="Check a specific session from dev up output")
    dev_logs = dev_actions.add_parser("logs", help="Read logs from the managed API or UI process")
    dev_logs.add_argument("--service", choices=("api", "ui", "all"), default="all")
    dev_logs.add_argument("--lines", type=int, choices=range(1, 1001), default=80)
    dev_logs.add_argument("--run-id", help="Read logs from a specific session")
    dev_down = dev_actions.add_parser("down", help="Stop only processes owned by the managed process manager")
    dev_down.add_argument("--run-id", help="Stop a specific session from dev up output")

    ui = commands.add_parser("ui", help="Discover and inspect registered UI contracts")
    ui_actions = ui.add_subparsers(dest="action", required=True)
    ui_guide = ui_actions.add_parser("guide", help="Read UI contract states, variants, and scenarios")
    ui_guide.add_argument("--feature", dest="feature_id")
    ui_guide.add_argument("--contract", dest="contract_id")
    ui_check = ui_actions.add_parser("check", help="Validate UI contract schema and Feature Map bindings")
    ui_check.add_argument("--feature", dest="feature_id")
    ui_inspect = ui_actions.add_parser("inspect", help="Observe a real local page and accessibility tree")
    ui_inspect.add_argument("--url", required=True)
    ui_inspect.add_argument("--viewport-width", type=int, default=1280)
    ui_inspect.add_argument("--viewport-height", type=int, default=900)
    ui_measure = ui_actions.add_parser("measure", help="Measure a registered UI scenario with repeated real browser runs")
    ui_measure.add_argument("scenario_id")
    ui_measure.add_argument("--ui-url", required=True)
    ui_measure.add_argument("--input-json", required=True)
    ui_measure.add_argument("--repeat", type=int, default=5)
    ui_measure.add_argument("--dataset-size", type=int, required=True)
    ui_measure.add_argument("--run-mode", choices=("development", "preview", "production"), required=True)
    ui_measure.add_argument("--viewport-width", type=int, default=1280)
    ui_measure.add_argument("--viewport-height", type=int, default=900)

    scenario = commands.add_parser("scenario", help="Discover or run registered scenarios")
    scenario_actions = scenario.add_subparsers(dest="action", required=True)
    scenario_actions.add_parser("list", help="List registered scenarios")
    describe_scenario = scenario_actions.add_parser("describe", help="Expand one scenario and its steps")
    describe_scenario.add_argument("scenario_id")
    run_scenario_parser = scenario_actions.add_parser("run", help="Run a registered read-only scenario")
    run_scenario_parser.add_argument("scenario_id")
    run_scenario_parser.add_argument("--note-id", type=int)
    add_note_list_arguments(run_scenario_parser, scenario=True)
    run_scenario_parser.add_argument("--query")
    run_scenario_parser.add_argument("--expected-note-id", type=int)
    run_scenario_parser.add_argument("--ui-url")
    run_scenario_parser.add_argument("--input-json")
    run_scenario_parser.add_argument("--viewport-width", type=int, default=1280)
    run_scenario_parser.add_argument("--viewport-height", type=int, default=900)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
