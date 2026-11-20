// Single source of truth for the backend API base URL.
// Local development (served from 127.0.0.1/localhost) talks to the local backend.
// On the phone over Wi-Fi, this page is opened via the computer's LAN IP, so
// window.location.hostname is already that IP — we reuse it for the API host.
const API_PORT = 8200;
const API_BASE_URL = `http://${window.location.hostname}:${API_PORT}`;
