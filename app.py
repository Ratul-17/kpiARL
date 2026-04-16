"""
AKIJ Resource — Production Planning KPI Dashboard
Streamlit App | app.py  (v3 — all formatting fixes applied)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
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
    "AIL":         {"full_name": "Akij Ispat Ltd.",                             "sheet": "AIL"},
    "AAFL":        {"full_name": "Akij Agro Feed Ltd.",                         "sheet": "AAFL"},
    "ACCL":        {"full_name": "Akij Cement Company Ltd.",                    "sheet": "ACCL"},
    "AEL (Flour)": {"full_name": "Akij Essential Flour Mill",                   "sheet": "AEL (Flour)"},
    "AEL (Rice)":  {"full_name": "Akij Essential Rice Mill",                    "sheet": "AEL (Rice)"},
    "APFIL":       {"full_name": "Akij Poly Fibre Industries Ltd.",             "sheet": "APFIL"},
    "ABSL":        {"full_name": "Akij Building Solutions Ltd.",                "sheet": "ABSL"},
    "ARMCL-01":    {"full_name": "Akij Ready Mix Concrete Ltd. - Narayanganj", "sheet": "ARMCL - 01"},
}

CRITERIA_COLORS = {
    "Machine Utilization & Execution": "#4F8FFF",
    "Idle Capacity Cost (BDT)":        "#B370FF",
    "Downtime & Reliability":          "#FF6B6B",
    "Planning Accuracy & Efficiency":  "#00E5B8",
    "Process & Culture":               "#FFB347",
}

# Exact lowercase KPI names where LOWER = BETTER
LOWER_IS_BETTER = {
    "reduce downtime (%)",
    "downtime cost (bdt)",
    "breakdown hours/month",
    "idle hours × fixed cost per hour",
    "production loss due to planning error (%)",
    "idle time due to material shortage (%)",
    "changeover time reduction (%)",
}

# Exact lowercase KPI names that are raw BDT monetary values (never ×100)
BDT_NAMES = {
    "downtime cost (bdt)",
    "idle hours × fixed cost per hour",
}

# Exact lowercase KPI names that are raw hours (never ×100)
HOURS_NAMES = {
    "breakdown hours/month",
}


# ─────────────────────────────────────────────────────────────
# VALUE TYPE HELPERS
# ─────────────────────────────────────────────────────────────
def is_bdt(kpi: str) -> bool:
    return kpi.lower() in BDT_NAMES

def is_hours(kpi: str) -> bool:
    return kpi.lower() in HOURS_NAMES

def is_pct(kpi: str) -> bool:
    return not is_bdt(kpi) and not is_hours(kpi)


# ─────────────────────────────────────────────────────────────
# SAFE FLOAT  ←  THE CRITICAL FIX
# ─────────────────────────────────────────────────────────────
def safe_float(v) -> "float | None":
    """
    Parse a raw cell value to float.

    KEY BEHAVIOUR:
    Google Sheets GViz CSV export converts cells that are
    formatted as % in the sheet into strings like "11.83%".
    openpyxl / Excel returns them as raw decimals 0.1183.

    We MUST detect the "%" suffix and divide by 100 so every
    value stored in the dataframe is always the raw decimal form:
        "11.83%"  →  0.1183
        "65.45%"  →  0.6545
        "1507935" →  1507935  (BDT, no change)
        "17.31"   →  17.31    (hours, no change)
    """
    if v is None:
        return None

    s = str(v).strip()

    # Reject errors and empties
    if not s or s in {
        "nan", "NaT", "None", "#REF!", "#DIV/0!", "#VALUE!",
        "#N/A", "#NAME?", "#NULL!", "N/A", "-",
    }:
        return None

    # Remember if GViz gave us a "%" string
    has_pct = s.endswith("%")

    # Strip formatting
    clean = s.replace("%", "").replace(",", "").strip()

    try:
        num = float(clean)
    except ValueError:
        return None   # e.g. "Changeover occurs within seconds…"

    # If GViz sent "11.83%", restore to decimal 0.1183
    if has_pct:
        num /= 100.0

    return num


# ─────────────────────────────────────────────────────────────
# DATE PARSER
# ─────────────────────────────────────────────────────────────
def parse_date(s: str) -> "date | None":
    if not s or s in ("nan", "None", ""):
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
        "%m/%d/%Y", "%d/%m/%Y",
        "%m-%d-%Y", "%d-%m-%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(s[:10], fmt[:10]).date()
        except Exception:
            pass
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_raw(sheet_id: str, sheet_name: str) -> pd.DataFrame:
    """Load sheet as CSV (all values as strings to preserve % suffixes)."""
    # Try service account
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        info = st.secrets.get("gcp_service_account", None)
        if info:
            creds = Credentials.from_service_account_info(
                info,
                scopes=[
                    "https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive",
                ],
            )
            gc = gspread.authorize(creds)
            rows = gc.open_by_key(sheet_id).worksheet(sheet_name).get_all_values()
            return pd.DataFrame(rows)
    except Exception:
        pass

    # Public GViz CSV — dtype=str preserves "11.83%" strings intact
    try:
        url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}"
            f"/gviz/tq?tqx=out:csv&sheet={sheet_name.replace(' ', '%20')}"
        )
        return pd.read_csv(url, header=None, dtype=str)
    except Exception as e:
        st.error(f"Cannot load '{sheet_name}': {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# PARSE INTO KPI DATAFRAME
# ─────────────────────────────────────────────────────────────
def parse_kpi_df(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty or len(raw) < 2:
        return pd.DataFrame()

    header = raw.iloc[0]

    # Map column index → date object for daily columns (col 6+)
    date_cols: dict = {}
    for c in range(6, len(raw.columns)):
        lbl = str(header.iloc[c]) if c < len(header) else ""
        d = parse_date(lbl)
        if d:
            date_cols[c] = d

    records = []
    for r in range(1, len(raw)):
        row = raw.iloc[r]

        kpi_name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        if not kpi_name or kpi_name.lower() in ("kpi", "nan", ""):
            continue

        criteria = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        baseline = safe_float(row.iloc[3] if len(row) > 3 else None)
        target   = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else ""
        actual   = safe_float(row.iloc[5] if len(row) > 5 else None)

        daily: dict = {}
        for c, dt in date_cols.items():
            val = safe_float(row.iloc[c] if c < len(row) else None)
            if val is not None:
                daily[dt] = val

        records.append(dict(
            criteria=criteria,
            kpi_name=kpi_name,
            baseline=baseline,
            target=target,
            actual=actual,
            daily=daily,
        ))

    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────
# DISPLAY FORMATTING
# ─────────────────────────────────────────────────────────────
def fmt(kpi: str, val: "float | None") -> str:
    """
    Format stored value for display labels.
    After safe_float:
      BDT  KPIs → raw large numbers  (1507935)  → ৳1.51M
      Hour KPIs → raw hour numbers   (17.3)     → 17.3 hrs
      Pct  KPIs → raw decimals       (0.1182)   → 11.8%
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"

    if is_bdt(kpi):
        a = abs(val)
        if a >= 1_000_000: return f"৳{val/1_000_000:.2f}M"
        if a >= 1_000:     return f"৳{val/1_000:.1f}K"
        return f"৳{val:,.0f}"

    if is_hours(kpi):
        return f"{val:.1f} hrs"

    # Percentage decimal → multiply by 100 for display
    return f"{val * 100:.1f}%"


