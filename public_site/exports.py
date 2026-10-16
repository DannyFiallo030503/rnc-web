"""Aggregate-only image, PDF and spreadsheet renderers."""

import csv
import io
from django.http import HttpResponse


def export_result(fmt, table, payload, params):
    filename = "consulta-rnc-sintetica"
    note = (
        payload["note"]
        + " · "
        + payload["metric"]
        + " · "
        + payload["unit"]
        + " · Método candidato; denominadores sintéticos. Las personas pueden aparecer en varias localizaciones."
    )
    header = [
        "Categoría",
        "Tumores",
        "Personas distintas",
        "Población sintética anual acumulada",
        "Valor",
    ]
    values = [
        [r[k] for k in ["label", "tumors", "persons", "population", "value"]]
        for r in table
    ]
    if len(payload["datasets"]) > 1:
        header += [
            d["label"]
            + (" (%)" if params["chart"] == "percent" else " · " + payload["metric"])
            for d in payload["datasets"]
        ]
        values = [
            row + [s["value"] for s in item["series"]]
            for row, item in zip(values, table)
        ]
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([note])
        writer.writerow(header)
        writer.writerows(values)
        response = HttpResponse(
            "\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8"
        )
    elif fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font

        book = Workbook()
        sheet = book.active
        sheet.title = "Consulta"
        sheet.append([note])
        sheet.append(header)
        for row in values:
            sheet.append(row)
        for c in sheet[2]:
            c.font = Font(bold=True)
        from openpyxl.utils import get_column_letter

        for col in range(1, len(header) + 1):
            sheet.column_dimensions[get_column_letter(col)].width = 32
        sheet.freeze_panes = "A3"
        output = io.BytesIO()
        book.save(output)
        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    elif fmt in {"png", "svg", "pdf"}:
        # OO Matplotlib avoids global pyplot state in concurrent requests.
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        import textwrap

        figure = Figure(figsize=(12, 8), layout="constrained")
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        labels = payload["labels"]
        kind = params["chart"]
        colors = [
            "#177c70",
            "#de765c",
            "#748cb5",
            "#b49a52",
            "#8b77a9",
            "#60a2a2",
            "#bb7792",
            "#7c9561",
        ]
        datasets = payload["datasets"]
        if kind in {"pie", "doughnut"}:
            axes.pie(
                datasets[0]["data"],
                labels=labels,
                autopct="%1.1f%%",
                colors=colors,
                wedgeprops={"width": 0.45} if kind == "doughnut" else None,
            )
        elif kind == "bar":
            axes.barh(labels, datasets[0]["data"], color=colors[0])
            axes.invert_yaxis()
        elif kind == "line":
            axes.plot(labels, datasets[0]["data"], marker="o", color=colors[0])
        elif kind in {"grouped", "stacked", "percent"}:
            bottom = [0] * len(labels)
            for index, dataset in enumerate(datasets):
                x = (
                    [i + (-0.2 if index == 0 else 0.2) for i in range(len(labels))]
                    if kind == "grouped"
                    else list(range(len(labels)))
                )
                axes.bar(
                    x,
                    dataset["data"],
                    width=0.4 if kind == "grouped" else 0.75,
                    bottom=None if kind == "grouped" else bottom,
                    color=colors[index],
                    label=dataset["label"],
                )
                bottom = [a + b for a, b in zip(bottom, dataset["data"])]
            axes.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
            axes.legend()
        else:
            axes.bar(labels, datasets[0]["data"], color=colors[0])
            axes.tick_params(axis="x", rotation=60)
        axes.set_title(payload["title"] + " · " + payload["unit"])
        figure.suptitle("RNC / Cuba · " + payload["metric"], fontsize=15)
        figure.supxlabel(
            "\n".join(textwrap.wrap(note, 140)), fontsize=8, parse_math=False
        )
        output = io.BytesIO()
        if fmt == "pdf":
            from matplotlib.backends.backend_pdf import PdfPages

            with PdfPages(output) as pdf:
                pdf.savefig(figure)
                # Detail pages preserve category names, context and tabular values.
                for start in range(0, len(values), 12):
                    detail = Figure(figsize=(11.7, 8.3))
                    FigureCanvasAgg(detail)
                    detail.text(
                        0.06, 0.94, "RNC / Cuba · Detalle de consulta", fontsize=16
                    )
                    detail.text(
                        0.06,
                        0.88,
                        "\n".join(textwrap.wrap(note, 140)),
                        fontsize=8,
                        va="top",
                        parse_math=False,
                    )
                    ax = detail.add_axes([0.05, 0.1, 0.9, 0.64])
                    ax.axis("off")
                    cells = [
                        [
                            "\n".join(textwrap.wrap(str(v), 28 if i == 0 else 13))
                            for i, v in enumerate(row)
                        ]
                        for row in values[start : start + 12]
                    ]
                    grid = ax.table(
                        cellText=cells,
                        colLabels=["\n".join(textwrap.wrap(h, 16)) for h in header],
                        loc="upper center",
                        cellLoc="left",
                        colWidths=[0.30]
                        + [0.70 / (len(header) - 1)] * (len(header) - 1),
                    )
                    grid.auto_set_font_size(False)
                    grid.set_fontsize(9)
                    for (row, col), cell in grid.get_celld().items():
                        cell.set_edgecolor("#d6e3dd")
                        cell.set_height(0.065 if row else 0.14)
                        if row == 0:
                            cell.set_facecolor("#176b5d")
                            cell.set_text_props(color="white", weight="bold")
                        else:
                            cell.set_facecolor("#f0f5f1" if row % 2 else "white")
                    detail.text(
                        0.94,
                        0.05,
                        f"Detalle {start//12+1}",
                        ha="right",
                        fontsize=8,
                        color="#60756b",
                    )
                    pdf.savefig(detail)
        else:
            figure.savefig(output, format=fmt, dpi=160)
        response = HttpResponse(
            output.getvalue(),
            content_type={
                "png": "image/png",
                "svg": "image/svg+xml",
                "pdf": "application/pdf",
            }[fmt],
        )
    else:
        return HttpResponse("Formato no disponible", status=400)
    response["Content-Disposition"] = f'attachment; filename="{filename}.{fmt}"'
    response["Cache-Control"] = "no-store"
    return response
