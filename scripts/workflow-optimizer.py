#!/usr/bin/env python3
import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path("/Users/mikehayes/Documents/Store Menus")
STATE_PATH = ROOT / "data/workflow-optimization.json"
REPORT_JSON_PATH = ROOT / "data/workflow-optimization-report.json"
REPORT_MD_PATH = ROOT / "data/workflow-optimization-report.md"
MAX_RECENT_EVENTS = 400
MAX_RECENT_RUNS = 60


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_from_ms(value_ms: Optional[int]) -> Optional[str]:
    if value_ms is None:
        return None
    return datetime.fromtimestamp(value_ms / 1000, tz=timezone.utc).isoformat()


def ms_from_iso(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"version": 2, "updated_at": None, "workflows": {}}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    temp_path = STATE_PATH.with_name(f"{STATE_PATH.stem}.{os.getpid()}.tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(STATE_PATH)


def write_report(workflow: str, summary: dict) -> None:
    REPORT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"Workflow: {workflow}",
        f"Updated: {summary.get('updated_at') or 'unknown'}",
        "",
        "Slowest steps:",
    ]
    slow_steps = summary.get("slow_steps", [])
    if slow_steps:
        for item in slow_steps:
            lines.append(
                f"- {item['step']}: avg {round(item['avg_duration_ms'] / 1000, 2)}s "
                f"(success {round(item['success_rate'] * 100)}%)"
            )
    else:
        lines.append("- none yet")

    lines.append("")
    lines.append("Most failure-prone steps:")
    failure_steps = summary.get("failure_prone_steps", [])
    if failure_steps:
        for item in failure_steps:
            lines.append(
                f"- {item['step']}: failure rate {round(item['failure_rate'] * 100)}% "
                f"over {item['attempts']} attempts"
            )
    else:
        lines.append("- none yet")

    lines.append("")
    lines.append("Suggested improvements:")
    improvements = summary.get("optimizations", [])
    if improvements:
        for item in improvements:
            before_text = (
                f", before {round(item['before_avg_duration_ms'] / 1000, 2)}s"
                if item.get("before_avg_duration_ms") is not None
                else ""
            )
            after_text = (
                f", after {round(item['after_avg_duration_ms'] / 1000, 2)}s"
                if item.get("after_avg_duration_ms") is not None
                else ""
            )
            lines.append(
                f"- {item['step']}: {item['suggested_improvement']} "
                f"[applied={item['applied']}, disabled={item['disabled']}{before_text}{after_text}]"
            )
    else:
        lines.append("- none yet")

    REPORT_MD_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def zero_stats() -> dict:
    return {
        "attempts": 0,
        "successes": 0,
        "failures": 0,
        "total_duration_ms": 0,
        "total_wait_ms": 0,
        "total_mouse_distance_px": 0,
        "total_retries": 0,
    }


def update_stats(stats: dict, status: str, duration_ms: int, wait_ms: int, mouse_distance_px: int, retries: int) -> None:
    stats["attempts"] += 1
    if status == "success":
        stats["successes"] += 1
    else:
        stats["failures"] += 1
    stats["total_duration_ms"] += max(duration_ms, 0)
    stats["total_wait_ms"] += max(wait_ms, 0)
    stats["total_mouse_distance_px"] += max(mouse_distance_px, 0)
    stats["total_retries"] += max(retries, 0)


def average(stats: dict, field: str) -> float:
    attempts = stats.get("attempts", 0) or 0
    if attempts <= 0:
        return 0.0
    return float(stats.get(field, 0)) / attempts


def success_rate(stats: dict) -> float:
    attempts = stats.get("attempts", 0) or 0
    if attempts <= 0:
        return 0.5
    return float(stats.get("successes", 0)) / attempts


def failure_rate(stats: dict) -> float:
    attempts = stats.get("attempts", 0) or 0
    if attempts <= 0:
        return 0.0
    return float(stats.get("failures", 0)) / attempts


def classify_action_type(action_type: str, method: str) -> str:
    value = (action_type or method or "").lower()
    if "api" in value:
        return "api call"
    if "batch" in value:
        return "batch"
    if any(token in value for token in ["selector", "role", "text", "element", "dom"]):
        return "selector targeting"
    if "keyboard" in value or "shortcut" in value:
        return "keyboard shortcut"
    if any(token in value for token in ["coordinate", "mouse", "click"]):
        return "mouse click"
    if "wait" in value or "poll" in value:
        return "wait"
    if "retry" in value:
        return "retry"
    if "manual" in value or "handoff" in value or "user" in value:
        return "manual/user input"
    return "other"


