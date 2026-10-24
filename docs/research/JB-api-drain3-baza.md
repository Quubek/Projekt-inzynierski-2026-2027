# JB — Research API, parsowania logów i bazy danych

- Osoba odpowiedzialna za obszar: Jakub Budziński (JB).
- Data opracowania notatki: 22.10.2026.
- Status: research dokumentacyjny; bez implementacji i testów praktycznych.

## 1. Cel i zakres

Rozpoznanie sposobu budowy warstwy wejściowej systemu: przyjmowania surowych logów, porządkowania zdarzeń, rozpoznawania szablonów i udostępniania wyników. Zakres obejmuje FastAPI, Drain3, wstępny kontrakt danych oraz porównanie SQLite i PostgreSQL.

## 2. FastAPI i dostęp do danych

Oficjalny samouczek FastAPI przedstawia integrację z relacyjną bazą przez SQLModel, modele danych, sesje i operacje zapisu oraz odczytu. Jest punktem odniesienia dla planowanego API. Zapoznanie się z samouczkiem nie oznacza jeszcze wyboru SQLModel jako obowiązkowej biblioteki projektu. [Źródło: FastAPI — SQL Databases](https://fastapi.tiangolo.com/tutorial/sql-databases/).

Proponowany kontrakt do uzgodnienia z zespołem:

| Endpoint | Planowana funkcja |
|---|---|
| `GET /health` | Sprawdzenie dostępności aplikacji |
| `POST /api/v1/analyze` | Przyjęcie paczki logów i uruchomienie analizy |
| `GET /api/v1/reports` | Pobranie listy zapisanych raportów |
| `GET /api/v1/reports/{report_id}` | Pobranie szczegółów raportu |

Są to propozycje, a nie istniejące endpointy. W pierwszej wersji wejściem może być JSON z listą tekstowych wpisów. Przed implementacją trzeba ustalić wymagane pola, limity paczek i sposób zwracania błędów.

## 3. Drain3 i normalizacja

Drain3 jest strumieniowym ekstraktorem szablonów komunikatów. Wyszukiwanie grup opiera na drzewie o stałej głębokości. Obsługuje maskowanie i ekstrakcję parametrów po rozpoznaniu szablonu. [Źródło: repozytorium Drain3](https://github.com/logpai/Drain3).

Ilustracja koncepcji, nie wynik uruchomionego parsera:

```text
Failed password for admin from 192.0.2.10 port 51234 ssh2
Failed password for root from 192.0.2.20 port 49812 ssh2

Oczekiwany wspólny wzorzec:
Failed password for <*> from <*> port <*> ssh2
```

Dokładny szablon będzie zależeć od masek, parametrów i danych. Drain3 nie rozstrzyga, czy zdarzenie jest atakiem. Należy osobno zaplanować odczyt nagłówka logu, normalizację czasu oraz przypisanie pól, np. IP i użytkownika. API powinno zachowywać oryginalny wpis i jego identyfikator, aby można było powiązać raport ze źródłem.

## 4. Rozpoznanie zbiorów logów

Loghub zawiera różne formaty logów. HDFS_v1 ma około 11,2 mln wpisów, a BGL około 4,7 mln. Próbki i opisy mogą pomóc określić wymagania parsera. Linux i OpenSSH nie są oznaczone w tabeli repozytorium jako zbiory z etykietami anomalii. [Źródło: Loghub](https://github.com/logpai/loghub).

Wniosek projektowy: format obsługiwany przez API trzeba uzgodnić z HD. Wyników modelu dla HDFS lub BGL nie należy automatycznie przenosić na logi SSH.

## 5. SQLite a PostgreSQL

| Kryterium | SQLite | PostgreSQL |
|---|---|---|
| Organizacja | Baza osadzona w aplikacji, przechowywana w pliku | Osobny serwer bazy danych |
| Uruchomienie prototypu | Bez osobnej usługi bazodanowej | Wymaga konfiguracji usługi i połączenia |
| Kierunek zastosowania | Proste lokalne przechowywanie danych | Rozbudowany dostęp współbieżny i wdrożenia serwerowe |

Porównanie oparto na [opisie zastosowań SQLite](https://www.sqlite.org/whentouse.html) i [opisie PostgreSQL](https://www.postgresql.org/about/). Nie wykonano porównania wydajności.

Decyzja projektowa: dla MVP przyjęto SQLite. JB przygotuje API dostępu do raportów, a JF kod zapisu i odczytu po stronie backendu. Dashboard ma korzystać z API, bez bezpośredniego otwierania pliku bazy.

## 6. Rezultat i weryfikacja

Rezultatem researchu jest koncepcja API, rozdzielenie normalizacji od ekstrakcji szablonów oraz wybór SQLite dla prototypu. Weryfikacja dokumentacyjna potwierdziła dostępność opisanych mechanizmów i wskazała zależność parsera od rodzaju logów.

Nie uruchomiono API, Drain3 ani bazy. Kontrakt pozostaje propozycją do przeglądu zespołowego. Kolejna weryfikacja powinna obejmować przyjęcie przykładowej paczki logów, odrzucenie błędnego wejścia i sprawdzenie pól oraz szablonów uzyskanych przez parser.

## 7. Kwestie otwarte i następne kroki

- Uzgodnienie z HD danych startowych, jednostki analizy i sposobu grupowania zdarzeń.
- Uzgodnienie z JF struktury raportu oraz odpowiedzi endpointów historii.
- Implementacja małego prototypu FastAPI i parsera dla jednego formatu.
- Podłączenie funkcji detekcji oraz raportowania do wspólnego przepływu.

Materiały potwierdzające na tym etapie: niniejsza notatka i wskazane źródła; brak kodu i wyników testów.
