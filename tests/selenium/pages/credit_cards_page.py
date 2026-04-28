from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class CreditCardsPage:
    URL = "https://www.americanexpress.com/"
    CREDIT_CARDS_NAV = (By.XPATH, "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'credit card')]")
    CARD_TILES = (By.CSS_SELECTOR, "[class*='card-tile'], [class*='CardTile'], [data-testid*='card']")
    FILTER_CHIPS = (By.CSS_SELECTOR, "[class*='filter-chip'], [class*='FilterChip'], [role='tab']")
    VIEW_DETAILS_LINKS = (By.XPATH, "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'view detail') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'learn more')]")
    CARD_BENEFITS = (By.XPATH, "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'benefit') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'reward') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'annual fee')]")
    LOGIN_BUTTON = (By.XPATH, "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'log in') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'sign in')]")
    CARD_HIGHLIGHTS = (By.XPATH, "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'featured benefit') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'highlight')]")

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)

    def open(self):
        self.driver.get(self.URL)

    def navigate_to_credit_cards(self):
        self.open()
        try:
            cc_link = self.wait.until(EC.element_to_be_clickable(self.CREDIT_CARDS_NAV))
            cc_link.click()
        except Exception:
            self.driver.get("https://www.americanexpress.com/us/credit-cards/")

    def get_card_tiles(self):
        return self.driver.find_elements(*self.CARD_TILES)

    def get_filter_chips(self):
        return self.driver.find_elements(*self.FILTER_CHIPS)

    def apply_filter(self, filter_name: str):
        chips = self.get_filter_chips()
        for chip in chips:
            if filter_name.lower() in chip.text.lower():
                chip.click()
                return True
        return False

    def click_first_card_details(self):
        links = self.driver.find_elements(*self.VIEW_DETAILS_LINKS)
        if links:
            links[0].click()
            return True
        tiles = self.get_card_tiles()
        if tiles:
            tiles[0].click()
            return True
        return False

    def get_card_benefits_elements(self):
        return self.driver.find_elements(*self.CARD_BENEFITS)

    def is_login_button_visible(self):
        elements = self.driver.find_elements(*self.LOGIN_BUTTON)
        return len(elements) > 0

    def get_card_highlights(self):
        return self.driver.find_elements(*self.CARD_HIGHLIGHTS)

    def current_url(self):
        return self.driver.current_url

    def page_title(self):
        return self.driver.title
