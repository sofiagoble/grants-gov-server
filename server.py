#!/usr/bin/env python3
"""MCP server (streamable-http transport) wrapping the Simpler Grants API
(api.simpler.grants.gov) for federal grant opportunity search.

This is the hosted counterpart to the hispanic-latam-grants plugin's
find-grants skill: it gives the skill a real, structured, authenticated
search instead of scraping public pages with WebSearch/WebFetch. Deploy
this once (see README.md); the skill calls it as an MCP tool from then on,
and falls back to its own WebSearch/WebFetch method if this server is ever
unreachable.

Requires a Simpler Grants API key (free, via Login.gov - see README.md for
how to get one), passed as SIMPLER_GRANTS_API_KEY. The key lives only on
this server - it is never distributed to plugin installers.
"""
import os
from typing import Optional

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP

_API_BASE_URL = os.environ.get("SIMPLER_GRANTS_API_BASE_URL", "https://api.simpler.grants.gov")
_API_KEY = os.environ["SIMPLER_GRANTS_API_KEY"]

_http_client = httpx.AsyncClient(
    base_url=_API_BASE_URL,
    headers={"X-API-Key": _API_KEY, "Content-Type": "application/json"},
    timeout=20.0,
)

DEFAULT_LIMIT = 10
MAX_LIMIT = 50

_ORDER_BY_MAP = {
    "close_date_asc": ("close_date", "ascending"),
    "post_date_desc": ("post_date", "descending"),
    "award_ceiling_desc": ("award_ceiling", "descending"),
}


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def _summarize(row: dict) -> dict:
    summary = row.get("summary") or {}
    return {
        "opportunity_id": row.get("opportunity_id"),
        "opportunity_number": row.get("opportunity_number"),
        "title": row.get("opportunity_title"),
        "agency_name": row.get("agency_name"),
        "status": row.get("opportunity_status"),
        "award_ceiling": summary.get("award_ceiling"),
        "award_floor": summary.get("award_floor"),
        "post_date": summary.get("post_date"),
        "close_date": summary.get("close_date"),
        "applicant_types": summary.get("applicant_types") or [],
        "funding_categories": summary.get("funding_categories") or [],
        "description": summary.get("summary_description"),
        "url": f"https://simpler.grants.gov/opportunity/{row.get('opportunity_id')}",
        "additional_info_url": summary.get("additional_info_url"),
    }


mcp = FastMCP(
    "grants-gov",
    instructions="""\
Federal grant opportunity search (read-only) - backed live by the Simpler
Grants API (api.simpler.grants.gov), the modernized replacement for legacy
grants.gov search.

WHAT IT'S FOR: finding open federal grant opportunities matching an
organization's sector, keywords, or eligibility. Two tools:
  - search_opportunities: keyword/filter search returning a list of matches
  - get_opportunity: full detail for one opportunity by its ID (e.g. to
    confirm current status/eligibility before presenting it as a match)

Always check the returned `status` field before presenting an opportunity
as open - only "posted" is currently accepting applications. "forecasted"
means expected to open soon; "closed"/"archived" are no longer open.

Eligible applicant types matter: if every entry in `applicant_types` is a
government body (state/county/city/tribal) with no nonprofit/501(c)(3)
code, the money is a pass-through - it reaches nonprofits only through a
state or local administering agency, not this posting directly.""",
)


@mcp.tool(title="Search federal grant opportunities")
async def search_opportunities(
    query: Optional[str] = None,
    applicant_type: Optional[str] = None,
    funding_category: Optional[str] = None,
    opportunity_status: Optional[str] = None,
    min_award_ceiling: Optional[int] = None,
    order_by: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Search federal grant opportunities via the Simpler Grants API.

    Args:
        query: free-text search over title and description. Terms are
            ANDed by the upstream API - a search that returns too few
            results should use fewer/broader terms, not more.
        applicant_type: one of the Simpler Grants API's applicant-type
            codes, e.g. "nonprofits_non_higher_education_with_501c3",
            "state_governments", "unrestricted".
        funding_category: one of the Simpler Grants API's funding-category
            codes, e.g. "education", "health", "employment_labor_and_training".
        opportunity_status: one of "forecasted", "posted", "closed",
            "archived". Omit to search across all statuses; pass "posted"
            to restrict to currently-open opportunities.
        min_award_ceiling: minimum award ceiling in whole US dollars.
        order_by: one of "close_date_asc", "post_date_desc",
            "award_ceiling_desc". Defaults to relevancy order when `query`
            is set, otherwise the API's own default order.
        limit: max results to return (default 10, capped at 50).

    Returns:
        {"opportunities": [...]} - each entry has opportunity_id, title,
        agency_name, status, award_ceiling, award_floor, post_date,
        close_date, applicant_types, funding_categories, description, url,
        additional_info_url. Pass an entry's opportunity_id to
        get_opportunity for full detail if needed (search results already
        carry enough fields for most cases).
    """
    limit = _clamp_limit(limit)
    pagination: dict = {"page_offset": 1, "page_size": limit}
    body: dict = {"pagination": pagination}

    if query:
        body["query"] = query
        pagination["sort_order"] = [{"order_by": "relevancy", "sort_direction": "descending"}]

    filters: dict = {}
    if applicant_type:
        filters["applicant_type"] = {"one_of": [applicant_type]}
    if funding_category:
        filters["funding_category"] = {"one_of": [funding_category]}
    if opportunity_status:
        filters["opportunity_status"] = {"one_of": [opportunity_status]}
    if min_award_ceiling is not None:
        filters["award_ceiling"] = {"min": min_award_ceiling}
    if filters:
        body["filters"] = filters

    if order_by:
        field, direction = _ORDER_BY_MAP[order_by]
        pagination["sort_order"] = [{"order_by": field, "sort_direction": direction}]

    resp = await _http_client.post("/v1/opportunities/search", json=body)
    resp.raise_for_status()
    data = resp.json()
    return {"opportunities": [_summarize(r) for r in data.get("data", [])]}


@mcp.tool(title="Get one federal grant opportunity by ID")
async def get_opportunity(opportunity_id: str) -> dict:
    """Look up a single federal grant opportunity by its opportunity_id
    (as returned by search_opportunities).

    Returns the same fields as a search_opportunities entry, or
    {"error": "not_found"} if the ID doesn't exist.
    """
    resp = await _http_client.get(f"/v1/opportunities/{opportunity_id}")
    if resp.status_code == 404:
        return {"error": "not_found"}
    resp.raise_for_status()
    return _summarize(resp.json()["data"])


def main():
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))


if __name__ == "__main__":
    main()
