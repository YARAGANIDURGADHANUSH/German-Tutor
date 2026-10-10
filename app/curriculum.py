"""Course map (aligned to Goethe-Zertifikat levels) and Sprechen exam outlines.

The exam outlines are practice approximations. Always check the current official
Modellsätze and format notes on goethe.de before your real exam date.
"""

UNITS = {
    "A1": [
        "Hallo and Tschüss: greetings, the alphabet, German sounds (ü, ö, ä, ch, r, ei/ie)",
        "Introducing yourself: ich heiße, ich komme aus, ich wohne in, ich spreche",
        "Numbers, age, phone numbers, spelling your name aloud",
        "Family and possessives: mein/meine, haben, sein",
        "Food, drinks, shopping: ich möchte, ich hätte gern, the accusative case, prices",
        "Time and daily routine: Uhrzeit, Wochentage, separable verbs",
        "Home and city: wohnen, Zimmer, es gibt, in/auf/neben",
        "Appointments and plans: können, müssen, wollen, Einladungen",
        "Directions and transport: Wegbeschreibung, Fahrkarte, Bahnhof",
        "Polite requests and A1 Sprechen mock exam",
    ],
    "A2": [
        "Past tense with haben/sein (Perfekt) and talking about yesterday",
        "Work, school and free time: weil, dass, denn",
        "Health and the doctor: Körper, Termin, Imperativ",
        "Clothes, shopping, comparing: Komparativ und Superlativ, Dativ",
        "Travel and accommodation: Hotel, Reise, Wegbeschreibungen",
        "Plans and invitations: werden, Konjunktiv II basics (ich würde gern)",
        "Housing and neighbours: Wohnungssuche, Beschwerden",
        "A2 Sprechen mock exam",
    ],
    "B1": [
        "Opinions and reasons: meiner Meinung nach, einerseits/andererseits",
        "Relative clauses and connectors: obwohl, damit, während",
        "Work life and applications: Bewerbung, Vorstellungsgespräch",
        "Media, technology and society: presenting a topic",
        "Planning something together and negotiating (B1 Sprechen Teil 1)",
        "Presenting a topic with structure (B1 Sprechen Teil 2)",
        "Reacting to a presentation and asking questions (B1 Sprechen Teil 3)",
        "B1 Sprechen full mock exam",
    ],
    "B2": [
        "Passive voice and nominalisation",
        "Argumentation and discussion: pro and contra",
        "Formal and semi-formal speaking: Bitten, Beschwerden, Vorträge",
        "B2 Sprechen mock exam",
    ],
}

EXAMS = {
    "A1": (
        "Goethe-Zertifikat A1 (Start Deutsch 1) Sprechen, about 15 minutes, normally with a "
        "partner. Teil 1: introduce yourself (name, age, country, city, languages, job, hobby). "
        "Teil 2: ask and answer simple questions from a keyword card (Wohnort, Essen, Familie, "
        "Uhrzeit ...). Teil 3: make polite requests and react (e.g. 'Können Sie bitte das "
        "Fenster öffnen?')."
    ),
    "A2": (
        "Goethe-Zertifikat A2 Sprechen, about 15 minutes, with a partner. Teil 1: ask and answer "
        "questions about a topic. Teil 2: talk about yourself or a familiar topic, then answer "
        "questions. Teil 3: plan something together and agree on details."
    ),
    "B1": (
        "Goethe-Zertifikat B1 Sprechen, about 15 minutes, in pairs. Teil 1: plan something "
        "together (propose, react, agree). Teil 2: give a short presentation on a topic "
        "(introduction, personal experience, situation in your country, pros and cons, "
        "conclusion) and answer a question. Teil 3: react to your partner's presentation: "
        "give feedback and ask a question."
    ),
    "B2": (
        "Goethe-Zertifikat B2 Sprechen: a prepared monologue presentation on a topic, then a "
        "discussion with a partner exchanging arguments for and against."
    ),
}

# CEFR rubric used when estimating exam scores
CRITERIA = ["task fulfilment", "interaction", "vocabulary", "grammar", "pronunciation and fluency"]

# Share of English the tutor should use at each level, and TTS speaking rate.
SCAFFOLD = {
    "A1": ("about 60 to 70 percent English, German phrases short and slow", "-15%"),
    "A2": ("about 40 percent English, mostly German instructions", "-8%"),
    "B1": ("about 15 percent English, only for tricky grammar explanations", "0%"),
    "B2": ("German only, English only if the learner is stuck", "0%"),
}
