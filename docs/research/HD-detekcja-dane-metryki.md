# HD — Research detekcji anomalii, danych i metryk

- Osoba odpowiedzialna za obszar: Hubert Dyda (HD).
- Data opracowania notatki: 22.10.2026.
- Status: przegląd literatury i dokumentacji; bez treningu i własnych wyników metryk.

## 1. Cel i zakres

Rozpoznanie metod reprezentacji logów i wykrywania anomalii, dostępnych danych oraz sposobu oceny detekcji. Zakres obejmuje TF-IDF, embeddingi, podejścia sekwencyjne DeepLog i LogBERT oraz Precision, Recall i F1.

## 2. Przegląd podejść

### TF-IDF i klasyfikator

TF-IDF reprezentuje tekst za pomocą wag terminów uwzględniających ich występowanie w tekście i w całym zbiorze. W scikit-learn można użyć `TfidfVectorizer`. Jest to metoda NLP, a nie odrębna od NLP kategoria rozwiązania. Sama reprezentacja nie podejmuje decyzji o anomalii. [Źródło: scikit-learn — ekstrakcja cech](https://scikit-learn.org/stable/modules/feature_extraction.html#tfidf-term-weighting).

Proponowany baseline projektu: TF-IDF oraz prosty klasyfikator, np. regresja logistyczna. Wariant nadzorowany wymaga etykiet odpowiadających przyjętej jednostce analizy.

### Embeddingi i klasyfikator

Kandydatem jest `sentence-transformers/all-MiniLM-L6-v2`, który tworzy 384-wymiarowe wektory krótkich tekstów. Model jest oznaczony jako anglojęzyczny; domyślnie tekst przekraczający 256 tokenów typu word pieces jest obcinany. [Źródło: karta modelu](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).

Wniosek projektowy: nie należy bez sprawdzenia sklejać całych długich sesji w jedno wejście. Sposób agregacji embeddingów zdarzeń oraz cechy liczebności i czasu pozostają do ustalenia. Pierwsze porównanie może użyć tego samego klasyfikatora dla TF-IDF i embeddingów. Nie zakładamy z góry wyższego F1 dla embeddingów.

### DeepLog i LogBERT

DeepLog wykorzystuje LSTM do modelowania sekwencji identyfikatorów typów zdarzeń i przewidywania kolejnego zdarzenia. Nietypowa kontynuacja sekwencji może stanowić sygnał anomalii. [Źródło: Du i in., DeepLog, 2017](https://www.cs.utah.edu/~lifeifei/papers/deeplog.pdf).

LogBERT jest podejściem samonadzorowanym opartym na BERT, uczącym wzorce normalnych sekwencji logów. Nie jest po prostu zamiennikiem modelu Sentence-Transformers w identycznym pipeline. [Źródło: Guo i in., LogBERT, 2021](https://arxiv.org/abs/2103.04475).

Obie metody są elementem przeglądu literatury. Ich implementacja nie jest zobowiązaniem MVP. Początkowy plan obejmuje baseline i wariant embeddingowy.

## 3. Zbiory danych i etykiety

Loghub oznacza HDFS_v1, BGL i Thunderbird jako zbiory z etykietami. Linux i OpenSSH nie mają takiego oznaczenia. Dostępność przykładowych szablonów parsera nie jest równoznaczna z etykietami anomalii. [Źródło: zestawienie Loghub](https://github.com/logpai/loghub).

| Zbiór | Znaczenie etykiet i konsekwencja |
|---|---|
| HDFS_v1 | Etykieta dotyczy śladu grupowanego po BlockID. Jednostką analizy powinna być odpowiednio przygotowana sekwencja. |
| BGL | Pierwsze pole wpisu rozróżnia komunikaty bez alertu (`-`) i kategorie alertów. Można rozważyć detekcję na poziomie wpisu. |
| Thunderbird | Kandydat do dalszych badań; duży rozmiar przemawia przeciw rozpoczynaniu od całego zbioru. |

Szczegóły etykiet: [opis HDFS](https://github.com/logpai/loghub/blob/master/HDFS/README.md), [opis BGL](https://github.com/logpai/loghub/blob/master/BGL/README.md).

Wniosek projektowy: benchmark na HDFS lub BGL nie dowodzi skuteczności wykrywania ataków SSH. Jeśli demonstracja pozostaje oparta na SSH, trzeba uzgodnić osobne oznaczone dane lub kontrolowane scenariusze laboratoryjne. Ostatecznego zestawu treningowego nie potwierdzono przez pobranie i analizę plików.

## 4. Plan przygotowania danych

1. Ustalić z JB format wejścia, jednostkę analizy i znaczenie etykiet.
2. Przygotować odtwarzalny skrypt wczytywania i przetwarzania danych.
3. Wydzielić trening, walidację i test, uwzględniając powiązane sesje lub grupy.
4. Dopasować TF-IDF i inne uczone przekształcenia tylko na treningu. Nie używać testu do wyboru parametrów. Dokumentacja scikit-learn wskazuje takie rozdzielenie jako sposób ograniczenia wycieku danych. [Źródło: Common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html).
5. Dobierać konfigurację i próg na walidacji, a test zachować do końcowej oceny.

Nie określono jeszcze proporcji podziału. Muszą uwzględniać liczbę anomalii i strukturę wybranego zbioru.

## 5. Metryki i plan porównania

Klasą pozytywną w ocenie będzie anomalia.

| Miara | Interpretacja |
|---|---|
| Precision | Jaka część zgłoszonych anomalii jest rzeczywiście anomalna |
| Recall | Jaką część rzeczywistych anomalii wykryto |
| F1 | Średnia harmoniczna Precision i Recall |

Planowane jest użycie `classification_report`, który podaje te miary i liczebność dla każdej klasy, oraz macierzy pomyłek. Przy zerowych mianownikach trzeba jawnie ustalić sposób raportowania. [Źródło: scikit-learn — classification_report](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.classification_report.html).

Oprócz metryk należy zapisać zbiór, podział, konfigurację, próg, losowe ziarno i czas predykcji. Wyniki różnych modeli będą porównywane na tych samych przykładach i przy tej samej definicji anomalii. Wyników z publikacji nie traktujemy jako wyników własnych ani gwarancji skuteczności na nowych danych.

## 6. Rezultat i weryfikacja

Powstała koncepcja porównania baseline’u z wariantem embeddingowym oraz plan przygotowania i oceny danych. Przegląd źródeł pozwolił rozróżnić metody i poziomy etykietowania. Ujawniono nierozstrzygniętą zależność między danymi benchmarkowymi a demonstracją SSH.

Nie przygotowano jeszcze działającego pipeline’u, nie wytrenowano modelu i nie obliczono własnych Precision, Recall ani F1. Weryfikacja praktyczna nastąpi po wyborze danych i implementacji baseline’u. Wtedy materiałami będą również skrypt, zapisany model i wektoryzator, predykcje, tabela metryk oraz macierz pomyłek.

Materiały potwierdzające obecny etap: niniejsza notatka i wskazane publikacje oraz dokumentacja.