def to_chart(kpi: str, val: "float | None") -> "float | None":
    """Convert stored value to chart-axis unit."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if is_bdt(kpi):   return val / 1_000   # show in K BDT on axis
    if is_hours(kpi): return val            # raw hours
    return val * 100                        # decimal → %


def axis_unit(kpi: str) -> str:
    if is_bdt(kpi):   return "K BDT"
    if is_hours(kpi): return "hrs"
    return "%"


# ─────────────────────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────────────────────
def score(kpi: str, val: "float | None") -> "float | None":
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None

    lower = kpi.lower() in LOWER_IS_BETTER

    if is_bdt(kpi):
        return max(0.0, 1.0 - min(1.0, abs(val) / 5_000_000))

    if is_hours(kpi):
        return max(0.0, 1.0 - min(1.0, abs(val) / 100.0))

    # Percentage decimal
    if lower:
        return max(0.0, 1.0 - min(1.0, abs(val)))
    else:
        return min(1.0, max(0.0, val))


def badge(sc: "float | None"):
    if sc is None:     return "N/A",      "#4e5870", "badge-na"
    if sc >= 0.75:     return "On Track", "#22d3a5", "badge-good"
    if sc >= 0.45:     return "At Risk",  "#f59e0b", "badge-warn"
    return "Critical", "#ef4444", "badge-bad"


# ─────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif}
.stApp{background:#0d0f14}
section[data-testid="stSidebar"]{background:#13161f!important;border-right:1px solid #ffffff0f}
section[data-testid="stSidebar"] *{color:#f0f2f8!important}
section[data-testid="stSidebar"] .stSelectbox>div>div{background:#1c2030;border:1px solid #ffffff1a}
header[data-testid="stHeader"]{background:transparent}
.top-bar{background:linear-gradient(135deg,#13161f,#1a1f2e);border:1px solid #ffffff0f;border-radius:16px;padding:20px 28px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between}
.brand-logo{width:44px;height:44px;background:linear-gradient(135deg,#4F8FFF,#00E5B8);border-radius:12px;display:flex;align-items:center;justify-content:center;font-family:'Syne',sans-serif;font-weight:800;color:#fff;font-size:15px;box-shadow:0 0 20px #4F8FFF33;float:left;margin-right:14px}
.brand-title{font-family:'Syne',sans-serif;font-weight:700;font-size:18px;color:#f0f2f8}
.brand-sub{font-size:11px;color:#4e5870;text-transform:uppercase;letter-spacing:.8px}
.sbu-hero-name{font-family:'Syne',sans-serif;font-weight:800;font-size:28px;background:linear-gradient(90deg,#4F8FFF,#00E5B8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sbu-hero-full{font-size:12px;color:#4e5870;margin-top:2px}
.kpi-card{background:#13161f;border:1px solid #ffffff0f;border-radius:14px;padding:18px 18px 14px;border-top:3px solid;min-height:140px}
.kpi-card:hover{border-color:#ffffff1a}
.kpi-card-cat{font-size:10px;color:#4e5870;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}
.kpi-card-val{font-family:'Syne',sans-serif;font-weight:700;font-size:26px;line-height:1;margin-bottom:6px}
.kpi-card-name{font-size:11.5px;color:#8892ab;margin-bottom:8px;line-height:1.3}
.kpi-badge{display:inline-block;padding:2px 10px;border-radius:99px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.4px}
.badge-good{background:#22d3a520;color:#22d3a5}
.badge-warn{background:#f59e0b20;color:#f59e0b}
.badge-bad{background:#ef444420;color:#ef4444}
.badge-na{background:#ffffff12;color:#4e5870}
.section-title{font-family:'Syne',sans-serif;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:#4e5870;margin:24px 0 12px 0}
[data-testid="stMetric"]{background:#13161f;border:1px solid #ffffff0f;border-radius:12px;padding:14px}
[data-testid="stMetricValue"]{font-family:'Syne',sans-serif!important}
[data-testid="stMetricLabel"]{font-size:11px!important;color:#4e5870!important}
hr{border-color:#ffffff0f!important}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#ffffff1a;border-radius:99px}
.kpi-table-wrap{overflow-x:auto}
table.kpi-table{width:100%;border-collapse:collapse;font-size:12.5px}
table.kpi-table th{background:#1c2030;color:#4e5870;padding:10px 14px;text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid #ffffff0f}
table.kpi-table td{padding:10px 14px;border-bottom:1px solid #ffffff0a;color:#8892ab}
table.kpi-table td:nth-child(2){color:#f0f2f8;font-weight:500}
table.kpi-table tr:hover td{background:#1a1f2e}
</style>
"""

