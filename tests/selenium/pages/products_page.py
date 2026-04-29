from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class ProductsPage:
    SHOP_URL = "https://ecommerce-playground.lambdatest.io/index.php?route=product/category&path=20"

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 15)

    def navigate_to_products_page(self):
        self.driver.get(self.SHOP_URL)
        self.wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))

    def current_url(self):
        return self.driver.current_url

    def get_product_tiles(self):
        try:
            return self.driver.find_elements(By.CSS_SELECTOR, ".product-thumb")
        except Exception:
            return []

    def apply_filter(self, filter_name):
        try:
            links = self.driver.find_elements(
                By.XPATH,
                f"//div[@id='column-left']//a[contains(normalize-space(.), '{filter_name}')]"
                f" | //div[contains(@class,'list-group')]//a[contains(normalize-space(.), '{filter_name}')]"
            )
            if not links:
                links = self.driver.find_elements(
                    By.XPATH,
                    f"//a[contains(normalize-space(.), '{filter_name}') and contains(@href, 'path=')]"
                )
            if links:
                links[0].click()
                self.wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                return True
            return False
        except Exception:
            return False

    def click_first_product_details(self):
        try:
            links = self.driver.find_elements(By.CSS_SELECTOR, ".product-thumb .image a")
            if not links:
                links = self.driver.find_elements(By.CSS_SELECTOR, ".product-thumb h4 a, .product-thumb .caption a")
            if links:
                links[0].click()
                return True
            return False
        except Exception:
            return False

    def get_product_details_elements(self):
        try:
            elements = self.driver.find_elements(
                By.CSS_SELECTOR, "#product-product, h1, .price, #tab-description"
            )
            return elements
        except Exception:
            return []

    def is_login_gate_present(self):
        try:
            gates = self.driver.find_elements(
                By.XPATH,
                "//*[contains(text(),'must be logged') or contains(text(),'login to view') or contains(text(),'Please login')]"
            )
            return len(gates) > 0
        except Exception:
            return False

    def has_guest_browsing_content(self):
        try:
            content = self.driver.find_elements(
                By.CSS_SELECTOR, ".product-thumb, .swiper-slide, h1, h2, h3, .carousel"
            )
            return len(content) > 0
        except Exception:
            return False

    def search_for_product(self, product_name):
        try:
            box = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='search']")))
            box.clear()
            box.send_keys(product_name)
            box.submit()
            return True
        except Exception:
            return False

    def add_first_product_to_cart(self):
        try:
            btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[onclick*='cart.add'], .btn-cart"))
            )
            btn.click()
            return True
        except Exception:
            return False

    def navigate_to_cart(self):
        try:
            link = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='route=checkout/cart']"))
            )
            link.click()
            return True
        except Exception:
            return False

    def update_cart_quantity(self, product_name, quantity):
        try:
            qty = self.driver.find_element(By.CSS_SELECTOR, "input[name*='quantity']")
            qty.clear()
            qty.send_keys(str(quantity))
            return True
        except Exception:
            return False
