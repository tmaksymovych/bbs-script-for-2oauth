from playwright.sync_api import Page, sync_playwright

BASE_URL = "https://b-o.bbs.ua/bo-bbs"
LOGIN_URL = f"{BASE_URL}/app/login"
USER_DATA_DIR = "./browser_profile"

HEADLESS = False
SLOW_MO = 100

USERNAME = "tmaksymovych"
PASSWORD = "dm202606"


def ensure_logged_in(page: Page) -> None:
    print("Проверка авторизации...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    if "login" not in page.url.lower() and not page.locator("input[type='password']").is_visible():
        print("Сессия активна.")
        return

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


def go_to_search(page: Page) -> None:
    """Переход в меню Контрагенти -> Пошук через точные селекторы меню."""
    burger_btn = page.locator("button[aria-label='Open drawer'], header button").first
    cagents_menu_item = page.locator("#left-menu #cagentMenuLink, #cagentMenuLink").first

    try:
        if not cagents_menu_item.is_visible():
            burger_btn.click()
            page.wait_for_timeout(400)
    except Exception:
        pass

    cagents_menu_item.wait_for(state="visible", timeout=15000)
    
    search_sub_item = page.locator("#left-menu #cagentSearchMenuLink, #cagentSearchMenuLink").first
    if not search_sub_item.is_visible():
        cagents_menu_item.click()
        page.wait_for_timeout(300)

    search_sub_item.wait_for(state="visible", timeout=10000)
    search_sub_item.click()
    page.wait_for_load_state("networkidle")


def search_cagent(page: Page, full_name: str) -> None:
    print(f"Поиск: {full_name}")
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


def click_edit_user(page: Page) -> None:
    edit_btn = page.locator("[id='cagentForm:editButton'], a:has-text('Редагувати')").first
    edit_btn.wait_for(state="visible", timeout=15000)
    edit_btn.click()

    page.locator("xpath=//*[contains(text(), 'Редагування контрагента')] | //select | //input[@type='radio']").first.wait_for(state="visible", timeout=15000)
    page.wait_for_load_state("networkidle")


def disable_2fa(page: Page) -> None:
    twofa_row = page.locator("tr").filter(has_text="Увімкнути двофакторну аутентифікацію").last
    twofa_row.wait_for(state="visible", timeout=15000)

    ni_label = twofa_row.locator("label:has-text('ні')").first
    ni_input = twofa_row.locator("input[type='radio']").last

    if not ni_input.is_checked():
        if ni_label.is_visible():
            ni_label.click()
        else:
            ni_input.check(force=True)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(400)
        print("  -> 2FA переключено в положение 'ні'")
    else:
        print("  -> 2FA уже выключено")


def save_user_changes(page: Page) -> None:
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(300)

    save_btn = (
        page.locator("#cagentForm")
        .locator("a, input, button")
        .filter(has_text="Зберегти")
        .locator("visible=true")
        .first
    )

    save_btn.scroll_into_view_if_needed()
    save_btn.wait_for(state="visible", timeout=10000)
    save_btn.click(force=True)

    page.wait_for_load_state("networkidle")
    page.locator("xpath=//*[contains(text(), 'Перегляд контрагента')]").wait_for(state="visible", timeout=15000)
    print("  -> Изменения успешно сохранены.")


def process_cagent_by_name(page: Page, full_name: str) -> None:
    """Ищет контрагента, проверяет количество учетных записей 'Користувач' и обрабатывает каждую."""
    go_to_search(page)
    search_cagent(page, full_name=full_name)

    # Ищем ссылки с ролью 'Користувач' в таблице результатов
    user_links = page.locator("xpath=//tr[td]//*[contains(text(), 'Користувач')] | //a[contains(text(), 'Користувач')]")
    user_count = user_links.count()

    if user_count == 0:
        print(f"[ИНФО] У контрагента '{full_name}' нет учетной записи 'Користувач' (только клиент/застрахованное лицо). Пропускаем.")
        return

    if user_count == 1:
        print("[ИНФО] Найдена 1 карточка пользователя. Выполняется обработка...")
        user_links.first.click()
        page.wait_for_load_state("networkidle")
        click_edit_user(page)
        disable_2fa(page)
        save_user_changes(page)
        return

    # Если найдено 2 или более карточек
    print(f"\n[ВНИМАНИЕ] Найдено {user_count} карточек с ролью 'Користувач' для '{full_name}'!")
    
    for i in range(user_count):
        print(f"\n--- Обработка карточки [{i + 1}/{user_count}] ---")
        
        # Для 2-й и последующих карточек возвращаемся в поиск заново
        if i > 0:
            go_to_search(page)
            search_cagent(page, full_name=full_name)
            user_links = page.locator("xpath=//tr[td]//*[contains(text(), 'Користувач')] | //a[contains(text(), 'Користувач')]")

        # Открываем i-ю запись
        user_links.nth(i).click()
        page.wait_for_load_state("networkidle")

        click_edit_user(page)
        disable_2fa(page)
        save_user_changes(page)
        print(f"Карточка [{i + 1}/{user_count}] завершена.")

    print(f"\n[УСПЕХ] Все {user_count} карточки для '{full_name}' успешно обработаны.")


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

        while True:
            name = input("\n>>> Введите ФИО контрагента (или Enter для выхода): ").strip()
            if not name:
                break

            try:
                process_cagent_by_name(page, full_name=name)
            except Exception as e:
                print(f"[ОШИБКА] При обработке '{name}': {e}")
                go_to_search(page)

        context.close()


if __name__ == "__main__":
    main()