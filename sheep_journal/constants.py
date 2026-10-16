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
    # False for rows that identify animals already counted, e.g. ear-tagging lambs
    # whose birth was recorded as a group. They don't change the balance.
    counted: bool = True


EVENT_TYPES = {
    e.key: e
    for e in [
        EventType("opening_balance", "in", "Ingående balans", "Ingående balans"),
        EventType("birth", "in", "Födda på gården", "Födda"),
        EventType(
            "tagging", "in", "Öronmärkning (identifiering)", "Identifiering / öronmärkning",
            counted=False,
        ),
        EventType("purchase", "in", "Inköp", "Inköp", movement=True),
        EventType(
            "loan_in", "in", "Inlånad / tillfälligt inkommen", "Inlånad / tillfälligt inkommen",
            movement=True,
        ),
        EventType(
            "return_home", "in", "Åter från tillfälligt ute", "Åter från tillfälligt ute",
            movement=True, temporary=True,
        ),
        EventType("recruitment_in", "in", "Egen rekrytering (nu individregistrerad)", "Egen rekrytering"),
        EventType("other_in", "in", "Övrigt in", "Övrigt in", movement=True),
        EventType("sale", "out", "Försäljning (levande)", "Försäljning", movement=True, transport=True),
        EventType("slaughter", "out", "Till slakt", "Slakt", movement=True, transport=True),
        EventType(
            "loan_return", "out", "Återlämnad till ägaren", "Återlämnad",
            movement=True, transport=True,
        ),
        EventType(
            "temp_out", "out", "Tillfälligt ute (bete m.m.)", "Tillfälligt ute",
            movement=True, transport=True, temporary=True,
        ),
        EventType("death", "out", "Död i besättningen", "Död i besättningen"),
        EventType("home_slaughter", "out", "Hemslakt", "Hemslakt"),
        EventType("recruitment_out", "out", "Egen rekrytering (ur grupp)", "Egen rekrytering"),
        EventType("other_out", "out", "Övrigt ut", "Övrigt ut", movement=True, transport=True),
    ]
}

UNCOUNTED_TYPES = tuple(k for k, e in EVENT_TYPES.items() if not e.counted)

# Events whose date isn't bound by the 48-hour rule: births are recorded once all
# lambs are born and tagged (at most 6 months after the first birth).
EXEMPT_FROM_48H = {"birth", "tagging", "opening_balance"}

SPECIES = {"sheep": "Får", "goat": "Get"}
SPECIES_PLURAL = {"sheep": "får", "goat": "getter"}
HOLDING_SPECIES = {"sheep": "Får", "goat": "Getter", "both": "Får och getter"}

SEXES = {"F": "Hona (tacka / get)", "M": "Hane (bagge / bock)"}

CATEGORIES = [
    "Kött",
    "Mjölk",
    "Ull",
    "Skinn",
    "Avel",
    "Landskapsvård",
    "Hobby",
]

TAG_TYPES = {"single": "Enkelt märke", "double": "Dubbla märken"}

CONTACT_KINDS = {"farm": "Gård", "slaughterhouse": "Slakteri", "other": "Övrigt"}

# Husbandry events outside the journal. Medicine kinds need the product recorded.
HERD_EVENT_KINDS = {
    "shearing": "Klippning",
    "treatment": "Läkemedelsbehandling",
    "vaccination": "Vaccination",
    "deworming": "Avmaskning",
    "hoof": "Klövverkning",
    "weighing": "Vägning",
    "mating": "Betäckning / bagge insläppt",
    "scanning": "Dräktighetsundersökning",
    "vet": "Veterinärbesök",
    "other": "Övrigt",
}
MEDICINE_KINDS = {"treatment", "vaccination", "deworming"}

FLAG_LABELS = {
    "late": "Registrerad > 48 h efter händelsen",
    "no_transport": "Transportör saknas",
    "no_cause": "Dödsorsak saknas",
}


def holding_species(holding):
    if holding is None:
        return ["sheep"]
    if holding["species"] == "both":
        return ["sheep", "goat"]
    return [holding["species"]]
