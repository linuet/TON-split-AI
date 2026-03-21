import base64
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.ai.prompts import (
    PARTICIPANTS_PARSE_SYSTEM,
    RECEIPT_PARSE_SYSTEM,
    RECEIPT_VERIFY_SYSTEM,
    SPLIT_INTENT_SYSTEM,
)
from app.services.receipt.schemas import ReceiptParseResult, ReceiptVerificationResult
from app.services.split.schemas import ParsedIntent, ParsedParticipants


class OpenAIService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    @staticmethod
    def _image_data_url(image_path: Path) -> str:
        encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"

    def _resolve_ref(self, ref: str, root_schema: dict[str, Any]) -> dict[str, Any]:
        if not ref.startswith("#/$defs/"):
            raise ValueError(f"Unsupported schema ref: {ref}")
        key = ref.split("/")[-1]
        defs = root_schema.get("$defs", {})
        if key not in defs:
            raise KeyError(f"Schema ref not found: {ref}")
        return defs[key]

    def _ensure_nullable(self, schema: dict[str, Any]) -> dict[str, Any]:
        if "anyOf" in schema:
            variants = schema["anyOf"]
            if any(isinstance(v, dict) and v.get("type") == "null" for v in variants):
                return schema
            return {"anyOf": [*variants, {"type": "null"}]}
        if isinstance(schema.get("type"), list):
            types = list(schema["type"])
            if "null" not in types:
                types.append("null")
            schema["type"] = types
            return schema
        if schema.get("type") == "null":
            return schema
        return {"anyOf": [schema, {"type": "null"}]}

    def _sanitize_schema_node(
        self,
        node: dict[str, Any],
        root_schema: dict[str, Any],
        originally_required: bool = True,
    ) -> dict[str, Any]:
        if "$ref" in node:
            resolved = self._resolve_ref(node["$ref"], root_schema)
            return self._sanitize_schema_node(
                resolved,
                root_schema,
                originally_required=originally_required,
            )

        sanitized: dict[str, Any] = {}
        if "anyOf" in node:
            sanitized["anyOf"] = [
                self._sanitize_schema_node(v, root_schema, originally_required=True)
                if isinstance(v, dict)
                else v
                for v in node["anyOf"]
            ]
        elif node.get("type") == "object" or "properties" in node:
            properties = node.get("properties", {})
            original_required = set(node.get("required", []))
            sanitized_properties: dict[str, Any] = {}
            for key, value in properties.items():
                child = self._sanitize_schema_node(
                    value,
                    root_schema,
                    originally_required=(key in original_required),
                )
                if key not in original_required:
                    child = self._ensure_nullable(child)
                sanitized_properties[key] = child
            sanitized["type"] = "object"
            sanitized["properties"] = sanitized_properties
            sanitized["required"] = list(sanitized_properties.keys())
            sanitized["additionalProperties"] = False
        elif node.get("type") == "array":
            sanitized["type"] = "array"
            items = node.get("items", {})
            sanitized["items"] = (
                self._sanitize_schema_node(items, root_schema, originally_required=True)
                if isinstance(items, dict)
                else items
            )
        else:
            for key in (
                "type",
                "enum",
                "const",
                "pattern",
                "format",
                "minimum",
                "maximum",
                "exclusiveMinimum",
                "exclusiveMaximum",
                "multipleOf",
            ):
                if key in node:
                    sanitized[key] = node[key]
        if "description" in node:
            sanitized["description"] = node["description"]
        if not originally_required:
            sanitized = self._ensure_nullable(sanitized)
        return sanitized

    def _schema_for_openai(self, model: Any, name: str) -> dict[str, Any]:
        raw = model.model_json_schema()
        sanitized = self._sanitize_schema_node(raw, raw, originally_required=True)
        return {"name": name, "schema": sanitized}

    async def _json_response(
        self,
        *,
        input_payload: list[dict[str, Any]],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.client.responses.create(
            model=self.model,
            input=input_payload,
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema["name"],
                    "schema": schema["schema"],
                    "strict": True,
                }
            },
        )
        return json.loads(response.output_text)

    @staticmethod
    def _normalize_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @staticmethod
    def _normalize_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"true", "1", "yes"}:
                return True
            if v in {"false", "0", "no"}:
                return False
        return bool(value)

    @staticmethod
    def _normalize_number_like(value: Any, default: Any = 0) -> Any:
        if value is None or value == "":
            return default
        if isinstance(value, (int, float, Decimal)):
            return value
        if not isinstance(value, str):
            return value
        s = value.strip()
        if not s:
            return default
        s = s.replace(" ", "").replace("\u00a0", "")
        s = re.sub(r"[^\d,.\-]", "", s)
        if not s:
            return default
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            parts = s.split(",")
            s = "".join(parts[:-1]) + "." + parts[-1] if len(parts[-1]) in (1, 2) else "".join(parts)
        elif "." in s:
            parts = s.split(".")
            s = "".join(parts[:-1]) + "." + parts[-1] if len(parts[-1]) in (1, 2) else "".join(parts)
        try:
            return str(Decimal(s))
        except (InvalidOperation, ValueError):
            return default

    def _normalize_receipt_item(self, item: Any) -> dict[str, Any] | None:
        if item is None or not isinstance(item, dict):
            return None
        return {
            "raw_text": item.get("raw_text"),
            "normalized_name": item.get("normalized_name") or "Unknown item",
            "quantity": self._normalize_number_like(item.get("quantity"), 1),
            "unit_price": self._normalize_number_like(item.get("unit_price"), 0),
            "line_total": self._normalize_number_like(item.get("line_total"), 0),
            "confidence_score": self._normalize_number_like(item.get("confidence_score"), 0.0),
            "is_uncertain": self._normalize_bool(item.get("is_uncertain"), False),
        }

    def _normalize_receipt_data(self, data: Any) -> dict[str, Any]:
        if data is None or not isinstance(data, dict):
            data = {}
        items_raw = self._normalize_list(data.get("items"))
        items_normalized = []
        for item in items_raw:
            normalized_item = self._normalize_receipt_item(item)
            if normalized_item is not None:
                items_normalized.append(normalized_item)
        return {
            "merchant_name": data.get("merchant_name"),
            "receipt_date": data.get("receipt_date"),
            "receipt_time": data.get("receipt_time"),
            "currency": data.get("currency") or "USD",
            "subtotal": self._normalize_number_like(data.get("subtotal"), None),
            "tax_amount": self._normalize_number_like(data.get("tax_amount"), None),
            "service_charge": self._normalize_number_like(data.get("service_charge"), None),
            "tips": self._normalize_number_like(data.get("tips"), None),
            "total": self._normalize_number_like(data.get("total"), None),
            "items": items_normalized,
            "uncertain_fields": [str(x) for x in self._normalize_list(data.get("uncertain_fields")) if x is not None],
            "parsing_notes": [str(x) for x in self._normalize_list(data.get("parsing_notes")) if x is not None],
            "confidence_score": self._normalize_number_like(data.get("confidence_score"), 0.0),
        }

    def _normalize_verification_data(self, data: Any) -> dict[str, Any]:
        if data is None or not isinstance(data, dict):
            data = {}
        return {
            "corrected_receipt": self._normalize_receipt_data(data.get("corrected_receipt")),
            "verification_notes": [str(x) for x in self._normalize_list(data.get("verification_notes")) if x is not None],
            "needs_manual_review": self._normalize_bool(data.get("needs_manual_review"), False),
        }

    def _normalize_action(self, action: Any) -> dict[str, Any] | None:
        if action is None or not isinstance(action, dict):
            return None
        return {
            "type": action.get("type") or "done",
            "item_match": action.get("item_match"),
            "category": action.get("category"),
            "participants": [str(x) for x in self._normalize_list(action.get("participants")) if x is not None],
            "ratios": [self._normalize_number_like(x, 0) for x in self._normalize_list(action.get("ratios")) if x is not None],
            "extra_kind": action.get("extra_kind"),
        }

    def _normalize_split_intent_data(self, data: Any) -> dict[str, Any]:
        if data is None or not isinstance(data, dict):
            data = {}
        actions_normalized = []
        for action in self._normalize_list(data.get("actions")):
            normalized_action = self._normalize_action(action)
            if normalized_action is not None:
                actions_normalized.append(normalized_action)
        cq = data.get("clarification_question")
        return {
            "actions": actions_normalized,
            "clarification_question": str(cq) if cq else None,
            "needs_clarification": self._normalize_bool(data.get("needs_clarification"), False),
        }

    def _normalize_participants_data(self, data: Any) -> dict[str, Any]:
        if data is None or not isinstance(data, dict):
            data = {}
        raw = self._normalize_list(data.get("participants"))
        cleaned = []
        for item in raw:
            if item is None:
                continue
            val = str(item).strip()
            if val:
                cleaned.append(val)
        return {"participants": cleaned}

    async def parse_receipt(self, original_image: Path, processed_image: Path) -> ReceiptParseResult:
        schema = self._schema_for_openai(ReceiptParseResult, "receipt_parse_result")
        payload = [
            {"role": "system", "content": [{"type": "input_text", "text": RECEIPT_PARSE_SYSTEM}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Parse this receipt with maximum accuracy."},
                    {"type": "input_image", "image_url": self._image_data_url(original_image)},
                    {"type": "input_image", "image_url": self._image_data_url(processed_image)},
                ],
            },
        ]
        data = await self._json_response(input_payload=payload, schema=schema)
        return ReceiptParseResult.model_validate(self._normalize_receipt_data(data))

    async def verify_receipt(self, original_image: Path, processed_image: Path, parsed: ReceiptParseResult) -> ReceiptVerificationResult:
        schema = self._schema_for_openai(ReceiptVerificationResult, "receipt_verification_result")
        payload = [
            {"role": "system", "content": [{"type": "input_text", "text": RECEIPT_VERIFY_SYSTEM}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Verify and correct this parsed receipt JSON against the images:\n" + parsed.model_dump_json(indent=2),
                    },
                    {"type": "input_image", "image_url": self._image_data_url(original_image)},
                    {"type": "input_image", "image_url": self._image_data_url(processed_image)},
                ],
            },
        ]
        data = await self._json_response(input_payload=payload, schema=schema)
        return ReceiptVerificationResult.model_validate(self._normalize_verification_data(data))

    async def parse_participants(self, text: str) -> ParsedParticipants:
        schema = self._schema_for_openai(ParsedParticipants, "parsed_participants")
        payload = [
            {"role": "system", "content": [{"type": "input_text", "text": PARTICIPANTS_PARSE_SYSTEM}]},
            {"role": "user", "content": [{"type": "input_text", "text": text}]},
        ]
        data = await self._json_response(input_payload=payload, schema=schema)
        return ParsedParticipants.model_validate(self._normalize_participants_data(data))

    async def parse_split_intent(
        self,
        command: str,
        available_items: list[str],
        participants: list[str],
        current_assignments: dict[str, list[str]] | None = None,
    ) -> ParsedIntent:
        schema = self._schema_for_openai(ParsedIntent, "parsed_split_intent")
        payload = [
            {"role": "system", "content": [{"type": "input_text", "text": SPLIT_INTENT_SYSTEM}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"Participants: {participants}\n"
                            f"Items: {available_items}\n"
                            f"Current assignments: {current_assignments or {}}\n"
                            f"User command: {command}"
                        ),
                    }
                ],
            },
        ]
        data = await self._json_response(input_payload=payload, schema=schema)
        return ParsedIntent.model_validate(self._normalize_split_intent_data(data))
