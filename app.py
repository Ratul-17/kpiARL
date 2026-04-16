"""
AKIJ Resource — Production Planning KPI Dashboard
Streamlit App | app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import gspread
from google.oauth2.service_account import Credentials
import json
import re
from datetime import datetime, date

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AKIJ Resource — KPI Dashboard",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
SHEET_ID = "1mv4TUi-JPD2AZBKssDoPmGgzUzGIIbTIKRAz0wjqOFY"

SBU_CONFIG = {
    "AIL":         {"full_name": "Akij Ispat Ltd.",                              "sheet": "AIL"},
    "AAFL":        {"full_name": "Akij Agro Feed Ltd.",                          "sheet": "AAFL"},
    "ACCL":        {"full_name": "Akij Cement Company Ltd.",                     "sheet": "ACCL"},
    "AEL (Flour)": {"full_name": "Akij Essential Flour Mill",                   "sheet": "AEL (Flour)"},
    "AEL (Rice)":  {"full_name": "Akij Essential Rice Mill",                    "sheet": "AEL (Rice)"},
    "APFIL":       {"full_name": "Akij Poly Fibre Industries Ltd.",              "sheet": "APFIL"},
    "ABSL":        {"full_name": "Akij Building Solutions Ltd.",                 "sheet": "ABSL"},
    "ARMCL-01":    {"full_name": "Akij Ready Mix Concrete Ltd. - Narayanganj",  "sheet": "ARMCL - 01"},
}

CRITERIA_COLORS = {
    "Machine Utilization & Execution": "#4F8FFF",
    "Idle Capacity Cost (BDT)":        "#B370FF",
    "Downtime & Reliability":          "#FF6B6B",
    "Planning Accuracy & Efficiency":  "#00E5B8",
    "Process & Culture":               "#FFB347",
}

# KPIs where LOWER value = BETTER performance
LOWER_IS_BETTER = [
    "Reduce Downtime (%)",
    "Downtime Cost (BDT)",
    "Breakdown Hours/Month",
    "Idle Hours × Fixed Cost per Hour",
    "Production Loss due to Planning Error (%)",
    "Idle Time due to Material Shortage (%)",
    "Changeover Time Reduction (%)",
]

# KPIs that are purely monetary (show as BDT, no × 100)
BDT_KPIS = [
    "Downtime Cost (BDT)",
    "Idle Hours × Fixed Cost per Hour",
]

# KPIs that are raw hours
HOURS_KPIS = ["Breakdown Hours/Month"]


# ─────────────────────────────────────────────────────────────
# STYLING
# ─────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

    /* Main background */
    .stApp { background: #0d0f14; }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #13161f !important;
        border-right: 1px solid #ffffff0f;
    }
    section[data-testid="stSidebar"] * { color: #f0f2f8 !important; }
    section[data-testid="stSidebar"] .stSelectbox > div > div {
        background: #1c2030; border: 1px solid #ffffff1a; color: #f0f2f8;
    }

    /* Hide default header */
    header[data-testid="stHeader"] { background: transparent; }

    /* Top bar */
    .top-bar {
        background: linear-gradient(135deg, #13161f 0%, #1a1f2e 100%);
        border: 1px solid #ffffff0f;
        border-radius: 16px;
        padding: 20px 28px;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .brand-logo {
        width: 44px; height: 44px;
        background: linear-gradient(135deg, #4F8FFF, #00E5B8);
        border-radius: 12px;
        display: flex; align-items: center; justify-content: center;
        font-family: 'Syne', sans-serif; font-weight: 800;
        color: white; font-size: 15px;
        box-shadow: 0 0 20px #4F8FFF33;
        float: left; margin-right: 14px;
    }
    .brand-text .brand-title {
        font-family: 'Syne', sans-serif; font-weight: 700;
        font-size: 18px; color: #f0f2f8; line-height: 1.2;
    }
    .brand-text .brand-sub {
        font-size: 11px; color: #4e5870;
        text-transform: uppercase; letter-spacing: 0.8px;
    }
    .sbu-hero { text-align: right; }
    .sbu-hero-name {
        font-family: 'Syne', sans-serif; font-weight: 800; font-size: 28px;
        background: linear-gradient(90deg, #4F8FFF, #00E5B8);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .sbu-hero-full { font-size: 12px; color: #4e5870; margin-top: 2px; }

    /* KPI Cards */
    .kpi-card {
        background: #13161f;
        border: 1px solid #ffffff0f;
        border-radius: 14px;
        padding: 18px 18px 14px;
        border-top: 3px solid;
        height: 140px;
        transition: all 0.2s;
    }
    .kpi-card:hover { border-color: #ffffff1a; transform: translateY(-2px); }
    .kpi-card-criteria {
        font-size: 10px; color: #4e5870;
        text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 6px;
    }
    .kpi-card-value {
        font-family: 'Syne', sans-serif; font-weight: 700;
        font-size: 26px; line-height: 1; margin-bottom: 6px;
    }
    .kpi-card-name { font-size: 11.5px; color: #8892ab; margin-bottom: 8px; line-height: 1.3; }
    .kpi-badge {
        display: inline-block;
        padding: 2px 10px; border-radius: 99px;
        font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px;
    }
    .badge-good { background: #22d3a520; color: #22d3a5; }
    .badge-warn { background: #f59e0b20; color: #f59e0b; }
    .badge-bad  { background: #ef444420; color: #ef4444; }
    .badge-na   { background: #ffffff12; color: #4e5870; }

    /* Section titles */
    .section-title {
        font-family: 'Syne', sans-serif; font-size: 12px; font-weight: 600;
        text-transform: uppercase; letter-spacing: 1px; color: #4e5870;
        margin: 24px 0 12px 0;
    }

    /* Metric override */
    [data-testid="stMetric"] {
        background: #13161f; border: 1px solid #ffffff0f;
        border-radius: 12px; padding: 14px;
    }
    [data-testid="stMetricValue"] { font-family: 'Syne', sans-serif !important; }
    [data-testid="stMetricLabel"] { font-size: 11px !important; color: #4e5870 !important; }

    /* Chart containers */
    .chart-container {
        background: #13161f; border: 1px solid #ffffff0f;
        border-radius: 14px; padding: 20px; margin-bottom: 16px;
    }
    .chart-title {
        font-family: 'Syne', sans-serif; font-size: 13px; font-weight: 600;
        color: #8892ab; margin-bottom: 14px;
    }

    /* Table */
    .kpi-table-wrap { overflow-x: auto; }
    table.kpi-table {
        width: 100%; border-collapse: collapse; font-size: 12.5px;
    }
    table.kpi-table th {
        background: #1c2030; color: #4e5870;
        padding: 10px 14px; text-align: left;
        font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.5px;
        border-bottom: 1px solid #ffffff0f;
    }
    table.kpi-table td {
        padding: 10px 14px; border-bottom: 1px solid #ffffff0a;
        color: #8892ab;
    }
    table.kpi-table td:nth-child(2) { color: #f0f2f8; font-weight: 500; }
    table.kpi-table tr:hover td { background: #1a1f2e; }

    /* Divider */
    hr { border-color: #ffffff0f !important; }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #ffffff1a; border-radius: 99px; }

    /* Plotly chart background override */
    .js-plotly-plot .plotly { background: transparent !important; }

    /* Status dot */
    .status-dot {
        width: 8px; height: 8px; border-radius: 50%;
        display: inline-block; margin-right: 6px;
    }
    </style>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_sheet_data(sheet_id: str, sheet_name: str) -> pd.DataFrame:
    """
    Load data from Google Sheets via gspread (service account)
    or fallback to CSV export URL (public sheet).
    Returns raw dataframe with header=None.
    """
    try:
        creds_json = st.secrets.get("gcp_service_account", None)
        if creds_json:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_info(creds_json, scopes=scope)
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(sheet_id)
            ws = sh.worksheet(sheet_name)
            data = ws.get_all_values()
            df = pd.DataFrame(data)
            return df
    except Exception as e:
        pass  # Fall through to CSV method

    # Fallback: public CSV export
    try:
        url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}"
            f"/gviz/tq?tqx=out:csv&sheet={sheet_name.replace(' ', '%20')}"
        )
        df = pd.read_csv(url, header=None)
        return df
    except Exception as e:
        st.error(f"⚠️ Could not load sheet '{sheet_name}': {e}")
        return pd.DataFrame()


def parse_kpi_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse raw sheet dataframe into structured KPI dataframe.
    Columns: criteria, kpi_name, formula, baseline, target, actual, + date columns
    Row 0 = header. Actual = col 5. Dates start at col 6.
    Values are stored AS-IS (decimals). Formatting done at display time.
    """
    if raw_df.empty or len(raw_df) < 2:
        return pd.DataFrame()

    header_row = raw_df.iloc[0]
    records = []

    # Collect date columns (col 6 onwards)
    date_cols = {}
    for c in range(6, len(raw_df.columns)):
        raw_label = str(header_row.iloc[c]) if c < len(header_row) else ""
        parsed_date = try_parse_date(raw_label)
        if parsed_date:
            date_cols[c] = parsed_date

    for r in range(1, len(raw_df)):
        row = raw_df.iloc[r]
        kpi_name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        if not kpi_name or kpi_name.lower() == "kpi":
            continue

        criteria = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        formula  = str(row.iloc[2]).strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ""
        baseline = safe_float(row.iloc[3] if len(row) > 3 else None)
        target   = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else ""
        actual   = safe_float(row.iloc[5] if len(row) > 5 else None)

        daily = {}
        for c, dt in date_cols.items():
            v = safe_float(row.iloc[c] if c < len(row) else None)
            if v is not None:
                daily[dt] = v

        records.append({
            "criteria":  criteria,
            "kpi_name":  kpi_name,
            "formula":   formula,
            "baseline":  baseline,
            "target":    target,
            "actual":    actual,      # RAW decimal as in sheet
            "daily":     daily,
        })

    return pd.DataFrame(records)


