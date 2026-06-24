import logging
import os
from datetime import datetime
import io
import contextlib
import time

from playwright.sync_api import sync_playwright
import numpy as np


class Runner:
    def __init__(self, url: str, server_type: str = "VTK", num_benchmarks: int = 100, snapshots: int = 10):
        self.url = url
        self.__server_type = server_type
        self.__request_times = []

        if server_type not in ["VTK", "Plotly", "Matplotlib"]:
            raise ValueError("Invalid server type. Currently supported: VTK, Plotly, Matplotlib. Hint: Case sensitive.")

        if snapshots < 10:
            print(
                "\033[91mWARNING: The number of snapshots is less than 10. This may not be enough to ensure stability.\033[0m")
        elif snapshots > 100:
            print(
                "\033[91mWARNING: The number of snapshots is greater than 100. This may be excessive. And might slow down the benchmark.\033[0m")

        if self.__server_type == "VTK":
            self.__JS_SELECTOR = ".v-main"
            self.__JS_ELEMENT = ".v-main img"
            self.__JS_STATE = "__previous_vtk_state"
            self.__STABLE_THRESHOLD = snapshots
        elif self.__server_type == "Plotly":
            self.__JS_SELECTOR = ".js-plotly-plot"
            self.__JS_ELEMENT = ".js-plotly-plot"
            self.__JS_STATE = "__previous_plotly_state"
            self.__STABLE_THRESHOLD = snapshots
        elif self.__server_type == "Matplotlib":
            self.__JS_SELECTOR = ".mpld3-figure"
            self.__JS_ELEMENT = ".mpld3-figure"
            self.__JS_STATE = "__previous_matplotlib_state"
            self.__STABLE_THRESHOLD = snapshots
        else:
            raise ValueError("Invalid server type. Currently supported: VTK, Plotly, Matplotlib. Hint: Case sensitive.")

        self.num_benchmarks = num_benchmarks
        self.__num_benchmarks = num_benchmarks + int(1)  # Add one to account for 0 index

        self.runner_helper = _RunnerHelper()

        self.runner_helper.setup_logging()

    def deploy_runner(self, ui_type: str = "slider", headless: bool = True, ignore_https_errors: bool = True):
        render_times = []
        detailed_timing_logs = []

        self.runner_helper.log(f"Starting benchmark for {self.url}")

        with sync_playwright() as the_browser:
            if headless is True:
                browser = the_browser.chromium.launch()
            elif headless is False:
                browser = the_browser.chromium.launch(headless=False)

            if ignore_https_errors is True:
                context = browser.new_context(ignore_https_errors=True)
            else:
                print("INFO: HTTPS errors are not ignored. This may cause issues depending on the server." +
                      "If you encounter issues, consider setting ignore_https_errors=True.")

            page = context.new_page()

            print("Going to the page")
            page.goto(self.url)
            print("Page loaded")

            print("Waiting for the figure to be visible")
            page.wait_for_selector(self.__JS_SELECTOR, timeout=5000)
            print("Figure is visible")

            def slider(page, i):
                try:
                    slider_thumb = page.locator(".v-slider__thumb-container")
                    assert slider_thumb is not None, "Slider thumb not found"

                    slider_track = page.locator(".v-slider__track-container")
                    assert slider_track is not None, "Slider track not found"

                    slider_track_box = slider_track.bounding_box()
                    assert slider_track_box is not None, "Unable to get slider track bounding box"

                    percentage = i / 100
                    new_position_x = slider_track_box["x"] + slider_track_box["width"] * percentage
                    new_position_y = slider_track_box["y"] + slider_track_box["height"] / 2

                    page.mouse.move(new_position_x, new_position_y)

                    if i == 0:
                        page.mouse.down()
                    elif i == 100:
                        page.mouse.up()
                except Exception as e:
                    print(f"Error simulating slider: {e}")

            def input_field(page, input_value):
                try:
                    input_container = page.locator(".v-input__slot")
                    assert input_container is not None, "Input container not found"

                    input_box = input_container.bounding_box()
                    assert input_box is not None, "Unable to get input container bounding box"

                    click_x = input_box["x"] + input_box["width"] / 2
                    click_y = input_box["y"] + input_box["height"] / 2

                    page.mouse.move(click_x, click_y)

                    page.mouse.down()
                    page.mouse.up()

                    for _ in range(5):
                        page.keyboard.press("Backspace")

                    page.keyboard.type(str(input_value))

                except Exception as e:
                    print(f"Error simulating number input: {e}")

            def get_network_requests(page):
                request_times = []
                benchmark_in_progress = True

                def capture_requests(request):
                    nonlocal benchmark_in_progress
                    if not benchmark_in_progress:
                        return

                    try:
                        response = request.response()
                        if response:
                            timing = request.timing
                            start_time = timing['startTime']  # Absolute high-precision timestamp
                            end_time = timing['responseEnd']  # Relative time delta, this is what we want to capture.

                            request_time = end_time
                            request_times.append(request_time)

                            # print(f"Request: {request.url}")                # Request URL
                            # print(f"Start Time (absolute): {start_time}")   # High precision timestamp
                            # print(f"Request Duration: {request_time} ms")   # Relative time delta
                    except Exception as e:
                        if benchmark_in_progress:
                            print(f"Error capturing request timing: {e}")

                page.on('request', capture_requests)
                page.goto(self.url)

                for i in range(self.__num_benchmarks):
                    print(f"Network benchmark {i} of {self.num_benchmarks}")
                    try:
                        if ui_type == "slider":
                            slider(page, i)
                            time.sleep(0.5)
                        elif ui_type == "input_field":
                            input_field(page, i)
                            time.sleep(0.5)
                    except Exception as e:
                        print(f"Error occurred during network benchmark {i}: {e}")
                        break

                page.unroute('*')
                benchmark_in_progress = False

                return request_times

            def js_function(page):
                result_handle = page.wait_for_function(
                    f"""
                   () => {{
                       // Enhanced timing tracking
                       if (!window.__detailed_timing) {{
                           window.__detailed_timing = {{
                               start_time: performance.now(),
                               check_times: [],
                               prev_check_time: performance.now(),
                               state_change_times: [],
                               stability_check_details: []
                           }};
                       }}

                       if (!window.__check_count) {{
                           window.__check_count = 0;
                       }}
                       if (!window.__stable_check_count) {{
                           window.__stable_check_count = 0;
                       }}
                       if (!window.__start_time) {{
                           window.__start_time = performance.now();
                       }}
                       if (!window.__stability_check_time) {{
                           window.__stability_check_time = 0;
                       }}

                       const STABLE_THRESHOLD = {self.__STABLE_THRESHOLD};  

                       const current_time = performance.now();
                       const detailed_timing = window.__detailed_timing;

                       // Track time between checks
                       const time_since_last_check = current_time - detailed_timing.prev_check_time;
                       detailed_timing.check_times.push(time_since_last_check);
                       detailed_timing.prev_check_time = current_time;

                       window.__check_count += 1;

                       const element = document.querySelector('{self.__JS_ELEMENT}');
                       if (!element) return false;

                       const previousState = window['{self.__JS_STATE}'] || null;
                       const currentState = {{
                           innerHTML: element.innerHTML,
                           attributes: Array.from(element.attributes).reduce((acc, attr) => {{
                               acc[attr.name] = attr.value;
                               return acc;
                           }}, {{}})
                       }};

                       // Measure stability check time
                       const stability_check_start = performance.now();

                       let stateChanged = false;
                       if (previousState && JSON.stringify(previousState) !== JSON.stringify(currentState)) {{
                           stateChanged = true;
                           detailed_timing.state_change_times.push(current_time - detailed_timing.start_time);
                       }}

                       if (previousState && JSON.stringify(previousState) === JSON.stringify(currentState)) {{
                           window.__stable_check_count += 1;
                       }} else {{
                           window.__stable_check_count = 0;
                       }}

                       const stability_check_end = performance.now();
                       const stability_check_duration = stability_check_end - stability_check_start;
                       window.__stability_check_time += stability_check_duration;

                       // Store detailed stability check information
                       detailed_timing.stability_check_details.push({{
                           check_count: window.__check_count,
                           stable_check_count: window.__stable_check_count,
                           state_changed: stateChanged,
                           check_duration: stability_check_duration
                       }});

                       window['{self.__JS_STATE}'] = currentState;

                       if (window.__stable_check_count >= STABLE_THRESHOLD) {{
                           const end_time = performance.now();

                           // Calculate render times
                           const total_render_time = end_time - window.__start_time;
                           const adjusted_render_time = total_render_time - window.__stability_check_time;

                           // Prepare comprehensive log
                           const log = {{
                               total_render_time,
                               stability_check_time: window.__stability_check_time,
                               adjusted_render_time,
                               detailed_timing: window.__detailed_timing
                           }};

                           console.log(JSON.stringify(log, null, 2));

                           // Choose render time
                           const final_render_time = 
                               adjusted_render_time > 0 ? adjusted_render_time : total_render_time;

                           // Reset variables
                           window.__check_count = 0;
                           window.__stable_check_count = 0;
                           window.__start_time = null;
                           window.__stability_check_time = 0;
                           window.__detailed_timing = null;

                           return {{ final_render_time, log }};
                       }}

                       return false;
                   }}
                   """,
                    timeout=60000,
                    polling=0.01
                )

                result = result_handle.json_value()
                final_render_time = result['final_render_time']
                log = result['log']
                return final_render_time, log

            def report(render_times):
                report_output = io.StringIO()
                with contextlib.redirect_stdout(report_output):
                    if self.__server_type == "VTK":
                        self.__request_times.sort()
                        min_request_time = np.min(self.__request_times)
                        q1_request_time = np.percentile(self.__request_times, 25)
                        median_request_time = np.median(self.__request_times)
                        q3_request_time = np.percentile(self.__request_times, 75)
                        max_request_time = np.max(self.__request_times)
                        mean_request_time = np.mean(self.__request_times)
                        std_dev_request_time = np.std(self.__request_times)

                        print("\nNetwork Request Statistics:")
                        print(f"Minimum: {min_request_time:.2f} ms")
                        print(f"First Quartile (Q1): {q1_request_time:.2f} ms")
                        print(f"Median (Q2): {median_request_time:.2f} ms")
                        print(f"Third Quartile (Q3): {q3_request_time:.2f} ms")
                        print(f"Maximum: {max_request_time:.2f} ms")
                        print(f"Mean: {mean_request_time:.2f} ms")
                        print(f"Standard Deviation: {std_dev_request_time:.2f} ms")

                    render_times.sort()
                    min_val = np.min(render_times)
                    q1 = np.percentile(render_times, 25)
                    median = np.median(render_times)
                    q3 = np.percentile(render_times, 75)
                    max_val = np.max(render_times)
                    mean = np.mean(render_times)
                    std_dev = np.std(render_times)

                    print("\nRender Time Statistics:")
                    print(f"Minimum: {min_val:.2f} ms")
                    print(f"First Quartile (Q1): {q1:.2f} ms")
                    print(f"Median (Q2): {median:.2f} ms")
                    print(f"Third Quartile (Q3): {q3:.2f} ms")
                    print(f"Maximum: {max_val:.2f} ms")
                    print(f"Mean: {mean:.2f} ms")
                    print(f"Standard Deviation: {std_dev:.2f} ms")

                    all_check_times = []
                    all_check_durations = []
                    state_change_times = []

                    for log in detailed_timing_logs:
                        detailed_timing = log.get('detailed_timing', {})
                        all_check_times.extend(detailed_timing.get('check_times', []))
                        state_change_times.extend(detailed_timing.get('state_change_times', []))

                        check_details = [detail['check_duration'] for detail in
                                         detailed_timing.get('stability_check_details', [])]
                        all_check_durations.extend(check_details)

                    print("\nCheck Time Diagnostics:")
                    print(f"Average time between checks: {np.mean(all_check_times):.2f} ms")
                    print(f"Max time between checks: {np.max(all_check_times):.2f} ms")
                    print(f"Min time between checks: {np.min(all_check_times):.2f} ms")
                    print(f"Number of checks: {len(all_check_times)}")

                    print("\nStability Check Diagnostics:")
                    print(f"Average stability check duration: {np.mean(all_check_durations):.2f} ms")
                    print(f"Max stability check duration: {np.max(all_check_durations):.2f} ms")

                    print("\nState Change Times:")
                    print(f"Number of state changes: {len(state_change_times)}")
                    print(f"Avg time between state changes: {np.mean(state_change_times):.2f} ms")
                    if state_change_times:
                        print(f"State change times: {state_change_times}")

                report_content = report_output.getvalue()
                self.runner_helper.log(report_content)
                self.runner_helper.save_benchmark_results(report_content)

            if self.__server_type == "VTK":
                print("Starting network benchmark requests")
                requests = get_network_requests(page)
                self.__request_times = requests
                print("Network benchmark requests complete")

            for i in range(self.__num_benchmarks):
                print(f"Rendering benchmark {i} of {self.num_benchmarks}")

                try:
                    if ui_type == "slider":
                        slider(page, i)
                    elif ui_type == "input_field":
                        input_field(page, i)

                    final_render_time, log = js_function(page)
                    render_times.append(final_render_time)
                    detailed_timing_logs.append(log)
                    # print(f"Histogram render time: {final_render_time:.2f} milliseconds")

                except Exception as e:
                    print(f"Error occurred during rendering benchmark {i}: {e}")
                    break

            report(render_times)

            browser.close()


