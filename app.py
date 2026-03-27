import gradio as gr
import plotly.graph_objects as go
import sqlite3
from datetime import datetime

# -----------------------------------------
#  DATABASE  (SQLite - pure Python)
# -----------------------------------------

DB_PATH = "risk_history.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS assessments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp      TEXT NOT NULL,
            name           TEXT,
            age            INTEGER,
            gender         TEXT,
            institution    TEXT,
            living         TEXT,
            sleep_hours    REAL,
            sleep_quality  INTEGER,
            nap_freq       INTEGER,
            attendance     REAL,
            study_hours    REAL,
            screen_time    REAL,
            gaming_hrs     REAL,
            score_sleep    INTEGER,
            score_academic INTEGER,
            score_digital  INTEGER,
            score_overall  INTEGER,
            risk_label     TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()


def db_save(name, age, gender, institution, living,
            sleep_hours, sleep_quality, nap_freq,
            attendance, study_hours, screen_time, gaming_hrs, scores):
    label, _ = risk_label(scores["Overall"])
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
        float(attendance), float(study_hours), float(screen_time), float(gaming_hrs),
        scores["Sleep Health"], scores["Academic"], scores["Digital"],
        scores["Overall"], label
    ))
    conn.commit()
    conn.close()


def db_user_history(name):
    """Return list of dicts for a given user (last 20) - viewer sees ONLY their own."""
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
    """Return all rows as list of dicts (admin only)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM assessments ORDER BY timestamp DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_stats():
    """Aggregate stats for admin dashboard."""
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
            'axis': {'range': [0,100], 'tickwidth': 1},
            'bar': {'color': color},
            'steps': [
                {'range': [0,25],  'color': '#E1F5EE'},
                {'range': [25,50], 'color': '#FAEEDA'},
                {'range': [50,72], 'color': '#FAECE7'},
                {'range': [72,100],'color': '#FCEBEB'},
            ],
            'threshold': {'line': {'color': color,'width': 4},'thickness': 0.8,'value': score}
        },
        number={'suffix': '/100', 'font': {'size': 28, 'color': color}}
    ))
    fig.update_layout(margin=dict(t=50,b=20,l=30,r=30), height=220,
                      paper_bgcolor='rgba(0,0,0,0)', font=dict(family='sans-serif'))
    return fig


def make_radar(scores):
    cats = ["Sleep Health","Academic","Digital"]
    vals = [scores[c] for c in cats] + [scores[cats[0]]]
    cc   = cats + [cats[0]]
    fig  = go.Figure()
    fig.add_trace(go.Scatterpolar(r=vals, theta=cc, fill='toself',
        fillcolor='rgba(83,74,183,0.18)', line=dict(color='#534AB7',width=2.5), name='Your Risk'))
    fig.add_trace(go.Scatterpolar(r=[35]*len(cc), theta=cc, fill='toself',
        fillcolor='rgba(29,158,117,0.10)', line=dict(color='#1D9E75',width=1.5,dash='dot'), name='Healthy'))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0,100], tickfont=dict(size=10))),
        showlegend=True, margin=dict(t=30,b=30,l=30,r=30),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='sans-serif', size=12), legend=dict(orientation='h', y=-0.12))
    return fig


def make_bars(scores):
    cats = ["Sleep Health","Academic","Digital"]
    vals = [scores[c] for c in cats]
    clrs = ['#1D9E75' if v<35 else '#BA7517' if v<65 else '#E24B4A' for v in vals]
    fig  = go.Figure(go.Bar(x=vals, y=cats, orientation='h',
        marker_color=clrs, text=[str(v) for v in vals],
        textposition='outside', textfont=dict(size=12)))
    fig.update_layout(
        xaxis=dict(range=[0,115], showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(autorange='reversed'),
        margin=dict(t=10,b=10,l=10,r=40), height=220,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='sans-serif', size=13))
    return fig


def make_pie(sleep_hours, study_hours, screen_time, gaming_hrs):
    other  = max(0, 24 - sleep_hours - study_hours - screen_time)
    labels = ['Sleep','Study','Screen','Other']
    values = [sleep_hours, study_hours, screen_time, other]
    clrs   = ['#534AB7','#1D9E75','#D85A30','#CCCCCC']
    fig    = go.Figure(go.Pie(labels=labels, values=values,
        marker=dict(colors=clrs), hole=0.45,
        textinfo='label+percent', textfont=dict(size=11)))
    fig.update_layout(
        margin=dict(t=10,b=10,l=10,r=10), height=260,
        paper_bgcolor='rgba(0,0,0,0)', font=dict(family='sans-serif',size=12),
        showlegend=False,
        annotations=[dict(text='24h Day',x=0.5,y=0.5,font_size=13,showarrow=False)])
    return fig


def make_trend_chart(history):
    """Line chart of overall score over time for a user."""
    if not history:
        return go.Figure()
    dates  = [r["timestamp"][:10] for r in reversed(history)]
    scores = [r["score_overall"]  for r in reversed(history)]
    fig    = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=scores, mode='lines+markers',
        line=dict(color='#534AB7', width=2.5),
        marker=dict(size=8, color='#534AB7'),
        name='Overall Risk'
    ))
    fig.add_hline(y=25, line_dash='dot', line_color='#1D9E75', annotation_text='Low Risk')
    fig.add_hline(y=50, line_dash='dot', line_color='#BA7517', annotation_text='Moderate')
    fig.add_hline(y=72, line_dash='dot', line_color='#E24B4A', annotation_text='High Risk')
    fig.update_layout(
        xaxis_title='Date', yaxis_title='Risk Score',
        yaxis=dict(range=[0,100]),
        margin=dict(t=20,b=40,l=40,r=20), height=280,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='sans-serif', size=12))
    return fig


def make_admin_bar(label_counts):
    labels = list(label_counts.keys())
    values = list(label_counts.values())
    clr_map = {"Low Risk":"#1D9E75","Moderate":"#BA7517","High Risk":"#D85A30","Critical":"#E24B4A"}
    clrs = [clr_map.get(l,"#999") for l in labels]
    fig  = go.Figure(go.Bar(x=labels, y=values, marker_color=clrs,
        text=values, textposition='outside'))
    fig.update_layout(
        margin=dict(t=10,b=10,l=10,r=10), height=220,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='sans-serif',size=13),
        xaxis=dict(showgrid=False), yaxis=dict(showgrid=False))
    return fig


# -----------------------------------------
#  RECOMMENDATIONS
# -----------------------------------------

def generate_recommendations(scores, sleep_hours, screen_time,
                              attendance, sleep_quality, study_hours, gaming_hrs):
    recs  = []
    total = sleep_hours + study_hours + screen_time
    if total > 24:
        recs.append(("URGENT","Impossible Daily Schedule",
            f"Sleep ({sleep_hours}h) + Study ({study_hours}h) + Screen ({screen_time}h) = {total}h "
            "which exceeds 24h. Audit your time honestly."))
    if sleep_hours < 7:
        recs.append(("URGENT","Sleep Deficit",
            f"Sleeping {sleep_hours}h/day is {round(7-sleep_hours,1)}h below minimum. "
            "Set a fixed bedtime, avoid screens 45min before sleep, no caffeine after 3pm."))
    if sleep_quality < 5:
        recs.append(("URGENT","Poor Sleep Quality",
            f"Quality {sleep_quality}/10 is critically low. Try white noise, a cooler room, "
            "and a consistent pre-sleep routine."))
    if screen_time > 9:
        recs.append(("HIGH","Screen Time Overload",
            f"{screen_time}h screen/day is too high. Use grayscale after 8pm, set app timers, "
            "take a 5-min break every 45min."))
    if gaming_hrs > 4:
        recs.append(("HIGH","Excessive Gaming",
            f"{gaming_hrs}h/day gaming. Cap at 1-2h, evenings only."))
    if attendance < 75:
        recs.append(("URGENT","Critical Attendance",
            f"{attendance}% attendance puts you at risk. Talk to your mentor and find root causes."))
    if not recs:
        recs.append(("GOOD","Healthy Patterns",
            "Great balance! Keep doing weekly check-ins and watch your habits during exam season."))
    return recs


# -----------------------------------------
#  MAIN PREDICTION
# -----------------------------------------

def run_prediction(name, age, gender, institution, living_situation,
                   sleep_hours, sleep_quality, nap_freq,
                   attendance, study_hours, screen_time, gaming_hrs):

    scores  = calculate_risk(sleep_hours, sleep_quality, nap_freq,
                              attendance, study_hours, screen_time, gaming_hrs)
    overall = scores["Overall"]

    db_save(name, age, gender, institution, living_situation,
            sleep_hours, sleep_quality, nap_freq,
            attendance, study_hours, screen_time, gaming_hrs, scores)

    domain_cards = ""
    for k, v in scores.items():
        if k == "Overall": continue
        c = "#1D9E75" if v<35 else "#BA7517" if v<65 else "#E24B4A"
        domain_cards += (
            f'<div style="background:white;border-radius:10px;padding:10px 16px;'
            f'border:1px solid #eee;min-width:110px;">'
            f'<div style="font-size:11px;color:#999;margin-bottom:2px">{k}</div>'
            f'<div style="font-size:18px;font-weight:600;color:{c}">{v}</div></div>'
        )
    total_hrs = sleep_hours + study_hours + screen_time
    hrs_warn  = ""
    if total_hrs > 24:
        hrs_warn = (
            f'<div style="background:#fce8e8;border-radius:8px;padding:8px 14px;'
            f'margin-top:10px;font-size:13px;color:#c0392b;">'
            f'WARNING: Sleep + Study + Screen = <b>{total_hrs}h</b> which exceeds 24h/day!</div>'
        )
    summary_html = f"""
    <div style="font-family:sans-serif;padding:16px 20px;
         background:linear-gradient(135deg,#f8f7ff,#f0f4ff);
         border-radius:14px;border:1px solid #ddd;margin-bottom:8px">
      <div style="font-size:13px;color:#888;margin-bottom:4px">Daily Risk Analysis for</div>
      <div style="font-size:20px;font-weight:700;color:#222;margin-bottom:2px">
        {name or 'Student'} &nbsp;&middot;&nbsp;
        <span style="font-size:15px;font-weight:400;color:#555">
          {int(age)} yrs &nbsp;&middot;&nbsp; {gender} &nbsp;&middot;&nbsp; {institution}
        </span>
      </div>
      <div style="font-size:12px;color:#888;margin-top:6px">
        24h breakdown: Sleep {sleep_hours}h | Study {study_hours}h | Screen {screen_time}h | Gaming {gaming_hrs}h
      </div>
      {hrs_warn}
      <div style="margin-top:14px;display:flex;gap:12px;flex-wrap:wrap">{domain_cards}</div>
    </div>
    """

    recs = generate_recommendations(scores, sleep_hours, screen_time,
                                     attendance, sleep_quality, study_hours, gaming_hrs)
    pc = {"URGENT":"#fce8e8","HIGH":"#fef3e2","LOW":"#e8f4fb","GOOD":"#e8f8f0"}
    pb = {"URGENT":"#f5a0a0","HIGH":"#f5c97a","LOW":"#7ec8e3","GOOD":"#7dd5a8"}
    recs_html = "<div style='font-family:sans-serif;display:flex;flex-direction:column;gap:10px'>"
    for priority, title, body in recs:
        recs_html += (
            f'<div style="background:{pc.get(priority,"#f5f5f5")};'
            f'border-left:4px solid {pb.get(priority,"#ddd")};'
            f'border-radius:0 10px 10px 0;padding:12px 16px">'
            f'<div style="font-size:12px;font-weight:600;color:#555;margin-bottom:3px">{priority}</div>'
            f'<div style="font-size:14px;font-weight:700;color:#222;margin-bottom:4px">{title}</div>'
            f'<div style="font-size:13px;color:#444;line-height:1.55">{body}</div></div>'
        )
    recs_html += "</div>"

    return (summary_html,
            make_gauge(overall),
            make_radar(scores),
            make_bars(scores),
            make_pie(sleep_hours, study_hours, screen_time, gaming_hrs),
            recs_html)


# -----------------------------------------
#  HISTORY HELPERS (for UI)
# -----------------------------------------

def render_user_history_html(rows, student_name=""):
    """Renders history cards for a single user - viewers only see their own records."""
    if not rows:
        if student_name:
            msg = (f"No assessments found for <b>{student_name}</b>. "
                   "Complete your first assessment to see history here.")
        else:
            msg = "No assessments found. Complete an assessment to see your history here."
        return f"<p style='color:#888;font-family:sans-serif;padding:12px'>{msg}</p>"

    count = len(rows)
    header = (
        f'<div style="font-family:sans-serif;font-size:13px;color:#534AB7;font-weight:600;'
        f'margin-bottom:12px;padding:8px 14px;background:#eef0ff;border-radius:8px;">'
        f'Showing {count} assessment{"s" if count > 1 else ""} for '
        f'<b>{student_name or "you"}</b>'
        f'</div>'
    )
    html = f"<div style='font-family:sans-serif;display:flex;flex-direction:column;gap:10px'>{header}"
    for r in rows:
        lbl, clr = risk_label(r["score_overall"])
        html += (
            f'<div style="background:white;border-radius:10px;padding:12px 16px;'
            f'border:1px solid #eee;box-shadow:0 1px 4px rgba(0,0,0,0.05)">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<span style="font-size:13px;color:#555">{r["timestamp"]}</span>'
            f'<span style="font-size:13px;font-weight:700;color:{clr}">'
            f'{lbl} ({r["score_overall"]}/100)</span>'
            f'</div>'
            f'<div style="margin-top:8px;display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#777">'
            f'<span>Sleep: <b style="color:#534AB7">{r["score_sleep"]}</b></span>'
            f'<span>Academic: <b style="color:#534AB7">{r["score_academic"]}</b></span>'
            f'<span>Digital: <b style="color:#534AB7">{r["score_digital"]}</b></span>'
            f'</div>'
            f'<div style="margin-top:6px;font-size:12px;color:#aaa">'
            f'Sleep {r["sleep_hours"]}h &middot; Study {r["study_hours"]}h &middot; '
            f'Screen {r["screen_time"]}h &middot; Gaming {r["gaming_hrs"]}h &middot; '
            f'Attendance {r["attendance"]}%'
            f'</div></div>'
        )
    html += "</div>"
    return html


def render_admin_table(rows):
    if not rows:
        return "<p style='color:#888;font-family:sans-serif;padding:12px'>No records yet.</p>"
    cols = ["id","timestamp","name","age","score_overall","risk_label",
            "sleep_hours","study_hours","screen_time","gaming_hrs","attendance"]
    header = "".join(
        f"<th style='padding:6px 10px;background:#f0f0f8;border:1px solid #ddd'>{c}</th>"
        for c in cols
    )
    body = ""
    for r in rows[:200]:
        lbl, clr = risk_label(r["score_overall"])
        body += "<tr>"
        for c in cols:
            val = r.get(c, "")
            style = f"color:{clr};font-weight:700" if c == "risk_label" else ""
            body += (f"<td style='padding:5px 10px;border:1px solid #eee;"
                     f"font-size:12px;{style}'>{val}</td>")
        body += "</tr>"
    count = len(rows)
    cap_note = f" (showing first 200 of {count})" if count > 200 else f" ({count} total)"
    return (
        f"<div style='font-family:sans-serif;font-size:12px;color:#888;"
        f"margin-bottom:6px'>All records{cap_note}</div>"
        f"<div style='overflow-x:auto;font-family:sans-serif'>"
        f"<table style='border-collapse:collapse;width:100%;min-width:600px'>"
        f"<thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>"
    )


# -----------------------------------------
#  CSS
# -----------------------------------------

CSS = """
body { font-family: 'Segoe UI', sans-serif !important; }
.gradio-container { max-width: 980px !important; margin: auto !important; }
.tag-pill {
    display: inline-block; background: #eef0ff; color: #4f46e5;
    padding: 3px 12px; border-radius: 12px;
    font-size: 12px; font-weight: 600; margin-bottom: 10px;
}
button.lg { border-radius: 10px !important; font-weight: 600 !important; }
"""

# -----------------------------------------
#  UI
# -----------------------------------------

with gr.Blocks(css=CSS, title="Digital Risk Prediction") as app:

    current_user = gr.State("")

    # PAGE 1: INTRO
    with gr.Column(visible=True) as page1:
        gr.HTML("""
        <div style="font-family:'Segoe UI',sans-serif;padding:32px 24px 20px;text-align:center">
          <div style="display:inline-block;background:#eef0ff;color:#4f46e5;padding:5px 18px;
               border-radius:20px;font-size:12px;font-weight:700;letter-spacing:.08em;margin-bottom:18px">
            STUDENT WELLNESS TOOL
          </div>
          <h1 style="font-size:36px;font-weight:800;color:#1a1a2e;line-height:1.15;margin-bottom:12px">
            Digital Risk Prediction<br><span style="color:#534AB7">for Students</span>
          </h1>
          <p style="font-size:16px;color:#555;max-width:520px;margin:0 auto 28px;line-height:1.6">
            Poor sleep, high screen time, and academic pressure are silently pushing students
            toward burnout. This tool analyses your <strong>24-hour daily schedule</strong>,
            tracks your history, and gives personalised action plans.
          </p>
          <div style="display:flex;justify-content:center;gap:16px;flex-wrap:wrap;margin-bottom:32px">
            <div style="background:#f8f7ff;border-radius:12px;padding:16px 20px;min-width:140px;border:1px solid #ede9ff">
              <div style="font-size:26px;font-weight:800;color:#534AB7">1 in 3</div>
              <div style="font-size:12px;color:#777;margin-top:4px">students show digital burnout signs</div>
            </div>
            <div style="background:#f8f7ff;border-radius:12px;padding:16px 20px;min-width:140px;border:1px solid #ede9ff">
              <div style="font-size:26px;font-weight:800;color:#D85A30">6.2h</div>
              <div style="font-size:12px;color:#777;margin-top:4px">avg daily screen time among teens</div>
            </div>
            <div style="background:#f8f7ff;border-radius:12px;padding:16px 20px;min-width:140px;border:1px solid #ede9ff">
              <div style="font-size:26px;font-weight:800;color:#1D9E75">5 min</div>
              <div style="font-size:12px;color:#777;margin-top:4px">to complete your full assessment</div>
            </div>
          </div>
          <div style="display:flex;justify-content:center;gap:20px;flex-wrap:wrap;
               margin-bottom:10px;font-size:13px;color:#555">
            <span>Profile</span>
            <span style="color:#ccc">-&gt;</span>
            <span>Habits</span>
            <span style="color:#ccc">-&gt;</span>
            <span>Results + My History + Admin</span>
          </div>
        </div>""")
        btn_start = gr.Button("Get Started", variant="primary", size="lg")

    # PAGE 2: PROFILE
    with gr.Column(visible=False) as page2:
        gr.HTML('<div class="tag-pill">STEP 1 OF 2 &nbsp;&middot;&nbsp; YOUR PROFILE</div>')
        gr.Markdown("### Tell us about yourself")
        with gr.Row():
            name = gr.Textbox(label="Full name", placeholder="e.g. Aryan Sharma")
            age  = gr.Number(label="Age", value=18, minimum=10, maximum=30)
        with gr.Row():
            gender = gr.Radio(["Male","Female","Non-binary","Prefer not to say"],
                              label="Gender", value="Male")
            institution = gr.Dropdown(
                ["School (Class 9-10)","School (Class 11-12)",
                 "Undergraduate College","Postgraduate / Masters","Other"],
                label="Institution type", value="Undergraduate College")
        living_situation = gr.Dropdown(
            ["With Family","Hostel/Dorm","Shared Flat","Alone"],
            label="Living situation", value="With Family")
        with gr.Row():
            btn_p2_back = gr.Button("Back")
            btn_p2_next = gr.Button("Next: Habits", variant="primary")

    # PAGE 3: HABITS
    with gr.Column(visible=False) as page3:
        gr.HTML('<div class="tag-pill">STEP 2 OF 2 &nbsp;&middot;&nbsp; DAILY HABITS (24h)</div>')
        gr.Markdown("### All hours are based on your **24-hour day**")

        with gr.Column(visible=True) as sec_sleep:
            gr.Markdown("#### Sleep")
            with gr.Row():
                sleep_hours   = gr.Slider(0, 24, value=6.5, step=0.5,
                                          label="Sleep hours/day (out of 24h)")
                sleep_quality = gr.Slider(1, 10, value=6, step=1,
                                          label="Sleep quality (1=terrible, 10=perfect)")
            nap_freq = gr.Slider(0, 14, value=2, step=1, label="Naps per week")
            with gr.Row():
                btn_s_back = gr.Button("Back to Profile")
                btn_s_next = gr.Button("Next: Academic", variant="primary")

        with gr.Column(visible=False) as sec_academic:
            gr.Markdown("#### Academic")
            with gr.Row():
                attendance  = gr.Slider(0, 100, value=72, step=1, label="Attendance (%)")
                study_hours = gr.Slider(0, 24, value=3, step=0.5,
                                        label="Study hours/day (out of 24h)")
            with gr.Row():
                btn_a_back = gr.Button("Back to Sleep")
                btn_a_next = gr.Button("Next: Screen and Digital", variant="primary")

        with gr.Column(visible=False) as sec_digital:
            gr.Markdown("#### Screen and Digital")
            gr.HTML(
                '<div style="font-size:12px;color:#666;margin-bottom:10px;background:#fffbe6;'
                'padding:8px 12px;border-radius:8px;border:1px solid #f5e58a;">'
                'Note: Sleep + Study + Screen should not exceed 24h/day</div>'
            )
            with gr.Row():
                screen_time = gr.Slider(0, 24, value=8, step=0.5,
                                        label="Screen time/day (out of 24h)")
                gaming_hrs  = gr.Slider(0, 24, value=2, step=0.5,
                                        label="Gaming/entertainment per day")
            with gr.Row():
                btn_d_back    = gr.Button("Back to Academic")
                btn_calculate = gr.Button("Calculate My Risk", variant="primary", size="lg")

    # PAGE 4: RESULTS + MY HISTORY + ADMIN
    with gr.Column(visible=False) as page4:

        with gr.Tabs():

            # TAB 1: RESULTS
            with gr.Tab("My Results"):
                gr.HTML('<div class="tag-pill">YOUR DAILY RISK REPORT</div>')
                summary_html_out = gr.HTML()
                with gr.Row():
                    gauge_out = gr.Plot(label="Overall Risk Score")
                    bars_out  = gr.Plot(label="Domain Breakdown")
                with gr.Row():
                    radar_out = gr.Plot(label="Risk Profile")
                    pie_out   = gr.Plot(label="Your 24-Hour Day")
                gr.Markdown("### Personalised Action Plan")
                recs_html_out = gr.HTML()
                gr.HTML("""
                <div style="font-family:sans-serif;margin-top:24px;padding:16px 20px;
                     background:#f8f7ff;border-radius:12px;border:1px solid #ede9ff;
                     text-align:center;font-size:13px;color:#666">
                  <strong style="color:#534AB7">Remember:</strong> This tool provides indicators,
                  not diagnoses. Please speak to a counsellor if you are in distress.
                  <br>
                  <span style="color:#aaa">
                    iCall India: 9152987821 &nbsp;&middot;&nbsp;
                    Vandrevala Foundation: 1860-2662-345
                  </span>
                </div>""")

            # TAB 2: MY HISTORY (viewer sees ONLY their own records)
            with gr.Tab("My History"):
                gr.Markdown("### Your Assessment History")
                gr.HTML(
                    '<div style="font-family:sans-serif;font-size:13px;color:#444;'
                    'background:#eef8f4;padding:10px 14px;border-radius:8px;'
                    'margin-bottom:14px;border:1px solid #b2dfce">'
                    '<b>Private view:</b> You can only see your own assessment records here. '
                    'Your history is filtered automatically based on the name you provided.</div>'
                )
                my_hist_name        = gr.Textbox(visible=False)
                btn_refresh_my_hist = gr.Button("Refresh My History", variant="secondary")
                my_trend_out        = gr.Plot(label="My Risk Score Over Time")
                my_hist_html        = gr.HTML()

            # TAB 3: ADMIN - ALL RECORDS
            with gr.Tab("Admin - All Records"):
                gr.Markdown("### All Assessment Records (Admin View)")
                gr.HTML(
                    '<div style="font-family:sans-serif;font-size:13px;color:#444;'
                    'background:#fef3e2;padding:10px 14px;border-radius:8px;'
                    'margin-bottom:14px;border:1px solid #f5c97a">'
                    '<b>Admin only:</b> This tab shows all student records. '
                    'Restrict access to authorised staff in production deployments.</div>'
                )
                btn_load_admin   = gr.Button("Refresh All Records", variant="secondary")
                admin_stats_html = gr.HTML()
                admin_chart_out  = gr.Plot(label="Risk Distribution Across All Students")
                admin_table_html = gr.HTML()

        btn_restart = gr.Button("Start New Assessment", variant="secondary")

    # =============================================
    #  NAVIGATION + EVENT WIRING
    # =============================================

    def show_page(n):
        return [gr.update(visible=(i == n)) for i in range(4)]

    def show_sec(n):
        return [gr.update(visible=(i == n)) for i in range(3)]

    btn_start.click(  lambda: show_page(1), outputs=[page1, page2, page3, page4])
    btn_p2_back.click(lambda: show_page(0), outputs=[page1, page2, page3, page4])
    btn_p2_next.click(lambda: show_page(2), outputs=[page1, page2, page3, page4])
    btn_restart.click(lambda: show_page(0), outputs=[page1, page2, page3, page4])
    btn_s_back.click( lambda: show_page(1), outputs=[page1, page2, page3, page4])

    btn_s_next.click(lambda: show_sec(1), outputs=[sec_sleep, sec_academic, sec_digital])
    btn_a_back.click(lambda: show_sec(0), outputs=[sec_sleep, sec_academic, sec_digital])
    btn_a_next.click(lambda: show_sec(2), outputs=[sec_sleep, sec_academic, sec_digital])
    btn_d_back.click(lambda: show_sec(1), outputs=[sec_sleep, sec_academic, sec_digital])

    # CALCULATE
    def on_calculate(name, age, gender, institution, living_situation,
                     sleep_hours, sleep_quality, nap_freq,
                     attendance, study_hours, screen_time, gaming_hrs):
        summary, gauge, radar, bars, pie, recs = run_prediction(
            name, age, gender, institution, living_situation,
            sleep_hours, sleep_quality, nap_freq,
            attendance, study_hours, screen_time, gaming_hrs
        )
        rows  = db_user_history(name)
        trend = make_trend_chart(rows)
        hist  = render_user_history_html(rows, student_name=name)
        return (
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=True),
            summary, gauge, radar, bars, pie, recs,
            name,
            name,
            trend,
            hist,
        )

    btn_calculate.click(
        on_calculate,
        inputs=[name, age, gender, institution, living_situation,
                sleep_hours, sleep_quality, nap_freq,
                attendance, study_hours, screen_time, gaming_hrs],
        outputs=[page1, page2, page3, page4,
                 summary_html_out, gauge_out, radar_out, bars_out, pie_out, recs_html_out,
                 my_hist_name, current_user,
                 my_trend_out, my_hist_html]
    )

    # REFRESH MY OWN HISTORY
    def on_refresh_my_hist(locked_name):
        rows  = db_user_history(locked_name)
        trend = make_trend_chart(rows)
        html  = render_user_history_html(rows, student_name=locked_name)
        return trend, html

    btn_refresh_my_hist.click(
        on_refresh_my_hist,
        inputs=[my_hist_name],
        outputs=[my_trend_out, my_hist_html]
    )

    # ADMIN: LOAD ALL RECORDS
    def on_load_admin():
        rows  = db_all_history()
        total, avg, hi, lo, label_counts = db_stats()
        stats_html = (
            '<div style="font-family:sans-serif;display:flex;gap:14px;'
            'flex-wrap:wrap;margin-bottom:12px">'
            + "".join(
                f'<div style="background:#f8f7ff;border-radius:10px;padding:12px 18px;'
                f'border:1px solid #ede9ff">'
                f'<div style="font-size:11px;color:#999">{label}</div>'
                f'<div style="font-size:20px;font-weight:700;color:#534AB7">{val}</div></div>'
                for label, val in [
                    ("Total Assessments", total),
                    ("Avg Overall Score", f"{avg:.1f}"),
                    ("Highest Score",     hi),
                    ("Lowest Score",      lo),
                ]
            )
            + '</div>'
        )
        chart = make_admin_bar(label_counts)
        table = render_admin_table(rows)
        return stats_html, chart, table

    btn_load_admin.click(on_load_admin,
                         outputs=[admin_stats_html, admin_chart_out, admin_table_html])


if __name__ == "__main__":
    app.launch()

import os

if __name__ == "__main__":
    # This finds the port Render assigns to your app
    port = int(os.environ.get("PORT", 7860))
    app.launch(server_name="0.0.0.0", server_port=port)
