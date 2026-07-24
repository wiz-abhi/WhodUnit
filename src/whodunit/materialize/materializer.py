"""The :class:`Materializer` — the interface the pipeline/CLI drives.

Turns a verified :class:`CompiledQuery` into owned SigNoz artifacts: a Trace
Explorer permalink, a native v6 dashboard, and an armed v2alpha1 alert rule.
Thin by design: each method delegates to the tested builders in
:mod:`permalink`, :mod:`dashboard` and :mod:`alert`.
"""

from __future__ import annotations

from whodunit.materialize import _http, alert, dashboard, permalink
from whodunit.signoz_client import SigNozClient
from whodunit.types import CompiledQuery


class Materializer:
    """Materialise compiled discriminators into SigNoz artifacts.

    ``ui_base_url`` defaults to the client's configured instance URL (API and UI
    share an origin), and is used only to construct human-facing permalinks.
    """

    def __init__(self, client: SigNozClient, *, ui_base_url: str | None = None) -> None:
        self._client = client
        self._ui_base_url = (ui_base_url or _http.ui_base_url(client)).rstrip("/")

    # -- permalink --------------------------------------------------------- #

    def permalink(
        self,
        compiled: CompiledQuery,
        *,
        window_start_ms: int,
        window_end_ms: int,
    ) -> str:
        """A Trace Explorer URL opening the compiled composite query."""
        return permalink.build_permalink(
            compiled,
            ui_base_url=self._ui_base_url,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
        )

    # -- dashboard --------------------------------------------------------- #

    def create_dashboard(self, compiled: CompiledQuery, *, title: str) -> str:
        """Author a native v6 dashboard; return its id."""
        return dashboard.create_dashboard(self._client, compiled, title=title)

    def dashboard_url(self, dashboard_id: str) -> str:
        """The UI URL for a created dashboard."""
        return f"{self._ui_base_url}/dashboard/{dashboard_id}"

    def delete_dashboard(self, dashboard_id: str) -> None:
        dashboard.delete_dashboard(self._client, dashboard_id)

    # -- alert ------------------------------------------------------------- #

    def arm_alert(
        self,
        compiled: CompiledQuery,
        *,
        rule_name: str,
        warn_threshold: float,
        crit_threshold: float,
        channel_webhook_url: str | None,
        window: str = "5m0s",
    ) -> str:
        """Create/reuse a webhook channel, then POST the armed rule; return rule id."""
        channel = alert.ensure_channel(self._client, webhook_url=channel_webhook_url)
        return alert.create_rule(
            self._client,
            compiled,
            rule_name=rule_name,
            warn_threshold=warn_threshold,
            crit_threshold=crit_threshold,
            channel=channel,
            window=window,
        )

    def get_rule(self, rule_id: str) -> dict[str, object]:
        return alert.get_rule(self._client, rule_id)

    def delete_rule(self, rule_id: str) -> None:
        alert.delete_rule(self._client, rule_id)

    def delete_channel(self, channel_id: str) -> None:
        alert.delete_channel(self._client, channel_id)

    def channel_id_by_name(self, name: str) -> str | None:
        return alert.channel_id_by_name(self._client, name)


__all__ = ["Materializer"]
