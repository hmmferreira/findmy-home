"""Keep empty Apple responses distinct from a legitimate no-sighting result."""
from findmy import AsyncAppleAccount
from findmy.errors import EmptyResponseError

class ReportSourceUnavailable(RuntimeError):
    """A stable classification; never carries the upstream response body."""

class ReportingAccount(AsyncAppleAccount):
    async def fetch_raw_reports(self, devices):
        try:
            return await super().fetch_raw_reports(devices)
        except EmptyResponseError:
            # FindMy.py's fetcher otherwise turns this protocol failure into [].
            raise ReportSourceUnavailable("empty_response") from None
