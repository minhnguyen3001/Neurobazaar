import os
import io
import json
import numpy as np
import pandas as pd
import vtk as standard_vtk
from time import perf_counter
from datetime import datetime
from trame.app import get_server
from trame.ui.vuetify import SinglePageLayout
from trame.widgets import vuetify, vtk as vtk_widgets, html


class LatencyTracker:

    def __init__(self):
        self.measurements = {}
        self.log_file = f"latency_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    def record(self, operation, latency_ms):
        if operation not in self.measurements:
            self.measurements[operation] = []
        self.measurements[operation].append(latency_ms)

    def get_stats(self, operation):
        if operation not in self.measurements or not self.measurements[operation]:
            return None
        data = self.measurements[operation]
        return {
            'count': len(data),
            'min': min(data),
            'max': max(data),
            'avg': sum(data) / len(data),
            'last': data[-1]
        }

    def print_summary(self):
        print("\n" + "=" * 70)
        print("CUMULATIVE LATENCY STATISTICS (ms)")
        print("=" * 70)
        print(f"{'Operation':<35} {'Count':>6} {'Min':>8} {'Max':>8} {'Avg':>8} {'Last':>8}")
        print("-" * 70)
        for op in sorted(self.measurements.keys()):
            stats = self.get_stats(op)
            if stats:
                print(f"{op:<35} {stats['count']:>6} {stats['min']:>8.2f} {stats['max']:>8.2f} "
                      f"{stats['avg']:>8.2f} {stats['last']:>8.2f}")
        print("=" * 70 + "\n")

    def save_to_file(self):
        data = {
            'timestamp': datetime.now().isoformat(),
            'measurements': self.measurements,
            'statistics': {op: self.get_stats(op) for op in self.measurements}
        }
        with open(self.log_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Latency data saved to: {self.log_file}")


class BarGraphApp:

    def __init__(self, csv_file_path, port: int = 8080, remote_rendering: bool = True):
        self.latency_tracker = LatencyTracker()
        startup_start = perf_counter()

        self.server = get_server(client_type="vue2")
        self.state, self.ctrl = self.server.state, self.server.controller
        self.port = port
        self._remote_rendering = remote_rendering
        self.ctrl.update_plot = self.update_plot
        self.ctrl.on_category_change = self.on_category_change
        self.ctrl.on_bar_selected = self.on_bar_selected
        self.ctrl.on_table_selection_change = self.on_table_selection_change
        self.ctrl.on_file_drop = self.on_file_drop
        self.ctrl.print_latency_stats = self.print_latency_stats
        self.ctrl.save_latency_data = self.save_latency_data
        self.ctrl.clear_selection = self.clear_selection
        self.ctrl.show_all_bars = self.show_all_bars
        self.ctrl.show_selected_only = self.show_selected_only

        # ------------------------
        # Load file
        # ------------------------
        start = perf_counter()
        if not os.path.exists(csv_file_path):
            raise FileNotFoundError(f"The file '{csv_file_path}' does not exist.")
        self.csv_file_path = csv_file_path

        if csv_file_path.endswith('.xlsx') or csv_file_path.endswith('.xls'):
            self.df = pd.read_excel(csv_file_path)
        else:
            try:
                self.df = pd.read_csv(csv_file_path)
            except UnicodeDecodeError:
                try:
                    self.df = pd.read_csv(csv_file_path, encoding='latin-1')
                except UnicodeDecodeError:
                    self.df = pd.read_csv(csv_file_path, encoding='iso-8859-1')

        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Startup: File load", latency)
        print(f"[Startup: File load]: {latency:.3f} ms")

        start = perf_counter()
        self.column_names = self.df.columns.tolist()
        self._precalculate_data_ranges()

        self.suitable_columns = self._filter_suitable_columns()
        self.unsuitable_columns = [col for col in self.column_names if col not in self.suitable_columns]

        if self.unsuitable_columns:
            print(f"\nNote: {len(self.unsuitable_columns)} columns excluded (contain text/sentences):")
            for col in self.unsuitable_columns[:5]:
                print(f"  - {col}")
            if len(self.unsuitable_columns) > 5:
                print(f"  ... and {len(self.unsuitable_columns) - 5} more")

        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Startup: Precalculate ranges", latency)
        print(f"[Startup: Precalculate ranges]: {latency:.3f} ms")

        # Initialize state
        self.state.selected_category = self.suitable_columns[0] if len(self.suitable_columns) >= 1 else None
        self.state.headers = []
        self.state.items = []
        self.state.page = 1
        self.state.itemsPerPage = 10
        self.state.selected = []
        self.state.bin_size = 1

        self.state.column_warning = ""
        self.state.show_warning = False

        # Filter mode state
        self.state.filter_mode = False
        self.state.selection_count = 0

        self._is_highlighting = False
        self._selection_start = None
        self._is_selecting = False
        self._last_hover_bar = -1

        self.server.state.category_options = self.suitable_columns

        # ------------------------
        # VTK
        # ------------------------
        self.table = None
        self.bars = None
        self.chart = None
        self.view = None
        self.renderWindow = None
        self.renderWindowInteractor = None
        self.color_array = None
        self.last_selected_bar_index = -1
        self.highlighted_bars = set()

        # Hover tooltip
        self.tooltip_actor = None

        start = perf_counter()
        self._init_vtk_bargraph()
        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Startup: VTK initialization", latency)
        print(f"[Startup: VTK initialization]: {latency:.3f} ms")

        start = perf_counter()
        self._setup_ui()
        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Startup: UI setup", latency)
        print(f"[Startup: UI setup]: {latency:.3f} ms")

        # ------------------------
        # Initial data update
        # ------------------------
        start = perf_counter()
        self._update_vtk_table()
        self._update_data_table()
        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Startup: Initial data update", latency)
        print(f"[Startup: Initial data update]: {latency:.3f} ms")

        # ------------------------
        # Remote/local view
        # ------------------------
        start = perf_counter()
        if self._remote_rendering:
            self.client_view = vtk_widgets.VtkRemoteView(self.renderWindow, trame_server=self.server, ref="bar_view")
        else:
            self.client_view = vtk_widgets.VtkLocalView(self.renderWindow, trame_server=self.server)
        self.ctrl.bar_view_update = self.client_view.update

        # Setup interactions
        self._setup_bar_selection()
        self._setup_interactions()

        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Startup: VTK view setup", latency)
        print(f"[Startup: VTK view setup]: {latency:.3f} ms")

        start = perf_counter()
        self.update_plot()
        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Startup: Initial plot render", latency)
        print(f"[Startup: Initial plot render]: {latency:.3f} ms")

        total_startup = (perf_counter() - startup_start) * 1000
        self.latency_tracker.record("Startup: TOTAL", total_startup)
        print(f"\n{'=' * 50}")
        print(f"TOTAL STARTUP TIME: {total_startup:.3f} ms")
        print(f"{'=' * 50}\n")


    def _is_suitable_for_bargraph(self, column_name):
        if column_name not in self.df.columns:
            return False

        column_data = self.df[column_name].dropna()
        if len(column_data) == 0:
            return False

        try:
            numeric_data = pd.to_numeric(column_data, errors='coerce').dropna()
            if len(numeric_data) > 0 and len(numeric_data) == len(column_data):
                return True
        except:
            pass

        unique_count = column_data.nunique()
        total_count = len(column_data)

        if unique_count > min(100, total_count * 0.5):
            return False

        avg_length = column_data.astype(str).str.len().mean()
        if avg_length > 50:
            return False

        sample_values = column_data.astype(str).head(10)
        sentence_indicators = 0
        for val in sample_values:
            if any(indicator in val for indicator in ['. ', '? ', '! ', ' the ', ' and ', ' is ', ' are ', ' was ']):
                sentence_indicators += 1

        if sentence_indicators > len(sample_values) * 0.3:
            return False

        return True

    def _filter_suitable_columns(self):
        suitable_columns = []
        for col in self.column_names:
            if self._is_suitable_for_bargraph(col):
                suitable_columns.append(col)
        return suitable_columns

    # ------------------------
    # Latency reporting
    # ------------------------
    def print_latency_stats(self):
        self.latency_tracker.print_summary()

    def save_latency_data(self):
        self.latency_tracker.save_to_file()

    # ------------------------
    # View mode controls
    # ------------------------
    def clear_selection(self):
        """Clear all selected bars"""
        print("[Clear Selection] Clearing all selections")
        self.highlighted_bars = set()
        self.state.selected = []
        self.state.selection_count = 0
        self.state.filter_mode = False
        self.update_plot()
        print("[Clear Selection] Done")

    def show_all_bars(self):
        """Show all bars (exit filter mode)"""
        print("[Show All] Exiting filter mode")
        self.state.filter_mode = False
        self.update_plot()
        print("[Show All] Now showing all bars")

    def show_selected_only(self):
        """Show only selected bars (enter filter mode)"""
        if len(self.highlighted_bars) > 0:
            print(f"[Show Selected Only] Entering filter mode with {len(self.highlighted_bars)} bars")
            self.state.filter_mode = True
            self.update_plot()
            print(f"[Show Selected Only] Now showing only selected bars")
        else:
            print("[Show Selected Only] No bars selected")

    # ------------------------
    # File drop
    # ------------------------
    def on_file_drop(self, files):
        if not files:
            return

        uploaded_file = files[0]
        content = uploaded_file.get("content")
        filename = uploaded_file.get("name", "")

        if content:
            start = perf_counter()
            try:
                bytes_io = io.BytesIO(content)
                if filename.endswith('.xlsx') or filename.endswith('.xls'):
                    new_df = pd.read_excel(bytes_io)
                else:
                    try:
                        new_df = pd.read_csv(bytes_io)
                    except UnicodeDecodeError:
                        bytes_io.seek(0)
                        try:
                            new_df = pd.read_csv(bytes_io, encoding='latin-1')
                        except UnicodeDecodeError:
                            bytes_io.seek(0)
                            new_df = pd.read_csv(bytes_io, encoding='iso-8859-1')

                self._reset_with_new_data(new_df)
                print(f"Successfully loaded new dataset: {filename}")
            except Exception as e:
                print(f"Error processing uploaded file: {e}")

            latency = (perf_counter() - start) * 1000
            self.latency_tracker.record("File upload", latency)

    def _reset_with_new_data(self, df):
        start = perf_counter()
        self.df = df
        self.column_names = self.df.columns.tolist()
        self._precalculate_data_ranges()

        self.suitable_columns = self._filter_suitable_columns()
        self.unsuitable_columns = [col for col in self.column_names if col not in self.suitable_columns]
        self.server.state.category_options = self.suitable_columns

        if len(self.suitable_columns) >= 1:
            self.state.selected_category = self.suitable_columns[0]
            self.state.show_warning = False
        else:
            self.state.selected_category = None
            self.state.column_warning = "No suitable columns found for bar graph visualization."
            self.state.show_warning = True

        self.update_plot()
        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Reset with new data", latency)

    # ------------------------
    # Precalculate ranges
    # ------------------------
    def _precalculate_data_ranges(self):
        start = perf_counter()
        self.data_ranges = {}
        numeric_columns = self.df.select_dtypes(include=[np.number]).columns.tolist()
        for column in numeric_columns:
            valid_values = self.df[column].dropna().values
            if len(valid_values) > 0:
                max_val = float(np.max(valid_values))
                padding = max_val * 0.1 if max_val > 0 else 1
                self.data_ranges[column] = {'min': 0, 'max': max_val + padding}
            else:
                self.data_ranges[column] = {'min': 0, 'max': 10}
        latency = (perf_counter() - start) * 1000
        if hasattr(self, 'latency_tracker'):
            self.latency_tracker.record("Precalculate ranges (runtime)", latency)

    # ------------------------
    # Category change
    # ------------------------
    def on_category_change(self, category_value, **kwargs):
        start = perf_counter()

        if category_value not in self.suitable_columns and category_value in self.column_names:
            self.state.column_warning = f"Warning: Column '{category_value}' contains text/sentences."
            self.state.show_warning = True
        else:
            self.state.show_warning = False

        self.state.selected_category = category_value
        self.state.filter_mode = False
        self.highlighted_bars = set()
        self.state.selected = []
        self.state.selection_count = 0
        self.update_plot()
        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Category change", latency)

    # ------------------------
    # Bar & Table selection
    # ------------------------
    def on_bar_selected(self, bar_index, **kwargs):
        start = perf_counter()

        if self._is_highlighting:
            return

        self._is_highlighting = True
        try:
            if bar_index >= 0 and bar_index < len(self.valid_bars):
                actual_index = self.valid_bars[bar_index]['original_index']

                print(f"[Bar Selected] Display index: {bar_index}, Original index: {actual_index}")

                if actual_index in self.highlighted_bars:
                    self.highlighted_bars.remove(actual_index)
                    print(f"  -> Deselected. Remaining: {self.highlighted_bars}")
                    for selected_item in list(self.state.selected):
                        if selected_item.get('original_index') == actual_index:
                            self.state.selected.remove(selected_item)
                            break
                else:
                    self.highlighted_bars.add(actual_index)
                    print(f"  -> Selected. Total now: {self.highlighted_bars}")
                    table_item = self.state.items[bar_index]
                    if table_item not in self.state.selected:
                        self.state.selected.append(table_item)

                self.state.selection_count = len(self.highlighted_bars)
                self._update_selected_bar_highlight()

                if self.highlighted_bars:
                    first_bar = min(self.highlighted_bars)
                    page_index = first_bar // self.state.itemsPerPage + 1
                    if page_index != self.state.page:
                        self.state.page = page_index
        finally:
            self._is_highlighting = False

        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Bar selection", latency)

    def on_table_selection_change(self, selected_items, **kwargs):
        start = perf_counter()

        if self._is_highlighting:
            return

        self._is_highlighting = True
        try:
            self.highlighted_bars = set()
            bar_indices = []
            for item in selected_items:
                if 'original_index' in item:
                    original_idx = item['original_index']
                    bar_indices.append(original_idx)
                    self.highlighted_bars.add(original_idx)

            self.state.selection_count = len(self.highlighted_bars)
            self._update_selected_bar_highlight(bar_indices)
        finally:
            self._is_highlighting = False

        latency = (perf_counter() - start) * 1000
        self.latency_tracker.record("Table selection", latency)

    # ------------------------
    # Interaction setup with HOVER
    # ------------------------
    def _setup_interactions(self):
        """Setup mouse interactions including hover tooltips"""
        self.renderWindowInteractor = self.renderWindow.GetInteractor()
        if self.renderWindowInteractor:
            # Mouse move for hover
            self.renderWindowInteractor.AddObserver(standard_vtk.vtkCommand.MouseMoveEvent, self._on_mouse_move)
            # Selection
            self.renderWindowInteractor.AddObserver(standard_vtk.vtkCommand.LeftButtonPressEvent,
                                                    self._on_left_button_press)
            self.renderWindowInteractor.AddObserver(standard_vtk.vtkCommand.LeftButtonReleaseEvent,
                                                    self._on_left_button_release)

            # Create tooltip text actor
            self.tooltip_actor = standard_vtk.vtkTextActor()
            self.tooltip_actor.GetTextProperty().SetFontSize(16)
            self.tooltip_actor.GetTextProperty().SetColor(1.0, 1.0, 1.0)
            self.tooltip_actor.GetTextProperty().SetBold(True)
            self.tooltip_actor.GetTextProperty().SetBackgroundColor(0.2, 0.2, 0.8)
            self.tooltip_actor.GetTextProperty().SetBackgroundOpacity(0.95)
            self.tooltip_actor.GetTextProperty().SetJustificationToCentered()
            self.tooltip_actor.SetVisibility(0)

            # Add to renderer
            renderer = self.view.GetRenderer()
            if renderer:
                renderer.AddActor2D(self.tooltip_actor)
                print("[Tooltip] Tooltip actor added to renderer")

    def _on_mouse_move(self, obj, event):

        if not self.renderWindowInteractor:
            return

        pos = self.renderWindowInteractor.GetEventPosition()
        bar_index = self._get_bar_at_position(pos)

        if bar_index != self._last_hover_bar:
            self._last_hover_bar = bar_index

            if bar_index >= 0 and bar_index < len(self.valid_bars):
                bar_data = self.valid_bars[bar_index]
                category = bar_data['category_str']
                count = bar_data['patient_count']

                # Show tooltip
                if self.tooltip_actor:
                    tooltip_text = f"{category}: {count}"
                    self.tooltip_actor.SetInput(tooltip_text)
                    self.tooltip_actor.SetPosition(pos[0] + 15, pos[1] + 15)
                    self.tooltip_actor.SetVisibility(1)

                print(f"[Hover] Bar {bar_index}: {category} = {count}")

                self.renderWindow.Render()
                self.ctrl.bar_view_update()
            else:
                if self.tooltip_actor:
                    self.tooltip_actor.SetVisibility(0)
                    self.renderWindow.Render()
                    self.ctrl.bar_view_update()

    def _get_bar_at_position(self, pos):
        """Get bar index at mouse position"""
        size = self.renderWindow.GetSize()
        if size[0] == 0 or size[1] == 0:
            return -1

        chart_pos = self.chart.GetPoint1()
        chart_size = self.chart.GetPoint2()

        if pos[0] < chart_pos[0] or pos[0] > chart_size[0]:
            return -1
        if pos[1] < chart_pos[1] or pos[1] > chart_size[1]:
            return -1

        bottom_axis = self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM)
        axis_range = [0.0, 0.0]
        bottom_axis.GetRange(axis_range)

        chart_width = chart_size[0] - chart_pos[0]
        if chart_width <= 0:
            return -1

        relative_x = (pos[0] - chart_pos[0]) / chart_width
        data_range = axis_range[1] - axis_range[0]

        if data_range <= 0:
            return -1

        bar_index = int(axis_range[0] + relative_x * data_range + 0.5)

        if 0 <= bar_index < len(self.valid_bars):
            return bar_index

        return -1

    def _on_left_button_press(self, obj, event):
        """Start rubber band selection"""
        if not self.renderWindowInteractor:
            return

        if self.renderWindowInteractor.GetShiftKey():
            self._selection_start = self.renderWindowInteractor.GetEventPosition()
            self._is_selecting = True
            print(f"[Selection] Started at: {self._selection_start}")

    def _on_left_button_release(self, obj, event):
        """End rubber band selection"""
        if not self._is_selecting or self._selection_start is None:
            return

        if not self.renderWindowInteractor:
            return

        selection_end = self.renderWindowInteractor.GetEventPosition()
        print(f"[Selection] Ended at: {selection_end}")

        selected_bars = self._get_bars_in_selection_box(self._selection_start, selection_end)

        if selected_bars:
            print(f"[Selection] Selected {len(selected_bars)} bars")
            self._is_highlighting = True
            try:
                for bar_idx in selected_bars:
                    actual_idx = self.valid_bars[bar_idx]['original_index']
                    if actual_idx not in self.highlighted_bars:
                        self.highlighted_bars.add(actual_idx)
                        table_item = self.state.items[bar_idx]
                        if table_item not in self.state.selected:
                            self.state.selected.append(table_item)

                self.state.selection_count = len(self.highlighted_bars)
                self._update_selected_bar_highlight()
            finally:
                self._is_highlighting = False

        self._selection_start = None
        self._is_selecting = False

    def _get_bars_in_selection_box(self, start_pos, end_pos):
        """Get all bar indices within selection box"""
        x_min = min(start_pos[0], end_pos[0])
        x_max = max(start_pos[0], end_pos[0])

        chart_pos = self.chart.GetPoint1()
        chart_size = self.chart.GetPoint2()
        chart_width = chart_size[0] - chart_pos[0]

        if chart_width <= 0:
            return []

        bottom_axis = self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM)
        axis_range = [0.0, 0.0]
        bottom_axis.GetRange(axis_range)
        data_range = axis_range[1] - axis_range[0]

        if data_range <= 0:
            return []

        selected_bars = []
        for i in range(len(self.valid_bars)):
            relative_x = (i - axis_range[0]) / data_range
            bar_x = chart_pos[0] + relative_x * chart_width

            if x_min <= bar_x <= x_max:
                selected_bars.append(i)

        return selected_bars

    # ------------------------
    # VTK init & update
    # ------------------------
    def _init_vtk_bargraph(self):
        self.table = standard_vtk.vtkTable()
        self._update_vtk_table()

        self.chart = standard_vtk.vtkChartXY()

        initial_plot = self.chart.AddPlot(standard_vtk.vtkChart.BAR)
        initial_plot.SetInputData(self.table, 0, 1)
        initial_plot.SetColor(100, 150, 200, 255)
        initial_plot.SetWidth(1.0)

        self.lut = standard_vtk.vtkLookupTable()
        self.lut.SetNumberOfTableValues(256)
        self.lut.Build()

        self.color_array = standard_vtk.vtkUnsignedCharArray()
        self.color_array.SetNumberOfComponents(4)
        self.color_array.SetName("Colors")

        self.chart.SetSelectionMethod(standard_vtk.vtkChart.SELECTION_PLOTS)
        self.chart.SetShowLegend(False)

        self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM).SetBehavior(standard_vtk.vtkAxis.FIXED)
        self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetBehavior(standard_vtk.vtkAxis.FIXED)
        self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetMinimumLimit(0)
        self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetUnscaledMinimum(0)
        self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetTitle("Number of Patients")
        self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM).SetTitle("Categories")
        self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM).SetTickLabelAlgorithm(standard_vtk.vtkAxis.TICK_SIMPLE)
        self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM).SetRange(-0.5, 10.5)
        self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetRange(0, 10)
        self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM).SetGridVisible(True)
        self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetGridVisible(True)

        self.view = standard_vtk.vtkContextView()
        self.view.GetScene().AddItem(self.chart)
        self.renderWindow = self.view.GetRenderWindow()
        self.renderWindow.SetSize(800, 600)

    def _setup_bar_selection(self):
        self.chart.AddObserver(standard_vtk.vtkCommand.SelectionChangedEvent, self._handle_selection_event)

    def _handle_selection_event(self, obj, event):
        selection = self.chart.GetSelectionPlots()
        if selection.GetNumberOfItems() > 0:
            plot_selection = selection.GetItem(0)
            if plot_selection and plot_selection.GetNumberOfTuples() > 0:
                bar_index = plot_selection.GetValue(0)
                print(f"[VTK Selection Event] Bar index: {bar_index}")
                self.on_bar_selected(bar_index)

    # ------------------------
    # VTK data table updates
    # ------------------------
    def _update_vtk_table(self):
        start = perf_counter()

        self.table.Initialize()
        arrX = standard_vtk.vtkFloatArray()
        arrX.SetName("Category (X - Axis)")
        arrY = standard_vtk.vtkFloatArray()
        arrY.SetName("Number of Patients (Y - Axis)")

        arrSelection = standard_vtk.vtkIntArray()
        arrSelection.SetName("Selection")

        selected_category = self.state.selected_category

        self.valid_bars = []
        self.category_labels = []

        if selected_category and selected_category in self.df.columns:
            category_data = self.df[selected_category].dropna()

            try:
                numeric_data = pd.to_numeric(category_data, errors='coerce').dropna()
                is_numeric = len(numeric_data) > 0 and len(numeric_data) == len(category_data)
            except:
                is_numeric = False

            if is_numeric and self.state.bin_size > 1:
                bin_size = max(1, int(self.state.bin_size))
                min_val = numeric_data.min()
                max_val = numeric_data.max()

                bins = np.arange(np.floor(min_val), np.ceil(max_val) + bin_size, bin_size)
                counts, edges = np.histogram(numeric_data, bins=bins)

                display_idx = 0
                for idx in range(len(edges) - 1):
                    left = edges[idx]
                    right = edges[idx + 1]
                    count = int(counts[idx])

                    if count > 0:
                        bin_label = f"{int(left)}-{int(right)}"

                        # CRITICAL: Filter mode check
                        if self.state.filter_mode and idx not in self.highlighted_bars:
                            continue

                        self.valid_bars.append({
                            "index": display_idx,
                            "original_index": idx,
                            "category": bin_label,
                            "category_str": bin_label,
                            "patient_count": count,
                        })

                        self.category_labels.append(bin_label)
                        arrX.InsertNextValue(display_idx)
                        arrY.InsertNextValue(count)
                        arrSelection.InsertNextValue(0)
                        display_idx += 1
            else:
                category_counts = {}

                for cat in category_data.values:
                    if pd.notna(cat):
                        cat_str = str(cat)
                        original_cat_str = cat_str

                        if len(cat_str) > 50:
                            cat_str = cat_str[:47] + "..."

                        if cat_str not in category_counts:
                            category_counts[cat_str] = {
                                'count': 0,
                                'original_cat': cat,
                                'original_str': original_cat_str
                            }
                        category_counts[cat_str]['count'] += 1

                original_idx = 0
                display_idx = 0
                for cat_str, data in sorted(category_counts.items()):
                    count = data['count']

                    # CRITICAL: Filter mode check
                    if self.state.filter_mode and original_idx not in self.highlighted_bars:
                        original_idx += 1
                        continue

                    self.valid_bars.append({
                        "index": display_idx,
                        "original_index": original_idx,
                        "category": data['original_cat'],
                        "category_str": cat_str,
                        "patient_count": count,
                    })

                    self.category_labels.append(cat_str)
                    arrX.InsertNextValue(display_idx)
                    arrY.InsertNextValue(count)
                    arrSelection.InsertNextValue(0)
                    original_idx += 1
                    display_idx += 1

        print(f"[Update VTK Table] Filter mode: {self.state.filter_mode}, Total bars: {len(self.valid_bars)}")

        self.table.AddColumn(arrX)
        self.table.AddColumn(arrY)
        self.table.AddColumn(arrSelection)

        self.color_array = standard_vtk.vtkUnsignedCharArray()
        self.color_array.SetNumberOfComponents(4)
        self.color_array.SetName("Colors")
        for i in range(len(self.valid_bars)):
            self.color_array.InsertNextTuple4(100, 150, 200, 255)
        self.table.AddColumn(self.color_array)

        latency = (perf_counter() - start) * 1000
        if hasattr(self, 'latency_tracker'):
            self.latency_tracker.record("Update VTK table", latency)

    def _update_data_table(self):
        start = perf_counter()

        self.state.headers = [
            {"text": "Category Value", "value": "category_str"},
            {"text": "Number of Patients", "value": "patient_count"},
        ]

        table_data = []
        if hasattr(self, 'valid_bars') and self.valid_bars:
            for i, bar in enumerate(self.valid_bars):
                row = {
                    "id": i,
                    "original_index": bar["original_index"],
                    "category_str": bar["category_str"],
                    "patient_count": bar["patient_count"],
                }
                table_data.append(row)

        self.state.items = table_data

        latency = (perf_counter() - start) * 1000
        if hasattr(self, 'latency_tracker'):
            self.latency_tracker.record("Update data table", latency)

    def _update_selected_bar_highlight(self, bar_indices=None):
        """Update visual highlighting of selected bars"""
        start = perf_counter()

        if isinstance(bar_indices, int):
            bar_indices = [bar_indices] if bar_indices >= 0 else []
        elif bar_indices is None:
            bar_indices = list(self.highlighted_bars)

        print(f"[Update Highlight] Highlighted: {self.highlighted_bars}, Filter mode: {self.state.filter_mode}")

        bottom_axis = self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM)
        left_axis = self.chart.GetAxis(standard_vtk.vtkAxis.LEFT)

        bottom_range = [0.0, 0.0]
        left_range = [0.0, 0.0]
        bottom_axis.GetRange(bottom_range)
        left_axis.GetRange(left_range)

        bottom_behavior = bottom_axis.GetBehavior()
        left_behavior = left_axis.GetBehavior()
        left_min_limit = left_axis.GetMinimumLimit()
        left_unscaled_min = left_axis.GetUnscaledMinimum()

        tick_positions = bottom_axis.GetTickPositions()
        tick_labels = bottom_axis.GetTickLabels()

        num_plots = self.chart.GetNumberOfPlots()
        for i in range(num_plots):
            self.chart.RemovePlotInstance(self.chart.GetPlot(0))

        arrX_unsel = standard_vtk.vtkFloatArray()
        arrX_unsel.SetName("Category")
        arrY_unsel = standard_vtk.vtkFloatArray()
        arrY_unsel.SetName("Count")

        arrX_sel = standard_vtk.vtkFloatArray()
        arrX_sel.SetName("Category")
        arrY_sel = standard_vtk.vtkFloatArray()
        arrY_sel.SetName("Count")

        for i in range(len(self.valid_bars)):
            x_val = float(i)
            y_val = float(self.valid_bars[i]['patient_count'])
            original_idx = self.valid_bars[i]['original_index']

            if self.state.filter_mode or original_idx in self.highlighted_bars:
                arrX_sel.InsertNextValue(x_val)
                arrY_sel.InsertNextValue(y_val)
            else:
                arrX_unsel.InsertNextValue(x_val)
                arrY_unsel.InsertNextValue(y_val)

        table_unsel = standard_vtk.vtkTable()
        table_unsel.AddColumn(arrX_unsel)
        table_unsel.AddColumn(arrY_unsel)

        table_sel = standard_vtk.vtkTable()
        table_sel.AddColumn(arrX_sel)
        table_sel.AddColumn(arrY_sel)

        if table_unsel.GetNumberOfRows() > 0:
            plot_unsel = self.chart.AddPlot(standard_vtk.vtkChart.BAR)
            plot_unsel.SetInputData(table_unsel, 0, 1)
            plot_unsel.SetColor(100, 150, 200, 255)
            plot_unsel.SetWidth(1.0)

        if table_sel.GetNumberOfRows() > 0:
            plot_sel = self.chart.AddPlot(standard_vtk.vtkChart.BAR)
            plot_sel.SetInputData(table_sel, 0, 1)
            plot_sel.SetColor(255, 0, 0, 255)
            plot_sel.SetWidth(1.0)

        bottom_axis.SetBehavior(bottom_behavior)
        left_axis.SetBehavior(left_behavior)

        bottom_axis.SetRange(bottom_range[0], bottom_range[1])
        left_axis.SetRange(left_range[0], left_range[1])

        left_axis.SetMinimumLimit(left_min_limit)
        left_axis.SetUnscaledMinimum(left_unscaled_min)

        if tick_positions and tick_labels:
            bottom_axis.SetCustomTickPositions(tick_positions, tick_labels)

        self.renderWindow.Render()
        self.ctrl.bar_view_update()

        latency = (perf_counter() - start) * 1000
        if hasattr(self, 'latency_tracker'):
            self.latency_tracker.record("Update bar highlight", latency)

    # ------------------------
    # Update plot
    # ------------------------
    def update_plot(self, **kwargs):
        start_total = perf_counter()

        self._is_highlighting = False

        current_bin_size = self.state.bin_size
        print(f"\n[UPDATE PLOT] Filter mode: {self.state.filter_mode}, Selected: {self.highlighted_bars}")

        if self.state.selected_category:
            start = perf_counter()
            self._update_vtk_table()
            vtk_table_time = (perf_counter() - start) * 1000

            start = perf_counter()
            self._update_data_table()
            data_table_time = (perf_counter() - start) * 1000

            start = perf_counter()
            self.table.Modified()

            while self.chart.GetNumberOfPlots() > 0:
                self.chart.RemovePlotInstance(self.chart.GetPlot(0))

            default_plot = self.chart.AddPlot(standard_vtk.vtkChart.BAR)
            default_plot.SetInputData(self.table, 0, 1)

            if self.state.filter_mode:
                default_plot.SetColor(255, 0, 0, 255)
            else:
                default_plot.SetColor(100, 150, 200, 255)

            default_plot.SetWidth(1.0)

            num_bars = len(self.valid_bars)
            if num_bars > 0:
                self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM).SetRange(-0.5, num_bars - 0.5)

                bottom_axis = self.chart.GetAxis(standard_vtk.vtkAxis.BOTTOM)
                tick_positions = standard_vtk.vtkDoubleArray()
                tick_labels = standard_vtk.vtkStringArray()
                for i, label in enumerate(self.category_labels):
                    tick_positions.InsertNextValue(i)
                    tick_labels.InsertNextValue(label)
                bottom_axis.SetCustomTickPositions(tick_positions, tick_labels)

            if self.valid_bars:
                max_count = max(bar['patient_count'] for bar in self.valid_bars)
                y_max = max_count * 1.1
                self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetRange(0, y_max)
                self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetMinimumLimit(0)
                self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetUnscaledMinimum(0)
            else:
                self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetRange(0, 10)
                self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetMinimumLimit(0)
                self.chart.GetAxis(standard_vtk.vtkAxis.LEFT).SetUnscaledMinimum(0)

            self.chart.RecalculateBounds()

            # Apply highlighting if not in filter mode
            if len(self.highlighted_bars) > 0 and not self.state.filter_mode:
                self._update_selected_bar_highlight()

            plot_update_time = (perf_counter() - start) * 1000

            start = perf_counter()
            self.renderWindow.Render()
            self.ctrl.bar_view_update()
            render_time = (perf_counter() - start) * 1000

            if hasattr(self, 'latency_tracker'):
                self.latency_tracker.record("Plot update: VTK table", vtk_table_time)
                self.latency_tracker.record("Plot update: Data table", data_table_time)
                self.latency_tracker.record("Plot update: Chart config", plot_update_time)
                self.latency_tracker.record("Plot update: Render", render_time)

        total_latency = (perf_counter() - start_total) * 1000
        if hasattr(self, 'latency_tracker'):
            self.latency_tracker.record("Plot update: TOTAL", total_latency)

        if self.state.bin_size != current_bin_size:
            self.state.bin_size = current_bin_size

        print(f"[UPDATE PLOT] Complete in {total_latency:.3f} ms\n")

    # ------------------------
    # UI
    # ------------------------
    def _setup_ui(self):
        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("Bar Graph")

            with layout.toolbar:
                vuetify.VSpacer()

                html.Input(
                    type="file",
                    ref="file_input",
                    change=(self.ctrl.on_file_drop, "[$event]"),
                    accept=".csv,.xlsx,.xls,.json",
                    style="display: none;",
                )
                vuetify.VBtn(
                    "Upload File",
                    click="$refs.file_input.click()",
                    color="secondary",
                    classes="mr-2",
                    small=True,
                )

                vuetify.VSelect(
                    label="Select Category",
                    items=("category_options", []),
                    v_model=("selected_category", None),
                    dense=True,
                    hide_details=True,
                    style="max-width: 250px",
                    change=(self.ctrl.on_category_change, "[$event]"),
                )

                vuetify.VSlider(
                    label="Bin Size",
                    v_model=("bin_size", 1),
                    min=1,
                    max=20,
                    step=1,
                    dense=True,
                    hide_details=True,
                    style="max-width: 150px; margin-left: 10px;",
                    change=(self.ctrl.update_plot, "[]"),
                )

                vuetify.VBtn(
                    "Show Selected Only",
                    click=self.ctrl.show_selected_only,
                    color="primary",
                    classes="ml-2",
                    small=True,
                    disabled=("selection_count === 0",),
                )

                vuetify.VBtn(
                    "Show All",
                    click=self.ctrl.show_all_bars,
                    color="info",
                    classes="ml-2",
                    small=True,
                    v_show=("filter_mode",),
                )

                vuetify.VBtn(
                    "Clear Selection",
                    click=self.ctrl.clear_selection,
                    color="warning",
                    classes="ml-2",
                    small=True,
                    disabled=("selection_count === 0",),
                )

            with layout.content:
                vuetify.VAlert(
                    v_show=("show_warning", False),
                    type="warning",
                    dismissible=True,
                    style="margin: 8px;",
                    children=("column_warning", ""),
                )


                with vuetify.VContainer(fluid=True, style="height: calc(100vh - 64px); padding: 0;"):
                    with vuetify.VRow(style="height: 100%; margin: 0;"):
                        with vuetify.VCol(cols=12, style="height: 50%; padding: 8px; min-height: 400px;"):
                            with vuetify.VCard(flat=True, style="height: 100%; display: flex; flex-direction: column;"):
                                with vuetify.VCardTitle():
                                    html.Div("Bar Graph", style="flex-grow: 1;")

                                with vuetify.VCardText(style="flex: 1; position: relative; padding-bottom: 16px;"):
                                    vtk_widgets.VtkRemoteView(
                                        self.renderWindow,
                                        ref="bar_view",
                                        interactive_quality=100,
                                        interactive_ratio=1,
                                        style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;",
                                    )

                        with vuetify.VCol(cols=12, style="height: 50%; padding: 8px; overflow-y: auto;"):
                            with vuetify.VCard(flat=True, style="height: 100%; display: flex; flex-direction: column;"):
                                vuetify.VCardTitle("Data Table")
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
        print(f"Server started at port {self.port}")

    def stop(self):
        self.latency_tracker.print_summary()
        self.latency_tracker.save_to_file()
        self.server.stop()


if __name__ == "__main__":
    csv_file_path = "/home/minhnguyen/Minh/SUHI.xlsx"
    app = BarGraphApp(csv_file_path, remote_rendering=True)
    app.start_now()