# ─────────────────────────────────────────────────────────────
# CHART CONSTANTS
# ─────────────────────────────────────────────────────────────
BG = "#13161f"; GRID = "rgba(255,255,255,0.06)"; TICK = "#8892ab"; FONT = "DM Sans,sans-serif"

def _base(h=300):
    return dict(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TICK, size=11),
        height=h, margin=dict(l=10, r=10, t=36, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        xaxis=dict(gridcolor=GRID, color=TICK, showline=False),
        yaxis=dict(gridcolor=GRID, color=TICK, showline=False),
    )


# ─────────────────────────────────────────────────────────────
# CHARTS
# ─────────────────────────────────────────────────────────────
def make_trend(df, kpi, d0, d1):
    row = df[df["kpi_name"] == kpi]
    if row.empty: return go.Figure()
    row = row.iloc[0]
    pts = sorted([(d, v) for d, v in row["daily"].items() if d0 <= d <= d1])
    if not pts: return go.Figure()
    xs = [p[0] for p in pts]
    ys = [to_chart(kpi, p[1]) for p in pts]
    u  = axis_unit(kpi)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers", name=kpi,
        line=dict(color="#4F8FFF", width=2.5), marker=dict(size=5, color="#4F8FFF"),
        fill="tozeroy", fillcolor="rgba(79,143,255,0.10)",
        hovertemplate=f"%{{x}}: %{{y:.2f}} {u}<extra></extra>",
    ))
    bv = to_chart(kpi, row["baseline"])
    if bv is not None:
        fig.add_hline(y=bv, line_dash="dot", line_color="#FF6B6B", line_width=1.5,
                      annotation_text=f"Baseline {bv:.2f} {u}",
                      annotation_font=dict(color="#FF6B6B", size=10))
    lay = _base(300)
    lay["title"] = dict(text=kpi[:60], font=dict(size=12, color=TICK))
    lay["yaxis"]["ticksuffix"] = f" {u}"
    fig.update_layout(**lay)
    return fig