def classify_method(method: str) -> str:
    return classify_action_type("", method).replace(" ", "-")


METHOD_CLASS_PRIORITY = {
    "api-call": 0,
    "batch": 1,
    "selector-targeting": 2,
    "keyboard-shortcut": 3,
    "wait": 4,
    "other": 5,
    "mouse-click": 6,
    "manual/user-input": 7,
}


def ensure_workflow(state: dict, workflow: str) -> dict:
    workflows = state.setdefault("workflows", {})
    return workflows.setdefault(
        workflow,
        {
            "created_at": utc_now(),
            "steps": {},
            "runs": [],
            "run_index": {},
        },
    )


def ensure_step(state: dict, workflow: str, step: str) -> dict:
    workflow_state = ensure_workflow(state, workflow)
    return workflow_state["steps"].setdefault(
        step,
        {
            "recent_events": [],
            "stats": zero_stats(),
            "methods": {},
            "last_used_method": None,
            "baseline_method": None,
            "applied_optimization": None,
        },
    )


def ensure_method(step_state: dict, method: str, action_type: str) -> dict:
    methods = step_state.setdefault("methods", {})
    method_state = methods.setdefault(
        method,
        {
            "class": classify_method(method),
            "action_type": action_type or classify_action_type("", method),
            "stats": zero_stats(),
            "recent_events": [],
            "disabled": False,
            "disabled_reason": None,
            "disabled_at": None,
        },
    )
    if action_type and not method_state.get("action_type"):
        method_state["action_type"] = action_type
    return method_state


def ensure_run(workflow_state: dict, run_id: str, started_at: Optional[str], ended_at: Optional[str]) -> dict:
    run_index = workflow_state.setdefault("run_index", {})
    if run_id in run_index:
        run = run_index[run_id]
        if started_at and not run.get("started_at"):
            run["started_at"] = started_at
        if ended_at:
            run["ended_at"] = ended_at
        return run

    run = {
        "run_id": run_id,
        "started_at": started_at or utc_now(),
        "ended_at": ended_at,
        "steps": [],
    }
    workflow_state.setdefault("runs", []).append(run)
    workflow_state["runs"] = workflow_state["runs"][-MAX_RECENT_RUNS:]
    workflow_state["run_index"] = {item["run_id"]: item for item in workflow_state["runs"]}
    return run


def compress_recent_events(events: List[dict]) -> List[dict]:
    return events[-MAX_RECENT_EVENTS:]


def recent_method_events(step_state: dict, method: str, limit: int = 5) -> List[dict]:
    events = [
        event for event in step_state.get("recent_events", [])
        if event.get("method") == method
    ]
    return events[-limit:]


def method_sort_key(step_state: dict, method: str, original_index: int) -> Tuple[float, int, float, float, float, int]:
    method_state = step_state.get("methods", {}).get(method, {})
    stats = method_state.get("stats", zero_stats())
    disabled = method_state.get("disabled", False)
    category = classify_method(method)
    avg_duration_ms = average(stats, "total_duration_ms") or (0.0 if stats.get("attempts", 0) == 0 else math.inf)
    avg_wait_ms = average(stats, "total_wait_ms")
    avg_mouse_px = average(stats, "total_mouse_distance_px")
    return (
        1.0 if disabled else 0.0,
        -success_rate(stats),
        METHOD_CLASS_PRIORITY.get(category, 99),
        avg_duration_ms if avg_duration_ms else 0.0,
        avg_wait_ms + avg_mouse_px,
        original_index,
    )


