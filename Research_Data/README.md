# Research Data — RepairRöpi Knowledge Corpus

> **Purpose:** This folder contains the curated research data, seed datasets, and source inventories needed to build the RepairRöpi knowledge layer. Everything here feeds directly into the Phase 0 Intelligence Spike (golden dataset, knowledge-layer shootout) and the ongoing knowledge pipeline.

## How This Folder Relates to the Mission

The Roadmap (Feature 0.0) requires **20 gold cases** with supporting documentation. The Knowledge Layer (Techstack §Knowledge) requires a corpus of error codes, manual pages, and fault patterns for SINUMERIK, Heidenhain, and Fanuc controllers. This folder is the staging area where that data is collected, structured, and validated before being promoted into `Repair_Logic_Agent/knowledge_spike/`.

---

## Directory Structure

```
Research_Data/
├── 01_error_code_databases/     ← Structured error/alarm code tables (YAML/JSON)
│   ├── sinumerik_alarms.yaml    ← SINUMERIK 840D/840D sl NC + drive alarms
│   ├── heidenhain_errors.yaml   ← Heidenhain TNC/iTNC error messages
│   ├── fanuc_alarms.yaml        ← Fanuc alarm codes by category
│   └── sources.md               ← Where each code came from
│
├── 02_service_manuals/          ← Manual source registry + download instructions
│   ├── manual_registry.yaml     ← Master list: what exists, where to get it, access level
│   └── download_guide.md        ← Step-by-step instructions for each portal
│
├── 03_community_knowledge/      ← Forum/Q&A data: real troubleshooting conversations
│   ├── forum_sources.yaml       ← Forum URLs, crawl strategies, licensing
│   └── sample_threads.jsonl     ← Seed sample of real diagnostic conversations
│
├── 04_fault_pattern_corpus/     ← Structured fault→symptom→cause→fix mappings
│   ├── mechanical_faults.yaml   ← Ball screw, bearing, spindle, axis patterns
│   ├── electrical_faults.yaml   ← Drive, encoder, power supply patterns
│   ├── control_faults.yaml      ← Parameter, PLC, software patterns
│   └── README.md                ← Taxonomy and schema explanation
│
├── 05_ml_datasets/              ← Open ML datasets for CNC fault detection
│   ├── dataset_registry.yaml    ← Links, descriptions, licensing
│   └── README.md                ← How each dataset maps to our use case
│
├── 06_spare_parts_data/         ← Part number cross-references & lookup tools
│   ├── bearing_cross_ref.yaml   ← SKF↔FAG↔NSK common CNC bearings
│   └── part_lookup_sources.md   ← Where to look up parts programmatically
│
└── 07_golden_test_cases/        ← Seed for the Phase 0 golden dataset
    ├── golden_cases.yaml        ← 20 SINUMERIK diagnostic cases (Roadmap Feature 0.0)
    └── README.md                ← Case format spec + validation instructions
```

---

## Data Collection Principles

1. **Respect licensing.** Every data point has a provenance entry. No bulk redistribution of copyrighted PDFs.
2. **Structured first.** Error codes are YAML/JSON, not prose. Machine-readable beats human-readable.
3. **CNC-vertical only.** No consumer electronics, no appliances. SINUMERIK → Heidenhain → Fanuc, in that priority.
4. **German-market reality.** Sources prioritize German-language forums, German OEM portals, and machines common in the Mittelstand.
5. **Seed, not scale.** This folder bootstraps the knowledge layer. The crawling pipeline (`Repair_Logic_Agent/data_crawling_pipe/`) handles scale.

---

*Stand: Mai 2026*
