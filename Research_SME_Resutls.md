Executive Summary

    Lagebild: Starker Fachkräftemangel + überalterte Belegschaften in der Produktion/Instandhaltung führen zu hohem Wissensverlust-Risiko; Digitalisierung ist fragmentiert (viele Insellösungen, viel Papier/Excel), aber Smartphone‑Nutzung und erste digitale Assistenzlösungen sind verbreitet.
    Folgen: Häufige Abhängigkeit von OEM‑Services, lange Diagnosezeiten, erhöhtes Stillstandrisiko bei älteren Maschinen mit lückenhafter Dokumentation.

Kernaussagen / Zahlen (kompakt)

    Offene Stellen: BA Q4/2024 ≈ 1,4 Mio. offene Stellen gesamt; Branchendaten: Maschinenbau ~38 % Betriebe mit offenen Stellen; Metall/Elektro ~36–42 %. (Quellen: BA, DIHK, VDMA)
    Altersstruktur: Industrie: ~37 % der Beschäftigten >50 J.; Maschinenbau: 24,9 % ≥55 J. → große Rentenabgänge in den nächsten 10 Jahren (IW/VDMA‑Schätzungen: z. B. ~296.000 Abgänge Maschinenbau bis ca. 2033).
    Typische Berufe: Mechatroniker, Industriemechaniker, Elektroniker, Zerspanungsmechaniker, Werkzeugmechaniker; daneben viele angelernte Maschinenführer/Produktionshelfer (on‑the‑job‑training).
    Smartphone/OS: Privat/beruflich dominiert Android (akt. Schätzungen/Statcounter Apr 2026 ≈ 59 % Android / 41 % iOS); in der Produktion oft rugged Android‑Geräte.
    Digitale Tools: breites Spektrum — Excel/Paper weit verbreitet, ERP/PM (z. B. SAP PM) bei größeren KMU, spezial. CMMS in vielen KMU noch selten; Bitkom/Fraunhofer: Industry‑4.0‑Nutzung steigt, Predictive/KI noch limitiert.
    Maschinenpark: Haupttypen = CNC‑Fräsen (40–45 %), CNC‑Drehen (30–35 %), Industrieroboter (~20 %), Spritzguss, Pressen, Schweiß‑/Fügeanlagen, Verpackungsmaschinen. Viele Anlagen 10–20+ Jahre alt; ein relevanter Anteil (>~30–35 %) >15 Jahre.
    Marken/Steuerungen: Maschinenhersteller: DMG MORI, Hermle, Trumpf, Bystronic u. a.; Steuerungen: Siemens, Heidenhain, Fanuc dominieren (je nach Segment unterschiedlich).
    Wartung & Service: Routinewartung meist intern; komplexe Reparaturen häufig OEM oder spez. Dienstleister. Standardgarantie 12–24 Monate; optionale Wartungsverträge 1–5 Jahre (bei Großanlagen auch länger, bis ≈10 Jahre); Retrofit‑/Modernisierungsverträge üblich für ältere Anlagen.
    Stillstandkosten & MTTR: starke Bandbreite je Branche — realistische KMU‑Werte z. B. 250–3.750 €/h (branchenabhängig); MTTR typ. 4–8 Stunden; Diagnoseanteil oft groß (bis 50–70 % der Ausfallzeit). (Quellen: Fluke, VDMA, Osapiens, Fraunhofer)

Wissenstransfer & Kompetenzlücken (Kurz)

    Modalitäten: überwiegend informell (Training on the job, Mentoring, „Kladde“, Excel, gelegentlich Videos/YouTube). Systematisches Wissensmanagement in vielen KMU fehlt (Fraunhofer IAO/IML).
    Folgen: DIHK/Fachkräftereports: ~35 % der Firmen sehen Wissensverlust durch Renteneintritte als Problem. Externe OEM‑Service‑Nutzung üblich, Häufigkeit variiert nach Komplexität.

Dokumentation & sprachliche Faktoren

    Verfügbarkeit: Große OEMs bieten digitale Handbücher/OEM‑Portale; viele Zulieferer liefern nur Papier oder Englisch. Für Altmaschinen (>15 J.) sind Unterlagen oft unvollständig oder schwer auffindbar.
    Sprachen: Betriebsanleitungen müssen in der Landessprache vorliegen (Maschinenrichtlinie), praktisch sind viele Handbücher DE/EN; bei Importmaschinen mitunter nur EN/JP.
    Belegschaft mit Migrationshintergrund: deutlich über dem Durchschnitt in bestimmten Sektoren (z. B. Lebensmittel bis ~50 %; Metall/Elektro ≈30 %). Relevante Gebrauchssprachen: Türkisch, Polnisch, Russisch, Arabisch; Englisch meist nur fachsprachlich.

Wartungsverträge, Ersatzteile, Dokumentenkosten (Kurz)

    Verträge: Basisgarantie 12–24 Monate; Verlängerungen/SLAs möglich (1–5 Jahre üblich; Großanlagen länger). Retrofit & Condition‑Monitoring‑Pakete (jährliche Kosten) sind marktfähig, aber teurer.
    Ersatzteile/Dokumente: OEM liefern oft nur im Rahmen aktiver Serviceverträge; Ersatzhandbücher/Teilekataloge können kostenpflichtig sein (Ersatz‑Dokumente teils im zweistelligen Euro‑Bereich).
    Altmaschinen: Service/Teileversorgung möglich, aber mit längeren Lieferzeiten und ggf. höheren Kosten.

Konsequenzen / Leitlinien für Produktanforderungen (sehr kurz)

    Offline‑fähige Mobile App (robuste Sync), QR/Foto/NFC‑Identifikation, multimodale (Bild/Video/Voice) schnelle Wissens‑Capture, step‑by‑step Reparaturanleitungen, mehrsprachige und visuelle Inhalte, einfache Eskalation an OEM/externen Service, Schnittstellen zu CMMS/ERP. Unterstützung für rugged Android-Geräte ist Pflicht.

Wichtige offene Punkte (für Validierung vor Umsetzung)

    Genaue CMMS/ERP‑Penetration in deiner Zielgruppe (welche Systeme?)
    Exakte Maschinen‑Altersverteilung in Ziel‑KMU (10–500 MA) pro Branche
    Konkrete Downtime‑Kosten für die anvisierten Betriebsgrößen/Branchen
    Anteil formell ausgebildeter Maschinenbediener vs. angelernt in Zielkunden
    Prioritäre Sprachen je Region (DE plus welche weiteren?)

Quellen (präferiert / aus der Recherchebasis)

    Bundesagentur für Arbeit (BA), DIHK (Fachkräftereports), VDMA, Fraunhofer IAO / IML, Bitkom, Destatis, KOFA, Osapiens/Fraunhofer‑Studien, Fluke/Branchenreports, IW, Statcounter/Statista (for OS market shares) — siehe deine Originalrecherche für konkrete Auszüge und Links.
