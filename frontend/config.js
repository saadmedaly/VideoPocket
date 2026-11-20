// Single source of truth for the backend API base URL.
//
// Relative paths ("" base) so the same build works whether this page is
// served directly by the dev static server, through the local reverse
// proxy (one origin for everything), or through the public Cloudflare
// Tunnel URL — in every case /api/* resolves against whatever origin the
// page itself was loaded from, with no hardcoded host or port.
const API_BASE_URL = '';
