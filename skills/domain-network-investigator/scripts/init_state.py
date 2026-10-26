"""Initialize a new, empty investigation store. Never modify existing state."""
import argparse
import json
import re
from pathlib import Path


def initialize(out, team, profile="team-001"):
    out = Path(out).expanduser().resolve()
    if not team.strip():
        raise ValueError("Team name must not be empty")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", profile):
        raise ValueError("Profile ID must contain lowercase letters, digits or hyphens")
    if out.exists():
        raise FileExistsError("State already exists; resume it instead: " + str(out))
    out.mkdir(parents=True, exist_ok=False)
    (out / "profiles").mkdir()
    (out / "runs").mkdir()
    data = {
        "registry.json": {
            "schema_version": 1, "active_profile_id": profile,
            "profiles": [{"id": profile, "name": team.strip(), "path": f"profiles/{profile}.json"}],
            "domains": [], "brands": [],
        },
        f"profiles/{profile}.json": {
            "id": profile, "name": team.strip(), "kind": "user_team_profile",
            "identity_status": "working_label_not_verified_operator",
            "user_seeds": [], "patterns": [], "assessments": [], "source_refs": [],
        },
        "frontier.json": {"items": []},
    }
    for relative, value in data.items():
        (out / relative).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--team", required=True)
    parser.add_argument("--profile", default="team-001")
    args = parser.parse_args()
    try:
        result = initialize(args.out, args.team, args.profile)
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps({"state": str(result), "profile": args.profile, "observations": 0}))
