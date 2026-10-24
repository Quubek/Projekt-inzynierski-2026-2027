# JF — Research raportów LLM, dashboardu, Docker Compose i SIEM

- Osoba odpowiedzialna za obszar: Jakub Filus (JF).
- Data opracowania notatki: 22.10.2026.
- Status: research dokumentacyjny; bez uruchomionych usług i testów praktycznych.

## 1. Cel i zakres

Rozpoznanie sposobu generowania czytelnych raportów z wykrytych anomalii, przechowywania historii i prezentowania wyników. Zakres obejmuje lokalny LLM przez Ollamę, walidację, SQLite, dashboard Streamlit, uruchomienie usług przez Docker Compose i możliwą integrację z Wazuh.

## 2. Generowanie raportu i structured outputs

Ollama pozwala przekazać schemat JSON w parametrze `format`. Schemat można uzyskać z modelu Pydantic, a otrzymaną odpowiedź zwalidować. Dokumentacja zaleca również umieszczenie schematu w instrukcji i obniżenie temperatury dla większej powtarzalności odpowiedzi. [Źródło: Ollama — Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs).

Kontrola struktury nie gwarantuje zgodności treści z rzeczywistością. Dlatego projekt przewiduje osobne sprawdzenie powiązania raportu z logami. Model ma opracować opis i rekomendację; fakty, takie jak host, czas, IP i liczba zdarzeń, mają pochodzić z kodu aplikacji.

Wstępnie proponowane pola raportu: identyfikator, opis zdarzenia, zakres czasu, host, kluczowe zdarzenia z identyfikatorami oraz rekomendacja. Ostateczny model danych wymaga uzgodnienia z JB i HD.

Planowane wejście do generatora to wynik detekcji wraz z powiązanymi zdarzeniami. Generator będzie wywoływany tylko dla anomalii. Obsługa niedostępności Ollamy, błędnej odpowiedzi i raportu zastępczego pozostaje do implementacji.

## 3. Dobór modelu i sprzętu

Jednym z kandydatów do pierwszych prób jest `qwen3:4b-instruct`, dostępny w bibliotece Ollamy jako model około 4 miliardów parametrów w kwantyzacji Q4_K_M. [Źródło: karta modelu w Ollamie](https://ollama.com/library/qwen3:4b-instruct).

Jest to kandydat, nie potwierdzony wybór. Nie wykonano pomiarów czasu generowania, zużycia RAM/VRAM ani jakości języka polskiego. Nie ustalono więc empirycznie minimalnych wymagań sprzętowych. Dobór zostanie potwierdzony krótkimi testami na dostępnym komputerze. Plan nie obejmuje trenowania LLM od podstaw.

## 4. Streamlit, historia i eksport

Proponowany dashboard będzie zawierał listę incydentów, szczegóły raportu, filtry i eksport. Raporty będą zapisywane w SQLite po stronie backendu, a interfejs pobierze dane przez API przygotowane z JB.

Streamlit udostępnia `st.download_button` do pobierania przygotowanych danych. Sam przycisk nie tworzy PDF ani Markdown — aplikacja musi wcześniej wygenerować zawartość pliku. [Źródło: dokumentacja st.download_button](https://docs.streamlit.io/develop/api-reference/widgets/st.download_button).

Decyzja zakresowa: JSON i Markdown w MVP; PDF jako rozszerzenie. W pierwszym prototypie wystarczy zapis i odczyt raportu bez dashboardu.

## 5. Docker Compose

Compose umożliwia opis usług, sieci i wolumenów w konfiguracji YAML oraz wspólne uruchamianie usług poleceniem `docker compose up`. [Źródło: Docker Compose](https://docs.docker.com/compose/).

Proponowana konfiguracja projektu obejmuje API, Streamlit i Ollamę. Baza SQLite pozostaje plikiem używanym przez backend; nie wymaga osobnej usługi bazodanowej. Należy zaplanować trwałe przechowywanie raportów i modeli oraz konfigurację adresu Ollamy. Wariant uruchomienia na GPU wymaga sprawdzenia środowiska.

Nie przygotowano ani nie uruchomiono jeszcze pliku Compose. Możliwość uruchomienia całego stosu nie została potwierdzona praktycznie.

## 6. Wazuh jako opcjonalne rozszerzenie

Moduł Integrator Wazuh umożliwia przekazywanie alertów do zewnętrznych narzędzi przez skrypty integracyjne. Wazuh publikuje również przykład wzbogacania alertów YARA przez zewnętrzny LLM. [Źródła: Integrator](https://documentation.wazuh.com/current/user-manual/manager/integration-with-external-apis.html), [przykład wzbogacania alertów](https://documentation.wazuh.com/current/proof-of-concept-guide/leveraging-llms-for-alert-enrichment.html).

To potwierdza możliwość połączeń tego rodzaju, ale nie stanowi gotowej integracji naszego systemu. Przykład korzysta z zewnętrznej usługi; projekt zakłada lokalne generowanie. Kierunek Wazuh → nasze API różni się od eksportu naszych raportów do SIEM. Wybór kierunku, mapowanie pól i sposób prezentacji pozostają otwarte. Integracja jest poza podstawowym zakresem MVP.

## 7. Rezultat i weryfikacja

Rezultatem jest koncepcja generatora, dashboardu i środowiska uruchomieniowego. Dokumentacja potwierdza dostępność mechanizmów kontroli formatu, pobierania plików i konfiguracji usług. Rozpoznano ograniczenia: format JSON nie zapewnia prawdziwości treści, a dobór sprzętu i modelu wymaga pomiarów.

Nie wygenerowano jeszcze raportu, nie utworzono bazy i nie uruchomiono dashboardu, kontenerów ani Wazuh. Nie ma własnych wyników jakości lub wydajności.

## 8. Następne kroki

1. Uzgodnić kontrakt wyniku detekcji i raportu.
2. Uruchomić lokalny model i wygenerować raport dla przykładowej anomalii.
3. Sprawdzić strukturę i zgodność faktów oraz zapis i odczyt SQLite.
4. Następnie przygotować dashboard, eksport i wspólne uruchomienie.

Materiały potwierdzające na tym etapie: niniejsza notatka i wskazane źródła; brak działającego kodu, bazy i wyników testów.
