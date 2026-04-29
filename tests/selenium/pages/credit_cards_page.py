from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class ProductsPage:
    URL = "https://ecommerce-playground.lambdatest.io/"
    SHOP_NAV = (By.XPATH, "//a[contains(., 'Shop')] | //span[contains(., 'Category')]")
    CARD_TILES = (By.CSS_SELECTOR, "[class*='card-tile'], [class*='CardTile'], [data-testid*='card']")
    FILTER_CHIPS = (By.CSS_SELECTOR, ".list-group-item, [class*='filter-chip'], [role='tab']")
    VIEW_DETAILS_LINKS = (By.XPATH, "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'view detail') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'learn more')]")
    CARD_BENEFITS = (By.XPATH, "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'benefit') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'reward') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'annual fee')]")
    LOGIN_BUTTON = (By.XPATH, "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'log in') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'sign in')]")
    CARD_HIGHLIGHTS = (By.XPATH, "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'featured benefit') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'highlight')]")
    COOKIE_BANNER_ACCEPT = (
        By.XPATH,
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'accept')]"
        "|//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'agree')]"
        "|//button[contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'accept')]",
    )
    LOGIN_GATE = (
        By.XPATH,
        "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'log in to continue')]"
        "|//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'sign in to continue')]",
    )

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)

    def open(self):
        self.driver.get(self.URL)

    def wait_for_ready_state(self):
        self.wait.until(lambda current_driver: current_driver.execute_script("return document.readyState") == "complete")

    def dismiss_common_overlays(self):
        try:
            buttons = self.driver.find_elements(*self.COOKIE_BANNER_ACCEPT)
            for button in buttons[:2]:
                if button.is_displayed():
                    self.safe_click(button)
                    break
        except Exception:
            pass

    def scroll_to_element(self, element):
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
            element,
        )

    def safe_click(self, element):
        self.scroll_to_element(element)
        try:
            self.wait.until(lambda _: element.is_displayed() and element.is_enabled())
            element.click()
            return True
        except (ElementClickInterceptedException, StaleElementReferenceException):
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception:
                return False
        except Exception:
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception:
                return False

    def navigate_to_credit_cards(self):
        self.open()
        self.wait_for_ready_state()
        self.dismiss_common_overlays()
        try:
            shop_link = self.wait.until(EC.element_to_be_clickable(self.SHOP_NAV))
            self.safe_click(shop_link)
        except Exception:
            self.driver.get("https://ecommerce-playground.lambdatest.io/index.php?route=product/category&path=57")
        self.wait_for_ready_state()
        self.dismiss_common_overlays()

    def get_card_tiles(self):
        return self.driver.find_elements(*self.CARD_TILES)

    def get_filter_chips(self):
        return self.driver.find_elements(*self.FILTER_CHIPS)

    def apply_filter(self, filter_name: str):
        chips = self.get_filter_chips()
        for chip in chips:
            if filter_name.lower() in chip.text.lower():
                previous_url = self.current_url()
                previous_count = len(self.get_card_tiles())
                if not self.safe_click(chip):
                    continue
                self.wait.until(
                    lambda current_driver: current_driver.current_url != previous_url
                    or len(self.get_card_tiles()) > 0
                )
                return len(self.get_card_tiles()) > 0 or previous_count > 0
        return False

    def click_first_card_details(self):
        links = self.driver.find_elements(*self.VIEW_DETAILS_LINKS)
        if links:
            return self.safe_click(links[0])
        tiles = self.get_card_tiles()
        if tiles:
            return self.safe_click(tiles[0])
        return False

    def get_card_benefits_elements(self):
        return self.driver.find_elements(*self.CARD_BENEFITS)

    def is_login_button_visible(self):
        elements = self.driver.find_elements(*self.LOGIN_BUTTON)
        return len(elements) > 0

    def is_login_gate_present(self):
        return len(self.driver.find_elements(*self.LOGIN_GATE)) > 0

    def get_card_highlights(self):
        return self.driver.find_elements(*self.CARD_HIGHLIGHTS)

    def has_guest_browsing_content(self):
        return bool(self.get_card_highlights() or self.get_card_tiles())

    def current_url(self):
        return self.driver.current_url

    def page_title(self):
        return self.driver.title
