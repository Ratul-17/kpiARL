"""
AKIJ Resource — Production Planning KPI Dashboard
app.py  v4  —  clean full rewrite
  • Dark / Light theme toggle
  • Correct % formatting (GViz CSV "11.83%" → safe_float → 0.1183 → fmt → "11.8%")
  • BDT & Hours KPIs never ×100
  • Baseline fallback cards when actual has sheet formula errors (#REF! / #DIV/0!)
  • Changeover Time baseline shown as raw minutes (not ×100)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import re
from datetime import datetime, date

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG  (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
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

# --- KPI TYPE SETS (lowercase exact names) ---

# Raw large monetary values — display as ৳ and NEVER ×100
BDT_NAMES = {
    "downtime cost (bdt)",
    "idle hours × fixed cost per hour",
}

# Raw hour values — display as "X.X hrs" and NEVER ×100
HOURS_NAMES = {
    "breakdown hours/month",
}

# These KPIs have baselines stored as raw minutes (not decimals) — show as "X.X min"
MINUTES_BASELINE = {
    "changeover time reduction (%)",
}

# Lower actual value = better performance
LOWER_IS_BETTER = {
    "reduce downtime (%)",
    "downtime cost (bdt)",
    "breakdown hours/month",
    "idle hours × fixed cost per hour",
    "production loss due to planning error (%)",
    "idle time due to material shortage (%)",
    "changeover time reduction (%)",
}

FONT = "DM Sans, sans-serif"


# ─────────────────────────────────────────────────────────────────────────────
# KPI TYPE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _n(kpi): return kpi.lower()

def is_bdt(kpi):   return _n(kpi) in BDT_NAMES
def is_hours(kpi): return _n(kpi) in HOURS_NAMES
def is_pct(kpi):   return not is_bdt(kpi) and not is_hours(kpi)


# ─────────────────────────────────────────────────────────────────────────────
# SAFE FLOAT  — handles GViz CSV "%" suffix
# ─────────────────────────────────────────────────────────────────────────────
def safe_float(v) -> "float | None":
    """
    Parse any cell value to a float in natural units.

    Handles all formats GViz CSV / pandas can send:
      "11.83%"          → 0.1183   (GViz % suffix → divide by 100)
      "226117.4444"     → 226117.4444
      "=196941*31/27"   → 226117.4444  (simple arithmetic formula → eval)
      "=IFERROR(__xludf.DUMMYFUNCTION(...),0.8299)" → 0.8299  (APFIL pattern)
      "#REF!" / "#DIV/0!" / "NaN" / "" etc → None
    """
    if v is None:
        return None
    # Handle actual float NaN passed directly
    if isinstance(v, float) and np.isnan(v):
        return None
    s = str(v).strip()
    if not s or s.lower() in {
        "", "nan", "nat", "none",
        "#ref!", "#div/0!", "#value!", "#n/a", "#name?", "#null!",
        "n/a", "-",
    }:
        return None

    # ── Excel formula strings GViz sends as-is ─────────────────────────────
    if s.startswith("="):
        # =IFERROR(__xludf.DUMMYFUNCTION("COMPUTED_VALUE"), fallback_number)
        iferr = re.search(r',\s*([-\d\.eE+]+)\s*\)\s*$', s)
        if iferr:
            try:
                return float(iferr.group(1))
            except ValueError:
                pass
        # Simple arithmetic: =196941*31/27  or  =27/30
        expr = s[1:].strip()
        if re.match(r'^[\d\s\+\-\*/\.\(\)]+$', expr):
            try:
                return float(eval(expr))   # noqa: S307 — safe: digits+operators only
            except Exception:
                pass
        return None

    has_pct = s.endswith("%")
    clean   = s.replace("%", "").replace(",", "").strip()
    try:
        num = float(clean)
    except ValueError:
        return None

    # Reject NaN/Inf that slipped through float()
    if np.isnan(num) or np.isinf(num):
        return None

    return num / 100.0 if has_pct else num


# ─────────────────────────────────────────────────────────────────────────────
# DATE PARSER
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# VALUE FORMATTING
# ─────────────────────────────────────────────────────────────────────────────
def fmt_val(kpi: str, val: "float | None") -> str:
    """
    Format a stored value for display.

    After safe_float the stored values are:
      BDT  KPIs → large raw numbers  (1 507 935)   → ৳1.51M
      Hour KPIs → raw hours          (17.3)         → 17.3 hrs
      Pct  KPIs → decimals           (0.1182)       → 11.8%
      Changeover baseline            (22.0 minutes) → 22.0 min
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
    # Changeover: if value > 2 it's raw minutes (baseline), not a decimal ratio
    if _n(kpi) in MINUTES_BASELINE and abs(val) > 2:
        return f"{val:.1f} min"
    # Standard percentage decimal
    return f"{val * 100:.1f}%"


