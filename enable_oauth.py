from datetime import datetime
from pathlib import Path
import re
import pandas as pd
from playwright.sync_api import Page, sync_playwright

BASE_URL = "https://b-o.bbs.ua/bo-bbs"
LOGIN_URL = f"{BASE_URL}/app/login"
USER_DATA_DIR = "./browser_profile"
EXCEL_FILE = "users.xlsx"
ERRORS_EXCEL_FILE = "validation_errors.xlsx"

# Браузер працює на максимальній швидкості без штучних пауз
HEADLESS = False
SLOW_MO = 0

USERNAME = "tmaksymovych"
PASSWORD = "dm202606"


def ensure_logged_in(page: Page) -> None:
    """Перевірка та збереження авторизації."""
    print("Перевірка авторизації...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")

    if "login" not in page.url.lower() and not page.locator("input[type='password']").is_visible():
        print("Сесія активна.")
        return

    print("Потрібна авторизація...")
    user_input = page.locator("input:not([type='hidden']):not([type='password'])").first
    pass_input = page.locator("input[type='password']").first

    user_input.wait_for(state="visible", timeout=20000)
    user_input.fill(USERNAME)
    pass_input.fill(PASSWORD)
    page.get_by_role("button", name="Вход").click()

    try:
        otp_input = page.locator("input:not([type='hidden']):not([type='password'])").first
        otp_input.wait_for(state="visible", timeout=5000)
        otp_code = input("\n>>> Введіть код із пошти: ").strip()
        otp_input.fill(otp_code)
        page.get_by_role("button", name="Подтвердить").click()
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass


def go_to_search(page: Page) -> None:
    """Миттєвий перехід у розділ пошуку."""
    burger_btn = page.locator("button[aria-label='Open drawer'], header button").first
    cagents_menu_item = page.locator("#left-menu #cagentMenuLink, #cagentMenuLink").first

    try:
        if not cagents_menu_item.is_visible():
            burger_btn.click()
    except Exception:
        pass

    cagents_menu_item.wait_for(state="visible", timeout=10000)

    search_sub_item = page.locator("#left-menu #cagentSearchMenuLink, #cagentSearchMenuLink").first
    if not search_sub_item.is_visible():
        cagents_menu_item.click()

    search_sub_item.wait_for(state="visible", timeout=10000)
    search_sub_item.click()
    page.wait_for_load_state("domcontentloaded")


def search_cagent(page: Page, full_name: str) -> None:
    """Миттєвий пошук без затримок."""
    search_input = page.locator(
        "xpath=(//*[contains(text(), 'ПІБ') and contains(text(), 'організації')]/following::input[not(@type='hidden')])[1]"
    )
    search_input.wait_for(state="visible", timeout=10000)
    search_input.fill(full_name)
    search_input.press("Enter")

    try:
        page.locator("button, input[type='button'], input[type='submit']").filter(has_text="Пошук").first.click(timeout=400)
    except Exception:
        pass
    page.wait_for_load_state("domcontentloaded")


def get_matching_user_rows(page: Page, full_name: str):
    """Фільтрація рядків строго за ПІБ та наявністю ролі 'Користувач'."""
    clean_name = " ".join(full_name.strip().split())
    name_pattern = re.compile(r"\s+".join(map(re.escape, clean_name.split())), re.IGNORECASE)

    return (
        page.locator("table tr")
        .filter(has=page.locator("td"))
        .filter(has_text=name_pattern)
        .filter(has_text="Користувач")
    )


def click_edit_user(page: Page) -> None:
    """Клік на 'Редагувати'."""
    edit_btn = page.locator("[id='cagentForm:editButton'], a:has-text('Редагувати')").first
    edit_btn.wait_for(state="visible", timeout=10000)
    edit_btn.click()
    page.locator("xpath=//*[contains(text(), 'Редагування контрагента')] | //select | //input[@type='radio']").first.wait_for(state="visible", timeout=10000)


