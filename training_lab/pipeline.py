"""Resumable local-LLM training lab for threat actor QA evaluation."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)
QUESTION_SCHEMA_VERSION = 3


@dataclass
class OllamaOptions:
    base_url: str = "http://localhost:11434"
    model: Optional[str] = None
    timeout_seconds: int = 90


class OllamaTextClient:
    """Thin Ollama wrapper used by question, answer, and evaluator agents."""

    def __init__(self, options: OllamaOptions):
        self.options = options

    def list_models(self) -> List[str]:
        try:
            response = requests.get(f"{self.options.base_url}/api/tags", timeout=8)
            response.raise_for_status()
            payload = response.json()
            return [m.get("name", "") for m in payload.get("models", []) if m.get("name")]
        except Exception as exc:
            logger.warning("Unable to list Ollama models: %s", exc)
            return []

    def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 700,
        json_mode: bool = False,
    ) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "num_predict": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"
        timeout = max(self.options.timeout_seconds, max_tokens // 4)

        try:
            response = requests.post(
                f"{self.options.base_url}/api/generate",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return (response.json().get("response") or "").strip()
        except Exception as exc:
            logger.error("Ollama generation failed: %s", exc)
            return ""


class TrainingLabManager:
    """Coordinates resumable question generation, answering, and hallucination checks."""

    def __init__(
        self,
        root_dir: Path,
        actors_path: Path,
        ollama_base_url: str,
        default_model: Optional[str] = None,
        project_answer_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
    ):
        self.root_dir = Path(root_dir)
        self.runtime_dir = self.root_dir / "runtime"
        self.runs_dir = self.runtime_dir / "runs"
        self.actors_path = Path(actors_path)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._active_run_id: Optional[str] = None

        self.client = OllamaTextClient(
            OllamaOptions(base_url=ollama_base_url, model=default_model)
        )
        self.default_model = default_model
        self.project_answer_fn = project_answer_fn

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def _state_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "state.json"

    def _config_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "config.json"

    def _records_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "qa_records.jsonl"

    def _questions_dir(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "questions"

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=True)
        tmp_path.replace(path)

    def _append_record(self, path: Path, record: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")

    def _load_actors(self) -> List[Dict[str, Any]]:
        with self.actors_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("actors"), list):
            return payload["actors"]
        return []

    def available_models(self) -> List[str]:
        return self.client.list_models()

    def recommend_model(self) -> str:
        models = self.available_models()
        preferred = [
            "qwen2.5:3b-instruct",
            "llama3.2:3b",
            "phi3:mini",
            "mistral:7b",
            "llama3:8b",
        ]
        for candidate in preferred:
            if candidate in models:
                return candidate
        return models[0] if models else (self.default_model or "llama3.2:3b")

    def available_answer_sources(self) -> List[str]:
        return ["main_project", "local_llm"]

    def _select_model(self, requested_model: Optional[str]) -> str:
        models = self.available_models()
        if requested_model and requested_model in models:
            return requested_model
        if requested_model and not models:
            return requested_model
        recommended = self.recommend_model()
        return recommended

    def _extract_json_payload(self, text: str) -> Any:
        cleaned = (text or "").strip()
        if not cleaned:
            return None
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        start_obj = cleaned.find("{")
        end_obj = cleaned.rfind("}")
        if 0 <= start_obj < end_obj:
            snippet = cleaned[start_obj : end_obj + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                pass

        start_arr = cleaned.find("[")
        end_arr = cleaned.rfind("]")
        if 0 <= start_arr < end_arr:
            snippet = cleaned[start_arr : end_arr + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                return None
        return None

    def _actor_name(self, actor: Dict[str, Any]) -> str:
        return actor.get("primary_name") or actor.get("name") or "unknown-actor"

    def _actor_aliases(self, actor: Dict[str, Any]) -> List[str]:
        aliases = actor.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        return [str(a).strip() for a in aliases if str(a).strip()]

    def _question_mentions_actor(self, question: str, actor: Dict[str, Any]) -> bool:
        haystack = (question or "").lower()
        names = [self._actor_name(actor)] + self._actor_aliases(actor)
        for name in names:
            if name and name.lower() in haystack:
                return True
        return False

    def _anchor_question_to_actor(self, question: str, actor: Dict[str, Any]) -> str:
        text = (question or "").strip()
        if not text:
            return f"Who is {self._actor_name(actor)}?"

        actor_name = self._actor_name(actor)

        # Replace ambiguous references with explicit actor name.
        replacements = [
            "this threat actor",
            "the threat actor",
            "this actor",
            "the actor",
            "this group",
            "the group",
        ]
        lowered = text.lower()
        for token in replacements:
            if token in lowered:
                idx = lowered.find(token)
                text = text[:idx] + actor_name + text[idx + len(token) :]
                lowered = text.lower()

        if not self._question_mentions_actor(text, actor):
            # Prefix with explicit actor scope to keep retrieval focused.
            text = f"For {actor_name}, {text[0].lower() + text[1:] if len(text) > 1 else text.lower()}"

        return text

    def _normalize_actor_questions(self, questions: List[str], actor: Dict[str, Any], limit: int) -> List[str]:
        normalized: List[str] = []
        seen = set()

        banned_tokens = ["mongo id", "mongodb id", "objectid", "uuid", "internal id", "database id"]

        for q in questions:
            candidate = self._anchor_question_to_actor(q, actor)
            lc = candidate.lower()
            if any(token in lc for token in banned_tokens):
                continue
            if candidate and candidate not in seen:
                seen.add(candidate)
                normalized.append(candidate)
            if len(normalized) >= limit:
                break

        return normalized

    def _sanitize_actor_for_llm(self, actor: Dict[str, Any]) -> Dict[str, Any]:
        """Keep only analyst-relevant fields and intentionally exclude internal IDs."""
        allowed_fields = {
            "name",
            "primary_name",
            "name_giver",
            "aliases",
            "countries",
            "description",
            "information_sources",
            "last_updated",
        }
        sanitized: Dict[str, Any] = {}
        for key, value in actor.items():
            if key in allowed_fields:
                sanitized[key] = value
        return sanitized

    def _max_possible_questions(self, actor: Dict[str, Any]) -> int:
        """Estimate how many distinct grounded questions are realistically possible."""
        possible = 1  # identity/overview

        if actor.get("description"):
            possible += 2
            if len((actor.get("description") or "")) > 350:
                possible += 1
        if actor.get("aliases"):
            possible += min(2, len(actor.get("aliases") or []))
        if actor.get("countries"):
            possible += min(2, len(actor.get("countries") or []))
        if actor.get("information_sources"):
            possible += min(2, len(actor.get("information_sources") or []))
        if actor.get("last_updated"):
            possible += 1

        # Hard safety bound prevents excessive questions on sparse records.
        return max(1, min(12, possible))

    def _question_count_for_actor(
        self,
        actor: Dict[str, Any],
        min_questions: int,
        max_questions: int,
    ) -> int:
        feasible_max = self._max_possible_questions(actor)
        adjusted_max = max(1, min(max_questions, feasible_max))
        adjusted_min = max(1, min(min_questions, adjusted_max))

        score = 0
        description = actor.get("description") or ""
        if len(description) > 250:
            score += 1
        if len(description) > 800:
            score += 1

        score += min(len(actor.get("aliases") or []), 4) // 2
        score += min(len(actor.get("countries") or []), 3)
        score += min(len(actor.get("information_sources") or []), 4) // 2

        proposed = adjusted_min + score
        return max(adjusted_min, min(adjusted_max, proposed))

    def _fallback_questions(self, actor: Dict[str, Any], count: int) -> List[str]:
        actor_name = self._actor_name(actor)
        questions: List[str] = [f"Who is {actor_name}?"]

        if actor.get("aliases"):
            questions.append(f"What are known aliases of {actor_name}?")
        if actor.get("countries"):
            questions.append(f"Which countries is {actor_name} associated with?")
        if actor.get("description"):
            questions.append(f"Summarize the known profile of {actor_name}.")
        if actor.get("information_sources"):
            questions.append(f"What sources document intelligence about {actor_name}?")

        while len(questions) < count:
            questions.append(
                f"For {actor_name}, what is the most important fact based on available data?"
            )

        return questions[:count]

    def _generate_questions(
        self,
        actor: Dict[str, Any],
        question_count: int,
        model: str,
    ) -> List[str]:
        actor_json = json.dumps(self._sanitize_actor_for_llm(actor), ensure_ascii=True, indent=2)
        prompt = (
            "You are a threat-intel question generator.\n"
            "Generate up to the requested number of questions strictly grounded in the actor data.\n"
            "Do not force low-quality questions when data is sparse.\n"
            "Do not invent missing data fields.\n"
            "Never ask about internal IDs, database IDs, or storage keys.\n"
            f"Every question must explicitly mention this actor by name: {self._actor_name(actor)}.\n"
            "Do not use generic phrasing like 'this actor' or 'the threat actor'.\n"
            "Return ONLY valid JSON as an array of strings, no markdown.\n"
            f"Maximum question count: {question_count}\n\n"
            f"Actor data:\n{actor_json}\n"
        )
        raw = self.client.generate(prompt=prompt, model=model, temperature=0.2, max_tokens=900)
        parsed = self._extract_json_payload(raw)

        questions: List[str] = []
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, str):
                    text = item.strip()
                    if text and text not in questions:
                        questions.append(text)

        questions = self._normalize_actor_questions(questions, actor, question_count)

        if len(questions) < question_count:
            fallback = self._fallback_questions(actor, question_count)
            for q in fallback:
                anchored = self._anchor_question_to_actor(q, actor)
                if anchored not in questions:
                    q = anchored
                    questions.append(q)
                if len(questions) >= question_count:
                    break

        return questions[:question_count]

    def _build_main_project_query(self, actor: Dict[str, Any], question: str) -> str:
        actor_name = self._actor_name(actor)
        aliases = self._actor_aliases(actor)
        alias_text = f" Aliases: {', '.join(aliases[:5])}." if aliases else ""
        return (
            f"Actor focus: {actor_name}.{alias_text} "
            f"Answer only for this actor.\n"
            f"Question: {question}"
        )

    def _generate_answer_local_llm(self, actor: Dict[str, Any], question: str, model: str) -> str:
        actor_json = json.dumps(self._sanitize_actor_for_llm(actor), ensure_ascii=True, indent=2)
        prompt = (
            "You are an answering agent restricted to the provided actor data only.\n"
            "Rules:\n"
            "1) Use only provided actor data.\n"
            "2) If the answer is not directly supported by the data, respond with exactly: no\n"
            "3) Do not add external knowledge.\n"
            "4) Keep answer concise.\n"
            "5) Never discuss internal IDs or storage identifiers.\n\n"
            f"Question: {question}\n\n"
            f"Actor data:\n{actor_json}\n"
        )
        answer = self.client.generate(prompt=prompt, model=model, temperature=0.0, max_tokens=350).strip()
        if not answer:
            return "no"
        if answer.lower() == "no":
            return "no"
        return answer

    def _generate_answer_main_project(self, actor: Dict[str, Any], question: str) -> str:
        """Use the project's real query pipeline for answers."""
        if not self.project_answer_fn:
            logger.warning("Main project answer function is not configured")
            return "no"

        try:
            project_query = self._build_main_project_query(actor, question)
            result = self.project_answer_fn(project_query) or {}
            answer = (result.get("answer") or "").strip()
            confidence = float(result.get("confidence", 0.0) or 0.0)

            # Keep strict behavior: low-confidence or missing answers become 'no'.
            if not answer:
                return "no"
            if confidence <= 0:
                return "no"

            lowered = answer.lower()
            deny_patterns = [
                "no relevant threat intelligence found",
                "please try a different search",
                "cannot determine",
                "insufficient evidence",
            ]
            if any(token in lowered for token in deny_patterns):
                return "no"

            return answer
        except Exception as exc:
            logger.error("Main project answer generation failed: %s", exc)
            return "no"

    def _evaluate_answer(
        self,
        actor: Dict[str, Any],
        question: str,
        answer: str,
        model: str,
    ) -> Dict[str, Any]:
        if answer.lower() == "no":
            return {
                "supported": False,
                "hallucinated": False,
                "workable": False,
                "confidence": 100,
                "reason": "No answer was returned due to insufficient support in actor data.",
                "matched_fields": [],
                "parse_failure": False,
            }

        actor_json = json.dumps(self._sanitize_actor_for_llm(actor), ensure_ascii=True, indent=2)
        prompt = (
            "You are a strict hallucination evaluator.\n"
            "Compare the answer with actor data only.\n"
            "Return ONLY JSON object with keys: supported (bool), hallucinated (bool), workable (bool), confidence (0-100 int), reason (string), matched_fields (array of strings).\n"
            "supported=true only when answer is grounded in provided data.\n"
            "hallucinated=true if answer includes unsupported claims.\n"
            "workable=true only when supported=true and hallucinated=false.\n\n"
            f"Question: {question}\n"
            f"Answer: {answer}\n\n"
            f"Actor data:\n{actor_json}\n"
        )
        raw = self.client.generate(
            prompt=prompt,
            model=model,
            temperature=0.0,
            max_tokens=700,
            json_mode=True,
        )
        parsed = self._extract_json_payload(raw)

        if not isinstance(parsed, dict):
            # Retry without json_mode for models that ignore JSON format instructions.
            retry_raw = self.client.generate(
                prompt=prompt,
                model=model,
                temperature=0.0,
                max_tokens=700,
                json_mode=False,
            )
            parsed = self._extract_json_payload(retry_raw)

        if not isinstance(parsed, dict):
            # Final normalization pass: transform any previous output into strict JSON.
            normalize_prompt = (
                "Convert the following evaluator output into valid JSON with exact keys: "
                "supported, hallucinated, workable, confidence, reason, matched_fields. "
                "Return JSON only.\n\n"
                f"Output to normalize:\n{raw}\n"
            )
            normalize_raw = self.client.generate(
                prompt=normalize_prompt,
                model=model,
                temperature=0.0,
                max_tokens=300,
                json_mode=True,
            )
            parsed = self._extract_json_payload(normalize_raw)

        if isinstance(parsed, dict):
            supported = bool(parsed.get("supported", False))
            hallucinated = bool(parsed.get("hallucinated", not supported))
            workable = bool(parsed.get("workable", supported and not hallucinated))
            confidence = int(parsed.get("confidence", 0))
            confidence = max(0, min(100, confidence))
            reason = str(parsed.get("reason", ""))[:500]
            matched_fields = parsed.get("matched_fields", [])
            if not isinstance(matched_fields, list):
                matched_fields = []
            matched_fields = [str(item) for item in matched_fields][:10]
            return {
                "supported": supported,
                "hallucinated": hallucinated,
                "workable": workable,
                "confidence": confidence,
                "reason": reason,
                "matched_fields": matched_fields,
                "parse_failure": False,
            }

        return {
            "supported": False,
            "hallucinated": True,
            "workable": False,
            "confidence": 0,
            "reason": "Evaluator did not return valid JSON; marked as hallucinated for safety.",
            "matched_fields": [],
            "parse_failure": True,
        }

    def _load_or_generate_questions(
        self,
        run_id: str,
        actor: Dict[str, Any],
        actor_index: int,
        min_questions: int,
        max_questions: int,
        model: str,
    ) -> List[str]:
        actor_key = actor.get("id") or f"actor-{actor_index}"
        q_path = self._questions_dir(run_id) / f"{actor_key}.json"
        existing = self._read_json(q_path)
        if (
            existing.get("schema_version") == QUESTION_SCHEMA_VERSION
            and isinstance(existing.get("questions"), list)
            and existing.get("questions")
        ):
            return [str(q) for q in existing["questions"]]

        count = self._question_count_for_actor(actor, min_questions, max_questions)
        questions = self._generate_questions(actor, count, model)
        payload = {
            "schema_version": QUESTION_SCHEMA_VERSION,
            "actor_id": actor_key,
            "actor_name": self._actor_name(actor),
            "question_count": len(questions),
            "questions": questions,
            "generated_at": self._utc_now(),
        }
        self._write_json(q_path, payload)
        return questions

    def _update_state_metrics(self, state: Dict[str, Any]) -> None:
        totals = state["totals"]
        answered = totals["answered"]
        hallucinated = totals["hallucinated"]
        total = totals["questions_total"]
        no_answer = totals["no_answer"]
        parse_failures = totals.get("evaluator_parse_failures", 0)

        totals["answer_rate_percent"] = round((answered / total) * 100, 2) if total else 0.0
        totals["no_answer_rate_percent"] = round((no_answer / total) * 100, 2) if total else 0.0
        totals["hallucination_percent"] = round((hallucinated / answered) * 100, 2) if answered else 0.0
        totals["evaluator_parse_failure_percent"] = round((parse_failures / total) * 100, 2) if total else 0.0

    def _run_worker(self, run_id: str) -> None:
        run_dir = self._run_dir(run_id)
        state_path = self._state_path(run_id)
        records_path = self._records_path(run_id)
        config = self._read_json(self._config_path(run_id))
        state = self._read_json(state_path)

        min_questions = int(config.get("min_questions_per_actor", 3))
        max_questions = int(config.get("max_questions_per_actor", 10))
        selected_model = config.get("model") or self.recommend_model()
        answer_source = config.get("answer_source", "main_project")

        actors = self._load_actors()
        state["total_actors"] = len(actors)
        state["status"] = "running"
        state["last_updated"] = self._utc_now()
        self._write_json(state_path, state)

        for actor_index in range(state.get("current_actor_index", 0), len(actors)):
            actor = actors[actor_index]
            actor_id = actor.get("id") or f"actor-{actor_index}"
            actor_name = self._actor_name(actor)

            questions = self._load_or_generate_questions(
                run_id,
                actor,
                actor_index,
                min_questions,
                max_questions,
                selected_model,
            )

            start_q = state.get("current_question_index", 0) if actor_index == state.get("current_actor_index", 0) else 0

            for question_index in range(start_q, len(questions)):
                if self._stop_event.is_set():
                    state["status"] = "paused"
                    state["last_updated"] = self._utc_now()
                    self._write_json(state_path, state)
                    logger.info("Training run paused: %s", run_id)
                    return

                question = questions[question_index]
                if answer_source == "main_project":
                    answer = self._generate_answer_main_project(actor, question)
                else:
                    answer = self._generate_answer_local_llm(actor, question, selected_model)
                evaluation = self._evaluate_answer(actor, question, answer, selected_model)

                answered_flag = answer.lower() != "no"
                record = {
                    "timestamp": self._utc_now(),
                    "run_id": run_id,
                    "actor_index": actor_index,
                    "actor_id": actor_id,
                    "actor_name": actor_name,
                    "question_index": question_index,
                    "question": question,
                    "answer": answer,
                    "answer_source": answer_source,
                    "answered": answered_flag,
                    "evaluation": evaluation,
                }
                self._append_record(records_path, record)

                totals = state["totals"]
                totals["questions_total"] += 1
                if answered_flag:
                    totals["answered"] += 1
                else:
                    totals["no_answer"] += 1

                if evaluation.get("hallucinated"):
                    totals["hallucinated"] += 1
                if evaluation.get("workable"):
                    totals["workable"] += 1
                if evaluation.get("parse_failure"):
                    totals["evaluator_parse_failures"] += 1

                state["current_actor_index"] = actor_index
                state["current_question_index"] = question_index + 1
                state["actors_completed"] = actor_index
                state["last_updated"] = self._utc_now()
                self._update_state_metrics(state)

                if state["current_question_index"] >= len(questions):
                    state["current_actor_index"] = actor_index + 1
                    state["current_question_index"] = 0
                    state["actors_completed"] = actor_index + 1

                self._write_json(state_path, state)

        state["status"] = "completed"
        state["completed_at"] = self._utc_now()
        state["last_updated"] = self._utc_now()
        self._update_state_metrics(state)
        self._write_json(state_path, state)
        logger.info("Training run completed: %s", run_id)

    def start_run(
        self,
        model: Optional[str] = None,
        min_questions_per_actor: int = 3,
        max_questions_per_actor: int = 10,
        answer_source: str = "main_project",
    ) -> Dict[str, Any]:
        with self._lock:
            if self._worker_thread and self._worker_thread.is_alive():
                return {"error": "A run is already active", "run_id": self._active_run_id}

            selected_model = self._select_model(model)
            if answer_source not in self.available_answer_sources():
                answer_source = "main_project"
            run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
            run_dir = self._run_dir(run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            self._questions_dir(run_id).mkdir(parents=True, exist_ok=True)

            config = {
                "run_id": run_id,
                "model": selected_model,
                "min_questions_per_actor": max(1, int(min_questions_per_actor)),
                "max_questions_per_actor": max(1, int(max_questions_per_actor)),
                "answer_source": answer_source,
                "created_at": self._utc_now(),
            }
            if config["max_questions_per_actor"] < config["min_questions_per_actor"]:
                config["max_questions_per_actor"] = config["min_questions_per_actor"]

            state = {
                "run_id": run_id,
                "status": "running",
                "started_at": self._utc_now(),
                "last_updated": self._utc_now(),
                "completed_at": None,
                "model": selected_model,
                "answer_source": answer_source,
                "total_actors": 0,
                "actors_completed": 0,
                "current_actor_index": 0,
                "current_question_index": 0,
                "totals": {
                    "questions_total": 0,
                    "answered": 0,
                    "no_answer": 0,
                    "hallucinated": 0,
                    "workable": 0,
                    "evaluator_parse_failures": 0,
                    "answer_rate_percent": 0.0,
                    "no_answer_rate_percent": 0.0,
                    "hallucination_percent": 0.0,
                    "evaluator_parse_failure_percent": 0.0,
                },
            }

            self._write_json(self._config_path(run_id), config)
            self._write_json(self._state_path(run_id), state)

            self._stop_event.clear()
            self._active_run_id = run_id
            self._worker_thread = threading.Thread(target=self._run_worker, args=(run_id,), daemon=True)
            self._worker_thread.start()

            return {
                "run_id": run_id,
                "status": "running",
                "model": selected_model,
                "answer_source": answer_source,
                "message": "Training run started",
            }

    def stop_run(self) -> Dict[str, Any]:
        with self._lock:
            if not self._worker_thread or not self._worker_thread.is_alive() or not self._active_run_id:
                return {"error": "No active run"}
            self._stop_event.set()
            return {"run_id": self._active_run_id, "message": "Stop requested"}

    def resume_run(self, run_id: str) -> Dict[str, Any]:
        with self._lock:
            if self._worker_thread and self._worker_thread.is_alive():
                return {"error": "Another run is currently active", "run_id": self._active_run_id}

            state = self._read_json(self._state_path(run_id))
            if not state:
                return {"error": "Run not found", "run_id": run_id}
            if state.get("status") == "completed":
                return {"error": "Run already completed", "run_id": run_id}

            state["status"] = "running"
            state["last_updated"] = self._utc_now()
            self._write_json(self._state_path(run_id), state)

            self._stop_event.clear()
            self._active_run_id = run_id
            self._worker_thread = threading.Thread(target=self._run_worker, args=(run_id,), daemon=True)
            self._worker_thread.start()

            return {"run_id": run_id, "status": "running", "message": "Run resumed"}

    def get_state(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        target_run = run_id or self._active_run_id
        if not target_run:
            latest = self.list_runs(limit=1)
            if not latest:
                return {"status": "idle", "message": "No training runs yet"}
            target_run = latest[0]["run_id"]

        state = self._read_json(self._state_path(target_run))
        if not state:
            return {"status": "idle", "message": "Run not found", "run_id": target_run}

        state["active"] = bool(
            self._active_run_id == target_run
            and self._worker_thread
            and self._worker_thread.is_alive()
        )
        return state

    def list_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        runs: List[Dict[str, Any]] = []
        for run_dir in self.runs_dir.glob("*"):
            if not run_dir.is_dir():
                continue
            state = self._read_json(run_dir / "state.json")
            if not state:
                continue
            runs.append(
                {
                    "run_id": state.get("run_id", run_dir.name),
                    "status": state.get("status", "unknown"),
                    "started_at": state.get("started_at"),
                    "last_updated": state.get("last_updated"),
                    "totals": state.get("totals", {}),
                    "model": state.get("model"),
                    "answer_source": state.get("answer_source", "main_project"),
                }
            )

        runs.sort(key=lambda item: item.get("started_at") or "", reverse=True)
        return runs[: max(1, int(limit))]

    def get_records(
        self,
        run_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        path = self._records_path(run_id)
        if not path.exists():
            return {"run_id": run_id, "records": [], "total": 0}

        with path.open("r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        total = len(lines)
        start = max(0, int(offset))
        end = min(total, start + max(1, int(limit)))
        selected = lines[start:end]

        records = []
        for line in selected:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return {
            "run_id": run_id,
            "records": records,
            "total": total,
            "offset": start,
            "limit": limit,
        }
