"""
AKIJ Resource — Production Planning KPI Dashboard  v6
Reads LIVE from Google Sheets public CSV export.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
from io import StringIO
from datetime import datetime, date

st.set_page_config(
    page_title="AKIJ Resource — KPI Dashboard",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
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

LOWER_IS_BETTER = {
    "reduce downtime (%)",
    "downtime cost (bdt)",
    "breakdown hours/month",
    "idle hours × fixed cost per hour",
    "production loss due to planning error (%)",
    "idle time due to material shortage (%)",
    "changeover time reduction (%)",
}

BDT_KPIS   = {"downtime cost (bdt)", "idle hours × fixed cost per hour"}
HOURS_KPIS = {"breakdown hours/month"}
FONT       = "DM Sans, sans-serif"


# ─────────────────────────────────────────────────────────────────────────────
# SAFE FLOAT — handles every format the live Google Sheet sends
# ─────────────────────────────────────────────────────────────────────────────
def safe_float(v) -> "float | None":
    """
    Convert any cell value to float.

    Live Google Sheet GViz CSV sends:
      "30.17%"    → 0.3017   (% suffix → divide by 100)
      "579566.9"  → 579566.9 (BDT raw, no % suffix)
      "17.70"     → 17.70    (hours raw)
      "N/A", ""   → None
      "0"         → 0.0
      "85%"       → 0.85
      "Changeover occurs within seconds..." → None (text)
    """
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    s = str(v).strip()
    if not s:
        return None
    # Case-insensitive reject list
    if s.lower() in {
        "nan", "nat", "none", "n/a", "-",
        "#ref!", "#div/0!", "#value!", "#n/a", "#name?", "#null!",
    }:
        return None
    # Excel formula strings (GViz sometimes sends these)
    if s.startswith("="):
        m = re.search(r',\s*([-\d\.eE+]+)\s*\)\s*$', s)
        if m:
            try: return float(m.group(1))
            except: pass
        expr = s[1:].strip()
        if re.match(r'^[\d\s\+\-\*/\.\(\)]+$', expr):
            try: return float(eval(expr))  # safe: only digits + operators
            except: pass
        return None
    has_pct = s.endswith("%")
    clean   = s.replace("%", "").replace(",", "").strip()
    try:
        num = float(clean)
    except ValueError:
        return None  # text like "Changeover occurs within seconds..."
    if np.isnan(num) or np.isinf(num):
        return None
    return num / 100.0 if has_pct else num


# ─────────────────────────────────────────────────────────────────────────────
# DATE PARSER
# ─────────────────────────────────────────────────────────────────────────────
def parse_date(s: str) -> "date | None":
    if not s or str(s).lower() in ("nan", "none", ""):
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y",
                "%d/%m/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt[:10]).date()
        except Exception:
            pass
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING — always fetches live from Google Sheets
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_sheet(sheet_id: str, sheet_name: str) -> pd.DataFrame:
    """
    Fetch sheet as CSV from Google Sheets public export.
    dtype=str ensures we receive raw strings like "30.17%" intact.
    """
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/gviz/tq?tqx=out:csv&sheet={sheet_name.replace(' ', '%20')}"
    )
    try:
        import requests
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text), header=None, dtype=str)
        return df
    except Exception:
        pass
    # urllib fallback
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=15) as r:
            text = r.read().decode("utf-8")
        df = pd.read_csv(StringIO(text), header=None, dtype=str)
        return df
    except Exception as e:
        st.error(f"❌ Could not load '{sheet_name}': {e}\n\nMake sure the sheet is set to 'Anyone with the link can view'.")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# PARSE RAW CSV → KPI DATAFRAME
# ─────────────────────────────────────────────────────────────────────────────
def parse_kpis(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Row 0  = header: Criteria | KPI | Formula | Baseline | Target | Actual | date…
    Rows 1+= one KPI per row.
    """
    if raw.empty or len(raw) < 2:
        return pd.DataFrame()

    header = raw.iloc[0]

    # Detect date columns (col 6 onward)
    date_cols: dict = {}
    for c in range(6, len(raw.columns)):
        d = parse_date(str(header.iloc[c]) if c < len(header) else "")
        if d:
            date_cols[c] = d

    records = []
    for ri in range(1, len(raw)):
        row      = raw.iloc[ri]
        kpi_name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        if not kpi_name or kpi_name.lower() in ("kpi", "nan", ""):
            continue
        criteria = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        baseline = safe_float(row.iloc[3] if len(row) > 3 else None)
        target   = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else ""
        actual   = safe_float(row.iloc[5] if len(row) > 5 else None)

        daily: dict = {}
        for c, dt in date_cols.items():
            v = safe_float(row.iloc[c] if c < len(row) else None)
            if v is not None:
                daily[dt] = v

        records.append(dict(
            criteria=criteria, kpi_name=kpi_name,
            baseline=baseline, target=target,
            actual=actual,    daily=daily,
        ))

    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# VALUE FORMATTING