def configure_2fa_settings(page: Page) -> None:
    """Виставлення 2FA: так / 30 днів / Email."""
    twofa_row = page.locator("tr").filter(has_text="Увімкнути двофакторну аутентифікацію").last
    twofa_row.wait_for(state="visible", timeout=10000)

    tak_label = twofa_row.locator("label:has-text('так')").first
    tak_input = twofa_row.locator("input[type='radio']").first

    if not tak_input.is_checked():
        if tak_label.is_visible():
            tak_label.click()
        else:
            tak_input.check(force=True)

    lifetime_row = page.locator("tr").filter(has_text="Час життя довіреного пристрою").last
    lifetime_select = lifetime_row.locator("select").first
    lifetime_select.wait_for(state="visible", timeout=8000)
    try:
        lifetime_select.select_option(label="30 днів")
    except Exception:
        lifetime_select.select_option(value="30")

    delivery_row = page.locator("tr").filter(has_text="Спосіб відправлення коду 2FA").last
    delivery_select = delivery_row.locator("select").first
    delivery_select.wait_for(state="visible", timeout=8000)
    try:
        delivery_select.select_option(label="Email")
    except Exception:
        delivery_select.select_option(value="EMAIL")


def save_user_changes_with_check(page: Page) -> tuple[bool, str]:
    """
    Фокусує увагу на збереженні: прокручує вниз, робить коротку паузу для видимості
    та фіксує результат/помилку валідації.
    """
    save_btn = (
        page.locator("#cagentForm")
        .locator("a, input, button")
        .filter(has_text="Зберегти")
        .locator("visible=true")
        .first
    )

    save_btn.scroll_into_view_if_needed()
    save_btn.wait_for(state="visible", timeout=8000)

    # Коротка пауза, щоб встигнути побачити заповнену картку перед кліком
    page.wait_for_timeout(350)
    save_btn.click(force=True)
    
    page.wait_for_load_state("networkidle")
    # Пауза після збереження для фіксації червоних повідомлень валідації
    page.wait_for_timeout(350)

    # 1. Успішне збереження
    if page.locator("xpath=//*[contains(text(), 'Перегляд контрагента')]").is_visible():
        return True, ""

    # 2. Зчитування помилок валідації
    error_locators = page.locator(
        "xpath=//*[contains(@style, 'color: red') or contains(@style, 'color:red') or contains(text(), 'SMS-підтвердження') or contains(text(), 'Введений ІПН') or contains(text(), 'помилка')]"
    )

    error_messages = []
    for i in range(error_locators.count()):
        el = error_locators.nth(i)
        if el.is_visible():
            txt = el.inner_text().strip()
            if txt and txt not in error_messages and "двофакторну" not in txt.lower():
                error_messages.append(txt)

    full_error_text = " | ".join(error_messages) if error_messages else "Помилка валідації форми"

    # 3. Швидке скидання через 'Відмінити'
    try:
        cancel_btn = page.locator("#cagentForm").locator("a, input, button").filter(has_text="Відмінити").locator("visible=true").first
        if cancel_btn.is_visible():
            cancel_btn.click(force=True)
            page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass

    return False, full_error_text


def save_errors_to_excel(errors_list: list[dict]) -> None:
    if not errors_list:
        return
    df_err = pd.DataFrame(errors_list)
    df_err.to_excel(ERRORS_EXCEL_FILE, index=False)


