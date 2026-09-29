"""Transparent context comparison and evidence handling; no external LLM required."""
import json
import re
from pathlib import Path

FIELDS = {
    "incident_id": "Incident ID", "machine": "Machine", "product": "Product",
    "batch": "Batch", "quality_defect": "Quality Defect",
    "machine_condition": "Machine Condition", "recent_change": "Recent Change",
    "previous_action": "Action Attempted", "previous_result": "Action Result",
    "confirmed_root_cause": "Confirmed Root Cause", "corrective_action": "Corrective Action",
    "before_metric": "Defect Rate Before", "after_metric": "Defect Rate After",
    "outcome": "Outcome", "verification_status": "Verification Status",
    "created_at": "Date / time",
}


def load_sample_incidents():
    return json.loads((Path(__file__).resolve().parents[1] / "data/sample_incidents.json").read_text())


def build_recall_query(incident):
    context = "\n".join(f"{FIELDS[key]}: {incident.get(key) or 'Not supplied'}" for key in
                        ("machine", "product", "quality_defect", "machine_condition", "recent_change"))
    return context + "\nWhat previous troubleshooting actions, failures, verified root causes and outcomes are relevant?"


def _mapping(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    raise ValueError("Malformed memory response")


def normalize_memories(response):
    """Use returned source chunks when present; never fill gaps with local samples."""
    data = _mapping(response)
    rows = data.get("results")
    if not isinstance(rows, list):
        raise ValueError("Malformed memory response")
    chunks = data.get("chunks") or {}
    if not isinstance(chunks, dict):
        raise ValueError("Malformed source chunks")
    memories, seen = [], set()
    for raw in rows:
        row = _mapping(raw)
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Malformed memory text")
        chunk = chunks.get(row.get("chunk_id"))
        source = _mapping(chunk) if chunk is not None else {}
        source_text = source.get("text")
        if source_text is not None and not isinstance(source_text, str):
            raise ValueError("Malformed source text")
        text = source_text or text
        if text in seen:
            continue
        seen.add(text)
        fields = {}
        for key, label in FIELDS.items():
            match = re.search(r"^" + re.escape(label) + r":\s*([^\r\n]+)", text, re.I | re.M)
            value = match.group(1).strip() if match else ""
            fields[key] = "" if value.lower() in ("not supplied", "not stated", "unknown") else value
        # Missing verification is unknown, never inferred from retrieval alone.
        verified = fields["verification_status"].upper() == "VERIFIED"
        actions = []
        if fields["previous_action"]:
            actions.append({"action": fields["previous_action"], "result": fields["previous_result"].upper()})
        if fields["corrective_action"]:
            actions.append({"action": fields["corrective_action"], "result": fields["outcome"].upper()})
        score = row.get("score")
        if score is None and isinstance(row.get("scores"), dict):
            score = row["scores"].get("final")
        memories.append({**fields, "text": text, "verified": verified, "actions": actions,
                         "source": "Hindsight source chunk" if source_text else "Hindsight recalled fact",
                         "source_id": row.get("document_id") or row.get("id") or "Not provided",
                         "date": fields["created_at"] or row.get("occurred_start") or row.get("mentioned_at"),
                         "truncated": bool(source.get("truncated")),
                         "score": score if isinstance(score, (float, int)) and not isinstance(score, bool) else None})
    # Put readable source records ahead of extracted facts; rank each group by
    # SDK relevance when supplied. Scores are not probabilities or confidence.
    return sorted(memories, key=lambda m: (bool(m["incident_id"]), m["score"] or 0), reverse=True)


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower())) - {"the", "a", "on", "of", "and", "is", "machine"}


def _overlap(current, evidence):
    words = _tokens(current)
    return bool(words) and len(words & _tokens(evidence)) / len(words) >= 0.75


def _torque(text):
    text = text.lower()
    if re.search(r"\b(unstable|inconsistent|fluctuating)\b", text):
        return "unstable"
    if re.search(r"\b(stable|consistent)\b", text):
        return "stable"
    return None


def compare_context(incident, memory):
    matched, different = [], []
    for key, label in [("machine", "Machine"), ("quality_defect", "Quality defect"),
                       ("machine_condition", "Machine condition"), ("product", "Product"),
                       ("recent_change", "Recent change")]:
        current = incident.get(key, "")
        prior = memory.get(key) or memory["text"]
        if not current:
            continue
        conflicts = key == "machine_condition" and _torque(current) and _torque(prior) and _torque(current) != _torque(prior)
        if not conflicts and _overlap(current, prior):
            matched.append(label)
        else:
            different.append(label + (": torque stability differs" if conflicts else ": differs or is not documented"))
    return {"matched": matched, "different": different}


