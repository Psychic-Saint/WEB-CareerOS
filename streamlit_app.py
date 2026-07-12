# streamlit_app.py
# Entry-point for Streamlit Community Cloud.
# Streamlit Cloud looks for this file in the repo root by default.
# It simply imports and runs the real dashboard.

from app.review_app import *   # noqa: F401, F403
