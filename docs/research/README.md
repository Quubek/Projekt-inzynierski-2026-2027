# Notatki z researchu projektu

Data opracowania notatek: 22.10.2026.

Dokumenty zbierają ustalenia etapu koncepcyjnego oraz ich weryfikację w dokumentacji i literaturze. Opisują dostępne rozwiązania, proponowane decyzje i kwestie otwarte. Nie są sprawozdaniem z implementacji ani testów działającego systemu.

## Podział obszarów

| Osoba | Notatka | Zakres |
|---|---|---|
| Jakub Budziński (JB) | [API, Drain3 i baza danych](JB-api-drain3-baza.md) | Przyjmowanie i normalizacja logów, szablony, kontrakt API, porównanie baz |
| Jakub Filus (JF) | [Raporty LLM, Streamlit, Docker Compose i SIEM](JF-llm-dashboard-docker-siem.md) | Generowanie i walidacja raportów, historia, eksport, uruchamianie usług |
| Hubert Dyda (HD) | [Dane, detekcja anomalii i metryki](HD-detekcja-dane-metryki.md) | Przegląd metod, etykiety, baseline, embeddingi i plan eksperymentów |

## Wspólna koncepcja

Planowany przepływ:

```text
Surowe logi → API → normalizacja i Drain3 → grupowanie zdarzeń
→ reprezentacja tekstu i klasyfikator → wynik detekcji
→ dla anomalii: lokalny LLM → walidacja raportu → SQLite
→ API raportów → dashboard Streamlit → eksport
```

JB odpowiada za wejście do systemu i połączenie modułów w API. HD przygotowuje detekcję i określa wymagany sposób grupowania danych. JF przygotowuje raportowanie, zapis i odczyt raportów, dashboard oraz konfigurację uruchomienia. Kontrakt danych wymaga wspólnego uzgodnienia.

MVP obejmuje eksport JSON i Markdown. PDF i integracja z SIEM są rozszerzeniami. SQLite jest przyjętym wariantem prototypowym; PostgreSQL był rozważany jako alternatywa.

## Status i rezultat researchu

- Powstały notatki i wstępna koncepcja podziału modułów.
- Dokumentacja i publikacje potwierdzają dostępność opisanych mechanizmów, nie poprawność przyszłej implementacji.
- Nie powstały jeszcze działające API, parser, generator raportów, dashboard ani konfiguracja kontenerów.
- Nie wytrenowano modelu, nie obliczono własnych metryk ani nie zmierzono wydajności.
- Wybór oznaczonych danych zgodnych z demonstracją SSH oraz docelowego modelu LLM pozostaje do potwierdzenia.

## Wykorzystanie jako materiałów do sprawozdania

W polu „Materiały potwierdzające” sprawozdania można podać bezpośredni link do notatki danej osoby w katalogu `docs/research/`:

- JB: „Notatka z researchu API, Drain3 i baz danych wraz ze źródłami — [link do pliku]”.
- JF: „Notatka z researchu raportowania LLM, Streamlit, Docker Compose i SIEM wraz ze źródłami — [link do pliku]”.
- HD: „Notatka z researchu metod detekcji, danych i metryk wraz ze źródłami — [link do pliku]”.

Dla zachowania wersji ocenianej w sprawozdaniu najlepiej wskazać plik w konkretnym commicie. Notatki potwierdzają opracowanie koncepcji; nie zastępują wyników testów ani eksperymentów. Każda osoba powinna sprawdzić treść własnego obszaru i zgodność z rzeczywistym zakresem swoich prac przed wykorzystaniem odnośnika w sprawozdaniu.