def safe_float(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in ("nan", "NaT", "None", "#REF!", "#DIV/0!", "#VALUE!", "#N/A", "#NAME?"):
        return None
    # Remove % if present
    s = s.replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def try_parse_date(s: str):
    """Try multiple date formats. Return date object or None."""
    if not s or s in ("nan", "None", ""):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
                "%m-%d-%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt[:len(fmt)]).date()
        except:
            pass
    # Try pandas
    try:
        return pd.to_datetime(s).date()
    except:
        return None


# ─────────────────────────────────────────────────────────────
# VALUE FORMATTING
# ─────────────────────────────────────────────────────────────
def fmt_value(kpi_name: str, val: float | None) -> str:
    """Format a raw sheet value for display."""
    if val is None:
        return "—"

    name = kpi_name.lower()

    # BDT monetary
    if any(k.lower() in name for k in ["cost (bdt)", "idle hours × fixed"]):
        if abs(val) >= 1_000_000:
            return f"৳{val/1_000_000:.2f}M"
        if abs(val) >= 1_000:
            return f"৳{val/1_000:.1f}K"
        return f"৳{val:,.0f}"

    # Hours
    if "hours/month" in name:
        return f"{val:.1f} hrs"

    # Percentage KPIs — values are stored as decimals (0.87 = 87%)
    # Detect: if absolute value ≤ 2 treat as decimal ratio → multiply by 100
    if abs(val) <= 2.0:
        return f"{val * 100:.1f}%"

    # Values > 2 are already in raw units (hours, BDT) — shouldn't reach here
    return f"{val:.2f}"


def score_kpi(kpi_name: str, actual: float | None) -> float | None:
    """
    Return a 0–1 performance score.
    Handles lower-is-better vs higher-is-better.
    """
    if actual is None:
        return None
    name = kpi_name
    is_lower_better = any(k.lower() in name.lower() for k in LOWER_IS_BETTER)

    # For percentage KPIs stored as decimals (≤2), clamp to [0,1]
    if is_lower_better:
        # Score = 1 when value is 0, score = 0 when value >= 1 (100%)
        clamped = max(0.0, min(1.0, abs(actual)))
        return 1.0 - clamped
    else:
        clamped = max(0.0, min(1.5, abs(actual)))
        return min(1.0, clamped)


def status_from_score(score: float | None):
    if score is None:
        return "na", "N/A", "#4e5870", "badge-na"
    if score >= 0.75:
        return "good", "On Track", "#22d3a5", "badge-good"
    if score >= 0.45:
        return "warn", "At Risk", "#f59e0b", "badge-warn"
    return "bad", "Critical", "#ef4444", "badge-bad"


# ─────────────────────────────────────────────────────────────
# PLOTLY CHART THEME
# ─────────────────────────────────────────────────────────────
PLOT_BG    = "#13161f"
PAPER_BG   = "#13161f"
GRID_COLOR = "rgba(255,255,255,0.06)"
TICK_COLOR = "#8892ab"
FONT_FMLY  = "DM Sans, sans-serif"

def base_layout(title="", height=320):
    return dict(
        title=dict(text=title, font=dict(size=13, color="#8892ab", family=FONT_FMLY)),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(family=FONT_FMLY, color=TICK_COLOR, size=11),
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        xaxis=dict(gridcolor=GRID_COLOR, color=TICK_COLOR, showline=False),
        yaxis=dict(gridcolor=GRID_COLOR, color=TICK_COLOR, showline=False),
    )


# ─────────────────────────────────────────────────────────────
# CHARTS
# ─────────────────────────────────────────────────────────────
def chart_trend(df: pd.DataFrame, selected_kpi: str, date_from, date_to) -> go.Figure:
    row = df[df["kpi_name"] == selected_kpi]
    if row.empty:
        return go.Figure()
    row = row.iloc[0]

    daily = {k: v for k, v in row["daily"].items()
             if date_from <= k <= date_to}
    if not daily:
        return go.Figure()

    dates = sorted(daily.keys())
    vals  = [daily[d] for d in dates]
    display_vals = [v * 100 if v is not None and abs(v) <= 2 else v for v in vals]
    unit = "%" if vals and abs(vals[0]) <= 2 else ""

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=display_vals,
        mode="lines+markers",
        name=selected_kpi,
        line=dict(color="#4F8FFF", width=2.5),
        marker=dict(size=5, color="#4F8FFF"),
        fill="tozeroy",
        fillcolor="rgba(79,143,255,0.10)",
        hovertemplate=f"%{{x}}: %{{y:.2f}}{unit}<extra></extra>",
    ))

    # Baseline reference line
    if row["baseline"] is not None:
        bv = row["baseline"] * 100 if abs(row["baseline"]) <= 2 else row["baseline"]
        fig.add_hline(
            y=bv, line_dash="dot", line_color="#FF6B6B", line_width=1.5,
            annotation_text=f"Baseline {bv:.1f}{unit}",
            annotation_font=dict(color="#FF6B6B", size=10),
        )

    layout = base_layout(selected_kpi, height=300)
    layout["yaxis"]["ticksuffix"] = unit
    fig.update_layout(**layout)
    return fig


