import os
import pandas as pd
from trame.app import get_server
from trame.ui.vuetify import SinglePageLayout
from trame.widgets import vuetify, vtk as vtk_widgets, html
import numpy as np
import vtk as standard_vtk
import io


class ScatterplotApp:
    def __init__(self, csv_file_path, port: int = 8080, remote_rendering: bool = True):
        self.server = get_server(client_type="vue2")
        self.state, self.ctrl = self.server.state, self.server.controller
        self.port = port
        self._remote_rendering = remote_rendering
        self.ctrl.update_plot = self.update_plot
        self.ctrl.on_x_change = self.on_x_change
        self.ctrl.on_y_change = self.on_y_change
        self.ctrl.on_point_selected = self.on_point_selected
        self.ctrl.on_table_selection_change = self.on_table_selection_change
        self.ctrl.on_file_drop = self.on_file_drop

        if not os.path.exists(csv_file_path):
            raise FileNotFoundError(f"The file '{csv_file_path}' does not exist.")

        self.csv_file_path = csv_file_path
        self.df = pd.read_csv(csv_file_path)
        self.column_names = self.df.columns.tolist()

        self._precalculate_data_ranges()

        self.state.selected_x = None
        self.state.selected_y = None
        self.state.headers = []
        self.state.items = []
        self.state.page = 1
        self.state.itemsPerPage = 10
        self.state.selected = []

        if len(self.column_names) >= 2:
            self.state.selected_x = self.column_names[0]
            self.state.selected_y = self.column_names[1]

        self.server.state.x_options = self.column_names
        self.server.state.y_options = self.column_names

        self.table = None
        self.points = None
        self.selected_point_table = None
        self.selected_point_plot = None
        self.chart = None
        self.view = None
        self.renderWindow = None
        self.last_selected_point_index = -1
        self.highlighted_points = set()

        self._init_vtk_scatterplot()
        self._setup_ui()

        self._update_vtk_table()
        self._update_data_table()

        if self._remote_rendering:
            self.client_view = vtk_widgets.VtkRemoteView(self.renderWindow, trame_server=self.server, ref="scatter_view")
        else:
            self.client_view = vtk_widgets.VtkLocalView(self.renderWindow, trame_server=self.server)

        self.ctrl.scatter_view_update = self.client_view.update
        self._setup_point_selection()

    def on_file_drop(self, files):
        if not files:
            return

        uploaded_file = files[0]
        content = uploaded_file.get("content")

        if content:
            try:
                bytes_io = io.BytesIO(content)
                new_df = pd.read_csv(bytes_io)
                self._reset_with_new_data(new_df)
                print(f"Successfully loaded new dataset: {uploaded_file.get('name')}")
            except Exception as e:
                print(f"Error processing uploaded file: {e}")

    def _reset_with_new_data(self, df):
        self.df = df
        self.column_names = self.df.columns.tolist()
        self._precalculate_data_ranges()
        self.server.state.x_options = self.column_names
        self.server.state.y_options = self.column_names

        if len(self.column_names) >= 2:
            self.state.selected_x = self.column_names[0]
            self.state.selected_y = self.column_names[1]
        elif len(self.column_names) == 1:
            self.state.selected_x = self.column_names[0]
            self.state.selected_y = self.column_names[0]
        else:
            self.state.selected_x = None
            self.state.selected_y = None

        self.update_plot()

    def _precalculate_data_ranges(self):
        self.data_ranges = {}
        numeric_columns = self.df.select_dtypes(include=[np.number]).columns.tolist()

        for column in numeric_columns:
            valid_values = self.df[column].dropna().values
            if len(valid_values) > 0:
                min_val = float(np.min(valid_values))
                max_val = float(np.max(valid_values))
                padding = (max_val - min_val) * 0.1 if max_val > min_val else 0.5
                self.data_ranges[column] = {
                    'min': min_val - padding,
                    'max': max_val + padding
                }
            else:
                self.data_ranges[column] = {'min': 0, 'max': 10}

    def on_x_change(self, x_value, **kwargs):
        self.state.selected_x = x_value

    def on_y_change(self, y_value, **kwargs):
        self.state.selected_y = y_value

    def on_point_selected(self, point_index, **kwargs):
        if point_index >= 0 and point_index < len(self.valid_points):
            if point_index in self.highlighted_points:
                self.highlighted_points.remove(point_index)
                for selected_item in self.state.selected:
                    if selected_item.get('id') == point_index:
                        self.state.selected.remove(selected_item)
                        break
            else:
                self.highlighted_points.add(point_index)
                table_item = self.state.items[point_index]
                if table_item not in self.state.selected:
                    self.state.selected.append(table_item)

            self._update_selected_point_highlight()

            if self.highlighted_points:
                first_point = min(self.highlighted_points)
                page_index = first_point // self.state.itemsPerPage + 1
                if page_index != self.state.page:
                    self.state.page = page_index

    def on_table_selection_change(self, selected_items, **kwargs):
        self.highlighted_points = set()
        point_indices = []
        for item in selected_items:
            if 'id' in item:
                point_index = item['id']
                point_indices.append(point_index)
                self.highlighted_points.add(point_index)

        self._update_selected_point_highlight(point_indices)

    def _init_vtk_scatterplot(self):
        self.table = standard_vtk.vtkTable()
        self._update_vtk_table()

        self.selected_point_table = standard_vtk.vtkTable()
        arrX = standard_vtk.vtkFloatArray()
        arrX.SetName("X Axis")
        self.selected_point_table.AddColumn(arrX)
        arrY = standard_vtk.vtkFloatArray()
        arrY.SetName("Y Axis")
        self.selected_point_table.AddColumn(arrY)

        self.chart = standard_vtk.vtkChartXY()
        self.points = self.chart.AddPlot(standard_vtk.vtkChart.POINTS)
        self.points.SetInputData(self.table, 0, 1)
        self.points.SetColor(0, 0, 0, 255)
        self.points.SetWidth(2.0)
        self.points.SetMarkerStyle(standard_vtk.vtkPlotPoints.CIRCLE)
        self.points.SetMarkerSize(10)

        self.selected_point_plot = self.chart.AddPlot(standard_vtk.vtkChart.POINTS)
        self.selected_point_plot.SetInputData(self.selected_point_table, 0, 1)
        self.selected_point_plot.SetColor(255, 0, 0, 255)
        self.selected_point_plot.SetWidth(5.0)
        self.selected_point_plot.SetMarkerStyle(standard_vtk.vtkPlotPoints.CROSS)
        self.selected_point_plot.SetMarkerSize(20)

        self.chart.SetSelectionMethod(standard_vtk.vtkChart.SELECTION_PLOTS)

        self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM).SetBehavior(standard_vtk.vtkAxis.FIXED)
        self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetBehavior(standard_vtk.vtkAxis.FIXED)

        self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM).SetRange(0, 11)
        self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetRange(0, 6)

        self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM).SetGridVisible(True)
        self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetGridVisible(True)

        self.view = standard_vtk.vtkContextView()
        self.view.GetScene().AddItem(self.chart)
        self.renderWindow = self.view.GetRenderWindow()
        self.renderWindow.SetSize(800, 600)

    def _setup_point_selection(self):
        self.chart.AddObserver(standard_vtk.vtkCommand.SelectionChangedEvent, self._handle_selection_event)

    def _handle_selection_event(self, obj, event):
        selection = self.chart.GetSelectionPlots()
        if selection.GetNumberOfItems() > 0:
            plot_selection = selection.GetItem(0)
            if plot_selection and plot_selection.GetNumberOfTuples() > 0:
                point_index = plot_selection.GetValue(0)
                self.on_point_selected(point_index)
        else:
            self.on_point_selected(-1)

    def _update_vtk_table(self):
        self.table.Initialize()
        arrX = standard_vtk.vtkFloatArray()
        arrX.SetName("X Axis")
        arrY = standard_vtk.vtkFloatArray()
        arrY.SetName("Y Axis")

        selected_x = self.state.selected_x
        selected_y = self.state.selected_y

        self.valid_points = []

        if selected_x and selected_y and selected_x in self.df.columns and selected_y in self.df.columns:
            x_data = self.df[selected_x].values
            y_data = self.df[selected_y].values

            for idx, (x, y) in enumerate(zip(x_data, y_data)):
                if pd.notna(x) and pd.notna(y):
                    try:
                        x_float = float(x)
                        y_float = float(y)
                        self.valid_points.append({
                            "index": idx,
                            "x": x_float,
                            "y": y_float,
                        })
                        arrX.InsertNextValue(x_float)
                        arrY.InsertNextValue(y_float)
                    except (ValueError, TypeError):
                        continue

        self.table.AddColumn(arrX)
        self.table.AddColumn(arrY)

    def _update_data_table(self):
        self.state.headers = []
        for col in self.df.columns:
            label = col
            if col == self.state.selected_x:
                label += " (X)"
            if col == self.state.selected_y:
                label += " (Y)"
            self.state.headers.append({"text": label, "value": col})

        table_data = []
        if hasattr(self, 'valid_points') and self.valid_points:
            for i, point in enumerate(self.valid_points):
                row = {"id": i}
                original_df_index = point["index"]
                for col in self.df.columns:
                    val = self.df.at[original_df_index, col]
                    row[col] = f"{val:.4f}" if isinstance(val, float) else str(val)
                table_data.append(row)

        self.state.items = table_data

    def _update_selected_point_highlight(self, point_indices=None):
        if isinstance(point_indices, int):
            point_indices = [point_indices] if point_indices >= 0 else []
        elif point_indices is None:
            point_indices = list(self.highlighted_points)

        self.selected_point_table.Initialize()
        arrX = standard_vtk.vtkFloatArray()
        arrX.SetName("X Axis")
        arrY = standard_vtk.vtkFloatArray()
        arrY.SetName("Y Axis")

        for idx in point_indices:
            if 0 <= idx < len(self.valid_points):
                point = self.valid_points[idx]
                arrX.InsertNextValue(point["x"])
                arrY.InsertNextValue(point["y"])
                self.highlighted_points.add(idx)

        self.selected_point_table.AddColumn(arrX)
        self.selected_point_table.AddColumn(arrY)

        self.selected_point_table.Modified()
        self.selected_point_plot.Modified()
        self.renderWindow.Render()
        self.ctrl.scatter_view_update()

    def update_plot(self, **kwargs):
        if self.state.selected_x and self.state.selected_y:
            self._update_vtk_table()
            self._update_data_table()
            self.table.Modified()
            self.points.Modified()

            x_column = self.state.selected_x
            y_column = self.state.selected_y

            if x_column in self.data_ranges:
                r = self.data_ranges[x_column]
                self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM).SetRange(r['min'], r['max'])

            if y_column in self.data_ranges:
                r = self.data_ranges[y_column]
                self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetRange(r['min'], r['max'])

            self.chart.RecalculateBounds()
            self.state.selected = []
            self.highlighted_points = set()
            self._update_selected_point_highlight([])
            self.renderWindow.Render()
            self.ctrl.scatter_view_update()

    def _setup_ui(self):
        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("Interactive Scatterplot")

            with layout.toolbar:
                vuetify.VSpacer()

                html.Input(
                    type="file",
                    ref="file_input",
                    change=(self.ctrl.on_file_drop, "[$event]"),
                    accept=".pdf,.csv,.xlsx,.JSON",
                    style="display: none;",
                )
                vuetify.VBtn(
                    "Upload File",
                    click="$refs.file_input.click()",
                    color="secondary",
                    classes="mr-2",
                    small=True,
                )

                vuetify.VSelect(label="X Axis", items=("x_options", []), v_model=("selected_x", None),
                                dense=True, hide_details=True, style="max-width: 200px",
                                change=(self.ctrl.on_x_change, "[$event]"))
                vuetify.VSelect(label="Y Axis", items=("y_options", []), v_model=("selected_y", None),
                                dense=True, hide_details=True, style="max-width: 200px",
                                change=(self.ctrl.on_y_change, "[$event]"))
                vuetify.VBtn("UPDATE PLOT", click=self.ctrl.update_plot, color="primary", class_="mx-3")

            with layout.content:
                with vuetify.VContainer(fluid=True, style="height: calc(100vh - 64px); padding: 0;"):
                    with vuetify.VRow(style="height: 100%; margin: 0;"):
                        with vuetify.VCol(cols=12, style="height: 50%; padding: 8px; min-height: 400px;"):
                            with vuetify.VCard(flat=True, style="height: 100%; display: flex; flex-direction: column;"):
                                vuetify.VCardTitle("Scatterplot (click on points to highlight)")
                                with vuetify.VCardText(style="flex: 1; position: relative; padding-bottom: 16px;"):
                                    vtk_widgets.VtkRemoteView(
                                        self.renderWindow,
                                        ref="scatter_view",
                                        interactive_quality=100,
                                        interactive_ratio=1,
                                        style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;",
                                    )

                        with vuetify.VCol(cols=12, style="height: 50%; padding: 8px; overflow-y: auto;"):
                            with vuetify.VCard(flat=True, style="height: 100%; display: flex; flex-direction: column;"):
                                vuetify.VCardTitle("Diagram data points table")
                                with vuetify.VCardText(style="flex: 1; overflow-y: auto; max-height: 100%;"):
                                    vuetify.VDataTable(
                                        headers=("headers", []),
                                        items=("items", []),
                                        v_model=("selected", []),
                                        input=(self.ctrl.on_table_selection_change, "[$event]"),
                                        dense=True,
                                        footer_props={"items-per-page-options": [10, 25, 50, 100]},
                                        items_per_page=("itemsPerPage", 10),
                                        page=("page", 1),
                                        multi_sort=True,
                                        class_="elevation-1",
                                        show_select=True,
                                        item_key="id",
                                    )

    def start_now(self):
        self.server.start(port=self.port)

    def stop(self):
        self.server.stop()


if __name__ == "__main__":
    csv_file_path = "/home/minhnguyen/Minh/MaxSlices_Manuf.csv"
    app = ScatterplotApp(csv_file_path, remote_rendering=True)
    app.start_now()