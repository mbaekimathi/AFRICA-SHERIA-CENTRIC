"""Country dial codes with ISO flags for phone input."""

# (iso2, name, dial_code)
COUNTRY_DIAL_CODES = (
    ("KE", "Kenya", "+254"),
    ("UG", "Uganda", "+256"),
    ("TZ", "Tanzania", "+255"),
    ("RW", "Rwanda", "+250"),
    ("ET", "Ethiopia", "+251"),
    ("SO", "Somalia", "+252"),
    ("SS", "South Sudan", "+211"),
    ("SD", "Sudan", "+249"),
    ("DJ", "Djibouti", "+253"),
    ("ER", "Eritrea", "+291"),
    ("BI", "Burundi", "+257"),
    ("CD", "DR Congo", "+243"),
    ("CG", "Congo", "+242"),
    ("ZA", "South Africa", "+27"),
    ("NG", "Nigeria", "+234"),
    ("GH", "Ghana", "+233"),
    ("EG", "Egypt", "+20"),
    ("MA", "Morocco", "+212"),
    ("DZ", "Algeria", "+213"),
    ("TN", "Tunisia", "+216"),
    ("LY", "Libya", "+218"),
    ("CM", "Cameroon", "+237"),
    ("CI", "Côte d'Ivoire", "+225"),
    ("SN", "Senegal", "+221"),
    ("ZM", "Zambia", "+260"),
    ("ZW", "Zimbabwe", "+263"),
    ("MW", "Malawi", "+265"),
    ("MZ", "Mozambique", "+258"),
    ("BW", "Botswana", "+267"),
    ("NA", "Namibia", "+264"),
    ("AO", "Angola", "+244"),
    ("MG", "Madagascar", "+261"),
    ("MU", "Mauritius", "+230"),
    ("SC", "Seychelles", "+248"),
    ("GB", "United Kingdom", "+44"),
    ("IE", "Ireland", "+353"),
    ("US", "United States", "+1"),
    ("CA", "Canada", "+1"),
    ("AU", "Australia", "+61"),
    ("NZ", "New Zealand", "+64"),
    ("IN", "India", "+91"),
    ("PK", "Pakistan", "+92"),
    ("BD", "Bangladesh", "+880"),
    ("CN", "China", "+86"),
    ("JP", "Japan", "+81"),
    ("KR", "South Korea", "+82"),
    ("AE", "United Arab Emirates", "+971"),
    ("SA", "Saudi Arabia", "+966"),
    ("QA", "Qatar", "+974"),
    ("KW", "Kuwait", "+965"),
    ("BH", "Bahrain", "+973"),
    ("OM", "Oman", "+968"),
    ("TR", "Türkiye", "+90"),
    ("DE", "Germany", "+49"),
    ("FR", "France", "+33"),
    ("IT", "Italy", "+39"),
    ("ES", "Spain", "+34"),
    ("PT", "Portugal", "+351"),
    ("NL", "Netherlands", "+31"),
    ("BE", "Belgium", "+32"),
    ("CH", "Switzerland", "+41"),
    ("SE", "Sweden", "+46"),
    ("NO", "Norway", "+47"),
    ("DK", "Denmark", "+45"),
    ("FI", "Finland", "+358"),
    ("PL", "Poland", "+48"),
    ("BR", "Brazil", "+55"),
    ("MX", "Mexico", "+52"),
    ("AR", "Argentina", "+54"),
    ("SG", "Singapore", "+65"),
    ("MY", "Malaysia", "+60"),
    ("PH", "Philippines", "+63"),
    ("ID", "Indonesia", "+62"),
    ("TH", "Thailand", "+66"),
    ("VN", "Vietnam", "+84"),
    ("HK", "Hong Kong", "+852"),
    ("TW", "Taiwan", "+886"),
    ("IL", "Israel", "+972"),
    ("RU", "Russia", "+7"),
)

DEFAULT_COUNTRY = "KE"


def country_choices():
    """Choices value is ISO|DIAL for unique select values (US/CA share +1)."""
    return [
        (f"{iso}|{dial}", f"{name} ({dial})")
        for iso, name, dial in COUNTRY_DIAL_CODES
    ]


def countries_for_js():
    return [
        {
            "iso": iso.lower(),
            "name": name,
            "dial": dial,
            "value": f"{iso}|{dial}",
            "flag": f"https://flagcdn.com/w40/{iso.lower()}.png",
            "flag2x": f"https://flagcdn.com/w80/{iso.lower()}.png",
        }
        for iso, name, dial in COUNTRY_DIAL_CODES
    ]


def nationality_choices():
    return [(iso, name) for iso, name, _dial in COUNTRY_DIAL_CODES]


def country_name(iso: str) -> str:
    iso = (iso or DEFAULT_COUNTRY).upper()
    for code, name, _dial in COUNTRY_DIAL_CODES:
        if code == iso:
            return name
    return iso or "—"


def parse_country_value(value):
    if not value or "|" not in value:
        return DEFAULT_COUNTRY, "+254"
    iso, dial = value.split("|", 1)
    return iso.upper(), dial


def dial_for_iso(iso):
    iso = (iso or DEFAULT_COUNTRY).upper()
    for code, _name, dial in COUNTRY_DIAL_CODES:
        if code == iso:
            return f"{code}|{dial}"
    return f"{DEFAULT_COUNTRY}|+254"
