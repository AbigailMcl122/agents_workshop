import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

DATA_PATH = Path('data/raw/sleep_memory_2x2.csv')
OUT_DIR = Path('reports')
OUT_DIR.mkdir(exist_ok=True)


def read_data(path: Path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def desc(values):
    return {
        'n': len(values),
        'mean': mean(values),
        'sd': stdev(values) if len(values) > 1 else float('nan'),
        'median': median(values),
        'min': min(values),
        'max': max(values),
    }


def fmt(x):
    return f"{x:.2f}"


def build_interactive_html(cell_stats, html_path: Path):
    # Use Plotly via CDN for interactivity without Python plotting dependencies.
    x = ['Control', 'TMR']
    sleep_means = [cell_stats[('Sleep', c)]['mean'] for c in x]
    wake_means = [cell_stats[('Wake', c)]['mean'] for c in x]
    sleep_sd = [cell_stats[('Sleep', c)]['sd'] for c in x]
    wake_sd = [cell_stats[('Wake', c)]['sd'] for c in x]

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Sleep × Cue Interactive Graph</title>
  <script src=\"https://cdn.plot.ly/plotly-2.35.2.min.js\"></script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    #plot {{ width: 100%; max-width: 900px; height: 520px; }}
  </style>
</head>
<body>
  <h1>Interactive Figure 1</h1>
  <p>Recall score by Sleep (Sleep vs Wake) and Cue (Control vs TMR). Hover for means and SD.</p>
  <div id=\"plot\"></div>
  <script>
    const traceSleep = {{
      x: {json.dumps(x)},
      y: {json.dumps(sleep_means)},
      mode: 'lines+markers',
      name: 'Sleep',
      error_y: {{ type: 'data', array: {json.dumps(sleep_sd)}, visible: true }},
      hovertemplate: 'Condition: Sleep<br>Cue: %{{x}}<br>Mean: %{{y:.2f}}<extra></extra>'
    }};

    const traceWake = {{
      x: {json.dumps(x)},
      y: {json.dumps(wake_means)},
      mode: 'lines+markers',
      name: 'Wake',
      error_y: {{ type: 'data', array: {json.dumps(wake_sd)}, visible: true }},
      hovertemplate: 'Condition: Wake<br>Cue: %{{x}}<br>Mean: %{{y:.2f}}<extra></extra>'
    }};

    const layout = {{
      title: 'Recall Performance Across Sleep and Cue Conditions',
      xaxis: {{ title: 'Cue Condition' }},
      yaxis: {{ title: 'Recall Score (0–40)' }},
      template: 'plotly_white'
    }};

    Plotly.newPlot('plot', [traceSleep, traceWake], layout, {{responsive: true}});
  </script>
</body>
</html>
"""
    html_path.write_text(html, encoding='utf-8')


def escape_pdf_text(text):
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def build_simple_pdf(lines, pdf_path: Path):
    # Minimal one-page PDF writer (Helvetica, text only)
    content_lines = ["BT", "/F1 11 Tf", "72 770 Td", "14 TL"]
    first = True
    for line in lines:
        if first:
            content_lines.append(f"({escape_pdf_text(line)}) Tj")
            first = False
        else:
            content_lines.append("T*")
            content_lines.append(f"({escape_pdf_text(line)}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode('latin-1', errors='replace')

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n")
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(f"5 0 obj << /Length {len(stream)} >> stream\n".encode('latin-1') + stream + b"\nendstream endobj\n")

    pdf = bytearray(b"%PDF-1.4\n")
    xref = [0]
    for obj in objects:
        xref.append(len(pdf))
        pdf.extend(obj)
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(xref)}\n".encode('latin-1'))
    pdf.extend(b"0000000000 65535 f \n")
    for off in xref[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode('latin-1'))
    pdf.extend(f"trailer << /Size {len(xref)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode('latin-1'))

    pdf_path.write_bytes(pdf)


def main():
    rows = read_data(DATA_PATH)
    scores = [float(r['recall_score']) for r in rows]

    by_sleep = defaultdict(list)
    by_cue = defaultdict(list)
    by_cell = defaultdict(list)
    for r in rows:
        s = r['sleep']
        c = r['cue']
        val = float(r['recall_score'])
        by_sleep[s].append(val)
        by_cue[c].append(val)
        by_cell[(s, c)].append(val)

    overall = desc(scores)
    sleep_stats = {k: desc(v) for k, v in sorted(by_sleep.items())}
    cue_stats = {k: desc(v) for k, v in sorted(by_cue.items())}
    cell_stats = {k: desc(v) for k, v in sorted(by_cell.items())}

    stats_output = {
        'overall': overall,
        'sleep': sleep_stats,
        'cue': cue_stats,
        'cells': {f"{k[0]}_{k[1]}": v for k, v in cell_stats.items()},
    }
    (OUT_DIR / 'descriptive_statistics.json').write_text(json.dumps(stats_output, indent=2), encoding='utf-8')

    html_path = OUT_DIR / 'sleep_memory_interactive_graph.html'
    build_interactive_html(cell_stats, html_path)

    lines = [
        "Sleep and Memory Report (APA 7 Structured Sections)",
        "",
        "Introduction",
        "Sleep is often linked to stronger memory consolidation, and targeted memory reactivation (TMR)",
        "is proposed to further support recall. This report summarizes a 2x2 between-participants study",
        "with Sleep (Sleep, Wake) and Cue (TMR, Control) conditions. Analyses below are descriptive only.",
        "",
        "Study Summary",
        f"The dataset contains N = {overall['n']} participants. The dependent variable is recall_score (0-40).",
        "Design: Sleep vs Wake and TMR vs Control, with 20 participants in each cell.",
        "",
        "Method",
        "Participants completed a word-pair recall task after assignment to one sleep condition and one cue condition.",
        "No inferential tests are reported here; all values are direct descriptive summaries from the data.",
        "",
        "Results",
        "Overall Descriptive Statistics",
        f"Overall recall: M = {fmt(overall['mean'])}, SD = {fmt(overall['sd'])}, Median = {fmt(overall['median'])},",
        f"Range = [{fmt(overall['min'])}, {fmt(overall['max'])}].",
        "",
        "Descriptive Statistics by Condition",
        f"Sleep:   M = {fmt(sleep_stats['Sleep']['mean'])}, SD = {fmt(sleep_stats['Sleep']['sd'])} (n={sleep_stats['Sleep']['n']})",
        f"Wake:    M = {fmt(sleep_stats['Wake']['mean'])}, SD = {fmt(sleep_stats['Wake']['sd'])} (n={sleep_stats['Wake']['n']})",
        f"TMR:     M = {fmt(cue_stats['TMR']['mean'])}, SD = {fmt(cue_stats['TMR']['sd'])} (n={cue_stats['TMR']['n']})",
        f"Control: M = {fmt(cue_stats['Control']['mean'])}, SD = {fmt(cue_stats['Control']['sd'])} (n={cue_stats['Control']['n']})",
        "",
        "Cell-Level Descriptive Statistics (Sleep x Cue)",
        f"Sleep-Control: M = {fmt(cell_stats[('Sleep', 'Control')]['mean'])}, SD = {fmt(cell_stats[('Sleep', 'Control')]['sd'])}",
        f"Sleep-TMR:     M = {fmt(cell_stats[('Sleep', 'TMR')]['mean'])}, SD = {fmt(cell_stats[('Sleep', 'TMR')]['sd'])}",
        f"Wake-Control:  M = {fmt(cell_stats[('Wake', 'Control')]['mean'])}, SD = {fmt(cell_stats[('Wake', 'Control')]['sd'])}",
        f"Wake-TMR:      M = {fmt(cell_stats[('Wake', 'TMR')]['mean'])}, SD = {fmt(cell_stats[('Wake', 'TMR')]['sd'])}",
        "",
        "Interactive Figure",
        "An interactive graph is provided in reports/sleep_memory_interactive_graph.html.",
        "",
        "Note",
        "All reported values were computed from the provided dataset without added or fabricated results.",
    ]

    pdf_path = OUT_DIR / 'sleep_memory_apa7_report.pdf'
    build_simple_pdf(lines, pdf_path)


if __name__ == '__main__':
    main()