# ─────────────────────────────────────────────────────────────────────────────
def fmt(kpi: str, val: "float | None") -> str:
    """Format stored value for display cards & table."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    k = kpi.lower()
    if k in BDT_KPIS:
        a = abs(val)
        if a >= 1_000_000: return f"৳{val/1_000_000:.2f}M"
        if a >= 1_000:     return f"৳{val/1_000:.1f}K"
        return f"৳{val:,.0f}"
    if k in HOURS_KPIS:
        return f"{val:.1f} hrs"
    # Percentage — stored as decimal after safe_float
    return f"{val * 100:.1f}%"


def to_chart_val(kpi: str, val: "float | None") -> "float | None":
    """Scale stored value for chart axes."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    k = kpi.lower()
    if k in BDT_KPIS:   return val / 1_000   # K BDT
    if k in HOURS_KPIS: return val            # hrs
    return val * 100                           # %


def axis_unit(kpi: str) -> str:
    k = kpi.lower()
    if k in BDT_KPIS:   return "K BDT"
    if k in HOURS_KPIS: return "hrs"
    return "%"


# ─────────────────────────────────────────────────────────────────────────────
# SCORING & BADGE
# ─────────────────────────────────────────────────────────────────────────────
def score(kpi: str, val: "float | None") -> "float | None":
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    k = kpi.lower()
    lower = k in LOWER_IS_BETTER
    if k in BDT_KPIS:
        return max(0.0, 1.0 - min(1.0, abs(val) / 5_000_000))
    if k in HOURS_KPIS:
        return max(0.0, 1.0 - min(1.0, abs(val) / 100.0))
    if lower:
        return max(0.0, 1.0 - min(1.0, abs(val)))
    return min(1.0, max(0.0, val))


def badge(sc: "float | None"):
    if sc is None:  return "N/A",      "#8892ab", "badge-na"
    if sc >= 0.75:  return "On Track", "#22d3a5", "badge-good"
    if sc >= 0.45:  return "At Risk",  "#f59e0b", "badge-warn"
    return "Critical", "#ef4444", "badge-bad"


# ─────────────────────────────────────────────────────────────────────────────
# THEME
# ─────────────────────────────────────────────────────────────────────────────
THEMES = {
    "🌙 Dark": dict(
        bg_page="#0d0f14", bg_card="#13161f", bg_sidebar="#13161f",
        bg_input="#1c2030", bg_th="#1c2030", bg_hover="#1a1f2e",
        border="rgba(255,255,255,0.06)", border_i="rgba(255,255,255,0.12)",
        border_h="rgba(255,255,255,0.14)",
        t1="#f0f2f8", t2="#8892ab", t3="#4e5870", t_side="#f0f2f8",
        topbar="linear-gradient(135deg,#13161f,#1a1f2e)",
        hr="rgba(255,255,255,0.06)", scroll="rgba(255,255,255,0.10)",
        m_bg="#13161f", m_bdr="rgba(255,255,255,0.06)",
        c_bg="#13161f", c_grid="rgba(255,255,255,0.06)", c_tick="#8892ab",
        legend_bg="rgba(0,0,0,0)",
    ),
    "☀️ Light": dict(
        bg_page="#f4f6fc", bg_card="#ffffff", bg_sidebar="#ffffff",
        bg_input="#f0f2f9", bg_th="#f0f2f9", bg_hover="#f8f9ff",
        border="rgba(0,0,0,0.07)", border_i="rgba(0,0,0,0.14)",
        border_h="rgba(79,143,255,0.35)",
        t1="#1a1f36", t2="#4a5068", t3="#8892ab", t_side="#1a1f36",
        topbar="linear-gradient(135deg,#ffffff,#f0f4ff)",
        hr="rgba(0,0,0,0.08)", scroll="rgba(0,0,0,0.15)",
        m_bg="#ffffff", m_bdr="rgba(0,0,0,0.07)",
        c_bg="#ffffff", c_grid="rgba(0,0,0,0.07)", c_tick="#4a5068",
        legend_bg="rgba(255,255,255,0)",
    ),
}

