"""Deterministic simulation of the Ucleany marketplace.

The simulation produces two views of the same data:

* ``changes``: every row version with ``_op`` and ``_commit_ts`` columns, the
  shape a CDC extract from SQL Server lands in the lakehouse.
* ``current``: the latest version of each row, the shape the operational
  SQL Server database holds today.

Both views carry the defects a real legacy database accumulates (duplicate
accounts, inconsistent free text, duplicate payment webhooks, out-of-range
ratings, internal test accounts). ``truth`` records exactly which rows are
defective so tests and the reconciliation can prove they were handled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd

from . import reference as ref

SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class ScenarioConfig:
    start: str = "2026-05-01"
    end: str = "2026-10-23"
    # Expansion to a second city is modelled but switched off: Ucleany only runs in Rome.
    milan_launch: str | None = None
    seed: int = 20260501
    scale: float = 1.0
    n_test_accounts: int = 12

    @property
    def start_ts(self) -> pd.Timestamp:
        return pd.Timestamp(self.start)

    @property
    def as_of_ts(self) -> pd.Timestamp:
        """Moment of the extract: the end date, 23:59:59 UTC."""
        return pd.Timestamp(self.end) + pd.Timedelta(hours=23, minutes=59, seconds=59)


@dataclass
class SyntheticDataset:
    config: ScenarioConfig
    changes: dict[str, pd.DataFrame]
    current: dict[str, pd.DataFrame]
    truth: dict[str, list] = field(default_factory=dict)


# Seasonality multipliers by calendar month.
ACQUISITION_SEASON = {1: 1.15, 2: 1.0, 3: 1.1, 4: 1.05, 5: 1.0, 6: 0.95, 7: 0.85, 8: 0.55, 9: 1.2, 10: 1.1, 11: 1.0, 12: 0.9}
TOURISM_SEASON = {1: 0.5, 2: 0.6, 3: 0.9, 4: 1.2, 5: 1.3, 6: 1.4, 7: 1.5, 8: 1.3, 9: 1.4, 10: 1.2, 11: 0.7, 12: 0.9}
HOUSEHOLD_SKIP = {1: 0.06, 2: 0.05, 3: 0.05, 4: 0.07, 5: 0.05, 6: 0.08, 7: 0.15, 8: 0.50, 9: 0.05, 10: 0.05, 11: 0.05, 12: 0.12}

HOURS_BY_SERVICE = {
    1: ([2.0, 2.5, 3.0, 3.5, 4.0], [0.30, 0.25, 0.25, 0.10, 0.10]),
    2: ([3.0, 4.0, 5.0, 6.0], [0.35, 0.35, 0.20, 0.10]),
    3: ([2.5], [1.0]),
    4: ([2.0, 3.0, 4.0], [0.45, 0.35, 0.20]),
    5: ([2.0, 3.0], [0.7, 0.3]),
    6: ([4.0, 6.0, 8.0], [0.4, 0.4, 0.2]),
    7: ([2.0, 3.0], [0.6, 0.4]),
}

LEVEL_MULTIPLIER = {"standard": 1.00, "senior": 1.05, "top": 1.10}

REVIEW_COMMENTS = {
    1: ["Non si e presentata in orario", "Lavoro fatto male", "Molto deludente"],
    2: ["Poco accurata in cucina", "Ritardo di un'ora", "Si poteva fare meglio"],
    3: ["Nella media", "Ok ma frettolosa", "Discreto"],
    4: ["Brava e puntuale", "Buon lavoro", "Casa pulita, qualche dettaglio da sistemare"],
    5: ["Perfetta, la richiedero", "Bravissima e gentile", "Casa splendente", "Servizio impeccabile", None],
}


def generate(config: ScenarioConfig | None = None) -> SyntheticDataset:
    cfg = config or ScenarioConfig()
    rng = np.random.default_rng(cfg.seed)

    zones = ref.zones_df()
    services = ref.services_df()
    channels = ref.channels_df()

    customers = _simulate_customers(rng, cfg, zones)
    bookings = _simulate_bookings(rng, cfg, customers)
    cleaners, cleaner_versions = _simulate_cleaners(rng, cfg, bookings, zones)
    bookings = _assign_cleaners(rng, bookings, cleaners)
    bookings = _finalise_bookings(rng, cfg, bookings, cleaner_versions, services)
    payments, duplicate_payment_ids = _simulate_payments(rng, cfg, bookings)
    reviews, invalid_review_ids, deleted_review_ids = _simulate_reviews(rng, cfg, bookings, cleaners)
    marketing = _simulate_marketing(rng, cfg, customers, channels)
    customer_versions = _customer_versions(rng, cfg, customers)

    as_of = cfg.as_of_ts
    changes = {
        "zones": _reference_changes(zones.drop(columns=["demand_weight", "short_let_weight"]), cfg),
        "services": _reference_changes(services, cfg),
        "channels": _reference_changes(channels.drop(columns=["cac_eur"]), cfg),
        "customers": customer_versions,
        "cleaners": cleaner_versions,
        "bookings": _booking_versions(bookings),
        "payments": _insert_only(payments, "created_at"),
        "reviews": _review_versions(reviews, deleted_review_ids),
        "marketing_spend": _reference_changes(marketing, cfg, ts_col="month_start"),
    }
    changes = {name: df[df["_commit_ts"] <= as_of].reset_index(drop=True) for name, df in changes.items()}

    keys = {
        "zones": ["zone_id"],
        "services": ["service_id"],
        "channels": ["channel_id"],
        "customers": ["customer_id"],
        "cleaners": ["cleaner_id"],
        "bookings": ["booking_id"],
        "payments": ["payment_id"],
        "reviews": ["review_id"],
        "marketing_spend": ["month_start", "city", "channel_id"],
    }
    current = {name: latest_versions(df, keys[name]) for name, df in changes.items()}

    test_ids = customers.loc[customers["_is_test"], "customer_id"].tolist()
    dup_ids = customers.loc[customers["_dup_of"].notna(), "customer_id"].tolist()
    truth = {
        "test_customer_ids": test_ids,
        "duplicate_customer_ids": dup_ids,
        "duplicate_payment_ids": [p for p in duplicate_payment_ids if p in set(current["payments"]["payment_id"])],
        "invalid_review_ids": [r for r in invalid_review_ids if r in set(current["reviews"]["review_id"])],
        "deleted_review_ids": deleted_review_ids,
    }
    return SyntheticDataset(config=cfg, changes=changes, current=current, truth=truth)


def fingerprint(ds: SyntheticDataset) -> str:
    """Stable hash of the current-state tables: proves two runs produced the same data."""
    import hashlib

    h = hashlib.sha256()
    for name in sorted(ds.current):
        df = ds.current[name]
        h.update(name.encode())
        h.update(df.to_csv(index=False, float_format="%.4f", date_format="%Y-%m-%dT%H:%M:%S").encode())
    return h.hexdigest()


def latest_versions(changes: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Collapse a change feed to the current state, dropping deleted rows."""
    ordered = changes.sort_values(keys + ["_commit_ts"], kind="mergesort")
    last = ordered.groupby(keys, sort=False).tail(1)
    last = last[last["_op"] != "DELETE"]
    return last.drop(columns=["_op", "_commit_ts"]).sort_values(keys).reset_index(drop=True)