def to_chart(kpi: str, val: "float | None") -> "float | None":
    """Convert stored value to chart-axis unit (same scale as fmt_val)."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if is_bdt(kpi):   return val / 1_000       # K BDT
    if is_hours(kpi): return val               # hrs
    if _n(kpi) in MINUTES_BASELINE and abs(val) > 2:
        return val                             # minutes
    return val * 100                           # %


def axis_unit(kpi: str) -> str:
    if is_bdt(kpi):   return "K BDT"
    if is_hours(kpi): return "hrs"
    if _n(kpi) in MINUTES_BASELINE: return "min / %"
    return "%"


# ─────────────────────────────────────────────────────────────────────────────
# SCORING & STATUS BADGE
# ─────────────────────────────────────────────────────────────────────────────
def score_kpi(kpi: str, val: "float | None") -> "float | None":
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    lower = _n(kpi) in LOWER_IS_BETTER
    if is_bdt(kpi):
        return max(0.0, 1.0 - min(1.0, abs(val) / 5_000_000))
    if is_hours(kpi):
        return max(0.0, 1.0 - min(1.0, abs(val) / 100.0))
    if lower:
        return max(0.0, 1.0 - min(1.0, abs(val)))
    return min(1.0, max(0.0, val))


def make_badge(sc: "float | None"):
    """Returns (label, hex_color, css_class)"""
    if sc is None:   return "N/A",      "#8892ab", "badge-na"
    if sc >= 0.75:   return "On Track", "#22d3a5", "badge-good"
    if sc >= 0.45:   return "At Risk",  "#f59e0b", "badge-warn"
    return "Critical", "#ef4444", "badge-bad"


# ─────────────────────────────────────────────────────────────────────────────
# THEME SYSTEM
# ─────────────────────────────────────────────────────────────────────────────
THEMES = {
    "🌙 Dark": {
        "bg_page":      "#0d0f14",
        "bg_card":      "#13161f",
        "bg_sidebar":   "#13161f",
        "bg_input":     "#1c2030",
        "bg_tbl_head":  "#1c2030",
        "bg_row_hover": "#1a1f2e",
        "border":       "rgba(255,255,255,0.06)",
        "border_input": "rgba(255,255,255,0.12)",
        "border_hover": "rgba(255,255,255,0.12)",
        "text_primary": "#f0f2f8",
        "text_sec":     "#8892ab",
        "text_muted":   "#4e5870",
        "sidebar_txt":  "#f0f2f8",
        "topbar":       "linear-gradient(135deg,#13161f,#1a1f2e)",
        "hr":           "rgba(255,255,255,0.06)",
        "scrollbar":    "rgba(255,255,255,0.10)",
        "metric_bg":    "#13161f",
        "metric_bdr":   "rgba(255,255,255,0.06)",
        "chart_bg":     "#13161f",
        "chart_grid":   "rgba(255,255,255,0.06)",
        "chart_tick":   "#8892ab",
        "legend_bg":    "rgba(0,0,0,0)",
    },
    "☀️ Light": {
        "bg_page":      "#f4f6fc",
        "bg_card":      "#ffffff",
        "bg_sidebar":   "#ffffff",
        "bg_input":     "#f0f2f9",
        "bg_tbl_head":  "#f0f2f9",
        "bg_row_hover": "#f8f9ff",
        "border":       "rgba(0,0,0,0.07)",
        "border_input": "rgba(0,0,0,0.14)",
        "border_hover": "rgba(79,143,255,0.35)",
        "text_primary": "#1a1f36",
        "text_sec":     "#4a5068",
        "text_muted":   "#8892ab",
        "sidebar_txt":  "#1a1f36",
        "topbar":       "linear-gradient(135deg,#ffffff,#f0f4ff)",
        "hr":           "rgba(0,0,0,0.08)",
        "scrollbar":    "rgba(0,0,0,0.15)",
        "metric_bg":    "#ffffff",
        "metric_bdr":   "rgba(0,0,0,0.07)",
        "chart_bg":     "#ffffff",
        "chart_grid":   "rgba(0,0,0,0.07)",
        "chart_tick":   "#4a5068",
        "legend_bg":    "rgba(255,255,255,0)",
    },
}


def T() -> dict:
    return THEMES[st.session_state.get("theme", "🌙 Dark")]


def build_css(t: dict) -> str:
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');
html,body,[class*="css"]{{font-family:'DM Sans',sans-serif}}
.stApp{{background:{t["bg_page"]}!important}}
section[data-testid="stSidebar"]{{background:{t["bg_sidebar"]}!important;border-right:1px solid {t["border"]}}}
section[data-testid="stSidebar"] *{{color:{t["sidebar_txt"]}!important}}
section[data-testid="stSidebar"] .stSelectbox>div>div{{background:{t["bg_input"]};border:1px solid {t["border_input"]}}}
header[data-testid="stHeader"]{{background:transparent}}
.top-bar{{background:{t["topbar"]};border:1px solid {t["border"]};border-radius:16px;padding:20px 28px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between}}
.brand-logo{{width:44px;height:44px;background:linear-gradient(135deg,#4F8FFF,#00E5B8);border-radius:12px;display:flex;align-items:center;justify-content:center;font-family:'Syne',sans-serif;font-weight:800;color:#fff;font-size:15px;box-shadow:0 0 20px #4F8FFF33;float:left;margin-right:14px}}
.brand-title{{font-family:'Syne',sans-serif;font-weight:700;font-size:18px;color:{t["text_primary"]}}}
.brand-sub{{font-size:11px;color:{t["text_muted"]};text-transform:uppercase;letter-spacing:.8px}}
.sbu-name{{font-family:'Syne',sans-serif;font-weight:800;font-size:28px;background:linear-gradient(90deg,#4F8FFF,#00E5B8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sbu-full{{font-size:12px;color:{t["text_muted"]};margin-top:2px}}
.kpi-card{{background:{t["bg_card"]};border:1px solid {t["border"]};border-radius:14px;padding:18px 18px 14px;border-top:3px solid;min-height:148px;transition:border-color .15s}}
.kpi-card:hover{{border-color:{t["border_hover"]}}}
.kpi-card-cat{{font-size:10px;color:{t["text_muted"]};text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}}
.kpi-card-val{{font-family:'Syne',sans-serif;font-weight:700;font-size:26px;line-height:1;margin-bottom:5px}}
.kpi-card-name{{font-size:11.5px;color:{t["text_sec"]};margin-bottom:3px;line-height:1.3}}
.kpi-card-sub{{font-size:10px;color:{t["text_muted"]};margin-bottom:6px;font-style:italic}}
.kpi-badge{{display:inline-block;padding:2px 10px;border-radius:99px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.4px}}
.badge-good{{background:#22d3a520;color:#22d3a5}}
.badge-warn{{background:#f59e0b20;color:#f59e0b}}
.badge-bad{{background:#ef444420;color:#ef4444}}
.badge-na{{background:{t["border"]};color:{t["text_muted"]}}}
.sec-title{{font-family:'Syne',sans-serif;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:{t["text_muted"]};margin:24px 0 12px 0}}
[data-testid="stMetric"]{{background:{t["metric_bg"]};border:1px solid {t["metric_bdr"]};border-radius:12px;padding:14px}}
[data-testid="stMetricValue"]{{font-family:'Syne',sans-serif!important;color:{t["text_primary"]}!important}}
[data-testid="stMetricLabel"]{{font-size:11px!important;color:{t["text_muted"]}!important}}
hr{{border-color:{t["hr"]}!important}}
::-webkit-scrollbar{{width:5px;height:5px}}
::-webkit-scrollbar-track{{background:transparent}}
::-webkit-scrollbar-thumb{{background:{t["scrollbar"]};border-radius:99px}}
.kpi-table-wrap{{overflow-x:auto}}
table.kpi-tbl{{width:100%;border-collapse:collapse;font-size:12.5px}}
table.kpi-tbl th{{background:{t["bg_tbl_head"]};color:{t["text_muted"]};padding:10px 14px;text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid {t["border"]}}}
table.kpi-tbl td{{padding:10px 14px;border-bottom:1px solid {t["border"]};color:{t["text_sec"]}}}
table.kpi-tbl td:nth-child(2){{color:{t["text_primary"]};font-weight:500}}
table.kpi-tbl tr:hover td{{background:{t["bg_row_hover"]}}}
</style>"""


