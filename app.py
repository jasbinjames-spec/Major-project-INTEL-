import gradio as gr
import plotly.graph_objects as go
import sqlite3
from datetime import datetime

# -----------------------------------------
#  DATABASE
# -----------------------------------------
DB_PATH = "risk_history.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            name TEXT, age INTEGER, gender TEXT,
            institution TEXT, living TEXT,
            sleep_hours REAL, sleep_quality INTEGER, nap_freq INTEGER,
            attendance REAL, study_hours REAL,
            screen_time REAL, gaming_hrs REAL,
            score_sleep INTEGER, score_academic INTEGER,
            score_digital INTEGER, score_overall INTEGER,
            risk_label TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()


def db_save(name, age, gender, institution, living,
            sleep_hours, sleep_quality, nap_freq,
            attendance, study_hours, screen_time, gaming_hrs, scores):
    lbl, _ = risk_label(scores["Overall"])
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO assessments
        (timestamp,name,age,gender,institution,living,
         sleep_hours,sleep_quality,nap_freq,attendance,study_hours,
         screen_time,gaming_hrs,score_sleep,score_academic,
         score_digital,score_overall,risk_label)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        str(name), int(age), str(gender), str(institution), str(living),
        float(sleep_hours), int(sleep_quality), int(nap_freq),
        float(attendance), float(study_hours),
        float(screen_time), float(gaming_hrs),
        scores["Sleep Health"], scores["Academic"], scores["Digital"],
        scores["Overall"], lbl
    ))
    conn.commit()
    conn.close()


