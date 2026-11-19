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
    filename = str(_("rnc-query"))
    caveat = (
        _("Fuente: BD_2022 y población municipal de 2022. ")
        + _("Las tasas utilizan la población de las edades seleccionadas; el ajuste truncado normaliza los pesos de ese intervalo. ")
        + _("Personas distintas: valores únicos de NOCASO. VH: MORF distinto de 8000. SCD: UNIDIDAD igual a 0000.")
    )
    metadata = [
        (_("Fuente y corte"), payload["note"]),
        (_("Población analizada"), {"all": _("Todas las edades"), "adult": _("20 años o más"), "child": _("Menores de 20 años")}[params.get("cohort", "all")]),
        (_("SHA-256 CSV original"), payload.get("provenance", {}).get("original_csv_sha256", "")),
        (_("SHA-256 diccionario"), payload.get("provenance", {}).get("dictionary_docx_sha256", "")),
        (_("Archivo poblacional"), "POBLACION _2022.xlsx"),
        (_("SHA-256 población"), payload.get("provenance", {}).get("population_xlsx_sha256", "")),
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
        _("Tasa cruda/específica por %(scale)s · %(unit)s") % {"scale": payload.get("rate_scale_label", "100 000"), "unit": payload["unit"]},
        payload.get("adjusted_rate_label", _("Tasa ajustada Segi–Doll por 100 000")),
        _("Verificación histológica (%)"),
        _("Solo certificado de defunción (%)"),
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
                "vh_percent",
                "scd_percent",
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

        def draw_chart(labels, datasets, chart_table, page_label=""):
            kind = params["chart"]
            horizontal = kind in {"bar", "ranking", "strip", "swarm"} or (kind in {"grouped", "stacked", "percent"} and len(payload["labels"]) > 10)
            wrapped = ["\n".join(textwrap.wrap(str(label), 44)) for label in labels]
            row_inches = [max(1, label.count("\n") + 1) * .19 + .20 for label in wrapped]
            width = 17 if horizontal else min(36, max(12, len(labels) * .65)) if kind in {"line", "trend", "curve", "grouped", "stacked", "percent"} else 12
            height = max(7, max(row_inches, default=.4) * len(labels) + 3.2) if horizontal else 9
            figure = Figure(figsize=(width, height))
            FigureCanvasAgg(figure)
            axes = figure.subplots()
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
            def number_label(value):
                numeric = float(value)
                return number_format(
                    numeric,
                    decimal_pos=0 if numeric.is_integer() else 2,
                    use_l10n=True,
                    force_grouping=True,
                )

            if kind == "map":
                import math
                from matplotlib.path import Path as PlotPath
                from matplotlib.patches import PathPatch, Patch
                from .province_map import geometries, map_context, COLORS
                context = map_context(chart_table)
                by_name = {region["name"]: region for region in context["regions"]}
                ratio = math.cos(math.radians(22.5))
                for region in geometries():
                    vertices, codes = [], []
                    for polygon in region["polygons"]:
                        for ring in polygon:
                            vertices.extend((point[0] * ratio, point[1]) for point in ring)
                            codes.extend([PlotPath.MOVETO] + [PlotPath.LINETO] * (len(ring) - 2) + [PlotPath.CLOSEPOLY])
                    axes.add_patch(PathPatch(PlotPath(vertices, codes), facecolor=by_name[region["name"]]["color"], edgecolor="white", linewidth=.4))
                axes.autoscale_view()
                axes.set_aspect("equal")
                axes.set_axis_off()
                minimum, maximum = context["minimum"], context["maximum"]
                handles = [Patch(facecolor=color, label=f"{number_label(minimum + (maximum-minimum)*i/5)}–{number_label(minimum + (maximum-minimum)*(i+1)/5)}") for i, color in enumerate(COLORS)]
                handles.append(Patch(facecolor="#dedede", label=str(_("Sin datos"))))
                axes.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, -.12), ncol=3, fontsize=8)
                axes.text(.5, -.23, "geoBoundaries · © OpenStreetMap contributors / Wambacher · ODbL 1.0 · 2017", transform=axes.transAxes, ha="center", fontsize=8)
            elif kind == "table":
                axes.set_axis_off()
                figure.set_size_inches(22, max(9, sum(max(1, len(textwrap.wrap(row["display_label"], 40))) * .19 + .18 for row in chart_table) + 4))
                def table_number(value):
                    return number_label(value) if value is not None else "—"
                rendered_table = axes.table(
                    cellText=[[
                        "\n".join(textwrap.wrap(row["display_label"], 40)), table_number(row["tumors"]),
                        table_number(row["persons"]),
                        table_number(row["relative_frequency"]), table_number(row["population"]),
                        table_number(row["crude_rate"]), table_number(row["adjusted_rate"]),
                        table_number(row["vh_percent"]), table_number(row["scd_percent"]),
                    ] for row in chart_table],
                    colLabels=[str(_("Categoría")), str(_("Tumores")), str(_("Personas distintas")), str(_("Frecuencia relativa (%)")), str(_("Población denominadora")), str(_("Tasa cruda/específica")) + "\n" + str(_("por")) + " " + payload.get("rate_scale_label", "100 000"), str(payload.get("adjusted_rate_label", _("Tasa ajustada Segi–Doll"))), "VH (%)", "SCD (%)"],
                    colWidths=[.28,.065,.085,.085,.10,.11,.12,.075,.08],
                    cellLoc="left", loc="upper center",
                )
                rendered_table.auto_set_font_size(False)
                rendered_table.set_fontsize(9)
                rendered_table.scale(1, 1.4)
                for (row_index, col_index), cell in rendered_table.get_celld().items():
                    if row_index == 0:
                        cell.get_text().set_text("\n".join(textwrap.wrap(cell.get_text().get_text(), 17)))
                        cell.set_height(.9 / (figure.get_figheight()-2.5))
                    else:
                        line_count = max(1, len(textwrap.wrap(chart_table[row_index-1]["display_label"], 40)))
                        cell.set_height((line_count * .19 + .18) / (figure.get_figheight()-2.5))
            elif kind in {"pie", "doughnut"}:
                pie_values = datasets[0]["data"]
                pie_value_iter = iter(pie_values)

                def pie_label(pct):
                    value = next(pie_value_iter)
                    if pct < 5:
                        return ""
                    suffix = "%" if "(%)" in payload["metric"] else ""
                    return (
                        f"{number_label(value)}%"
                        if suffix
                        else f"{number_label(value)}\n({pct:.1f}%)"
                    )

                _wedges, _texts, pie_labels = axes.pie(
                    pie_values,
                    labels=None,
                    autopct=pie_label,
                    colors=colors,
                    wedgeprops={"width": 0.45} if kind == "doughnut" else None,
                )
                axes.legend(_wedges, ["\n".join(textwrap.wrap(str(label), 26)) for label in labels], loc="center left", bbox_to_anchor=(1, .5), fontsize=9)
                for index, text in enumerate(pie_labels):
                    text.set_color("#ffffff" if index == 0 else "#183f39")
            elif kind in {"bar", "ranking"}:
                bars = axes.barh(range(len(labels)), datasets[0]["data"], color=colors[0])
                axes.set_yticks(range(len(labels)), wrapped, fontsize=9)
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
                axes.set_yticks(range(len(labels)), wrapped, fontsize=9)
                axes.invert_yaxis()
                axes.set_xlabel(payload["axis_unit"])
                axes.set_ylabel(payload["dimension_label"])
                for x, y in zip(values_x, positions):
                    axes.annotate(number_label(x), (x, y), xytext=(6, 0), textcoords="offset points", va="center", fontsize=8)
                axes.grid(axis="x", alpha=0.2)
            elif kind in {"line", "trend", "curve"}:
                if kind == "curve" and len(labels) > 1:
                    values = datasets[0]["data"]
                    slopes = [b-a for a,b in zip(values, values[1:])]
                    tangents = [slopes[0]] + [2*a*b/(a+b) if a*b>0 else 0 for a,b in zip(slopes,slopes[1:])] + [slopes[-1]]
                    xx, yy = [], []
                    for index in range(len(values)-1):
                        for step in range(21):
                            u = step/20
                            xx.append(index+u)
                            yy.append((2*u**3-3*u**2+1)*values[index] + (u**3-2*u**2+u)*tangents[index] + (-2*u**3+3*u**2)*values[index+1] + (u**3-u**2)*tangents[index+1])
                    axes.plot(xx, yy, color=colors[0])
                    axes.scatter(range(len(values)), values, color=colors[0])
                    axes.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
                else:
                    axes.plot(labels, datasets[0]["data"], marker="o", color=colors[0])
                axes.margins(y=0.12)
                for x, value in enumerate(datasets[0]["data"]):
                    if x % max(1, len(labels) // 16):
                        continue
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
                    draw_bars = axes.barh if horizontal else axes.bar
                    bar_options = {"height": .4 if kind == "grouped" else .75, "left": None if kind == "grouped" else bottom} if horizontal else {"width": .4 if kind == "grouped" else .75, "bottom": None if kind == "grouped" else bottom}
                    bars = draw_bars(
                        x,
                        dataset["data"],
                        **bar_options,
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
                if horizontal:
                    axes.set_yticks(range(len(labels)), wrapped, fontsize=9)
                    axes.invert_yaxis()
                else:
                    axes.set_xticks(range(len(labels)), ["\n".join(textwrap.wrap(str(label), 18)) for label in labels], fontsize=9)
                axes.legend()
                axes.set_xlabel(payload["axis_unit"] if horizontal else payload["dimension_label"])
                axes.set_ylabel(payload["dimension_label"] if horizontal else (_("Porcentaje de cada categoría (%)") if kind == "percent" else payload["axis_unit"]))
                if kind == "percent":
                    (axes.set_xlim if horizontal else axes.set_ylim)(0, 100)
            else:
                bars = axes.bar(labels, datasets[0]["data"], color=colors[0])
                axes.bar_label(bars, labels=[number_label(v) if v else "" for v in datasets[0]["data"]], padding=4)
                axes.margins(y=0.12)
                axes.tick_params(axis="x", rotation=60)
                axes.set_xlabel(payload["dimension_label"])
                axes.set_ylabel(payload["axis_unit"])
            axes.set_title(payload["dimension_label"])
            figure.suptitle("RNC / Cuba · " + payload["metric"] + " · " + payload["unit"], fontsize=15, y=1-.22/figure.get_figheight(), va="top")
            width, height = figure.get_size_inches()
            footer = "\n".join(textwrap.wrap(str(payload["note"]) + " · " + str(payload["filter_summary"]) + " · " + str(caveat) + " · " + str(payload.get("display_note", "")), max(90, int(width * 12))))
            footer_inches = max(.9, .14 * len(footer.splitlines()) + .3)
            figure.subplots_adjust(left=5.9 / width if horizontal else .08, right=.95 if kind not in {"pie", "doughnut"} else .66, top=1-.95/height, bottom=footer_inches/height)
            if horizontal:
                axes.set_ylim(len(labels)-.4, -.6)
                axes.grid(axis="x", alpha=.15)
                axes.set_axisbelow(True)
            if kind not in {"map", "table", "pie", "doughnut"} and not horizontal:
                axes.tick_params(axis="x", labelsize=9)
            note = payload["note"] + " · " + payload["filter_summary"] + " · " + caveat
            if params["chart"] == "scatter":
                note += " · " + str(_("El tamaño o rótulo del punto indica cuántas categorías coinciden en las mismas coordenadas."))
            figure.text(
                0.5, .18 / height,
                footer,
                ha="center", va="bottom", fontsize=7, parse_math=False,
            )
            if page_label:
                axes.set_title(str(payload["dimension_label"]) + " · " + page_label)
            _apply_export_font_fallback(figure)
            return figure

        figure = draw_chart(payload["labels"], payload["datasets"], table)
        output = io.BytesIO()
        if fmt == "pdf":
            from matplotlib.backends.backend_pdf import PdfPages

            with PdfPages(output) as pdf:
                split_chart = params["chart"] in {"bar", "ranking", "strip", "swarm", "grouped", "stacked", "percent", "table"} and len(payload["labels"]) > 20
                if split_chart:
                    for first in range(0, len(payload["labels"]), 20):
                        end = min(first + 20, len(payload["labels"]))
                        sliced = [{**dataset, "data": dataset["data"][first:end]} for dataset in payload["datasets"]]
                        if params["chart"] in {"strip", "swarm"}:
                            sliced = [{**dataset, "data": [{**point, "y": point["y"]-first} for point in dataset["data"]]} for dataset in sliced]
                        page = draw_chart(payload["labels"][first:end], sliced, table[first:end], f"{first+1}–{end} / {len(payload['labels'])}")
                        if params["chart"] in {"bar", "ranking", "strip", "swarm", "grouped", "stacked", "percent"}:
                            page.axes[0].set_xlim(figure.axes[0].get_xlim())
                        pdf.savefig(page)
                        page.clear()
                else:
                    pdf.savefig(figure)
                # Detail pages preserve category names, context and tabular values.
                detail_pages, batch, used = [], [], 0
                for value_row in values:
                    cells = ["\n".join(textwrap.wrap(str(value) if value is not None else "—", 28 if column == 0 else 13)) for column, value in enumerate(value_row)]
                    row_inches = max(text.count("\n") + 1 for text in cells) * .14 + .15
                    if batch and (used + row_inches > 4.2 or len(batch) >= 12):
                        detail_pages.append(batch); batch, used = [], 0
                    batch.append((cells, row_inches)); used += row_inches
                if batch:
                    detail_pages.append(batch)
                for page_index, detail_rows in enumerate(detail_pages):
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
                    cells = [row[0] for row in detail_rows]
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
                        cell.set_height(detail_rows[row-1][1] / (8.3 * .64) if row else .95 / (8.3 * .64))
                        if row == 0:
                            cell.set_facecolor("#176b5d")
                            cell.set_text_props(color="white", weight="bold")
                        else:
                            cell.set_facecolor("#f0f5f1" if row % 2 else "white")
                    detail.text(
                        0.94,
                        0.05,
                        str(_("Detalle %(page)s")) % {"page": page_index + 1},
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
                import math
                width, height = figure.get_size_inches()
                dpi = min(160, 16000 / max(width, height), math.sqrt(40000000 / (width * height)))
                figure.savefig(output, format=fmt, dpi=dpi)
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