# ─────────────────────────────────────────────────────────────────────────────
# CHART BASE (theme-aware)
# ─────────────────────────────────────────────────────────────────────────────
def _base(h=300):
    t = T()
    return dict(
        paper_bgcolor=t["chart_bg"], plot_bgcolor=t["chart_bg"],
        font=dict(family=FONT, color=t["chart_tick"], size=11),
        height=h, margin=dict(l=10, r=10, t=36, b=10),
        legend=dict(bgcolor=t["legend_bg"], font=dict(size=11, color=t["chart_tick"])),
        xaxis=dict(gridcolor=t["chart_grid"], color=t["chart_tick"], showline=False),
        yaxis=dict(gridcolor=t["chart_grid"], color=t["chart_tick"], showline=False),
    )


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def load_raw(sheet_id: str, sheet_name: str) -> pd.DataFrame:
    """Pull sheet as all-string CSV (preserves '11.83%' suffix from GViz)."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        info = st.secrets.get("gcp_service_account", None)
        if info:
            creds = Credentials.from_service_account_info(
                info,
                scopes=["https://spreadsheets.google.com/feeds",
                        "https://www.googleapis.com/auth/drive"],
            )
            gc = gspread.authorize(creds)
            rows = gc.open_by_key(sheet_id).worksheet(sheet_name).get_all_values()
            return pd.DataFrame(rows)
    except Exception:
        pass
    try:
        url = (f"https://docs.google.com/spreadsheets/d/{sheet_id}"
               f"/gviz/tq?tqx=out:csv&sheet={sheet_name.replace(' ', '%20')}")
        return pd.read_csv(url, header=None, dtype=str)
    except Exception as e:
        st.error(f"Cannot load '{sheet_name}': {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# PARSE SHEET INTO KPI DATAFRAME
# ─────────────────────────────────────────────────────────────────────────────
def parse_df(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Row 0  = header: Criteria | KPI | Formula | Baseline | Target | Actual | date…
    Rows 1+= data rows (one KPI per row).
    Returns dataframe with columns:
      criteria, kpi_name, baseline, target, actual, daily (dict{date: float})
    """
    if raw.empty or len(raw) < 2:
        return pd.DataFrame()

    header = raw.iloc[0]

    # Build date-column map: {col_index: date}
    date_cols: dict = {}
    for c in range(6, len(raw.columns)):
        d = parse_date(str(header.iloc[c]) if c < len(header) else "")
        if d:
            date_cols[c] = d

    records = []
    for ri in range(1, len(raw)):
        row = raw.iloc[ri]

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
            criteria=criteria,
            kpi_name=kpi_name,
            baseline=baseline,
            target=target,
            actual=actual,
            daily=daily,
        ))

    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# CHARTS
