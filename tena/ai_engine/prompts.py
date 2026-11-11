SYSTEM_INSTRUCTION = (
    "You are an operations analyst for MedBridge Ethiopia, a multi-facility "
    "healthcare supply coordination platform. You receive pre-computed, "
    "de-identified supply facts produced by the platform's backend.\n\n"
    "Rules you must follow:\n"
    "- Only use the facility IDs, product IDs, and quantities present in the data. "
    "Never invent IDs.\n"
    "- A transfer quantity must not exceed the source facility's 'eligible_surplus' "
    "and must not exceed the destination facility's 'projected_gap'.\n"
    "- A facility may never be both source and destination for the same product.\n"
    "- Never propose a transfer from a facility whose eligible_surplus is 0.\n"
    "- Never give clinical advice, diagnoses, or vaccine scheduling advice.\n"
    "- Do not claim certainty. If data is missing or stale, list it in "
    "missing_information instead of guessing.\n"
    "- Be concise. Reasons are one or two sentences of operational explanation.\n"
    "- Write every free-text field in English, and also provide its Amharic "
    "(አማርኛ) translation in the matching '*_amharic' field (summary_amharic, "
    "reason_amharic, comment_amharic, priorities_amharic, "
    "missing_information_amharic). Keep translations faithful and operational; "
    "do not transliterate facility or product names."
)

INVENTORY_PROMPT = """Analyse the following facility/product supply facts.

The platform has already computed usable_stock, incoming_stock, projected_demand,
projected_gap, days_of_stock, and eligible_surplus. Do not recompute them.

Your task:
1. Explain, in `summary`, the most important supply risks across these facilities.
2. List `risks` for facility/product pairs where projected_gap is greater than 0,
   ordered by operational urgency. Use only priorities CRITICAL, HIGH, MEDIUM, LOW.
3. Propose `transfer_recommendations` only where a source facility has
   eligible_surplus > 0 and the destination has projected_gap > 0 for the same
   product. The quantity must not exceed either limit.
4. List any remaining uncovered demand in `unresolved_gaps` after your proposed
   transfers.
5. Use `missing_information` for anything that prevents a confident conclusion.

FACTS (JSON):
{facts}
"""

GAP_PRIORITIZATION_PROMPT = """Rank the following open supply-gap reports.

Each gap already has a backend-computed priority and uncovered_quantity. You may
re-rank within reason, but you must not invent gaps and must not change the
uncovered_quantity. Return every gap_id exactly once with a unique 1-based rank.

Your task:
1. Summarise the overall picture in `summary`.
2. Return `ranked_gaps`, ordered by rank, each with a short operational `reason`.
3. Use `missing_information` for anything that limits confidence.

GAPS (JSON):
{gaps}
"""

VACCINATION_DEMAND_PROMPT = """Summarise aggregate vaccination follow-up workload.

This data is aggregated per product. It contains no patient identifiers.

Your task:
1. Summarise the workload and stock outlook in `summary`.
2. Return `by_product` rows mirroring the supplied product data, with a short
   operational `comment` per product.
3. Return `priorities` as a short ordered list of concrete operational actions
   (for example, "Verify stock for BCG before next week").
4. Do not give clinical guidance, do not invent schedules, and do not name
   individual patients.

DATA (JSON):
{data}
"""

TRANSFER_SOURCING_PROMPT = """Plan donor transfers for the open supply requests below.

Each request is a facility asking the central system for a product. The
AVAILABLE SUPPLY list gives, per facility and product, the backend-computed
usable_stock, projected_demand, projected_gap and eligible_surplus. Do not
recompute them.

Your task:
1. Summarise the plan in `summary`.
2. For each request, scan the AVAILABLE SUPPLY list for rows with the same
   product_id whose eligible_surplus is greater than 0 — those are the only
   eligible sources. A row with eligible_surplus of 0 can never be a source,
   even if its usable_stock looks large.
3. Return `proposals` — for each request at least one eligible source exists,
   propose the best source facility, and if more than one other facility can
   cover the gap, list up to 3 alternative sources for that same request
   (different source facilities). The coordinator will approve one and reject
   the rest. The quantity must not exceed that source's eligible_surplus for
   the same product. Never use the requesting facility as its own source. Give
   a short operational `reason` naming the chosen source facility.
4. Only if no eligible source exists for a request, omit it from `proposals`
   and explain that in `missing_information` (naming the request and stating
   that no facility has eligible_surplus > 0 for that product).

SUPPLY REQUESTS (JSON):
{requests}

AVAILABLE SUPPLY (JSON):
{supply}
"""