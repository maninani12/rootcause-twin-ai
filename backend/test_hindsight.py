"""Manual cloud integration test: python -m backend.test_hindsight."""

INCIDENT = """Incident ID: INC-001
Machine: Capping Machine C-07
Product: 1L Bottle
Batch: B301
Quality Defect: Bottle cap leakage
Defect Rate Before: 4.8%
Machine Condition: Unstable capping torque
Action Attempted: Torque calibration
Action Result: FAILED
Confirmed Root Cause: Worn capping chuck
Corrective Action: Chuck replacement
Defect Rate After: 0.2%
Outcome: SUCCESS
Verification Status: VERIFIED"""

QUERY = (
    "Bottle leakage on C-07 with unstable capping torque. "
    "What previous troubleshooting actions and root causes are relevant?"
)


def main() -> int:
    stage = "setup"
    try:
        # Import here so missing dependencies/configuration produce a clean error.
        if __package__:
            from .hindsight_service import recall_incidents, retain_incident
        else:
            from hindsight_service import recall_incidents, retain_incident

        stage = "retain"
        print("=== RETAIN TEST ===", flush=True)
        retained = retain_incident(INCIDENT)
        if not retained.success:
            print("Error: Hindsight did not confirm successful storage.")
            return 1
        print("Memory stored successfully.")

        stage = "recall"
        print("\n=== RECALL TEST ===", flush=True)
        recalled = recall_incidents(QUERY)
        print("Relevant memories:")
        if not recalled.results:
            print("No relevant memories returned. Check the bank and retry recall.")
            return 1
        for index, memory in enumerate(recalled.results, start=1):
            print(f"{index}. {memory.text}")
        return 0
    except ImportError:
        print("Error: Missing dependency. Run: python -m pip install -r requirements.txt")
    except ValueError as exc:
        print(f"Configuration/input error: {exc}")
    except Exception as exc:
        # Do not print raw SDK errors: they may contain request data or credentials.
        status = getattr(exc, "status", None)
        if status in (401, 403):
            message = "Authentication or access denied. Check your API key and bank access."
        elif status == 404:
            message = "Resource not found. Check HINDSIGHT_BASE_URL and HINDSIGHT_BANK_ID."
        elif status == 429:
            message = "Rate limit reached. Wait briefly before trying again."
        else:
            message = "Request failed. Check connectivity, cloud service status, and configuration."
        print(f"Error during {stage}: {message}")
        if stage == "recall":
            print("Retention succeeded; the stored memory remains in your bank.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
