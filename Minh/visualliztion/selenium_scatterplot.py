from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Configuration
URL = "http://localhost:8080"
POINT_DENSITY_SLIDER = "input[type='range']"  # Adjust based on UI element
UPDATE_BUTTON = "button:contains('Update Plot')"  # Adjust based on UI element

# Setup WebDriver
driver = webdriver.Chrome()  # Use the appropriate WebDriver for your browser
driver.get(URL)

# Wait for the page to load
WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, POINT_DENSITY_SLIDER))
)

# Measure page load latency
start_time = time.time()
driver.refresh()
WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.CSS_SELECTOR, POINT_DENSITY_SLIDER))
)
page_load_latency = time.time() - start_time
print(f"Page Load Latency: {page_load_latency:.3f} seconds")

# Measure interaction latency
# Simulate changing point density and updating the plot
slider = driver.find_element(By.CSS_SELECTOR, POINT_DENSITY_SLIDER)
update_button = driver.find_element(By.CSS_SELECTOR, UPDATE_BUTTON)

# Interact with slider and measure update latency
start_time = time.time()
slider.send_keys("50")  # Adjust slider value (e.g., 50 points)
update_button.click()

# Wait for scatterplot update (adjust based on specific triggers in the UI)
WebDriverWait(driver, 10).until(
    lambda d: "Update Completed" in d.page_source  # Replace with appropriate check
)
interaction_latency = time.time() - start_time
print(f"Interaction Latency: {interaction_latency:.3f} seconds")

# Cleanup
driver.quit()