# --------------------------------------------------------------------------- customers


def _logistic(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _monthly_signups(cfg: ScenarioConfig) -> list[tuple[pd.Timestamp, str, float]]:
    months = pd.date_range(cfg.start, cfg.end, freq="MS")
    milan = pd.Timestamp(cfg.milan_launch) if cfg.milan_launch else None
    out = []
    for i, m in enumerate(months):
        season = ACQUISITION_SEASON[m.month]
        # Share of the month covered by the extract (the last month is partial).
        elapsed = min(1.0, ((cfg.as_of_ts - m).total_seconds() / SECONDS_PER_DAY) / m.days_in_month)
        rome = (60 + 340 * _logistic(np.array((i - 2.5) / 1.2))) * season * elapsed
        out.append((m, "Roma", float(rome) * cfg.scale))
        if milan is not None and m >= milan:
            j = (m.year - milan.year) * 12 + m.month - milan.month
            launch_boost = 1.6 if j == 0 else 1.0
            mil = (22 + 130 * _logistic(np.array((j - 8) / 4.5))) * season * launch_boost
            out.append((m, "Milano", float(mil) * cfg.scale))
    return out


def _simulate_customers(rng: np.random.Generator, cfg: ScenarioConfig, zones: pd.DataFrame) -> pd.DataFrame:
    segments = list(ref.SEGMENT_MIX)
    seg_p = list(ref.SEGMENT_MIX.values())
    rows = []
    for month, city, expected in _monthly_signups(cfg):
        n = rng.poisson(expected)
        if n == 0:
            continue
        days_in_month = month.days_in_month
        seg = rng.choice(segments, size=n, p=seg_p)
        span = min(days_in_month * SECONDS_PER_DAY, int((cfg.as_of_ts - month).total_seconds()))
        offsets = rng.integers(0, span, size=n)
        city_zones = zones[zones["city"] == city]
        for k in range(n):
            s = seg[k]
            weights = city_zones["short_let_weight" if s == "short_let_host" else "demand_weight"].to_numpy()
            zone_id = int(rng.choice(city_zones["zone_id"].to_numpy(), p=weights / weights.sum()))
            channel_id = int(rng.choice([c[0] for c in ref.CHANNELS], p=ref.CHANNEL_MIX[s]))
            rows.append((month + pd.Timedelta(seconds=int(offsets[k])), city, s, zone_id, channel_id))

    cust = pd.DataFrame(rows, columns=["signup_at", "city", "segment", "zone_id", "acquisition_channel_id"])
    cust["_is_test"] = False
    cust["_dup_of"] = pd.Series([None] * len(cust), dtype="object")

    n = len(cust)
    first = rng.choice(ref.FIRST_NAMES[:40], size=n)
    last = rng.choice(ref.LAST_NAMES[:40], size=n)
    cust["first_name"] = first
    cust["last_name"] = last
    cust["profile"] = [_pick_profile(rng, s) for s in cust["segment"]]
    cust["marketing_opt_in"] = rng.random(n) < 0.62
    cust["_lifetime_months"] = _lifetimes(rng, cust)

    # Internal QA accounts used to test the app in production.
    t_n = cfg.n_test_accounts
    test_signups = pd.to_datetime(
        rng.integers(cfg.start_ts.value // 10**9, (cfg.as_of_ts - pd.Timedelta(days=60)).value // 10**9, size=t_n), unit="s"
    )
    test = pd.DataFrame(
        {
            "signup_at": test_signups,
            "city": "Roma",
            "segment": "household",
            "zone_id": 104,
            "acquisition_channel_id": 4,
            "_is_test": True,
            "_dup_of": None,
            "first_name": "QA",
            "last_name": [f"Tester {i + 1}" for i in range(t_n)],
            "profile": "one_off",
            "marketing_opt_in": False,
            "_lifetime_months": 1,
        }
    )
    cust = pd.concat([cust, test], ignore_index=True)
    cust = cust.sort_values("signup_at", kind="mergesort").reset_index(drop=True)
    cust["customer_id"] = np.arange(10_001, 10_001 + len(cust))
    cust["email"] = [
        _email(rng, fn, ln, cid, t) for fn, ln, cid, t in zip(cust["first_name"], cust["last_name"], cust["customer_id"], cust["_is_test"])
    ]
    # Different people never share an inbox: add the customer id when two addresses collide.
    seen: set[str] = set()
    for i, e in enumerate(cust["email"]):
        key = e.strip().lower()
        if key in seen:
            local, domain = e.split("@")
            e = f"{local}{cust.at[i, 'customer_id']}@{domain}"
            cust.at[i, "email"] = e
            key = e.strip().lower()
        seen.add(key)

    # Duplicate accounts: the same person signs up again with a differently cased email.
    real = cust[~cust["_is_test"]]
    n_dup = int(round(len(real) * 0.015))
    originals = real.sample(n=n_dup, random_state=int(rng.integers(1 << 31)))
    dups = originals.copy()
    dups["_dup_of"] = originals["customer_id"].to_numpy()
    dups["signup_at"] = originals["signup_at"].to_numpy() + pd.to_timedelta(rng.integers(3, 90, size=n_dup), unit="D")
    dups["email"] = [_recase(rng, e) for e in originals["email"]]
    dups["acquisition_channel_id"] = 4
    dups["segment"] = "household"
    dups["profile"] = "one_off"
    dups["_lifetime_months"] = 1
    dups = dups[dups["signup_at"] < cfg.as_of_ts - pd.Timedelta(days=14)]
    cust = pd.concat([cust, dups], ignore_index=True).sort_values("signup_at", kind="mergesort").reset_index(drop=True)
    is_dup = cust["_dup_of"].notna()
    max_id = int(cust["customer_id"].max())
    cust.loc[is_dup, "customer_id"] = np.arange(max_id + 1, max_id + 1 + int(is_dup.sum()))
    cust = cust.sort_values("customer_id").reset_index(drop=True)

    cust["phone"] = [_phone(rng) for _ in range(len(cust))]
    cust["city_text"] = [rng.choice(ref.CITY_SPELLINGS[c]) for c in cust["city"]]

    # A few customers move to another zone of the same city during their lifetime.
    movers = rng.random(len(cust)) < 0.06
    movers &= ~cust["_is_test"].to_numpy() & (cust["_lifetime_months"].to_numpy() >= 3)
    cust["_move_at"] = pd.NaT
    cust["_zone_after_move"] = pd.NA
    for i in np.flatnonzero(movers):
        life_days = int(cust.at[i, "_lifetime_months"] * 30)
        cust.at[i, "_move_at"] = cust.at[i, "signup_at"] + pd.Timedelta(days=int(rng.integers(30, max(31, life_days))))
        options = zones.loc[(zones["city"] == cust.at[i, "city"]) & (zones["zone_id"] != cust.at[i, "zone_id"]), "zone_id"].to_numpy()
        cust.at[i, "_zone_after_move"] = int(rng.choice(options))
    return cust


def _pick_profile(rng: np.random.Generator, segment: str) -> str:
    profiles = ref.FREQUENCY[segment]
    idx = rng.choice(len(profiles), p=[p[1] for p in profiles])
    return profiles[idx][0]


def _lifetimes(rng: np.random.Generator, cust: pd.DataFrame) -> np.ndarray:
    churn = cust["segment"].map(ref.MONTHLY_CHURN).to_numpy()
    life = rng.geometric(churn)
    life[cust["profile"].to_numpy() == "one_off"] = 1
    return life


def _ascii(s: str) -> str:
    return s.lower().replace(" ", "").replace("'", "")


def _email(rng: np.random.Generator, first: str, last: str, cid: int, is_test: bool) -> str:
    if is_test:
        return f"qa.{cid}@ucleany.test"
    style = rng.integers(0, 4)
    fn, ln = _ascii(first), _ascii(last)
    local = [f"{fn}.{ln}", f"{fn}{ln}{cid % 97}", f"{fn[0]}{ln}", f"{fn}_{ln}{cid % 13}"][style]
    email = f"{local}@{rng.choice(ref.EMAIL_DOMAINS)}"
    r = rng.random()
    if r < 0.12:
        email = email[0].upper() + email[1:]
    elif r < 0.14:
        email = f" {email}" if rng.random() < 0.5 else f"{email} "
    return email


def _recase(rng: np.random.Generator, email: str) -> str:
    e = email.strip()
    variants = [e.upper(), e.capitalize(), e.split("@")[0].title() + "@" + e.split("@")[1].upper()]
    return variants[int(rng.integers(0, len(variants)))]


def _phone(rng: np.random.Generator) -> str:
    digits = "3" + "".join(str(d) for d in rng.integers(0, 10, size=9))
    style = rng.integers(0, 5)
    if style == 0:
        return f"+39 {digits[:3]} {digits[3:6]} {digits[6:]}"
    if style == 1:
        return digits
    if style == 2:
        return f"0039{digits}"
    if style == 3:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return f"+39{digits}"


# --------------------------------------------------------------------------- bookings


def _simulate_bookings(rng: np.random.Generator, cfg: ScenarioConfig, cust: pd.DataFrame) -> pd.DataFrame:
    horizon = cfg.as_of_ts + pd.Timedelta(days=21)
    seg_service_ids = [s[0] for s in ref.SERVICES]
    out_cust, out_start, out_service, out_hours, out_zone, out_rec = [], [], [], [], [], []

    # itertuples drops attribute names that start with an underscore.
    for row in cust.rename(columns=lambda c: c.lstrip("_")).itertuples(index=False):
        signup = row.signup_at
        first = (signup + pd.Timedelta(days=float(rng.uniform(1, 9)))).normalize()
        if first > horizon:
            continue
        service = int(rng.choice(seg_service_ids, p=ref.SERVICE_MIX[row.segment]))
        hours_opts, hours_p = HOURS_BY_SERVICE[service]
        hours = float(rng.choice(hours_opts, p=hours_p))
        dates: list[pd.Timestamp] = []

        if row.profile == "one_off":
            dates.append(first)
            if row.is_test:
                for _ in range(int(rng.integers(1, 7))):
                    dates.append(first + pd.Timedelta(days=int(rng.integers(5, 120))))
            elif rng.random() < 0.30:
                for _ in range(int(rng.integers(1, 4))):
                    dates.append(first + pd.Timedelta(days=int(rng.integers(20, 180))))
            recurrence = "none"
        elif row.profile == "turnover":
            end = min(first + pd.DateOffset(months=int(row.lifetime_months)), horizon)
            for m in pd.date_range(first.replace(day=1), end, freq="MS"):
                k = rng.poisson(6.0 * TOURISM_SEASON[m.month])
                days = rng.integers(0, m.days_in_month, size=k)
                dates.extend(m + pd.Timedelta(days=int(d)) for d in days)
            dates = [d for d in dates if first <= d <= end] or [first]
            recurrence = "on_demand"
        else:
            step = {"monthly": 28, "biweekly": 14, "weekly": 7, "twice_weekly": 3.5}[row.profile]
            end = min(first + pd.DateOffset(months=int(row.lifetime_months)), horizon)
            n = int((end - first).days / step) + 1
            offsets = np.round(np.arange(n) * step).astype(int)
            cand = [first + pd.Timedelta(days=int(o)) for o in offsets]
            if row.segment == "household":
                cand = [d for d in cand if rng.random() >= HOUSEHOLD_SKIP[d.month]]
            else:
                cand = [d for d in cand if not (d.month == 8 and 8 <= d.day <= 22)]
            dates = cand or [first]
            recurrence = row.profile

        dates = [d for d in dates if d <= horizon]
        if not dates:
            continue
        n = len(dates)
        if row.segment == "office":
            hour = rng.choice([7.0, 7.5, 18.5, 19.0], size=n)
        else:
            hour = rng.choice(np.arange(8.0, 17.5, 0.5), size=n)
        starts = [d + pd.Timedelta(hours=float(h)) for d, h in zip(dates, hour)]
        # Households rarely book on Sundays: move those to Saturday.
        if row.segment == "household":
            starts = [s - pd.Timedelta(days=1) if s.dayofweek == 6 else s for s in starts]

        if row.profile == "one_off" and n > 1:
            svc = rng.choice(seg_service_ids, size=n, p=ref.SERVICE_MIX[row.segment]).astype(int)
            hrs = [float(rng.choice(HOURS_BY_SERVICE[int(s)][0], p=HOURS_BY_SERVICE[int(s)][1])) for s in svc]
        else:
            svc = np.full(n, service)
            hrs = [hours] * n

        move_at = row.move_at
        zones_for = [int(row.zone_after_move) if (pd.notna(move_at) and s > move_at) else int(row.zone_id) for s in starts]
        out_cust.extend([row.customer_id] * n)
        out_start.extend(starts)
        out_service.extend(svc.tolist())
        out_hours.extend(hrs)
        out_zone.extend(zones_for)
        out_rec.extend([recurrence] * n)

    b = pd.DataFrame(
        {
            "customer_id": out_cust,
            "scheduled_start": pd.to_datetime(out_start),
            "service_id": out_service,
            "planned_hours": out_hours,
            "zone_id": out_zone,
            "recurrence": out_rec,
        }
    )
    b = b.merge(cust[["customer_id", "signup_at", "segment", "city", "acquisition_channel_id", "_is_test"]], on="customer_id")
    b = b[b["scheduled_start"] > b["signup_at"]]
    return b.sort_values(["scheduled_start", "customer_id"], kind="mergesort").reset_index(drop=True)


# --------------------------------------------------------------------------- cleaners


def _simulate_cleaners(rng: np.random.Generator, cfg: ScenarioConfig, bookings: pd.DataFrame, zones: pd.DataFrame):
    months = pd.date_range(cfg.start, cfg.as_of_ts + pd.Timedelta(days=21), freq="MS")
    demand = (
        bookings.assign(month=bookings["scheduled_start"].dt.to_period("M").dt.to_timestamp())
        .groupby(["city", "month"])["planned_hours"]
        .sum()
    )
    capacity_choices = np.array([15, 20, 25, 30, 35])
    contract_choices = ["partita_iva", "prestazione_occasionale", "dipendente"]

    cleaners = []
    next_id = 501
    for city in ["Roma", "Milano"]:
        city_zones = zones[zones["city"] == city]
        zw = city_zones["demand_weight"].to_numpy()
        active: list[dict] = []
        for m in months:
            hours = float(demand.get((city, m), 0.0))
            if hours == 0 and not active:
                continue
            # Monthly churn after a two-month probation period.
            for c in active:
                tenure = (m - c["onboarded_at"]).days
                if tenure > 60 and c["offboarded_at"] is None and rng.random() < 0.035:
                    c["offboarded_at"] = m + pd.Timedelta(days=int(rng.integers(0, m.days_in_month)), hours=18)
            still = [c for c in active if c["offboarded_at"] is None]
            capacity = sum(c["weekly_capacity_hours"] for c in still) * 4.33
            needed = hours / 0.72
            while capacity < needed or len(still) < 3:
                cap = int(rng.choice(capacity_choices, p=[0.15, 0.25, 0.30, 0.20, 0.10]))
                c = {
                    "cleaner_id": next_id,
                    "city": city,
                    "home_zone_id": int(rng.choice(city_zones["zone_id"].to_numpy(), p=zw / zw.sum())),
                    "contract_type": str(rng.choice(contract_choices, p=[0.68, 0.22, 0.10])),
                    "weekly_capacity_hours": cap,
                    "onboarded_at": m - pd.Timedelta(days=int(rng.integers(3, 20))) + pd.Timedelta(hours=10),
                    "offboarded_at": None,
                    "quality": float(np.clip(rng.normal(4.55, 0.25), 3.6, 4.98)),
                    "first_name": str(rng.choice(ref.FIRST_NAMES)),
                    "last_name": str(rng.choice(ref.LAST_NAMES)),
                }
                next_id += 1
                still.append(c)
                cleaners.append(c)
                capacity += cap * 4.33
            active = still

    df = pd.DataFrame(cleaners)
    df["onboarded_at"] = df["onboarded_at"].clip(lower=cfg.start_ts - pd.Timedelta(days=20))
    df["offboarded_at"] = pd.to_datetime(df["offboarded_at"])
    df["email"] = [
        f"{_ascii(fn)}.{_ascii(ln)}{i}@team.ucleany.it" for fn, ln, i in zip(df["first_name"], df["last_name"], df["cleaner_id"])
    ]
    df["phone"] = [_phone(rng) for _ in range(len(df))]

    versions = _cleaner_versions(rng, cfg, df, zones)
    return df, versions


def _cleaner_versions(rng: np.random.Generator, cfg: ScenarioConfig, df: pd.DataFrame, zones: pd.DataFrame) -> pd.DataFrame:
    rows = []
    cols = [
        "cleaner_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "home_zone_id",
        "contract_type",
        "level",
        "weekly_capacity_hours",
        "onboarded_at",
        "offboarded_at",
    ]
    for c in df.itertuples(index=False):
        state = {k: getattr(c, k) for k in cols if k not in ("level", "offboarded_at")}
        state["level"] = "standard"
        state["offboarded_at"] = pd.NaT
        events = [(c.onboarded_at, "INSERT", dict(state))]
        end = c.offboarded_at if pd.notna(c.offboarded_at) else cfg.as_of_ts + pd.Timedelta(days=365)
        # Promotion after a 120-day review for well rated cleaners, top level after 240 days.
        senior_at = c.onboarded_at + pd.Timedelta(days=120)
        if senior_at < end and c.quality > 4.5:
            state["level"] = "senior"
            events.append((senior_at, "UPDATE", dict(state)))
            top_at = c.onboarded_at + pd.Timedelta(days=240)
            if top_at < end and c.quality > 4.7:
                state["level"] = "top"
                events.append((top_at, "UPDATE", dict(state)))
        if rng.random() < 0.05:
            move_at = c.onboarded_at + pd.Timedelta(days=int(rng.integers(30, 200)))
            if move_at < end:
                options = zones.loc[(zones["city"] == c.city) & (zones["zone_id"] != c.home_zone_id), "zone_id"].to_numpy()
                events.append((move_at, "ZONE", int(rng.choice(options))))
        if pd.notna(c.offboarded_at):
            events.append((c.offboarded_at, "OFFBOARD", None))

        events.sort(key=lambda e: e[0])
        state = dict(events[0][2])
        for ts, kind, payload in events:
            if kind == "INSERT":
                rows.append({**state, "_op": "INSERT", "_commit_ts": ts})
                continue
            if kind == "UPDATE":
                state["level"] = payload["level"]
            elif kind == "ZONE":
                state["home_zone_id"] = payload
            elif kind == "OFFBOARD":
                state["offboarded_at"] = ts
            rows.append({**state, "_op": "UPDATE", "_commit_ts": ts})
    out = pd.DataFrame(rows)
    out["offboarded_at"] = pd.to_datetime(out["offboarded_at"])
    out["modified_at"] = out["_commit_ts"]
    return out


def _assign_cleaners(rng: np.random.Generator, b: pd.DataFrame, cleaners: pd.DataFrame) -> pd.DataFrame:
    """Sticky assignment: a customer keeps the same cleaner while they are active."""
    starts = b["scheduled_start"].to_numpy()
    on = cleaners["onboarded_at"].to_numpy()
    off = cleaners["offboarded_at"].fillna(pd.Timestamp("2100-01-01")).to_numpy()
    ids = cleaners["cleaner_id"].to_numpy()
    city = cleaners["city"].to_numpy()
    zone = cleaners["home_zone_id"].to_numpy()
    by_city = {c: np.flatnonzero(city == c) for c in np.unique(city)}
    idx_of = {int(cid): i for i, cid in enumerate(ids)}

    assigned = np.zeros(len(b), dtype=np.int64)
    preferred: dict[int, int] = {}
    order = np.lexsort((starts, b["customer_id"].to_numpy()))
    cust_arr = b["customer_id"].to_numpy()
    city_arr = b["city"].to_numpy()
    zone_arr = b["zone_id"].to_numpy()
    for i in order:
        t = starts[i]
        cid = int(cust_arr[i])
        cur = preferred.get(cid)
        if cur is not None:
            j = idx_of[cur]
            if on[j] <= t < off[j] and rng.random() > 0.05:
                assigned[i] = cur
                continue
        pool = by_city[city_arr[i]]
        valid = pool[(on[pool] <= t) & (t < off[pool])]
        if len(valid) == 0:
            valid = pool[on[pool] <= t] if (on[pool] <= t).any() else pool
        w = np.where(zone[valid] == zone_arr[i], 3.0, 1.0)
        pick = int(ids[rng.choice(valid, p=w / w.sum())])
        preferred[cid] = pick
        assigned[i] = pick
    b = b.copy()
    b["cleaner_id"] = assigned
    return b


# --------------------------------------------------------------------------- booking lifecycle


def _rome_to_utc(local: pd.Series) -> pd.Series:
    return local.dt.tz_localize("Europe/Rome", ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC").dt.tz_localize(None)


def _finalise_bookings(
    rng: np.random.Generator, cfg: ScenarioConfig, b: pd.DataFrame, cleaner_versions: pd.DataFrame, services: pd.DataFrame
) -> pd.DataFrame:
    b = b.merge(services[["service_id", "pricing_model", "list_price_eur", "cleaner_rate_eur"]], on="service_id")
    b = b.sort_values(["scheduled_start", "customer_id"], kind="mergesort").reset_index(drop=True)
    n = len(b)
    start_utc = _rome_to_utc(b["scheduled_start"])
    b["_start_utc"] = start_utc

    # Prices: new price list from September 2026.
    after = b["scheduled_start"] >= pd.Timestamp(ref.PRICE_INCREASE_DATE)
    hourly = b["pricing_model"] == "hourly"
    up = b["list_price_eur"] * (1 + ref.PRICE_INCREASE_PCT)
    up = np.where(hourly, np.floor(up) + 0.90, np.round(up))
    b["unit_price"] = np.where(after, up, b["list_price_eur"]).round(2)

    # Lifecycle outcome.
    past = (start_utc + pd.to_timedelta(b["planned_hours"], unit="h")) <= cfg.as_of_ts
    r = rng.random(n)
    one_off = b["recurrence"].eq("none").to_numpy()
    p_cancel_c = np.where(one_off, 0.10, 0.065)
    status = np.full(n, "completed", dtype=object)
    status[r < p_cancel_c] = "cancelled_by_customer"
    band = (r >= p_cancel_c) & (r < p_cancel_c + 0.02)
    reassigned = band & (rng.random(n) < 0.6)
    status[band & ~reassigned] = "cancelled_by_cleaner"
    noshow = (r >= p_cancel_c + 0.02) & (r < p_cancel_c + 0.028)
    status[noshow] = "no_show"
    status[b["_is_test"].to_numpy() & (status != "completed")] = "completed"
    status[~past.to_numpy()] = "confirmed"
    b["status"] = status
    b["_reassigned"] = reassigned & (status == "completed")

    # Creation time: bookings are made between 12 hours and 14 days ahead.
    lead_h = rng.uniform(12, 14 * 24, size=n)
    created = start_utc - pd.to_timedelta(lead_h, unit="h")
    created = np.maximum(created, b["signup_at"] + pd.Timedelta(minutes=7))
    b["created_at"] = pd.to_datetime(created).dt.floor("s")

    # Billed hours: hourly jobs overrun by 30 minutes about 8% of the time.
    overrun = hourly.to_numpy() & (rng.random(n) < 0.08) & (status == "completed")
    b["billed_hours"] = np.where(overrun, b["planned_hours"] + 0.5, b["planned_hours"])
    b["planned_gross"] = np.where(hourly, b["unit_price"] * b["planned_hours"], b["unit_price"]).round(2)
    gross = np.where(hourly, b["unit_price"] * b["billed_hours"], b["unit_price"])
    gross = np.where(b["segment"].eq("office"), gross * 0.90, gross)
    b["gross_amount"] = np.round(gross, 2)
    b["planned_gross"] = np.where(b["segment"].eq("office"), b["planned_gross"] * 0.90, b["planned_gross"]).round(2)

    # Promotions on the first booking of a customer.
    first = ~b.duplicated("customer_id")
    promo = np.full(n, None, dtype=object)
    disc = np.zeros(n)
    welcome = first.to_numpy() & ~b["segment"].eq("office").to_numpy() & (rng.random(n) < 0.55)
    referral = first.to_numpy() & b["acquisition_channel_id"].eq(3).to_numpy()
    promo[welcome] = "BENVENUTO15"
    promo[referral] = "AMICO10"
    summer = (b["scheduled_start"].dt.year == 2026) & (b["scheduled_start"].dt.month == 7) & (rng.random(n) < 0.18) & (promo == None)  # noqa: E711
    promo[summer.to_numpy()] = "ESTATE10"
    disc = np.where(promo == "BENVENUTO15", b["gross_amount"] * 0.15, disc)
    disc = np.where(promo == "ESTATE10", b["gross_amount"] * 0.10, disc)
    disc = np.where(promo == "AMICO10", np.minimum(10.0, b["gross_amount"]), disc)
    b["promo_code"] = promo
    b["discount_amount"] = np.round(disc, 2)
    b["net_amount"] = (b["gross_amount"] - b["discount_amount"]).round(2)

    # Late cancellations (< 24h) and no-shows pay a 50% fee.
    cancel_lead_h = rng.uniform(0.5, np.maximum(1.0, (start_utc - b["created_at"]).dt.total_seconds() / 3600 - 0.5))
    late = (status == "cancelled_by_customer") & (cancel_lead_h < 24)
    b["cancelled_at"] = pd.NaT
    is_cancel = np.isin(status, ["cancelled_by_customer", "cancelled_by_cleaner"])
    b.loc[is_cancel, "cancelled_at"] = (start_utc - pd.to_timedelta(cancel_lead_h, unit="h"))[is_cancel].dt.floor("s")
    fee = np.where(late | (status == "no_show"), np.round(b["net_amount"] * 0.5, 2), 0.0)
    b["cancellation_fee"] = fee

    # Cleaner payout depends on the cleaner's level at the time of the job.
    level = _level_at(b, cleaner_versions)
    mult = level.map(LEVEL_MULTIPLIER).to_numpy()
    payout = np.where(hourly, b["cleaner_rate_eur"] * b["billed_hours"], b["cleaner_rate_eur"]) * mult
    b["cleaner_payout"] = np.where(status == "completed", np.round(payout, 2), 0.0)
    b["completed_at"] = pd.NaT
    done = status == "completed"
    b.loc[done, "completed_at"] = (start_utc + pd.to_timedelta(b["billed_hours"], unit="h"))[done]

    b = b.sort_values(["created_at", "customer_id"], kind="mergesort").reset_index(drop=True)
    b["booking_id"] = np.arange(1_000_001, 1_000_001 + len(b))

    # Reassigned jobs: the first cleaner dropped out, a colleague took over.
    if b["_reassigned"].any():
        idx = np.flatnonzero(b["_reassigned"].to_numpy())
        b["_original_cleaner_id"] = b["cleaner_id"]
        shuffled = b.loc[idx, "cleaner_id"].sample(frac=1.0, random_state=int(rng.integers(1 << 31))).to_numpy()
        b.loc[idx, "_original_cleaner_id"] = shuffled
    else:
        b["_original_cleaner_id"] = b["cleaner_id"]
    return b


def _level_at(b: pd.DataFrame, versions: pd.DataFrame) -> pd.Series:
    v = versions[["cleaner_id", "_commit_ts", "level"]].sort_values("_commit_ts")
    v["_commit_ts"] = v["_commit_ts"].astype("datetime64[us]")
    v["cleaner_id"] = v["cleaner_id"].astype("int64")
    left = b[["cleaner_id", "_start_utc"]].reset_index().sort_values("_start_utc")
    left["_start_utc"] = left["_start_utc"].astype("datetime64[us]")
    left["cleaner_id"] = left["cleaner_id"].astype("int64")
    merged = pd.merge_asof(left, v, left_on="_start_utc", right_on="_commit_ts", by="cleaner_id", direction="backward")
    return merged.set_index("index")["level"].reindex(b.index).fillna("standard")


def _booking_versions(b: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "booking_id",
        "customer_id",
        "cleaner_id",
        "service_id",
        "zone_id",
        "scheduled_start",
        "planned_hours",
        "billed_hours",
        "unit_price",
        "gross_amount",
        "discount_amount",
        "net_amount",
        "cancellation_fee",
        "cleaner_payout",
        "status",
        "recurrence",
        "promo_code",
        "created_at",
        "cancelled_at",
        "completed_at",
    ]
    v1 = b[cols].copy()
    v1["status"] = "confirmed"
    v1["cleaner_id"] = b["_original_cleaner_id"]
    v1["billed_hours"] = b["planned_hours"]
    v1["gross_amount"] = b["planned_gross"]
    v1["net_amount"] = (b["planned_gross"] - b["discount_amount"]).round(2)
    v1["cancellation_fee"] = 0.0
    v1["cleaner_payout"] = 0.0
    v1["cancelled_at"] = pd.NaT
    v1["completed_at"] = pd.NaT
    v1["_op"] = "INSERT"
    v1["_commit_ts"] = b["created_at"]

    final = b["status"] != "confirmed"
    v2 = b.loc[final, cols].copy()
    end_ts = b.loc[final, "completed_at"].fillna(b.loc[final, "cancelled_at"])
    noshow_ts = b.loc[final, "_start_utc"] + pd.Timedelta(minutes=45)
    v2["_commit_ts"] = end_ts.fillna(noshow_ts).dt.floor("s")
    v2["_op"] = "UPDATE"

    out = pd.concat([v1, v2], ignore_index=True)
    out["modified_at"] = out["_commit_ts"]
    return out.sort_values(["_commit_ts", "booking_id"], kind="mergesort").reset_index(drop=True)


# --------------------------------------------------------------------------- payments and reviews


def _simulate_payments(rng: np.random.Generator, cfg: ScenarioConfig, b: pd.DataFrame):
    done = b[b["status"] == "completed"]
    charges = pd.DataFrame(
        {
            "booking_id": done["booking_id"].to_numpy(),
            "payment_type": "charge",
            "amount": done["net_amount"].to_numpy(),
            "status": "succeeded",
            "created_at": (done["completed_at"] + pd.to_timedelta(rng.integers(60, 1800, size=len(done)), unit="s")).to_numpy(),
        }
    )
    # About 1.5% of first attempts fail and are retried the next day.
    failed_mask = rng.random(len(charges)) < 0.015
    failed = charges[failed_mask].copy()
    failed["status"] = "failed"
    charges.loc[failed_mask, "created_at"] = charges.loc[failed_mask, "created_at"] + pd.Timedelta(days=1)

    feeb = b[b["cancellation_fee"] > 0]
    fee_ts = feeb["cancelled_at"].fillna(feeb["_start_utc"] + pd.Timedelta(hours=1))
    fees = pd.DataFrame(
        {
            "booking_id": feeb["booking_id"].to_numpy(),
            "payment_type": "cancellation_fee",
            "amount": feeb["cancellation_fee"].to_numpy(),
            "status": "succeeded",
            "created_at": (fee_ts + pd.Timedelta(minutes=5)).to_numpy(),
        }
    )

    refund_mask = rng.random(len(done)) < 0.025
    rb = done[refund_mask]
    refunds = pd.DataFrame(
        {
            "booking_id": rb["booking_id"].to_numpy(),
            "payment_type": "refund",
            "amount": -np.round(rb["net_amount"].to_numpy() * rng.choice([0.3, 0.5, 1.0], size=len(rb), p=[0.4, 0.35, 0.25]), 2),
            "status": "succeeded",
            "created_at": (rb["completed_at"] + pd.to_timedelta(rng.integers(1, 6, size=len(rb)), unit="D")).to_numpy(),
        }
    )

    p = pd.concat([failed, charges, fees, refunds], ignore_index=True)
    p["provider"] = "stripe"
    p["currency"] = "EUR"
    p["provider_txn_id"] = [f"pi_{h:016x}" for h in rng.integers(0, 2**62, size=len(p))]

    # Payment provider webhook retries create duplicate rows for the same transaction.
    succeeded_charges = p.index[(p["status"] == "succeeded") & (p["payment_type"] == "charge")]
    dup_src = rng.choice(succeeded_charges, size=int(len(succeeded_charges) * 0.004), replace=False)
    dups = p.loc[np.sort(dup_src)].copy()
    dups["created_at"] = dups["created_at"] + pd.to_timedelta(rng.integers(1, 4, size=len(dups)), unit="s")
    dups["_is_dup"] = True
    p["_is_dup"] = False
    p = pd.concat([p, dups], ignore_index=True)
    p["created_at"] = pd.to_datetime(p["created_at"]).dt.floor("s")
    p = p.sort_values(["created_at", "booking_id", "_is_dup"], kind="mergesort").reset_index(drop=True)
    p["payment_id"] = np.arange(5_000_001, 5_000_001 + len(p))
    dup_ids = p.loc[p["_is_dup"], "payment_id"].tolist()
    p = p.drop(columns="_is_dup")
    cols = ["payment_id", "booking_id", "payment_type", "amount", "currency", "status", "provider", "provider_txn_id", "created_at"]
    return p[cols], dup_ids


def _simulate_reviews(rng: np.random.Generator, cfg: ScenarioConfig, b: pd.DataFrame, cleaners: pd.DataFrame):
    done = b[b["status"] == "completed"]
    done = done[rng.random(len(done)) < 0.55]
    q = done["cleaner_id"].map(cleaners.set_index("cleaner_id")["quality"]).to_numpy()
    rating = np.clip(np.round(rng.normal(q, 0.85)), 1, 5).astype(int)
    # A small share of jobs go badly regardless of the cleaner.
    disaster = rng.random(len(done)) < 0.015
    rating = np.where(disaster, rng.choice([1, 2], size=len(done)), rating)
    created = done["completed_at"] + pd.to_timedelta(rng.uniform(0.1, 7.0, size=len(done)), unit="D")

    # Until the app release of 15 July 2026, a bug let some ratings through as 0 or 6.
    buggy = (created < pd.Timestamp("2026-07-15")).to_numpy() & (rng.random(len(done)) < 0.012)
    rating = np.where(buggy, rng.choice([0, 6], size=len(done)), rating)

    comments = [rng.choice(REVIEW_COMMENTS[int(min(max(r, 1), 5))]) if rng.random() < 0.6 else None for r in rating]
    rv = pd.DataFrame(
        {
            "booking_id": done["booking_id"].to_numpy(),
            "customer_id": done["customer_id"].to_numpy(),
            "cleaner_id": done["cleaner_id"].to_numpy(),
            "rating": rating,
            "comment": comments,
            "created_at": pd.to_datetime(created.to_numpy()).floor("s"),
            "_invalid": buggy,
        }
    )
    rv = rv.sort_values(["created_at", "booking_id"], kind="mergesort").reset_index(drop=True)
    rv["review_id"] = np.arange(700_001, 700_001 + len(rv))
    invalid_ids = rv.loc[rv["_invalid"], "review_id"].tolist()
    # Moderation removes about 1% of reviews (spam, abuse).
    deleted = rv.loc[rng.random(len(rv)) < 0.01, "review_id"].tolist()
    rv = rv.drop(columns="_invalid")
    return rv[["review_id", "booking_id", "customer_id", "cleaner_id", "rating", "comment", "created_at"]], invalid_ids, deleted


def _review_versions(rv: pd.DataFrame, deleted_ids: list[int]) -> pd.DataFrame:
    ins = rv.copy()
    ins["_op"] = "INSERT"
    ins["_commit_ts"] = ins["created_at"]
    dele = rv[rv["review_id"].isin(deleted_ids)].copy()
    dele["_op"] = "DELETE"
    dele["_commit_ts"] = dele["created_at"] + pd.Timedelta(days=2)
    return pd.concat([ins, dele], ignore_index=True).sort_values(["_commit_ts", "review_id"], kind="mergesort").reset_index(drop=True)


# --------------------------------------------------------------------------- marketing and customer history


def _simulate_marketing(rng: np.random.Generator, cfg: ScenarioConfig, cust: pd.DataFrame, channels: pd.DataFrame) -> pd.DataFrame:
    real = cust[~cust["_is_test"] & cust["_dup_of"].isna()]
    counts = (
        real.assign(month_start=real["signup_at"].dt.to_period("M").dt.to_timestamp())
        .groupby(["month_start", "city", "acquisition_channel_id"])
        .size()
        .rename("new_customers")
        .reset_index()
        .rename(columns={"acquisition_channel_id": "channel_id"})
    )
    months = pd.date_range(cfg.start, cfg.end, freq="MS")
    cities = ["Roma"] + (["Milano"] if cfg.milan_launch else [])
    grid = pd.MultiIndex.from_product([months, cities, channels["channel_id"]], names=["month_start", "city", "channel_id"]).to_frame(
        index=False
    )
    if cfg.milan_launch:
        grid = grid[(grid["city"] == "Roma") | (grid["month_start"] >= pd.Timestamp(cfg.milan_launch) - pd.DateOffset(months=1))]
    m = grid.merge(counts, how="left").fillna({"new_customers": 0})
    cac = m["channel_id"].map(channels.set_index("channel_id")["cac_eur"])
    spend = m["new_customers"] * cac * rng.lognormal(0, 0.15, size=len(m))
    seo = m["channel_id"].eq(4)
    spend = np.where(seo, 900.0, spend)
    # Launch campaign in the first month on paid social and creators.
    launch = m["month_start"].eq(pd.Timestamp(cfg.start)) & m["channel_id"].isin([2, 6])
    spend = np.where(launch, spend + 3000.0, spend)
    m["spend_eur"] = np.round(spend, 2)
    return m[["month_start", "city", "channel_id", "spend_eur"]].reset_index(drop=True)


def _customer_versions(rng: np.random.Generator, cfg: ScenarioConfig, cust: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "segment",
        "zone_id",
        "city_text",
        "acquisition_channel_id",
        "signup_at",
        "marketing_opt_in",
    ]
    base = cust[cols].copy()
    base["_op"] = "INSERT"
    base["_commit_ts"] = base["signup_at"]
    frames = [base]

    moved = cust[cust["_move_at"].notna()]
    mv = moved[cols].copy()
    mv["zone_id"] = moved["_zone_after_move"].astype(int).to_numpy()
    mv["_op"] = "UPDATE"
    mv["_commit_ts"] = moved["_move_at"].to_numpy()
    frames.append(mv)

    phone_change = cust[(rng.random(len(cust)) < 0.04) & ~cust["_is_test"]]
    pc = phone_change[cols].copy()
    pc["phone"] = [_phone(rng) for _ in range(len(pc))]
    pc["_op"] = "UPDATE"
    pc["_commit_ts"] = phone_change["signup_at"].to_numpy() + pd.to_timedelta(rng.integers(10, 120, size=len(pc)), unit="D")
    frames.append(pc)

    out = pd.concat(frames, ignore_index=True).sort_values(["customer_id", "_commit_ts"], kind="mergesort")
    # Carry forward earlier changes so each version holds the full row state.
    out["zone_id"] = _carry(out, "zone_id", moved_ids=set(moved["customer_id"]), move_rows=mv)
    out["phone"] = out.groupby("customer_id")["phone"].transform(lambda s: s)

    # GDPR erasure for some churned customers, 30 to 90 days after their last activity.
    churned = cust[(cust["_lifetime_months"] <= 6) & ~cust["_is_test"]]
    erase = churned[rng.random(len(churned)) < 0.03]
    last_state = out.groupby("customer_id").tail(1).set_index("customer_id")
    er = last_state.loc[erase["customer_id"]].reset_index()
    er["first_name"] = None
    er["last_name"] = None
    er["phone"] = None
    er["email"] = [f"erased+{c}@privacy.ucleany.invalid" for c in er["customer_id"]]
    er["marketing_opt_in"] = False
    life = erase.set_index("customer_id")["_lifetime_months"].reindex(er["customer_id"]).to_numpy()
    er["_commit_ts"] = erase.set_index("customer_id")["signup_at"].reindex(er["customer_id"]).to_numpy() + pd.to_timedelta(
        life * 30 + rng.integers(30, 90, size=len(er)), unit="D"
    )
    er["_op"] = "UPDATE"
    out = pd.concat([out, er], ignore_index=True).sort_values(["_commit_ts", "customer_id"], kind="mergesort").reset_index(drop=True)
    out["modified_at"] = out["_commit_ts"]
    return out


def _carry(out: pd.DataFrame, col: str, moved_ids: set, move_rows: pd.DataFrame) -> pd.Series:
    """After a move, later versions (e.g. a phone change) keep the new zone."""
    result = out[col].copy()
    move_at = move_rows.set_index("customer_id")["_commit_ts"]
    new_zone = move_rows.set_index("customer_id")["zone_id"]
    mask = out["customer_id"].isin(moved_ids)
    sub = out[mask]
    later = sub["_commit_ts"].to_numpy() >= sub["customer_id"].map(move_at).to_numpy()
    result.loc[sub.index[later]] = sub.loc[sub.index[later], "customer_id"].map(new_zone).to_numpy()
    return result


def _reference_changes(df: pd.DataFrame, cfg: ScenarioConfig, ts_col: str | None = None) -> pd.DataFrame:
    out = df.copy()
    out["_op"] = "INSERT"
    out["_commit_ts"] = out[ts_col] if ts_col else cfg.start_ts - timedelta(days=30)
    if ts_col:
        # Spend for a month is booked on the first day of the following month.
        out["_commit_ts"] = pd.to_datetime(out[ts_col]) + pd.offsets.MonthBegin(1)
        out.loc[out["_commit_ts"] > cfg.as_of_ts, "_commit_ts"] = cfg.as_of_ts
    return out


def _insert_only(df: pd.DataFrame, ts_col: str) -> pd.DataFrame:
    out = df.copy()
    out["_op"] = "INSERT"
    out["_commit_ts"] = out[ts_col]
    return out
