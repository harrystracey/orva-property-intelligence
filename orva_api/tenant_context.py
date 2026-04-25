"""
Tenant resolution for the ORVA SaaS.

Phase 6 added a `tenant_id` column (TEXT NOT NULL DEFAULT 'orva') to
every multi-tenant table. This module is the seam where requests get
their tenant: routers call `current_tenant_id(user)`, which reads the
`tenant` claim out of the JWT and falls back to `DEFAULT_TENANT_ID`
when the claim is missing (single-tenant deployments / pre-multi-tenant
JWTs both keep working).

Manager modules (contact_manager, data_ingestion, etc.) accept a
`tenant_id` keyword argument with a default of `DEFAULT_TENANT_ID`,
so legacy callers that don't pass it still target the original
tenant -- no behaviour changes for the existing single-tenant
deployment.
"""

from __future__ import annotations

DEFAULT_TENANT_ID = "orva"


def current_tenant_id(user: dict | None) -> str:
    """
    Resolve the tenant for the current request.

    `user` is whatever orva_api.auth.get_current_user returned -- a dict
    that may carry a 'tenant' claim. If absent (legacy JWTs, anonymous
    contexts in tests), we return the default tenant.
    """
    if not user:
        return DEFAULT_TENANT_ID
    tenant = user.get("tenant")
    if not tenant or not isinstance(tenant, str):
        return DEFAULT_TENANT_ID
    return tenant
