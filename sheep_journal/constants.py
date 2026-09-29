from dataclasses import dataclass


@dataclass(frozen=True)
class EventType:
    key: str
    direction: str  # "in" (plusblad) or "out" (minusblad)
    label: str
    label_sv: str
    # Animals come from / go to another holding: supplier or recipient is required.
    movement: bool = False
    # Animals leave on a vehicle: driver's name and vehicle registration are expected.
    transport: bool = False
    # Temporary stay away from the holding (tillfälligt ute), e.g. summer grazing.
    temporary: bool = False


EVENT_TYPES = {
    e.key: e
    for e in [
        EventType("opening_balance", "in", "Opening balance", "Ingående balans"),
        EventType("birth", "in", "Born on the holding", "Födda"),
        EventType("purchase", "in", "Purchased", "Inköp", movement=True),
        EventType("loan_in", "in", "Borrowed in (e.g. a ram)", "Inlånad", movement=True),
        EventType(
            "return_home", "in", "Back from temporary stay", "Åter från tillfälligt ute",
            movement=True, temporary=True,
        ),
        EventType("recruitment_in", "in", "Own recruitment (now individual)", "Egen rekrytering"),
        EventType("other_in", "in", "Other arrival", "Övrigt in", movement=True),
        EventType("sale", "out", "Sold live", "Försäljning", movement=True, transport=True),
        EventType("slaughter", "out", "Sent to slaughter", "Slakt", movement=True, transport=True),
        EventType(
            "loan_return", "out", "Borrowed animal returned", "Återlämnad",
            movement=True, transport=True,
        ),
        EventType(
            "temp_out", "out", "Temporarily away (grazing etc.)", "Tillfälligt ute",
            movement=True, transport=True, temporary=True,
        ),
        EventType("death", "out", "Died on the holding", "Död i besättningen"),
        EventType("home_slaughter", "out", "Home slaughter", "Hemslakt"),
        EventType("recruitment_out", "out", "Own recruitment (out of group)", "Egen rekrytering"),
        EventType("other_out", "out", "Other departure", "Övrigt ut", movement=True, transport=True),
    ]
}

# Events whose date isn't bound by the 48-hour rule: births are recorded once all
# lambs are born and tagged (at most 6 months after the first birth).
EXEMPT_FROM_48H = {"birth", "opening_balance"}

SPECIES = {"sheep": "Sheep (får)", "goat": "Goat (get)"}
HOLDING_SPECIES = {**SPECIES, "both": "Sheep and goats"}

SEXES = {"F": "Female (tacka / get)", "M": "Male (bagge / bock)"}

CATEGORIES = [
    "Meat (kött)",
    "Milk (mjölk)",
    "Wool (ull)",
    "Skins (skinn)",
    "Breeding (avel)",
    "Landscape management (landskapsvård)",
    "Hobby",
]

FLAG_LABELS = {
    "late": "Recorded > 48 h after event",
    "no_transport": "Transporter missing",
    "no_cause": "Cause of death missing",
}


def holding_species(holding):
    if holding is None:
        return ["sheep"]
    if holding["species"] == "both":
        return ["sheep", "goat"]
    return [holding["species"]]
