# RepairRöpi Mobile — Build & Run

## Dev-Loop (Feldtest, kein Android SDK nötig)

1. Backend starten (Laptop):
   ```bash
   cd Repair_Logic_Agent
   docker compose -f infra/docker-compose.yml up -d postgres minio
   S3_ENDPOINT_URL=http://<laptop-lan-ip>:9000 .venv/bin/uvicorn app.main:app --host 0.0.0.0
   ```
   (`S3_ENDPOINT_URL` mit LAN-IP — presigned URLs müssen vom Handy erreichbar sein,
   gleiche Falle wie beim 1.4-Feldtest.)
2. App starten: `cd RepairRöpiApp/mobile && npx expo start`
3. Handy: **Expo Go** installieren (Play Store), QR-Code scannen. Gleiches WLAN wie Laptop.
   Die App leitet die API-URL aus dem Metro-Host ab (`http://<laptop-ip>:8000`) — null Konfiguration.

## Checks

```bash
npm run typecheck   # tsc --noEmit
npm test            # Reducer-Tests (node --test, kein Framework)
```

## APK bauen (Akzeptanz: rugged Android)

`extra.apiUrl` ist gebacken (`http://192.168.178.30:8000` — Laptop-LAN-IP; im APK gibt
es keinen Metro-Host; bei neuer IP hier ändern + neu bauen). Expo Go ignoriert das und
leitet weiter vom Metro-Host ab. Optional `extra.tenantId` pro Pilot-Kunde.

**Pfad A — EAS Cloud-Build (eingerichtet: projectId in app.json, eas.json vorhanden):**
```bash
npx eas-cli login                                  # einmalig, interaktiv
npx eas-cli build -p android --profile preview     # → APK-Download-Link
```
Falls die Projekt-Verknüpfung bemängelt wird:
`npx eas-cli init --id 07eafe19-1728-4f40-a2fa-7132c43a1da6`

**Pfad B — lokal (Android SDK + JDK 17+ nötig, JDK 21 vorhanden):**
```bash
npx expo prebuild -p android   # generiert android/
cd android && ./gradlew assembleRelease
# → android/app/build/outputs/apk/release/app-release.apk
```

`usesCleartextTraffic` ist aktiv (LAN-HTTP im Feldtest); wird mit dem
HTTPS-Deploy in Feature 3.1 wieder entfernt.
