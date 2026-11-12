"""Aggregate-only image, PDF and spreadsheet renderers."""

import csv
import io
from django.http import HttpResponse
from django.utils.formats import number_format
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _


def _apply_export_font_fallback(figure):
    """Choose installed Unicode fonts for labels in translated chart exports."""
    from matplotlib.font_manager import FontProperties, fontManager
    from matplotlib.table import Cell
    from matplotlib.text import Text

    candidates = (
        "DejaVu Sans",
        "Noto Sans CJK SC",
        "Noto Sans Devanagari",
        "Noto Sans Bengali",
        "Noto Sans Arabic",
        "Noto Naskh Arabic",
        "Noto Nastaliq Urdu",
    )
    families = []
    for family in candidates:
        try:
            fontManager.findfont(
                FontProperties(family=[family]), fallback_to_default=False
            )
        except ValueError:
            continue
        families.append(family)
    if not families:
        return
    for artist in figure.findobj():
        if isinstance(artist, Text):
            artist.set_fontfamily(families)
        elif isinstance(artist, Cell):
            artist.get_text().set_fontfamily(families)


def export_result(fmt, table, payload, params):
    filename = str(_("rnc-synthetic-query"))
    caveat = (
        _("Métodos candidatos; denominadores sintéticos, no son resultados oficiales. ")
        + _("Las tasas se calculan con la unidad elegida; los grupos de localización pueden solaparse en personas distintas. ")
        + _("Al combinar años, la población denominadora acumula las poblaciones anuales seleccionadas.")
    )
    metadata = [
        (_("Fuente y corte"), payload["note"]),
        (_("Año de incidencia"), next((f["value"] for f in payload["filters"] if f.get("key") == "year"), _("Todos"))),
        (_("Provincia de residencia"), next((f["value"] for f in payload["filters"] if f.get("key") == "territory"), _("Todas las provincias"))),
        (_("Municipio de residencia"), next((f["value"] for f in payload["filters"] if f.get("key") == "municipality"), _("Todos los municipios"))),
        (_("Sexo"), next((f["value"] for f in payload["filters"] if f.get("key") == "sex"), _("Todos"))),
        (_("Edad"), next((f["value"] for f in payload["filters"] if f.get("key") == "age"), _("Todos"))),
        (_("Grupo de localización"), next((f["value"] for f in payload["filters"] if f.get("key") == "site"), _("Todos"))),
        (_("Agrupación"), payload["dimension_label"]),
        (_("Indicador del gráfico"), payload["metric"]),
        (_("Unidad"), payload["unit"]),
        (_("Gráfico"), payload["chart_label"]),
        (_("Nota"), caveat),
    ]
    header = [
        _("Categoría"),
        _("Tumores (frecuencia absoluta)"),
        _("Personas distintas (frecuencia absoluta)"),
        _("Población denominadora"),
        _("Frecuencia relativa (%%) · %(unit)s") % {"unit": payload["unit"]},
        _("Tasa cruda/específica por 100 000 · %(unit)s") % {"unit": payload["unit"]},
        _("Tasa ajustada Segi–Doll por 100 000 · %(unit)s") % {"unit": payload["unit"]},
    ]
    values = [
        [
            r[k]
            for k in [
                "display_label",
                "tumors",
                "persons",
                "population",
                "relative_frequency",
                "crude_rate",
                "adjusted_rate",
            ]
        ]
        for r in table
    ]
    if params["chart"] == "ranking":
        header.insert(0, _("Posición"))
        values = [[r["rank"]] + row for r, row in zip(table, values)]
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

    # Resolve gettext_lazy labels at the export boundary. openpyxl rejects
    # Django Promise objects, while CSV/Matplotlib should receive plain strings.
    def resolve(row):
        return [str(value) if isinstance(value, Promise) else value for value in row]

    metadata = [resolve(row) for row in metadata]
    header = resolve(header)
    values = [resolve(row) for row in values]
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([str(_("Contexto de la consulta")), str(_("Selección"))])
        writer.writerows(metadata)
        writer.writerow([])
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
        sheet.title = str(_("Consulta"))
        sheet.append([str(_("Contexto de la consulta")), str(_("Selección"))])
        for row in metadata:
            sheet.append(row)
        sheet.append([])
        sheet.append(header)
        for row in values:
            sheet.append(row)
        header_row = len(metadata) + 3
        for c in sheet[header_row]:
            c.font = Font(bold=True)
        from openpyxl.utils import get_column_letter

        for col in range(1, len(header) + 1):
            sheet.column_dimensions[get_column_letter(col)].width = 36 if col == 1 else 32
        sheet.freeze_panes = f"A{header_row + 1}"
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

        figure = Figure(figsize=(12, 9))
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
        def number_label(value):
            numeric = float(value)
            return number_format(
                numeric,
                decimal_pos=0 if numeric.is_integer() else 2,
                use_l10n=True,
                force_grouping=True,
            )

        if kind in {"pie", "doughnut"}:
            pie_values = datasets[0]["data"]
            pie_value_iter = iter(pie_values)

            def pie_label(pct):
                value = next(pie_value_iter)
                suffix = "%" if "(%)" in payload["metric"] else ""
                return (
                    f"{number_label(value)}%"
                    if suffix
                    else f"{number_label(value)}\n({pct:.1f}%)"
                )

            _wedges, _texts, pie_labels = axes.pie(
                pie_values,
                labels=labels,
                autopct=pie_label,
                colors=colors,
                wedgeprops={"width": 0.45} if kind == "doughnut" else None,
            )
            for index, text in enumerate(pie_labels):
                text.set_color("#ffffff" if index == 0 else "#183f39")
        elif kind in {"bar", "ranking"}:
            bars = axes.barh(labels, datasets[0]["data"], color=colors[0])
            axes.bar_label(bars, labels=[number_label(v) if v else "" for v in datasets[0]["data"]], padding=4)
            axes.margins(x=0.12)
            axes.invert_yaxis()
            axes.set_xlabel(payload["axis_unit"])
            axes.set_ylabel(payload["dimension_label"])
        elif kind == "scatter":
            grouped_points = {}
            for point in datasets[0]["data"]:
                key = (point["x"], point["y"])
                grouped_points.setdefault(key, []).append(point["category"])
            point_data = [
                {"x": x, "y": y, "categories": categories}
                for (x, y), categories in grouped_points.items()
            ]
            values_x = [point["x"] for point in point_data]
            values_y = [point["y"] for point in point_data]
            sizes = [min(220, 48 + 24 * (len(point["categories"]) - 1)) for point in point_data]
            axes.scatter(
                values_x, values_y, color=colors[0], s=sizes, alpha=0.78,
                edgecolors="#ffffff", linewidths=1, zorder=3,
            )
            axes.set_xlabel(payload["axis_unit"])
            axes.set_ylabel(payload["y_axis_unit"])
            for point in point_data:
                count = len(point["categories"])
                if count > 1:
                    axes.annotate(
                        f"×{count}", (point["x"], point["y"]), xytext=(6, 5),
                        textcoords="offset points", fontsize=8, fontweight="bold",
                    )
            axes.grid(alpha=0.2)
        elif kind in {"strip", "swarm"}:
            point_data = datasets[0]["data"]
            values_x = [point["x"] for point in point_data]
            positions = [point["y"] for point in point_data]
            axes.scatter(values_x, positions, color=colors[0], s=48, zorder=3)
            axes.set_yticks(range(len(labels)), labels)
            axes.invert_yaxis()
            axes.set_xlabel(payload["axis_unit"])
            axes.set_ylabel(payload["dimension_label"])
            for x, y in zip(values_x, positions):
                axes.annotate(number_label(x), (x, y), xytext=(6, 0), textcoords="offset points", va="center", fontsize=8)
            axes.grid(axis="x", alpha=0.2)
        elif kind == "line":
            axes.plot(labels, datasets[0]["data"], marker="o", color=colors[0])
            axes.margins(y=0.12)
            for x, value in enumerate(datasets[0]["data"]):
                axes.annotate(number_label(value), (x, value), xytext=(0, 8), textcoords="offset points", ha="center")
            axes.set_xlabel(payload["dimension_label"])
            axes.set_ylabel(payload["axis_unit"])
        elif kind in {"grouped", "stacked", "percent"}:
            bottom = [0] * len(labels)
            for index, dataset in enumerate(datasets):
                x = (
                    [i + (-0.2 if index == 0 else 0.2) for i in range(len(labels))]
                    if kind == "grouped"
                    else list(range(len(labels)))
                )
                bars = axes.bar(
                    x,
                    dataset["data"],
                    width=0.4 if kind == "grouped" else 0.75,
                    bottom=None if kind == "grouped" else bottom,
                    color=colors[index],
                    label=dataset["label"],
                )
                shown_values = [
                    (number_label(value) + ("%" if kind == "percent" else ""))
                    if value and (kind != "percent" or value >= 6)
                    else ""
                    for value in dataset["data"]
                ]
                axes.bar_label(
                    bars,
                    labels=shown_values,
                    label_type="center" if kind in {"stacked", "percent"} else "edge",
                    padding=3,
                    fontsize=8,
                    color=("#ffffff" if index == 0 else "#183f39")
                    if kind in {"stacked", "percent"}
                    else "#183f39",
                )
                bottom = [a + b for a, b in zip(bottom, dataset["data"])]
            axes.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
            axes.legend()
            axes.set_xlabel(payload["dimension_label"])
            axes.set_ylabel(_("Porcentaje de cada categoría (%)") if kind == "percent" else payload["axis_unit"])
            if kind == "percent":
                axes.set_ylim(0, 100)
        else:
            bars = axes.bar(labels, datasets[0]["data"], color=colors[0])
            axes.bar_label(bars, labels=[number_label(v) if v else "" for v in datasets[0]["data"]], padding=4)
            axes.margins(y=0.12)
            axes.tick_params(axis="x", rotation=60)
            axes.set_xlabel(payload["dimension_label"])
            axes.set_ylabel(payload["axis_unit"])
        axes.set_title(payload["dimension_label"])
        figure.suptitle("RNC / Cuba · " + payload["metric"] + " · " + payload["unit"], fontsize=15)
        figure.subplots_adjust(left=0.25, right=0.97, top=0.87, bottom=0.30)
        note = payload["note"] + " · " + payload["filter_summary"] + " · " + caveat
        if params["chart"] == "scatter":
            note += " · " + str(_("El tamaño o rótulo del punto indica cuántas categorías coinciden en las mismas coordenadas."))
        figure.text(
            0.5, 0.035,
            "\n".join(textwrap.wrap(note, 150)),
            ha="center", va="bottom", fontsize=7, parse_math=False,
        )
        _apply_export_font_fallback(figure)
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
                        0.06, 0.94, str(_("RNC / Cuba · Detalle de consulta")), fontsize=16
                    )
                    detail.text(
                        0.06,
                        0.88,
                        "\n".join(textwrap.wrap(payload["note"] + " · " + payload["filter_summary"] + " · " + caveat, 140)),
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
                    detail_row_height = min(0.11, 0.78 / max(len(cells), 1))
                    for (row, col), cell in grid.get_celld().items():
                        cell.set_edgecolor("#d6e3dd")
                        cell.set_height(detail_row_height if row else 0.14)
                        if row == 0:
                            cell.set_facecolor("#176b5d")
                            cell.set_text_props(color="white", weight="bold")
                        else:
                            cell.set_facecolor("#f0f5f1" if row % 2 else "white")
                    detail.text(
                        0.94,
                        0.05,
                        str(_("Detalle %(page)s")) % {"page": start // 12 + 1},
                        ha="right",
                        fontsize=8,
                        color="#60756b",
                    )
                    _apply_export_font_fallback(detail)
                    pdf.savefig(detail)
        else:
            context_text = payload["note"] + " · " + payload["filter_summary"]
            if fmt == "svg":
                import matplotlib

                with matplotlib.rc_context({"svg.fonttype": "none"}):
                    figure.savefig(
                        output,
                        format=fmt,
                        dpi=160,
                        metadata={"Description": context_text},
                    )
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
        return HttpResponse(_("Formato no disponible"), status=400)
    response["Content-Disposition"] = f'attachment; filename="{filename}.{fmt}"'
    response["Cache-Control"] = "no-store"
    return response
