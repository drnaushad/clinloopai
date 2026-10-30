// Where the ClinLoop API lives.
// On the public site (GitHub Pages) there is no API: this static file leaves it unset.
// When the ClinLoop container serves these pages, the API answers /config.js itself
// and points the pages at its own origin.
window.CLINLOOP_API_BASE = window.CLINLOOP_API_BASE || null;