def make_radar(df):
    grp: dict = {}
    for _, r in df.iterrows():
        s = score(r["kpi_name"], r["actual"])
        if s is not None:
            grp.setdefault(r["criteria"], []).append(s * 100)
    if not grp: return go.Figure()
    labs = [k.split(" & ")[0][:20] for k in grp]
    vals = [float(np.mean(v)) for v in grp.values()]
    labs += [labs[0]]; vals += [vals[0]]
    fig = go.Figure(go.Scatterpolar(
        r=vals, theta=labs, fill="toself",
        fillcolor="rgba(79,143,255,0.18)",
        line=dict(color="#4F8FFF", width=2), marker=dict(color="#4F8FFF", size=5),
    ))
    fig.update_layout(
        polar=dict(bgcolor=BG,
                   radialaxis=dict(visible=True, range=[0, 100], gridcolor=GRID,
                                   tickfont=dict(size=9, color=TICK), ticksuffix="%"),
                   angularaxis=dict(color=TICK, gridcolor=GRID,
                                    tickfont=dict(size=10, color=TICK))),
        paper_bgcolor=BG, font=dict(family=FONT, color=TICK),
        height=300, margin=dict(l=20, r=20, t=30, b=20), showlegend=False,
    )
    return fig


def make_bar(df):
    rows = df[df["actual"].notna()].copy()
    if rows.empty: return go.Figure()
    labs = [k[:38] for k in rows["kpi_name"]]
    act  = [to_chart(r["kpi_name"], r["actual"])   for _, r in rows.iterrows()]
    base = [to_chart(r["kpi_name"], r["baseline"]) for _, r in rows.iterrows()]
    fig  = go.Figure()
    if any(b is not None for b in base):
        fig.add_trace(go.Bar(y=labs, x=base, name="Baseline", orientation="h",
                             marker_color="rgba(79,143,255,0.45)",
                             marker_line=dict(color="#4F8FFF", width=1)))
    fig.add_trace(go.Bar(y=labs, x=act, name="Actual", orientation="h",
                         marker_color="rgba(0,229,184,0.45)",
                         marker_line=dict(color="#00E5B8", width=1)))
    h = max(300, len(rows) * 30)
    fig.update_layout(
        barmode="group", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TICK, size=11), height=h,
        margin=dict(l=10, r=20, t=36, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor=GRID, color=TICK),
        yaxis=dict(gridcolor=GRID, color=TICK, automargin=True, tickfont=dict(size=10)),
        title=dict(text="Baseline vs Actual", font=dict(size=12, color=TICK)),
    )
    return fig


