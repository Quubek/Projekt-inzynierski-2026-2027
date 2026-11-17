"""Statyczny komunikat operacji bez animacji ładowania."""

from contextlib import contextmanager

import streamlit as st


@contextmanager
def working_message(message: str):
    placeholder = st.empty()
    placeholder.info(message)
    try:
        yield
    finally:
        placeholder.empty()