def process_cagent(page: Page, full_name: str) -> tuple[str, str]:
    clean_name = " ".join(full_name.strip().split())
    go_to_search(page)
    search_cagent(page, full_name=clean_name)

    matching_rows = get_matching_user_rows(page, clean_name)
    user_count = matching_rows.count()

    if user_count == 0:
        name_pattern = re.compile(r"\s+".join(map(re.escape, clean_name.split())), re.IGNORECASE)
        any_row = page.locator("table tr").filter(has=page.locator("td")).filter(has_text=name_pattern)
        if any_row.count() > 0:
            return "skipped", "Контрагента знайдено, але немає ролі 'Користувач'"
        return "skipped", "Контрагента з таким ПІБ не знайдено"

    if user_count == 1:
        user_link = matching_rows.first.locator("xpath=.//*[contains(text(), 'Користувач')]").first
        user_link.click()
        page.wait_for_load_state("domcontentloaded")
        click_edit_user(page)
        configure_2fa_settings(page)
        success, err_msg = save_user_changes_with_check(page)
        if not success:
            return "validation_error", err_msg
        return "done", ""

    print(f"  -> Знайдено {user_count} карток")
    card_results = []
    has_validation_error = False

    for i in range(user_count):
        if i > 0:
            go_to_search(page)
            search_cagent(page, full_name=clean_name)
            matching_rows = get_matching_user_rows(page, clean_name)

        user_link = matching_rows.nth(i).locator("xpath=.//*[contains(text(), 'Користувач')]").first
        user_link.click()
        page.wait_for_load_state("domcontentloaded")
        click_edit_user(page)
        configure_2fa_settings(page)
        
        success, err_msg = save_user_changes_with_check(page)
        if success:
            card_results.append(f"Картка {i + 1}: OK")
        else:
            has_validation_error = True
            card_results.append(f"Картка {i + 1}: ПОМИЛКА ({err_msg})")

    full_details = " | ".join(card_results)
    if has_validation_error:
        return "validation_error", full_details

    return f"done ({user_count} cards)", ""


def main() -> None:
    excel_path = Path(EXCEL_FILE)
    if not excel_path.exists():
        print(f"Помилка: Файл '{EXCEL_FILE}' не знайдено.")
        return

    df = pd.read_excel(EXCEL_FILE)
    if "ПІБ" not in df.columns:
        print("Помилка: У файлі Excel відсутня колонка 'ПІБ'.")
        return

    if "Status" not in df.columns:
        df["Status"] = ""
    if "Error_Msg" not in df.columns:
        df["Error_Msg"] = ""

    validation_errors_list = []
    if Path(ERRORS_EXCEL_FILE).exists():
        try:
            validation_errors_list = pd.read_excel(ERRORS_EXCEL_FILE).to_dict(orient="records")
        except Exception:
            pass

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

        total = len(df)
        for idx, row in df.iterrows():
            current_status = str(row.get("Status", "")).strip().lower()
            if current_status.startswith("done"):
                continue

            name = str(row["ПІБ"]).strip()
            if not name or name.lower() == "nan":
                continue

            print(f"\n[{idx + 1}/{total}] {name}...", end=" ")

            try:
                status, err_msg = process_cagent(page, full_name=name)
                df.at[idx, "Status"] = status
                df.at[idx, "Error_Msg"] = err_msg

                if status == "validation_error":
                    print(f"ПОМИЛКА ВАЛІДАЦІЇ: {err_msg}")
                    validation_errors_list.append({
                        "ПІБ": name,
                        "Помилка": err_msg,
                        "Час": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    save_errors_to_excel(validation_errors_list)
                else:
                    print(f"OK ({status})")

            except Exception as e:
                df.at[idx, "Status"] = "error"
                df.at[idx, "Error_Msg"] = str(e)[:150]
                print(f"ЗБІЙ: {e}")
                try:
                    page.screenshot(path=f"err_{idx + 1}.png")
                    go_to_search(page)
                except Exception:
                    pass

            df.to_excel(EXCEL_FILE, index=False)

        print("\nОбробку списку завершено.")
        if validation_errors_list:
            print(f"Звіт помилок збережено у: {ERRORS_EXCEL_FILE}")

        input("Натисніть Enter, щоб закрити вікно...\n")
        context.close()


if __name__ == "__main__":
    main()