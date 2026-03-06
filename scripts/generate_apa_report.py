import csv
import json
import argparse
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


def _content_stream(lines):
    content_lines = ["BT", "/F1 10 Tf", "72 770 Td", "13 TL"]
    first = True
    for line in lines:
        if first:
            content_lines.append(f"({escape_pdf_text(line)}) Tj")
            first = False
        else:
            content_lines.append("T*")
            content_lines.append(f"({escape_pdf_text(line)}) Tj")
    content_lines.append("ET")
    return "\n".join(content_lines).encode('latin-1', errors='replace')


def build_multi_page_pdf(lines, pdf_path: Path, lines_per_page: int = 50):
    pages = [lines[i:i + lines_per_page] for i in range(0, len(lines), lines_per_page)]
    if not pages:
        pages = [[]]

    objects = []
    # 1 catalog, 2 pages, 3 font
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")

    # placeholder for pages object at index 1 in objects list
    objects.append(b"")

    objects.append(b"3 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")

    next_obj_num = 4
    page_obj_nums = []
    content_obj_nums = []
    for _ in pages:
        page_obj_nums.append(next_obj_num)
        next_obj_num += 1
        content_obj_nums.append(next_obj_num)
        next_obj_num += 1

    kids = " ".join(f"{n} 0 R" for n in page_obj_nums)
    objects[1] = f"2 0 obj << /Type /Pages /Kids [{kids}] /Count {len(page_obj_nums)} >> endobj\n".encode('latin-1')

    for page_obj, content_obj, page_lines in zip(page_obj_nums, content_obj_nums, pages):
        page = f"{page_obj} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >> endobj\n"
        stream = _content_stream(page_lines)
        content = f"{content_obj} 0 obj << /Length {len(stream)} >> stream\n".encode('latin-1') + stream + b"\nendstream endobj\n"
        objects.append(page.encode('latin-1'))
        objects.append(content)

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode('latin-1'))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode('latin-1'))
    pdf.extend(f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode('latin-1'))

    pdf_path.write_bytes(pdf)


def build_report_lines(rows, overall, sleep_stats, cue_stats, cell_stats):
    lines = [
        "Sleep and Memory Report (APA 7 Structured Sections)",
        "",
        "Title Page",
        "Sleep, Cueing, and Recall Performance in a 2x2 Between-Participants Study",
        "",
        "Introduction",
        "Sleep is often associated with memory consolidation, while targeted memory reactivation (TMR)",
        "is hypothesized to improve recall beyond control conditions.",
        "",
        "Study Summary",
        f"Dataset size: N = {overall['n']} participants.",
        "Design: 2x2 between-participants factors: Sleep (Sleep vs Wake) and Cue (TMR vs Control).",
        "Outcome: recall_score (0 to 40).",
        "",
        "Method",
        "Participants completed a word-pair learning and recall task under assigned sleep and cue conditions.",
        "This report contains descriptive statistics only; no inferential claims are made.",
        "",
        "Results: Overall Descriptive Statistics",
        f"Overall recall score: M = {fmt(overall['mean'])}, SD = {fmt(overall['sd'])}, Median = {fmt(overall['median'])},",
        f"Range = [{fmt(overall['min'])}, {fmt(overall['max'])}]",
        "",
        "Results: By Sleep Condition",
        f"Sleep: n = {sleep_stats['Sleep']['n']}, M = {fmt(sleep_stats['Sleep']['mean'])}, SD = {fmt(sleep_stats['Sleep']['sd'])},",
        f"Median = {fmt(sleep_stats['Sleep']['median'])}, Range = [{fmt(sleep_stats['Sleep']['min'])}, {fmt(sleep_stats['Sleep']['max'])}]",
        f"Wake:  n = {sleep_stats['Wake']['n']}, M = {fmt(sleep_stats['Wake']['mean'])}, SD = {fmt(sleep_stats['Wake']['sd'])},",
        f"Median = {fmt(sleep_stats['Wake']['median'])}, Range = [{fmt(sleep_stats['Wake']['min'])}, {fmt(sleep_stats['Wake']['max'])}]",
        "",
        "Results: By Cue Condition",
        f"TMR:     n = {cue_stats['TMR']['n']}, M = {fmt(cue_stats['TMR']['mean'])}, SD = {fmt(cue_stats['TMR']['sd'])},",
        f"Median = {fmt(cue_stats['TMR']['median'])}, Range = [{fmt(cue_stats['TMR']['min'])}, {fmt(cue_stats['TMR']['max'])}]",
        f"Control: n = {cue_stats['Control']['n']}, M = {fmt(cue_stats['Control']['mean'])}, SD = {fmt(cue_stats['Control']['sd'])},",
        f"Median = {fmt(cue_stats['Control']['median'])}, Range = [{fmt(cue_stats['Control']['min'])}, {fmt(cue_stats['Control']['max'])}]",
        "",
        "Results: Cell-Level Statistics (Sleep x Cue)",
        f"Sleep-Control: n = {cell_stats[('Sleep', 'Control')]['n']}, M = {fmt(cell_stats[('Sleep', 'Control')]['mean'])}, SD = {fmt(cell_stats[('Sleep', 'Control')]['sd'])}",
        f"Sleep-TMR:     n = {cell_stats[('Sleep', 'TMR')]['n']}, M = {fmt(cell_stats[('Sleep', 'TMR')]['mean'])}, SD = {fmt(cell_stats[('Sleep', 'TMR')]['sd'])}",
        f"Wake-Control:  n = {cell_stats[('Wake', 'Control')]['n']}, M = {fmt(cell_stats[('Wake', 'Control')]['mean'])}, SD = {fmt(cell_stats[('Wake', 'Control')]['sd'])}",
        f"Wake-TMR:      n = {cell_stats[('Wake', 'TMR')]['n']}, M = {fmt(cell_stats[('Wake', 'TMR')]['mean'])}, SD = {fmt(cell_stats[('Wake', 'TMR')]['sd'])}",
        "",
        "Complete Provided Data (All Rows)",
        "id | sleep | cue | recall_score",
        "--------------------------------",
    ]

    for row in rows:
        lines.append(f"{row['id']} | {row['sleep']} | {row['cue']} | {row['recall_score']}")

    lines.extend([
        "",
        "Interactive Graph",
        "An interactive Plotly graph is available at: reports/sleep_memory_interactive_graph.html",
        "",
        "Data Integrity Note",
        "All values in this PDF were computed or transcribed from the provided CSV without fabrication.",
    ])
    return lines


def parse_args():
    parser = argparse.ArgumentParser(description='Generate APA-style sleep-memory report artifacts.')
    parser.add_argument(
        '--pdf-output',
        default='sleep_memory_apa7_report.pdf',
        help='PDF filename to write under reports/ (default: sleep_memory_apa7_report.pdf)',
    )
    return parser.parse_args()


def main():
    args = parse_args()
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

    build_interactive_html(cell_stats, OUT_DIR / 'sleep_memory_interactive_graph.html')

    report_lines = build_report_lines(rows, overall, sleep_stats, cue_stats, cell_stats)
    build_multi_page_pdf(report_lines, OUT_DIR / args.pdf_output)


if __name__ == '__main__':
    main()