def evaluate_method_safeguards(step_state: dict, method: str) -> None:
    method_state = step_state.get("methods", {}).get(method)
    if not method_state:
      return

    recent_events = recent_method_events(step_state, method, limit=4)
    if len(recent_events) < 3:
        return

    recent_failures = sum(1 for event in recent_events if event.get("status") != "success")
    recent_success_rate = 1 - (recent_failures / len(recent_events))
    recent_avg_duration = sum(event.get("duration_ms", 0) for event in recent_events) / len(recent_events)

    baseline_method = step_state.get("baseline_method")
    baseline_state = step_state.get("methods", {}).get(baseline_method or "", {})
    baseline_stats = baseline_state.get("stats", zero_stats())
    baseline_avg_duration = average(baseline_stats, "total_duration_ms") or None
    baseline_success = success_rate(baseline_stats)

    is_non_baseline = baseline_method and method != baseline_method
    regression = False
    regression_reason = None

    if recent_success_rate < 0.5 and recent_failures >= 2:
        regression = True
        regression_reason = "recent failure rate exceeded safeguard threshold"
    elif (
        is_non_baseline
        and baseline_avg_duration
        and recent_avg_duration > baseline_avg_duration * 1.5
        and recent_success_rate <= baseline_success
    ):
        regression = True
        regression_reason = "optimized method regressed versus baseline timing"

    if regression:
        method_state["disabled"] = True
        method_state["disabled_reason"] = regression_reason
        method_state["disabled_at"] = utc_now()
        if step_state.get("applied_optimization", {}).get("method") == method:
            step_state["applied_optimization"]["status"] = "rolled_back"
            step_state["applied_optimization"]["reason"] = regression_reason


def infer_improvement(step_name: str, current_method: str, recommended_method: str) -> str:
    current_class = classify_action_type("", current_method)
    recommended_class = classify_action_type("", recommended_method)
    if current_class == "mouse click" and recommended_class == "selector targeting":
        return "Replace coordinate-based mouse clicks with reliable selectors."
    if current_class == "mouse click" and recommended_class == "keyboard shortcut":
        return "Replace repeated mouse clicks with a safer keyboard shortcut."
    if current_class == "wait" and recommended_class != "wait":
        return "Replace fixed waits with state-based readiness checks."
    if recommended_class == "api call":
        return "Use an available API instead of UI automation for this step."
    if recommended_class == "batch":
        return "Batch repeated operations to reduce repeated UI work."
    if recommended_class == "selector targeting":
        return "Use direct element targeting instead of slower UI navigation."
    return f"Prefer {recommended_method} for {step_name}."


def has_meaningful_improvement(step_state: dict, current_method: Optional[str], recommended_method: Optional[str]) -> bool:
    if not current_method or not recommended_method:
        return False
    if current_method == recommended_method:
        current_stats = step_state.get("methods", {}).get(current_method, {}).get("stats", zero_stats())
        recommended_stats = step_state.get("methods", {}).get(recommended_method, {}).get("stats", zero_stats())
        return average(recommended_stats, "total_duration_ms") + 1 < average(current_stats, "total_duration_ms")
    return True


def best_method_for_step(step_state: dict) -> Optional[str]:
    methods = list(step_state.get("methods", {}).keys())
    if not methods:
        return None
    ordered = sorted(methods, key=lambda method: method_sort_key(step_state, method, methods.index(method)))
    return ordered[0] if ordered else None


