"""
One-shot historical bars — equivalent intent to:

  poetry run python examples/request_ibapi.py historical --duration "5 H" --bar-size "1 hour" --use-rth 1 --client-id 2

``reqHistoricalData`` ``durationStr`` only allows ``S|D|W|M|Y`` (no ``H``).
Five hours → ``18000 S``; ``request_ibapi`` gets that via ``Duration.to_ibkr_duration_str()``.

Bar size: IB expects ``1 hour``, not ``1 hours``. Needs TWS / IB Gateway on the socket.
"""

from __future__ import annotations

import os
import sys
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from ibapi.client import EClient
from ibapi.const import NO_VALID_ID
from ibapi.contract import Contract
from ibapi.errors import CONNECT_FAIL
from ibapi.wrapper import EWrapper

REQ_ID = 1

_NOISE = frozenset({2104, 2106, 2107, 2108, 2158, 2119, 2137})

HOST = "127.0.0.1"
PORT = 4002
CLIENT_ID = 2

SYMBOL = "GLD"
# IB rejects "5 H"; sub-day windows use seconds (max 86400 S per request).
DURATION_STR = f"{5 * 3600} S"
BAR_SIZE = "1 hour"
WHAT_TO_SHOW = "BID"
USE_RTH = 1

_PACIFIC = ZoneInfo("US/Pacific")
_UTC = ZoneInfo("UTC")
_END = datetime(2026, 4, 10, 1, 0, 0, tzinfo=_PACIFIC)


def _end_utc_str(dt: datetime) -> str:
    return dt.astimezone(_UTC).strftime("%Y%m%d-%H:%M:%S")


class App(EWrapper, EClient):
    def __init__(self) -> None:
        EClient.__init__(self, self)
        self._done = threading.Event()
        self._sent = False

    def nextValidId(self, orderId: int) -> None:
        if self._sent:
            return
        self._sent = True
        c = Contract()
        c.symbol = SYMBOL
        c.secType = "STK"
        c.exchange = "SMART"
        c.currency = "USD"
        end_s = _end_utc_str(_END)
        self.reqHistoricalData(
            reqId=REQ_ID,
            contract=c,
            endDateTime=end_s,
            durationStr=DURATION_STR,
            barSizeSetting=BAR_SIZE,
            whatToShow=WHAT_TO_SHOW,
            useRTH=USE_RTH,
            formatDate=1,
            keepUpToDate=False,
            chartOptions=[],
        )

    def historicalData(self, reqId, bar) -> None:
        if reqId == REQ_ID:
            print(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        if reqId == REQ_ID:
            self._done.set()

    def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson="") -> None:
        print(
            f"error reqId={reqId} errorTime={errorTime} code={errorCode} {errorString}",
            file=sys.stderr,
        )
        if reqId == NO_VALID_ID and errorCode == CONNECT_FAIL.code():
            self._done.set()
            return
        if errorCode in _NOISE:
            return
        if reqId in (NO_VALID_ID, REQ_ID):
            self._done.set()

    def connectionClosed(self) -> None:
        super().connectionClosed()
        self._done.set()


def test_historical_data(wait_timeout: float = 120.0) -> int:
    """Connect to IB Gateway/TWS API and fetch one historical request.

    Returns 0 when ``historicalDataEnd`` is received successfully, otherwise 1.

    Override defaults with env vars (optional):

    - ``IB_HIST_HOST`` — API host (default ``127.0.0.1``)
    - ``IB_HIST_PORT`` — API port (default ``4002`` paper in-container)
    - ``IB_HIST_CLIENT_ID`` — client id (default ``2``)

    Used by MCP / orchestrator (``IBGATEWAY_ACTION=test_historical_data``) and CLI ``test-historical-data``.
    """
    host = os.getenv("IB_HIST_HOST", HOST)
    port = int(os.getenv("IB_HIST_PORT", str(PORT)))
    client_id = int(os.getenv("IB_HIST_CLIENT_ID", str(CLIENT_ID)))

    app = App()
    app.connect(host, port, clientId=client_id)
    if not app.isConnected():
        print("connect() failed — is Gateway/TWS up and port correct?", file=sys.stderr)
        return 1
    threading.Thread(target=app.run, daemon=True).start()
    try:
        if not app._done.wait(timeout=wait_timeout):
            print("timed out waiting for historicalDataEnd", file=sys.stderr)
            return 1
        return 0
    finally:
        if app.isConnected():
            app.disconnect()


def main() -> int:
    return test_historical_data()


if __name__ == "__main__":
    raise SystemExit(main())
