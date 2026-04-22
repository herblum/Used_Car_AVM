# ─────────────────────────────────────────────
#  config.py — MercadoLibre car scraper config
# ─────────────────────────────────────────────
import os

# ── Firecrawl ─────────────────────────────────
# Get your key at https://app.firecrawl.dev
FIRECRAWL_API_KEY: str = os.environ["FIRECRAWL_API_KEY"]

# ── MercadoLibre ──────────────────────────────
# ML caps pagination at ~2000 results per search URL (~42 pages × 48 items).
# To collect more URLs we cycle through province-filtered listing URLs,
# each of which has its own independent 2000-item window.
# Provinces are ordered by used-car market size (largest first).
ITEMS_PER_PAGE   = 48          # ML paginates in steps of 48
MAX_PAGES_PER_FILTER = 42      # ML hard limit before results go empty

LISTING_URLS = [
    # ── Priority filters (largest used-car markets) ───────────────────────────
    # Path-based sub-regions of Buenos Aires + CABA
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/capital-federal",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/bsas-gba-norte",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/bsas-gba-sur",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/bsas-gba-oeste",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/bsas-costa-atlantica",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/buenos-aires-interior",
    # Province ID filters
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados_PciaId_cordoba",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados_PciaId_santa-fe",
    # ── Fallback provinces (smaller markets, used if more URLs needed) ────────
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/mendoza",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/tucuman",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/entre-rios",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/salta",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/misiones",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/corrientes",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/chaco",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/santiago-del-estero",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/san-juan",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/neuquen",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/rio-negro",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/jujuy",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/san-luis",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/la-pampa",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/chubut",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/catamarca",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/la-rioja",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/formosa",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/santa-cruz",
    "https://listado.mercadolibre.com.ar/autos-y-camionetas/usados/tierra-del-fuego",
]

# Keep for backward compatibility
BASE_LISTING_URL = LISTING_URLS[0]

# ── Scrape parameters — listing index pages ───
# firecrawl-py v4+ uses snake_case kwargs passed directly to app.scrape()
LISTING_PARAMS = {
    "formats":           ["markdown"],
    "only_main_content": True,
    "proxy":             "stealth",
    "wait_for":          2500,
    "mobile":            False,
    "location":          {"country": "AR", "languages": ["es-AR", "es"]},
    "exclude_tags": [
        "header", "footer", "nav", "aside",
        ".recommendations-carousel", ".ui-recommendations",
        ".nav-header", ".nav-footer", ".breadcrumb",
        "script", "style", "noscript",
    ],
}

# ── Scrape parameters — individual item pages ─
# include_tags removed — CSS class names vary and over-filter the specs table.
# only_main_content + exclude_tags is sufficient to get the full specs.
# Selectors cover both old (.ui-pdp-*) and new (.poly-*) ML component names.
ITEM_PARAMS = {
    "formats":           ["markdown"],
    "only_main_content": True,
    "proxy":             "stealth",
    "wait_for":          2000,
    "mobile":            False,
    "location":          {"country": "AR", "languages": ["es-AR", "es"]},
    "exclude_tags": [
        # HTML structural tags
        "header", "footer", "nav", "aside",
        "script", "style", "noscript",
        # Seller / store info block
        ".ui-pdp-seller-info", ".seller-container", ".seller-data-header",
        ".poly-component__seller-info", ".ui-seller-data",
        # Security tips
        ".security-tips", ".ui-pdp-security-tips",
        # Reference prices (shown on some listings)
        ".ui-pdp-price-reference", ".comparison-prices", ".ui-pdp-compats",
        # Recommendations / other seller listings
        ".recommendations", ".ui-recommendations", ".ui-recommendations-container",
        ".seller-other-items", ".poly-card--grid",
        # Contact seller form
        ".ui-pdp-contact", ".contact-seller", ".ui-pdp-contact-form",
        # Q&A, reviews, shipping estimate
        ".qadb", ".ui-review-capability", ".seller-reputation",
        ".questions-and-answers", ".ui-pdp-shipping",
        # Site footer nav links
        ".nav-footer", ".nav-footer-desktop",
    ],
}

# ── Pacing ────────────────────────────────────
SLEEP_MIN_S      = 3.0    # min sleep between individual item requests
SLEEP_MAX_S      = 7.0    # max sleep between individual item requests
BATCH_SLEEP_MIN  = 15.0   # min pause after each batch
BATCH_SLEEP_MAX  = 30.0   # max pause after each batch
LISTING_SLEEP_MIN = 4.0   # min pause between listing index pages
LISTING_SLEEP_MAX = 9.0   # max pause between listing index pages

# ── Retry ─────────────────────────────────────
MAX_RETRIES      = 4      # max retry attempts per URL
RETRY_BASE_S     = 5.0    # base seconds for exponential backoff

# ── Data paths ────────────────────────────────
DATA_DIR         = "data"
RAW_DIR          = "data/raw"
ITEM_URLS_FILE   = "data/item_urls.txt"
SCRAPED_URLS_FILE = "data/scraped_urls.json"   # global registry of successfully written URLs
