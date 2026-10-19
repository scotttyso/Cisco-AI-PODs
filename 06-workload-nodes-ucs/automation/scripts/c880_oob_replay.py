"""Pure offline replay of C880 OOB update decisions and task transitions.

No network, credentials, files, upload, reset or boot transport exists here.
Catalog deadlines and poll spacing come from local Cisco script v1.2 source.
This exercises the future updater's control flow without reflashing a pilot.
It is NOT a supported live firmware executor or HUU implementation.
"""

import re


TIMEOUTS = {"BMC": 2700, "BIOS": 2700, "GPU": 2400,
            "DCSCM-CPLD": 2700, "MB-CPLD": 3600,
            "E1S-BP-CPLD": 1800, "BP-CPLD": 2100,
            "EROT-BMC": 300, "EROT-BIOS": 300}
POLL_SECONDS = 30
INTER_COMPONENT_SECONDS = 20
TASK_PATH = re.compile(r"^/redfish/v1/TaskService/Tasks/[0-9]+$")
FAILURES = {"Exception", "Interrupted", "Suspended", "Killed", "Cancelled"}
ACTIVE = {"New", "Starting", "Running", "Pending"}


def _version(component, value):
    if not isinstance(value, str) or len(value) > 128:
        return None
    if component == "BMC":
        match = re.fullmatch(r"([0-9]+)\.([0-9]+)\(([0-9]+)\.([0-9]+)\)", value)
        if match:
            return tuple(int(part) for part in match.groups())
    fields = 3 if component.startswith("EROT-") else 4
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){" + str(fields - 1) + r"}", value):
        return None
    return tuple(int(part) for part in value.split("."))


def choose_action(component, current, target):
    """Never equate an exact mismatch with permission to reflash/downgrade."""
    if component not in TIMEOUTS:
        raise ValueError("Component outside reviewed OOB scope")
    if component == "GPU":
        # Cross-branch composite GPU ordering needs a verified component policy.
        valid = re.compile(r"^[0-9A-F]{2}(?:\.[0-9A-F]{2}){4}-G[0-9]{3}\.[0-9]{4}\.[0-9]{2}\.[0-9]{2}$")
        if (not isinstance(current, str) or not isinstance(target, str)
                or not valid.fullmatch(current) or not valid.fullmatch(target)):
            return "blocked_version_unverified"
        return "skip_already_target" if current == target else "blocked_gpu_order_review"
    running, packaged = _version(component, current), _version(component, target)
    if (running is None or packaged is None or not any(running) or not any(packaged)
            or running[:2] == (0, 0) or packaged[:2] == (0, 0)):
        return "blocked_version_unverified"
    if running == packaged:
        return "skip_already_target"
    if running[:2] != packaged[:2]:
        return "blocked_release_family_review"
    return "blocked_downgrade" if running > packaged else "replay_upgrade_candidate"


def _task_path(submission):
    body = submission.get("body")
    messages = body.get("Messages") if isinstance(body, dict) else None
    if not isinstance(messages, list) or len(messages) > 16:
        return None
    paths = []
    for message in messages:
        if not isinstance(message, dict) or message.get("MessageId") != "Task.1.0.New":
            continue
        arguments = message.get("MessageArgs")
        if (not isinstance(arguments, list) or len(arguments) != 1
                or not isinstance(arguments[0], str) or not TASK_PATH.fullmatch(arguments[0])):
            return None
        paths.append(arguments[0])
    return paths[0] if len(paths) == 1 else None


def replay(component, current, target, submission=None, samples=()):
    """Consume recorded/synthetic outcomes, never cause a submission or poll.

Each sample carries elapsed_seconds since submission. An ambiguous upload is
never resubmitted. Task completion is not activation or independent readback.
"""
    action = choose_action(component, current, target)
    result = {"mode": "offline_replay", "component": component, "action": action,
              "decision": action, "simulated_uploads": 0, "simulated_task_reads": 0,
              "catalog_deadline_seconds": TIMEOUTS[component],
              "minimum_poll_seconds": POLL_SECONDS,
              "minimum_inter_component_seconds": INTER_COMPONENT_SECONDS,
              "resubmit_permitted": False, "automatic_activation_permitted": False,
              "activation_and_independent_readback_required": False,
              "live_execution_implemented": False, "network_requests": 0,
              "upgrade_signoff": False}
    if action != "replay_upgrade_candidate":
        return result
    result["simulated_uploads"] = 1
    if not isinstance(submission, dict) or submission.get("outcome") == "ambiguous":
        result["decision"] = "stop_submission_ambiguous_no_retry"
        return result
    if submission.get("http_status") not in (200, 202) or not _task_path(submission):
        result["decision"] = "stop_submission_unverified_no_retry"
        return result
    if not isinstance(samples, (list, tuple)) or len(samples) > TIMEOUTS[component] // POLL_SECONDS:
        raise ValueError("Task replay exceeds bounded read budget")
    previous = 0
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("Malformed replay sample")
        elapsed = sample.get("elapsed_seconds")
        if type(elapsed) is not int or elapsed - previous < POLL_SECONDS:
            raise ValueError("Task replay violates poll spacing")
        if elapsed >= TIMEOUTS[component]:
            result["decision"] = "stop_deadline_no_retry"
            return result
        previous = elapsed
        result["simulated_task_reads"] += 1
        state, status, percent = sample.get("TaskState"), sample.get("TaskStatus"), sample.get("PercentComplete")
        if state in FAILURES or status == "Critical":
            result["decision"] = "stop_task_failure_no_retry"
            return result
        if state == "Completed":
            if status != "OK" or type(percent) is not int or percent != 100:
                result["decision"] = "stop_completion_unverified_no_retry"
                return result
            result["decision"] = "task_completed_activation_readback_still_required"
            result["activation_and_independent_readback_required"] = True
            return result
        if state not in ACTIVE or status not in ("OK", "Warning", None):
            result["decision"] = "stop_unknown_task_state_no_retry"
            return result
    result["decision"] = "task_incomplete_observation_only"
    result["next_poll_not_before_elapsed_seconds"] = previous + POLL_SECONDS
    return result
