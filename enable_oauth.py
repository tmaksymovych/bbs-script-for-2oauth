from pathlib import Path
import pandas as pd
from playwright.sync_api import Page, sync_playwright

BASE_URL = "https://b-o.bbs.ua/bo-bbs"
LOGIN_URL = f"{BASE_URL}/app/login"
USER_DATA_DIR = "./browser_profile"

HEADLESS = False
SLOW_MO = 100

USERNAME = "tmaksymovych"
PASSWORD = "dm202606"


def ensure_logged_in(page: Page) -> None:
    """Проверка и сохранение авторизации в профиле браузера."""
    print("Проверка авторизации...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    if "login" not in page.url.lower() and not page.locator("input[type='password']").is_visible():
        print("Сессия активна: вход выполнен.")
        return

    print("Требуется авторизация...")
    user_input = page.locator("input:not([type='hidden']):not([type='password'])").first
    pass_input = page.locator("input[type='password']").first

    user_input.wait_for(state="visible", timeout=20000)
    user_input.fill(USERNAME)
    pass_input.fill(PASSWORD)
    page.get_by_role("button", name="Вход").click()

    try:
        otp_input = page.locator("input:not([type='hidden']):not([type='password'])").first
        otp_input.wait_for(state="visible", timeout=6000)
        otp_code = input("\n>>> Введите разовый код подтверждения из почты: ").strip()
        otp_input.fill(otp_code)
        page.get_by_role("button", name="Подтвердить").click()
        page.wait_for_load_state("networkidle")
    except Exception:
        pass

    print("Авторизация успешно завершена.")


def go_to_search(page: Page) -> None:
    """Переход в меню Контрагенти -> Пошук."""
    burger_btn = page.locator("header button, .v-app-bar__nav-icon, button:has(svg)").first
    try:
        if not page.get_by_text("Контрагенти", exact=True).is_visible(timeout=2000):
            burger_btn.click()
    except Exception:
        pass

    cagents_btn = page.get_by_text("Контрагенти", exact=True)
    cagents_btn.wait_for(state="visible", timeout=15000)
    cagents_btn.click()

    search_btn = page.get_by_text("Пошук", exact=True)
    search_btn.wait_for(state="visible", timeout=10000)
    search_btn.click()
    page.wait_for_load_state("networkidle")
    print("Раздел 'Пошук' открыт.")


def search_cagent(page: Page, full_name: str) -> None:
    """Поиск контрагента по ФИО."""
    print(f"Поиск контрагента: {full_name}")
    search_input = page.locator(
        "xpath=(//*[contains(text(), 'ПІБ') and contains(text(), 'організації')]/following::input[not(@type='hidden')])[1]"
    )
    search_input.wait_for(state="visible", timeout=15000)
    search_input.fill("")
    search_input.fill(full_name)
    search_input.press("Enter")

    try:
        page.locator("button, input[type='button'], input[type='submit']").filter(has_text="Пошук").first.click(timeout=1500)
    except Exception:
        pass
    page.wait_for_load_state("networkidle")


def open_user_card(page: Page) -> None:
    """Переход на вкладку 'Користувач'."""
    print("Открытие роли 'Користувач'...")
    user_link = page.locator("xpath=//tr[td]//*[contains(text(), 'Користувач')] | //a[contains(text(), 'Користувач')]").first
    user_link.wait_for(state="visible", timeout=15000)
    user_link.click()
    page.wait_for_load_state("networkidle")


def click_edit_user(page: Page) -> None:
    """Точный клик по ссылке 'Редагувати' и ожидание перехода в режим формы."""
    print("Нажатие кнопки 'Редагувати'...")
    
    # Точный ID кнопки из полученного HTML
    edit_btn = page.locator("[id='cagentForm:editButton'], a:has-text('Редагувати')").first
    edit_btn.wait_for(state="visible", timeout=15000)
    edit_btn.click()

    # Ждем, пока откроется режим редактирования
    page.locator("xpath=//*[contains(text(), 'Редагування контрагента')] | //select | //input[@type='radio']").first.wait_for(state="visible", timeout=15000)
    page.wait_for_load_state("networkidle")
    print("Форма редактирования успешно загружена.")


def configure_2fa_settings(page: Page) -> None:
    """Включение 2FA, выбор 30 дней и Email."""
    print("Настройка параметров 2FA...")

    # 1. Точный выбор конкретной строки таблицы без конфликтов с родительскими тегами
    twofa_row = page.locator("tr").filter(has_text="Увімкнути двофакторну аутентифікацію").last
    twofa_row.wait_for(state="visible", timeout=15000)

    tak_label = twofa_row.locator("label:has-text('так')").first
    tak_input = twofa_row.locator("input[type='radio']").first

    # Включаем радиокнопку, если не активна
    if not tak_input.is_checked():
        print("Включение переключателя 'так'...")
        if tak_label.is_visible():
            tak_label.click()
        else:
            tak_input.check(force=True)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)

    # 2. Выбор "30 днів" в строке времени жизни устройства
    lifetime_row = page.locator("tr").filter(has_text="Час життя довіреного пристрою").last
    lifetime_select = lifetime_row.locator("select").first
    
    lifetime_select.wait_for(state="visible", timeout=10000)
    try:
        lifetime_select.select_option(label="30 днів")
    except Exception:
        lifetime_select.select_option(value="30")
    print("Установлено: 30 днів")

    # 3. Выбор "Email" в строке способа отправки
    delivery_row = page.locator("tr").filter(has_text="Спосіб відправлення коду 2FA").last
    delivery_select = delivery_row.locator("select").first
    
    delivery_select.wait_for(state="visible", timeout=10000)
    try:
        delivery_select.select_option(label="Email")
    except Exception:
        delivery_select.select_option(value="EMAIL")
    print("Установлено: Email")

    print("Параметры 2FA успешно обновлены.")


def save_user_changes(page: Page) -> None:
    print("Сохранение изменений...")
    
    # 1. Скроллим в самый низ
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(300)

    # 2. Ищем видимую кнопку "Зберегти" строго внутри cagentForm (игнорируя модалки)
    save_btn = (
        page.locator("#cagentForm")
        .locator("a, input, button")
        .filter(has_text="Зберегти")
        .locator("visible=true")
        .first
    )

    save_btn.scroll_into_view_if_needed()
    save_btn.wait_for(state="visible", timeout=10000)
    
    # Кликаем с force=True для надежного срабатывания JSF-обработчика
    save_btn.click(force=True)

    # 3. Ждем возврата страницы в режим просмотра (исчезновения режима редактирования)
    page.wait_for_load_state("networkidle")
    page.locator("xpath=//*[contains(text(), 'Перегляд контрагента')]").wait_for(state="visible", timeout=15000)
    
    print("Изменения успешно сохранены (возврат в режим просмотра).")


def main() -> None:
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=HEADLESS,
            slow_mo=SLOW_MO,
            no_viewport=True,
            args=["--start-maximized"]
        )

        page = context.pages[0] if context.pages else context.new_page()

        ensure_logged_in(page)
        go_to_search(page)
        search_cagent(page, full_name="ПЕТРІЙ ОЛЕКСАНДР АНАТОЛІЙОВИЧ")
        open_user_card(page)
        
        # Редактирование и сохранение
        click_edit_user(page)
        configure_2fa_settings(page)
        save_user_changes(page)

        print("\nГотово! Проверьте карточку в браузере.")
        input("Нажмите Enter в терминале, чтобы завершить...\n")
        context.close()


if __name__ == "__main__":
    main()