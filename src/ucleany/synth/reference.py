"""Reference data for the synthetic Ucleany scenario.

Everything here is invented to resemble an on-demand cleaning marketplace in
Rome and Milan. None of it comes from the real company.
"""

from __future__ import annotations

import pandas as pd

# zone_id, zone_name, city, area_type, demand_weight, short_let_weight
ZONES = [
    (101, "Centro Storico", "Roma", "historic_centre", 1.3, 3.0),
    (102, "Monti", "Roma", "historic_centre", 1.1, 2.4),
    (103, "Trastevere", "Roma", "historic_centre", 1.2, 2.8),
    (104, "Prati", "Roma", "residential_premium", 1.6, 1.4),
    (105, "Parioli", "Roma", "residential_premium", 1.5, 0.6),
    (106, "Flaminio", "Roma", "residential_premium", 1.0, 0.7),
    (107, "Testaccio", "Roma", "residential", 0.9, 1.2),
    (108, "Ostiense", "Roma", "residential", 0.8, 0.6),
    (109, "San Lorenzo", "Roma", "residential", 0.7, 0.9),
    (110, "Pigneto", "Roma", "residential", 0.8, 0.8),
    (111, "Garbatella", "Roma", "residential", 0.7, 0.4),
    (112, "EUR", "Roma", "business", 1.2, 0.3),
    (113, "Monteverde", "Roma", "residential", 1.0, 0.5),
    (114, "Appio-Latino", "Roma", "residential", 1.1, 0.5),
    (115, "Nomentano", "Roma", "residential", 0.9, 0.5),
    (116, "San Giovanni", "Roma", "residential", 1.0, 0.9),
    (201, "Brera", "Milano", "historic_centre", 1.2, 2.2),
    (202, "Navigli", "Milano", "residential", 1.2, 1.8),
    (203, "Porta Romana", "Milano", "residential_premium", 1.3, 0.9),
    (204, "Isola", "Milano", "residential", 1.0, 1.2),
    (205, "Citta Studi", "Milano", "residential", 0.8, 0.6),
    (206, "Porta Venezia", "Milano", "residential", 1.1, 1.4),
    (207, "CityLife", "Milano", "business", 1.3, 0.4),
    (208, "Bicocca", "Milano", "business", 0.7, 0.3),
    (209, "Lambrate", "Milano", "residential", 0.6, 0.4),
    (210, "Centrale", "Milano", "business", 0.9, 1.6),
]

# service_id, code, name, pricing_model, price_eur, min_hours, cleaner_rate_eur
# Prices are what the customer pays (per hour, or per job for flat services).
# cleaner_rate_eur is what the cleaner earns (per hour, or per job).
SERVICES = [
    (1, "ORD", "Pulizia ordinaria", "hourly", 21.90, 2.0, 15.50),
    (2, "DEEP", "Pulizia profonda", "hourly", 27.90, 3.0, 19.00),
    (3, "STR", "Turnover affitti brevi", "flat", 59.00, 2.5, 38.00),
    (4, "OFF", "Pulizia uffici", "hourly", 24.90, 2.0, 17.00),
    (5, "IRON", "Stiro", "hourly", 19.90, 2.0, 14.00),
    (6, "RENO", "Post ristrutturazione", "hourly", 32.90, 4.0, 22.00),
    (7, "WIN", "Vetri", "hourly", 25.90, 2.0, 17.50),
]

# New price list from 1 September 2026, applied to every service.
PRICE_INCREASE_DATE = "2026-09-01"
PRICE_INCREASE_PCT = 0.05

# channel_id, code, name, is_paid, cac_eur (cost per acquired customer)
CHANNELS = [
    (1, "google_ads", "Google Ads", True, 38.0),
    (2, "meta_ads", "Meta Ads", True, 31.0),
    (3, "referral", "Referral programme", True, 10.0),
    (4, "organic_seo", "Organic / SEO", False, 0.0),
    (5, "partnerships", "Agenzie e property manager", True, 55.0),
    (6, "instagram_creators", "Instagram creators", True, 44.0),
]

# Share of new customers by channel, by segment.
CHANNEL_MIX = {
    "household": [0.30, 0.22, 0.18, 0.20, 0.02, 0.08],
    "short_let_host": [0.25, 0.10, 0.10, 0.15, 0.38, 0.02],
    "office": [0.45, 0.05, 0.10, 0.25, 0.15, 0.00],
}

SEGMENT_MIX = {"household": 0.78, "short_let_host": 0.14, "office": 0.08}