def T():
    return THEMES[st.session_state.get("theme", "🌙 Dark")]

def css(t):
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');
html,body,[class*="css"]{{font-family:'DM Sans',sans-serif}}
.stApp{{background:{t["bg_page"]}!important}}
section[data-testid="stSidebar"]{{background:{t["bg_sidebar"]}!important;border-right:1px solid {t["border"]}}}
section[data-testid="stSidebar"] *{{color:{t["t_side"]}!important}}
section[data-testid="stSidebar"] .stSelectbox>div>div{{background:{t["bg_input"]};border:1px solid {t["border_i"]}}}
header[data-testid="stHeader"]{{background:transparent}}
.topbar{{background:{t["topbar"]};border:1px solid {t["border"]};border-radius:16px;padding:20px 28px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between}}
.logo{{width:44px;height:44px;background:linear-gradient(135deg,#4F8FFF,#00E5B8);border-radius:12px;display:flex;align-items:center;justify-content:center;font-family:'Syne',sans-serif;font-weight:800;color:#fff;font-size:15px;box-shadow:0 0 20px #4F8FFF33;float:left;margin-right:14px}}
.brand{{font-family:'Syne',sans-serif;font-weight:700;font-size:18px;color:{t["t1"]}}}
.brand-sub{{font-size:11px;color:{t["t3"]};text-transform:uppercase;letter-spacing:.8px}}
.sbu-name{{font-family:'Syne',sans-serif;font-weight:800;font-size:28px;background:linear-gradient(90deg,#4F8FFF,#00E5B8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sbu-full{{font-size:12px;color:{t["t3"]};margin-top:2px}}
.kcard{{background:{t["bg_card"]};border:1px solid {t["border"]};border-radius:14px;padding:18px 18px 14px;border-top:3px solid;min-height:150px;transition:border-color .15s}}
.kcard:hover{{border-color:{t["border_h"]}}}
.kcard-cat{{font-size:10px;color:{t["t3"]};text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}}
.kcard-val{{font-family:'Syne',sans-serif;font-weight:700;font-size:26px;line-height:1;margin-bottom:5px}}
.kcard-name{{font-size:11.5px;color:{t["t2"]};margin-bottom:3px;line-height:1.3}}
.kcard-base{{font-size:10px;color:{t["t3"]};margin-bottom:6px}}
.kbadge{{display:inline-block;padding:2px 10px;border-radius:99px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.4px}}
.badge-good{{background:#22d3a520;color:#22d3a5}}
.badge-warn{{background:#f59e0b20;color:#f59e0b}}
.badge-bad{{background:#ef444420;color:#ef4444}}
.badge-na{{background:{t["border"]};color:{t["t3"]}}}
.sec{{font-family:'Syne',sans-serif;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:{t["t3"]};margin:24px 0 12px 0}}
[data-testid="stMetric"]{{background:{t["m_bg"]};border:1px solid {t["m_bdr"]};border-radius:12px;padding:14px}}
[data-testid="stMetricValue"]{{font-family:'Syne',sans-serif!important;color:{t["t1"]}!important}}
[data-testid="stMetricLabel"]{{font-size:11px!important;color:{t["t3"]}!important}}
hr{{border-color:{t["hr"]}!important}}
::-webkit-scrollbar{{width:5px;height:5px}}::-webkit-scrollbar-track{{background:transparent}}
::-webkit-scrollbar-thumb{{background:{t["scroll"]};border-radius:99px}}
.tw{{overflow-x:auto}}
table.kt{{width:100%;border-collapse:collapse;font-size:12.5px}}
table.kt th{{background:{t["bg_th"]};color:{t["t3"]};padding:10px 14px;text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid {t["border"]}}}
table.kt td{{padding:10px 14px;border-bottom:1px solid {t["border"]};color:{t["t2"]}}}
table.kt td:nth-child(2){{color:{t["t1"]};font-weight:500}}
table.kt tr:hover td{{background:{t["bg_hover"]}}}
</style>"""


# ─────────────────────────────────────────────────────────────────────────────
# CHART HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _base(h=300):
    t = T()
    return dict(
        paper_bgcolor=t["c_bg"], plot_bgcolor=t["c_bg"],
        font=dict(family=FONT, color=t["c_tick"], size=11),
        height=h, margin=dict(l=10, r=10, t=36, b=10),
        legend=dict(bgcolor=t["legend_bg"], font=dict(size=11, color=t["c_tick"])),
        xaxis=dict(gridcolor=t["c_grid"], color=t["c_tick"], showline=False),
        yaxis=dict(gridcolor=t["c_grid"], color=t["c_tick"], showline=False),
    )

def ch_trend(df, kpi, d0, d1):
    t   = T()
    row = df[df["kpi_name"] == kpi]
    if row.empty: return go.Figure()
    row = row.iloc[0]
    pts = sorted([(d,v) for d,v in row["daily"].items() if d0<=d<=d1])
    if not pts: return go.Figure()
    u   = axis_unit(kpi)
    xs  = [p[0] for p in pts]
    ys  = [to_chart_val(kpi, p[1]) for p in pts]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers", name=kpi,
        line=dict(color="#4F8FFF", width=2.5),
        marker=dict(size=5, color="#4F8FFF"),
        fill="tozeroy", fillcolor="rgba(79,143,255,0.10)",
        hovertemplate=f"%{{x}}: %{{y:.2f}} {u}<extra></extra>",
    ))
    bv = to_chart_val(kpi, row["baseline"])
    if bv is not None:
        fig.add_hline(y=bv, line_dash="dot", line_color="#FF6B6B", line_width=1.5,
                      annotation_text=f"Baseline {bv:.2f} {u}",
                      annotation_font=dict(color="#FF6B6B", size=10))
    lay = _base(300)
    lay["title"] = dict(text=kpi[:60], font=dict(size=12, color=t["c_tick"]))
    lay["yaxis"]["ticksuffix"] = f" {u}"
    fig.update_layout(**lay)
    return fig

def ch_radar(df):
    t   = T()
    grp = {}
    for _, r in df.iterrows():
        s = score(r["kpi_name"], r["actual"])
        if s is not None:
            grp.setdefault(r["criteria"], []).append(s*100)
    if not grp: return go.Figure()
    labs = [k.split(" & ")[0][:20] for k in grp]
    vals = [float(np.mean(v)) for v in grp.values()]
    labs += [labs[0]]; vals += [vals[0]]
    fig = go.Figure(go.Scatterpolar(
        r=vals, theta=labs, fill="toself",
        fillcolor="rgba(79,143,255,0.18)",
        line=dict(color="#4F8FFF", width=2),
        marker=dict(color="#4F8FFF", size=5),
    ))
    fig.update_layout(
        polar=dict(bgcolor=t["c_bg"],
                   radialaxis=dict(visible=True, range=[0,100], gridcolor=t["c_grid"],
                                   tickfont=dict(size=9, color=t["c_tick"]), ticksuffix="%"),
                   angularaxis=dict(color=t["c_tick"], gridcolor=t["c_grid"],
                                    tickfont=dict(size=10, color=t["c_tick"]))),
        paper_bgcolor=t["c_bg"], font=dict(family=FONT, color=t["c_tick"]),
        height=300, margin=dict(l=20,r=20,t=30,b=20), showlegend=False,
    )
    return fig

def ch_bar(df):
    t    = T()
    rows = df[df["actual"].notna()].copy()
    if rows.empty: return go.Figure()
    labs  = [k[:38] for k in rows["kpi_name"]]
    act   = [to_chart_val(r["kpi_name"], r["actual"])   for _, r in rows.iterrows()]
    base  = [to_chart_val(r["kpi_name"], r["baseline"]) for _, r in rows.iterrows()]
    fig   = go.Figure()
    if any(b is not None for b in base):
        fig.add_trace(go.Bar(y=labs, x=base, name="Baseline", orientation="h",
                             marker_color="rgba(79,143,255,0.45)",
                             marker_line=dict(color="#4F8FFF", width=1)))
    fig.add_trace(go.Bar(y=labs, x=act, name="Actual", orientation="h",
                         marker_color="rgba(0,229,184,0.45)",
                         marker_line=dict(color="#00E5B8", width=1)))
    h = max(300, len(rows)*30)
    fig.update_layout(
        barmode="group", paper_bgcolor=t["c_bg"], plot_bgcolor=t["c_bg"],
        font=dict(family=FONT, color=t["c_tick"], size=11), height=h,
        margin=dict(l=10,r=20,t=36,b=10),
        legend=dict(bgcolor=t["legend_bg"], font=dict(color=t["c_tick"])),
        xaxis=dict(gridcolor=t["c_grid"], color=t["c_tick"]),
        yaxis=dict(gridcolor=t["c_grid"], color=t["c_tick"],
                   automargin=True, tickfont=dict(size=10)),
        title=dict(text="Baseline vs Actual", font=dict(size=12, color=t["c_tick"])),
    )
    return fig

def ch_heatmap(df, kpi, d0, d1):
    t   = T()
    row = df[df["kpi_name"] == kpi]
    if row.empty: return go.Figure()
    row = row.iloc[0]
    pts = sorted([(d,v) for d,v in row["daily"].items() if d0<=d<=d1])
    if not pts: return go.Figure()
    u = axis_unit(kpi)
    fig = go.Figure(go.Heatmap(
        x=[str(p[0]) for p in pts], y=[kpi[:30]],
        z=[[to_chart_val(kpi, p[1]) for p in pts]],
        colorscale=[[0,"#ef4444"],[0.5,"#f59e0b"],[1,"#22d3a5"]],
        hovertemplate=f"%{{x}}: %{{z:.2f}} {u}<extra></extra>",
        showscale=True,
        colorbar=dict(tickfont=dict(color=t["c_tick"], size=10),
                      outlinewidth=0, bgcolor=t["c_bg"]),
    ))
    fig.update_layout(
        paper_bgcolor=t["c_bg"], plot_bgcolor=t["c_bg"],
        font=dict(family=FONT, color=t["c_tick"], size=11),
        height=130, margin=dict(l=10,r=10,t=10,b=50),
        xaxis=dict(color=t["c_tick"], tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(color=t["c_tick"], tickfont=dict(size=9)),
    )
    return fig

def ch_donut(df):
    t   = T()
    grp = {}
    for _, r in df.iterrows():
        s = score(r["kpi_name"], r["actual"])
        if s is not None:
            grp.setdefault(r["criteria"], []).append(s*100)
    if not grp: return go.Figure()
    labs   = list(grp.keys())
    vals   = [float(np.mean(v)) for v in grp.values()]
    colors = [CRITERIA_COLORS.get(l, "#8892ab") for l in labs]
    fig = go.Figure(go.Pie(
        labels=[l.split(" & ")[0] for l in labs], values=vals, hole=0.65,
        marker=dict(colors=[c+"aa" for c in colors], line=dict(color=colors, width=2)),
        textfont=dict(size=11, color=t["t1"]),
        hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=t["c_bg"], font=dict(family=FONT, color=t["c_tick"], size=11),
        height=280, margin=dict(l=10,r=10,t=10,b=10),
        legend=dict(bgcolor=t["legend_bg"], font=dict(size=10, color=t["c_tick"])),
        annotations=[dict(text="Score", x=0.5, y=0.5,
                          font=dict(size=13, color=t["t3"]), showarrow=False)],
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    if "theme" not in st.session_state:
        st.session_state["theme"] = "🌙 Dark"

    t = T()
    st.markdown(css(t), unsafe_allow_html=True)

    # ── SIDEBAR ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🏭 AKIJ Resource")
        st.markdown("---")
        st.markdown("**Appearance**")
        chosen = st.radio("Theme", list(THEMES.keys()),
                          index=list(THEMES.keys()).index(st.session_state["theme"]),
                          horizontal=True, label_visibility="collapsed")
        if chosen != st.session_state["theme"]:
            st.session_state["theme"] = chosen
            st.rerun()

        st.markdown("---")
        st.markdown("**Select SBU**")
        sbu = st.selectbox("SBU", list(SBU_CONFIG.keys()),
                           format_func=lambda k: f"{k}  —  {SBU_CONFIG[k]['full_name'][:28]}",
                           label_visibility="collapsed")
        cfg   = SBU_CONFIG[sbu]
        sname = cfg["sheet"]

        st.markdown("---")
        st.markdown("**Date Range**")
        with st.spinner("Loading…"):
            raw = load_sheet(SHEET_ID, sname)
        df = parse_kpis(raw)

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

        t = T()
        st.markdown(
            f"<p style='font-size:10px;color:{t['t3']};text-align:center;margin-top:16px'>"
            "AKIJ Resource · Production Planning<br>"
            "KPI Intelligence · Live Google Sheets<br>"
            "<b style='color:#4F8FFF'>v6</b></p>",
            unsafe_allow_html=True,
        )

    t = T()
    st.markdown(css(t), unsafe_allow_html=True)

    # ── HEADER ───────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="topbar">
      <div style="display:flex;align-items:center">
        <div class="logo">AR</div>
        <div>
          <div class="brand">AKIJ Resource</div>
          <div class="brand-sub">Production Planning KPI Intelligence</div>
        </div>
      </div>
      <div style="text-align:right">
        <div class="sbu-name">{sbu}</div>
        <div class="sbu-full">{cfg['full_name']}</div>
      </div>
    </div>""", unsafe_allow_html=True)

    if df.empty:
        st.error("No data loaded. Check that the Google Sheet is public (Share → Anyone with the link → Viewer).")
        return

    # ── FILTER ───────────────────────────────────────────────────────────────
    view = df.copy()
    if cat != "All":
        view = view[view["criteria"] == cat].reset_index(drop=True)
    view["daily"] = view["daily"].apply(
        lambda d: {k: v for k, v in d.items() if d0 <= k <= d1})

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    sc_all  = [score(r.kpi_name, r.actual) for r in view.itertuples()]
    sc_v    = [s for s in sc_all if s is not None]
    avg_sc  = np.mean(sc_v)*100 if sc_v else 0

    st.markdown(
        f"<p style='font-size:12px;color:{t['t3']};margin-bottom:12px'>"
        f"📅 {d0.strftime('%d %b %Y')} → {d1.strftime('%d %b %Y')}"
        f"  |  {len(view)} KPIs</p>", unsafe_allow_html=True)

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Overall Score", f"{avg_sc:.1f}%")
    c2.metric("KPIs Tracked",  len(view))
    c3.metric("✅ On Track",   sum(1 for s in sc_v if s >= 0.75))
    c4.metric("⚠️ At Risk",   sum(1 for s in sc_v if 0.45 <= s < 0.75))
    c5.metric("🔴 Critical",  sum(1 for s in sc_v if s < 0.45))
    st.markdown("<hr>", unsafe_allow_html=True)

    # ── SCORECARDS ───────────────────────────────────────────────────────────
    st.markdown('<div class="sec">KPI Scorecard</div>', unsafe_allow_html=True)
    COLS = 4
    for i in range(0, len(view), COLS):
        chunk = view.iloc[i:i+COLS]
        cols  = st.columns(len(chunk))
        for col, (_, r) in zip(cols, chunk.iterrows()):
            actual   = r["actual"]
            baseline = r["baseline"]
            has_act  = actual   is not None and not (isinstance(actual,   float) and np.isnan(actual))
            has_base = baseline is not None and not (isinstance(baseline, float) and np.isnan(baseline))

            sc               = score(r["kpi_name"], actual) if has_act else None
            blabel,bcol,bcls = badge(sc)
            val_str          = fmt(r["kpi_name"], actual if has_act else baseline)
            base_str         = f"Baseline: {fmt(r['kpi_name'], baseline)}" if has_base else ""
            if not has_act and has_base:
                blabel = "Ref Only"; bcls = "badge-na"
                muted  = t["t3"]
                sub    = f'<div class="kcard-base" style="color:{muted}">Baseline ref (no actual data)</div>'
            elif not has_act and not has_base:
                val_str = "—"; blabel = "No Data"; bcls = "badge-na"
                sub     = ""
            else:
                sub = f'<div class="kcard-base">{base_str}</div>' if base_str else ""

            with col:
                st.markdown(f"""
                <div class="kcard" style="border-top-color:{bcol}">
                  <div class="kcard-cat">{r['criteria'][:26]}</div>
                  <div class="kcard-val" style="color:{bcol}">{val_str}</div>
                  <div class="kcard-name">{r['kpi_name']}</div>
                  {sub}
                  <span class="kbadge {bcls}">{blabel}</span>
                </div>""", unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── TREND + RADAR ─────────────────────────────────────────────────────────
    st.markdown('<div class="sec">Trend & Category Radar</div>', unsafe_allow_html=True)
    ct, cr = st.columns([3, 2])
    kpis_w_daily = [r["kpi_name"] for _, r in view.iterrows()
                    if any(d0 <= d <= d1 for d in r["daily"])]
    with ct:
        if kpis_w_daily:
            sel_t = st.selectbox("KPI (trend)", kpis_w_daily, key="t",
                                 label_visibility="collapsed")
            st.plotly_chart(ch_trend(view, sel_t, d0, d1),
                            use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No daily data for selected range.")
    with cr:
        st.plotly_chart(ch_radar(view), use_container_width=True,
                        config={"displayModeBar": False})

    # ── BAR + DONUT ───────────────────────────────────────────────────────────
    st.markdown('<div class="sec">Baseline vs Actual & Category Distribution</div>',
                unsafe_allow_html=True)
    cb, cd = st.columns([3, 2])
    with cb:
        st.plotly_chart(ch_bar(view), use_container_width=True,
                        config={"displayModeBar": False})
    with cd:
        st.plotly_chart(ch_donut(view), use_container_width=True,
                        config={"displayModeBar": False})

    # ── HEATMAP ───────────────────────────────────────────────────────────────
    if kpis_w_daily:
        st.markdown('<div class="sec">Daily Performance Heatmap</div>',
                    unsafe_allow_html=True)
        sel_h = st.selectbox("KPI (heatmap)", kpis_w_daily, key="h",
                             label_visibility="collapsed")
        st.plotly_chart(ch_heatmap(view, sel_h, d0, d1),
                        use_container_width=True, config={"displayModeBar": False})

    # ── TABLE ─────────────────────────────────────────────────────────────────
    st.markdown('<div class="sec">KPI Detail Table</div>', unsafe_allow_html=True)
    tbody = ""
    for _, r in view.iterrows():
        actual   = r["actual"]
        baseline = r["baseline"]
        has_act  = actual   is not None and not (isinstance(actual,   float) and np.isnan(actual))
        has_base = baseline is not None and not (isinstance(baseline, float) and np.isnan(baseline))
        sc               = score(r["kpi_name"], actual) if has_act else None
        blabel,bcol,bcls = badge(sc)
        if not has_act:
            blabel = "Ref Only" if has_base else "No Data"; bcls = "badge-na"
        ccol = CRITERIA_COLORS.get(r["criteria"], t["t3"])
        act_cell = (f"<span style='color:{bcol};font-weight:600'>{fmt(r['kpi_name'], actual)}</span>"
                    if has_act else
                    f"<span style='color:{t['t3']}'>{fmt(r['kpi_name'], baseline)} <em>(ref)</em></span>"
                    if has_base else "—")
        tbody += (
            f"<tr>"
            f"<td><span style='color:{ccol};font-size:10px'>{r['criteria']}</span></td>"
            f"<td>{r['kpi_name']}</td>"
            f"<td>{fmt(r['kpi_name'], baseline) if has_base else '—'}</td>"
            f"<td>{r['target']}</td>"
            f"<td>{act_cell}</td>"
            f"<td><span class='kbadge {bcls}'>{blabel}</span></td>"
            f"</tr>"
        )
    st.markdown(
        f"<div class='tw'><table class='kt'><thead><tr>"
        f"<th>Criteria</th><th>KPI</th><th>Baseline</th>"
        f"<th>Target</th><th>Actual</th><th>Status</th>"
        f"</tr></thead><tbody>{tbody}</tbody></table></div>",
        unsafe_allow_html=True)

    st.markdown(
        f"<br><p style='text-align:center;font-size:11px;color:{t['t3']}'>"
        "AKIJ Resource · Production Planning KPI Intelligence · Google Sheets Live · v6</p>",
        unsafe_allow_html=True)


if __name__ == "__main__":
    main()
