from argus.adapters.base import BaseAdapter, CheckResult, StockStatus, ErrorKind
import requests
import time
import logging
from datetime import datetime

logger = logging.getLogger("argus.adapters.cineplex")

DATES_URL = "https://apis.cineplex.com/prod/cpx/theatrical/api/v1/dates/bookable"
SHOWTIMES_URL = "https://apis.cineplex.com/prod/cpx/theatrical/api/v1/showtimes"

HEADERS = {
    "Ocp-Apim-Subscription-Key": "dcdac5601d864addbc2675a2e96cb1f8", # public client side key
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
}

class CineplexAdapter(BaseAdapter):
    def source_name(self):
        return "cineplex"
    
    def check(self, product: dict) -> CheckResult:

        params = {
            "filmId": product["film_id"],
            "locationId": product["location_id"]
        }

        # === PHASE 1 - SEE IF THERE ARE ANY NEW DATES RELEASED ===
        start = time.monotonic()
        try:
            resp = requests.get(DATES_URL, params=params, headers=HEADERS, timeout=10)
        except requests.Timeout as e:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error(f"{product['id']} request failed: {e}")
            return CheckResult(StockStatus.UNKNOWN, latency_ms, f"request failed {e}", ErrorKind.TIMEOUT)
        except requests.ConnectionError as e:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error(f"{product['id']} request failed: {e}")
            return CheckResult(StockStatus.UNKNOWN, latency_ms, f"request failed {e}", ErrorKind.CONNECTION)
        except requests.RequestException as e:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error(f"{product['id']} request failed: {e}")
            return CheckResult(StockStatus.UNKNOWN, latency_ms, f"request failed {e}", ErrorKind.CONNECTION)
        
        latency_ms = (time.monotonic() - start) * 1000
        if 200 <= resp.status_code < 300:
            try:
                # cineplex's response looks like
                # ["2026-07-19T00:00:00","2026-07-20T00:00:00","2026-07-21T00:00:00"]
                data = resp.json()

                new_dates = [date for date in data if date[:10] > product["after_date"]]

                # If there are no new dates we'll do an early return
                if not new_dates:
                    return CheckResult(StockStatus.OUT_OF_STOCK, latency_ms)
                
            except (ValueError, KeyError, IndexError) as e:
                logger.error(f"{product['id']} json error: {e}")
                return CheckResult(StockStatus.UNKNOWN, latency_ms, f"json error {e}", ErrorKind.PARSE)

            logger.info(f"{product['id']} bookable_dates={len(data)} new_past_threshold={len(new_dates)} latency={latency_ms:.0f}ms")
            # === PHASE 2 - CONFIRM THE THEATRE HAS THE SHOWING ===
            for date in new_dates:
                dt = datetime.fromisoformat(date)

                params = {
                    "language": "en",
                    "locationId": product["location_id"],
                    "date": f"{dt.month}/{dt.day}/{dt.year}",
                    "filmId": product["film_id"]
                }

                try:
                    resp = requests.get(SHOWTIMES_URL, params=params, headers=HEADERS, timeout=10)
                except requests.Timeout as e:
                    latency_ms = (time.monotonic() - start) * 1000
                    logger.error(f"{product['id']} request failed: {e}")
                    return CheckResult(StockStatus.UNKNOWN, latency_ms, f"request failed {e}", ErrorKind.TIMEOUT)
                except requests.ConnectionError as e:
                    latency_ms = (time.monotonic() - start) * 1000
                    logger.error(f"{product['id']} request failed: {e}")
                    return CheckResult(StockStatus.UNKNOWN, latency_ms, f"request failed {e}", ErrorKind.CONNECTION)
                except requests.RequestException as e:
                    latency_ms = (time.monotonic() - start) * 1000
                    logger.error(f"{product['id']} request failed: {e}")
                    return CheckResult(StockStatus.UNKNOWN, latency_ms, f"request failed {e}", ErrorKind.CONNECTION)

                latency_ms = (time.monotonic() - start) * 1000
                if 200 <= resp.status_code < 300:
                    try:
                        data = resp.json()

                        for theatre in data:
                            for date_entry in theatre.get("dates", []):
                                for movie in date_entry.get("movies", []):
                                    if movie.get("id", 0) != product["film_id"]:
                                        continue
                                
                                    for experience in movie.get("experiences", []):
                                        experience_type = experience.get("experienceTypes", [])

                                        if set(product["experience"]).issubset(experience_type):
                                            for session in experience.get("sessions", []):
                                                if not session.get("isSoldOut", True) and not session.get("isInThePast", True):
                                                    logger.info(f"{product['id']} MATCH {product['experience']} on {date[:10]} session={session.get('showStartDateTime')} seats={session.get('seatsRemaining')}")
                                                    return CheckResult(StockStatus.IN_STOCK, latency_ms)
                                                                                    
                    except (ValueError, KeyError, IndexError) as e:
                        logger.error(f"{product['id']} json error: {e}")
                        return CheckResult(StockStatus.UNKNOWN, latency_ms, f"json error {e}", ErrorKind.PARSE)
                    
                else:
                    code = resp.status_code
                    retry_after = None

                    if code == 429:
                        kind = ErrorKind.RATE_LIMITED
                        retry_after: str | None = resp.headers.get("Retry-After")
                    elif code >= 500:
                        kind = ErrorKind.HTTP_5XX
                    elif code == 403:
                        kind = ErrorKind.BLOCKED
                    else:
                        kind = ErrorKind.HTTP_4XX

                    retry_after_s = float(retry_after) if retry_after and retry_after.isdigit() else None

                    logger.error(f"{product['id']} response status code: {resp.status_code}")
                    return CheckResult(StockStatus.UNKNOWN,latency_ms, f"http {resp.status_code}", kind, retry_after_s)
                
            return CheckResult(StockStatus.OUT_OF_STOCK, latency_ms)


        else:
            code = resp.status_code
            retry_after = None

            if code == 429:
                kind = ErrorKind.RATE_LIMITED
                retry_after: str | None = resp.headers.get("Retry-After")
            elif code >= 500:
                kind = ErrorKind.HTTP_5XX
            elif code == 403:
                kind = ErrorKind.BLOCKED
            else:
                kind = ErrorKind.HTTP_4XX

            retry_after_s = float(retry_after) if retry_after and retry_after.isdigit() else None

            logger.error(f"{product['id']} response status code: {resp.status_code}")
            return CheckResult(StockStatus.UNKNOWN,latency_ms, f"http {resp.status_code}", kind, retry_after_s)
                    