def chart_radar(df: pd.DataFrame) -> go.Figure:
    groups = df.groupby("criteria").apply(
        lambda g: np.nanmean([
            s * 100 for s in g["actual"].apply(
                lambda a: score_kpi(g.iloc[0]["kpi_name"], a)
            ) if s is not None
        ]) if len(g) else 0
    ).reset_index()
    groups.columns = ["criteria", "score"]

    labels = [c.split(" & ")[0][:20] for c in groups["criteria"]]
    scores = groups["score"].fillna(0).tolist()
    labels.append(labels[0])
    scores.append(scores[0])

    fig = go.Figure(go.Scatterpolar(
        r=scores, theta=labels,
        fill="toself",
        fillcolor="rgba(79,143,255,0.18)",
        line=dict(color="#4F8FFF", width=2),
        marker=dict(color="#4F8FFF", size=5),
    ))
    fig.update_layout(
        polar=dict(
            bgcolor=PLOT_BG,
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=GRID_COLOR,
                           tickcolor=TICK_COLOR, tickfont=dict(size=9, color=TICK_COLOR),
                           ticksuffix="%"),
            angularaxis=dict(color=TICK_COLOR, gridcolor=GRID_COLOR,
                            tickfont=dict(size=10, color=TICK_COLOR)),
        ),
        paper_bgcolor=PAPER_BG,
        font=dict(family=FONT_FMLY, color=TICK_COLOR),
        height=320,
        margin=dict(l=20, r=20, t=30, b=20),
        showlegend=False,
    )
    return fig


