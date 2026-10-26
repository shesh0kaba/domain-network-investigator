# Persistent state and repeated search

State lives in the project workspace, not the installed skill. The method can travel between teams; evidence remains scoped.

## Files

```text
investigation-state/
  registry.json              active profile, seen domains/URLs and names
  profiles/<stable-id>.json   one named team's anchors, patterns and assessments
  runs/<run-id>.json          grouping decision, queries, sources, delta and coverage
  frontier.json              unresolved next pivots with parent evidence
```

Use atomic index writes and new files for new run logs; preserve raw evidence. `source_refs` hold paths relative to the project workspace or public URLs. Import exact old observation times when available; otherwise preserve date-only precision. Do not invent Google queries, ad-platform checks or historical timestamps during migration.

`registry.json` requires `schema_version: 1`, `active_profile_id`, `profiles`, `domains`, `brands`.

- Profile index entry: `id`, `name`, `path` (relative to the state directory).
- Domain: `domain`, `urls`, `seen_in_profiles`, `source_refs`, `first_seen`, `last_seen`, optional `discovery_only`. Seen in an investigation does **not** mean owned by that team. An indexed but unfetched neighbor is `discovery_only: true` and remains worth checking.
- Brand: stable `id`, `name`, `aliases`, `observations`, `profile_assessments`, `seo`.
- Name observation: spelling, kind (`ad`, `prelanding`, `seo_site`, `article`, `source_literal`, `historical_scan`, `search_index`, `user_supplied`, `speculative`), source, date. A domain-shaped string alone is not an established advertised name.
- Brand affiliation: profile ID, assessment (`user_assigned`, `supported`, `tentative`, `unassigned`, `contradicted`), evidence. Same name in two profiles does not merge them.
- `seo`: status, candidate/found URLs and checks. Each check includes actual query/source, language/region if known, date, outcome and limitations. Use `not_checked` when needed checks were not recorded.

Normalize case, Unicode and whitespace for duplicate detection. Do not silently remove “AI,” hyphens or other meaningful parts. Alias equivalence requires evidence; preserve original spelling.

## Profile and naming decision

Each profile requires `id`, `name`, `kind: "user_team_profile"`, `identity_status`, `user_seeds`, `patterns`, `assessments`, `source_refs`.

Normally `identity_status` is `working_label_not_verified_operator`. Use the user's team name or assign a short distinctive project/domain label. Keep IDs stable through renaming and record previous names as aliases.

New bare **user** link + active team → ask «Это команда „<name>“ или новая?» before assigning it. Explicit new team or named existing team → act without reconfirming. First investigation with no active team → initialize and name it. An **agent-discovered** URL is a lead in the current investigation, not a reason to interrupt the user. A new profile starts with its own seeds and empty pattern list, not a copy of the active profile.

Each pattern has:

```json
{
  "id": "team-001:pattern-01",
  "profile_id": "team-001",
  "scope": "shared_platform",
  "observation": "A particular script hash and configuration recur.",
  "use": "discovery_only",
  "source_refs": ["path/to/comparison.json"],
  "supporting_domains": [],
  "known_in_other_profiles": [],
  "counterevidence": [],
  "first_seen": "2026-10-21",
  "last_seen": "2026-10-21"
}
```

Scopes: `team_hypothesis`, `campaign_family`, `shared_platform`, `generic`. Uses: `discovery_only`, `corroboration`, `specific_evidence`. Shared-platform and generic patterns remain discovery-only **for team attribution**, regardless of certainty about the exact technical overlap. This does not prevent giving a direct IP high search priority. Per-domain assessments separately record same IP, same custom code, brand promotion, direct link, coordinated deployment or verified operator evidence.

Never automatically inherit another team's patterns or confirm a candidate solely through a signature learned from that candidate. Record contrary examples and cross-team overlap explicitly. Preserve user-declared separation; explain a conflict instead of silently merging profiles.

## Frontier and runs

`frontier.json` contains `items`. Each item has ID, profile ID, parent/source evidence, action, reason, priority, state (`open`, `checked`, `blocked_source`, `deferred`) and retry condition if needed. Label queues for new names, name-to-SEO, candidate domains, infrastructure expansion, campaigns and historical gaps.

Use an `advertorial_variants` queue for reused news-style content. Save variant observations in run logs with `profile_id`, scoped `content_family_id`, `seed_url`, `variant_url`, `matched_elements` (element type, source location, comparison method and evidence), `names_in_article`, `cta_url`, `observed_destination_url`, `names_at_destination`, observation time and SEO-check status. Unknown destinations remain null with a reason. Preserve raw excerpts or local evidence references without treating an alleged quote as true.

Full-story, paragraph, quote, number, image and CTA matches are separate observation types. Exact, normalized, translated and visual matches are not interchangeable. Keep each distinct name/destination even if normalized story content is identical. Content-family deduplication must not suppress new brand leads. Store query variants that omit the old brand so later runs do not keep finding only the already-known naming.

A run log records profile, user input/grouping decision, branches, exact queries/filters/locales, source availability, evidence paths, new names/domains/paths/relations, status changes and next pivots. Failed or empty searches are coverage observations, not proof of absence.

On resumption:

1. Load the active profile, its frontier and the global seen-index. Other teams' signatures are not positive search criteria.
2. Prioritize a fresh name, direct IP or brand link, unexamined deep path, or useful failed check whose retry condition is met.
3. Add a different route if previous work was one-sided: ads, brand search, full/partial advertorial reuse, content links, code/scans, infrastructure or history. Extract public exact-IP candidates and leave unprocessed candidates queued.
4. Every useful new candidate supplies its own pivots. Continue recursively; profile separation is not a stopping condition.
5. Check SEO presence independently of advertising design. Keep names with no found site on the frontier, with completed query coverage.
6. Save a delta. A domain known globally but newly connected to this profile is a new relation, not a new domain.

## Helper

`state_tool.py validate <state-dir>` checks structure, stable IDs, pattern ownership and incompatible attribution uses. It does not prove research conclusions.

`state_tool.py triage <state-dir> <candidates.json> --profile <id> --out <file>` never changes the registry. Input: array of objects with `url` or `domain`, optional `brand`, `source_refs`, `parent_pivot`. Output marks known/new domains, URLs and brands, plus prior presence in the chosen investigation. It never assigns ownership, changes active team or automatically merges aliases.

Create/rename profiles and reconcile accepted observations with ordinary file edits. Do not add an automatic “accept every match” import.

## Behavioral checks

- Different user-declared teams share hosting/SDK: expand candidates, retain separate profiles and record supplier overlap.
- Ad brand and differently designed SEO site: investigate brand/campaign evidence, do not reject for appearance.
- Name found, no site found in searches: save early name and coverage; do not invent a site or state that none was built.
- Repeat run finds new path on known domain: label new URL/name/relation, not new domain.
- Bare new user link: ask named-team-or-new. Agent-discovered link: queue within the active investigation.
- The same news-style story promotes three names, or the CTA changes while the story name stays old: retain each brand/destination observation and search each name's SEO presence; do not reduce the variants to one duplicate or infer a team merge.