# ─────────────────────────────────────────────────────────────────────────────
def chart_trend(df, kpi, d0, d1):
    t   = T()
    row = df[df["kpi_name"] == kpi]
    if row.empty: return go.Figure()
    row = row.iloc[0]
    pts = sorted([(d, v) for d, v in row["daily"].items() if d0 <= d <= d1])
    if not pts: return go.Figure()
    u   = axis_unit(kpi)
    xs  = [p[0] for p in pts]
    ys  = [to_chart(kpi, p[1]) for p in pts]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers", name=kpi,
        line=dict(color="#4F8FFF", width=2.5),
        marker=dict(size=5, color="#4F8FFF"),
        fill="tozeroy", fillcolor="rgba(79,143,255,0.10)",
        hovertemplate=f"%{{x}}: %{{y:.2f}} {u}<extra></extra>",
    ))
    bv = to_chart(kpi, row["baseline"])
    if bv is not None:
        fig.add_hline(y=bv, line_dash="dot", line_color="#FF6B6B", line_width=1.5,
                      annotation_text=f"Baseline {bv:.2f} {u}",
                      annotation_font=dict(color="#FF6B6B", size=10))
    lay = _base(300)
    lay["title"] = dict(text=kpi[:60], font=dict(size=12, color=t["chart_tick"]))
    lay["yaxis"]["ticksuffix"] = f" {u}"
    fig.update_layout(**lay)
    return fig


