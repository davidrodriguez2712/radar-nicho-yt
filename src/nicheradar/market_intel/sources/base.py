from typing import Protocol

from nicheradar.market_intel.contracts import CrawlResult, ListingDetail


class ListingSource(Protocol):
    name: str

    def crawl(self) -> CrawlResult: ...

    def fetch_detail(self, external_id: str) -> ListingDetail | None: ...
