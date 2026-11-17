"""Strumieniowe wejście UTF-8. Przechowuje wyłącznie ograniczoną listę wpisów."""

import codecs
import io

from log_analyzer.contracts import MAX_LOG_LINE_CHARS, MAX_LOG_LINES


MAX_FILE_BYTES = 2 * 1024**3
READ_CHUNK_BYTES = 64 * 1024


class LogImportError(ValueError):
    status_code = 422


class FileTooLarge(LogImportError):
    status_code = 413


class LogFileReader:
    def __init__(self):
        self.bytes_received = 0
        self.lines = []
        self._line = ""
        self._physical_line = 1
        self._decoder = io.IncrementalNewlineDecoder(
            codecs.getincrementaldecoder("utf-8-sig")("strict"), translate=True,
        )

    @staticmethod
    def check_size(size: int) -> None:
        if size > MAX_FILE_BYTES:
            raise FileTooLarge("Plik może mieć maksymalnie 2 GB (2048 MiB).")

    def feed(self, chunk: bytes) -> None:
        self.bytes_received += len(chunk)
        self.check_size(self.bytes_received)
        # Także nietypowo duży fragment ASGI dekodujemy w małych częściach.
        for offset in range(0, len(chunk), READ_CHUNK_BYTES):
            self._decode(chunk[offset:offset + READ_CHUNK_BYTES])

    def _decode(self, chunk: bytes, *, final=False) -> None:
        try:
            text = self._decoder.decode(chunk, final=final)
        except UnicodeDecodeError as error:
            raise LogImportError("Nie można odczytać pliku. Zapisz go w kodowaniu UTF-8.") from error
        parts = text.split("\n")
        for index, part in enumerate(parts):
            # Same puste wiersze i początkowe białe znaki nie powiększają bufora.
            if not self._line:
                part = part.lstrip()
            self._line += part
            if len(self._line) > MAX_LOG_LINE_CHARS:
                raise LogImportError(f"Wiersz pliku {self._physical_line}: pojedynczy wpis może mieć maksymalnie 10 000 znaków.")
            if index < len(parts) - 1:
                self._finish_line()
                self._physical_line += 1

    def _finish_line(self) -> None:
        line = self._line.strip()
        self._line = ""
        if line:
            if len(self.lines) >= MAX_LOG_LINES:
                raise LogImportError(f"Jedna paczka może zawierać maksymalnie {MAX_LOG_LINES} niepustych wpisów. Podziel plik na mniejsze paczki.")
            self.lines.append(line)

    def finish(self) -> list[str]:
        self._decode(b"", final=True)
        self._finish_line()
        if not self.lines:
            raise LogImportError("Plik nie zawiera niepustych wpisów.")
        return self.lines