def make_heatmap(df, kpi, d0, d1):
    row = df[df["kpi_name"] == kpi]
    if row.empty: return go.Figure()
    row = row.iloc[0]
    pts = sorted([(d, v) for d, v in row["daily"].items() if d0 <= d <= d1])
    if not pts: return go.Figure()
    u = axis_unit(kpi)
    fig = go.Figure(go.Heatmap(
        x=[str(p[0]) for p in pts],
        y=[kpi[:30]],
        z=[[to_chart(kpi, p[1]) for p in pts]],
        colorscale=[[0,"#ef4444"],[0.5,"#f59e0b"],[1,"#22d3a5"]],
        hovertemplate=f"%{{x}}: %{{z:.2f}} {u}<extra></extra>",
        showscale=True,
        colorbar=dict(tickfont=dict(color=TICK, size=10), outlinewidth=0, bgcolor=BG),
    ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family=FONT, color=TICK, size=11),
        height=130, margin=dict(l=10, r=10, t=10, b=50),
        xaxis=dict(color=TICK, tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(color=TICK, tickfont=dict(size=9)),
    )
    return fig


def make_donut(df):
    grp: dict = {}
    for _, r in df.iterrows():
        s = score(r["kpi_name"], r["actual"])
        if s is not None:
            grp.setdefault(r["criteria"], []).append(s * 100)
    if not grp: return go.Figure()
    labs   = list(grp.keys())
    vals   = [float(np.mean(v)) for v in grp.values()]
    colors = [CRITERIA_COLORS.get(l, "#8892ab") for l in labs]
    fig = go.Figure(go.Pie(
        labels=[l.split(" & ")[0] for l in labs], values=vals, hole=0.65,
        marker=dict(colors=[c+"aa" for c in colors], line=dict(color=colors, width=2)),
        textfont=dict(size=11, color="#f0f2f8"),
        hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=BG, font=dict(family=FONT, color=TICK, size=11),
        height=280, margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10, color=TICK)),
        annotations=[dict(text="Score", x=0.5, y=0.5,
                          font=dict(size=13, color="#8892ab"), showarrow=False)],
    )
    return fig


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    st.markdown(CSS, unsafe_allow_html=True)

    # ── SIDEBAR ──────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🏭 AKIJ Resource")
        st.markdown("---")
        st.markdown("**Select SBU**")
        sbu = st.selectbox(
            "SBU", list(SBU_CONFIG.keys()),
            format_func=lambda k: f"{k}  —  {SBU_CONFIG[k]['full_name'][:28]}",
            label_visibility="collapsed",
        )
        cfg  = SBU_CONFIG[sbu]
        sname = cfg["sheet"]

        st.markdown("---")
        st.markdown("**Date Range**")

        with st.spinner("Loading…"):
            raw = load_raw(SHEET_ID, sname)
        df = parse_kpi_df(raw)

        all_dates = sorted({d for r in df.itertuples() for d in r.daily}) if not df.empty else []
        min_d = all_dates[0]  if all_dates else date(2026, 4, 1)
        max_d = all_dates[-1] if all_dates else date(2026, 4, 30)

        d0 = st.date_input("From", value=min_d, min_value=min_d, max_value=max_d)
        d1 = st.date_input("To",   value=max_d, min_value=min_d, max_value=max_d)

        st.markdown("---")
        st.markdown("**Filter Category**")
        cats = ["All"] + sorted(df["criteria"].unique().tolist()) if not df.empty else ["All"]
        cat  = st.selectbox("Category", cats, label_visibility="collapsed")

        st.markdown("---")
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown(
            "<p style='font-size:10px;color:#4e5870;text-align:center;margin-top:16px'>"
            "AKIJ Resource · Production Planning<br>KPI Intelligence · Live Google Sheets</p>",
            unsafe_allow_html=True,
        )

    # ── HEADER ───────────────────────────────────────────────
    st.markdown(f"""
    <div class="top-bar">
      <div style="display:flex;align-items:center">
        <div class="brand-logo">AR</div>
        <div>
          <div class="brand-title">AKIJ Resource</div>
          <div class="brand-sub">Production Planning KPI Intelligence</div>
        </div>
      </div>
      <div style="text-align:right">
        <div class="sbu-hero-name">{sbu}</div>
        <div class="sbu-hero-full">{cfg['full_name']}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if df.empty:
        st.warning("⚠️ No data. Share the sheet publicly: Share → Anyone with link → Viewer.")
        return

    # ── FILTER ───────────────────────────────────────────────
    view = df.copy()
    if cat != "All":
        view = view[view["criteria"] == cat].reset_index(drop=True)
    view["daily"] = view["daily"].apply(
        lambda d: {k: v for k, v in d.items() if d0 <= k <= d1}
    )

    # ── SUMMARY METRICS ──────────────────────────────────────
    scores_all = [score(r.kpi_name, r.actual) for r in view.itertuples()]
    valid      = [s for s in scores_all if s is not None]
    avg_sc     = np.mean(valid) * 100 if valid else 0

    st.markdown(
        f"<p style='font-size:12px;color:#4e5870;margin-bottom:12px'>"
        f"📅 {d0.strftime('%d %b %Y')} → {d1.strftime('%d %b %Y')}"
        f"  |  {len(view)} KPIs</p>",
        unsafe_allow_html=True,
    )
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Overall Score",  f"{avg_sc:.1f}%")
    c2.metric("KPIs Tracked",   len(view))
    c3.metric("✅ On Track",    sum(1 for s in valid if s >= 0.75))
    c4.metric("⚠️ At Risk",    sum(1 for s in valid if 0.45 <= s < 0.75))
    c5.metric("🔴 Critical",   sum(1 for s in valid if s < 0.45))
    st.markdown("<hr>", unsafe_allow_html=True)

    # ── KPI SCORE CARDS ──────────────────────────────────────
    st.markdown('<div class="section-title">KPI Scorecard</div>', unsafe_allow_html=True)
    COLS = 4
    for i in range(0, len(view), COLS):
        chunk = view.iloc[i:i+COLS]
        cols  = st.columns(len(chunk))
        for col, (_, r) in zip(cols, chunk.iterrows()):
            sc            = score(r["kpi_name"], r["actual"])
            blabel, bcol, bcls = badge(sc)
            val_str       = fmt(r["kpi_name"], r["actual"])
            with col:
                st.markdown(f"""
                <div class="kpi-card" style="border-top-color:{bcol}">
                  <div class="kpi-card-cat">{r['criteria'][:26]}</div>
                  <div class="kpi-card-val" style="color:{bcol}">{val_str}</div>
                  <div class="kpi-card-name">{r['kpi_name']}</div>
                  <span class="kpi-badge {bcls}">{blabel}</span>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── TREND + RADAR ─────────────────────────────────────────
    st.markdown('<div class="section-title">Trend & Category Radar</div>', unsafe_allow_html=True)
    ct, cr = st.columns([3, 2])
    kpis_daily = [
        r["kpi_name"] for _, r in view.iterrows()
        if any(d0 <= d <= d1 for d in r["daily"])
    ]
    with ct:
        if kpis_daily:
            sel_t = st.selectbox("KPI (trend)", kpis_daily, key="t", label_visibility="collapsed")
            st.plotly_chart(make_trend(view, sel_t, d0, d1), use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("No daily data for selected range.")
    with cr:
        st.plotly_chart(make_radar(view), use_container_width=True,
                        config={"displayModeBar": False})

    # ── BAR + DONUT ───────────────────────────────────────────
    st.markdown('<div class="section-title">Baseline vs Actual & Category Distribution</div>',
                unsafe_allow_html=True)
    cb, cd = st.columns([3, 2])
    with cb:
        st.plotly_chart(make_bar(view), use_container_width=True, config={"displayModeBar": False})
    with cd:
        st.plotly_chart(make_donut(view), use_container_width=True, config={"displayModeBar": False})

    # ── HEATMAP ───────────────────────────────────────────────
    if kpis_daily:
        st.markdown('<div class="section-title">Daily Performance Heatmap</div>',
                    unsafe_allow_html=True)
        sel_h = st.selectbox("KPI (heatmap)", kpis_daily, key="h", label_visibility="collapsed")
        st.plotly_chart(make_heatmap(view, sel_h, d0, d1), use_container_width=True,
                        config={"displayModeBar": False})

    # ── DETAIL TABLE ─────────────────────────────────────────
    st.markdown('<div class="section-title">KPI Detail Table</div>', unsafe_allow_html=True)
    tbody = ""
    for _, r in view.iterrows():
        sc            = score(r["kpi_name"], r["actual"])
        blabel, bcol, bcls = badge(sc)
        ccol = CRITERIA_COLORS.get(r["criteria"], "#4e5870")
        tbody += (
            f"<tr>"
            f"<td><span style='color:{ccol};font-size:10px'>{r['criteria']}</span></td>"
            f"<td>{r['kpi_name']}</td>"
            f"<td>{fmt(r['kpi_name'], r['baseline'])}</td>"
            f"<td>{r['target']}</td>"
            f"<td style='color:{bcol};font-weight:600'>{fmt(r['kpi_name'], r['actual'])}</td>"
            f"<td><span class='kpi-badge {bcls}'>{blabel}</span></td>"
            f"</tr>"
        )
    st.markdown(
        f"<div class='kpi-table-wrap'><table class='kpi-table'>"
        f"<thead><tr><th>Criteria</th><th>KPI</th><th>Baseline</th>"
        f"<th>Target</th><th>Actual</th><th>Status</th></tr></thead>"
        f"<tbody>{tbody}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<br><p style='text-align:center;font-size:11px;color:#ffffff'>"
        "AKIJ Resource · Production Planning KPI Intelligence · Created By: Md. Ariful Islam Ratul (MTO - Operations) </p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
