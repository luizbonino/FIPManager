"""Application settings, env prefix FIPM_.

DECLARATION_STATUSES is the single source of truth for the allowed values of
the free-text "status" field inside a FIP's `answers` JSON. It will be
replaced by the enum finalised in docs/specs/00-fip-ontology-mapping.md; until
then this tuple is authoritative and nothing else may hard-code the values.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/fipm/config.py -> backend/fipm -> backend -> repo root. FIPM_DB_PATH
# and FIPM_DATA_DIR default relative to the repo root (not the process cwd),
# so `cd backend && uv run python -m fipm ...` finds ../data and ../fipm.db
# regardless of where it's invoked from.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

DECLARATION_STATUSES: tuple[str, ...] = (
    "current",
    "planned",
    "planned-development",
    "planned-replacement",
    "none",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIPM_", env_file=".env", extra="ignore")

    base_url: str = "http://localhost:8000"
    # spec 03 §2.1 / FAIR-ontology audit finding 2: the `fipmx` extension
    # VOCABULARY namespace (classes/properties FIP Manager defines) is a
    # fixed, deployment-independent IRI -- unlike instance IRIs (FIPs,
    # sessions, free-text FERs), which keep following base_url.
    ext_ns: str = "https://w3id.org/fipm/ns#"
    db_path: str = str(_REPO_ROOT / "fipm.db")
    secret_key: str = "dev-secret-change-me"
    id_prefix: str = ""
    admin_email: str | None = None
    admin_password: str | None = None
    default_language: str = "en"
    data_dir: str = str(_REPO_ROOT / "data")
    # Offline user guides (spec: GET /api/guides): docs/*-guide*.md +
    # docs/images/ are the single source of truth (never duplicated into
    # data/) and ship in the image via `COPY docs/ /app/docs/` in the
    # Dockerfile, which sets FIPM_GUIDES_DIR=/app/docs to match. Resolved
    # relative to the repo root, like data_dir/db_path above, so a local
    # checkout works with no env var set.
    guides_dir: str = str(_REPO_ROOT / "docs")
    static_dir: str = str(_REPO_ROOT / "frontend" / "dist")
    session_ttl_days: int = 14
    cookie_secure: bool = True
    allowed_origins: str = ""
    registration_open: bool = True
    # spec 09-standalone-fips.md: whether an anonymous caller with no
    # workshop session may create a FIP at all (POST /fips with neither
    # sessionId nor a signed-in cookie). True by default -- session
    # participants (who already carry a joinCode) are unaffected either way.
    anonymous_fips: bool = True
    env: str = "development"
    # Audit finding 12: nothing called `logging.basicConfig`/added a
    # handler, so every `logger.info` -- including the console mail
    # backend's only record of a verify/reset link -- was silently dropped
    # by the root logger's default WARNING level. `fipm.logging_setup.
    # configure_logging` reads this at startup; INFO by default so that
    # record is visible without any deployment-side configuration.
    log_level: str = "INFO"
    # Review finding 3: hard cap on the request body of any POST/PUT/PATCH
    # under /api/, enforced by fipm.main.BodySizeLimitMiddleware before the
    # body is read (a Content-Length over the cap is rejected outright; a
    # chunked/unbounded body is rejected as soon as the running total crosses
    # the cap). 2 MiB matches the pre-existing import-specific check.
    max_body_bytes: int = 2 * 1024 * 1024
    # spec 06-dmp-linkage.md §1.1: the host a `relatedDmps` URL is matched
    # against to detect a FioDMP plan (vs. a generic "other" plan URL).
    fiodmp_base_url: str = "https://fiodmp.fiocruz.br"
    # spec 06-dmp-linkage.md §3: comma-separated CSP `frame-ancestors` allow
    # list for GET /fips/{id}/embed. `'self'` is always prepended unless the
    # value is exactly `*`; empty means `'self'` only.
    embed_allowed_origins: str = "https://fiodmp.fiocruz.br"
    # spec 05-v1-completion.md §4: POST /api/feedback is 403 feedback_disabled
    # when False; both GET feedback routes keep working either way.
    feedback_enabled: bool = True
    # spec 05-v1-completion.md §2: substituted into the privacy notice
    # markdown for {{CONTACT_EMAIL}} / {{HOSTING_ORG}} and echoed by
    # GET /api/health.
    contact_email: str = "contact@example.org"
    hosting_org: str = "the FIP Manager operators"
    # Review finding 6: X-Forwarded-For is only trusted (for the feedback
    # rate limiter's client_ip()) when a reverse proxy in front of this
    # deployment is known to set it and strip any client-supplied copy --
    # False by default, since trusting it blindly lets a client spoof its
    # own rate-limit bucket.
    trust_proxy: bool = False

    # spec 11-nanopub-network.md §3.4: the read-only nanopublication-network
    # proxy. `network_enabled=false` -> 503 network_disabled on all three
    # /api/network/* endpoints and GET /api/health reports it, so the
    # frontend can hide the nav entry.
    network_enabled: bool = True
    # Scheme + host only, no trailing slash (checked by check_network_safety
    # below); every upstream URL is built as f"{this}/repo/..." or
    # f"{this}/api/...". The verified mirror https://query.petapico.org is a
    # drop-in alternative.
    nanopub_query_url: str = "https://query.knowledgepixels.com"
    network_timeout_seconds: float = 10.0
    network_cache_ttl_seconds: int = 900
    network_max_response_bytes: int = 8 * 1024 * 1024

    def check_network_safety(self) -> None:
        """Refuse to start with an `FIPM_NANOPUB_QUERY_URL` that could be
        turned into an SSRF vector (spec 11 §5): must be `https`, must have a
        hostname, must carry no userinfo and no path (every upstream URL is
        built by appending a *literal* path to this fixed base, so a base
        that already has a path or embedded credentials would silently
        change what gets requested, or leak credentials, on every call)."""
        parsed = urlparse(self.nanopub_query_url)
        if parsed.scheme != "https":
            raise RuntimeError(
                f"FIPM_NANOPUB_QUERY_URL must use https://, got {self.nanopub_query_url!r}"
            )
        if not parsed.hostname:
            raise RuntimeError(
                f"FIPM_NANOPUB_QUERY_URL must have a hostname, got {self.nanopub_query_url!r}"
            )
        if parsed.username or parsed.password:
            raise RuntimeError("FIPM_NANOPUB_QUERY_URL must not carry userinfo")
        if parsed.path:
            raise RuntimeError(
                f"FIPM_NANOPUB_QUERY_URL must have no path, got {self.nanopub_query_url!r}"
            )

    # spec 07-mail-and-migration.md §1: mail backend. `console` (default)
    # logs one INFO record on `fipm.mail`; `smtp` dispatches via
    # `smtplib.SMTP`/`SMTP_SSL`. Both features are off/invisible by default
    # (§0): console mail and FIPM_REQUIRE_EMAIL_VERIFICATION=false.
    mail_backend: str = "console"
    mail_from: str = "FIP Manager <no-reply@localhost>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_tls: str = "starttls"
    smtp_timeout: int = 10
    # spec 07 §2: the email-verification gate. Off by default -- nothing here
    # runs during CONFOA (spec §9 A1).
    require_email_verification: bool = False
    mail_token_ttl_hours: int = 24
    reset_token_ttl_hours: int = 1

    def check_mail_safety(self) -> None:
        """Refuse to start with an unusable mail configuration (spec 07 §1):
        an unknown FIPM_MAIL_BACKEND, `smtp` with no FIPM_SMTP_HOST, or an
        unrecognised FIPM_SMTP_TLS. The last one matters beyond a typo:
        `fipm.mail._send_smtp` treats anything other than the literal
        `"starttls"`/`"ssl"` as "send over a bare, unencrypted socket" --
        so a mistyped value (e.g. `"ststarttls"`) would silently drop TLS
        rather than fail loudly."""
        if self.mail_backend not in ("console", "smtp"):
            raise RuntimeError(
                f"FIPM_MAIL_BACKEND must be 'console' or 'smtp', got {self.mail_backend!r}"
            )
        if self.mail_backend == "smtp" and not self.smtp_host:
            raise RuntimeError("FIPM_SMTP_HOST is required when FIPM_MAIL_BACKEND=smtp")
        if self.smtp_tls not in ("starttls", "ssl", "none"):
            raise RuntimeError(
                f"FIPM_SMTP_TLS must be one of 'starttls', 'ssl', 'none', got {self.smtp_tls!r}"
            )

    # spec 13-fip-dashboard.md §7.5: the five-view dashboard. Defaults are
    # the cost model of §3/§4, not measurements -- §8.2's scale test exists
    # to replace them with real numbers on real hardware (§7.4).
    dashboard_enabled: bool = True
    dashboard_min_population: int = 5
    dashboard_live_max_cells: int = 250_000
    dashboard_sync_max_cells: int = 600_000
    dashboard_fallback_max_fips: int = 200
    dashboard_snapshot_ttl_seconds: int = 3600
    dashboard_snapshot_max_bytes: int = 4 * 1024 * 1024
    dashboard_csv_max_rows: int = 100_000
    dashboard_backfill_on_startup: bool = True
    dashboard_startup_backfill_max_fips: int = 500
    dashboard_posting_budget: int = 20_000
    dashboard_posting_cap: int = 2_000
    dashboard_candidate_cap: int = 200
    dashboard_df_skip_share: float = 0.20
    dashboard_df_min_keys: int = 3
    dashboard_lsh_k: int = 128
    dashboard_lsh_bands: int = 32
    dashboard_lsh_rows: int = 4
    dashboard_lsh_seed: int = 20260911
    dashboard_lsh_bucket_max: int = 500
    dashboard_lsh_pair_cap: int = 200_000
    dashboard_exact_pairs_max_fips: int = 300
    dashboard_live_max_fips_scatter: int = 300
    dashboard_cluster_min_sim: float = 0.6
    dashboard_default_weighting: str = "principle"
    # spec 13-fip-dashboard.md §11.3 (amendment, 11 Sep 2026): the scatter's
    # `edges` are thresholded at dashboard_cluster_min_sim, ordered by
    # similarity, and capped here -- an uncapped edge list is unbounded
    # (300 FIPs already admits 44,850 pairs) in a view whose whole premise
    # is that no response scales with the population.
    dashboard_map_edge_cap: int = 5000

    def check_dashboard_safety(self) -> None:
        """spec 13-fip-dashboard.md §7.5: refuse to start with a dashboard
        configuration that would silently corrupt LSH banding, admit a
        `population_too_small` bypass, allow the sync path to be *smaller*
        than the live-tier ceiling it must cover, or a document-frequency
        skip share that can never trigger (<=0) or that skips everything
        (>1). Modelled on `check_network_safety` above."""
        if self.dashboard_lsh_bands * self.dashboard_lsh_rows != self.dashboard_lsh_k:
            raise RuntimeError(
                "FIPM_DASHBOARD_LSH_BANDS * FIPM_DASHBOARD_LSH_ROWS must equal "
                f"FIPM_DASHBOARD_LSH_K, got {self.dashboard_lsh_bands} * "
                f"{self.dashboard_lsh_rows} != {self.dashboard_lsh_k}"
            )
        if self.dashboard_min_population < 1:
            raise RuntimeError(
                f"FIPM_DASHBOARD_MIN_POPULATION must be >= 1, got {self.dashboard_min_population}"
            )
        if self.dashboard_sync_max_cells < self.dashboard_live_max_cells:
            raise RuntimeError(
                "FIPM_DASHBOARD_SYNC_MAX_CELLS must be >= FIPM_DASHBOARD_LIVE_MAX_CELLS, got "
                f"{self.dashboard_sync_max_cells} < {self.dashboard_live_max_cells}"
            )
        if not (0 < self.dashboard_df_skip_share <= 1):
            raise RuntimeError(
                "FIPM_DASHBOARD_DF_SKIP_SHARE must be in (0, 1], got "
                f"{self.dashboard_df_skip_share}"
            )

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def embed_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.embed_allowed_origins.split(",") if o.strip()]

    def check_production_safety(self) -> None:
        """Refuse to start with an insecure default secret key in production."""
        if self.env == "production" and self.secret_key == "dev-secret-change-me":
            raise RuntimeError(
                "FIPM_SECRET_KEY must be set to a non-default value when FIPM_ENV=production"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