def build_summary(state: dict, workflow: str) -> dict:
    workflow_state = state.get("workflows", {}).get(workflow, {})
    steps = workflow_state.get("steps", {})
    slow_steps: List[dict] = []
    failure_prone_steps: List[dict] = []
    unnecessary_waits: List[dict] = []
    replaceable_ui_actions: List[dict] = []
    optimizations: List[dict] = []

    for step_name, step_state in steps.items():
        step_stats = step_state.get("stats", zero_stats())
        attempts = step_stats.get("attempts", 0)
        if not attempts:
            continue

        avg_duration_ms = average(step_stats, "total_duration_ms")
        avg_wait_ms = average(step_stats, "total_wait_ms")
        avg_mouse_px = average(step_stats, "total_mouse_distance_px")
        avg_retries = average(step_stats, "total_retries")
        wait_ratio = (avg_wait_ms / avg_duration_ms) if avg_duration_ms else 0.0
        best_method = best_method_for_step(step_state)
        current_method = step_state.get("last_used_method") or best_method
        baseline_method = step_state.get("baseline_method")
        current_method_state = step_state.get("methods", {}).get(current_method or "", {})
        best_method_state = step_state.get("methods", {}).get(best_method or "", {})

        slow_steps.append(
            {
                "step": step_name,
                "avg_duration_ms": round(avg_duration_ms, 1),
                "avg_wait_ms": round(avg_wait_ms, 1),
                "avg_mouse_distance_px": round(avg_mouse_px, 1),
                "avg_retries": round(avg_retries, 2),
                "success_rate": round(success_rate(step_stats), 3),
            }
        )
        failure_prone_steps.append(
            {
                "step": step_name,
                "failure_rate": round(failure_rate(step_stats), 3),
                "attempts": attempts,
                "avg_retries": round(avg_retries, 2),
            }
        )

        if wait_ratio >= 0.25 and avg_wait_ms >= 1000:
            unnecessary_waits.append(
                {
                    "step": step_name,
                    "avg_wait_ms": round(avg_wait_ms, 1),
                    "wait_ratio": round(wait_ratio, 3),
                    "suggested_improvement": "Replace fixed waits with state-based waits where safe.",
                }
            )

        coordinate_methods = [
            method_name
            for method_name in step_state.get("methods", {})
            if classify_action_type("", method_name) == "mouse click"
        ]
        direct_methods = [
            method_name
            for method_name in step_state.get("methods", {})
            if classify_action_type("", method_name) in {"selector targeting", "keyboard shortcut", "api call", "batch"}
        ]
        if coordinate_methods and direct_methods:
            slow_mouse_method = sorted(
                coordinate_methods,
                key=lambda name: method_sort_key(step_state, name, coordinate_methods.index(name)),
            )[0]
            best_direct_method = sorted(
                direct_methods,
                key=lambda name: method_sort_key(step_state, name, direct_methods.index(name)),
            )[0]
            replaceable_ui_actions.append(
                {
                    "step": step_name,
                    "current_method": slow_mouse_method,
                    "recommended_method": best_direct_method,
                    "suggested_improvement": infer_improvement(step_name, slow_mouse_method, best_direct_method),
                }
            )

        if best_method and has_meaningful_improvement(step_state, baseline_method or current_method, best_method):
            before_stats = step_state.get("methods", {}).get(baseline_method or current_method or "", {}).get("stats", zero_stats())
            after_stats = best_method_state.get("stats", zero_stats())
            best_state = step_state.get("methods", {}).get(best_method, {})
            applied = step_state.get("applied_optimization", {})
            optimizations.append(
                {
                    "step": step_name,
                    "suggested_improvement": infer_improvement(step_name, current_method or "", best_method),
                    "recommended_method": best_method,
                    "current_method": current_method,
                    "applied": bool(applied and applied.get("method") == best_method and applied.get("status") == "active"),
                    "disabled": bool(best_state.get("disabled")),
                    "disabled_reason": best_state.get("disabled_reason"),
                    "before_avg_duration_ms": round(average(before_stats, "total_duration_ms"), 1) if before_stats.get("attempts") else None,
                    "after_avg_duration_ms": round(average(after_stats, "total_duration_ms"), 1) if after_stats.get("attempts") else None,
                    "applied_method": applied.get("method") if applied else None,
                    "applied_status": applied.get("status") if applied else None,
                }
            )

    slow_steps.sort(key=lambda item: item["avg_duration_ms"], reverse=True)
    failure_prone_steps.sort(key=lambda item: (item["failure_rate"], item["avg_retries"]), reverse=True)
    unnecessary_waits.sort(key=lambda item: item["avg_wait_ms"], reverse=True)
    replaceable_ui_actions.sort(key=lambda item: item["step"])
    optimizations.sort(
        key=lambda item: (
            item["disabled"],
            not item["applied"],
            -1 if item["before_avg_duration_ms"] is None else item["before_avg_duration_ms"],
        )
    )

    return {
        "workflow": workflow,
        "updated_at": state.get("updated_at"),
        "slow_steps": slow_steps[:5],
        "failure_prone_steps": failure_prone_steps[:5],
        "unnecessary_waits": unnecessary_waits[:5],
        "replaceable_ui_actions": replaceable_ui_actions[:5],
        "optimizations": optimizations[:8],
        "recent_runs": workflow_state.get("runs", [])[-10:],
    }


