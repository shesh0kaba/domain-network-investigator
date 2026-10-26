# Synthetic example: an advertisement leads to new names

All names, domains and observations below are invented. `.example` URLs are documentation placeholders, not targets to fetch. No real team signature is bundled with this skill.

1. The user supplies `https://publisher.example/news/interview/` and says this is a new team, “Example Team.” Create `team-001`, with this user-assigned grouping and no inherited signatures.
2. The article visibly promotes **Example Aurora**. Its observed CTA points to `https://offers.example/start/aurora/`. Save the article and destination separately; a link in source and a successfully visited destination are different observations.
3. A search for the exact name finds `https://aurora.example/`, with matching branding, About/FAQ/legal pages. Record `site_found`. Do not call it Google-indexed unless an actual Google result is preserved.
4. Search a rare sentence from the article **without “Example Aurora.”** A variant at `https://daily.example/features/interview/` promotes **Example Meridian**. Record both the matching paragraph and the changed name. Search the new name independently, even if its site looks different.
5. The source page links a custom script with a literal name list. Save the raw script and extract the first snapshot `[Example Aurora, Example Meridian]`. This is a baseline, not two newly launched names.
6. In a later run, a younger related domain serves a comparable script containing `[Example Aurora, Example Meridian, Example Cedar]`. Only **Example Cedar** is new to this dictionary history. Check whether it was already observed elsewhere in the registry. An identical copy of the old script on a new domain adds zero names.
7. Search for Example Cedar and find no verified SEO site in the completed checks. Keep the name with source evidence and open SEO/ad follow-ups. Do not invent `cedar.com` or substitute the name into an existing ad URL.
8. An exact-IP index shows another newly registered domain sharing a currently direct-looking serving IP. It has no responding website. Retain a domain-only candidate and its source/registration/DNS/failure records; the observed-name count does not increase. If the IP instead belongs to a CDN/proxy, overlap alone does not add that candidate.
9. The user separately starts “Example Team B.” A common SDK appears there too. Record shared-platform reuse and retain both profiles. Do not import all of Team A's names or treat the SDK as a Team B ownership signature.

The cumulative report retains the original article/CTA/SEO links and adds new observations. Each domain has its own registration date. Groups sort by their newest domain, unknown dates last. The next run loads the saved frontier and dictionary union, avoiding a restart from the first seed.
