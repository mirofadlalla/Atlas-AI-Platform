// `organization_name` is the canonical field: it's what the backend
// expects when a tenant is registered (see apiService.registerTenant)
// and what it echoes back in that response. GET /auth/profile should
// return the same field for a returning user. The extra fallbacks just
// guard against older/alternate shapes rather than being the primary source.
export function getOrganizationName(user) {
  if (!user) return null;
  return (
    user.organization_name ||
    user.organization ||
    user.tenant_name ||
    user.company_name ||
    (user.tenant && (user.tenant.organization_name || user.tenant.name)) ||
    null
  );
}

// Merges a /auth/profile-style response into the locally-held user object
// without clobbering fields the profile call doesn't return.
export function mergeProfileIntoUser(user, profile) {
  if (!profile) return user;
  return {
    ...user,
    ...profile,
    // Keep whichever id/tenant_id we already trust if the profile call
    // omits them.
    id: profile.id || user?.id,
    tenant_id: profile.tenant_id || user?.tenant_id,
  };
}