class _RunnerHelper:
    """
    A helper class to manage logging and benchmark result tracking.

    Provides functionality for logging application events and capturing benchmark results
    in separate directories with timestamped files.

    Attributes:
        log_directory (str): Directory to store log files.
        benchmark_directory (str): Directory to store benchmark result files.
    """

    def __init__(self, log_directory='logs', benchmark_directory='benchmarks'):
        """
        Initialize RunnerHelper with configurable log and benchmark directories.

        Args:
            log_directory (str, optional): Path to directory for log files. Defaults to 'logs'.
            benchmark_directory (str, optional): Path to directory for benchmark results. Defaults to 'benchmarks'.
        """
        self.log_directory = log_directory
        self.benchmark_directory = benchmark_directory

        os.makedirs(self.log_directory, exist_ok=True)
        os.makedirs(self.benchmark_directory, exist_ok=True)

        self.logger = None
        self.log_file_path = None
        self.benchmark_file_path = None

    def setup_logging(self, log_level=logging.INFO):
        """
        Configure logging with console and file handlers.

        Args:
            log_level (int, optional): Logging level. Defaults to logging.INFO.

        Returns:
            logging.Logger: Configured logger instance.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"runner_{timestamp}.log"
        self.log_file_path = os.path.join(self.log_directory, log_filename)

        self.logger = logging.getLogger('BenchmarkRunner')
        self.logger.setLevel(log_level)

        self.logger.handlers.clear()

        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)

        file_handler = logging.FileHandler(self.log_file_path)
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
        file_handler.setFormatter(file_formatter)

        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)

        return self.logger

    def log(self, message, level='info'):
        """
        Log a message with the specified logging level.

        Args:
            message (str): Message to log.
            level (str, optional): Logging level. Defaults to 'info'.
                Supported levels: 'info', 'warning', 'error', 'debug'.
        """
        if not self.logger:
            self.setup_logging()

        log_methods = {
            'info': self.logger.info,
            'warning': self.logger.warning,
            'error': self.logger.error,
            'debug': self.logger.debug
        }

        log_method = log_methods.get(level.lower(), self.logger.info)
        log_method(message)

    def save_benchmark_results(self, content):
        """
        Save benchmark results to a file in the benchmark directory.

        Args:
            content (str): Benchmark results to save.

        Returns:
            str: Path to the saved benchmark results file.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        benchmark_filename = f"benchmark_results_{timestamp}.txt"

        self.benchmark_file_path = os.path.join(self.benchmark_directory, benchmark_filename)

        with open(self.benchmark_file_path, 'w') as f:
            f.write(content)

        return self.benchmark_file_path


if __name__ == "__main__":
    url = "http://localhost:8080"

    plotly = "Plotly"
    vtk = "VTK"
    matplotlib = "Matplotlib"
    num_benchmarks = 100
    threshold = 10

    slider = "slider"
    input_field = "input_field"
    headless = False
    ignore_https_errors = True

    runner = Runner(url, server_type=vtk, num_benchmarks=num_benchmarks, snapshots=threshold)
    runner.deploy_runner(ui_type=slider, headless=headless, ignore_https_errors=ignore_https_errors)