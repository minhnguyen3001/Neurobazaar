import os
import sys
import logging
import time

from trame.app import get_server  # type: ignore
from trame.decorators import TrameApp, change  # type: ignore
from trame.widgets import vtk, vuetify  # type: ignore
from trame.ui.vuetify import SinglePageLayout  # type: ignore
import vtk as standard_vtk

import numpy as np  # type: ignore
import dask.array as da  # type: ignore
import dask_histogram as dh  # type: ignore
import boost_histogram as bh  # type: ignore

# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

@TrameApp()
class VtkApp:
    def __init__(self, data_size=1_000, ui_type="slider ", port: int = 8080, remote_rendering: bool = True):
        self.server = get_server(client_type="vue2")
        self.state, self.ctrl = self.server.state, self.server.controller
        self.port = port
        self._remote_rendering = remote_rendering

        self.data = da.from_array(np.random.normal(size=data_size), chunks='auto')
        self.data_min, self.data_max = self._compute_min_max(self.data)
        self.state.bins = 5

        self.computing_total = []
        self.server_side_rendering_total = []
        self._initial_histogram()

        if self._remote_rendering:
            self.client_view = vtk.VtkRemoteView(
                self.renderWindow, trame_server=self.server, ref="view"
            )
        else:
            self.client_view = vtk.VtkLocalView(self.renderWindow, trame_server=self.server)

        if ui_type == "slider":
            self._setup_slider_layout()
        elif ui_type == "input":
            self._setup_input_layout()
        else:
            raise ValueError("Invalid ui_type")

    def _vtk_histogram(self):
        """Initialize histogram"""
        self.hist, self.bin_edges = self._compute_hist(self.data, self.state.bins)

        self.table = standard_vtk.vtkTable()

        self.arrX = standard_vtk.vtkFloatArray()
        self.arrX.SetName("X Axis")
        self.arrY = standard_vtk.vtkFloatArray()
        self.arrY.SetName("Frequency")

        for i in range(len(self.hist)):
            self.arrX.InsertNextValue(self.bin_edges[i])
            self.arrY.InsertNextValue(self.hist[i])

        self.table.AddColumn(self.arrX)
        self.table.AddColumn(self.arrY)

        self.plot = standard_vtk.vtkPlotBar()
        self.plot.SetInputData(self.table)
        self.plot.SetInputArray(0, "X Axis")
        self.plot.SetInputArray(1, "Frequency")
        self.plot.SetColor(0, 0, 0, 255)

        self.chart = standard_vtk.vtkChartXY()
        self.chart.SetBarWidthFraction(1.0)
        self.chart.GetAxis(0).SetTitle("Frequency")
        self.chart.GetAxis(1).SetTitle("Feature")
        self.chart.AddPlot(self.plot)

        self.view = standard_vtk.vtkContextView()
        self.view.GetScene().AddItem(self.chart)

        self.renderWindow = self.view.GetRenderWindow()
        self.view.GetRenderWindow().SetSize(800, 600)

    def _update_histogram(self):
        """Update histogram"""
        compute_start = time.time()
        self.hist, self.bin_edges = self._compute_hist(self.data, self.state.bins)
        compute_end = time.time()

        self.computing_total.append(compute_end - compute_start)

        render_start = time.time()
        self.arrX.Reset()
        self.arrY.Reset()

        for i in range(len(self.hist)):
            self.arrX.InsertNextValue(self.bin_edges[i])
            self.arrY.InsertNextValue(self.hist[i])

        render_end = time.time()

        if self._remote_rendering is True:
            self.client_view.update()

        self.server_side_rendering_total.append(render_end - render_start)

    def _compute_min_max(self, dask_data):
        """Compute min and max efficiently"""
        return dask_data.min().compute(), dask_data.max().compute()

    def _compute_hist(self, dask_data, bins):
        """Optimize histogram computation"""
        try:
            bins = int(bins)
            dask_hist = dh.factory(dask_data, axes=(bh.axis.Regular(bins, self.data_min, self.data_max),))
            hist_result = dask_hist.persist().compute(scheduler='threads')
            frequencies = hist_result.to_numpy()[0]

            bin_edges = np.linspace(self.data_min, self.data_max, bins + 1)
            return frequencies, bin_edges

        except Exception as e:
            logging.error(f"Histogram computation error: {e}")
            return None, None

    def _initial_histogram(self):
        """Initialize histogram"""
        self._vtk_histogram()

    @change("bins")
    def _on_bins_change(self, **kwargs):
        """Efficiently handle bin changes"""
        logging.info(f"Bins changed to: {self.state.bins}")
        self._update_histogram()

    def _setup_slider_layout(self):
        """Setup layout with slider"""
        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("Optimized Interactive Histogram")

            with layout.toolbar:
                vuetify.VSpacer()
                vuetify.VSlider(
                    v_model=("bins", 5),
                    min=1,
                    max=100,
                    label="Number of Bins",
                    hide_details=False,
                    dense=True,
                    thumb_label=True,
                    thumb_size=20,
                    style="padding-top: 20px;",
                )

            if self._remote_rendering:
                with layout.content:
                    with vuetify.VContainer(
                            fluid=True,
                            classes="pa-0 fill-height",
                    ):
                        self.client_view = vtk.VtkRemoteView(
                            self.renderWindow,
                            trame_server=self.server,
                            ref="view"
                        )
            else:
                with layout.content:
                    with vuetify.VContainer(
                            fluid=True,
                            classes="pa-0 fill-height",
                    ):
                        self.client_view = vtk.VtkLocalView(self.renderWindow, trame_server=self.server, ref="view")
                        self.ctrl.view_update = self.client_view.update

    def _setup_input_layout(self):
        """Setup input layout"""
        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("Optimized Interactive Histogram")

            with layout.toolbar:
                vuetify.VSpacer()
                vuetify.VTextField(
                    v_model=("bins", 5),
                    label="Number of Bins",
                    type="number",
                    style="padding-top: 20px;",
                )

            if self._remote_rendering:
                with layout.content:
                    with vuetify.VContainer(
                            fluid=True,
                            classes="pa-0 fill-height",
                    ):
                        self.client_view = vtk.VtkRemoteView(
                            self.renderWindow,
                            trame_server=self.server,
                            ref="view"
                        )
            else:
                with layout.content:
                    with vuetify.VContainer(
                            fluid=True,
                            classes="pa-0 fill-height",
                    ):
                        self.client_view = vtk.VtkLocalView(self.renderWindow, trame_server=self.server, ref="view")
                        self.ctrl.view_update = self.client_view.update

    def start_now(self):
        """Start server now"""
        self.server.start(port=self.port)

    async def start_later(self):
        """Start server later"""
        return await self.server.start(exec_mode="task", port=self.port)

    def stop(self):
        """Stop server"""
        self.server.stop()


if __name__ == "__main__":
    vtk_app = VtkApp(data_size=1_000, ui_type="slider", remote_rendering=True)
    vtk_app.start_now()
    vtk_app.stop()