def db_user_history(name):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT timestamp, score_sleep, score_academic, score_digital,
               score_overall, risk_label,
               sleep_hours, study_hours, screen_time, gaming_hrs, attendance
        FROM assessments
        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
        ORDER BY timestamp DESC LIMIT 20
    """, (str(name),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_all_history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM assessments ORDER BY timestamp DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), AVG(score_overall), MAX(score_overall), MIN(score_overall) FROM assessments")
    total, avg, hi, lo = c.fetchone()
    c.execute("SELECT risk_label, COUNT(*) FROM assessments GROUP BY risk_label")
    label_counts = dict(c.fetchall())
    conn.close()
    return total or 0, avg or 0, hi or 0, lo or 0, label_counts


# -----------------------------------------
#  RISK ENGINE
# -----------------------------------------
def calculate_risk(sleep_hours, sleep_quality, nap_freq,
                   attendance, study_hours, screen_time, gaming_hrs):
    scores = {}

    s = 0
    if sleep_hours < 5:    s += 35
    elif sleep_hours < 6:  s += 22
    elif sleep_hours < 7:  s += 12
    elif sleep_hours > 10: s += 8
    s += (10 - sleep_quality) * 3
    s += max(0, nap_freq - 3) * 3
    scores["Sleep Health"] = min(100, s)

    a = 0
    if attendance < 60:   a += 25
    elif attendance < 75: a += 14
    elif attendance < 85: a += 6
    if study_hours < 1:   a += 18
    elif study_hours < 2: a += 10
    elif study_hours < 3: a += 5
    scores["Academic"] = min(100, a)

    d = 0
    if screen_time > 12:  d += 25
    elif screen_time > 9: d += 15
    elif screen_time > 7: d += 8
    elif screen_time > 5: d += 3
    d += gaming_hrs * 2
    scores["Digital"] = min(100, max(0, d))

    total = sleep_hours + study_hours + screen_time
    if total > 24:
        bump = (total - 24) * 2
        for k in scores:
            scores[k] = min(100, scores[k] + bump)

    weights = {"Sleep Health": 0.35, "Academic": 0.35, "Digital": 0.30}
    scores["Overall"] = round(sum(scores[k] * weights[k] for k in scores))
    return scores


def risk_label(score):
    if score < 25: return "Low Risk",  "#1D9E75"
    if score < 50: return "Moderate",  "#BA7517"
    if score < 72: return "High Risk", "#D85A30"
    return               "Critical",  "#E24B4A"


# -----------------------------------------
#  CHARTS
# -----------------------------------------
def make_gauge(score):
    label, color = risk_label(score)
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score,
        title={'text': label, 'font': {'size': 16}},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': color},
            'steps': [
                {'range': [0,  25], 'color': '#E1F5EE'},
                {'range': [25, 50], 'color': '#FAEEDA'},
                {'range': [50, 72], 'color': '#FAECE7'},
                {'range': [72,100], 'color': '#FCEBEB'},
            ],
            'threshold': {'line': {'color': color, 'width': 4}, 'thickness': 0.8, 'value': score}
        },
        number={'suffix': '/100', 'font': {'size': 28, 'color': color}}
    ))
    fig.update_layout(margin=dict(t=50, b=20, l=30, r=30), height=250,
                      paper_bgcolor='white', font=dict(family='sans-serif'))
    return fig


def make_radar(scores):
    cats = ["Sleep Health", "Academic", "Digital"]
    vals = [scores[c] for c in cats] + [scores[cats[0]]]
    cc   = cats + [cats[0]]
    fig  = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals, theta=cc, fill='toself',
        fillcolor='rgba(83,74,183,0.18)',
        line=dict(color='#534AB7', width=2.5), name='Your Risk'))
    fig.add_trace(go.Scatterpolar(
        r=[35] * len(cc), theta=cc, fill='toself',
        fillcolor='rgba(29,158,117,0.10)',
        line=dict(color='#1D9E75', width=1.5, dash='dot'), name='Healthy'))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=True, margin=dict(t=30, b=30, l=30, r=30),
        paper_bgcolor='white', plot_bgcolor='white',
        font=dict(family='sans-serif', size=12),
        legend=dict(orientation='h', y=-0.15))
    return fig


def make_bars(scores):
    cats = ["Sleep Health", "Academic", "Digital"]
    vals = [scores[c] for c in cats]
    clrs = ['#1D9E75' if v < 35 else '#BA7517' if v < 65 else '#E24B4A' for v in vals]
    fig  = go.Figure(go.Bar(
        x=vals, y=cats, orientation='h',
        marker_color=clrs,
        text=[str(v) for v in vals],
        textposition='outside'))
    fig.update_layout(
        xaxis=dict(range=[0, 115], showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(autorange='reversed'),
        margin=dict(t=10, b=10, l=10, r=40), height=200,
        paper_bgcolor='white', plot_bgcolor='white',
        font=dict(family='sans-serif', size=13))
    return fig


def make_pie(sleep_hours, study_hours, screen_time, gaming_hrs):
    other  = max(0, 24 - sleep_hours - study_hours - screen_time)
    fig    = go.Figure(go.Pie(
        labels=['Sleep', 'Study', 'Screen', 'Other'],
        values=[sleep_hours, study_hours, screen_time, other],
        marker=dict(colors=['#534AB7', '#1D9E75', '#D85A30', '#CCCCCC']),
        hole=0.45, textinfo='label+percent', textfont=dict(size=11)))
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10), height=250,
        paper_bgcolor='white', showlegend=False,
        annotations=[dict(text='24h', x=0.5, y=0.5, font_size=14, showarrow=False)])
    return fig


def make_trend_chart(history):
    if not history:
        fig = go.Figure()
        fig.update_layout(paper_bgcolor='white',
                          annotations=[dict(text='No history yet', x=0.5, y=0.5,
                                           showarrow=False, font=dict(size=14, color='#aaa'))])
        return fig
    dates  = [r["timestamp"][:10] for r in reversed(history)]
    vals   = [r["score_overall"] for r in reversed(history)]
    fig    = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=vals, mode='lines+markers',
        line=dict(color='#534AB7', width=2.5),
        marker=dict(size=8, color='#534AB7')))
    fig.add_hline(y=25, line_dash='dot', line_color='#1D9E75', annotation_text='Low')
    fig.add_hline(y=50, line_dash='dot', line_color='#BA7517', annotation_text='Moderate')
    fig.add_hline(y=72, line_dash='dot', line_color='#E24B4A', annotation_text='High')
    fig.update_layout(
        xaxis_title='Date', yaxis_title='Risk Score',
        yaxis=dict(range=[0, 100]),
        margin=dict(t=20, b=40, l=40, r=20), height=280,
        paper_bgcolor='white', plot_bgcolor='white',
        font=dict(family='sans-serif', size=12))
    return fig


def make_admin_bar(label_counts):
    if not label_counts:
        return go.Figure()
    clr_map = {"Low Risk": "#1D9E75", "Moderate": "#BA7517",
               "High Risk": "#D85A30", "Critical": "#E24B4A"}
    labels = list(label_counts.keys())
    values = list(label_counts.values())
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=[clr_map.get(l, "#999") for l in labels],
        text=values, textposition='outside'))
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10), height=220,
        paper_bgcolor='white', plot_bgcolor='white',
        font=dict(family='sans-serif', size=13))
    return fig


# -----------------------------------------
#  RECOMMENDATIONS
# -----------------------------------------
def generate_recommendations(scores, sleep_hours, screen_time,
                              attendance, sleep_quality, study_hours, gaming_hrs):
    recs  = []
    total = sleep_hours + study_hours + screen_time
    if total > 24:
        recs.append(("URGENT", "Impossible Daily Schedule",
            f"Sleep ({sleep_hours}h) + Study ({study_hours}h) + Screen ({screen_time}h) = {total}h exceeds 24h. Audit your time."))
    if sleep_hours < 7:
        recs.append(("URGENT", "Sleep Deficit",
            f"Sleeping {sleep_hours}h — {round(7-sleep_hours,1)}h below minimum. Set a fixed bedtime, avoid screens 45min before sleep."))
    if sleep_quality < 5:
        recs.append(("URGENT", "Poor Sleep Quality",
            f"Quality {sleep_quality}/10 is critically low. Try white noise, cooler room, consistent pre-sleep routine."))
    if screen_time > 9:
        recs.append(("HIGH", "Screen Time Overload",
            f"{screen_time}h/day is too high. Use grayscale after 8pm, set app timers, 5-min break every 45min."))
    if gaming_hrs > 4:
        recs.append(("HIGH", "Excessive Gaming",
            f"{gaming_hrs}h/day gaming. Cap at 1-2h, evenings only."))
    if attendance < 75:
        recs.append(("URGENT", "Critical Attendance",
            f"{attendance}% attendance puts you at risk. Talk to your mentor and find root causes."))
    if not recs:
        recs.append(("GOOD", "Healthy Patterns",
            "Great balance! Keep doing weekly check-ins and watch habits during exam season."))
    return recs


# -----------------------------------------
#  HTML RENDERERS
# -----------------------------------------
def render_summary(name, age, gender, institution, sleep_hours,
                   study_hours, screen_time, gaming_hrs, scores):
    domain_cards = ""
    for k, v in scores.items():
        if k == "Overall": continue
        c = "#1D9E75" if v < 35 else "#BA7517" if v < 65 else "#E24B4A"
        domain_cards += (
            f'<div style="background:white;border-radius:10px;padding:10px 16px;'
            f'border:1px solid #eee;min-width:120px">'
            f'<div style="font-size:11px;color:#999;margin-bottom:2px">{k}</div>'
            f'<div style="font-size:20px;font-weight:700;color:{c}">{v}</div></div>'
        )
    total_hrs = sleep_hours + study_hours + screen_time
    warn = ""
    if total_hrs > 24:
        warn = (f'<div style="background:#fce8e8;border-radius:8px;padding:8px 14px;'
                f'margin-top:10px;font-size:13px;color:#c0392b">'
                f' Sleep + Study + Screen = <b>{total_hrs}h</b> — exceeds 24h!</div>')
    lbl, clr = risk_label(scores["Overall"])
    return f"""
    <div style="font-family:sans-serif;padding:20px 24px;
         background:linear-gradient(135deg,#f8f7ff,#f0f4ff);
         border-radius:16px;border:1px solid #ddd;margin-bottom:16px">
      <div style="font-size:12px;color:#888;margin-bottom:4px">Risk Analysis for</div>
      <div style="font-size:22px;font-weight:800;color:#1a1a2e;margin-bottom:2px">
        {name or 'Student'}
        <span style="font-size:14px;font-weight:400;color:#666">
          &nbsp;·&nbsp; {int(age)} yrs &nbsp;·&nbsp; {gender} &nbsp;·&nbsp; {institution}
        </span>
      </div>
      <div style="margin-top:8px;display:inline-block;background:{clr}22;
           border:1px solid {clr}55;border-radius:20px;padding:4px 16px;
           font-size:14px;font-weight:700;color:{clr}">
        {lbl} — {scores["Overall"]}/100
      </div>
      {warn}
      <div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap">{domain_cards}</div>
    </div>
    """


def render_recs(recs):
    pc = {"URGENT": "#fce8e8", "HIGH": "#fef3e2", "LOW": "#e8f4fb", "GOOD": "#e8f8f0"}
    pb = {"URGENT": "#f5a0a0", "HIGH": "#f5c97a", "LOW": "#7ec8e3", "GOOD": "#7dd5a8"}
    ic = {"URGENT":  "HIGH", "LOW", "GOOD"}
    html = "<div style='font-family:sans-serif;display:flex;flex-direction:column;gap:10px'>"
    for priority, title, body in recs:
        html += (
            f'<div style="background:{pc.get(priority,"#f5f5f5")};'
            f'border-left:4px solid {pb.get(priority,"#ddd")};'
            f'border-radius:0 12px 12px 0;padding:12px 16px">'
            f'<div style="font-size:11px;font-weight:700;color:#777;margin-bottom:3px">'
            f'{ic.get(priority,"")} {priority}</div>'
            f'<div style="font-size:14px;font-weight:700;color:#222;margin-bottom:4px">{title}</div>'
            f'<div style="font-size:13px;color:#444;line-height:1.6">{body}</div></div>'
        )
    html += "</div>"
    return html


def render_user_history_html(rows, student_name=""):
    if not rows:
        return (f"<p style='color:#888;font-family:sans-serif;padding:12px'>"
                f"No assessments found for <b>{student_name}</b>. "
                f"Complete your first assessment above.</p>")
    html = (f"<div style='font-family:sans-serif;font-size:13px;color:#534AB7;"
            f"font-weight:600;margin-bottom:12px;padding:8px 14px;"
            f"background:#eef0ff;border-radius:8px'>"
            f"{len(rows)} assessment(s) for <b>{student_name}</b></div>"
            f"<div style='display:flex;flex-direction:column;gap:10px;font-family:sans-serif'>")
    for r in rows:
        lbl, clr = risk_label(r["score_overall"])
        html += (
            f'<div style="background:white;border-radius:10px;padding:12px 16px;'
            f'border:1px solid #eee;box-shadow:0 1px 4px rgba(0,0,0,0.05)">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<span style="font-size:13px;color:#555">{r["timestamp"]}</span>'
            f'<span style="font-size:13px;font-weight:700;color:{clr}">'
            f'{lbl} ({r["score_overall"]}/100)</span></div>'
            f'<div style="margin-top:8px;display:flex;gap:16px;font-size:12px;color:#777">'
            f'<span>Sleep: <b style="color:#534AB7">{r["score_sleep"]}</b></span>'
            f'<span>Academic: <b style="color:#534AB7">{r["score_academic"]}</b></span>'
            f'<span>Digital: <b style="color:#534AB7">{r["score_digital"]}</b></span></div>'
            f'<div style="margin-top:6px;font-size:12px;color:#aaa">'
            f'Sleep {r["sleep_hours"]}h · Study {r["study_hours"]}h · '
            f'Screen {r["screen_time"]}h · Gaming {r["gaming_hrs"]}h · '
            f'Attendance {r["attendance"]}%</div></div>'
        )
    html += "</div>"
    return html


def render_admin_table(rows):
    if not rows:
        return "<p style='color:#888;font-family:sans-serif;padding:12px'>No records yet.</p>"
    cols = ["id", "timestamp", "name", "age", "score_overall", "risk_label",
            "sleep_hours", "study_hours", "screen_time", "gaming_hrs", "attendance"]
    header = "".join(
        f"<th style='padding:6px 10px;background:#f0f0f8;border:1px solid #ddd;white-space:nowrap'>{c}</th>"
        for c in cols)
    body = ""
    for r in rows[:200]:
        _, clr = risk_label(r.get("score_overall", 0))
        body += "<tr>"
        for c in cols:
            val   = r.get(c, "")
            style = f"color:{clr};font-weight:700" if c == "risk_label" else ""
            body += (f"<td style='padding:5px 10px;border:1px solid #eee;"
                     f"font-size:12px;{style}'>{val}</td>")
        body += "</tr>"
    return (f"<div style='overflow-x:auto;font-family:sans-serif'>"
            f"<table style='border-collapse:collapse;width:100%'>"
            f"<thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>")


# -----------------------------------------
#  MAIN PREDICT FUNCTION
# -----------------------------------------
def run_prediction(name, age, gender, institution, living,
                   sleep_hours, sleep_quality, nap_freq,
                   attendance, study_hours, screen_time, gaming_hrs):
    scores  = calculate_risk(sleep_hours, sleep_quality, nap_freq,
                             attendance, study_hours, screen_time, gaming_hrs)
    db_save(name, age, gender, institution, living,
            sleep_hours, sleep_quality, nap_freq,
            attendance, study_hours, screen_time, gaming_hrs, scores)
    recs      = generate_recommendations(scores, sleep_hours, screen_time,
                                         attendance, sleep_quality, study_hours, gaming_hrs)
    summary   = render_summary(name, age, gender, institution,
                               sleep_hours, study_hours, screen_time, gaming_hrs, scores)
    recs_html = render_recs(recs)
    rows      = db_user_history(name)
    hist_html = render_user_history_html(rows, student_name=name)
    trend     = make_trend_chart(rows)
    return (summary,
            make_gauge(scores["Overall"]),
            make_radar(scores),
            make_bars(scores),
            make_pie(sleep_hours, study_hours, screen_time, gaming_hrs),
            recs_html,
            hist_html,
            trend,
            name)  # pass name to locked state


# -----------------------------------------
#  CSS
# -----------------------------------------
CSS = """
body { background: #f5f5f7 !important; font-family: 'Segoe UI', sans-serif !important; }
.gradio-container { max-width: 960px !important; margin: auto !important;
                    background: #f5f5f7 !important; }
.gr-tab-nav { background: white !important; border-radius: 12px !important;
              padding: 4px !important; margin-bottom: 12px !important; }
footer { display: none !important; }
"""

INTRO_HTML = """
<div style="font-family:'Segoe UI',sans-serif;padding:32px 24px 8px;text-align:center;
     background:white;border-radius:16px;border:1px solid #eee;margin-bottom:8px">
  <div style="display:inline-block;background:#eef0ff;color:#4f46e5;padding:5px 18px;
       border-radius:20px;font-size:12px;font-weight:700;letter-spacing:.08em;margin-bottom:16px">
    STUDENT WELLNESS TOOL
  </div>
  <h1 style="font-size:32px;font-weight:800;color:#1a1a2e;line-height:1.2;margin-bottom:12px">
    Digital Risk Prediction<br><span style="color:#534AB7">for Students</span>
  </h1>
  <p style="font-size:15px;color:#555;max-width:500px;margin:0 auto 24px;line-height:1.6">
    Poor sleep, high screen time and academic pressure push students toward burnout.
    Fill in your daily habits and get your personalised risk report instantly.
  </p>
  <div style="display:flex;justify-content:center;gap:16px;flex-wrap:wrap;margin-bottom:24px">
    <div style="background:#f8f7ff;border-radius:12px;padding:14px 20px;
         min-width:130px;border:1px solid #ede9ff">
      <div style="font-size:24px;font-weight:800;color:#534AB7">1 in 3</div>
      <div style="font-size:12px;color:#777;margin-top:4px">students show burnout signs</div>
    </div>
    <div style="background:#f8f7ff;border-radius:12px;padding:14px 20px;
         min-width:130px;border:1px solid #ede9ff">
      <div style="font-size:24px;font-weight:800;color:#D85A30">6.2h</div>
      <div style="font-size:12px;color:#777;margin-top:4px">avg daily screen time</div>
    </div>
    <div style="background:#f8f7ff;border-radius:12px;padding:14px 20px;
         min-width:130px;border:1px solid #ede9ff">
      <div style="font-size:24px;font-weight:800;color:#1D9E75">5 min</div>
      <div style="font-size:12px;color:#777;margin-top:4px">to complete assessment</div>
    </div>
  </div>
  <div style="font-size:13px;color:#888;margin-bottom:8px">
     Go to the <b style="color:#534AB7">Assessment</b> tab to get started
  </div>
</div>
"""

# -----------------------------------------
#  UI  — tabs only, no visible toggling
# -----------------------------------------
with gr.Blocks(css=CSS, title="Digital Risk Prediction") as app:

    locked_name = gr.State("")

    with gr.Tabs() as tabs:

        # ── TAB 1: HOME ───────────────────────────────────────
        with gr.Tab(" Home"):
            gr.HTML(INTRO_HTML)
            gr.HTML("""
            <div style="font-family:sans-serif;background:white;border-radius:14px;
                 padding:20px 24px;border:1px solid #eee;margin-top:8px">
              <div style="font-weight:700;font-size:15px;color:#1a1a2e;margin-bottom:12px">
                What we measure
              </div>
              <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
                <div style="background:#f8f7ff;border-radius:10px;padding:12px 14px">
                  <div style="font-size:18px;margin-bottom:6px"></div>
                  <div style="font-weight:600;font-size:13px;color:#222">Sleep Health</div>
                  <div style="font-size:12px;color:#777;margin-top:3px">Hours, quality, nap patterns</div>
                </div>
                <div style="background:#f8f7ff;border-radius:10px;padding:12px 14px">
                  <div style="font-size:18px;margin-bottom:6px"></div>
                  <div style="font-weight:600;font-size:13px;color:#222">Academic</div>
                  <div style="font-size:12px;color:#777;margin-top:3px">Attendance, study hours</div>
                </div>
                <div style="background:#f8f7ff;border-radius:10px;padding:12px 14px">
                  <div style="font-size:18px;margin-bottom:6px"></div>
                  <div style="font-weight:600;font-size:13px;color:#222">Digital</div>
                  <div style="font-size:12px;color:#777;margin-top:3px">Screen time, gaming habits</div>
                </div>
              </div>
            </div>
            """)

        # ── TAB 2: ASSESSMENT ─────────────────────────────────
        with gr.Tab(" Assessment"):
            gr.HTML('<div style="font-family:sans-serif;font-size:13px;font-weight:600;'
                    'color:#4f46e5;background:#eef0ff;display:inline-block;padding:4px 14px;'
                    'border-radius:12px;margin-bottom:12px">FILL IN YOUR DETAILS BELOW</div>')

            # Profile section
            gr.Markdown("### 👤 Your Profile")
            with gr.Row():
                name        = gr.Textbox(label="Full name", placeholder="e.g. Aryan Sharma")
                age         = gr.Number(label="Age", value=18, minimum=10, maximum=30)
            with gr.Row():
                gender      = gr.Radio(["Male", "Female", "Non-binary", "Prefer not to say"],
                                       label="Gender", value="Male")
                institution = gr.Dropdown(
                    ["School (Class 9-10)", "School (Class 11-12)",
                     "Undergraduate College", "Postgraduate / Masters", "Other"],
                    label="Institution", value="Undergraduate College")
            living = gr.Dropdown(
                ["With Family", "Hostel/Dorm", "Shared Flat", "Alone"],
                label="Living situation", value="With Family")

            gr.HTML('<hr style="border:none;border-top:1px solid #eee;margin:16px 0">')

            # Sleep section
            gr.Markdown("###  Sleep")
            with gr.Row():
                sleep_hours   = gr.Slider(0, 12, value=6.5, step=0.5,
                                          label="Sleep hours per night")
                sleep_quality = gr.Slider(1, 10, value=6, step=1,
                                          label="Sleep quality (1=terrible · 10=perfect)")
            nap_freq = gr.Slider(0, 14, value=2, step=1, label="Naps per week")

            gr.HTML('<hr style="border:none;border-top:1px solid #eee;margin:16px 0">')

            # Academic section
            gr.Markdown("###  Academic")
            with gr.Row():
                attendance  = gr.Slider(0, 100, value=72, step=1, label="Attendance (%)")
                study_hours = gr.Slider(0, 12,  value=3,  step=0.5, label="Study hours per day")

            gr.HTML('<hr style="border:none;border-top:1px solid #eee;margin:16px 0">')

            # Digital section
            gr.Markdown("### Screen & Digital")
            with gr.Row():
                screen_time = gr.Slider(0, 16, value=8, step=0.5, label="Screen time per day (hours)")
                gaming_hrs  = gr.Slider(0, 12, value=2, step=0.5, label="Gaming / entertainment (hours/day)")

            gr.HTML('<hr style="border:none;border-top:1px solid #eee;margin:16px 0">')

            btn_calculate = gr.Button(" Calculate My Risk Score", variant="primary", size="lg")

        # ── TAB 3: MY RESULTS ─────────────────────────────────
        with gr.Tab(" My Results"):
            summary_out  = gr.HTML("<p style='color:#aaa;font-family:sans-serif;padding:20px;"
                                   "text-align:center'>Complete the Assessment tab first to see your results.</p>")
            with gr.Row():
                gauge_out = gr.Plot(label="Overall Risk Score")
                bars_out  = gr.Plot(label="Domain Breakdown")
            with gr.Row():
                radar_out = gr.Plot(label="Risk Profile")
                pie_out   = gr.Plot(label="Your 24-Hour Day")
            gr.Markdown("###  Your Action Plan")
            recs_out = gr.HTML()
            gr.HTML("""
            <div style="font-family:sans-serif;margin-top:20px;padding:14px 18px;
                 background:#f8f7ff;border-radius:12px;border:1px solid #ede9ff;
                 text-align:center;font-size:13px;color:#666">
              <b style="color:#534AB7">Remember:</b> This tool gives indicators, not diagnoses.
              Speak to a counsellor if you are in distress.<br>
              <span style="color:#aaa">iCall India: 9152987821 &nbsp;·&nbsp; Vandrevala: 1860-2662-345</span>
            </div>""")

        # ── TAB 4: MY HISTORY ─────────────────────────────────
        with gr.Tab("My History"):
            gr.HTML('<div style="font-family:sans-serif;font-size:13px;color:#444;'
                    'background:#eef8f4;padding:10px 14px;border-radius:8px;'
                    'margin-bottom:14px;border:1px solid #b2dfce">'
                    '<b>Private:</b> You only see your own records here.</div>')
            btn_refresh = gr.Button("  Refresh My History", variant="secondary")
            trend_out   = gr.Plot(label="Risk Score Over Time")
            hist_out    = gr.HTML()

        # ── TAB 5: ADMIN ──────────────────────────────────────
        with gr.Tab(" Admin"):
            gr.HTML('<div style="font-family:sans-serif;font-size:13px;color:#444;'
                    'background:#fef3e2;padding:10px 14px;border-radius:8px;'
                    'margin-bottom:14px;border:1px solid #f5c97a">'
                    '<b>Admin only:</b> Shows all student records.</div>')
            btn_admin      = gr.Button(" Load All Records", variant="secondary")
            admin_stats    = gr.HTML()
            admin_chart    = gr.Plot(label="Risk Distribution")
            admin_table    = gr.HTML()

    # ── EVENT HANDLERS ────────────────────────────────────────

    btn_calculate.click(
        run_prediction,
        inputs=[name, age, gender, institution, living,
                sleep_hours, sleep_quality, nap_freq,
                attendance, study_hours, screen_time, gaming_hrs],
        outputs=[summary_out, gauge_out, radar_out, bars_out, pie_out,
                 recs_out, hist_out, trend_out, locked_name]
    )

    def refresh_history(lname):
        rows = db_user_history(lname)
        return make_trend_chart(rows), render_user_history_html(rows, lname)

    btn_refresh.click(refresh_history,
                      inputs=[locked_name],
                      outputs=[trend_out, hist_out])

    def load_admin():
        rows  = db_all_history()
        total, avg, hi, lo, label_counts = db_stats()
        stats = (
            '<div style="font-family:sans-serif;display:flex;gap:14px;flex-wrap:wrap;margin-bottom:12px">'
            + "".join(
                f'<div style="background:#f8f7ff;border-radius:10px;padding:12px 18px;border:1px solid #ede9ff">'
                f'<div style="font-size:11px;color:#999">{lbl}</div>'
                f'<div style="font-size:20px;font-weight:700;color:#534AB7">{val}</div></div>'
                for lbl, val in [("Total Assessments", total),
                                  ("Avg Score", f"{avg:.1f}"),
                                  ("Highest", hi),
                                  ("Lowest", lo)]
            ) + '</div>'
        )
        return stats, make_admin_bar(label_counts), render_admin_table(rows)

    btn_admin.click(load_admin,
                    outputs=[admin_stats, admin_chart, admin_table])


if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)