def chart_radar(df):
    t   = T()
    grp: dict = {}
    for _, r in df.iterrows():
        s = score_kpi(r["kpi_name"], r["actual"])
        if s is not None:
            grp.setdefault(r["criteria"], []).append(s * 100)
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
        polar=dict(
            bgcolor=t["chart_bg"],
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=t["chart_grid"],
                            tickfont=dict(size=9, color=t["chart_tick"]), ticksuffix="%"),
            angularaxis=dict(color=t["chart_tick"], gridcolor=t["chart_grid"],
                             tickfont=dict(size=10, color=t["chart_tick"])),
        ),
        paper_bgcolor=t["chart_bg"],
        font=dict(family=FONT, color=t["chart_tick"]),
        height=300, margin=dict(l=20, r=20, t=30, b=20), showlegend=False,
    )
    return fig


def chart_bar(df):
    t    = T()
    rows = df[df["actual"].notna()].copy()
    if rows.empty: return go.Figure()
    labs  = [k[:38] for k in rows["kpi_name"]]
    act   = [to_chart(r["kpi_name"], r["actual"])   for _, r in rows.iterrows()]
    base  = [to_chart(r["kpi_name"], r["baseline"]) for _, r in rows.iterrows()]
    fig   = go.Figure()
    if any(b is not None for b in base):
        fig.add_trace(go.Bar(y=labs, x=base, name="Baseline", orientation="h",
                             marker_color="rgba(79,143,255,0.45)",
                             marker_line=dict(color="#4F8FFF", width=1)))
    fig.add_trace(go.Bar(y=labs, x=act, name="Actual", orientation="h",
                         marker_color="rgba(0,229,184,0.45)",
                         marker_line=dict(color="#00E5B8", width=1)))
    h = max(300, len(rows) * 30)
    fig.update_layout(
        barmode="group",
        paper_bgcolor=t["chart_bg"], plot_bgcolor=t["chart_bg"],
        font=dict(family=FONT, color=t["chart_tick"], size=11), height=h,
        margin=dict(l=10, r=20, t=36, b=10),
        legend=dict(bgcolor=t["legend_bg"], font=dict(color=t["chart_tick"])),
        xaxis=dict(gridcolor=t["chart_grid"], color=t["chart_tick"]),
        yaxis=dict(gridcolor=t["chart_grid"], color=t["chart_tick"],
                   automargin=True, tickfont=dict(size=10)),
        title=dict(text="Baseline vs Actual", font=dict(size=12, color=t["chart_tick"])),
    )
    return fig


