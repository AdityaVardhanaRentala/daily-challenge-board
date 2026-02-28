def fetch_dailies():
    general = []
    roles = {
        "bounty": [],
        "trader": [],
        "collector": [],
        "moonshiner": [],
        "naturalist": []
    }

    try:
        response = requests.get("https://rdo-dailies.com/", timeout=10)
        lang_response = requests.get(
            "https://rdo-dailies.com/website/languages/en.json",
            timeout=10
        )

        soup = BeautifulSoup(response.text, "html.parser")
        lang_data = lang_response.json()

        containers = soup.find_all("div", class_="daily-container")

        for index, container in enumerate(containers):
            rows = container.find_all("div", class_="rows")
            formatted_rows = []

            for row in rows:
                goal = row.find("p", class_="daily-goal")
                text = row.find("p", class_="daily-general")

                if not goal or not text:
                    continue

                quantity = goal.get("data-goal")
                key = text.get("data-text")

                if not quantity or not key:
                    continue

                readable = lang_data.get(key, key)
                formatted = format_quantity(quantity, readable)
                formatted_rows.append(formatted)

            # Assign by fixed order
            if index == 0:
                general = formatted_rows
            elif index == 1:
                roles["bounty"] = formatted_rows[:3]
            elif index == 2:
                roles["trader"] = formatted_rows[:3]
            elif index == 3:
                roles["collector"] = formatted_rows[:3]
            elif index == 4:
                roles["moonshiner"] = formatted_rows[:3]
            elif index == 5:
                roles["naturalist"] = formatted_rows[:3]

    except Exception as e:
        print("Error fetching dailies:", e)

    return general, roles
