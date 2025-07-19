from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from datetime import datetime
from reportlab.lib.units import inch

def generate_pdf_report(survey: dict, stats: list, output_path: str = "report.pdf") -> str:
    doc = SimpleDocTemplate(output_path, pagesize=A4, rightMargin=inch, leftMargin=inch, topMargin=1.2*inch, bottomMargin=1.2*inch)
    styles = getSampleStyleSheet()
    story = []
    COLOR_PRIMARY = colors.HexColor("#2C3E50")
    COLOR_SECONDARY = colors.HexColor("#3498DB")
    COLOR_ACCENT = colors.HexColor("#1ABC9C")
    COLOR_LIGHT_GREY = colors.HexColor("#ECF0F1")
    COLOR_DARK_GREY = colors.HexColor("#7F8C8D")
    styles.add(ParagraphStyle(name='ReportTitlePage', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=48, leading=55, alignment=1, textColor=COLOR_PRIMARY))
    styles.add(ParagraphStyle(name='ReportSubtitlePage', parent=styles['Italic'], fontName='Helvetica', fontSize=18, leading=22, alignment=1, textColor=COLOR_DARK_GREY))
    styles.add(ParagraphStyle(name='SectionHeading', parent=styles['h3'], fontName='Helvetica-Bold', fontSize=22, leading=26, alignment=1, textColor=COLOR_PRIMARY))
    styles.add(ParagraphStyle(name='NormalText', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14, alignment=0, textColor=COLOR_PRIMARY))
    styles.add(ParagraphStyle(name='FooterStyle', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=8, alignment=1, textColor=colors.white))

    def first_page(canvas, doc):
        canvas.saveState()
        title_text = survey.get("title", "Informe de Encuesta")
        description_text = survey.get("description", "Análisis detallado de los resultados de la encuesta.")
        p_title = Paragraph(title_text, styles["ReportTitlePage"])
        w_title, h_title = p_title.wrapOn(canvas, doc.width, doc.height)
        p_title.drawOn(canvas, (A4[0] - w_title) / 2, A4[1] - 3 * inch)
        p_desc = Paragraph(description_text, styles["ReportSubtitlePage"])
        w_desc, h_desc = p_desc.wrapOn(canvas, doc.width, doc.height)
        p_desc.drawOn(canvas, (A4[0] - w_desc) / 2, A4[1] - 4.5 * inch)
        generated_date = datetime.now().strftime("Generado el %d de %B de %Y a las %H:%M")
        p_date = Paragraph(generated_date, styles["ReportSubtitlePage"])
        w_date, h_date = p_date.wrapOn(canvas, doc.width, doc.height)
        p_date.drawOn(canvas, (A4[0] - w_date) / 2, 1.5 * inch)
        canvas.restoreState()

    def later_pages(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(COLOR_SECONDARY)
        canvas.rect(0, A4[1] - 0.8 * inch, A4[0], 0.8 * inch, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 12)
        header_title = survey.get('title', 'Informe de Encuesta')
        canvas.drawCentredString(A4[0] / 2, A4[1] - 0.5 * inch, header_title)
        canvas.setFillColor(COLOR_SECONDARY)
        canvas.rect(0, 0, A4[0], 0.8 * inch, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 10)
        canvas.drawCentredString(A4[0] / 2, 0.3 * inch, f"Página {doc.page}")
        canvas.restoreState()

    story.append(PageBreak())
    story.append(Spacer(1, 0.5 * inch))

    for item in stats:
        story.append(Paragraph(item['question'], styles["SectionHeading"]))
        story.append(Spacer(1, 0.15 * inch))
        if "data" in item and item["data"]:
            data_table = [["Opción", "Cantidad", "Porcentaje"]]
            total_responses_for_question = sum(item["data"].values())
            for key, val in item["data"].items():
                percentage = (val / total_responses_for_question) * 100 if total_responses_for_question > 0 else 0
                data_table.append([str(key), str(val), f"{percentage:.1f}%"])
            table_style = TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_SECONDARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, COLOR_DARK_GREY),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ])
            for i in range(1, len(data_table)):
                table_style.add("BACKGROUND", (0, i), (-1, i), COLOR_LIGHT_GREY if i % 2 == 0 else colors.white)
            table = Table(data_table, hAlign="CENTER")
            table.setStyle(table_style)
            story.append(table)
            story.append(Spacer(1, 0.25 * inch))
            bar_drawing = Drawing(doc.width, 220)
            bar_chart = VerticalBarChart()
            bar_chart.x = (doc.width - 370) / 2
            bar_chart.y = 30
            bar_chart.height = 160
            bar_chart.width = 370
            values = list(item["data"].values())
            labels = list(item["data"].keys())
            bar_chart.data = [values]
            bar_chart.categoryAxis.categoryNames = labels
            bar_chart.categoryAxis.labels.boxAnchor = 'ne'
            bar_chart.categoryAxis.labels.dx = 8
            bar_chart.categoryAxis.labels.dy = -2
            bar_chart.categoryAxis.labels.angle = 30
            bar_chart.bars[0].fillColor = COLOR_SECONDARY
            bar_chart.valueAxis.valueMin = 0
            bar_chart.valueAxis.valueMax = max(values) + 1 if values else 1
            bar_chart.valueAxis.valueStep = max(1, int((max(values) + 1) / 5)) if values else 1
            for i, val in enumerate(values):
                label_y = bar_chart.y + bar_chart.height * val / bar_chart.valueAxis.valueMax + 5
                if val == 0:
                    label_y = bar_chart.y - 10
                bar_drawing.add(String(bar_chart.x + bar_chart.width * (i + 0.5) / len(values) - len(str(val))*3, label_y, str(val), fontName='Helvetica-Bold', fontSize=8, fillColor=COLOR_PRIMARY))
            bar_drawing.add(bar_chart)
            story.append(bar_drawing)
            story.append(Spacer(1, 0.25 * inch))
            if item["type"] == "multiple_choice" and len(values) > 1 and total_responses_for_question > 0:
                pie_drawing = Drawing(doc.width, 200)
                pie = Pie()
                pie.x = (doc.width - 160) / 2
                pie.y = 20
                pie.width = 160
                pie.height = 160
                pie.data = values
                pie.labels = [f"{label} ({val})" for label, val in zip(labels, values)]
                pie.slices.strokeWidth = 0.5
                pie.slices.strokeColor = colors.white
                pie_colors = [COLOR_ACCENT, colors.HexColor("#2ECC71"), colors.HexColor("#3498DB"),
                              colors.HexColor("#9B59B6"), colors.HexColor("#F1C40F"), colors.HexColor("#E67E22"),
                              colors.HexColor("#E74C3C"), colors.HexColor("#BDC3C7")]
                for i, slice_color in enumerate(pie_colors):
                    if i < len(pie.data):
                        pie.slices[i].fillColor = slice_color
                pie_drawing.add(String(pie.x + pie.width/2 - 50, pie.y + pie.height + 10, "Distribución de Respuestas", fontName='Helvetica-Bold', fontSize=12, fillColor=COLOR_PRIMARY))
                pie_drawing.add(pie)
                story.append(pie_drawing)
                story.append(Spacer(1, 0.25 * inch))
        if item.get("type") == "number_input" and "histogram" in item:
            hist_values = list(item["histogram"].values())
            hist_labels = list(item["histogram"].keys())
            if hist_values and hist_labels:
                story.append(Paragraph("<para align='center'>Distribución numérica (histograma):</para>", styles["NormalText"]))
                story.append(Spacer(1, 0.1 * inch))
                hist_drawing = Drawing(doc.width, 220)
                hist_chart = VerticalBarChart()
                hist_chart.x = (doc.width - 370) / 2
                hist_chart.y = 30
                hist_chart.height = 160
                hist_chart.width = 370
                hist_chart.data = [hist_values]
                hist_chart.categoryAxis.categoryNames = hist_labels
                hist_chart.bars[0].fillColor = COLOR_ACCENT
                hist_chart.valueAxis.valueMin = 0
                hist_chart.valueAxis.valueMax = max(hist_values) + 1 if hist_values else 1
                hist_chart.valueAxis.valueStep = max(1, int((max(hist_values) + 1) / 5)) if hist_values else 1
                for i, val in enumerate(hist_values):
                    label_y = hist_chart.y + hist_chart.height * val / hist_chart.valueAxis.valueMax + 5
                    if val == 0:
                        label_y = hist_chart.y - 10
                    hist_drawing.add(String(hist_chart.x + hist_chart.width * (i + 0.5) / len(hist_values) - len(str(val))*3, label_y, str(val), fontName='Helvetica-Bold', fontSize=8, fillColor=COLOR_PRIMARY))
                hist_drawing.add(hist_chart)
                story.append(hist_drawing)
                story.append(Spacer(1, 0.25 * inch))
            else:
                story.append(Paragraph("<para align='center'>No hay datos suficientes para generar un histograma.</para>", styles["NormalText"]))
                story.append(Spacer(1, 0.1 * inch))
        if item.get("type") == "number_input":
            story.append(Paragraph("<para align='center'>Métricas clave:</para>", styles["NormalText"]))
            story.append(Spacer(1, 0.05 * inch))
            stats_info = [
                f"<para align='center'><b>Promedio:</b> {item.get('avg', 'N/A'):.2f}</para>" if isinstance(item.get('avg'), (int, float)) else f"<para align='center'><b>Promedio:</b> {item.get('avg', 'N/A')}</para>",
                f"<para align='center'><b>Mediana:</b> {item.get('median', 'N/A'):.2f}</para>" if isinstance(item.get('median'), (int, float)) else f"<para align='center'><b>Mediana:</b> {item.get('median', 'N/A')}</para>",
                f"<para align='center'><b>Mínimo:</b> {item.get('min', 'N/A')}</para>",
                f"<para align='center'><b>Máximo:</b> {item.get('max', 'N/A')}</para>"
            ]
            for line in stats_info:
                story.append(Paragraph(line, styles["NormalText"]))
                story.append(Spacer(1, 0.05 * inch))
            story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph(f"<i>Total de respuestas para esta pregunta: {item.get('total', 0)}</i>", styles["FooterStyle"]))
        story.append(Spacer(1, 0.5 * inch))
        if story and story[-1].__class__.__name__ != 'PageBreak' and len(story) > 5:
            story.append(PageBreak())
    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    return output_path