def cmd_record_step(args: argparse.Namespace) -> int:
    state = load_state()
    workflow_state = ensure_workflow(state, args.workflow)
    step_state = ensure_step(state, args.workflow, args.step)

    started_at = args.started_at or iso_from_ms(args.started_at_ms) or utc_now()
    ended_at = args.ended_at or iso_from_ms(args.ended_at_ms) or utc_now()
    duration_ms = args.duration_ms
    if duration_ms is None:
        start_ms = ms_from_iso(started_at)
        end_ms = ms_from_iso(ended_at)
        duration_ms = max(0, (end_ms or 0) - (start_ms or 0))

    action_type = args.action_type or classify_action_type("", args.method)
    event = {
        "run_id": args.run_id,
        "step": args.step,
        "start_time": started_at,
        "end_time": ended_at,
        "duration_ms": duration_ms,
        "action_type": action_type,
        "method": args.method,
        "status": args.status,
        "retries": args.retries,
        "wait_ms": args.wait_ms,
        "mouse_distance_px": args.mouse_distance_px,
        "error_message": args.error_message,
        "failure_reason": args.error_message,
        "user_override": args.user_override,
        "user_correction": args.user_correction,
        "notes": args.notes,
    }
    if args.metadata_json:
        event["metadata"] = json.loads(args.metadata_json)

    step_state["recent_events"].append(event)
    step_state["recent_events"] = compress_recent_events(step_state["recent_events"])
    update_stats(step_state["stats"], args.status, duration_ms, args.wait_ms, args.mouse_distance_px, args.retries)
    step_state["last_used_method"] = args.method
    if not step_state.get("baseline_method"):
        step_state["baseline_method"] = args.method

    method_state = ensure_method(step_state, args.method, action_type)
    method_state["recent_events"].append(event)
    method_state["recent_events"] = compress_recent_events(method_state["recent_events"])
    update_stats(method_state["stats"], args.status, duration_ms, args.wait_ms, args.mouse_distance_px, args.retries)

    if args.user_override or args.user_correction:
        method_state["last_user_override"] = {
            "at": utc_now(),
            "value": args.user_override or args.user_correction,
        }

    if args.run_id:
        run = ensure_run(workflow_state, args.run_id, started_at, ended_at)
        run["steps"].append(event)
        run["steps"] = run["steps"][-MAX_RECENT_EVENTS:]
        run["ended_at"] = ended_at

    evaluate_method_safeguards(step_state, args.method)

    best_method = best_method_for_step(step_state)
    if best_method and not step_state.get("methods", {}).get(best_method, {}).get("disabled"):
        step_state["applied_optimization"] = {
            "method": best_method,
            "status": "active" if step_state.get("last_used_method") == best_method else "pending",
            "updated_at": utc_now(),
        }

    save_state(state)
    summary = build_summary(state, args.workflow)
    write_report(args.workflow, summary)
    print(json.dumps({"ok": True}))
    return 0


def cmd_method_order(args: argparse.Namespace) -> int:
    state = load_state()
    step_state = ensure_step(state, args.workflow, args.step)
    methods = [item for item in args.methods.split(",") if item]
    ordered = sorted(methods, key=lambda method: method_sort_key(step_state, method, methods.index(method)))
    print(json.dumps({"methods": ordered}, indent=2))
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    state = load_state()
    summary = build_summary(state, args.workflow)
    write_report(args.workflow, summary)
    print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    record_step = subparsers.add_parser("record-step")
    record_step.add_argument("--workflow", required=True)
    record_step.add_argument("--run-id")
    record_step.add_argument("--step", required=True)
    record_step.add_argument("--status", required=True, choices=["success", "failure"])
    record_step.add_argument("--started-at")
    record_step.add_argument("--ended-at")
    record_step.add_argument("--started-at-ms", type=int)
    record_step.add_argument("--ended-at-ms", type=int)
    record_step.add_argument("--duration-ms", type=int)
    record_step.add_argument("--action-type", default="")
    record_step.add_argument("--wait-ms", type=int, default=0)
    record_step.add_argument("--mouse-distance-px", type=int, default=0)
    record_step.add_argument("--method", required=True)
    record_step.add_argument("--retries", type=int, default=0)
    record_step.add_argument("--error-message", default="")
    record_step.add_argument("--user-override", default="")
    record_step.add_argument("--user-correction", default="")
    record_step.add_argument("--notes", default="")
    record_step.add_argument("--metadata-json")
    record_step.set_defaults(func=cmd_record_step)

    method_order = subparsers.add_parser("method-order")
    method_order.add_argument("--workflow", required=True)
    method_order.add_argument("--step", required=True)
    method_order.add_argument("--methods", required=True)
    method_order.set_defaults(func=cmd_method_order)

    summary = subparsers.add_parser("summary")
    summary.add_argument("--workflow", required=True)
    summary.set_defaults(func=cmd_summary)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