def chart_bar_baseline_actual(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar: Baseline vs Actual for all KPIs with numeric data."""
    valid = df[df["actual"].notna() & df["baseline"].notna()].copy()
    if valid.empty:
        valid = df[df["actual"].notna()].copy()

    # Convert to display %
    def to_pct(row, col):
        v = row[col]
        if v is None or pd.isna(v):
            return None
        if any(k.lower() in row["kpi_name"].lower() for k in BDT_KPIS + HOURS_KPIS):
            return v
        return v * 100 if abs(v) <= 2 else v

    valid["actual_disp"]   = valid.apply(lambda r: to_pct(r, "actual"), axis=1)
    valid["baseline_disp"] = valid.apply(lambda r: to_pct(r, "baseline"), axis=1)

    labels = [k[:38] for k in valid["kpi_name"]]

    fig = go.Figure()
    if "baseline_disp" in valid and valid["baseline_disp"].notna().any():
        fig.add_trace(go.Bar(
            y=labels, x=valid["baseline_disp"],
            name="Baseline", orientation="h",
            marker_color="rgba(79,143,255,0.45)",
            marker_line=dict(color="#4F8FFF", width=1),
        ))
    fig.add_trace(go.Bar(
        y=labels, x=valid["actual_disp"],
        name="Actual", orientation="h",
        marker_color="rgba(0,229,184,0.45)",
        marker_line=dict(color="#00E5B8", width=1),
    ))

    layout = base_layout("Baseline vs Actual", height=max(320, len(valid) * 28))
    layout["barmode"] = "group"
    layout["xaxis"]["title"] = "Value"
    layout.pop("xaxis", None)
    fig.update_layout(
        barmode="group",
        paper_bgcolor=PAPER_BG, plot_bgcolor=PLOT_BG,
        font=dict(family=FONT_FMLY, color=TICK_COLOR, size=11),
        height=max(320, len(valid) * 30),
        margin=dict(l=10, r=20, t=40, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor=GRID_COLOR, color=TICK_COLOR),
        yaxis=dict(gridcolor=GRID_COLOR, color=TICK_COLOR, automargin=True,
                   tickfont=dict(size=10)),
    )
    return fig


def chart_heatmap(df: pd.DataFrame, selected_kpi: str, date_from, date_to) -> go.Figure:
    row = df[df["kpi_name"] == selected_kpi]
    if row.empty:
        return go.Figure()
    row = row.iloc[0]

    daily = {k: v for k, v in row["daily"].items()
             if date_from <= k <= date_to}
    if not daily:
        return go.Figure()

    dates = sorted(daily.keys())
    vals  = [daily[d] for d in dates]
    disp_vals = [v * 100 if v is not None and abs(v) <= 2 else v for v in vals]
    unit = "%" if vals and abs(vals[0]) <= 2 else ""

    fig = go.Figure(go.Heatmap(
        x=[str(d) for d in dates],
        y=[selected_kpi[:30]],
        z=[disp_vals],
        colorscale=[[0, "#ef4444"], [0.5, "#f59e0b"], [1, "#22d3a5"]],
        hoverongaps=False,
        hovertemplate="%{x}: %{z:.2f}" + unit + "<extra></extra>",
        showscale=True,
        colorbar=dict(
            tickfont=dict(color=TICK_COLOR, size=10),
            outlinewidth=0, bgcolor=PAPER_BG,
        ),
    ))
    fig.update_layout(
        paper_bgcolor=PAPER_BG, plot_bgcolor=PLOT_BG,
        font=dict(family=FONT_FMLY, color=TICK_COLOR, size=11),
        height=130,
        margin=dict(l=10, r=10, t=10, b=50),
        xaxis=dict(color=TICK_COLOR, tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(color=TICK_COLOR, tickfont=dict(size=9)),
    )
    return fig


def chart_donut(df: pd.DataFrame) -> go.Figure:
    groups = {}
    for _, row in df.iterrows():
        c = row["criteria"]
        s = score_kpi(row["kpi_name"], row["actual"])
        if s is not None:
            groups.setdefault(c, []).append(s * 100)

    labels = list(groups.keys())
    values = [np.mean(v) for v in groups.values()]
    colors = [CRITERIA_COLORS.get(l, "#8892ab") for l in labels]

    fig = go.Figure(go.Pie(
        labels=[l.split(" & ")[0] for l in labels],
        values=values,
        hole=0.65,
        marker=dict(colors=[c + "aa" for c in colors],
                    line=dict(color=colors, width=2)),
        textfont=dict(size=11, color="#f0f2f8"),
        hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=PAPER_BG,
        font=dict(family=FONT_FMLY, color=TICK_COLOR, size=11),
        height=280,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10, color=TICK_COLOR),
                    orientation="v"),
        annotations=[dict(
            text="Score", x=0.5, y=0.5, font_size=13,
            font=dict(color="#8892ab"), showarrow=False
        )],
        showlegend=True,
    )
    return fig


# ─────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────
def main():
    inject_css()

    # ── SIDEBAR ──────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🏭 AKIJ Resource")
        st.markdown("---")

        # SBU Selector
        st.markdown("**Select SBU**")
        sbu_key = st.selectbox(
            "SBU",
            options=list(SBU_CONFIG.keys()),
            format_func=lambda k: f"{k} — {SBU_CONFIG[k]['full_name'][:28]}",
            label_visibility="collapsed",
        )

        st.markdown("---")
        st.markdown("**Date Range**")

        # Get available dates for selected SBU to set defaults
        sbu_info    = SBU_CONFIG[sbu_key]
        sheet_name  = sbu_info["sheet"]

        with st.spinner("Loading…"):
            raw_df = load_sheet_data(SHEET_ID, sheet_name)
        kpi_df = parse_kpi_df(raw_df)

        all_dates = sorted(set(
            d for row in kpi_df.itertuples()
            for d in row.daily.keys()
        )) if not kpi_df.empty else []

        min_date = all_dates[0]  if all_dates else date(2026, 4, 1)
        max_date = all_dates[-1] if all_dates else date(2026, 4, 30)

        date_from = st.date_input("From", value=min_date, min_value=min_date, max_value=max_date)
        date_to   = st.date_input("To",   value=max_date, min_value=min_date, max_value=max_date)

        st.markdown("---")
        st.markdown("**Filter by Category**")
        all_criteria = ["All"] + sorted(kpi_df["criteria"].unique().tolist()) if not kpi_df.empty else ["All"]
        cat_filter = st.selectbox("Category", all_criteria, label_visibility="collapsed")

        st.markdown("---")
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.markdown(
            '<p style="font-size:10px;color:#4e5870;text-align:center">'
            'AKIJ Resource Production Planning<br>KPI Intelligence Dashboard<br>'
            'Data pulled live from Google Sheets</p>',
            unsafe_allow_html=True,
        )

    # ── HEADER BAR ───────────────────────────────────────────
    st.markdown(f"""
    <div class="top-bar">
      <div style="display:flex;align-items:center">
        <div class="brand-logo">AR</div>
        <div class="brand-text">
          <div class="brand-title">AKIJ Resource</div>
          <div class="brand-sub">Production Planning KPI Intelligence</div>
        </div>
      </div>
      <div class="sbu-hero">
        <div class="sbu-hero-name">{sbu_key}</div>
        <div class="sbu-hero-full">{sbu_info['full_name']}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if kpi_df.empty:
        st.warning("⚠️ No data loaded. Check your Google Sheet connection and sheet name.")
        st.info("If the sheet is not public, configure a service account in `.streamlit/secrets.toml`.")
        return

    # ── APPLY FILTERS ────────────────────────────────────────
    display_df = kpi_df.copy()
    if cat_filter != "All":
        display_df = display_df[display_df["criteria"] == cat_filter]

    # Filter daily data by date range
    display_df = display_df.copy()
    display_df["daily"] = display_df["daily"].apply(
        lambda d: {k: v for k, v in d.items() if date_from <= k <= date_to}
    )

    # ── SUMMARY METRICS ──────────────────────────────────────
    valid_actuals = [r for r in display_df.itertuples() if r.actual is not None]
    scores_all = [score_kpi(r.kpi_name, r.actual) for r in valid_actuals]
    scores_clean = [s for s in scores_all if s is not None]

    avg_score  = np.mean(scores_clean) * 100 if scores_clean else 0
    on_track   = sum(1 for s in scores_clean if s >= 0.75)
    at_risk    = sum(1 for s in scores_clean if 0.45 <= s < 0.75)
    critical   = sum(1 for s in scores_clean if s < 0.45)
    total_kpis = len(display_df)

    date_label = f"{date_from.strftime('%d %b %Y')} → {date_to.strftime('%d %b %Y')}"
    st.markdown(f'<p style="font-size:12px;color:#4e5870;margin-bottom:12px">📅 {date_label} &nbsp;|&nbsp; {total_kpis} KPIs tracked</p>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Overall Score", f"{avg_score:.1f}%")
    with c2:
        st.metric("KPIs Tracked", str(total_kpis))
    with c3:
        st.metric("✅ On Track", str(on_track))
    with c4:
        st.metric("⚠️ At Risk", str(at_risk))
    with c5:
        st.metric("🔴 Critical", str(critical))

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── KPI SCORE CARDS ──────────────────────────────────────
    st.markdown('<div class="section-title">KPI Scorecard</div>', unsafe_allow_html=True)

    cards_per_row = 4
    rows = [display_df.iloc[i:i+cards_per_row] for i in range(0, len(display_df), cards_per_row)]

    for row_df in rows:
        cols = st.columns(len(row_df))
        for col, (_, kpi_row) in zip(cols, row_df.iterrows()):
            score = score_kpi(kpi_row["kpi_name"], kpi_row["actual"])
            status, status_label, color, badge_class = status_from_score(score)
            display_val = fmt_value(kpi_row["kpi_name"], kpi_row["actual"])
            crit_color  = CRITERIA_COLORS.get(kpi_row["criteria"], "#4e5870")

            with col:
                st.markdown(f"""
                <div class="kpi-card" style="border-top-color:{color}">
                  <div class="kpi-card-criteria">{kpi_row['criteria'][:25]}</div>
                  <div class="kpi-card-value" style="color:{color}">{display_val}</div>
                  <div class="kpi-card-name">{kpi_row['kpi_name']}</div>
                  <span class="kpi-badge {badge_class}">{status_label}</span>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── TREND + RADAR ─────────────────────────────────────────
    st.markdown('<div class="section-title">Trend Analysis & Category Performance</div>', unsafe_allow_html=True)
    col_trend, col_radar = st.columns([3, 2])

    with col_trend:
        numeric_kpis = [r["kpi_name"] for _, r in display_df.iterrows()
                        if r["daily"] and any(v is not None for v in r["daily"].values())]
        if numeric_kpis:
            sel_kpi = st.selectbox("Select KPI for trend", numeric_kpis, key="trend_sel",
                                   label_visibility="collapsed")
            fig_trend = chart_trend(display_df, sel_kpi, date_from, date_to)
            st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No daily data available for the selected range.")

    with col_radar:
        fig_radar = chart_radar(display_df)
        st.plotly_chart(fig_radar, use_container_width=True, config={"displayModeBar": False})

    # ── BAR CHART + DONUT ─────────────────────────────────────
    st.markdown('<div class="section-title">Baseline vs Actual Comparison & Category Distribution</div>', unsafe_allow_html=True)
    col_bar, col_donut = st.columns([3, 2])

    with col_bar:
        fig_bar = chart_bar_baseline_actual(display_df)
        st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

    with col_donut:
        fig_donut = chart_donut(display_df)
        st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})

    # ── HEATMAP ───────────────────────────────────────────────
    st.markdown('<div class="section-title">Daily Performance Heatmap</div>', unsafe_allow_html=True)
    if numeric_kpis:
        sel_heat = st.selectbox("Select KPI for heatmap", numeric_kpis, key="heat_sel",
                                label_visibility="collapsed")
        fig_heat = chart_heatmap(display_df, sel_heat, date_from, date_to)
        st.plotly_chart(fig_heat, use_container_width=True, config={"displayModeBar": False})

    # ── KPI DETAIL TABLE ─────────────────────────────────────
    st.markdown('<div class="section-title">KPI Detail Table</div>', unsafe_allow_html=True)

    table_rows = ""
    for _, kpi_row in display_df.iterrows():
        score = score_kpi(kpi_row["kpi_name"], kpi_row["actual"])
        _, status_label, color, badge_class = status_from_score(score)
        display_val  = fmt_value(kpi_row["kpi_name"], kpi_row["actual"])
        baseline_val = fmt_value(kpi_row["kpi_name"], kpi_row["baseline"])
        crit = kpi_row["criteria"]
        crit_color = CRITERIA_COLORS.get(crit, "#4e5870")

        table_rows += f"""
        <tr>
          <td><span style="color:{crit_color};font-size:10px">{crit}</span></td>
          <td>{kpi_row['kpi_name']}</td>
          <td>{baseline_val}</td>
          <td>{kpi_row['target']}</td>
          <td style="color:{color};font-weight:600">{display_val}</td>
          <td><span class="kpi-badge {badge_class}">{status_label}</span></td>
        </tr>"""

    st.markdown(f"""
    <div class="kpi-table-wrap">
    <table class="kpi-table">
      <thead><tr>
        <th>Criteria</th><th>KPI</th><th>Baseline</th>
        <th>Target</th><th>Actual</th><th>Status</th>
      </tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
    </div>
    """, unsafe_allow_html=True)

    # ── FOOTER ───────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<p style="text-align:center;font-size:11px;color:#4e5870">'
        'AKIJ Resource Production Planning KPI Intelligence &nbsp;|&nbsp; '
        'Data Source: Google Sheets (Live) &nbsp;|&nbsp; '
        'Built for Operations Planning</p>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