# Service mix by segment, in SERVICES order.
SERVICE_MIX = {
    "household": [0.68, 0.12, 0.0, 0.0, 0.11, 0.03, 0.06],
    "short_let_host": [0.0, 0.08, 0.92, 0.0, 0.0, 0.0, 0.0],
    "office": [0.0, 0.0, 0.0, 0.90, 0.0, 0.0, 0.10],
}

# Booking frequency profile by segment: (profile, share, bookings per 4 weeks)
FREQUENCY = {
    "household": [("one_off", 0.36, 0.0), ("monthly", 0.20, 1.0), ("biweekly", 0.25, 2.0), ("weekly", 0.19, 4.0)],
    "short_let_host": [("turnover", 1.0, 6.0)],
    "office": [("weekly", 0.65, 4.0), ("twice_weekly", 0.35, 8.0)],
}

# Monthly churn probability of a recurring customer, by segment.
MONTHLY_CHURN = {"household": 0.065, "short_let_host": 0.045, "office": 0.03}

FIRST_NAMES = [
    "Giulia",
    "Francesca",
    "Chiara",
    "Sara",
    "Martina",
    "Valentina",
    "Alessia",
    "Elena",
    "Federica",
    "Silvia",
    "Laura",
    "Anna",
    "Paola",
    "Roberta",
    "Ilaria",
    "Marta",
    "Beatrice",
    "Giorgia",
    "Claudia",
    "Serena",
    "Marco",
    "Luca",
    "Andrea",
    "Matteo",
    "Alessandro",
    "Lorenzo",
    "Davide",
    "Simone",
    "Francesco",
    "Stefano",
    "Giovanni",
    "Riccardo",
    "Federico",
    "Paolo",
    "Roberto",
    "Tommaso",
    "Emanuele",
    "Daniele",
    "Fabio",
    "Gabriele",
    "Ana",
    "Maria",
    "Ioana",
    "Elena",
    "Olena",
    "Rosa",
    "Carmen",
    "Lucia",
    "Mihaela",
    "Natalia",
    "Joy",
    "Grace",
    "Fatima",
    "Amina",
    "Rahim",
    "Jorge",
    "Luis",
    "Andrei",
    "Mihai",
    "Rafael",
]

LAST_NAMES = [
    "Rossi",
    "Russo",
    "Ferrari",
    "Esposito",
    "Bianchi",
    "Romano",
    "Colombo",
    "Ricci",
    "Marino",
    "Greco",
    "Bruno",
    "Gallo",
    "Conti",
    "De Luca",
    "Mancini",
    "Costa",
    "Giordano",
    "Rizzo",
    "Lombardi",
    "Moretti",
    "Barbieri",
    "Fontana",
    "Santoro",
    "Mariani",
    "Rinaldi",
    "Caruso",
    "Ferrara",
    "Galli",
    "Martini",
    "Leone",
    "Longo",
    "Gentile",
    "Martinelli",
    "Vitale",
    "Lombardo",
    "Serra",
    "Coppola",
    "De Santis",
    "D'Angelo",
    "Marchetti",
    "Popescu",
    "Ionescu",
    "Garcia",
    "Santos",
    "Reyes",
    "Cruz",
    "Kovalenko",
    "Shevchenko",
    "Rahman",
    "Hossain",
    "Fernandez",
    "Torres",
    "Dumitru",
    "Stan",
    "Mendoza",
    "Silva",
    "Pereira",
    "Bello",
    "Okafor",
    "Diallo",
]

EMAIL_DOMAINS = ["gmail.com", "libero.it", "hotmail.it", "yahoo.it", "outlook.com", "icloud.com", "virgilio.it", "tiscali.it"]

# Free-text city spellings that leak into the legacy customer table.
CITY_SPELLINGS = {
    "Roma": ["Roma", "Roma", "Roma", "ROMA", "Rome", "roma", "Roma (RM)", "Roma "],
    "Milano": ["Milano", "Milano", "Milano", "MILANO", "Milan", "milano", "Milano (MI)"],
}


def zones_df() -> pd.DataFrame:
    return pd.DataFrame(ZONES, columns=["zone_id", "zone_name", "city", "area_type", "demand_weight", "short_let_weight"])


def services_df() -> pd.DataFrame:
    return pd.DataFrame(
        SERVICES,
        columns=["service_id", "service_code", "service_name", "pricing_model", "list_price_eur", "min_hours", "cleaner_rate_eur"],
    )


def channels_df() -> pd.DataFrame:
    return pd.DataFrame(CHANNELS, columns=["channel_id", "channel_code", "channel_name", "is_paid", "cac_eur"])