def classify_incident(incident, recalled_memories):
    comparisons = [compare_context(incident, m) for m in recalled_memories]
    useful = [c for c in comparisons if {"Machine", "Quality defect"} & set(c["matched"])]
    best = max(useful, key=lambda c: len(c["matched"]), default={"matched": [], "different": []})
    if not useful:
        kind = "NOVEL"
        reasons = ["No recalled experience has useful machine or defect overlap. This is not proof the incident has never occurred."]
    elif {"Machine", "Quality defect", "Machine condition"} <= set(best["matched"]) and not best["different"]:
        kind = "KNOWN"
        reasons = ["A recalled record matches machine, defect and operating condition; supplied product and recent-change context do not conflict.",
                   "Known describes contextual similarity, not confirmation of the current root cause."]
    else:
        kind = "PARTIAL"
        reasons = ["Related machine or defect evidence exists, but operating context differs or is incomplete."]
    return {"classification": kind, "classification_reason": reasons,
            "matched_factors": best["matched"], "different_factors": best["different"]}


def summarize_memory_evidence(memories):
    return {"failed": sum(a["result"] == "FAILED" for m in memories for a in m["actions"]),
            "successful": sum(a["result"] == "SUCCESS" for m in memories for a in m["actions"]),
            "verified": sum(m["verified"] for m in memories)}


def generate_recommendation(incident, memories, classification):
    """Only quote actual evidence; generic checks are clearly recommendations."""
    relevant = [m for m in memories if {"Machine", "Quality defect"} & set(compare_context(incident, m)["matched"])]
    failed = [a["action"] for m in relevant for a in m["actions"] if a["result"] == "FAILED"]
    worked = [a["action"] for m in relevant for a in m["actions"] if a["result"] == "SUCCESS"]
    causes = list(dict.fromkeys(m["confirmed_root_cause"] for m in relevant if m["confirmed_root_cause"]))
    prior = "Historical evidence suggests related troubleshooting experience is available." if relevant else "No useful prior experience was recalled; collect measurements before proposing a cause."
    if causes:
        prior += " Recorded root causes: " + "; ".join(causes) + ". Confirm their applicability to this incident."
    checks = "Inspect the reported defect, record operating conditions, and verify candidate causes with measurements."
    if _torque(incident.get("machine_condition", "")) == "stable" and "supplier" in incident.get("recent_change", "").lower():
        checks = "Torque is currently stable and a supplier change is reported. Inspect cap dimensions and incoming material quality before attributing leakage to the capping machine. Do not assume chuck replacement is appropriate."
    elif any("chuck" in c.lower() for c in causes):
        checks = "Historical evidence suggests inspecting chuck wear and verifying torque consistency before repeating calibration. Confirm the cause before replacing parts."
    metrics = [f"{m['before_metric']} → {m['after_metric']}" for m in relevant if m["before_metric"] and m["after_metric"]]
    return [
        ("What previous incidents suggest", prior),
        ("What previously failed", "; ".join(dict.fromkeys(failed)) or "No structured failed action is documented in the returned evidence; review the source text."),
        ("What previously worked", ("; ".join(dict.fromkeys(worked)) or "No structured successful action is documented in the returned evidence.") + (". Recorded before → after: " + "; ".join(dict.fromkeys(metrics)) if metrics else "")),
        ("What to check now", checks),
        ("What differs now", "; ".join(classification["different_factors"]) or "No supplied factor was identified as different. Unmeasured differences may still exist; do not assume the same cause."),
    ]


def build_verified_memory(incident, resolution):
    if resolution.get("verification_status") != "VERIFIED":
        raise ValueError("Only verified resolutions may become trusted memory.")
    fields = {**incident, "confirmed_root_cause": resolution["confirmed_root_cause"],
              "corrective_action": resolution["action_taken"], "outcome": resolution["action_result"],
              "before_metric": resolution["before_metric"], "after_metric": resolution["after_metric"],
              "verification_status": "VERIFIED"}
    text = "\n".join(f"{label}: {fields.get(key) or 'Not supplied'}" for key, label in FIELDS.items())
    return text + "\nRecord Origin: " + ("Synthetic demo scenario, human-confirmed for demonstration." if incident.get("demo") else "Human-submitted investigation.")
