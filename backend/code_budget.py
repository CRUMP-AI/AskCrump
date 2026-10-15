"""Fail-closed, Code-only provider admission. Amounts are integer USD millionths.

This is separate from customer credits and existing video/Gateway accounting.
No model aliases or prices are inferred. The operator must supply an approved
maximum input rate (including any cache-write premium) and output rate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
import re
from typing import Any, Mapping


class CodeBudgetError(RuntimeError):
    def __init__(self, message: str, code: str = "CODE_PROVIDER_BUDGET_UNAVAILABLE") -> None:
        super().__init__(message)
        self.code = code
        self.status_code = 409 if code.endswith(("CONFLICT", "UNCERTAIN")) else 503


def _positive(value: Any, name: str, maximum: int = 10**12) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]{0,12}", str(value or "")):
        raise CodeBudgetError(f"Crump Code requires an explicit positive {name}.", "CODE_BUDGET_NOT_CONFIGURED")
    result = int(value)
    if result > maximum:
        raise CodeBudgetError(f"Crump Code {name} exceeds its supported bound.", "CODE_BUDGET_NOT_CONFIGURED")
    return result


@dataclass(frozen=True, slots=True)
class CodeBudgetPolicy:
    model: str
    input_rate: int
    output_rate: int
    max_input_bytes: int
    max_output_tokens: int
    call_limit: int
    run_limit: int
    account_daily_limit: int
    global_daily_limit: int

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{1,119}", self.model):
            raise CodeBudgetError("An exact approved coding model is required.", "CODE_BUDGET_NOT_CONFIGURED")
        for key, value in asdict(self).items():
            if key != "model":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise CodeBudgetError(f"Code budget {key} must be an integer.", "CODE_BUDGET_NOT_CONFIGURED")
                _positive(value, key, 2_000_000 if key == "max_input_bytes" else 16_384 if key == "max_output_tokens" else 10**12)
        if not self.call_limit <= self.run_limit <= self.account_daily_limit <= self.global_daily_limit:
            raise CodeBudgetError("Code budget limits must increase from call through global.", "CODE_BUDGET_NOT_CONFIGURED")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> CodeBudgetPolicy:
        source = os.environ if environ is None else environ
        names = {
            "input_rate": "INPUT_USD_MICROS_PER_MILLION", "output_rate": "OUTPUT_USD_MICROS_PER_MILLION",
            "max_input_bytes": "MAX_INPUT_BYTES", "max_output_tokens": "MAX_OUTPUT_TOKENS",
            "call_limit": "CALL_USD_MICROS", "run_limit": "RUN_USD_MICROS",
            "account_daily_limit": "ACCOUNT_DAILY_USD_MICROS", "global_daily_limit": "GLOBAL_DAILY_USD_MICROS",
        }
        return cls(model=str(source.get("CODE_PROVIDER_MODEL", "")).strip(), **{
            field: _positive(source.get(f"CODE_PROVIDER_{suffix}"), field) for field, suffix in names.items()
        })

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def price(self, input_tokens: int, output_tokens: int) -> int:
        return (input_tokens * self.input_rate + output_tokens * self.output_rate + 999_999) // 1_000_000

    def request_details(self, body: dict[str, Any]) -> tuple[str, int, int, int]:
        if not isinstance(body, dict) or body.get("model") != self.model:
            raise CodeBudgetError("Coding model does not match the approved price policy.", "CODE_BUDGET_MODEL_MISMATCH")
        output = body.get("max_tokens")
        if isinstance(output, bool) or not isinstance(output, int) or not 1 <= output <= self.max_output_tokens:
            raise CodeBudgetError("Coding output exceeds the approved bound.", "CODE_BUDGET_REQUEST_TOO_LARGE")
        try:
            encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, UnicodeError) as exc:
            raise CodeBudgetError("The coding request is not bounded JSON.", "CODE_BUDGET_REQUEST_INVALID") from exc
        if len(encoded) > self.max_input_bytes:
            raise CodeBudgetError("Coding input exceeds the approved byte bound.", "CODE_BUDGET_REQUEST_TOO_LARGE")
        # Every request field is included, including system text/tool schemas. This
        # deliberately assumes one input token per UTF-8 byte, plus framing room.
        input_ceiling = len(encoded) + 4096
        amount = self.price(input_ceiling, output)
        if amount <= 0 or amount > self.call_limit:
            raise CodeBudgetError("The coding call exceeds its approved cost ceiling.", "CODE_PROVIDER_BUDGET_EXHAUSTED")
        return hashlib.sha256(encoded).hexdigest(), amount, input_ceiling, output

    def estimate_request(self, body: dict[str, Any]) -> int:
        return self.request_details(body)[1]


def rpc_object(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, dict):
        raise CodeBudgetError("Coding budget admission could not be confirmed.")
    return value


class CodeProviderBudgetService:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def reserve_call(self, task: dict[str, Any], *, call_key: str,
                           request_body: dict[str, Any], policy: CodeBudgetPolicy) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", str(call_key)):
            raise CodeBudgetError("Invalid stable coding call key.", "CODE_BUDGET_REQUEST_INVALID")
        digest, amount, input_ceiling, output_ceiling = policy.request_details(request_body)
        result = rpc_object(await self.db.rpc("reserve_code_provider_call", {
            "p_task_id": task["id"], "p_user_id": task["user_id"],
            "p_lease_token": task.get("lease_token"), "p_call_key": call_key,
            "p_request_sha256": digest, "p_reserved_micros": amount,
            "p_input_ceiling": input_ceiling, "p_output_ceiling": output_ceiling,
            "p_policy": policy.as_dict(),
        }, retry_transient=True))
        if result.get("outcome") not in {"reserved", "reserved_replay"}:
            raise CodeBudgetError("Coding provider admission was refused.", str(result.get("code") or "CODE_PROVIDER_BUDGET_EXHAUSTED"))
        reservation = result.get("reservation")
        if not isinstance(reservation, dict):
            raise CodeBudgetError("Coding reservation could not be confirmed.")
        return reservation

    async def begin_call(self, task: dict[str, Any], reservation: dict[str, Any]) -> dict[str, Any]:
        result = await self._change("begin_code_provider_call", task, reservation)
        if result.get("outcome") != "started":
            raise CodeBudgetError("Coding dispatch ownership is uncertain; it will not be replayed.", "CODE_PROVIDER_OUTCOME_UNCERTAIN")
        return rpc_object(result.get("reservation"))

    async def settle_call(self, task: dict[str, Any], reservation: dict[str, Any], *,
                          usage: dict[str, Any] | None = None, uncertain: bool = False) -> dict[str, Any]:
        actual = None
        try:
            policy = CodeBudgetPolicy(**reservation["policy"])
            if not isinstance(usage, dict):
                raise ValueError("Missing usage")
            values = []
            for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                value = usage[key] if key in {"input_tokens", "output_tokens"} else usage.get(key, 0)
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000_000:
                    raise ValueError("Invalid usage")
                values.append(value)
            actual = policy.price(values[0] + values[2] + values[3], values[1])
            uncertain = uncertain or values[0] + values[2] + values[3] > int(reservation["input_ceiling"]) or values[1] > int(reservation["output_ceiling"])
        except (KeyError, ValueError, TypeError, CodeBudgetError):
            uncertain = True
        return await self._change("settle_code_provider_call", task, reservation,
                                  p_actual_micros=actual, p_uncertain=bool(uncertain))

    async def release_before_dispatch(self, task: dict[str, Any], reservation: dict[str, Any]) -> dict[str, Any]:
        return await self._change("release_code_provider_call", task, reservation)

    async def _change(self, function: str, task: dict[str, Any], reservation: dict[str, Any], **values: Any) -> dict[str, Any]:
        return rpc_object(await self.db.rpc(function, {
            "p_task_id": task["id"], "p_user_id": task["user_id"],
            "p_lease_token": task.get("lease_token"), "p_reservation_id": reservation["id"], **values,
        }, retry_transient=True))