def chart_heatmap(df, kpi, d0, d1):
    t   = T()
    row = df[df["kpi_name"] == kpi]
    if row.empty: return go.Figure()
    row = row.iloc[0]
    pts = sorted([(d, v) for d, v in row["daily"].items() if d0 <= d <= d1])
    if not pts: return go.Figure()
    u   = axis_unit(kpi)
    fig = go.Figure(go.Heatmap(
        x=[str(p[0]) for p in pts],
        y=[kpi[:30]],
        z=[[to_chart(kpi, p[1]) for p in pts]],
        colorscale=[[0, "#ef4444"], [0.5, "#f59e0b"], [1, "#22d3a5"]],
        hovertemplate=f"%{{x}}: %{{z:.2f}} {u}<extra></extra>",
        showscale=True,
        colorbar=dict(tickfont=dict(color=t["chart_tick"], size=10),
                      outlinewidth=0, bgcolor=t["chart_bg"]),
    ))
    fig.update_layout(
        paper_bgcolor=t["chart_bg"], plot_bgcolor=t["chart_bg"],
        font=dict(family=FONT, color=t["chart_tick"], size=11),
        height=130, margin=dict(l=10, r=10, t=10, b=50),
        xaxis=dict(color=t["chart_tick"], tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(color=t["chart_tick"], tickfont=dict(size=9)),
    )
    return fig


def chart_donut(df):
    t    = T()
    grp: dict = {}
    for _, r in df.iterrows():
        s = score_kpi(r["kpi_name"], r["actual"])
        if s is not None:
            grp.setdefault(r["criteria"], []).append(s * 100)
    if not grp: return go.Figure()
    labs   = list(grp.keys())
    vals   = [float(np.mean(v)) for v in grp.values()]
    colors = [CRITERIA_COLORS.get(l, "#8892ab") for l in labs]
    fig = go.Figure(go.Pie(
        labels=[l.split(" & ")[0] for l in labs], values=vals, hole=0.65,
        marker=dict(colors=[c + "aa" for c in colors],
                    line=dict(color=colors, width=2)),
        textfont=dict(size=11, color=t["text_primary"]),
        hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=t["chart_bg"],
        font=dict(family=FONT, color=t["chart_tick"], size=11),
        height=280, margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(bgcolor=t["legend_bg"], font=dict(size=10, color=t["chart_tick"])),
        annotations=[dict(text="Score", x=0.5, y=0.5,
                          font=dict(size=13, color=t["text_muted"]), showarrow=False)],
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    # Init session state
    if "theme" not in st.session_state:
        st.session_state["theme"] = "🌙 Dark"

    # Inject CSS (must happen before any widget render)
    st.markdown(build_css(T()), unsafe_allow_html=True)

    # ── SIDEBAR ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🏭 AKIJ Resource")
        st.markdown("---")

        # Theme toggle
        st.markdown("**Appearance**")
        chosen = st.radio(
            "Theme", list(THEMES.keys()),
            index=list(THEMES.keys()).index(st.session_state["theme"]),
            horizontal=True, label_visibility="collapsed",
        )
        if chosen != st.session_state["theme"]:
            st.session_state["theme"] = chosen
            st.rerun()

        st.markdown("---")
        st.markdown("**Select SBU**")
        sbu = st.selectbox(
            "SBU", list(SBU_CONFIG.keys()),
            format_func=lambda k: f"{k}  —  {SBU_CONFIG[k]['full_name'][:28]}",
            label_visibility="collapsed",
        )
        cfg   = SBU_CONFIG[sbu]
        sname = cfg["sheet"]

        st.markdown("---")
        st.markdown("**Date Range**")
        with st.spinner("Loading…"):
            raw = load_raw(SHEET_ID, sname)
        df = parse_df(raw)

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
            f"<p style='font-size:10px;color:{t['text_muted']};text-align:center;margin-top:16px'>"
            "AKIJ Resource · Production Planning<br>KPI Intelligence · Live Google Sheets</p>",
            unsafe_allow_html=True,
        )

    # Re-fetch theme after sidebar interactions
    t = T()
    st.markdown(build_css(t), unsafe_allow_html=True)

    # ── HEADER ───────────────────────────────────────────────────────────────
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
        <div class="sbu-name">{sbu}</div>
        <div class="sbu-full">{cfg['full_name']}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if df.empty:
        st.warning("⚠️ No data loaded. Make sheet public: Share → Anyone with link → Viewer.")
        return

    # ── FILTER ───────────────────────────────────────────────────────────────
    view = df.copy()
    if cat != "All":
        view = view[view["criteria"] == cat].reset_index(drop=True)
    view["daily"] = view["daily"].apply(
        lambda d: {k: v for k, v in d.items() if d0 <= k <= d1}
    )

    # ── SUMMARY METRICS ──────────────────────────────────────────────────────
    scores_all  = [score_kpi(r.kpi_name, r.actual) for r in view.itertuples()]
    valid_sc    = [s for s in scores_all if s is not None]
    avg_sc      = np.mean(valid_sc) * 100 if valid_sc else 0
    no_data_cnt = sum(1 for r in view.itertuples()
                      if r.actual is None or (isinstance(r.actual, float) and np.isnan(r.actual)))

    st.markdown(
        f"<p style='font-size:12px;color:{t['text_muted']};margin-bottom:12px'>"
        f"📅 {d0.strftime('%d %b %Y')} → {d1.strftime('%d %b %Y')}"
        f"  &nbsp;|&nbsp;  {len(view)} KPIs tracked</p>",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Overall Score", f"{avg_sc:.1f}%")
    c2.metric("KPIs Tracked",  len(view))
    c3.metric("✅ On Track",   sum(1 for s in valid_sc if s >= 0.75))
    c4.metric("⚠️ At Risk",   sum(1 for s in valid_sc if 0.45 <= s < 0.75))
    c5.metric("🔴 Critical",  sum(1 for s in valid_sc if s < 0.45))
    st.markdown("<hr>", unsafe_allow_html=True)

    # ── KPI SCORECARD ────────────────────────────────────────────────────────
    st.markdown('<div class="sec-title">KPI Scorecard</div>', unsafe_allow_html=True)

    if no_data_cnt > 0:
        st.markdown(
            f"<p style='font-size:11.5px;color:{t['text_muted']};margin:-4px 0 12px;'>"
            f"ℹ️  <b>{no_data_cnt} KPI(s)</b> have no Actual data (sheet formula errors — "
            f"#REF! / #DIV/0!). Baseline values are shown instead for reference.</p>",
            unsafe_allow_html=True,
        )

    COLS = 4
    for i in range(0, len(view), COLS):
        chunk = view.iloc[i:i + COLS]
        cols  = st.columns(len(chunk))
        for col, (_, r) in zip(cols, chunk.iterrows()):
            actual   = r["actual"]
            baseline = r["baseline"]
            has_act  = (actual is not None
                        and not (isinstance(actual, float) and np.isnan(actual)))
            has_base = (baseline is not None
                        and not (isinstance(baseline, float) and np.isnan(baseline)))

            if has_act:
                # ── Normal card: show actual value ────────────────────────
                sc                   = score_kpi(r["kpi_name"], actual)
                blabel, bcol, bcls   = make_badge(sc)
                val_str              = fmt_val(r["kpi_name"], actual)
                base_str             = fmt_val(r["kpi_name"], baseline) if has_base else "—"
                sub_html             = (f'<div class="kpi-card-sub">'
                                        f'Baseline: {base_str}</div>')
            elif has_base:
                # ── Fallback card: show baseline, label as reference ──────
                blabel = "No Actual"
                bcol   = t["text_sec"]
                bcls   = "badge-na"
                val_str  = fmt_val(r["kpi_name"], baseline)
                muted    = t["text_muted"]
                sub_html = (f'<div class="kpi-card-sub" style="color:{muted}">'
                             f'Baseline ref &mdash; sheet error on Actual</div>')
            else:
                # ── Empty card: no data at all ────────────────────────────
                blabel   = "No Data"
                bcol     = t["text_muted"]
                bcls     = "badge-na"
                val_str  = "—"
                muted2   = t["text_muted"]
                sub_html = (f'<div class="kpi-card-sub" style="color:{muted2}">'
                             f'No data in sheet</div>')

            with col:
                st.markdown(f"""
                <div class="kpi-card" style="border-top-color:{bcol}">
                  <div class="kpi-card-cat">{r['criteria'][:26]}</div>
                  <div class="kpi-card-val" style="color:{bcol}">{val_str}</div>
                  <div class="kpi-card-name">{r['kpi_name']}</div>
                  {sub_html}
                  <span class="kpi-badge {bcls}">{blabel}</span>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── TREND + RADAR ─────────────────────────────────────────────────────────
    st.markdown('<div class="sec-title">Trend & Category Radar</div>', unsafe_allow_html=True)
    ct, cr = st.columns([3, 2])
    kpis_with_daily = [
        r["kpi_name"] for _, r in view.iterrows()
        if any(d0 <= d <= d1 for d in r["daily"])
    ]
    with ct:
        if kpis_with_daily:
            sel_t = st.selectbox("KPI (trend)", kpis_with_daily, key="t",
                                 label_visibility="collapsed")
            st.plotly_chart(chart_trend(view, sel_t, d0, d1),
                            use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No daily data available for selected range.")
    with cr:
        st.plotly_chart(chart_radar(view), use_container_width=True,
                        config={"displayModeBar": False})

    # ── BAR + DONUT ───────────────────────────────────────────────────────────
    st.markdown('<div class="sec-title">Baseline vs Actual & Category Distribution</div>',
                unsafe_allow_html=True)
    cb, cd = st.columns([3, 2])
    with cb:
        st.plotly_chart(chart_bar(view), use_container_width=True,
                        config={"displayModeBar": False})
    with cd:
        st.plotly_chart(chart_donut(view), use_container_width=True,
                        config={"displayModeBar": False})

    # ── HEATMAP ───────────────────────────────────────────────────────────────
    if kpis_with_daily:
        st.markdown('<div class="sec-title">Daily Performance Heatmap</div>',
                    unsafe_allow_html=True)
        sel_h = st.selectbox("KPI (heatmap)", kpis_with_daily, key="h",
                             label_visibility="collapsed")
        st.plotly_chart(chart_heatmap(view, sel_h, d0, d1),
                        use_container_width=True, config={"displayModeBar": False})

    # ── DETAIL TABLE ──────────────────────────────────────────────────────────
    st.markdown('<div class="sec-title">KPI Detail Table</div>', unsafe_allow_html=True)
    tbody = ""
    for _, r in view.iterrows():
        actual   = r["actual"]
        baseline = r["baseline"]
        has_act  = (actual is not None
                    and not (isinstance(actual, float) and np.isnan(actual)))
        has_base = (baseline is not None
                    and not (isinstance(baseline, float) and np.isnan(baseline)))

        sc                 = score_kpi(r["kpi_name"], actual) if has_act else None
        blabel, bcol, bcls = make_badge(sc)
        ccol               = CRITERIA_COLORS.get(r["criteria"], t["text_muted"])

        if has_act:
            act_cell = (f"<span style='color:{bcol};font-weight:600'>"
                        f"{fmt_val(r['kpi_name'], actual)}</span>")
        elif has_base:
            act_cell = (f"<span style='color:{t['text_muted']};font-size:11px'>"
                        f"{fmt_val(r['kpi_name'], baseline)}"
                        f" <em>(baseline — sheet error)</em></span>")
            blabel = "No Actual"; bcls = "badge-na"
        else:
            act_cell = f"<span style='color:{t['text_muted']}'>—</span>"
            blabel = "No Data"; bcls = "badge-na"

        tbody += (
            f"<tr>"
            f"<td><span style='color:{ccol};font-size:10px'>{r['criteria']}</span></td>"
            f"<td>{r['kpi_name']}</td>"
            f"<td>{fmt_val(r['kpi_name'], baseline) if has_base else '—'}</td>"
            f"<td>{r['target']}</td>"
            f"<td>{act_cell}</td>"
            f"<td><span class='kpi-badge {bcls}'>{blabel}</span></td>"
            f"</tr>"
        )

    st.markdown(
        f"<div class='kpi-table-wrap'><table class='kpi-tbl'>"
        f"<thead><tr><th>Criteria</th><th>KPI</th><th>Baseline</th>"
        f"<th>Target</th><th>Actual</th><th>Status</th></tr></thead>"
        f"<tbody>{tbody}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<br><p style='text-align:center;font-size:11px;color:{t['text_muted']}'>"
        "AKIJ Resource · Production Planning KPI Intelligence. Created by : Md. Ariful Islam (MTO - Operations) .</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
